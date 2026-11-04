package ru.replika.ml

import com.k2fsa.sherpa.onnx.*
interface AsrEngine: AutoCloseable {
 val source: String
 fun recognize(samples: FloatArray): String
}
class GigaAmEngine(models: ModelManager, threads: Int = 2): AsrEngine {
 override val source="GigaAM v2 Transducer INT8 / sherpa-onnx 2.0.1"
 private val recognizer=OfflineRecognizer(config=OfflineRecognizerConfig(
  modelConfig=OfflineModelConfig(
   transducer=OfflineTransducerModelConfig(
    encoder=models.file("giga-v2/encoder.int8.onnx").path,
    decoder=models.file("giga-v2/decoder.onnx").path,
    joiner=models.file("giga-v2/joiner.onnx").path),
   tokens=models.file("giga-v2/tokens.txt").path,modelType="nemo_transducer",numThreads=ru.replika.domain.MlPolicy.threads(threads))))
 override fun recognize(samples: FloatArray): String {
  val stream=recognizer.createStream()
  try { stream.acceptWaveform(samples,16000);recognizer.decode(stream);return recognizer.getResult(stream).text.trim() }
  finally { stream.release() }
 }
 override fun close()=recognizer.release()
}
