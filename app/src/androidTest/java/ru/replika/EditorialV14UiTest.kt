package ru.replika

import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import ru.replika.data.*
import ru.replika.ui.*
import java.io.File

/** Controlled UI evidence; no fabricated inference or physical-microphone claims. */
@RunWith(AndroidJUnit4::class)
class EditorialV14UiTest {
 @get:Rule val compose=createAndroidComposeRule<MainActivity>()
 private val app get()=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
 private lateinit var vm: AppViewModel
 private val id="v14-visual-fixture"
 private var originalTheme=ThemeMode.SYSTEM
 @Before fun setup() {
  compose.activityRule.scenario.onActivity { vm=ViewModelProvider(it)[AppViewModel::class.java];vm.autoProcessNew=false }
  if(BuildConfig.BUNDLED_MODELS) runBlocking { app.bundledModels.awaitReady() }
  compose.waitForIdle()
  compose.activityRule.scenario.onActivity { vm.selected.value=null;vm.clearNotice() }
  originalTheme=runBlocking { AppearancePreferences(app).mode.first() }
  val source=File(app.filesDir,"integration-example.wav");assertTrue(source.exists())
  runBlocking {
   app.db.dao().insert(Recording(id,"Разговор о городе · UI fixture",source.path,status="READY",durationMs=11290,peaks=(0..120).joinToString(",") { (.1+ kotlin.math.abs(kotlin.math.sin(it*.6))*.7).toString() }))
   app.db.dao().clearSegments(id)
   app.db.dao().insertSegments(listOf(
    SegmentRow("$id-a",id,0,3500,0,"Что делает место своим? Для меня это внимание к повседневной жизни.","controlled UI fixture"),
    SegmentRow("$id-b",id,3600,7000,1,"Важно сохранить то, что уже работает. Изменения должны помогать людям.","controlled UI fixture"),
    SegmentRow("$id-c",id,7100,10000,-1,"Можно я добавлю? Иногда маленькая деталь меняет целый район.","controlled UI fixture",reasons="""["Неоднозначный говорящий"]""")))
   app.db.dao().speaker(SpeakerRow(id,0,"Анна"));app.db.dao().speaker(SpeakerRow(id,1,"Михаил"))
  }
 }
 @After fun cleanup() {
  if(::vm.isInitialized) compose.activityRule.scenario.onActivity { vm.selected.value=null;vm.clearNotice() }
  runBlocking { app.db.dao().deleteRecording(id);AppearancePreferences(app).select(originalTheme) }
 }
 private fun capture(name: String) {
  compose.waitForIdle()
  val committed=java.util.concurrent.CountDownLatch(1)
  compose.activityRule.scenario.onActivity { activity ->
   if(android.os.Build.VERSION.SDK_INT>=29) {
    activity.window.decorView.viewTreeObserver.registerFrameCommitCallback { committed.countDown() }
    activity.window.decorView.invalidate()
   } else committed.countDown()
  }
  committed.await(3,java.util.concurrent.TimeUnit.SECONDS)
  InstrumentationRegistry.getInstrumentation().waitForIdleSync()
  Thread.sleep(800) // Surface compositor, dialog and IME transitions are outside Compose idleness.
  val i=InstrumentationRegistry.getInstrumentation()
  val dir=File(app.filesDir,"human-review-v1.5").apply { mkdirs() }
  val c=compose.activity.resources.configuration
  val prefix="${c.screenWidthDp}x${c.screenHeightDp}-font${c.fontScale}-"
  val shot=i.uiAutomation.takeScreenshot()?:error("Screenshot unavailable")
  File(dir,prefix+name+".png").outputStream().use { shot.compress(Bitmap.CompressFormat.PNG,100,it) };shot.recycle()
 }
 private fun open() {
  compose.activityRule.scenario.onActivity { vm.selected.value=id }
  compose.waitUntil(15000) { compose.onAllNodesWithTag("segment-$id-a").fetchSemanticsNodes().isNotEmpty() }
 }
 private fun singleLineAction(label: String) {
  val layouts=mutableListOf<androidx.compose.ui.text.TextLayoutResult>()
  compose.onNodeWithText(label,substring=false,useUnmergedTree=true).performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.GetTextLayoutResult) { action -> assertTrue(action(layouts)) }
  val detail=layouts.joinToString { "size=${it.size},lines=${it.lineCount},overflowWidth=${it.didOverflowWidth},overflowHeight=${it.didOverflowHeight},paragraph=${it.multiParagraph.width}x${it.multiParagraph.height},line=${it.getLineLeft(0)}..${it.getLineRight(0)},lineBottom=${it.getLineBottom(0)},constraints=${it.layoutInput.constraints}" }
  // A no-wrap paragraph retains the available width (122px), while Text can measure to
  // its glyph width (52px for Pause). didOverflowWidth compares those two boxes, so check
  // the actual line extents to detect wrapping/clipping of a label, including old Stop.
  val fits=layouts.isNotEmpty() && layouts.all { it.lineCount==1 && !it.multiParagraph.didExceedMaxLines && it.getLineLeft(0)>=-.5f && it.getLineRight(0)<=it.size.width+.5f && it.getLineBottom(0)<=it.size.height+.5f }
  if(!fits) { File(app.filesDir,"action-layout-$label.txt").writeText(detail);capture("action-layout-failure-$label") }
  assertTrue("Action must fit at the user's font size: $label; $detail",fits)
 }
 private fun contentAboveRecordingActions(paused: Boolean) {
  val firstAction=listOf("recording-delete","recording-pause","recording-stop").minOf { compose.onNodeWithTag(it).getUnclippedBoundsInRoot().top }
  assertTrue("Timer must stay above all three recording actions",compose.onNodeWithTag("recording-timer").getUnclippedBoundsInRoot().bottom<=firstAction)
  // V1.7 keeps one status line ("Идёт запись" / "На паузе") instead of a status plus a hint.
  compose.onNodeWithTag("recording-status").assertTextEquals(if(paused) "На паузе" else "Идёт запись")
  assertTrue("Recording status must stay above all actions",compose.onNodeWithTag("recording-status").getUnclippedBoundsInRoot().bottom<=firstAction)
 }
 @Test fun bothThemesEightScreensAndKeyboard() {
  for(theme in listOf(ThemeMode.LIGHT,ThemeMode.DARK)) {
   compose.activityRule.scenario.onActivity { vm.selected.value=null;vm.selectTheme(theme) }
   compose.waitUntil(5000) { runBlocking { AppearancePreferences(app).mode.first()==theme } }
   // A theme switch can recreate the Activity; wait until its Compose hierarchy is back.
   compose.waitUntil(10000) { runCatching { compose.onAllNodesWithTag("tab-library").fetchSemanticsNodes().isNotEmpty() }.getOrDefault(false) }
   compose.onNodeWithTag("tab-library").performClick()
   capture("${theme.name}-library")
   compose.onNodeWithTag("appearance-settings").performClick()
   compose.onNodeWithTag("theme-"+theme.name).assertIsSelected();capture("${theme.name}-settings")
   compose.onNodeWithContentDescription("Назад").performClick()
   compose.onNodeWithTag("tab-home").performClick()
   compose.onNodeWithTag("liquid-voice-orb").assertExists();capture("${theme.name}-recording-idle")
   compose.onNodeWithTag("tab-models").performClick();capture("${theme.name}-models")
   compose.onNodeWithTag("tab-library").performClick()
   open();capture("${theme.name}-dialogue")
   compose.onNodeWithTag("mode-reading").performClick();capture("${theme.name}-reading")
   compose.onNodeWithTag("mode-dialogue").performClick()
   compose.onNodeWithTag("smart-review-toggle").performClick();capture("${theme.name}-review")
   compose.onNodeWithTag("review-queue").performScrollToNode(hasTestTag("review-edit-$id-c"))
   compose.onNodeWithTag("review-edit-$id-c").performScrollTo().assertIsDisplayed().performClick();capture("${theme.name}-editor")
   compose.onNodeWithTag("editor-text").performClick()
   compose.waitForIdle();Thread.sleep(500)
   compose.onNodeWithTag("editor-text").performScrollTo().assertIsDisplayed()
   val fieldBounds=compose.onNodeWithTag("editor-text").fetchSemanticsNode().boundsInRoot
   assertTrue("Editing field must remain visible above IME",fieldBounds.height>=48f)
   compose.onNodeWithTag("editor-save").assertIsDisplayed()
   capture("${theme.name}-editor-keyboard")
   androidx.test.espresso.Espresso.closeSoftKeyboard()
   compose.onNodeWithTag("editor-save").assertIsDisplayed()
   compose.onNodeWithContentDescription("Закрыть редактор").performClick()
   compose.activityRule.scenario.onActivity { vm.selected.value=null }
   runBlocking { app.db.dao().status(id,"IMPORTED","Готово к обработке") }
   compose.activityRule.scenario.onActivity { vm.selected.value=id }
   compose.waitUntil(10000) { compose.onAllNodesWithTag("processing-pane").fetchSemanticsNodes().isNotEmpty() };capture("${theme.name}-processing-setup")
   // Persisted phase is a UI fixture; never run fictitious ML or attach it to a WorkRequest.
   runBlocking { app.models.gate.lock();app.db.dao().status(id,"PROCESSING","Распознавание речи · UI fixture") }
   try { capture("${theme.name}-processing") }
   finally { runBlocking { app.db.dao().status(id,"ERROR","Ошибка","Controlled fixture: no model files removed") };app.models.gate.unlock() }
   capture("${theme.name}-error")
   runBlocking { app.db.dao().status(id,"READY","Готово") }
   compose.activityRule.scenario.onActivity { vm.selected.value=null }
  }
 }
 @Test fun keyboardSaveAndUndoKeepTheOriginalRoomSegment() {
  open()
  val before=runBlocking { app.db.dao().segment("$id-a")!! }
  compose.onNode(hasContentDescription("Изменить реплику") and hasAnyAncestor(hasTestTag("segment-$id-a")),useUnmergedTree=true).performClick()
  compose.onNodeWithTag("editor-text").performClick().performTextReplacement("Текст после клавиатурной правки.")
  compose.waitForIdle();Thread.sleep(600)
  compose.onNodeWithTag("editor-text").performScrollTo().assertIsDisplayed()
  compose.onNodeWithTag("editor-save").assertIsDisplayed().assertIsEnabled().performClick()
  compose.waitUntil(10000) { runBlocking { app.db.dao().segment("$id-a")?.text=="Текст после клавиатурной правки." } }
  compose.onNodeWithText("Отменить правку",substring=false).performClick()
  compose.waitUntil(10000) { runBlocking { app.db.dao().segment("$id-a")==before } }
 }
 @Test fun appearancePersistsAcrossRecreationAndCanFollowSystem() {
  compose.onNodeWithTag("appearance-settings").performClick()
  compose.onNodeWithTag("theme-DARK").performClick()
  compose.waitUntil(5000) { runBlocking { AppearancePreferences(app).mode.first()==ThemeMode.DARK } }
  compose.activityRule.scenario.recreate()
  compose.onNodeWithTag("theme-DARK").assertIsSelected()
  compose.onNodeWithTag("theme-SYSTEM").performClick()
  compose.waitUntil(5000) { runBlocking { AppearancePreferences(app).mode.first()==ThemeMode.SYSTEM } }
  compose.onNodeWithTag("theme-SYSTEM").assertIsSelected()
 }
 @Test fun virtualRecorderPauseBackSaveDecodeReopen() {
  Assume.assumeTrue("Emulator input only; physical microphone untested",android.os.Build.MODEL.contains("sdk",ignoreCase=true))
  val before=runBlocking { app.db.dao().recordingList().map { it.id }.toSet() }
  compose.onNodeWithTag("liquid-voice-orb").performClick()
  compose.waitUntil(10000) { vm.recordingPhase.value==RecordingPhase.RECORDING }
  compose.waitUntil(10000) { vm.elapsed.value>=1800 }
  assertTrue(vm.voiceLevel.value.isFinite())
  singleLineAction("Удалить");singleLineAction("Пауза");singleLineAction("Сохранить")
  assertTrue("Recording status must stay below the header at the user's font size",compose.onNodeWithTag("recording-status").getUnclippedBoundsInRoot().top>=compose.onNodeWithTag("recording-exit").getUnclippedBoundsInRoot().bottom)
  contentAboveRecordingActions(false)
  capture("virtual-mic-recording")
  compose.onNodeWithTag("recording-pause").performClick();singleLineAction("Продолжить");singleLineAction("Сохранить");contentAboveRecordingActions(true);capture("virtual-mic-paused")
  compose.onNodeWithTag("recording-pause").performClick()
  // System Back is asynchronous: wait for each effect (decision shown, then dismissed and resumed).
  InstrumentationRegistry.getInstrumentation().uiAutomation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
  compose.waitUntil(10000) { vm.recordingPhase.value==RecordingPhase.PAUSED && compose.onAllNodesWithTag("recording-decision").fetchSemanticsNodes().isNotEmpty() }
  InstrumentationRegistry.getInstrumentation().uiAutomation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
  compose.waitUntil(10000) { vm.recordingPhase.value==RecordingPhase.RECORDING && compose.onAllNodesWithTag("recording-decision").fetchSemanticsNodes().isEmpty() }
  compose.onNodeWithTag("recording-stop").performClick() // ✓ saves at once in V1.7.
  compose.onNodeWithTag("recording-decision").assertDoesNotExist()
  compose.waitUntil(12000) { vm.recordingPhase.value==RecordingPhase.SAVED }
  val rec=runBlocking { app.db.dao().recordingList().single { it.id !in before } }
  assertTrue(File(rec.audioPath).length()>0)
  val decoded=runBlocking { ru.replika.ml.AudioDecoder.decode(rec.audioPath,File(app.cacheDir,"v14-recording-check.pcm")) }
  assertTrue(decoded.durationMs>=1000);decoded.file.delete()
  compose.waitUntil(10000) { compose.onAllNodesWithTag("processing-pane").fetchSemanticsNodes().isNotEmpty() }
  compose.activityRule.scenario.recreate();compose.onNodeWithTag("processing-pane").assertExists()
  capture("virtual-mic-saved-reopened")
  compose.activityRule.scenario.onActivity { vm=ViewModelProvider(it)[AppViewModel::class.java];vm.selected.value=null }
  runBlocking { ProductStorage(app.db,File(app.filesDir,"audio")).deleteRecording(rec.id) }
 }
}
