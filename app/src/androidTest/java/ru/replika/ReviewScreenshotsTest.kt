package ru.replika
import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.*
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
 @Test fun libraryModelsAndRecording() {
  capture("01-library.png")
  compose.onNodeWithText("Модели").performClick();capture("07-models-diagnostics.png")
  compose.onNodeWithText("Записи").performClick();compose.onNodeWithText("Записать").performClick()
  capture("02-recording.png")
  compose.onNodeWithText("Отменить запись").performClick()
 }
 @Test fun realTranscriptReviewAndSpeakerEditing() {
  val i=InstrumentationRegistry.getInstrumentation();val app=i.targetContext.applicationContext as ReplikaApp
  val ready=kotlinx.coroutines.runBlocking { app.db.dao().recording("integration-real-giga")?.status=="READY" }
  Assume.assumeTrue("Run real PipelineTest first",ready)
  compose.onNode(hasScrollAction()).performScrollToNode(hasText("Официальный русский ML smoke test"))
  compose.onNodeWithText("Официальный русский ML smoke test").performClick();capture("04-transcript-workspace.png")
  val before=kotlinx.coroutines.runBlocking { app.db.dao().segmentList("integration-real-giga").first() }
  compose.onAllNodesWithContentDescription("Изменить реплику").onFirst().performClick();capture("05-speaker-editing.png")
  compose.onNodeWithText("Участник 2").performClick()
  val corrected=if(before.text.startsWith("чьих ")) "ни"+before.text else before.text+" (проверено)"
  compose.onNode(isToggleable() and hasAnySibling(hasText("Фрагмент проверен"))).performClick()
  compose.onNode(hasSetTextAction()).performClick().performTextReplacement(corrected)
  compose.onNodeWithText("Сохранить исправления").performScrollTo().performClick()
  compose.waitUntil(5000) {
   val saved=kotlinx.coroutines.runBlocking { app.db.dao().segmentList("integration-real-giga").first() }
   saved.text==corrected && saved.speakerId==1 && saved.edited && saved.reviewed
  }
  capture("04-transcript-workspace.png")
  compose.onNodeWithText("Smart Review",substring=true).performClick();capture("06-smart-review.png")
 }
}
