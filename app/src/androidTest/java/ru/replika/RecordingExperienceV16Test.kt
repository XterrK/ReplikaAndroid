package ru.replika

import android.Manifest
import android.accessibilityservice.AccessibilityService
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.os.Build
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import ru.replika.data.AppearancePreferences
import ru.replika.data.ProductStorage
import ru.replika.data.Recording
import ru.replika.data.ThemeMode
import ru.replika.ml.AudioDecoder
import ru.replika.ui.AppViewModel
import ru.replika.ui.RecordingPhase
import ru.replika.ui.clock
import java.io.File
import java.io.FileInputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.math.abs

/** Real emulator MediaRecorder sessions. Silence is valid; no physical-audio or inference claim. */
@RunWith(AndroidJUnit4::class)
class RecordingExperienceV16Test {
 @get:Rule val compose=createAndroidComposeRule<MainActivity>()
 private val instrumentation get()=InstrumentationRegistry.getInstrumentation()
 private val app get()=instrumentation.targetContext.applicationContext as ReplikaApp
 private lateinit var vm: AppViewModel
 private var originalTheme: ThemeMode?=null
 private var originalRows: List<Recording>?=null
 private var originalFiles: Set<String>?=null
 private val audioDirectory get()=File(app.filesDir,"audio")
 private fun audioFiles()=audioDirectory.walkTopDown().filter { it.isFile }.map { it.canonicalPath }.toSet()
 private fun rows()=runBlocking { app.db.dao().recordingList() }
 private fun exists(tag: String)=compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()

 @Before fun prepare() {
  Assume.assumeTrue("Real emulator recording only; physical microphones are outside this regression",
   Build.MODEL.contains("sdk",true) || Build.MODEL.contains("emulator",true) ||
    Build.HARDWARE in setOf("ranchu","goldfish") || Build.FINGERPRINT.startsWith("generic"))
  instrumentation.uiAutomation.executeShellCommand("pm grant ${app.packageName} ${Manifest.permission.RECORD_AUDIO}").use { descriptor ->
   FileInputStream(descriptor.fileDescriptor).bufferedReader().use { it.readText() }
  }
  assertEquals(PackageManager.PERMISSION_GRANTED,app.checkSelfPermission(Manifest.permission.RECORD_AUDIO))
  if(BuildConfig.BUNDLED_MODELS) runBlocking { app.bundledModels.awaitReady() }
  // Freeze only Compose animation time. MediaRecorder and elapsed use real wall time.
  // Explicit frame advancement prevents the continuously drawn orb/VU from blocking idleness.
  compose.mainClock.autoAdvance=false
  compose.activityRule.scenario.onActivity {
   vm=ViewModelProvider(it)[AppViewModel::class.java];vm.selected.value=null;vm.clearNotice()
  }
  compose.waitUntil(30000) { vm.library.value.loaded && exists("recording-home") }
  originalTheme=runBlocking { AppearancePreferences(app).mode.first() }
  originalRows=rows();originalFiles=audioFiles()
  settleFrames()
 }

 @After fun cleanup() {
  if(originalRows!=null && ::vm.isInitialized) {
   compose.activityRule.scenario.onActivity {
    if(vm.isRecording.value || vm.recordingPhase.value==RecordingPhase.STARTING) vm.stopRecording(false)
   }
   compose.waitUntil(15000) { !vm.isRecording.value && vm.recordingPhase.value !in setOf(RecordingPhase.STARTING,RecordingPhase.STOPPING) }
   compose.activityRule.scenario.onActivity { vm.selected.value=null;vm.clearNotice() }
   val before=originalRows!!.map { it.id }.toSet()
   runBlocking { rows().filter { it.id !in before }.forEach { ProductStorage(app.db,audioDirectory).deleteRecording(it.id) } }
   (audioFiles()-originalFiles.orEmpty()).forEach { File(it).delete() }
  }
  originalTheme?.let { runBlocking { AppearancePreferences(app).select(it) } }
 }

 private fun settleFrames() {
  compose.mainClock.advanceTimeBy(600)
  instrumentation.waitForIdleSync()
 }
 private fun systemBack() {
  assertTrue("Android must dispatch system Back",instrumentation.uiAutomation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
  instrumentation.waitForIdleSync()
  settleFrames()
 }
 private fun assertUnpublished() {
  assertEquals("A live/decision draft must not create a Room recording",originalRows,rows())
  assertEquals("No draft may be published to the library",originalRows!!.map { it.id }.toSet(),vm.library.value.records.map { it.id }.toSet())
  assertNull("A draft must not select a Workspace",vm.selected.value)
 }
 private fun startRealRecording(): File {
  compose.onNodeWithTag("recording-timer").assertDoesNotExist()
  assertEquals(0L,vm.elapsed.value)
  compose.onNodeWithTag("liquid-voice-orb").performClick()
  compose.waitUntil(15000) { vm.recordingPhase.value==RecordingPhase.RECORDING && vm.elapsed.value>=1800L }
  settleFrames()
  assertTrue(vm.isRecording.value);assertFalse(vm.paused.value)
  assertTrue("Silence is allowed; the real envelope must stay finite and normalized",vm.voiceLevel.value.isFinite() && vm.voiceLevel.value in 0f..1f)
  compose.onNodeWithTag("recording-exit").assertIsDisplayed().assertIsEnabled()
  compose.onNodeWithText("Запись",substring=false).assertIsDisplayed()
  compose.onNodeWithText("Говорите, мы слушаем",substring=false).assertIsDisplayed()
  compose.onNodeWithTag("recording-stop").assertTextEquals("Завершить")
  compose.onNodeWithTag("recording-timer").assertIsDisplayed()
  val draft=(audioFiles()-originalFiles.orEmpty()).single()
  assertUnpublished()
  return File(draft)
 }
 private fun openDecision(trigger: String) {
  if(trigger=="system-back") systemBack() else {
   compose.onNodeWithTag(trigger).performClick();settleFrames()
  }
  compose.waitUntil(10000) {
   compose.mainClock.advanceTimeBy(64)
   vm.recordingPhase.value==RecordingPhase.PAUSED && exists("recording-decision")
  }
  settleFrames()
  compose.onNodeWithTag("recording-decision").assertIsDisplayed()
  compose.onNodeWithTag("recording-save").assertIsDisplayed().assertIsEnabled().assertTextEquals("Сохранить запись")
  compose.onNodeWithTag("recording-discard").assertIsDisplayed().assertIsEnabled().assertTextEquals("Удалить запись")
  assertTrue("Decision pauses, rather than finalizes, MediaRecorder",vm.isRecording.value && vm.paused.value)
  assertFrozenElapsed()
  assertUnpublished()
 }
 private fun assertFrozenElapsed() {
  val elapsed=vm.elapsed.value
  Thread.sleep(700) // Wall time: a Compose clock advance cannot prove MediaRecorder is paused.
  assertEquals("Paused recording must exclude decision time",elapsed,vm.elapsed.value)
 }
 private fun dismissDecision(expected: RecordingPhase) {
  systemBack()
  compose.waitUntil(10000) {
   compose.mainClock.advanceTimeBy(64)
   vm.recordingPhase.value==expected && !exists("recording-decision")
  }
  settleFrames()
  compose.onNodeWithTag("recording-timer").assertIsDisplayed()
  assertUnpublished()
 }
 private fun discard(draft: File) {
  compose.onNodeWithTag("recording-discard").performClick();settleFrames()
  compose.waitUntil(15000) { vm.recordingPhase.value==RecordingPhase.IDLE && !draft.exists() }
  settleFrames()
  assertFalse("Discard must delete the actual recorder output",draft.exists())
  assertEquals("Discard must leave no orphan audio",originalFiles,audioFiles())
  assertUnpublished()
  assertFalse(vm.isRecording.value);assertFalse(vm.paused.value)
  assertEquals(0L,vm.elapsed.value)
  compose.onNodeWithTag("recording-home").assertIsDisplayed()
  compose.onNodeWithTag("workspace").assertDoesNotExist()
  compose.onNodeWithTag("library-list").assertDoesNotExist()
  compose.onNodeWithTag("recording-decision").assertDoesNotExist()
  compose.onNodeWithTag("recording-timer").assertDoesNotExist()
  compose.onNodeWithTag("recording-exit").assertDoesNotExist()
  compose.onNodeWithText("Нажмите на шар для записи",substring=false).assertIsDisplayed()
 }

 @Test fun savePublishesOneDecodableRecordingAndOpensWorkspace() {
  startRealRecording()
  openDecision("recording-stop")
  val recordedDuration=vm.elapsed.value
  compose.onNodeWithTag("recording-save").performClick();settleFrames()
  compose.waitUntil(15000) { vm.recordingPhase.value==RecordingPhase.SAVED && vm.selected.value!=null }
  settleFrames()
  val before=originalRows!!.map { it.id }.toSet()
  val saved=rows().filter { it.id !in before }.single()
  assertEquals(saved.id,vm.selected.value)
  assertEquals("Saved metadata retains live time after elapsed resets",recordedDuration,saved.durationMs)
  assertTrue(saved.durationMs>=1500L)
  assertEquals(0L,vm.elapsed.value);assertFalse(vm.isRecording.value)
  assertEquals("Save keeps exactly one owned audio file",setOf(File(saved.audioPath).canonicalPath),audioFiles()-originalFiles.orEmpty())
  assertTrue(File(saved.audioPath).length()>0)
  compose.waitUntil(15000) {
   compose.mainClock.advanceTimeBy(64)
   runCatching {
    compose.onNodeWithTag("workspace").assertIsDisplayed()
    compose.onNodeWithTag("processing-pane").assertIsDisplayed()
    true
   }.getOrDefault(false)
  }
  compose.onNodeWithTag("recording-decision").assertDoesNotExist()
  compose.onNodeWithTag("recording-timer").assertDoesNotExist()
  val pcm=File(app.cacheDir,"v16-${saved.id}-decode.pcm")
  try {
   val decoded=runBlocking { AudioDecoder.decode(saved.audioPath,pcm) }
   assertTrue("Real AAC output must decode to at least 1.5 seconds",decoded.durationMs>=1500L)
   assertEquals(decoded.samples.toLong()*4,decoded.file.length())
   assertTrue("Decoded duration must follow live time",abs(decoded.durationMs-saved.durationMs)<=1000L)
   assertTrue("Silent decoded samples are valid",AudioDecoder.read(decoded.file,0,decoded.samples).all { it.isFinite() && it in -1f..1f })
  } finally { pcm.delete() }
  compose.activityRule.scenario.recreate()
  compose.activityRule.scenario.onActivity { vm=ViewModelProvider(it)[AppViewModel::class.java] }
  compose.waitUntil(15000) { compose.mainClock.advanceTimeBy(64);exists("workspace") && exists("processing-pane") }
  settleFrames()
  assertEquals(saved.id,vm.selected.value)
  assertEquals("Reopening must not publish a duplicate",listOf(saved),rows().filter { it.id !in before })
  systemBack()
  compose.waitUntil(10000) {
   compose.mainClock.advanceTimeBy(64)
   vm.selected.value==null && exists("library-list")
  }
  settleFrames()
  compose.onNodeWithText("Запись",substring=false).performClick();settleFrames()
  compose.onNodeWithTag("recording-home").assertIsDisplayed()
  compose.onNodeWithTag("recording-timer").assertDoesNotExist()
  assertEquals(0L,vm.elapsed.value)
  runBlocking { ProductStorage(app.db,audioDirectory).deleteRecording(saved.id) }
  assertNull(runBlocking { app.db.dao().recording(saved.id) })
  assertFalse(File(saved.audioPath).exists())
  assertEquals(originalFiles,audioFiles())
 }

 @Test fun exitStopAndSystemBackPauseDecisionAndDismissRestoresOnlyRunningSessions() {
  val draft=startRealRecording()
  for(trigger in listOf("recording-exit","recording-stop","system-back")) {
   openDecision(trigger)
   assertTrue("Draft must remain on disk until an explicit decision",draft.isFile)
   dismissDecision(RecordingPhase.RECORDING)
   val resumed=vm.elapsed.value
   compose.waitUntil(10000) { vm.elapsed.value>=resumed+350 }
   assertFalse(vm.paused.value)
  }
  compose.onNodeWithText("Пауза",substring=false).performClick();settleFrames()
  compose.waitUntil(10000) { vm.recordingPhase.value==RecordingPhase.PAUSED }
  for(trigger in listOf("recording-exit","recording-stop")) {
   openDecision(trigger)
   dismissDecision(RecordingPhase.PAUSED)
   assertTrue(vm.paused.value)
   assertFrozenElapsed()
   compose.onNodeWithText("Продолжить",substring=false).assertIsDisplayed()
   compose.onNodeWithText("Продолжите, когда будете готовы",substring=false).assertIsDisplayed()
  }
  openDecision("recording-stop")
  discard(draft)
 }

 @Test fun lightAndDarkCenteredHomeCaptureIdleRecordingDecisionAndPostDiscard() {
  for(theme in listOf(ThemeMode.LIGHT,ThemeMode.DARK)) {
   compose.activityRule.scenario.onActivity { vm.selectTheme(theme) }
   compose.waitUntil(10000) { vm.themeMode.value==theme && runBlocking { AppearancePreferences(app).mode.first()==theme } }
   settleFrames()
   assertCenteredHome();compose.onNodeWithTag("recording-timer").assertDoesNotExist()
   capture(theme,"idle")
   val draft=startRealRecording()
   assertCenteredHome()
   capture(theme,"recording")
   openDecision(if(theme==ThemeMode.LIGHT) "recording-exit" else "recording-stop")
   capture(theme,"decision")
   discard(draft)
   assertCenteredHome()
   capture(theme,"post-discard")
  }
 }
 private fun assertCenteredHome() {
  val home=compose.onNodeWithTag("recording-home").getUnclippedBoundsInRoot()
  val orb=compose.onNodeWithTag("liquid-voice-orb").getUnclippedBoundsInRoot()
  val meter=compose.onNodeWithTag("microphone-vu").getUnclippedBoundsInRoot()
  val center=(home.left.value+home.right.value)/2
  assertTrue("The orb must be centered without end padding or a VU gutter",abs((orb.left.value+orb.right.value)/2-center)<=1.1f)
  assertTrue("Orb canvas remains square",abs((orb.right-orb.left).value-(orb.bottom-orb.top).value)<=1.1f)
  assertTrue("Orb remains within home",orb.left>=home.left && orb.right<=home.right && orb.top>=home.top && orb.bottom<=home.bottom)
  assertTrue("VU is a tall home overlay",(meter.bottom-meter.top).value>=(home.bottom-home.top).value*.70f)
  assertTrue("VU is approximately 64dp wide",abs((meter.right-meter.left).value-64f)<=2f)
  assertTrue("VU is anchored to the physical right edge",abs(meter.right.value-home.right.value)<=1.1f)
  assertTrue("VU remains within home height",meter.top>=home.top && meter.bottom<=home.bottom)
  for(tag in listOf("recording-status","recording-timer")) if(exists(tag)) {
   val text=compose.onNodeWithTag(tag).getUnclippedBoundsInRoot()
   assertTrue("$tag must share the orb center",abs((text.left.value+text.right.value)/2-center)<=1.1f)
  }
  if(vm.isRecording.value) {
   val actionTop=compose.onNodeWithTag("recording-stop").getUnclippedBoundsInRoot().top
   assertTrue("Timer must remain above recording controls",compose.onNodeWithTag("recording-timer").getUnclippedBoundsInRoot().bottom<=actionTop)
   val stop=compose.onNodeWithTag("recording-stop").getUnclippedBoundsInRoot()
   assertTrue("Recording controls retain a 56dp target",stop.bottom-stop.top>=56.dp)
  }
 }
 private fun capture(theme: ThemeMode,stage: String,injected: Boolean=false) {
  settleFrames()
  val committed=CountDownLatch(1)
  compose.activityRule.scenario.onActivity { activity ->
   if(Build.VERSION.SDK_INT>=29) {
    activity.window.decorView.viewTreeObserver.registerFrameCommitCallback { committed.countDown() }
    activity.window.decorView.postInvalidateOnAnimation()
   } else committed.countDown()
  }
  committed.await(2,TimeUnit.SECONDS)
  Thread.sleep(500) // Bounded compositor settling, including the real modal window; no Compose idle loop.
  val directory=File(app.filesDir,"ui-v1.6").apply { check(isDirectory || mkdirs()) }
  val configuration=compose.activity.resources.configuration
  val name="${configuration.screenWidthDp}x${configuration.screenHeightDp}-font${configuration.fontScale}-${theme.name}-$stage"
  val screenshot=instrumentation.uiAutomation.takeScreenshot()?:error("Android screenshot unavailable")
  val target=File(directory,"$name.png")
  try { target.outputStream().use { assertTrue(screenshot.compress(Bitmap.CompressFormat.PNG,100,it)) } }
  finally { screenshot.recycle() }
  assertTrue("Actual Android screenshot must be written",target.isFile && target.length()>0)
  File(directory,"$name.json").writeText(JSONObject()
   .put("image",target.name).put("theme",theme.name).put("stage",stage)
   .put("capture","uiAutomation.takeScreenshot; actual app window")
   .put("audioSource","Emulator MediaRecorder input; silence allowed; physical microphone untested")
   .put("voiceLevelInjected",injected).put("voiceLevelObserved",vm.voiceLevel.value)
   .put("phase",vm.recordingPhase.value.name).put("elapsedMs",vm.elapsed.value)
   .put("timer",if(vm.isRecording.value) clock(vm.elapsed.value) else JSONObject.NULL)
   .put("device",Build.MODEL).put("api",Build.VERSION.SDK_INT).toString(2))
 }
}
