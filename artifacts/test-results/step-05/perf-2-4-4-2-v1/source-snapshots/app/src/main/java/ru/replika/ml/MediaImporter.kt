package ru.replika.ml

import android.content.Context
import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMuxer
import android.net.Uri
import android.os.SystemClock
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import ru.replika.data.ProductOperationException
import java.io.File
import java.io.FileNotFoundException
import java.io.RandomAccessFile
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.roundToLong

/** Imports local audio, or extracts only audio packets/PCM from a video. Never decodes video frames.
 * Source documents are read-only. The original video is never copied or modified.
 * Multiple tracks: select the first default-marked audio track, otherwise the first audio track.
 */
class MediaImporter(private val context: Context,private val availableSpace: (File)->Long = { it.usableSpace }) {
 enum class Mode { AUDIO_COPY, AAC_REMUX, PCM_AUDIO_DECODE }
 data class Result(val file: File,val title: String,val durationMs: Long,val fromVideo: Boolean,
                   val audioTrackCount: Int,val selectedTrack: Int,val mode: Mode)
 private data class Track(val index: Int,val format: MediaFormat)
 private data class Inspection(val audio: List<Track>,val chosen: Track,val video: Boolean)
 private val reserveBytes=8L*1024*1024

 suspend fun importMedia(uri: Uri,directory: File,id: String,progress: (String)->Unit): Result {
  val owned=mutableListOf<File>()
  try {
   return withContext(Dispatchers.IO) {
    require(id.matches(Regex("[A-Za-z0-9-]+"))) { "Unsafe import ID" }
    check(directory.isDirectory || directory.mkdirs()) { "Cannot create local audio directory" }
    val metadata=runCatching {
     context.contentResolver.query(uri,arrayOf(OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE),null,null,null)?.use { cursor ->
      val nameIndex=cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);val sizeIndex=cursor.getColumnIndex(OpenableColumns.SIZE)
      if(cursor.moveToFirst()) (if(nameIndex>=0) cursor.getString(nameIndex) else null) to (if(sizeIndex<0 || cursor.isNull(sizeIndex)) -1L else cursor.getLong(sizeIndex)) else null
     }
    }.getOrNull()
    val title=metadata?.first?.takeIf { it.isNotBlank() }?:uri.lastPathSegment?:"Новая запись"
    fun output(suffix: String)=File(directory,"$id.$suffix").also { check(!it.exists()) { "Import target already exists" };owned+=it }
    try {
     ensureSpace(directory)
     progress("Проверка аудио и видео…")
     val inspection=extractor(uri).useExtractor { inspect(it) }
     val chosen=inspection.chosen
     val duration=if(chosen.format.containsKey(MediaFormat.KEY_DURATION)) chosen.format.getLong(MediaFormat.KEY_DURATION)/1000 else 0L
     val result=if(!inspection.video && inspection.audio.size==1) {
      val file=output("audio")
      ensureSpace(directory,(metadata?.second?:0L).coerceAtLeast(0))
      progress("Копирование аудио…")
      context.contentResolver.openInputStream(uri)?.use { source -> file.outputStream().buffered().use { target ->
       val buffer=ByteArray(128*1024);var sinceCheck=0L
       while(true) {
        currentCoroutineContext().ensureActive();val n=source.read(buffer);if(n<0) break
        target.write(buffer,0,n);sinceCheck+=n
        if(sinceCheck>=1024*1024) { ensureSpace(directory);sinceCheck=0 }
       }
      } }?:throw ProductOperationException("Не удалось прочитать файл. Выберите его заново.","Source document could not be opened")
      if(file.length()==0L) throw ProductOperationException("Выбранный файл пуст.","Empty source audio")
      Result(file,title,duration,false,1,chosen.index,Mode.AUDIO_COPY)
     } else {
      val firstSampleTime=extractor(uri).useExtractor {
       it.selectTrack(chosen.index);it.sampleTime
      }
      // Android 9 ignores two-entry MP4 edit lists. Inspect their real movie clock before
      // accepting zero PTS as zero offset; a newer extractor may already apply the edit.
      val timing=audioTimeline(uri,chosen,firstSampleTime)
      // MPEG-4 muxers can rebase delayed tracks. PCM explicitly retains leading silence.
      val canRemux=chosen.format.getString(MediaFormat.KEY_MIME)=="audio/mp4a-latm" &&
       firstSampleTime==0L && timing.leadingEmptyUs==0L
      var remuxed: File?=null
      if(canRemux) {
       val file=output("m4a")
       try { progress("Извлечение звуковой дорожки…");remux(uri,chosen,file,progress);remuxed=file }
       catch(e: CancellationException) { throw e }
       catch(e: ProductOperationException) { throw e }
       catch(_: Exception) { file.delete() /* Device/container muxer mismatch: use system audio decoder. */ }
      }
      if(remuxed!=null) Result(remuxed,title,duration,inspection.video,inspection.audio.size,chosen.index,Mode.AAC_REMUX)
      else {
       val file=output("wav")
       progress("Подготовка звуковой дорожки…")
       currentCoroutineContext().ensureActive()
       val decodedDuration=decodeAudio(uri,chosen,file,progress,timing.additionalOffsetUs)
       Result(file,title,decodedDuration,inspection.video,inspection.audio.size,chosen.index,Mode.PCM_AUDIO_DECODE)
      }
     }
     currentCoroutineContext().ensureActive()
     result
    } catch(e: Throwable) {
     owned.forEach { it.delete() }
     when(e) {
      is CancellationException -> throw e
      is ProductOperationException -> throw e
      is FileNotFoundException -> throw ProductOperationException("Файл больше недоступен. Выберите аудио или видео заново.","Source document no longer available",e)
      is SecurityException -> throw ProductOperationException("Доступ к файлу потерян. Выберите аудио или видео заново.","Source permission denied",e)
      else -> throw ProductOperationException("Не удалось прочитать звуковую дорожку. Возможно, файл повреждён или его аудиокодек не поддерживается устройством.","Audio/video import failed for $uri",e)
     }
    }
   }
  } catch(error: Throwable) {
   // withContext may deliver cancellation after its IO block completed but before its result
   // reaches the caller. Retain ownership until that delivery succeeds, and clean this race too.
   withContext(NonCancellable+Dispatchers.IO) { owned.forEach { it.delete() } }
   throw error
  }
 }

 private suspend fun audioTimeline(uri: Uri,track: Track,firstSampleTimeUs: Long): IsoBmffAudioTimeline.Timing {
  val coroutine=currentCoroutineContext()
  try {
   val descriptor=context.contentResolver.openAssetFileDescriptor(uri,"r")
    ?:throw FileNotFoundException("Source timeline descriptor is unavailable")
   descriptor.use { asset ->
    // Own the duplicate through AutoCloseInputStream; never close/reuse the provider's FD.
    ParcelFileDescriptor.AutoCloseInputStream(ParcelFileDescriptor.dup(asset.fileDescriptor)).use { input ->
     val channel=input.channel
     val length=if(asset.declaredLength>=0) asset.declaredLength else channel.size()-asset.startOffset
     val metadata=IsoBmffAudioTimeline.read(IsoBmffAudioTimeline.ChannelSource(channel,asset.startOffset,length)) { coroutine.ensureActive() }
     val trackId=if(track.format.containsKey(MediaFormat.KEY_TRACK_ID)) track.format.getInteger(MediaFormat.KEY_TRACK_ID).toLong() and 0xffffffffL else null
     return metadata?.timing(trackId,firstSampleTimeUs)?:IsoBmffAudioTimeline.Timing(0,0)
    }
   }
  } catch(e: IsoBmffAudioTimeline.UnsupportedTimeline) {
   throw ProductOperationException("Временная шкала этой звуковой дорожки не поддерживается. Сохраните копию видео в стандартном MP4 и повторите импорт.","Unsupported source audio timeline: ${e.message}",e)
  } catch(e: FileNotFoundException) { throw e }
   catch(e: IOException) {
    throw ProductOperationException("Не удалось проверить временную шкалу видео. Сохраните его локальную копию и повторите импорт.","Source timeline metadata is not seekable/readable",e)
   }
 }

 private fun extractor(uri: Uri)=MediaExtractor().also { extractor ->
  try {
   // Open through the resolver explicitly: the Context/Uri overload can swallow a provider's
   // SecurityException and retry its URI as a string, losing the actionable permission cause.
   require(uri.scheme=="content" || uri.scheme=="file") { "Only local document URIs are supported" }
   val descriptor=context.contentResolver.openAssetFileDescriptor(uri,"r")
    ?:throw FileNotFoundException("Source document descriptor is unavailable")
   descriptor.use {
    if(it.length==0L) throw ProductOperationException("Выбранный файл пуст.","Empty source document descriptor")
    if(it.declaredLength<0) {
     require(it.startOffset==0L) { "Unknown-length document with a non-zero offset" }
     extractor.setDataSource(it.fileDescriptor)
    } else extractor.setDataSource(it.fileDescriptor,it.startOffset,it.declaredLength)
   }
  } catch(e: Throwable) { extractor.release();throw e }
 }
 private inline fun <T> MediaExtractor.useExtractor(action: (MediaExtractor)->T): T = try { action(this) } finally { release() }
 private fun inspect(extractor: MediaExtractor): Inspection {
  val tracks=(0 until extractor.trackCount).map { Track(it,extractor.getTrackFormat(it)) }
  val audio=tracks.filter { it.format.getString(MediaFormat.KEY_MIME)?.startsWith("audio/")==true }
  if(audio.isEmpty()) throw ProductOperationException("В этом файле нет звуковой дорожки. Выберите видео со звуком или аудиофайл.","No audio track in source")
  val chosen=audio.firstOrNull { it.format.containsKey("is-default") && it.format.getInteger("is-default")==1 }?:audio.first()
  extractor.selectTrack(chosen.index)
  if(extractor.sampleTrackIndex<0) throw ProductOperationException("Звуковая дорожка пуста. Выберите файл со звуком.","Selected audio track has no packets")
  if(extractor.sampleFlags and MediaExtractor.SAMPLE_FLAG_ENCRYPTED!=0) throw ProductOperationException("Защищённую звуковую дорожку нельзя импортировать. Выберите незашифрованный файл.","Encrypted audio track")
  return Inspection(audio,chosen,tracks.any { it.format.getString(MediaFormat.KEY_MIME)?.startsWith("video/")==true })
 }
 private fun ensureSpace(directory: File,additional: Long=0) {
  val free=availableSpace(directory)
  if(free<reserveBytes || additional.coerceAtLeast(0)>free-reserveBytes) throw ProductOperationException("Недостаточно места для звуковой дорожки. Освободите память и повторите импорт.","Insufficient local storage for audio import")
 }
 private fun sampleBuffer(format: MediaFormat): ByteBuffer {
  val requested=if(format.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)) format.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE) else 0
  return ByteBuffer.allocateDirect(requested.coerceIn(1024*1024,8*1024*1024))
 }
 private suspend fun remux(uri: Uri,track: Track,destination: File,progress: (String)->Unit) {
  extractor(uri).useExtractor { source ->
   source.selectTrack(track.index)
   val muxer=MediaMuxer(destination.path,MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
   var started=false;var packets=0L;var lastTime=-1L;var bytesSinceSpaceCheck=0L
   try {
    val target=muxer.addTrack(track.format);muxer.start();started=true
    val buffer=sampleBuffer(track.format);val info=MediaCodec.BufferInfo()
    while(true) {
     currentCoroutineContext().ensureActive();buffer.clear()
     val size=source.readSampleData(buffer,0);if(size<0) break
     if(source.sampleFlags and MediaExtractor.SAMPLE_FLAG_ENCRYPTED!=0) throw ProductOperationException("Защищённую звуковую дорожку нельзя импортировать. Выберите незашифрованный файл.","Encrypted audio track")
     val pts=source.sampleTime
     check(pts>=0 && pts>=lastTime) { "Non-monotonic compressed audio timestamps" };lastTime=pts
     if(bytesSinceSpaceCheck>=1024*1024 || size>=1024*1024) { ensureSpace(destination.parentFile!!,size.toLong());bytesSinceSpaceCheck=0 }
     info.set(0,size,pts,if(source.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC!=0) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0)
     muxer.writeSampleData(target,buffer,info);packets++;bytesSinceSpaceCheck+=size
     if(packets%64L==0L) { ensureSpace(destination.parentFile!!);progress("Извлечение звука · ${destination.length()/1024/1024} МБ") }
     if(!source.advance()) break
    }
    check(packets>0) { "Empty audio track" }
    muxer.stop();started=false
   } finally {
    if(started) runCatching { muxer.stop() }
    muxer.release()
   }
  }
 }
 private suspend fun decodeAudio(uri: Uri,track: Track,destination: File,progress: (String)->Unit,timelineOffsetUs: Long): Long = extractor(uri).useExtractor { source ->
  source.selectTrack(track.index)
  val mime=track.format.getString(MediaFormat.KEY_MIME)?:error("Audio MIME missing")
  val codec=MediaCodec.createDecoderByType(mime)
  var started=false
  try {
   codec.configure(track.format,null,null,0);codec.start();started=true
   RandomAccessFile(destination,"rw").use { output ->
    output.setLength(0);output.write(ByteArray(44))
    var rate=track.format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
    var channels=track.format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
    var encoding=AudioFormat.ENCODING_PCM_16BIT
    require(rate in 8000..384000 && channels in 1..32) { "Invalid source audio format" }
    var writtenFrames=0L;var inputEnded=false;var outputEnded=false
    var lastActivity=SystemClock.elapsedRealtime();var nextProgress=lastActivity
    val info=MediaCodec.BufferInfo()
    while(!outputEnded) {
     currentCoroutineContext().ensureActive()
     if(!inputEnded) {
      val inputIndex=codec.dequeueInputBuffer(10000)
      if(inputIndex>=0) {
       val input=codec.getInputBuffer(inputIndex)!!;input.clear()
       val n=source.readSampleData(input,0)
       if(n<0) { codec.queueInputBuffer(inputIndex,0,0,0,MediaCodec.BUFFER_FLAG_END_OF_STREAM);inputEnded=true }
       else {
        if(source.sampleFlags and MediaExtractor.SAMPLE_FLAG_ENCRYPTED!=0) throw ProductOperationException("Защищённую звуковую дорожку нельзя импортировать. Выберите незашифрованный файл.","Encrypted audio track")
        codec.queueInputBuffer(inputIndex,0,n,source.sampleTime,0);source.advance()
       }
       lastActivity=SystemClock.elapsedRealtime()
      }
     }
     val index=codec.dequeueOutputBuffer(info,10000)
     when {
      index==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
       val format=codec.outputFormat
       val newRate=format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
       require(writtenFrames==0L || newRate==rate) { "Audio sample rate changes midstream" }
       rate=newRate;channels=format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
       require(rate in 8000..384000 && channels in 1..32) { "Invalid decoded audio format" }
       encoding=if(format.containsKey(MediaFormat.KEY_PCM_ENCODING)) format.getInteger(MediaFormat.KEY_PCM_ENCODING) else AudioFormat.ENCODING_PCM_16BIT
       lastActivity=SystemClock.elapsedRealtime()
      }
      index>=0 -> {
       try {
        if(info.size>0 && info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG==0) {
         val pcm=codec.getOutputBuffer(index)!!.duplicate().order(ByteOrder.LITTLE_ENDIAN)
         pcm.position(info.offset);pcm.limit(info.offset+info.size)
         val sampleBytes=when(encoding) {
          AudioFormat.ENCODING_PCM_8BIT -> 1
          AudioFormat.ENCODING_PCM_16BIT -> 2
          AudioFormat.ENCODING_PCM_24BIT_PACKED -> 3
          AudioFormat.ENCODING_PCM_FLOAT,AudioFormat.ENCODING_PCM_32BIT -> 4
          else -> error("Unsupported decoded PCM encoding $encoding")
         }
         val frames=info.size/(channels*sampleBytes)
         val presentationUs=Math.addExact(info.presentationTimeUs,timelineOffsetUs)
         val sourceFrame=(presentationUs.toDouble()*rate/1_000_000.0).roundToLong()
         val targetFrame=sourceFrame.coerceAtLeast(0)
         if(targetFrame>MAX_WAV_BYTES/2) throw ProductOperationException("Звуковая дорожка слишком длинная для импорта. Разделите видео на части.","Source timeline exceeds WAV capacity")
         // Silence before a delayed track and real timestamp gaps; overlapping/negative frames are trimmed.
         if(targetFrame>writtenFrames) {
          var silence=(targetFrame-writtenFrames)*2;val zeros=ByteArray(64*1024)
          while(silence>0) {
           currentCoroutineContext().ensureActive();ensureSpace(destination.parentFile!!)
           val n=minOf(silence,zeros.size.toLong()).toInt();output.write(zeros,0,n);silence-=n
          }
          writtenFrames=targetFrame
         }
         val skip=(writtenFrames-sourceFrame).coerceIn(0,frames.toLong()).toInt()
         pcm.position(pcm.position()+skip*channels*sampleBytes)
         val bytes=ByteArray((frames-skip)*2)
         for(frame in skip until frames) {
          var mono=0.0
          repeat(channels) { mono+=when(encoding) {
           AudioFormat.ENCODING_PCM_8BIT -> ((pcm.get().toInt() and 255)-128)/128.0
           AudioFormat.ENCODING_PCM_16BIT -> pcm.short/32768.0
           AudioFormat.ENCODING_PCM_FLOAT -> pcm.float.toDouble().let { if(it.isFinite()) it else 0.0 }
           AudioFormat.ENCODING_PCM_24BIT_PACKED -> { val x=(pcm.get().toInt() and 255) or ((pcm.get().toInt() and 255) shl 8) or (pcm.get().toInt() shl 16);x/8388608.0 }
           else -> pcm.int/2147483648.0
          } }
          val value=(mono/channels*32768).roundToLong().coerceIn(-32768,32767).toInt()
          val offset=(frame-skip)*2;bytes[offset]=value.toByte();bytes[offset+1]=(value shr 8).toByte()
         }
         if((writtenFrames+frames-skip)*2>MAX_WAV_BYTES) throw ProductOperationException("Звуковая дорожка слишком длинная для импорта. Разделите видео на части.","Decoded audio exceeds WAV capacity")
         ensureSpace(destination.parentFile!!,bytes.size.toLong());output.write(bytes);writtenFrames+=frames-skip
        }
        outputEnded=info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM!=0
       } finally { codec.releaseOutputBuffer(index,false) }
       lastActivity=SystemClock.elapsedRealtime()
      }
     }
     val now=SystemClock.elapsedRealtime()
     check(now-lastActivity<20000) { "System audio decoder timed out" }
     if(now>=nextProgress) { progress("Подготовка звука · ${output.length()/1024/1024} МБ");nextProgress=now+500 }
    }
    if(writtenFrames==0L) throw ProductOperationException("Звуковая дорожка пуста. Выберите файл со звуком.","Audio decoder produced no samples")
    writeWavHeader(output,rate,writtenFrames*2)
    writtenFrames*1000/rate
   }
  } finally { if(started) runCatching { codec.stop() };codec.release() }
 }
 private fun writeWavHeader(output: RandomAccessFile,rate: Int,dataBytes: Long) {
  val header=ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
  header.put("RIFF".toByteArray(Charsets.US_ASCII)).putInt((36+dataBytes).toInt())
   .put("WAVEfmt ".toByteArray(Charsets.US_ASCII)).putInt(16).putShort(1).putShort(1)
   .putInt(rate).putInt(rate*2).putShort(2).putShort(16)
   .put("data".toByteArray(Charsets.US_ASCII)).putInt(dataBytes.toInt())
  output.seek(0);output.write(header.array());output.fd.sync()
 }
 companion object { private const val MAX_WAV_BYTES=0xfffffff0L-44 }
}
