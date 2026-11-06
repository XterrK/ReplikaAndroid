package ru.replika

import android.content.Intent
import android.media.MediaExtractor
import android.media.MediaFormat
import android.net.Uri
import android.os.Build
import android.os.SystemClock
import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.work.WorkManager
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.data.ProductStorage
import ru.replika.data.Recording
import ru.replika.data.ReplikaDatabase
import ru.replika.domain.Exporter
import ru.replika.ml.MediaImporter
import ru.replika.ml.ProcessingWorker
import java.io.File
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID

/** Actual video→platform audio extraction→production offline Worker→Room reopen→export.
 * Stage tools/create_video_pipeline_fixture.py's 99 KB video as files/integration-video-v15.mp4.
 * No recognizer mocks, injected transcript or alternative recognition path.
 */
@RunWith(AndroidJUnit4::class)
class VideoPipelineV15Test {
 @Test fun videoAudioIsRecognizedOfflinePersistedAndExported(): Unit=runBlocking {
  val instrumentation=InstrumentationRegistry.getInstrumentation()
  val app=instrumentation.targetContext.applicationContext as ReplikaApp
  val source=File(app.filesDir,"integration-video-v15.mp4")
  assertTrue("Stage /mnt/f/ReplikaToolchain/integration-video-v15.mp4 in app files before running",source.isFile)
  assertEquals("Video must contain the pinned public Russian sample",VIDEO_SHA256,hash(source))
  withTimeout(10*60*1000L) { app.bundledModels.awaitReady() }
  app.models.requireReady(includeDiarization=false)
  val started=SystemClock.elapsedRealtime()
  val progress=mutableListOf<String>()
  val imported=MediaImporter(app).importMedia(Uri.fromFile(source),File(app.filesDir,"audio"),"video-v15-${UUID.randomUUID()}") { progress+=it }
  assertTrue(imported.fromVideo);assertEquals(MediaImporter.Mode.AAC_REMUX,imported.mode)
  val extractor=MediaExtractor()
  try {
   extractor.setDataSource(imported.file.path)
   assertEquals(1,extractor.trackCount)
   assertTrue(extractor.getTrackFormat(0).getString(MediaFormat.KEY_MIME)!!.startsWith("audio/"))
  } finally { extractor.release() }
  val work=WorkManager.getInstance(app)
  withContext(Dispatchers.IO) { work.cancelUniqueWork("replika-$ID").result.get() }
  app.models.gate.withLock {
   val previous=app.db.dao().recording(ID)
   if(previous!=null) {
    // This test owns only its dedicated ID and any app-owned audio referenced by that row.
    if(previous.status in setOf("QUEUED","PROCESSING","CANCELLING")) app.db.dao().status(ID,"CANCELLED","QA retry")
    ProductStorage(app.db,File(app.filesDir,"audio")).deleteRecording(ID)
   }
   app.db.dao().insert(Recording(ID,"Видео · офлайн-расшифровка",imported.file.path,durationMs=imported.durationMs,backend=app.models.asrId,expectedSpeakers=1))
  }
  app.startActivity(Intent(app,MainActivity::class.java).putExtra("recordingId",ID)
   .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
  withTimeout(30000) {
   while(true) {
    var resumed=false
    instrumentation.runOnMainSync { resumed=ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).any { it is MainActivity } }
    if(resumed) break
    delay(100)
   }
  }
  try {
   ProcessingWorker.enqueue(app,ID)
   withTimeout(10*60*1000L) {
    while(true) {
     val rec=app.db.dao().recording(ID)!!
     if(rec.status=="ERROR") fail("Actual video Worker failed: ${rec.error}")
     if(rec.status=="CANCELLED") fail("Actual video Worker was cancelled")
     if(rec.status=="READY") break
     delay(200)
    }
   }
   app.models.gate.withLock { } // Wait for final diagnostics/native cleanup after READY commit.
   val rows=app.db.dao().segmentList(ID)
   assertTrue("Actual GigaAM must transcribe the extracted voice",rows.isNotEmpty())
   assertTrue(rows.all { it.text.isNotBlank() && it.source.contains("GigaAM") && it.speakerId==0 })
   val transcript=rows.joinToString(" ") { it.text }
   assertTrue("Known leading word must survive video extraction and VAD",transcript.lowercase(Locale.ROOT).trimStart().startsWith("ничьих"))
   val recording=app.db.dao().recording(ID)!!
   assertEquals(app.models.asrId,recording.backend)
   assertTrue(recording.durationMs in 11000..11600)
   assertTrue(rows.all { it.startMs>=0 && it.endMs>it.startMs && it.endMs<=recording.durationMs })
   val diagnostic=JSONObject(recording.diagnostics)
   assertEquals("single",diagnostic.getString("clusteringMode"))
   assertEquals(0L,diagnostic.getJSONObject("stagesMs").getLong("diarizationMs"))
   assertTrue(diagnostic.getJSONArray("vadSpans").length()>0)
   assertTrue(diagnostic.getJSONArray("asrSlices").length()>0)

   val reopened=Room.databaseBuilder(app,ReplikaDatabase::class.java,"replika.db").build()
   try {
    assertEquals(recording,reopened.dao().recording(ID))
    assertEquals(rows,reopened.dao().segmentList(ID))
    assertTrue(File(reopened.dao().recording(ID)!!.audioPath).isFile)
   } finally { reopened.close() }
   val folder=File(app.filesDir,"video-v15-evidence").apply { mkdirs() }
   val json=Exporter.json(recording.title,rows.map { it.domain() }) { "Участник ${it+1}" }
   val txt=Exporter.txt(recording.title,rows.map { it.domain() }) { "Участник ${it+1}" }
   val srt=Exporter.srt(rows.map { it.domain() }) { "Участник ${it+1}" }
   File(folder,"video-transcript.json").writeText(json);File(folder,"video-transcript.txt").writeText(txt);File(folder,"video-transcript.srt").writeText(srt)
   val exported=JSONObject(File(folder,"video-transcript.json").readText()).getJSONArray("segments")
   assertEquals(rows.size,exported.length())
   assertEquals(rows.first().text,exported.getJSONObject(0).getString("text"))
   assertTrue(File(folder,"video-transcript.txt").readText().contains(rows.first().text))
   assertTrue(File(folder,"video-transcript.srt").readText().contains(" --> "))
   assertEquals(VIDEO_SHA256,hash(source))
   val report=JSONObject().put("device","${Build.MANUFACTURER} ${Build.MODEL}").put("api",Build.VERSION.SDK_INT)
    .put("abis",JSONArray(Build.SUPPORTED_ABIS.toList())).put("originalVideoSha256",hash(source))
    .put("audioArtifactSha256",hash(imported.file)).put("audioArtifactBytes",imported.file.length()).put("importMode",imported.mode.name)
    .put("recordingId",ID).put("backend",recording.backend).put("segments",rows.size).put("durationMs",recording.durationMs)
    .put("databaseReopen",true).put("exportsReadBack",JSONArray(listOf("json","txt","srt")))
    .put("flowElapsedMs",SystemClock.elapsedRealtime()-started).put("actualPipelineDiagnostics",diagnostic)
    .put("scope","Real platform AAC extraction and production offline Worker on recorded device; video/speech fixture is public, not a microphone recording")
   File(folder,"acceptance.json").writeText(report.toString(2))
  } finally {
   instrumentation.runOnMainSync { ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).filterIsInstance<MainActivity>().forEach { it.finish() } }
  }
 }
 private fun hash(file: File): String {
  val digest=MessageDigest.getInstance("SHA-256")
  file.inputStream().buffered().use { source -> val block=ByteArray(128*1024);while(true) { val count=source.read(block);if(count<0) break;digest.update(block,0,count) } }
  return digest.digest().joinToString("") { "%02x".format(it) }
 }
 companion object {
  const val ID="integration-video-v15"
  const val VIDEO_SHA256="e05cefe96c748b0bd519cf4193702ddb1283d5b1c994e22681ea471757842e66"
 }
}
