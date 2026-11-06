package ru.replika

import android.content.ClipboardManager
import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import ru.replika.data.*
import ru.replika.ui.AppViewModel
import java.io.File

/** Controlled UI fixture only; it makes no claim about ASR quality. */
@RunWith(AndroidJUnit4::class)
class TranscriptModesV13Test {
 @get:Rule val compose=createAndroidComposeRule<MainActivity>()
 private val app get()=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
 private val id="v13-ui-${System.nanoTime()}"
 private lateinit var vm: AppViewModel
 @Before fun setup()=runBlocking {
  val source=File(app.filesDir,"integration-example.wav");assertTrue(source.isFile)
  app.db.dao().insert(Recording(id,"UI fixture · два представления",source.path,status="READY",durationMs=11290))
  app.db.dao().insertSegments(listOf(
   SegmentRow("$id-a",id,0,1500,0,"Первая часть мысли.","controlled UI fixture"),
   SegmentRow("$id-b",id,1900,3000,0,"Продолжение мысли.","controlled UI fixture"),
   SegmentRow("$id-c",id,4000,5000,1,"Ответ другого участника.","controlled UI fixture")))
  compose.activityRule.scenario.onActivity { vm=ViewModelProvider(it)[AppViewModel::class.java];vm.selected.value=id }
  compose.waitUntil(15000) { compose.onAllNodesWithTag("segment-$id-a").fetchSemanticsNodes().isNotEmpty() }
 }
 @After fun cleanup() {
  if(::vm.isInitialized) compose.activityRule.scenario.onActivity { vm.selected.value=null;vm.clearNotice() }
  runBlocking { app.db.dao().deleteRecording(id) }
 }
 private fun capture(name: String) {
  compose.waitForIdle();Thread.sleep(300)
  val folder=File(app.filesDir,"human-review-v1.3").apply { mkdirs() }
  val image=InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()!!
  File(folder,name).outputStream().use { image.compress(Bitmap.CompressFormat.PNG,100,it) };image.recycle()
 }
 @Test fun readingCopyEditAndRecreationShareRoomDataWithoutInference() {
  compose.onNodeWithTag("segment-$id-a").assertExists()
  compose.onNodeWithTag("segment-$id-b").assertExists()
  capture("01-dialogue-controlled.png")
  compose.onNodeWithTag("mode-reading").performClick()
  compose.onNodeWithText("Первая часть мысли. Продолжение мысли.").assertIsDisplayed()
  compose.onNodeWithTag("copy-plain-text").performClick()
  var copied=""
  compose.activityRule.scenario.onActivity { activity -> copied=activity.getSystemService(ClipboardManager::class.java).primaryClip!!.getItemAt(0).text.toString() }
  assertEquals("Первая часть мысли. Продолжение мысли.\n\nОтвет другого участника.",copied)
  capture("02-reading-controlled.png")
  compose.onNodeWithTag("mode-dialogue").performClick()
  compose.onNode(hasContentDescription("Изменить реплику") and hasAnyAncestor(hasTestTag("segment-$id-a")),useUnmergedTree=true).performClick()
  compose.onNodeWithTag("editor-text").performTextReplacement("Ручная правка сохранена.")
  androidx.test.espresso.Espresso.closeSoftKeyboard()
  compose.onNodeWithTag("editor-save").performClick()
  compose.waitUntil(10000) { compose.onAllNodesWithTag("transcript-editor").fetchSemanticsNodes().isEmpty() }
  compose.onNodeWithTag("mode-reading").performClick()
  compose.onNodeWithText("Ручная правка сохранена. Продолжение мысли.").assertIsDisplayed()
  val before=runBlocking { app.db.dao().segmentList(id) }
  assertTrue(before.first().edited);assertEquals(0L,before.first().startMs);assertEquals(1500L,before.first().endMs)
  compose.activityRule.scenario.recreate()
  compose.waitUntil(15000) { compose.onAllNodesWithTag("reading-text").fetchSemanticsNodes().isNotEmpty() }
  compose.onNodeWithText("Ручная правка сохранена. Продолжение мысли.").assertIsDisplayed()
  assertEquals(before,runBlocking { app.db.dao().segmentList(id) })
  assertEquals("",runBlocking { app.db.dao().recording(id)!!.diagnostics })
  compose.onNodeWithTag("mode-dialogue").performClick()
  compose.onNodeWithTag("segment-$id-a").assertExists()
 }
}
