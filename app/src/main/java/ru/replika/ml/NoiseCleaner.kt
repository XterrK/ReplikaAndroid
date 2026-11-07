package ru.replika.ml

import android.content.res.AssetManager
import com.k2fsa.sherpa.onnx.OfflineSpeechDenoiser
import com.k2fsa.sherpa.onnx.OfflineSpeechDenoiserConfig
import com.k2fsa.sherpa.onnx.OfflineSpeechDenoiserGtcrnModelConfig
import com.k2fsa.sherpa.onnx.OfflineSpeechDenoiserModelConfig
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import ru.replika.domain.NoiseGate
import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Measures background noise of the decoded PCM and, only for steady broadband noise, cleans it in place. */
object NoiseCleaner {
 const val ENABLED=true // kill switch: false keeps every recording on the original PCM
 const val MODEL_ASSET="denoise/gtcrn_simple.onnx"
 private const val CHUNK=30*16000

 fun analyse(pcm: File,samples: Int): NoiseGate.Decision {
  val frames=minOf(samples/NoiseGate.FRAME,NoiseGate.MAX_ANALYSED_FRAMES)
  if(frames<20) return NoiseGate.Decision(Double.POSITIVE_INFINITY,1.0,false)
  val audio=AudioDecoder.read(pcm,0,frames*NoiseGate.FRAME)
  val energies=DoubleArray(frames) { NoiseGate.energy(audio,it*NoiseGate.FRAME) }
  val (snr,quiet)=NoiseGate.snr(energies)
  val step=maxOf(1,quiet.size/NoiseGate.MAX_SPECTRA)
  val flat=quiet.sorted().filterIndexed { i,_ -> i%step==0 }.take(NoiseGate.MAX_SPECTRA)
   .map { NoiseGate.flatness(audio,it*NoiseGate.FRAME) }
  return NoiseGate.decide(snr,NoiseGate.median(flat))
 }

 /**
  * GTCRN over 30 s chunks, written back to the same big-endian Float32 PCM file. The denoiser is
  * created before the first write, so a creation failure leaves the PCM untouched.
  */
 suspend fun clean(assets: AssetManager,pcm: File,samples: Int,threads: Int) {
  val denoiser=OfflineSpeechDenoiser(assets,OfflineSpeechDenoiserConfig(OfflineSpeechDenoiserModelConfig(
   gtcrn=OfflineSpeechDenoiserGtcrnModelConfig(MODEL_ASSET),numThreads=threads)))
  try {
   RandomAccessFile(pcm,"rw").use { file ->
    var start=0
    while(start<samples) {
     currentCoroutineContext().ensureActive()
     val count=minOf(CHUNK,samples-start)
     val input=AudioDecoder.read(pcm,start,count)
     val output=denoiser.run(input,16000).samples
     val bytes=ByteBuffer.allocate(count*4).order(ByteOrder.BIG_ENDIAN)
     for(i in 0 until count) bytes.putFloat(if(i<output.size) output[i].coerceIn(-1f,1f) else 0f)
     file.seek(start.toLong()*4);file.write(bytes.array())
     start+=count
    }
   }
  } finally { denoiser.release() }
 }
}
