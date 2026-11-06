package ru.replika

import android.media.MediaExtractor
import android.media.MediaFormat
import android.net.Uri
import androidx.core.content.FileProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.data.ProductOperationException
import ru.replika.ml.AudioDecoder
import ru.replika.ml.MediaImporter
import ru.replika.ml.ModelManager
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import kotlin.math.abs
import kotlin.math.sqrt

/** Tiny original synthetic codec fixtures; verifies actual Android extraction, not speech quality. */
@RunWith(AndroidJUnit4::class)
class MediaImportV15Test {
 private val instrumentation get()=InstrumentationRegistry.getInstrumentation()
 private val context get()=instrumentation.targetContext
 private lateinit var directory: File
 private lateinit var output: File
 @Before fun createIsolatedDirectory() {
  directory=File(File(context.cacheDir,"exports"),"media-import-${System.nanoTime()}").apply { check(mkdirs()) }
  output=File(directory,"owned")
 }
 @After fun deleteOnlyOurFixtures() { directory.deleteRecursively() }
 private fun fixture(name: String)=File(directory,name).also { target ->
  instrumentation.context.assets.open("media-import/$name").use { source -> target.outputStream().use { source.copyTo(it) } }
 }
 private fun hash(file: File)=MessageDigest.getInstance("SHA-256").digest(file.readBytes()).toList()
 private fun audioOnly(file: File): MediaFormat {
  val extractor=MediaExtractor()
  try {
   extractor.setDataSource(file.path)
   assertEquals("Local artifact must contain only the selected audio track",1,extractor.trackCount)
   return extractor.getTrackFormat(0).also { assertTrue(it.getString(MediaFormat.KEY_MIME)!!.startsWith("audio/")) }
  } finally { extractor.release() }
 }
 private fun rms(samples: FloatArray)=if(samples.isEmpty()) 0.0 else sqrt(samples.sumOf { (it*it).toDouble() }/samples.size)

 @Test fun aacVideoIsRemuxedWithoutVideoAndSourceIsUnchanged(): Unit=runBlocking {
  val source=fixture("aac-zero.mp4");val before=hash(source)
  val progress=mutableListOf<String>()
  val result=MediaImporter(context).importMedia(Uri.fromFile(source),output,"aac-remux") { progress+=it }
  assertEquals(MediaImporter.Mode.AAC_REMUX,result.mode)
  assertTrue(result.fromVideo);assertEquals(1,result.audioTrackCount)
  assertEquals("audio/mp4a-latm",audioOnly(result.file).getString(MediaFormat.KEY_MIME))
  assertEquals(before,hash(source));assertTrue(progress.isNotEmpty())
  val pcm=AudioDecoder.decode(result.file.path,File(directory,"remux.pcm"))
  assertTrue("Actual extracted sound is non-silent",rms(AudioDecoder.read(pcm.file,0,pcm.samples))>0.03)
  assertTrue("AAC priming allowed, no timeline drift: ${pcm.durationMs}",abs(pcm.durationMs-1021)<90)
 }

 @Test fun delayedTrackKeepsVideoClockAsLeadingSilence(): Unit=runBlocking {
  val source=fixture("aac-offset.mp4");val before=hash(source)
  val result=MediaImporter(context).importMedia(Uri.fromFile(source),output,"offset") {}
  assertEquals(MediaImporter.Mode.PCM_AUDIO_DECODE,result.mode)
  assertEquals("wav",result.file.extension);audioOnly(result.file)
  assertEquals(before,hash(source))
  val pcm=AudioDecoder.decode(result.file.path,File(directory,"offset.pcm"))
  assertTrue("Offset remains on video timeline: ${pcm.durationMs}",pcm.durationMs in 1300..1500)
  assertTrue("First 300 ms must remain silent",rms(AudioDecoder.read(pcm.file,0,4800))<0.001)
  assertTrue("Tone starts after source offset",rms(AudioDecoder.read(pcm.file,8000,4000))>0.03)
 }

 @Test fun delayedContentUriKeepsItsClockWithoutDoubleApplyingTheEdit(): Unit=runBlocking {
  val source=fixture("aac-offset.mp4");val before=hash(source)
  val uri=FileProvider.getUriForFile(context,"${context.packageName}.files",source)
  val result=MediaImporter(context).importMedia(uri,output,"offset-provider") {}
  assertEquals(MediaImporter.Mode.PCM_AUDIO_DECODE,result.mode)
  val pcm=AudioDecoder.decode(result.file.path,File(directory,"provider-offset.pcm"))
  assertTrue("One offset only, on both old and new extractors: ${pcm.durationMs}",pcm.durationMs in 1300..1500)
  assertTrue(rms(AudioDecoder.read(pcm.file,0,4800))<0.001)
  assertTrue(rms(AudioDecoder.read(pcm.file,8000,4000))>0.03)
  assertEquals(before,hash(source))
 }

 @Test fun singlePositiveAacPrimingEditDoesNotBecomeAnExtraStartOffset(): Unit=runBlocking {
  val source=fixture("aac-priming.mp4");val before=hash(source)
  val result=MediaImporter(context).importMedia(Uri.fromFile(source),output,"priming") {}
  audioOnly(result.file)
  val pcm=AudioDecoder.decode(result.file.path,File(directory,"priming.pcm"))
  assertTrue("Normal gapless AAC remains approximately one second: ${pcm.durationMs}",pcm.durationMs in 950..1070)
  assertTrue("AAC priming is not a fabricated leading gap",rms(AudioDecoder.read(pcm.file,0,1600))>0.03)
  assertEquals(before,hash(source))
 }

 @Test fun unsupportedEditRateIsRejectedWithoutRebasingOrLeavingAudioArtifacts(): Unit=runBlocking {
  val source=fixture("aac-offset.mp4")
  val bytes=source.readBytes();val buffer=ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN)
  val audioEdit=(4 until bytes.size-24).first { i ->
   bytes[i]=='e'.code.toByte() && bytes[i+1]=='l'.code.toByte() && bytes[i+2]=='s'.code.toByte() && bytes[i+3]=='t'.code.toByte() &&
    buffer.getInt(i+8)==2 && buffer.getInt(i+16)== -1
  }
  buffer.putInt(audioEdit+32,0) // Deliberate dwell/non-unit media edit in a private fixture copy only.
  source.writeBytes(bytes);val before=hash(source)
  try { MediaImporter(context).importMedia(Uri.fromFile(source),output,"unsupported-edit") {};fail("Expected honest timeline error") }
  catch(e: ProductOperationException) { assertTrue(e.userMessage.contains("Временная шкала")) }
  assertEquals(before,hash(source));assertTrue(output.listFiles().orEmpty().isEmpty())
 }

 @Test fun opusUsesSystemAudioDecoderAndProducesPortableWav(): Unit=runBlocking {
  val source=fixture("opus-fallback.webm");val before=hash(source)
  val result=MediaImporter(context).importMedia(Uri.fromFile(source),output,"opus") {}
  assertTrue(result.fromVideo);assertEquals(MediaImporter.Mode.PCM_AUDIO_DECODE,result.mode)
  val format=audioOnly(result.file)
  assertEquals(1,format.getInteger(MediaFormat.KEY_CHANNEL_COUNT));assertEquals(before,hash(source))
  val pcm=AudioDecoder.decode(result.file.path,File(directory,"opus.pcm"))
  assertTrue(pcm.durationMs in 900..1100);assertTrue(rms(AudioDecoder.read(pcm.file,0,pcm.samples))>0.03)
 }

 @Test fun multipleAudioTracksUseDeclaredDefaultOrFirstFallbackOnly(): Unit=runBlocking {
  val source=fixture("multi-audio.mp4")
  val extractor=MediaExtractor();extractor.setDataSource(source.path)
  val expected=try {
   val audio=(0 until extractor.trackCount).filter { extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/")==true }
   audio.firstOrNull { val f=extractor.getTrackFormat(it);f.containsKey("is-default") && f.getInteger("is-default")==1 }?:audio.first()
  } finally { extractor.release() }
  val result=MediaImporter(context).importMedia(Uri.fromFile(source),output,"multi") {}
  assertEquals(2,result.audioTrackCount);assertEquals(expected,result.selectedTrack);audioOnly(result.file)
 }

 @Test fun ordinaryAudioStaysBitIdenticalAndNeedsNoVideoCopy(): Unit=runBlocking {
  val source=fixture("audio-only.m4a")
  val result=MediaImporter(context).importMedia(Uri.fromFile(source),output,"audio") {}
  assertFalse(result.fromVideo);assertEquals(MediaImporter.Mode.AUDIO_COPY,result.mode)
  assertEquals(hash(source),hash(result.file));audioOnly(result.file)
 }

 @Test fun silentVideoAndCorruptFilesGiveActionableErrorsWithoutPartialArtifacts(): Unit=runBlocking {
  val sources=listOf(fixture("no-audio.mp4"),File(directory,"corrupt.mp4").apply { writeText("not a media container") })
  for((index,source) in sources.withIndex()) {
   var failure: ProductOperationException?=null
   try { MediaImporter(context).importMedia(Uri.fromFile(source),output,"rejected-$index") {};fail("Expected invalid media rejection") }
   catch(e: ProductOperationException) { failure=e }
   assertTrue(failure!!.userMessage.isNotBlank())
   if(index==0) assertTrue(failure.userMessage.contains("нет звуковой дорожки"))
   assertTrue("Source remains available",source.isFile)
   assertTrue("No orphan import artifacts",output.listFiles().orEmpty().isEmpty())
  }
 }

 @Test fun cancellationDeletesPartialAudioAndPreservesSource(): Unit=runBlocking {
  val source=fixture("aac-offset.mp4");val before=hash(source)
  val child=launch(Dispatchers.Default) {
   val caller=currentCoroutineContext()
   MediaImporter(context).importMedia(Uri.fromFile(source),output,"cancelled") { if(it.startsWith("Подготовка")) caller.cancel() }
  }
  child.join();assertTrue(child.isCancelled)
  assertTrue(output.listFiles().orEmpty().isEmpty());assertEquals(before,hash(source))
 }

 @Test fun contentUriUsesProviderDescriptorAndRetainsDocumentName(): Unit=runBlocking {
  val source=fixture("aac-zero.mp4");val before=hash(source)
  val uri=FileProvider.getUriForFile(context,"${context.packageName}.files",source)
  assertEquals("content",uri.scheme)
  val result=MediaImporter(context).importMedia(uri,output,"provider") {}
  assertEquals(source.name,result.title);assertEquals(MediaImporter.Mode.AAC_REMUX,result.mode)
  audioOnly(result.file);assertEquals(before,hash(source))
 }

 @Test fun emptyAndNoLongerAvailableDocumentsHaveDistinctActionableErrors(): Unit=runBlocking {
  val empty=File(directory,"empty.mp4").apply { writeBytes(byteArrayOf()) }
  val emptyUri=FileProvider.getUriForFile(context,"${context.packageName}.files",empty)
  try { MediaImporter(context).importMedia(emptyUri,output,"empty") {};fail("Expected empty-file error") }
  catch(e: ProductOperationException) { assertTrue(e.userMessage.contains("пуст")) }
  val vanished=fixture("aac-zero.mp4")
  val vanishedUri=FileProvider.getUriForFile(context,"${context.packageName}.files",vanished)
  assertTrue(vanished.delete())
  try { MediaImporter(context).importMedia(vanishedUri,output,"vanished") {};fail("Expected missing document error") }
  catch(e: ProductOperationException) { assertTrue(e.userMessage.contains("недоступен")) }
  assertTrue(output.listFiles().orEmpty().isEmpty());assertTrue(empty.isFile)
 }

 @Test fun insufficientSpaceBeforeImportAndDuringCopyDeletesOnlyOurPartialFile(): Unit=runBlocking {
  val source=fixture("aac-zero.mp4");val before=hash(source)
  val existing=File(output.apply { mkdirs() },"unrelated.m4a").apply { writeText("existing recording fixture") }
  try { MediaImporter(context,availableSpace={0}).importMedia(Uri.fromFile(source),output,"no-space") {};fail("Expected storage error") }
  catch(e: ProductOperationException) { assertTrue(e.userMessage.contains("Недостаточно места")) }
  assertEquals(listOf(existing.name),output.listFiles().orEmpty().map { it.name });assertEquals(before,hash(source))

  val wav=File(directory,"streaming.wav")
  val frames=48000*12
  val header=java.nio.ByteBuffer.allocate(44).order(java.nio.ByteOrder.LITTLE_ENDIAN)
  header.put("RIFF".toByteArray()).putInt(36+frames*2).put("WAVEfmt ".toByteArray()).putInt(16)
   .putShort(1).putShort(1).putInt(48000).putInt(96000).putShort(2).putShort(16).put("data".toByteArray()).putInt(frames*2)
  wav.outputStream().use { stream -> stream.write(header.array());val zeros=ByteArray(4096);var remaining=frames*2
   while(remaining>0) { val n=minOf(remaining,zeros.size);stream.write(zeros,0,n);remaining-=n }
  }
  val original=hash(wav);var checks=0
  try { MediaImporter(context,availableSpace={ if(++checks<3) Long.MAX_VALUE else 0L }).importMedia(Uri.fromFile(wav),output,"disk-full") {};fail("Expected mid-copy storage error") }
  catch(e: ProductOperationException) { assertTrue(e.userMessage.contains("Недостаточно места")) }
  assertTrue(checks>=3);assertEquals(original,hash(wav));assertEquals("existing recording fixture",existing.readText())
  assertEquals(listOf(existing.name),output.listFiles().orEmpty().map { it.name })
 }

 @Test fun collidingOutputAndUnsafeImportIdNeverDeleteExistingAudio(): Unit=runBlocking {
  val source=fixture("audio-only.m4a")
  val existing=File(output.apply { mkdirs() },"collision.audio").apply { writeText("previous saved file") }
  try { MediaImporter(context).importMedia(Uri.fromFile(source),output,"collision") {};fail("Expected collision rejection") }
  catch(_: ProductOperationException) { }
  assertEquals("previous saved file",existing.readText())
  try { MediaImporter(context).importMedia(Uri.fromFile(source),output,"../escape") {};fail("Expected unsafe ID rejection") }
  catch(_: IllegalArgumentException) { }
  assertEquals("previous saved file",existing.readText());assertFalse(File(directory,"escape.audio").exists())
 }

 @Test fun retiringWhisperDeletesOnlyOwnedWeightAndPreservesExternalPackAndAudio(): Unit {
  val isolated=object: android.content.ContextWrapper(context) { override fun getFilesDir()=directory }
  val manager=ModelManager(isolated)
  val retired=manager.file("whisper-tiny/ggml-tiny.bin").apply { parentFile!!.mkdirs();writeText("removed model fixture") }
  val audio=File(directory,"audio/saved.m4a").apply { parentFile!!.mkdirs();writeText("saved audio") }
  val pack=File(directory,"replika-offline-pack.zip").apply { writeText("historical external pack") }
  manager.removeRetiredWhisperFiles()
  assertFalse(retired.exists());assertTrue(audio.isFile);assertTrue(pack.isFile)
 }
}
