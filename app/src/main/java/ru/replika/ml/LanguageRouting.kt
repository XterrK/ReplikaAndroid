package ru.replika.ml

import com.k2fsa.sherpa.onnx.SpokenLanguageIdentification
import com.k2fsa.sherpa.onnx.SpokenLanguageIdentificationConfig
import com.k2fsa.sherpa.onnx.SpokenLanguageIdentificationWhisperConfig
import kotlinx.coroutines.CancellationException
import org.json.JSONArray
import org.json.JSONObject
import ru.replika.domain.*

/** Whisper tiny spoken-language identification (sherpa-onnx). One native instance per decision. */
class LanguageIdentifier(models: ModelManager,threads: Int): AutoCloseable {
 private val lid=SpokenLanguageIdentification(config=SpokenLanguageIdentificationConfig(
  whisper=SpokenLanguageIdentificationWhisperConfig(
   encoder=models.file("${ModelManager.LID_GROUP}/tiny-encoder.int8.onnx").path,
   decoder=models.file("${ModelManager.LID_GROUP}/tiny-decoder.int8.onnx").path,tailPaddings=-1),
  numThreads=MlPolicy.threads(threads)))
 fun identify(samples: FloatArray): String {
  val stream=lid.createStream()
  try { stream.acceptWaveform(samples,16000);return lid.compute(stream) } finally { stream.release() }
 }
 override fun close()=lid.release()
}

/**
 * Chooses the recognition language before ASR. It only reads audio: VAD, chunks and diarization are
 * unchanged, and a Russian decision leaves the GigaAM path byte-for-byte as before.
 * Any failure (missing model, native error) falls back to Russian, the priority language.
 */
object LanguageRouting {
 suspend fun decide(models: ModelManager,mode: LanguageMode,perSegment: Boolean,chunks: List<Span>,threads: Int,
  read: suspend (Long,Long)->FloatArray): LanguageDecision {
  mode.forced?.let { forced -> return LanguageDecision(mode,false,forced,chunks.map { forced },reason="forced") }
  if(chunks.isEmpty()) return LanguageDecision(mode,perSegment,AsrLanguage.RU,emptyList(),reason="no_speech")
  if(!models.groupReady(ModelManager.LID_GROUP))
   return LanguageDecision(mode,perSegment,AsrLanguage.RU,chunks.map { AsrLanguage.RU },reason="lid_unavailable")
  return try {
   LanguageIdentifier(models,threads).use { lid ->
    val labels=LanguagePlan.probes(chunks).map { probe ->
     val parts=probe.map { read(it.startMs,it.endMs) }
     val audio=FloatArray(parts.sumOf { it.size });var offset=0
     for(part in parts) { part.copyInto(audio,offset);offset+=part.size }
     lid.identify(audio)
    }
    val file=LanguagePlan.vote(labels.map(AsrLanguage::fromWhisper))
    val perChunk=if(!perSegment) chunks.map { file } else chunks.map { chunk ->
     val duration=chunk.endMs-chunk.startMs
     LanguagePlan.segmentLanguage(if(duration<LanguagePlan.SEGMENT_MIN_MS) null else AsrLanguage.fromWhisper(lid.identify(read(chunk.startMs,chunk.endMs))),duration,file)
    }
    LanguageDecision(mode,perSegment,file,perChunk,labels,reason=if(labels.isEmpty()) "too_little_speech" else "whisper_vote")
   }
  } catch(e: CancellationException) { throw e
  } catch(e: OutOfMemoryError) { throw e
  } catch(e: Throwable) {
   LanguageDecision(mode,perSegment,AsrLanguage.RU,chunks.map { AsrLanguage.RU },reason="lid_failed:"+e.javaClass.simpleName)
  }
 }

 fun json(decision: LanguageDecision): JSONObject = JSONObject().put("mode",decision.mode.wireId)
  .put("perSegment",decision.perSegment).put("fileLanguage",decision.fileLanguage.wireId)
  .put("summary",decision.summary).put("reason",decision.reason)
  .put("probeLabels",JSONArray(decision.probeLabels))
  .put("chunkLanguages",JSONArray(decision.chunkLanguages.map { it.wireId }))
  .put("policy","first 30 s of VAD speech, up to 3 probes x 10 s, strict 'en' majority else ru; chunks < 1.5 s inherit the file decision")
}
