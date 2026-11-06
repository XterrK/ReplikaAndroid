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
