package ru.replika

import androidx.compose.ui.test.*
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.*
import org.junit.Assert.*
import ru.replika.data.*
import ru.replika.ui.*
import java.io.File

/** User-visible regression: home/export navigation and the formerly offset transcript player. */
class HomeExperienceV15Test {
 @get:Rule val compose=androidx.compose.ui.test.junit4.createAndroidComposeRule<MainActivity>()
 private val app get()=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
 private lateinit var vm: AppViewModel
 private val id="v15-home-player-fixture"
 @Before fun fixture() {
  if(BuildConfig.BUNDLED_MODELS) runBlocking { app.bundledModels.awaitReady() }
  compose.waitForIdle()
  compose.activityRule.scenario.onActivity { vm=ViewModelProvider(it)[AppViewModel::class.java];vm.selected.value=null;vm.clearNotice() }
  val source=File(app.filesDir,"integration-example.wav");assertTrue(source.isFile)
  runBlocking {
   app.db.dao().insert(Recording(id,"Экспорт с главной · UI fixture",source.path,status="READY",durationMs=11290,peaks=(0..160).joinToString(",") { (.03+kotlin.math.abs(kotlin.math.sin(it*.17))*.8).toString() }))
   app.db.dao().clearSegments(id)
   app.db.dao().insertSegments(listOf(SegmentRow("$id-a",id,0,11000,0,"Проверяем экспорт с главного экрана.","Controlled UI fixture, no ASR claim")))
  }
 }
 @After fun clean() {
  if(::vm.isInitialized) compose.activityRule.scenario.onActivity { vm.selected.value=null;vm.clearNotice() }
  runBlocking { app.db.dao().deleteRecording(id) }
 }
 @Test fun launcherOpensOrbLibraryHasOwnTabAndTranscriptExportsRoomText() {
  val activity=compose.activity
  compose.onNodeWithTag("recording-home").assertIsDisplayed()
  compose.onNodeWithTag("liquid-voice-orb").assertIsDisplayed().assertHasClickAction()
  compose.onNodeWithTag("home-import").assertIsDisplayed().assert(hasText("Импорт аудио или видео")).assertHasClickAction()
  // V1.7: home has no «Экспорт» (nothing is selected there); export lives in the transcript.
  compose.onNodeWithTag("home-export").assertDoesNotExist()
  compose.onNodeWithTag("tab-library").performClick()
  compose.onNodeWithTag("library-search").assertIsDisplayed()
  compose.onNodeWithTag("library-list").performScrollToNode(hasTestTag("recording-$id"))
  compose.onNodeWithTag("recording-meta-$id",useUnmergedTree=true).assertTextEquals("00:11 · 1 говорящий · RU")
  compose.onNodeWithTag("recording-preview-$id",useUnmergedTree=true).assertTextEquals("Проверяем экспорт с главного экрана.")
  compose.onNodeWithTag("recording-$id").performClick()
  compose.waitUntil(10000) { compose.onAllNodesWithTag("workspace-export").fetchSemanticsNodes().isNotEmpty() }
  compose.onNodeWithTag("workspace-export").performClick()
  compose.onNodeWithTag("transcript-export").assertExists()
  val target=File(app.cacheDir,"exports/replika-$id.json").apply { delete() }
  compose.onNodeWithText("JSON",substring=false).performClick()
  compose.waitUntil(10000) { target.isFile && target.length()>0 }
  val json=org.json.JSONObject(target.readText())
  assertEquals(listOf("transcript"),json.keys().asSequence().toList())
  val exported=json.getJSONArray("transcript").getJSONObject(0)
  assertEquals("Проверяем экспорт с главного экрана.",exported.getString("text"))
  assertEquals("speaker_1",exported.getString("speaker_id"))
  assertEquals(0L,exported.getLong("start_ms"));assertEquals(11000L,exported.getLong("end_ms"))
  assertEquals(setOf("speaker_id","start_ms","end_ms","text"),exported.keys().asSequence().toSet())
  assertFalse(target.readBytes().take(3)==listOf(0xef.toByte(),0xbb.toByte(),0xbf.toByte()))
  val automation=InstrumentationRegistry.getInstrumentation().uiAutomation
  compose.waitUntil(15000) { automation.rootInActiveWindow?.packageName?.toString() in setOf("android","com.android.intentresolver") }
  automation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
  // API28 can retain the Chooser accessibility root after Back even while WindowManager
  // has already resumed/focused this Activity. Verify the actual app window and content.
  compose.waitUntil(10000) {
   var focused=false
   InstrumentationRegistry.getInstrumentation().runOnMainSync { focused=activity.window.decorView.hasWindowFocus() && activity.lifecycle.currentState==androidx.lifecycle.Lifecycle.State.RESUMED }
   focused
  }
  compose.onNodeWithTag("workspace").assertIsDisplayed()
  val juryBytes=target.readBytes()
  compose.onNodeWithTag("workspace-export").performClick()
  val diagnostic=File(app.cacheDir,"exports/replika-$id.diagnostic.json").apply { delete() }
  compose.onNodeWithTag("export-diagnostic-json").performScrollTo().performClick()
  compose.waitUntil(10000) { diagnostic.isFile && diagnostic.length()>0 }
  val legacy=org.json.JSONObject(diagnostic.readText())
  assertEquals("Проверяем экспорт с главного экрана.",legacy.getJSONArray("segments").getJSONObject(0).getString("text"))
  assertEquals(id,legacy.getString("recordingId"));assertTrue(legacy.has("diagnostics"))
  assertArrayEquals("Diagnostic export must not overwrite jury JSON",juryBytes,target.readBytes())
  val proof=File(app.filesDir,"hack-step01-ui").apply { mkdirs() }
  File(proof,"jury.json").writeBytes(juryBytes)
  File(proof,"diagnostic.json").writeBytes(diagnostic.readBytes())
  File(proof,"scope.json").writeText(org.json.JSONObject().put("controlledUiFixture",true).put("newModelInference",false).put("sourceTest","HomeExperienceV15Test").put("bothFormatsExportedThroughUi",true).put("juryFileNotOverwritten",true).toString(2))
  // File creation precedes the Main-dispatcher chooser launch. Wait for its window before Back.
  compose.waitUntil(15000) { automation.rootInActiveWindow?.packageName?.toString() in setOf("android","com.android.intentresolver") }
  automation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
  compose.waitUntil(10000) {
   var focused=false
   InstrumentationRegistry.getInstrumentation().runOnMainSync { focused=activity.window.decorView.hasWindowFocus() }
   focused
  }
  compose.onNodeWithTag("workspace").assertIsDisplayed()
 }
 @Test fun newRecordingDefaultsToAutomaticAndManualModesRemainSelectable() {
  runBlocking { app.db.dao().insert(Recording(id,"Новый импорт · default auto",File(app.filesDir,"integration-example.wav").path,status="IMPORTED")) }
  compose.activityRule.scenario.onActivity { vm.selected.value=id }
  // V1.7b: no setup screen. One line shows the defaults; the parameters live in an optional sheet.
  compose.waitUntil(10000) { compose.onAllNodesWithTag("processing-options").fetchSemanticsNodes().isNotEmpty() }
  compose.onNodeWithTag("processing-options-summary",useUnmergedTree=true).assertTextEquals("Говорящие: авто · Язык: авто")
  compose.onNodeWithTag("create-transcript").assertIsDisplayed().assertIsEnabled()
  compose.onNodeWithTag("speakers-automatic").assertDoesNotExist()
  // Everything fits without scrolling on a phone-sized screen.
  val pane=compose.onNodeWithTag("processing-pane").getUnclippedBoundsInRoot()
  val row=compose.onNodeWithTag("processing-options").getUnclippedBoundsInRoot()
  assertTrue("Processing setup must not need scrolling",row.bottom<=pane.bottom)
  compose.onNodeWithTag("processing-options").performClick()
  compose.waitUntil(10000) { compose.onAllNodesWithTag("speakers-automatic").fetchSemanticsNodes().isNotEmpty() }
  compose.onNodeWithTag("speakers-automatic").assertIsSelected()
  compose.onNodeWithTag("speakers-single").assertIsNotSelected().performClick().assertIsSelected()
  compose.onNodeWithTag("speakers-fixed").performClick().assertIsSelected()
  compose.onNodeWithTag("speaker-count").assertIsDisplayed()
  compose.onNodeWithTag("speakers-automatic").performClick().assertIsSelected()
  compose.onNodeWithTag("speakers-single").performClick()
  androidx.test.espresso.Espresso.pressBack()
  compose.waitUntil(10000) { compose.onAllNodesWithTag("processing-options-sheet").fetchSemanticsNodes().isEmpty() }
  assertEquals("Dismissing the sheet starts nothing","IMPORTED",runBlocking { app.db.dao().recording(id)!!.status })
 }
 @Test fun largeMonoWaveformAndTransportStayCenteredAndSeekIsAccessible() {
  compose.activityRule.scenario.onActivity { vm.selected.value=id }
  compose.waitUntil(10000) { compose.onAllNodesWithTag("audio-waveform").fetchSemanticsNodes().isNotEmpty() }
  val player=compose.onNodeWithTag("audio-player").getUnclippedBoundsInRoot()
  val play=compose.onNodeWithTag("player-main-play").getUnclippedBoundsInRoot()
  val wave=compose.onNodeWithTag("audio-waveform").getUnclippedBoundsInRoot()
  assertTrue("Play control must be centered independently of metadata",kotlin.math.abs((player.left.value+player.right.value)/2-(play.left.value+play.right.value)/2)<1.1f)
  assertTrue("Waveform must be substantial even on compact devices",wave.bottom-wave.top>=80.dp)
  val speed=compose.onNodeWithTag("playback-speed").getUnclippedBoundsInRoot()
  val forward=compose.onNodeWithContentDescription("Вперёд 10 секунд").getUnclippedBoundsInRoot()
  if(speed.top<forward.bottom && speed.bottom>forward.top) assertTrue("Speed must not crowd the forward target",speed.left-forward.right>=6.dp)
  compose.onNodeWithContentDescription("Звуковая дорожка одного участника").assertExists()
  compose.onNodeWithTag("audio-waveform").performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.SetProgress) { it(.5f) }
  compose.waitUntil(5000) { runCatching { compose.onNodeWithTag("playback-clock").assertTextEquals("00:05");true }.getOrDefault(false) }
  compose.onNodeWithTag("smart-review-toggle").performClick()
  compose.onNodeWithTag("audio-waveform").assertDoesNotExist()
  compose.onNodeWithTag("review-queue").assertIsDisplayed()
  compose.onNodeWithTag("mode-reading").performClick()
  compose.onNodeWithTag("audio-waveform").assertDoesNotExist()
  compose.onNodeWithTag("playback-speed").assertIsDisplayed()
 }
}
