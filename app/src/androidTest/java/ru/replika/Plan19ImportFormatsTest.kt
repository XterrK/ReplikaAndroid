package ru.replika

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.media.MediaCodecList
import android.media.MediaExtractor
import android.media.MediaFormat
import android.os.Build
import android.os.Bundle
import android.os.FileObserver
import android.os.SystemClock
import android.view.KeyEvent
import android.view.accessibility.AccessibilityNodeInfo
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.work.WorkManager
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import org.junit.*
import org.junit.Assert.*
import org.junit.rules.TestName
import org.junit.runner.RunWith
import ru.replika.data.ProductOperationException
import ru.replika.data.ProductStorage
import ru.replika.data.Recording
import ru.replika.data.SegmentRow
import ru.replika.ml.AudioDecoder
import ru.replika.ml.MediaImporter
import ru.replika.ui.AppViewModel
import java.io.DataOutputStream
import java.io.File
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.*

/** No model inference: actual provider import, system codec and production PCM conversion. */
private object Plan19ImportEvidence {
 const val assets="plan19-import"
 val instrumentation get()=InstrumentationRegistry.getInstrumentation()
 val context get()=instrumentation.targetContext
 fun sha(file: File): String {
  val digest=MessageDigest.getInstance("SHA-256")
  file.inputStream().buffered().use { input ->
   val block=ByteArray(128*1024)
   while(true) { val count=input.read(block);if(count<0) break;digest.update(block,0,count) }
  }
  return digest.digest().joinToString("") { "%02x".format(it) }
 }
 fun manifest()=JSONObject(instrumentation.context.assets.open("$assets/fixtures.json").bufferedReader().use { it.readText() })
 fun fixtures(): List<JSONObject> {
  val manifest=manifest();check(manifest.getInt("schema_version")==1)
  val rows=manifest.getJSONArray("files")
  return List(rows.length()) { rows.getJSONObject(it) }.also {
   check(it.size==13 && it.map { row -> row.getString("name") }.distinct().size==13)
  }
 }
 fun copy(row: JSONObject,directory: File): File=File(directory,row.getString("name")).also { target ->
  check(!target.exists())
  instrumentation.context.assets.open("$assets/${target.name}").use { source -> target.outputStream().use { source.copyTo(it) } }
  check(target.length()==row.getLong("bytes") && sha(target)==row.getString("sha256"))
 }
 fun uri(source: File)=FileProvider.getUriForFile(context,"${context.packageName}.files",source)
 fun reportDirectory(name: String)=File(context.filesDir,"plan19-import-evidence/$name").also { check(!it.exists() && it.mkdirs()) }
 fun header()=JSONObject().put("schema_version",1).put("newModelInference",false)
  .put("scope","Import/codec/URI/channel/resampling integrity; no speech-quality, ARM or performance acceptance")
  .put("sdk",Build.VERSION.SDK_INT).put("fingerprint",Build.FINGERPRINT)
  .put("fixture_manifest",manifest())
  .put("fixture_manifest_sha256",MessageDigest.getInstance("SHA-256").digest(instrumentation.context.assets.open("$assets/fixtures.json").use { it.readBytes() }).joinToString("") { "%02x".format(it) })
  .put("status","RUNNING")
 fun rms(samples: FloatArray): Double=sqrt(samples.sumOf { it.toDouble()*it }/samples.size.coerceAtLeast(1))
 fun amplitude(samples: FloatArray,hz: Int): Double {
  var real=0.0;var imaginary=0.0
  for(i in samples.indices) { val phase=2*PI*hz*i/16000;real+=samples[i]*cos(phase);imaginary+=samples[i]*sin(phase) }
  return 2*hypot(real,imaginary)/samples.size
 }
 fun inspect(file: File): JSONObject {
  val extractor=MediaExtractor()
  try {
   extractor.setDataSource(file.path)
   assertEquals("Exactly one audio track",1,extractor.trackCount)
   val format=extractor.getTrackFormat(0);val mime=format.getString(MediaFormat.KEY_MIME)!!
   assertTrue(mime.startsWith("audio/"))
   return JSONObject().put("mime",mime).put("rate",format.getInteger(MediaFormat.KEY_SAMPLE_RATE))
    .put("channels",format.getInteger(MediaFormat.KEY_CHANNEL_COUNT))
    .put("advertisedDecoderNames",JSONArray(MediaCodecList(MediaCodecList.REGULAR_CODECS).codecInfos
     .filter { !it.isEncoder && it.supportedTypes.any { type -> type.equals(mime,true) } }.map { it.name }))
  } finally { extractor.release() }
 }
 /** Little-endian PCM16 WAV, generated in bounded blocks. No model data. */
 fun largeWav(file: File,samples: Int) {
  DataOutputStream(file.outputStream().buffered()).use { output ->
   fun le16(value: Int) { output.writeByte(value and 255);output.writeByte((value ushr 8) and 255) }
   fun le32(value: Int) { le16(value and 65535);le16(value ushr 16) }
   output.writeBytes("RIFF");le32(36+samples*2);output.writeBytes("WAVEfmt ");le32(16)
   le16(1);le16(1);le32(16000);le32(32000);le16(2);le16(16);output.writeBytes("data");le32(samples*2)
   val block=ByteArray(32000)
   repeat(16000) { i ->
    val value=(9000*sin(2*PI*440*i/16000)).roundToInt()
    block[i*2]=(value and 255).toByte();block[i*2+1]=((value ushr 8) and 255).toByte()
   }
   var remaining=samples
   while(remaining>0) { val count=minOf(remaining,16000);output.write(block,0,count*2);remaining-=count }
  }
 }
}

@RunWith(AndroidJUnit4::class)
class Plan19ImportFormatsTest {
 @get:Rule val testName=TestName()
 private val evidence=Plan19ImportEvidence
 private lateinit var directory: File
 private lateinit var output: File
 private lateinit var reportDirectory: File
 private lateinit var report: JSONObject
 private val records=JSONArray()
 @Before fun prepare() {
  val identity=UUID.randomUUID().toString()
  directory=File(evidence.context.cacheDir,"exports/plan19-$identity").apply { check(mkdirs()) }
  output=File(directory,"owned").apply { check(mkdir()) }
  reportDirectory=evidence.reportDirectory("formats-$identity")
  report=evidence.header().put("test",testName.methodName).put("cases",records)
 }
 @After fun finish() {
  val removed=if(::directory.isInitialized) directory.deleteRecursively() else true
  if(::report.isInitialized) {
   if(report.getString("status")!="COMPLETE") report.put("status","FAILED_OR_INTERRUPTED")
   if(!removed) report.put("status","CLEANUP_FAILED")
   report.put("temporaryDirectoryRemoved",removed)
   File(reportDirectory,"report.json").writeText(report.toString(2))
  }
  assertTrue("Remove only this test's temporary directory",removed)
 }
 private fun fixture(id: String)=evidence.copy(evidence.fixtures().single { it.getString("id")==id },directory)
 private suspend fun importSource(source: File,id: String=UUID.randomUUID().toString())=
  withTimeout(30000) { MediaImporter(evidence.context).importMedia(evidence.uri(source),output,id) {} }

 @Test fun allThirteenContentUrisImportAndDecodeActualFormats(): Unit=runBlocking {
  for(row in evidence.fixtures()) {
   val result=JSONObject().put("id",row.getString("id")).put("newModelInference",false)
   records.put(result)
   try {
    val source=evidence.copy(row,directory);val original=evidence.sha(source)
    val begin=SystemClock.elapsedRealtime();val imported=importSource(source)
    assertEquals(MediaImporter.Mode.AUDIO_COPY,imported.mode)
    assertFalse(imported.fromVideo);assertEquals(1,imported.audioTrackCount)
    assertEquals(source.name,imported.title)
    assertEquals(original,evidence.sha(imported.file))
    val format=evidence.inspect(imported.file)
    assertEquals(row.getInt("sample_rate"),format.getInt("rate"))
    assertEquals(row.getInt("channels"),format.getInt("channels"))
    val decoded=withTimeout(30000) { withContext(Dispatchers.IO) { AudioDecoder.decode(imported.file.path,File(output,"${UUID.randomUUID()}.pcm")) } }
    val pcm=AudioDecoder.read(decoded.file,0,decoded.samples)
    assertEquals(decoded.samples.toLong()*4,decoded.file.length())
    assertEquals(decoded.samples.toLong()*1000/16000,decoded.durationMs)
    assertTrue("Finite normalized samples: ${source.name}",pcm.all { it.isFinite() && it in -1f..1f })
    assertTrue("Clock ${source.name}: ${decoded.durationMs}",abs(decoded.durationMs-row.getLong("expected_duration_ms"))<=row.getLong("duration_tolerance_ms"))
    assertTrue("Nonempty genuine peaks",decoded.peaks.isNotEmpty() && decoded.peaks.all { it.isFinite() } && decoded.peaks.any { it>0.03f })
    val interior=AudioDecoder.read(decoded.file,16000,16000)
    val a440=evidence.amplitude(interior,440);val a880=evidence.amplitude(interior,880);val a1300=evidence.amplitude(interior,1300)
    assertTrue("440 Hz survives codec/downmix: $a440",a440>0.06)
    val expectedAmplitude=row.getDouble("tone_amplitude_per_source_channel")/row.getInt("channels")
    assertTrue("Actual channel average, with broad codec tolerance",abs(a440-expectedAmplitude)<=expectedAmplitude*0.4)
    if(row.getInt("channels")==2) {
     assertTrue("Right 880 Hz must survive stereo average: $a880",a880>0.06)
     assertTrue("Right channel is averaged rather than summed",abs(a880-expectedAmplitude)<=expectedAmplitude*0.4)
     assertTrue("Both stereo channels retain comparable amplitude",a440/a880 in 0.55..1.8)
    } else assertTrue("Mono has no invented right channel",a880<0.03)
    assertTrue("Tones dominate off-frequency residual",a1300<minOf(a440,if(row.getInt("channels")==2) a880 else a440)/6)
    assertTrue("Leading silence remains",evidence.rms(pcm.copyOfRange(0,1600))<0.025)
    assertTrue("Trailing silence remains",evidence.rms(pcm.copyOfRange(pcm.size-800,pcm.size))<0.025)
    assertTrue("Interior remains non-silent",evidence.rms(interior)>0.07)
    assertEquals(original,evidence.sha(source));assertEquals(original,evidence.sha(imported.file))
    result.put("status","PASS").put("input_sha256",original).put("imported_sha256",evidence.sha(imported.file))
     .put("importMode",imported.mode.name).put("extractedFormat",format).put("samples",decoded.samples)
     .put("duration_ms",decoded.durationMs).put("pcm_bytes",decoded.file.length()).put("pcm_sha256",evidence.sha(decoded.file))
     .put("allSamplesFinite",true).put("rms",evidence.rms(interior))
     .put("spectral_amplitudes",JSONObject().put("440",a440).put("880",a880).put("1300",a1300))
     .put("actualSystemDecode",true).put("elapsed_ms",SystemClock.elapsedRealtime()-begin)
    decoded.file.delete()
   } catch(error: Throwable) { result.put("status","FAIL").put("error",error.toString());throw error }
  }
  assertEquals(13,records.length());report.put("status","COMPLETE")
 }

 @Test fun repeatedContentUriHasIndependentUuidFiles(): Unit=runBlocking {
  val source=fixture("ogg-opus-48k-stereo");val before=evidence.sha(source)
  val first=importSource(source);val second=importSource(source)
  assertNotEquals(first.file.canonicalPath,second.file.canonicalPath)
  assertEquals(before,evidence.sha(first.file));assertEquals(before,evidence.sha(second.file))
  assertTrue(first.file.delete());assertTrue(second.file.isFile)
  val decoded=withTimeout(30000) { withContext(Dispatchers.IO) { AudioDecoder.decode(second.file.path,File(output,"second.pcm")) } }
  assertTrue(decoded.durationMs in 2750..3250);assertTrue(AudioDecoder.read(decoded.file,16000,16000).any { abs(it)>0.03f })
  assertEquals(before,evidence.sha(source));assertEquals(before,evidence.sha(second.file))
  records.put(JSONObject().put("first",first.file.name).put("second",second.file.name).put("input_sha256",before)
   .put("survivorDecodedSamples",decoded.samples).put("firstDeletionDidNotAffectSecond",true))
  report.put("status","COMPLETE")
 }

 @Test fun emptyGarbageAndMissingUrisLeaveNoOwnedOutput(): Unit=runBlocking {
  val sentinel=File(output,"unrelated.keep").apply { writeText("Do not delete unrelated files") };val sentinelHash=evidence.sha(sentinel)
  val empty=File(directory,"empty.wav").apply { writeBytes(byteArrayOf()) }
  val garbage=File(directory,"garbage.mp3").apply { writeText("This original synthetic fixture is not an audio container") }
  val missing=File(directory,"missing.flac")
  for(source in listOf(empty,garbage,missing)) {
   val before=source.takeIf { it.isFile }?.let(evidence::sha)
   var failure: ProductOperationException?=null
   try { importSource(source);fail("Expected actionable import failure: ${source.name}") }
   catch(error: ProductOperationException) { failure=error }
   assertTrue(failure!!.userMessage.isNotBlank())
   assertEquals(listOf(sentinel.name),output.listFiles()!!.map { it.name })
   assertEquals(before,source.takeIf { it.isFile }?.let(evidence::sha));assertEquals(sentinelHash,evidence.sha(sentinel))
   records.put(JSONObject().put("fixture",source.name).put("userMessage",failure!!.userMessage).put("sourceUnchanged",true).put("ownedOutputRemoved",true))
  }
  report.put("status","COMPLETE")
 }

 @Test fun truncatedWavEitherFailsCleanlyOrReportsOnlyAvailablePrefix(): Unit=runBlocking {
  val original=fixture("wav-16k-mono")
  val truncated=File(directory,"truncated.wav").apply { writeBytes(original.readBytes().copyOf(44+32000)) }
  val before=evidence.sha(truncated);val imported=importSource(truncated);val pcm=File(output,"truncated.pcm")
  val result=JSONObject().put("input_sha256",before).put("declared_source_duration_ms",3000)
  try {
   val decoded=withTimeout(30000) { withContext(Dispatchers.IO) { AudioDecoder.decode(imported.file.path,pcm) } }
   assertTrue("Never report missing two seconds as decoded audio",decoded.durationMs in 1L..1250L)
   assertTrue(AudioDecoder.read(pcm,0,decoded.samples).all { it.isFinite() })
   result.put("outcome","DECODED_AVAILABLE_PREFIX").put("decoded_duration_ms",decoded.durationMs)
  } catch(error: CancellationException) { throw error }
   catch(error: Exception) {
    assertFalse("Failed decode removes partial PCM",pcm.exists())
    result.put("outcome","EXPLICIT_DECODE_ERROR").put("error",error.toString())
   }
  assertEquals(before,evidence.sha(truncated));assertEquals(before,evidence.sha(imported.file))
  records.put(result);report.put("status","COMPLETE")
 }

 @Test fun cancelAfterActualCopyWriteRemovesOnlyOwnedPartial(): Unit=runBlocking {
  // 64 MB gives the FileObserver a bounded real-write interval; no large asset is bundled.
  val source=File(directory,"large-copy.wav")
  withContext(Dispatchers.IO) { evidence.largeWav(source,32_000_000) }
  val before=evidence.sha(source);val sentinel=File(output,"prior.keep").apply { writeText("preserved") }
  val sentinelHash=evidence.sha(sentinel);val identity=UUID.randomUUID().toString();val partial=File(output,"$identity.audio")
  val observed=CompletableDeferred<Long>();val jobHolder=AtomicReference<Job>()
  @Suppress("DEPRECATION")
  val observer=object: FileObserver(output.path,FileObserver.MODIFY or FileObserver.CLOSE_WRITE) {
   override fun onEvent(event: Int,path: String?) {
    if(path==partial.name) {
     val size=partial.length()
     if(size>0 && size<source.length() && observed.complete(size)) jobHolder.get()?.cancel(CancellationException("QA cancellation after actual copy bytes"))
    }
   }
  }
  val copying=launch(Dispatchers.IO,start=CoroutineStart.LAZY) { importSource(source,identity) }
  jobHolder.set(copying);observer.startWatching()
  try {
   copying.start()
   val bytes=withTimeout(20000) { observed.await() }
   withTimeout(10000) { copying.join() }
   assertTrue("Cancellation occurred during real copying",copying.isCancelled)
   assertFalse(partial.exists());assertEquals(before,evidence.sha(source));assertEquals(sentinelHash,evidence.sha(sentinel))
   assertEquals(listOf(sentinel.name),output.listFiles()!!.map { it.name })
   records.put(JSONObject().put("actualPartialBytesObserved",bytes).put("sourceBytes",source.length()).put("source_sha256",before)
    .put("cancelledAfterActualWrite",true).put("partialRemoved",true))
  } finally { observer.stopWatching();copying.cancelAndJoin() }
  report.put("status","COMPLETE")
 }

 @Test fun cancelAfterActualDecoderFramesRemovesPcmAndPreservesSource(): Unit=runBlocking {
  val source=File(directory,"long-decode.wav")
  withContext(Dispatchers.IO) { evidence.largeWav(source,16000*180) }
  val before=evidence.sha(source);val imported=importSource(source);val pcm=File(output,"cancelled-decode.pcm")
  val sentinel=File(output,"prior.keep").apply { writeText("preserved") };val sentinelHash=evidence.sha(sentinel)
  val decoding=launch(Dispatchers.IO) { AudioDecoder.decode(imported.file.path,pcm) }
  try {
   val bytes=withTimeout(20000) {
    while(pcm.length()<65536 && decoding.isActive) delay(1)
    assertTrue("Observe real decoder output before cancellation",pcm.length()>=65536 && decoding.isActive)
    pcm.length()
   }
   withTimeout(10000) { decoding.cancelAndJoin() }
   assertTrue(decoding.isCancelled);assertFalse(pcm.exists())
   assertEquals(before,evidence.sha(source));assertEquals(before,evidence.sha(imported.file));assertEquals(sentinelHash,evidence.sha(sentinel))
   records.put(JSONObject().put("actualPcmBytesObserved",bytes).put("source_sha256",before)
    .put("cancelledAfterActualFrames",true).put("partialPcmRemoved",true))
  } finally { decoding.cancelAndJoin() }
  report.put("status","COMPLETE")
 }
}

/** Explicit opt-in real DocumentsUI flow. Root stages three manifest fixtures in Download.
 * Arguments: plan19PickerRun=<fresh-safe-id>, plan19PickerNames=<three exact comma-separated names>.
 * A staged name may have a unique prefix, but must end with its manifest fixture filename.
 */
@RunWith(AndroidJUnit4::class)
class Plan19DocumentsImportTest {
 @get:Rule val compose=createAndroidComposeRule<MainActivity>()
 private val evidence=Plan19ImportEvidence
 private val instrumentation get()=evidence.instrumentation
 private val app get()=evidence.context.applicationContext as ReplikaApp
 private lateinit var vm: AppViewModel
 private lateinit var reportDirectory: File
 private lateinit var report: JSONObject
 private var originalRows: List<Recording>?=null
 private val originalSegments=mutableMapOf<String,List<SegmentRow>>()
 private val originalFileHashes=mutableMapOf<String,String>()
 private val owned=mutableSetOf<String>()
 private var names=emptyList<String>()
 private var ownsImportSession=false
 private fun rows()=runBlocking { app.db.dao().recordingList() }
 private fun exists(tag: String)=compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
 private fun settle() { compose.mainClock.advanceTimeBy(96);compose.waitForIdle() }

 @Before fun prepare() {
  val args=InstrumentationRegistry.getArguments()
  val run=args.getString("plan19PickerRun")?:throw AssertionError("Explicitly stage Download fixtures and pass plan19PickerRun; do not silently skip picker coverage")
  require(Regex("[A-Za-z0-9_-]+").matches(run))
  names=args.getString("plan19PickerNames")?.split(',')?:throw AssertionError("Pass three exact staged Download filenames")
  require(names.size==3 && names.distinct().size==3 && names.all { '/' !in it && '\\' !in it && it.isNotBlank() })
  for(name in names) check(evidence.fixtures().count { name.endsWith(it.getString("name")) }==1)
  reportDirectory=evidence.reportDirectory("picker-$run")
  report=evidence.header().put("test","threeSequentialDownloadsAndPickerBack").put("stagedNames",JSONArray(names))
  if(BuildConfig.BUNDLED_MODELS) runBlocking { app.bundledModels.awaitReady() }
  compose.mainClock.autoAdvance=false
  compose.activityRule.scenario.onActivity {
   vm=ViewModelProvider(it)[AppViewModel::class.java]
   vm.autoProcessNew=false // Import-format checks inspect the IMPORTED row; V1.7b auto-processing is covered elsewhere.
   check(!vm.isRecording.value && vm.importProgress.value==null) { "Do not interrupt an existing recording or import" }
   vm.selected.value=null;vm.clearNotice()
  }
  compose.waitUntil(30000) { compose.mainClock.advanceTimeBy(64);vm.library.value.loaded && exists("recording-home") }
  originalRows=rows()
  check(originalRows!!.none { it.status in setOf("QUEUED","PROCESSING","CANCELLING") }) { "Run import UI coverage while no existing Worker is active" }
  runBlocking {
   for(row in originalRows!!) {
    originalSegments[row.id]=app.db.dao().segmentList(row.id)
    File(row.audioPath).takeIf { it.isFile }?.let { originalFileHashes[it.canonicalPath]=evidence.sha(it) }
   }
  }
  ownsImportSession=true
  settle()
 }
 @After fun cleanOnlyOwnedImports() {
  try {
   if(::vm.isInitialized && ownsImportSession && originalRows!=null) {
    // Return from a picker on failure; never cancel another recording or processing job.
    if(instrumentation.uiAutomation.rootInActiveWindow?.packageName?.toString()?.endsWith(".documentsui")==true)
     instrumentation.uiAutomation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
    val selectedByThisPicker=vm.selected.value
    compose.activityRule.scenario.onActivity { vm.cancelImport();vm.selected.value=null;vm.clearNotice() }
    compose.waitUntil(15000) { vm.importProgress.value==null }
    val before=originalRows?.map { it.id }?.toSet().orEmpty()
    // Recover only the ID returned to this Activity by our picker, never every new matching title.
    rows().singleOrNull { it.id==selectedByThisPicker }?.let { row ->
     if(row.id !in before && row.title in names && runCatching { UUID.fromString(row.id).toString() }.getOrNull()==row.id) owned+=row.id
    }
    runBlocking {
     app.models.gate.withLock {
      val storage=ProductStorage(app.db,File(app.filesDir,"audio"))
      for(identity in owned) {
       val row=app.db.dao().recording(identity)?:continue
       check(identity !in before && row.title in names && row.status=="IMPORTED")
       val file=File(row.audioPath).canonicalFile
       check(file.parentFile==File(app.filesDir,"audio").canonicalFile && file.name.startsWith("$identity."))
       storage.deleteRecording(identity)
      }
     }
     for(row in originalRows.orEmpty()) {
      assertEquals("Preserve prior Room row ${row.id}",row,app.db.dao().recording(row.id))
      assertEquals("Preserve prior corrections ${row.id}",originalSegments[row.id],app.db.dao().segmentList(row.id))
     }
    }
    for((path,hash) in originalFileHashes) assertEquals("Preserve prior audio $path",hash,evidence.sha(File(path)))
    if(originalRows!=null) assertEquals(originalRows!!.map { it.id }.toSet(),rows().map { it.id }.toSet())
    if(::report.isInitialized) report.put("ownedImportedRowsCleaned",owned.size).put("priorRowsAndAudioPreserved",true)
   }
  } catch(error: Throwable) {
   if(::report.isInitialized) report.put("status","CLEANUP_FAILED").put("cleanupError",error.toString())
   throw error
  } finally {
   if(::report.isInitialized) {
    if(report.optString("status")=="RUNNING") report.put("status","FAILED_OR_INTERRUPTED")
    File(reportDirectory,"report.json").writeText(report.toString(2))
   }
  }
 }

 private fun systemWait(timeout: Long=15000,predicate: ()->Boolean) {
  val deadline=SystemClock.elapsedRealtime()+timeout
  while(SystemClock.elapsedRealtime()<deadline) { if(predicate()) return;Thread.sleep(100) }
  capture("timeout-${SystemClock.elapsedRealtime()}")
  throw AssertionError("Timed out waiting for the actual system document picker")
 }
 private fun node(predicate: (AccessibilityNodeInfo)->Boolean): AccessibilityNodeInfo? {
  val root=instrumentation.uiAutomation.rootInActiveWindow?:return null
  fun descend(current: AccessibilityNodeInfo): AccessibilityNodeInfo? {
   if(predicate(current)) return current
   for(index in 0 until current.childCount) current.getChild(index)?.let { child -> descend(child)?.let { return it } }
   return null
  }
  return descend(root)
 }
 private fun clickNode(target: AccessibilityNodeInfo): Boolean {
  var current: AccessibilityNodeInfo?=target
  repeat(8) {
   val value=current?:return false
   if(value.isClickable && value.isEnabled && value.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
   current=value.parent
  }
  return false
 }
 private fun hasClickableParent(target: AccessibilityNodeInfo): Boolean {
  var current: AccessibilityNodeInfo?=target
  repeat(4) {
   val value=current?:return false
   if(value.isClickable && value.isEnabled) return true
   current=value.parent
  }
  return false
 }
 private fun capture(name: String) {
  if(!::reportDirectory.isInitialized) return
  instrumentation.uiAutomation.takeScreenshot()?.let { image ->
   File(reportDirectory,"$name.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG,100,it) };image.recycle()
  }
 }
 private fun openPicker() {
  compose.onNodeWithTag("home-import").assertIsDisplayed().performClick()
  systemWait { instrumentation.uiAutomation.rootInActiveWindow?.packageName?.toString()?.endsWith(".documentsui")==true }
  capture("picker-open-${SystemClock.elapsedRealtime()}")
 }
 private fun chooseDownload(name: String) {
  // Use the real roots drawer. Text fallbacks cover the English/Russian emulator images.
  val isDownload: (AccessibilityNodeInfo)->Boolean={
   it.text?.toString() in setOf("Downloads","Download","Загрузки","Скачанные файлы") && it.isVisibleToUser && hasClickableParent(it)
  }
  if(node(isDownload)==null) {
   val roots=node {
    val description=it.contentDescription?.toString().orEmpty()
    it.isVisibleToUser && it.isClickable && (description.equals("Show roots",true) || description.equals("Open navigation drawer",true) ||
     description.contains("панель навигации",true) || description.contains("Показать корни",true) || description.contains("Показать папки",true))
   }?:throw AssertionError("DocumentsUI roots drawer not found; preserve the captured screenshot")
   assertTrue(clickNode(roots));systemWait { node(isDownload)!=null }
  }
  assertTrue(clickNode(node(isDownload)!!));Thread.sleep(300)
  if(node { it.text?.toString()==name && it.isVisibleToUser }==null) {
   val search=node {
    it.isVisibleToUser && (it.viewIdResourceName?.endsWith("/option_menu_search")==true ||
     it.contentDescription?.toString() in setOf("Search","Поиск"))
   }?:throw AssertionError("DocumentsUI search action unavailable")
   assertTrue(clickNode(search))
   systemWait { node { it.isEditable && it.isVisibleToUser }!=null }
   val field=node { it.isEditable && it.isVisibleToUser }!!
   val arguments=Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,name) }
   assertTrue(field.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,arguments))
   instrumentation.sendKeyDownUpSync(KeyEvent.KEYCODE_ENTER)
  }
  systemWait { node { it.text?.toString()==name && it.isVisibleToUser }!=null }
  capture("picker-${names.indexOf(name)+1}")
  assertTrue(clickNode(node { it.text?.toString()==name && it.isVisibleToUser }!!))
  systemWait(20000) {
   val packageName=instrumentation.uiAutomation.rootInActiveWindow?.packageName?.toString()
   if(packageName?.endsWith(".documentsui")==true) {
    node { it.isVisibleToUser && it.text?.toString() in setOf("Open","OPEN","Открыть","ОТКРЫТЬ") }?.let { clickNode(it) }
    false
   } else packageName==app.packageName
  }
 }
 @Test fun threeSequentialDownloadsAndPickerBack() {
  val prior=originalRows!!;openPicker();capture("picker-back-before")
  assertTrue(instrumentation.uiAutomation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
  systemWait { instrumentation.uiAutomation.rootInActiveWindow?.packageName?.toString()==app.packageName }
  settle();assertEquals(prior,rows());assertNull(vm.importProgress.value)
  report.put("pickerBackCreatedNoRecording",true)
  val importedCases=JSONArray();report.put("cases",importedCases)
  for((index,name) in names.withIndex()) {
   openPicker();chooseDownload(name)
   compose.waitUntil(30000) { vm.importProgress.value==null && vm.selected.value!=null }
   settle()
   val fresh=rows().filter { it.id !in prior.map { value -> value.id }.toSet() && it.id !in owned }
   assertEquals("Exactly one recording per completed picker selection",1,fresh.size)
   val row=fresh.single();owned+=row.id
   val fixture=evidence.fixtures().single { name.endsWith(it.getString("name")) }
   assertEquals(name,row.title);assertEquals("IMPORTED",row.status);assertEquals(-1,row.expectedSpeakers)
   assertEquals(fixture.getString("sha256"),evidence.sha(File(row.audioPath)))
   assertTrue(runBlocking { app.db.dao().segmentList(row.id) }.isEmpty())
   assertTrue("Import must not enqueue model inference",WorkManager.getInstance(app).getWorkInfosByTag(row.id).get().isEmpty())
   val pcm=File(app.cacheDir,"plan19-picker-${row.id}.pcm")
   try {
    val decoded=runBlocking { withTimeout(30000) { withContext(Dispatchers.IO) { AudioDecoder.decode(row.audioPath,pcm) } } }
    assertTrue(abs(decoded.durationMs-fixture.getLong("expected_duration_ms"))<=fixture.getLong("duration_tolerance_ms"))
    assertTrue(AudioDecoder.read(pcm,0,decoded.samples).all { it.isFinite() })
    importedCases.put(JSONObject().put("stagedName",name).put("fixture",fixture.getString("id")).put("recordingId",row.id)
     .put("imported_sha256",evidence.sha(File(row.audioPath))).put("status",row.status).put("samples",decoded.samples)
     .put("duration_ms",decoded.durationMs).put("actualSystemPicker",true).put("actualSystemDecode",true).put("newModelInference",false))
   } finally { pcm.delete() }
   capture("imported-${index+1}")
   assertTrue(instrumentation.uiAutomation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
   compose.waitUntil(10000) { compose.mainClock.advanceTimeBy(64);vm.selected.value==null && exists("library-list") }
   compose.onNodeWithTag("tab-home").performClick();settle()
   compose.onNodeWithTag("home-import").assertIsDisplayed()
  }
  assertEquals(3,owned.size);assertEquals(prior.size+3,rows().size)
  report.put("status","COMPLETE").put("allThreeSequentialImports",true)
 }
}
