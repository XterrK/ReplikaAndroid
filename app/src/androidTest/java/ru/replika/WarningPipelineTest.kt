package ru.replika

import android.content.Intent
import android.os.SystemClock
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
import ru.replika.data.Recording
import ru.replika.domain.Exporter
import ru.replika.ml.AudioDecoder
import ru.replika.ml.ProcessingWorker
import java.io.DataOutputStream
import java.io.File
import java.security.MessageDigest
import java.util.UUID
import kotlin.math.min
import kotlin.math.roundToInt

/** Real speech excerpts through the unchanged Worker, never injected transcript/warning rows. */
@RunWith(AndroidJUnit4::class)
class WarningPipelineTest {
 private fun sha256(file: File): String {
  val digest=MessageDigest.getInstance("SHA-256")
  file.inputStream().buffered().use { input ->
   val block=ByteArray(65536)
   while(true) { val n=input.read(block);if(n<0) break;digest.update(block,0,n) }
  }
  return digest.digest().joinToString("") { "%02x".format(it) }
 }

 private fun writeExcerpt(file: File,samples: FloatArray,start: Int,count: Int) {
  DataOutputStream(file.outputStream().buffered()).use { out ->
   fun le16(value: Int) { out.writeByte(value and 255);out.writeByte((value ushr 8) and 255) }
   fun le32(value: Int) { le16(value and 65535);le16(value ushr 16) }
   out.writeBytes("RIFF");le32(36+count*2);out.writeBytes("WAVEfmt ");le32(16)
   le16(1);le16(1);le32(16000);le32(32000);le16(2);le16(16)
   out.writeBytes("data");le32(count*2)
   repeat(count) { i -> le16((samples[start+i]*32768f).roundToInt().coerceIn(-32768,32767)) }
  }
 }

 @Test fun completeRealShortSpeechWarningPipeline()=runBlocking {
  val instrumentation=InstrumentationRegistry.getInstrumentation()
  val app=instrumentation.targetContext.applicationContext as ReplikaApp
  val dao=app.db.dao();val work=WorkManager.getInstance(app)
  val source=File(app.filesDir,"integration-example.wav")
  assertTrue("Stage the official public Russian WAV before running this test",source.isFile)
  assertEquals("This fixture must not silently use personal or replacement audio",SOURCE_SHA256,sha256(source))
  app.models.requireReady()
  assertEquals(100L,ProcessingWorker.PRE_ROLL_MS)
  assertEquals(0L,ProcessingWorker.POST_ROLL_MS)

  val runId=UUID.randomUUID().toString()
  val runFolder=File(app.filesDir,"v12-warning-evidence/$runId").apply { mkdirs() }
  val outcomes=JSONArray()
  val report=JSONObject().put("schemaVersion",1).put("recordingId",RECORDING_ID)
   .put("source","official GigaAM conversion Russian mono WAV; a controlled excerpt, not a new dialogue")
   .put("sourceSha256",SOURCE_SHA256).put("sampleRate",16000).put("backend",app.models.asrId)
   .put("transform","decode source to mono 16 kHz; crop real samples; write signed PCM16 little-endian WAV")
   .put("timestampScope","timestamps are global within the new excerpt file; add sourceOffsetMs only when relating back to the source")
   .put("warningPolicy","unchanged production conditions; no injected text, speaker turns or warning reasons")
   .put("russianMultispeakerE2E",false).put("status","RUNNING").put("candidates",outcomes)
  fun save(name: String,text: String) {
   File(runFolder,name).writeText(text)
   File(app.filesDir,name).writeText(text)
  }
  fun saveReport()=save("v12-warning-pipeline.json",report.toString(2))
  suspend fun awaitFinished()=withTimeout(30000L) {
   while(withContext(Dispatchers.IO) { work.getWorkInfosForUniqueWork("replika-$RECORDING_ID").get().any { !it.state.isFinished } }) delay(100)
  }
  val decoded=AudioDecoder.decode(source.path,File(app.cacheDir,"v12-warning-source-$runId.pcm"))
  var successful=false
  try {
   report.put("sourceAudioMs",decoded.durationMs);saveReport()
   val samples=AudioDecoder.read(decoded.file,0,decoded.samples)
   // These are fixed source sample ranges. No VAD/clustering threshold is tuned to the test.
   val offsets=listOf(0L,1000L,1500L,2500L,4000L,5500L,9800L,10000L)
   withTimeout(10*60*1000L) {
    for((index,offsetMs) in offsets.withIndex()) {
     awaitFinished()
     val start=(offsetMs*16).toInt();val count=min(650*16,samples.size-start)
     assertTrue("Source excerpt must contain at least 250ms of original samples",count>=250*16)
     val audio=File(File(app.filesDir,"audio").apply { mkdirs() },"v12-warning-$runId-$index.wav")
     writeExcerpt(audio,samples,start,count)
     val candidate=JSONObject().put("sourceOffsetMs",offsetMs).put("sourceStartSample",start)
      .put("sampleCount",count).put("requestedDurationMs",650).put("derivedAudioMs",count/16)
      .put("derivedFile",audio.name).put("derivedSha256",sha256(audio)).put("status","IMPORTED")
     outcomes.put(candidate);saveReport()
     // Only this dedicated QA record is replaced. The source and all other recordings remain intact.
     dao.clearSegments(RECORDING_ID)
     dao.insert(Recording(RECORDING_ID,TITLE,audio.path,backend=app.models.asrId,expectedSpeakers=-1))
     if(index==0) {
      app.startActivity(Intent(app,MainActivity::class.java).putExtra("recordingId",RECORDING_ID)
       .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
      withTimeout(30000L) {
       while(true) {
        var resumed=false
        instrumentation.runOnMainSync {
         resumed=ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).any { it is MainActivity }
        }
        if(resumed) break
        delay(100)
       }
      }
     }
     val started=SystemClock.elapsedRealtime()
     ProcessingWorker.enqueue(app,RECORDING_ID)
     withTimeout(180000L) {
      while(dao.recording(RECORDING_ID)?.status !in setOf("READY","ERROR","CANCELLED")) delay(100)
     }
     awaitFinished()
     val record=dao.recording(RECORDING_ID)!!
     val rows=dao.segmentList(RECORDING_ID)
     candidate.put("status",record.status).put("observedWorkerWallMs",SystemClock.elapsedRealtime()-started)
      .put("workerError",record.error?:JSONObject.NULL)
      .put("diagnostics",if(record.diagnostics.isBlank()) JSONObject.NULL else JSONObject(record.diagnostics))
      .put("transcript",JSONObject(Exporter.json(TITLE,rows.map { it.domain() }) { if(it<0) "Неизвестный" else "Участник ${it+1}" }))
     saveReport()
     val warning=rows.firstOrNull { it.text.isNotBlank() && it.domain().reasons.isNotEmpty() }
     if(record.status=="READY" && warning!=null) {
      assertTrue(rows.all { it.source.contains("GigaAM") && it.endMs>it.startMs && it.startMs>=0 && it.endMs<=record.durationMs })
      assertTrue(warning.domain().reasons.any { it.contains("Короткая реплика") })
      assertTrue(rows.none { it.edited || it.reviewed })
      report.put("status","WORKING").put("selectedCandidate",index).put("sourceOffsetMs",offsetMs)
       .put("warningSegmentId",warning.id).put("warningReasons",JSONArray(warning.domain().reasons))
      save("v12-warning-diagnostics.json",record.diagnostics)
      save("v12-warning-transcript.json",Exporter.json(TITLE,rows.map { it.domain() }) { if(it<0) "Неизвестный" else "Участник ${it+1}" })
      save("v12-warning-transcript.txt",Exporter.txt(TITLE,rows.map { it.domain() }) { if(it<0) "Неизвестный" else "Участник ${it+1}" })
      successful=true;saveReport();break
     }
    }
   }
  } catch(error: Throwable) {
   report.put("status","BLOCKED").put("testError",error.message?:error.javaClass.simpleName)
   dao.recording(RECORDING_ID)?.let { report.put("lastWorkerStatus",it.status).put("lastWorkerPhase",it.phase).put("lastWorkerError",it.error) }
   saveReport()
   throw error
  } finally {
   if(!successful) {
    report.put("status","BLOCKED").put("limitation","No actual nonblank short-speech warning obtained from the attempted real excerpts")
    saveReport()
    withContext(NonCancellable) {
     withContext(Dispatchers.IO) { work.cancelUniqueWork("replika-$RECORDING_ID").result.get() }
     // Wait for a returning native call; cancelling the WorkRequest alone is not a native abort.
     app.models.gate.withLock { }
    }
   }
   decoded.file.delete()
   instrumentation.runOnMainSync {
    ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).filterIsInstance<MainActivity>().forEach { it.finish() }
   }
  }
  assertTrue("No genuine warning was produced; inspect files/v12-warning-pipeline.json instead of creating a demonstration segment",successful)
 }

 companion object {
  const val RECORDING_ID="integration-v12-warning"
  const val TITLE="Короткая реплика · Smart Review"
  private const val SOURCE_SHA256="d8aaaa18a5098d7c6de0595ae7ac1e64cacd0d4022af3595213bdaf23be77e69"
 }
}
