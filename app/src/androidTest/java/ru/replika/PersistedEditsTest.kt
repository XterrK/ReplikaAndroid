package ru.replika

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.first
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Run after screenshots, using a separate am instrument invocation after force-stop. */
@RunWith(AndroidJUnit4::class)
class PersistedEditsTest {
 @Test fun actualUiCorrectionsSurviveProcessRelaunch()=runBlocking {
  val app=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
  val exported=File(app.cacheDir,"exports/replika-integration-real-giga.json")
  Assume.assumeTrue("Run real pipeline and UI corrections first",exported.isFile)
  val rows=app.db.dao().segmentList("integration-real-giga")
  val edited=rows.first { it.edited && it.reviewed && it.speakerId==1 }
  val speaker=app.db.dao().speakers("integration-real-giga").first().single { it.speakerId==1 }
  assertEquals("Проверенная подпись",speaker.name)
  val json=JSONObject(exported.readText()).getJSONArray("segments")
  val item=(0 until json.length()).map { json.getJSONObject(it) }.single { it.getString("id")==edited.id }
  assertEquals(edited.text,item.getString("text"));assertEquals(speaker.name,item.getString("speakerName"))
  assertTrue(item.getBoolean("edited"));assertTrue(item.getBoolean("reviewed"));assertEquals(1,item.getInt("speakerId"))
  File(app.filesDir,"edit-persistence.json").writeText(JSONObject().put("processId",android.os.Process.myPid()).put("editedSegmentId",edited.id).put("text",edited.text).put("speakerId",edited.speakerId).put("speakerName",speaker.name).put("roomMatchesUiExport",true).put("requiresSeparateInvocationAfterForceStop",true).toString(2))
 }
}
