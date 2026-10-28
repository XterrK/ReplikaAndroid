package ru.replika.ml
class WhisperEngine(models: ModelManager): AsrEngine {
 override val source="Whisper tiny multilingual / whisper.cpp 1.7.6 / ru"
 private var handle=init(models.file("whisper-tiny/ggml-tiny.bin").path).also { require(it!=0L) { "Не удалось загрузить Whisper tiny" } }
 override fun recognize(samples: FloatArray)=transcribe(handle,samples).trim()
 override fun close() { if(handle!=0L) { free(handle);handle=0 } }
 private external fun init(path: String): Long
 private external fun transcribe(handle: Long,audio: FloatArray): String
 private external fun free(handle: Long)
 companion object { init { System.loadLibrary("replika-whisper") } }
}
