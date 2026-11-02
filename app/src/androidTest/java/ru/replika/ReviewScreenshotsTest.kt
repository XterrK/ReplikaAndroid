package ru.replika
import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.File
@RunWith(AndroidJUnit4::class)
class ReviewScreenshotsTest {
 @get:Rule val compose=createAndroidComposeRule<MainActivity>()
 private fun capture(name: String) {
  compose.waitForIdle()
  Thread.sleep(500) // Compose idleness does not wait for the native dialog fade/compositor.
  compose.waitForIdle()
  InstrumentationRegistry.getInstrumentation().waitForIdleSync()
  Thread.sleep(100)
  val i=InstrumentationRegistry.getInstrumentation();val folder=File(i.targetContext.filesDir,"human-review-v1.2").apply { mkdirs() }
  val image=i.uiAutomation.takeScreenshot()?:error("Android did not return a screenshot")
  val prefix=if(compose.activity.resources.configuration.fontScale>=1.25f) "compact130-" else ""
  val destination=File(folder,prefix+name)
  if(destination.exists()) check(destination.renameTo(File(folder,prefix+name.removeSuffix(".png")+"-"+System.nanoTime()+".png")))
  destination.outputStream().use { image.compress(Bitmap.CompressFormat.PNG,100,it) };image.recycle()
 }
 private fun hideKeyboard() {
  // The editor is a dialog window; the Activity token belongs to a different input target.
  androidx.test.espresso.Espresso.closeSoftKeyboard()
  compose.mainClock.advanceTimeBy(500)
  compose.waitForIdle()
 }
 @Test fun libraryModelsAndRecording() {
  capture("01-library.png")
  compose.onNodeWithText("Модели").performClick()
  compose.waitUntil(60000) {
   var checked=false
   compose.activityRule.scenario.onActivity { checked=androidx.lifecycle.ViewModelProvider(it)[ru.replika.ui.AppViewModel::class.java].models.value.size==4 }
   checked
  }
  capture("07-models-diagnostics.png")
  if(BuildConfig.BUNDLED_MODELS) {
   compose.onNodeWithTag("models-list").performScrollToNode(hasTestTag("models-advanced-toggle"))
   compose.onNodeWithTag("models-advanced-toggle").performClick()
  }
  compose.onNodeWithTag("models-list").performScrollToNode(hasText("Импорт offline pack"));capture("13-offline-pack.png")
  compose.onNodeWithTag("models-list").performScrollToNode(hasText("Silero VAD"));capture("31-models-installed-small-file.png")
  compose.onNodeWithTag("models-list").performScrollToNode(hasText("Диагностика"))
  compose.onNodeWithText("Память · PSS").performScrollTo();capture("12-models-diagnostics-details.png")
  compose.onNodeWithTag("models-list").performScrollToNode(hasTestTag("diagnostics-details"))
  compose.onNodeWithTag("diagnostics-details").performScrollTo();capture("35-models-metrics.png")
  compose.onNodeWithTag("diagnostics-details").performClick();capture("30-models-technical-details.png")
  compose.onNodeWithContentDescription("Закрыть диагностику").performClick()
  compose.onNodeWithText("Записи").performClick()
  // Physical microphone validation requires separate explicit consent.
  Assume.assumeTrue("Recording screenshot is restricted to an emulator",android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk",ignoreCase=true))
  val app=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
  val idsBefore=runBlocking { app.db.dao().recordingList().map { it.id }.toSet() }
  compose.onNodeWithText("Записать").performClick();capture("02-recording.png")
  compose.waitUntil(5000) {
   var ticks=false;compose.activityRule.scenario.onActivity { ticks=androidx.lifecycle.ViewModelProvider(it)[ru.replika.ui.AppViewModel::class.java].levels.value.size>=3 };ticks
  }
  capture("32-recording-early-levels.png")
  compose.onNodeWithText("Пауза").performClick()
  compose.onNodeWithText("Продолжить").assertIsDisplayed().performClick()
  compose.onNodeWithText("Пауза").assertIsDisplayed()
  compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.CREATED)
  compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.RESUMED)
  compose.onNodeWithText("Продолжить").assertIsDisplayed()
  compose.onNodeWithText("Продолжить").performClick()
  compose.waitUntil(10000) {
   var elapsed=0L;compose.activityRule.scenario.onActivity { elapsed=androidx.lifecycle.ViewModelProvider(it)[ru.replika.ui.AppViewModel::class.java].elapsed.value };elapsed>=2000
  }
  compose.onNodeWithText("Сохранить",substring=false).performClick()
  var saved: ru.replika.data.Recording?=null
  compose.waitUntil(10000) { saved=runBlocking { app.db.dao().recordingList().singleOrNull { it.id !in idsBefore } };saved!=null }
  val record=saved!!;assertEquals("IMPORTED",record.status);assertTrue(File(record.audioPath).length()>0)
  val decoded=runBlocking { ru.replika.ml.AudioDecoder.decode(record.audioPath,File(app.cacheDir,"v12-virtual-recording.pcm")) }
  assertTrue(decoded.durationMs>=1000);decoded.file.delete()
  compose.waitUntil(10000) { compose.onAllNodesWithTag("processing-pane").fetchSemanticsNodes().isNotEmpty() }
  compose.onNodeWithText("Готово к обработке").assertIsDisplayed()
  capture("33-recording-saved-setup.png")
  File(app.filesDir,"v12-recording-ui-"+compose.activity.resources.configuration.fontScale+".json").writeText(org.json.JSONObject()
   .put("virtualEmulatorInputOnly",true).put("physicalMicrophoneTested",false).put("pauseResume",true)
   .put("backgroundAutoPause",true).put("savedPlayableM4a",true).put("decodedDurationMs",decoded.durationMs).toString(2))
  compose.activityRule.scenario.onActivity { androidx.lifecycle.ViewModelProvider(it)[ru.replika.ui.AppViewModel::class.java].selected.value=null }
  runBlocking { app.models.gate.lock();try { ru.replika.data.ProductStorage(app.db,File(app.filesDir,"audio")).deleteRecording(record.id) } finally { app.models.gate.unlock() } }
  assertFalse(File(record.audioPath).exists())
 }
 @Test fun actualShortSpeechReviewQueue() {
  val i=InstrumentationRegistry.getInstrumentation();val app=i.targetContext.applicationContext as ReplikaApp
  val dao=app.db.dao();val id="integration-v12-warning"
  val row=runBlocking { dao.segmentList(id).firstOrNull { ru.replika.ui.reviewIssues(it).isNotEmpty() } }?:error("Run WarningPipelineTest: real nonblank warning is required")
  val resetReviewed=row.reviewed
  if(resetReviewed) runBlocking { dao.updateSegment(row.copy(reviewed=false)) }
  compose.onNodeWithTag("library-search").performTextReplacement("Короткая реплика")
  hideKeyboard()
  compose.onNodeWithTag("library-list").performScrollToNode(hasTestTag("recording-$id"))
  compose.onNodeWithTag("recording-$id").performClick()
  compose.waitUntil(10000) { compose.onAllNodesWithTag("segment-${row.id}").fetchSemanticsNodes().isNotEmpty() }
  compose.onNodeWithTag("smart-review-toggle").performClick()
  compose.onNodeWithTag("review-queue").performScrollToNode(hasTestTag("review-${row.id}"))
  capture("14-smart-review-real-warning.png")
  compose.onNodeWithTag("review-listen-${row.id}").performScrollTo().performClick()
  compose.waitUntil(5000) { compose.onAllNodesWithContentDescription("Пауза").fetchSemanticsNodes().isNotEmpty() }
  compose.waitUntil(5000) { compose.onAllNodesWithContentDescription("Пауза").fetchSemanticsNodes().isEmpty() }
  val compact=compose.activity.resources.configuration.screenHeightDp<680 || compose.activity.resources.configuration.fontScale>=1.25f
  compose.waitUntil(5000) { runCatching { compose.onNodeWithTag("playback-clock").assertTextEquals(if(compact) "650 мс" else "650 мс / 650 мс");true }.getOrDefault(false) }
  compose.onNodeWithTag("review-edit-${row.id}").performScrollTo().performClick()
  compose.onNodeWithTag("editor-listen").assertExists()
  capture("15-smart-review-warning-editor.png")
  compose.onNodeWithContentDescription("Закрыть редактор").performClick()
  compose.onNodeWithTag("review-queue").performScrollToNode(hasTestTag("review-done-${row.id}"))
  compose.onNodeWithTag("review-done-${row.id}").performScrollTo().performClick()
  compose.waitUntil(10000) { runBlocking { dao.segmentList(id).single { it.id==row.id }.reviewed } }
  compose.onNodeWithTag("review-empty").assertExists()
  compose.onNodeWithTag("review-queue").performScrollToNode(hasText("Проверенные",substring=false))
  compose.onNodeWithText("Проверенные",substring=false).performClick()
  compose.onNodeWithTag("review-queue").performScrollToNode(hasTestTag("review-${row.id}"))
  capture("16-smart-review-reviewed.png")
  compose.activityRule.scenario.recreate()
  compose.waitUntil(10000) { compose.onAllNodesWithTag("review-empty").fetchSemanticsNodes().isNotEmpty() }
  assertTrue(runBlocking { dao.segmentList(id).single { it.id==row.id }.reviewed })
  File(app.filesDir,"v12-review-queue-ui.json").writeText(org.json.JSONObject()
   .put("realInferenceRecordingId",id).put("segmentId",row.id).put("text",row.text)
   .put("persistedReasons",row.reasons).put("manuallyInjectedWarnings",false)
   .put("subsecondClockClamped",true).put("warningVisible",true).put("editorOpened",true).put("markReviewedPersisted",true)
   .put("activityRecreationVerified",true).put("fontScale",compose.activity.resources.configuration.fontScale).put("reviewStateResetForRepeat",resetReviewed).toString(2))
 }
 @Test fun realTranscriptReviewAndSpeakerEditing() {
  val i=InstrumentationRegistry.getInstrumentation();val app=i.targetContext.applicationContext as ReplikaApp
  val ready=runBlocking { app.db.dao().recording("integration-real-giga")?.status=="READY" }
  Assume.assumeTrue("Run real PipelineTest first",ready)
  compose.onNodeWithTag("library-list").performScrollToNode(hasText("Официальный русский ML smoke test"))
  compose.onNodeWithText("Официальный русский ML smoke test").performClick()
  val before=runBlocking { app.db.dao().segmentList("integration-real-giga").first() }
  compose.waitUntil(10000) { compose.onAllNodesWithTag("segment-${before.id}").fetchSemanticsNodes().isNotEmpty() };capture("04-transcript-workspace.png")
  // Actual player state and active-row semantics validate the tap-to-play behavior.
  compose.onNodeWithText(before.text).performClick()
  compose.waitUntil(5000) { compose.onAllNodesWithContentDescription("Пауза").fetchSemanticsNodes().isNotEmpty() }
  compose.onNodeWithTag("segment-${before.id}").assertIsSelected()
  compose.onNodeWithContentDescription("Пауза").performClick()
  compose.onNodeWithText("Smart Review",substring=true).performClick();capture("06-smart-review.png")
  compose.onNodeWithText("Smart Review",substring=true).performClick()
  compose.onAllNodesWithContentDescription("Изменить реплику").onFirst().performClick();capture("05-segment-editing.png")
  compose.onNodeWithTag("editor-speaker").performClick()
  compose.onNodeWithTag("speaker-add").performClick()
  val corrected=if(before.text.startsWith("чьих ")) "ни"+before.text else before.text+" (проверено)"
  compose.onNodeWithTag("editor-reviewed").performScrollTo().performClick()
  compose.onNodeWithTag("editor-text").performScrollTo().performClick().performTextReplacement(corrected)
  capture("09-segment-editing-keyboard.png")
  hideKeyboard()
  compose.onNodeWithTag("editor-save").assertIsDisplayed()
  compose.mainClock.advanceTimeBy(500);compose.waitForIdle()
  capture("10-segment-editing-save.png")
  compose.onNodeWithText("Сохранить исправления").performClick()
  compose.waitUntil(10000) {
   val saved=runBlocking { app.db.dao().segmentList("integration-real-giga").first() }
   saved.text==corrected && saved.speakerId==1 && saved.edited && saved.reviewed
  }
  // Rename the manually assigned speaker and verify the persisted export after recreation.
  compose.onNodeWithText(corrected).assertIsDisplayed()
  compose.onAllNodesWithText("Участник 2").onLast().performClick()
  capture("05-speaker-editing.png")
  compose.onNode(hasSetTextAction()).performTextReplacement("Проверенная подпись")
  compose.onNodeWithText("Сохранить",useUnmergedTree=true).performClick()
  compose.activityRule.scenario.recreate()
  compose.onNodeWithText(corrected).assertIsDisplayed()
  compose.onAllNodesWithText("Проверенная подпись").onLast().assertIsDisplayed()
  capture("11-transcript-after-correction.png")
  val exported=File(app.cacheDir,"exports/replika-integration-real-giga.json").apply { delete() }
  compose.onNodeWithContentDescription("Экспорт").performClick()
  compose.onNodeWithText("JSON").performClick()
  compose.waitUntil(5000) { exported.exists() && exported.length()>0 }
  val json=org.json.JSONObject(exported.readText()).getJSONArray("segments")
  val row=(0 until json.length()).map { json.getJSONObject(it) }.single { it.getString("id")==before.id }
  assertEquals(corrected,row.getString("text"));assertEquals(1,row.getInt("speakerId"))
  assertEquals("Проверенная подпись",row.getString("speakerName"));assertTrue(row.getBoolean("edited"));assertTrue(row.getBoolean("reviewed"))
  i.uiAutomation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
 }
}
