package ru.replika

import android.graphics.Bitmap
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import ru.replika.data.Recording
import ru.replika.ml.ProcessingWorker
import java.io.File

@RunWith(AndroidJUnit4::class)
class PipelineTest {
 @Test fun completeRealGigaPipeline()=runBlocking {
  val instrumentation=InstrumentationRegistry.getInstrumentation();val app=instrumentation.targetContext.applicationContext as ReplikaApp
  val audio=File(app.filesDir,"integration-example.wav")
  Assume.assumeTrue("Real WAV and models must be staged first",audio.exists())
  app.models.requireReady()
  val id="integration-real-giga"
  app.db.openHelper.writableDatabase.execSQL("DELETE FROM speakers WHERE recordingId = ?",arrayOf(id))
  val prior=app.db.dao().recording(id)
  if(prior!=null) app.db.dao().clearSegments(id)
  app.db.dao().insert(Recording(id,"Официальный русский ML smoke test",audio.path,status="IMPORTED",phase="Ожидание обработки"))
  // Avoid startActivitySync's idle wait on an animated indeterminate processing screen.
  app.startActivity(android.content.Intent(app,MainActivity::class.java).putExtra("recordingId",id).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK))
  withTimeout(30000) {
   while(true) {
    var resumed=false
    instrumentation.runOnMainSync { resumed=ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).any { it is MainActivity } }
    if(resumed) break
    delay(100)
   }
  }
  try {
   ProcessingWorker.enqueue(app,id)
   var ready=false;var captured=false
   fun capture(name: String) { runCatching { val folder=File(app.filesDir,"human-review").apply { mkdirs() };instrumentation.uiAutomation.takeScreenshot()?.let { bitmap -> File(folder,name).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) };bitmap.recycle() } } }
   withTimeout(20*60*1000L) {
    while(true) { delay(1000);val record=app.db.dao().recording(id)!!
     if(record.status=="PROCESSING" && !captured) { capture("03-processing.png");captured=true }
     if(record.status=="ERROR") fail("ML pipeline failed: ${record.error}")
     if(record.status=="READY") { ready=true;File(app.filesDir,"android-pipeline-diagnostics.json").writeText(record.diagnostics);break }
    }
   }
   delay(1500);capture("04-transcript-workspace.png")
   assertTrue(ready);val rows=app.db.dao().segmentList(id);assertTrue(rows.isNotEmpty());assertTrue(rows.all { it.endMs>it.startMs && it.source.contains("GigaAM") })
   assertTrue("Pre-roll regression: actual GigaAM prefix was clipped",rows.first().text.startsWith("ничьих"))
   assertEquals(100,org.json.JSONObject(app.db.dao().recording(id)!!.diagnostics).getInt("preRollMs"))
   File(app.filesDir,"android-transcript.json").writeText(ru.replika.domain.Exporter.json("Real integration",rows.map { it.domain() }) { "speaker-$it" })
  } finally { instrumentation.runOnMainSync {
   ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).filterIsInstance<MainActivity>().forEach { it.finish() }
  } }
 }
 @Test fun completeRealWhisperPipeline()=runBlocking {
  val instrumentation=InstrumentationRegistry.getInstrumentation();val app=instrumentation.targetContext.applicationContext as ReplikaApp
  val audio=File(app.filesDir,"integration-example.wav")
  Assume.assumeTrue(audio.exists() && app.models.file("whisper-tiny/ggml-tiny.bin").exists())
  val id="integration-real-whisper"
  app.db.dao().insert(Recording(id,"Whisper полный русский mono pipeline",audio.path,status="IMPORTED",backend="whisper-tiny"))
  app.startActivity(android.content.Intent(app,MainActivity::class.java).putExtra("recordingId",id).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK))
  delay(2000)
  ProcessingWorker.enqueue(app,id)
  withTimeout(20*60*1000L) {
   while(true) {
    delay(500);val rec=app.db.dao().recording(id)!!
    if(rec.status=="ERROR") fail(rec.error)
    if(rec.status=="READY") {
     val rows=app.db.dao().segmentList(id);assertTrue(rows.isNotEmpty());assertTrue(rows.all { it.source.contains("Whisper") })
     File(app.filesDir,"android-whisper-pipeline-diagnostics.json").writeText(rec.diagnostics)
     File(app.filesDir,"android-whisper-transcript.json").writeText(ru.replika.domain.Exporter.json("Actual Whisper Worker result",rows.map { it.domain() }) { "speaker-$it" })
     break
    }
   }
  }
  instrumentation.runOnMainSync { ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).filterIsInstance<MainActivity>().forEach { it.finish() } }
 }
 @Test fun realWhisperBackend()=runBlocking {
  val app=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
  val audio=File(app.filesDir,"integration-example.wav")
  Assume.assumeTrue(audio.exists() && app.models.file("whisper-tiny/ggml-tiny.bin").exists())
  app.models.requireReady("whisper-tiny")
  val pcm=ru.replika.ml.AudioDecoder.decode(audio.path,File(app.cacheDir,"whisper-test.pcm"))
  try {
   ru.replika.ml.WhisperEngine(app.models).use { engine ->
    val start=android.os.SystemClock.elapsedRealtime();val text=engine.recognize(ru.replika.ml.AudioDecoder.read(pcm.file,0,pcm.samples))
    assertTrue(text.isNotBlank());File(app.filesDir,"android-whisper.txt").writeText("${engine.source}\n${android.os.SystemClock.elapsedRealtime()-start} ms\n$text")
   }
  } finally { pcm.file.delete() }
 }
}
