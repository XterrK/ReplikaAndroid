package ru.replika.ml

/**
 * Progress callback for OfflineSpeakerDiarization.processWithCallback.
 *
 * sherpa-onnx 2.0.1 JNI looks up `invoke(IIJ)Ljava/lang/Integer;` on the callback object. A Kotlin 2.x
 * lambda is compiled through invokedynamic and lacks that method, which aborted the process on Android
 * (SIGABRT, see MODEL_RESEARCH.md). A named class keeps a real method with that exact descriptor:
 * verified with `javap -s` on the compiled class (public java.lang.Integer invoke(int, int, long),
 * descriptor (IIJ)Ljava/lang/Integer;) and by a real diarization run on an emulator.
 */
class DiarizationProgressCallback(private val onProgress: (done: Int, total: Int) -> Unit) : (Int, Int, Long) -> Int {
 override fun invoke(numProcessedChunks: Int, numTotalChunks: Int, arg: Long): Int {
  runCatching { onProgress(numProcessedChunks, numTotalChunks) }
  return 0
 }
}
