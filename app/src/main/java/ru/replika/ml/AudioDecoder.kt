package ru.replika.ml

import android.media.*
import java.io.*
import java.nio.ByteOrder
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlin.math.*

data class AudioInfo(val file: File,val samples: Int,val peaks: List<Float>) { val durationMs get() = samples.toLong()*1000/16000 }
/** Disk-backed 16kHz mono float PCM. Decoder PTS populates silence/gaps; no loudness normalization. */
object AudioDecoder {
 suspend fun decode(source: String, destination: File): AudioInfo {
  val ex=MediaExtractor()
  var codec: MediaCodec?=null
  try {
   ex.setDataSource(source)
   val track=(0 until ex.trackCount).firstOrNull { ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/")==true } ?: error("В файле нет аудиодорожки")
   ex.selectTrack(track)
   val format=ex.getTrackFormat(track)
   val decoder=MediaCodec.createDecoderByType(format.getString(MediaFormat.KEY_MIME)!!)
   codec=decoder; decoder.configure(format,null,null,0); decoder.start()
   var rate=format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
   var channels=format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
   var filter=ru.replika.domain.PcmLowPass(rate)
   var lastInputTime=0.0
   var encoding=AudioFormat.ENCODING_PCM_16BIT
   var inputDone=false;var outputDone=false;var written=0L
   var previous=0f;var previousTime=-1.0;var nextTime=0.0
   val blockPeaks=mutableListOf<Float>();var peak=0f;var peakCount=0
   val info=MediaCodec.BufferInfo()
   DataOutputStream(BufferedOutputStream(FileOutputStream(destination))).use { out ->
    fun emit(value: Float) {
     // Big endian IEEE float; RandomAccessFile reader uses the same representation.
     out.writeFloat(value);written++;peak=max(peak,abs(value));peakCount++
     if(peakCount==1600) { blockPeaks+=peak;peak=0f;peakCount=0 }
    }
    fun resample(value: Float,time: Double) {
     if(time+1e-8 < previousTime) return
     while(nextTime<=time+1e-9) {
      val gap=time-previousTime
      val v=if(previousTime< -0.5 || gap>0.1) { if(abs(nextTime-time)<1.0/rate) value else 0f }
       else { val t=((nextTime-previousTime)/gap.coerceAtLeast(1e-12)).coerceIn(0.0,1.0).toFloat();previous+(value-previous)*t }
      emit(v);nextTime+=1.0/16000
      require(written < Int.MAX_VALUE) { "Слишком длинная запись" }
     };previous=value;previousTime=time
    }
    while(!outputDone) {
     currentCoroutineContext().ensureActive()
     if(!inputDone) {
      val i=decoder.dequeueInputBuffer(10000)
      if(i>=0) {
       val buf=decoder.getInputBuffer(i)!!
       val size=ex.readSampleData(buf,0)
       if(size<0) { decoder.queueInputBuffer(i,0,0,0,MediaCodec.BUFFER_FLAG_END_OF_STREAM);inputDone=true }
       else { decoder.queueInputBuffer(i,0,size,ex.sampleTime,0);ex.advance() }
      }
     }
     when(val i=decoder.dequeueOutputBuffer(info,10000)) {
      MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
       val f=decoder.outputFormat;rate=f.getInteger(MediaFormat.KEY_SAMPLE_RATE);channels=f.getInteger(MediaFormat.KEY_CHANNEL_COUNT);filter=ru.replika.domain.PcmLowPass(rate)
       encoding=if(f.containsKey(MediaFormat.KEY_PCM_ENCODING)) f.getInteger(MediaFormat.KEY_PCM_ENCODING) else AudioFormat.ENCODING_PCM_16BIT
       require(encoding==AudioFormat.ENCODING_PCM_16BIT || encoding==AudioFormat.ENCODING_PCM_FLOAT) { "Неподдерживаемый PCM: $encoding" }
      }
      else -> if(i>=0) {
       try {
        val b=decoder.getOutputBuffer(i)!!.order(ByteOrder.LITTLE_ENDIAN)
        b.position(info.offset);b.limit(info.offset+info.size)
        val bytes=if(encoding==AudioFormat.ENCODING_PCM_FLOAT) 4 else 2
        val frames=info.size/(bytes*channels)
        val start=info.presentationTimeUs/1000000.0
        // Preserve encoder timestamps, but tolerate sub-sample rounding.
        for(f in 0 until frames) {
         var value=0f
         repeat(channels) { value+=if(bytes==4) b.float else b.short/32768f }
         value=(value/channels).coerceIn(-1f,1f)
         val time=start+f.toDouble()/rate
         lastInputTime=time
         resample(filter.accept(value),time-filter.delaySamples.toDouble()/rate)
        }
       } finally { decoder.releaseOutputBuffer(i,false) }
       outputDone=info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
      }
     }
    }
    repeat(filter.delaySamples) { i -> resample(filter.accept(0f),lastInputTime+(i+1-filter.delaySamples).toDouble()/rate) }
   }
   require(written>0) { "Пустой или повреждённый аудиофайл" }
   if(peakCount>0) blockPeaks+=peak
   // At most 1200 genuine maxima for a compact UI.
   val stride=max(1,ceil(blockPeaks.size/1200.0).toInt())
   return AudioInfo(destination,written.toInt(),blockPeaks.chunked(stride).map { it.maxOrNull()?:0f })
  } catch(t: Throwable) { destination.delete();throw t }
  finally { codec?.let { runCatching { it.stop() };it.release() };ex.release() }
 }
 fun read(file: File,start: Int,count: Int): FloatArray {
  require(start>=0 && count>=0)
  return RandomAccessFile(file,"r").use { f -> f.seek(start.toLong()*4); FloatArray(count) { f.readFloat() } }
 }
}
