package ru.replika

import android.os.Build
import android.os.Debug
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.k2fsa.sherpa.onnx.*
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assume
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.domain.*
import ru.replika.ml.*
import java.io.File
import java.security.MessageDigest
import kotlin.math.min
import kotlin.math.roundToLong

/** Real opt-in comparisons. No synthetic transcript, no reference-dependent quality assertions. */
@RunWith(AndroidJUnit4::class)
class MLComparisonTest {
 private val app get()=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
 private fun hash(file: File)=MessageDigest.getInstance("SHA-256").let { digest ->
  file.inputStream().use { input -> val block=ByteArray(65536);while(true) { val n=input.read(block);if(n<0) break;digest.update(block,0,n) } }
  digest.digest().joinToString("") { "%02x".format(it) }
 }
 private fun metadata()=JSONObject().put("device","${Build.MANUFACTURER} ${Build.MODEL}").put("api",Build.VERSION.SDK_INT)
  .put("abi",Build.SUPPORTED_ABIS.joinToString()).put("threads",2).put("sampleRate",16000)
  .put("WER","N/A; no independently annotated reference").put("CER","N/A; no independently annotated reference")
  .put("peakMemory","N/A; PSS observations are snapshots")
 private fun save(name: String,data: JSONObject)=File(app.filesDir,name).writeText(data.toString(2))
 private fun pss(): Int { val m=Debug.MemoryInfo();Debug.getMemoryInfo(m);return m.totalPss }
 private fun diar(count: Int,threshold: Float=0.5f)=OfflineSpeakerDiarization(config=OfflineSpeakerDiarizationConfig(
  segmentation=OfflineSpeakerSegmentationModelConfig(pyannote=OfflineSpeakerSegmentationPyannoteModelConfig(app.models.file("diar/segmentation.onnx").path),numThreads=2),
  embedding=SpeakerEmbeddingExtractorConfig(model=app.models.file("diar/embedding.onnx").path,numThreads=2),
  clustering=FastClusteringConfig(numClusters=count,threshold=threshold)))
 private fun spansJson(spans: List<Span>)=JSONArray().also { a -> spans.forEach { a.put(JSONObject().put("startMs",it.startMs).put("endMs",it.endMs)) } }
 private fun turnsJson(turns: List<Turn>)=JSONArray().also { a -> turns.forEach { a.put(JSONObject().put("startMs",it.startMs).put("endMs",it.endMs).put("speakerId",it.speaker)) } }

 @Test fun directAsrSameInputColdThenWarm()=runBlocking {
  val source=File(app.filesDir,"integration-example.wav")
  Assume.assumeTrue("Stage verified models and official Russian WAV",source.exists() && app.models.file("whisper-tiny/ggml-tiny.bin").exists())
  app.models.gate.withLock {
   app.models.requireReady("giga-v2");app.models.requireReady("whisper-tiny")
   val pcm=AudioDecoder.decode(source.path,File(app.cacheDir,"comparison-asr.pcm"))
   try {
    val samples=AudioDecoder.read(pcm.file,0,pcm.samples)
    val result=metadata().put("audioSha256",hash(source)).put("audioMs",pcm.durationMs)
     .put("scope","direct ASR, identical decoded full waveform; excludes VAD, diarization, decoding")
     .put("coldDefinition","new engine, first inference; filesystem cache uncontrolled; NOT reboot-cold")
    val backends=JSONArray();result.put("backends",backends)
    for(backend in listOf("giga-v2","whisper-tiny")) {
     val loadStart=SystemClock.elapsedRealtime()
     val engine: AsrEngine=if(backend=="giga-v2") GigaAmEngine(app.models) else WhisperEngine(app.models)
     val loadMs=SystemClock.elapsedRealtime()-loadStart
     val runs=JSONArray()
     val row=JSONObject().put("backend",engine.source).put("loadMs",loadMs).put("runs",runs)
      .put("modelBytes",app.models.statuses().filter { it.id==backend }.sumOf { it.bytes })
     backends.put(row)
     engine.use { repeat(3) { index ->
      val start=SystemClock.elapsedRealtime();val text=engine.recognize(samples);val elapsed=SystemClock.elapsedRealtime()-start
      assertTrue("Real ASR must return nonblank output",text.isNotBlank())
      runs.put(JSONObject().put("run",index).put("condition",if(index==0) "first inference after new engine" else "warm, same engine")
       .put("inferenceMs",elapsed).put("rtf",elapsed.toDouble()/pcm.durationMs).put("pssKb",pss()).put("text",text))
      save("ml-asr-comparison.json",result)
     } }
    }
   } finally { pcm.file.delete() }
  }
 }

 @Test fun vadBoundaryComparisons()=runBlocking {
  val source=File(app.filesDir,"integration-example.wav")
  Assume.assumeTrue("Stage official Russian WAV",source.exists())
  app.models.gate.withLock {
   app.models.requireReady()
   val pcm=AudioDecoder.decode(source.path,File(app.cacheDir,"comparison-vad.pcm"))
   try {
    val samples=AudioDecoder.read(pcm.file,0,pcm.samples)
    val sd=diar(-1)
    val turns=try { Alignment.stable(sd.process(samples).map { Turn((it.start*1000).roundToLong(),(it.end*1000).roundToLong(),it.speaker) }) } finally { sd.release() }
    val result=metadata().put("audioSha256",hash(source)).put("audioMs",pcm.durationMs).put("diarizationTurns",turnsJson(turns))
     .put("qualityNote","Inspect actual first word; no WER/CER or claim VAD is sole cause without reference")
    val runs=JSONArray();result.put("runs",runs)
    data class Variant(val name: String,val threshold: Float=.5f,val minSpeech: Float=.25f,val minSilence: Float=.25f,val pre: Long=0,val post: Long=0)
    val variants=listOf(Variant("current"),Variant("pre100",pre=100),Variant("post100",post=100),Variant("pre100-post100",pre=100,post=100),Variant("pre200",pre=200),Variant("pre300-post100",pre=300,post=100),
     Variant("threshold035-minSpeech010",threshold=.35f,minSpeech=.1f),Variant("threshold065-minSilence040",threshold=.65f,minSilence=.4f))
    GigaAmEngine(app.models).use { engine ->
     val rawStart=SystemClock.elapsedRealtime();val raw=engine.recognize(samples)
     runs.put(JSONObject().put("name","raw-no-vad-no-diar-crop").put("text",raw).put("inferenceMs",SystemClock.elapsedRealtime()-rawStart))
     for(v in variants) {
      val vad=Vad(config=VadModelConfig(sileroVadModelConfig=SileroVadModelConfig(model=app.models.file("vad/silero_vad.onnx").path,
       threshold=v.threshold,minSpeechDuration=v.minSpeech,minSilenceDuration=v.minSilence,maxSpeechDuration=20f)))
      val spans=mutableListOf<Span>()
      try {
       fun drain() { while(!vad.empty()) { val s=vad.front();spans+=Span(s.start*1000/16000,(s.start+s.samples.size)*1000/16000);vad.pop() } }
       var offset=0
       while(offset<samples.size) { val block=FloatArray(512);val n=min(512,samples.size-offset);samples.copyInto(block,0,offset,offset+n);vad.acceptWaveform(block);offset+=n;drain() }
       vad.flush();drain()
      } finally { vad.release() }
      val contextual=Alignment.context(spans,pcm.durationMs,v.pre,v.post)
      val sliceResults=JSONArray();val vadOnlyResults=JSONArray()
      // VAD-only and full alignment are separate: diarization cropping can independently lose a prefix.
      fun recognize(a: Long,b: Long): JSONObject {
       val start=(a*16).toInt();val end=min((b*16).toInt(),samples.size)
       val t=SystemClock.elapsedRealtime();val text=engine.recognize(samples.copyOfRange(start,end))
       return JSONObject().put("startMs",a).put("endMs",b).put("text",text).put("blank",text.isBlank()).put("inferenceMs",SystemClock.elapsedRealtime()-t)
      }
      contextual.forEach { vadOnlyResults.put(recognize(it.startMs,it.endMs)) }
      val slices=Alignment.slices(contextual,turns)
      slices.forEach { sliceResults.put(recognize(it.startMs,it.endMs).put("speakerId",it.speaker)) }
      val planned=RecognitionPlanner.plan(contextual,turns)
      val plannedResults=JSONArray()
      planned.forEach { plannedResults.put(recognize(it.startMs,it.endMs).put("speakerId",it.speaker)) }
      assertTrue(planned.zipWithNext().all { (a,b) -> a.endMs<=b.startMs })
      assertEquals(contextual.sumOf { it.endMs-it.startMs },planned.sumOf { it.endMs-it.startMs })
      if(v.name=="pre100") assertTrue("New planner must retain the known real prefix",plannedResults.getJSONObject(0).getString("text").startsWith("ничьих"))
      assertTrue(slices.zipWithNext().all { (a,b) -> a.endMs<=b.startMs })
      assertTrue(slices.all { it.startMs>=0 && it.endMs<=pcm.durationMs })
      runs.put(JSONObject().put("name",v.name).put("threshold",v.threshold).put("minSpeechSec",v.minSpeech).put("minSilenceSec",v.minSilence)
       .put("preMs",v.pre).put("postMs",v.post).put("vadSpans",spansJson(spans)).put("contextSpans",spansJson(contextual))
       .put("vadOnly",vadOnlyResults).put("alignedSlices",sliceResults).put("repairedPlanner",plannedResults))
      save("ml-vad-comparison.json",result)
     }
    }
   } finally { pcm.file.delete() }
  }
 }

 @Test fun diarizationAutomaticVersusKnownFour()=runBlocking {
  val source=File(app.filesDir,"integration-multispeaker.wav")
  Assume.assumeTrue("Stage official Chinese four-speaker WAV; this is not Russian E2E",source.exists())
  app.models.gate.withLock {
   app.models.requireReady()
   val pcm=AudioDecoder.decode(source.path,File(app.cacheDir,"comparison-diar.pcm"))
   try {
    val samples=AudioDecoder.read(pcm.file,0,pcm.samples)
    val result=metadata().put("audioSha256",hash(source)).put("audioMs",pcm.durationMs).put("language","zh")
     .put("DER","N/A; independent time-aligned reference unavailable").put("purpose","configuration sensitivity, not global threshold tuning")
    val runs=JSONArray();result.put("runs",runs)
    for((count,threshold) in listOf(-1 to .5f,4 to .5f,-1 to .65f)) {
     val start=SystemClock.elapsedRealtime();val sd=diar(count,threshold);val load=SystemClock.elapsedRealtime()-start
     try {
      val t=SystemClock.elapsedRealtime();val turns=Alignment.stable(sd.process(samples).map { Turn((it.start*1000).roundToLong(),(it.end*1000).roundToLong(),it.speaker) })
      val elapsed=SystemClock.elapsedRealtime()-t
      assertTrue(turns.isNotEmpty());assertTrue(turns.all { it.startMs>=0 && it.endMs>it.startMs })
      runs.put(JSONObject().put("mode",if(count>0) "fixed" else "automatic").put("numClusters",count).put("threshold",threshold)
       .put("thresholdApplied",count<=0).put("loadMs",load).put("inferenceMs",elapsed).put("rtf",elapsed.toDouble()/pcm.durationMs)
       .put("speakerCount",turns.map { it.speaker }.distinct().size).put("pssKb",pss()).put("minDurationOnSec",.2).put("minDurationOffSec",.5)
       .put("windowShiftRatio",.1).put("turns",turnsJson(turns)))
      save("ml-diarization-comparison.json",result)
     } finally { sd.release() }
    }
   } finally { pcm.file.delete() }
  }
 }
}
