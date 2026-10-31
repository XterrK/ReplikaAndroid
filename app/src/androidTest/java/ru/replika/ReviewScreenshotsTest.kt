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
  val i=InstrumentationRegistry.getInstrumentation();val folder=File(i.targetContext.filesDir,"human-review").apply { mkdirs() }
  val image=i.uiAutomation.takeScreenshot()?:error("Android did not return a screenshot")
  File(folder,name).outputStream().use { image.compress(Bitmap.CompressFormat.PNG,100,it) };image.recycle()
 }
 private fun hideKeyboard() {
  // The editor is a dialog window; the Activity token belongs to a different input target.
  androidx.test.espresso.Espresso.closeSoftKeyboard()
  compose.mainClock.advanceTimeBy(500)
  compose.waitForIdle()
 }
 @Test fun libraryModelsAndRecording() {
  capture("01-library.png")
  compose.onNodeWithText("Модели").performClick();capture("07-models-diagnostics.png")
  compose.onNode(hasScrollAction()).performScrollToNode(hasText("Импорт offline pack"));capture("13-offline-pack.png")
  compose.onNode(hasScrollAction()).performScrollToNode(hasText("Диагностика"));capture("12-models-diagnostics-details.png")
  compose.onNodeWithText("Записи").performClick()
  // Physical microphone validation requires separate explicit consent.
  Assume.assumeTrue("Recording screenshot is restricted to an emulator",android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk",ignoreCase=true))
  compose.onNodeWithText("Записать").performClick();capture("02-recording.png")
  compose.onNodeWithText("Пауза").performClick()
  compose.onNodeWithText("Продолжить").assertIsDisplayed().performClick()
  compose.onNodeWithText("Пауза").assertIsDisplayed()
  compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.CREATED)
  compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.RESUMED)
  compose.onNodeWithText("Продолжить").assertIsDisplayed()
  compose.onNodeWithText("Отменить запись").performClick()
 }
 @Test fun realTranscriptReviewAndSpeakerEditing() {
  val i=InstrumentationRegistry.getInstrumentation();val app=i.targetContext.applicationContext as ReplikaApp
  val ready=runBlocking { app.db.dao().recording("integration-real-giga")?.status=="READY" }
  Assume.assumeTrue("Run real PipelineTest first",ready)
  compose.onNode(hasScrollAction()).performScrollToNode(hasText("Официальный русский ML smoke test"))
  compose.onNodeWithText("Официальный русский ML smoke test").performClick();capture("04-transcript-workspace.png")
  val before=runBlocking { app.db.dao().segmentList("integration-real-giga").first() }
  // Actual player state and active-row semantics validate the tap-to-play behavior.
  compose.onNodeWithText(before.text).performClick()
  compose.waitUntil(5000) { compose.onAllNodesWithContentDescription("Пауза").fetchSemanticsNodes().isNotEmpty() }
  compose.onNodeWithTag("segment-${before.id}").assertIsSelected()
  compose.onNodeWithContentDescription("Пауза").performClick()
  compose.onNodeWithText("Smart Review",substring=true).performClick();capture("06-smart-review.png")
  compose.onNodeWithText("Smart Review",substring=true).performClick()
  compose.onAllNodesWithContentDescription("Изменить реплику").onFirst().performClick();capture("05-segment-editing.png")
  compose.onNodeWithText("Участник 2").performScrollTo().performClick()
  val corrected=if(before.text.startsWith("чьих ")) "ни"+before.text else before.text+" (проверено)"
  compose.onNode(isToggleable() and hasAnySibling(hasText("Фрагмент проверен"))).performScrollTo().performClick()
  compose.onNode(hasSetTextAction()).performClick().performTextReplacement(corrected)
  capture("09-segment-editing-keyboard.png")
  hideKeyboard()
  compose.onNodeWithText("Сохранить исправления").performScrollTo().assertIsDisplayed()
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
