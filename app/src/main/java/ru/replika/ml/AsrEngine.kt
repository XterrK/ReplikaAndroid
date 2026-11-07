package ru.replika.ml

import com.k2fsa.sherpa.onnx.*
data class AsrHypothesis(val text: String,val tokens: List<String>,val timestampsSeconds: FloatArray,val frameStrideMs: Long)
interface AsrEngine: AutoCloseable {
 val source: String
 fun recognize(samples: FloatArray): String
 fun recognizeDetailed(samples: FloatArray)=AsrHypothesis(recognize(samples),emptyList(),FloatArray(0),0)
}
class GigaAmEngine(models: ModelManager, threads: Int = 2): AsrEngine {
 private val modelId=models.asrId.also { require(it=="giga-v2" || it=="giga-v3") { "Unsupported GigaAM family" } }
 override val source=sourceForModel(modelId)
 private val recognizer=OfflineRecognizer(config=OfflineRecognizerConfig(
  modelConfig=OfflineModelConfig(
   transducer=OfflineTransducerModelConfig(
    encoder=models.file("$modelId/encoder.int8.onnx").path,
    decoder=models.file("$modelId/decoder.onnx").path,
    joiner=models.file("$modelId/joiner.onnx").path),
   tokens=models.file("$modelId/tokens.txt").path,modelType="nemo_transducer",numThreads=ru.replika.domain.MlPolicy.threads(threads))))
 override fun recognize(samples: FloatArray): String {
  val stream=recognizer.createStream()
  try { stream.acceptWaveform(samples,16000);recognizer.decode(stream);return recognizer.getResult(stream).text.trim() }
  finally { stream.release() }
 }
 override fun recognizeDetailed(samples: FloatArray): AsrHypothesis {
  val stream=recognizer.createStream()
  try {
   stream.acceptWaveform(samples,16000);recognizer.decode(stream)
   val result=recognizer.getResult(stream)
   // GigaAM v3's pinned encoder metadata: subsampling_factor=4, feature frame shift=10ms.
   // Unknown families must fall back rather than invent word boundaries.
   return AsrHypothesis(result.text.trim(),result.tokens.toList(),result.timestamps.copyOf(),if(modelId=="giga-v3") 40L else 0L)
  } finally { stream.release() }
 }
 override fun close()=recognizer.release()
 companion object {
  /** Attribution is available without allocating a native recognizer for no-speech recordings. */
  fun sourceForModel(id: String): String = when(id) {
   "giga-v3" -> "GigaAM v3 E2E RNNT INT8 / sherpa-onnx 2.0.1"
   "giga-v2" -> "GigaAM v2 Transducer INT8 / sherpa-onnx 2.0.1"
   else -> error("Unsupported GigaAM family")
  }
 }
}

/** NVIDIA Parakeet TDT 0.6B v2 (English, punctuation and case). Loaded only for English chunks. */
class ParakeetEngine(models: ModelManager, threads: Int = 2): AsrEngine {
 override val source=SOURCE
 private val recognizer=OfflineRecognizer(config=OfflineRecognizerConfig(
  modelConfig=OfflineModelConfig(
   transducer=OfflineTransducerModelConfig(
    encoder=models.file("${ModelManager.ENGLISH_GROUP}/encoder.int8.onnx").path,
    decoder=models.file("${ModelManager.ENGLISH_GROUP}/decoder.int8.onnx").path,
    joiner=models.file("${ModelManager.ENGLISH_GROUP}/joiner.int8.onnx").path),
   tokens=models.file("${ModelManager.ENGLISH_GROUP}/tokens.txt").path,modelType="nemo_transducer",numThreads=ru.replika.domain.MlPolicy.threads(threads))))
 override fun recognize(samples: FloatArray): String = recognizeDetailed(samples).text
 override fun recognizeDetailed(samples: FloatArray): AsrHypothesis {
  val stream=recognizer.createStream()
  try {
   stream.acceptWaveform(samples,16000);recognizer.decode(stream)
   val result=recognizer.getResult(stream)
   // Pinned encoder metadata: NeMo EncDecRNNTBPEModel, subsampling_factor=8 over 10 ms features.
   // Verified on the host stand: TDT token timestamps lie on this 80 ms grid.
   return AsrHypothesis(result.text.trim(),result.tokens.toList(),result.timestamps.copyOf(),FRAME_STRIDE_MS)
  } finally { stream.release() }
 }
 override fun close()=recognizer.release()
 companion object {
  const val SOURCE="Parakeet TDT 0.6B v2 INT8 / sherpa-onnx 2.0.1"
  const val FRAME_STRIDE_MS=80L
 }
}

/**
 * Holds exactly one recognizer. Russian always uses the unchanged GigaAmEngine; English models are
 * opened only when an English chunk is reached and the previous recognizer is released first.
 */
class RoutedAsrEngine(private val models: ModelManager,private val threads: Int,first: ru.replika.domain.AsrLanguage,
 private val onLoad: (ru.replika.domain.AsrLanguage,Long)->Unit = { _,_ -> }): AsrEngine {
 var language=first;private set
 private var engine: AsrEngine?=open(first)
 val loadedLanguages=mutableListOf(first)
 override val source: String get()=active().source
 private fun active()=checkNotNull(engine) { "Модель распознавания не загружена" }
 private fun open(target: ru.replika.domain.AsrLanguage): AsrEngine {
  val started=android.os.SystemClock.elapsedRealtime()
  return (if(target==ru.replika.domain.AsrLanguage.EN) ParakeetEngine(models,threads) else GigaAmEngine(models,threads))
   .also { onLoad(target,android.os.SystemClock.elapsedRealtime()-started) }
 }
 fun select(target: ru.replika.domain.AsrLanguage) {
  if(target==language && engine!=null) return
  engine?.close();engine=null
  engine=open(target);language=target;loadedLanguages+=target
 }
 override fun recognize(samples: FloatArray)=active().recognize(samples)
 override fun recognizeDetailed(samples: FloatArray)=active().recognizeDetailed(samples)
 override fun close() { engine?.close();engine=null }
 companion object {
  fun sourceFor(language: ru.replika.domain.AsrLanguage,russianBackend: String)=
   if(language==ru.replika.domain.AsrLanguage.EN) ParakeetEngine.SOURCE else GigaAmEngine.sourceForModel(russianBackend)
 }
}
