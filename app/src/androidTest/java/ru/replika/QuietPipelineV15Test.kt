package ru.replika

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.work.WorkManager
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.data.Recording
import ru.replika.domain.Exporter
import ru.replika.domain.QuietAudioGain
import ru.replika.ml.AudioDecoder
import ru.replika.ml.ProcessingWorker
import java.io.DataOutputStream
import java.io.File
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID
import kotlin.math.abs
import kotlin.math.roundToInt

/** Actual Android MediaCodec -> VAD -> GigaAM -> Room. No injected transcript or microphone claim. */
@RunWith(AndroidJUnit4::class)
class QuietPipelineV15Test {
 private val instrumentation get()=InstrumentationRegistry.getInstrumentation()
 private val app get()=instrumentation.targetContext.applicationContext as ReplikaApp

 private fun sha256(file: File): String {
  val digest=MessageDigest.getInstance("SHA-256")
  file.inputStream().buffered().use { input ->
   val bytes=ByteArray(65536)
   while(true) { val n=input.read(bytes);if(n<0) break;digest.update(bytes,0,n) }
  }
  return digest.digest().joinToString("") { "%02x".format(it) }
 }

 /** Explicit digital attenuation then PCM16 quantization. This does not synthesize whisper. */
 private fun writePcm16(file: File,samples: FloatArray,scale: Float): Float {
  var peak=0f
  DataOutputStream(file.outputStream().buffered()).use { out ->
   fun le16(value: Int) { out.writeByte(value and 255);out.writeByte((value ushr 8) and 255) }
   fun le32(value: Int) { le16(value and 65535);le16(value ushr 16) }
   out.writeBytes("RIFF");le32(36+samples.size*2);out.writeBytes("WAVEfmt ");le32(16)
   le16(1);le16(1);le32(16000);le32(32000);le16(2);le16(16)
   out.writeBytes("data");le32(samples.size*2)
   for(sample in samples) {
    val value=(sample*scale*32768f).roundToInt().coerceIn(-32768,32767)
    le16(value);peak=maxOf(peak,abs(value/32768f))
   }
  }
  return peak
 }

 private suspend fun foreground(id: String) {
  app.startActivity(Intent(app,MainActivity::class.java).putExtra("recordingId",id)
   .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
  withTimeout(30000) {
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

 private suspend fun runCase(silence: Boolean) {
  val dao=app.db.dao();val work=WorkManager.getInstance(app)
  val case=if(silence) "silence" else "quiet-pcm16-minus40db"
  val id="qa-v15-$case-${UUID.randomUUID()}"
  val temporary=File(app.cacheDir,id).apply { mkdirs() }
  val source=File(app.filesDir,"integration-example.wav")
  val sourceCopy=File(temporary,"source-copy.wav")
  val decodedCopy=File(temporary,"source-copy.pcm")
  val derived=File(temporary,"input.wav")
  val evidence=File(File(app.filesDir,"v15-quiet-pipeline").apply { mkdirs() },"$case.json")
  val report=JSONObject().put("case",case).put("recordingId",id)
   .put("platform","Android instrumentation; imported public fixture, NOT a phone microphone test")
   .put("backend",app.models.asrId).put("expectedSpeakers",1).put("sampleRate",16000)
   .put("sourceSha256",SOURCE_SHA256)
   .put("transform",if(silence) "three seconds of exact digital silence, signed mono PCM16 WAV" else "copy verified official WAV; decode copy to mono 16k; multiply by0.01(-40dB); quantize to signed PCM16 WAV")
   .put("realWhisper",false).put("status","RUNNING")
  fun save()=evidence.writeText(report.toString(2))
  try {
   assertTrue("Stage the official integration-example.wav before this test",source.isFile)
   assertEquals("Official source must not be silently replaced",SOURCE_SHA256,sha256(source))
   app.models.requireReady(app.models.asrId,false)
   val peak=if(silence) writePcm16(derived,FloatArray(16000*3),1f) else {
    source.copyTo(sourceCopy)
    assertEquals(SOURCE_SHA256,sha256(sourceCopy))
    val decoded=AudioDecoder.decode(sourceCopy.path,decodedCopy)
    val samples=AudioDecoder.read(decoded.file,0,decoded.samples)
    report.put("sourceAudioMs",decoded.durationMs)
    writePcm16(derived,samples,.01f)
   }
   report.put("derivedSha256",sha256(derived)).put("derivedPeak",peak);save()
   if(silence) assertEquals(0f,peak,0f) else {
    assertTrue("Derived fixture must trigger only the low-level repair",peak>QuietAudioGain.SILENCE_FLOOR && peak<QuietAudioGain.TRIGGER_PEAK)
   }
   dao.insert(Recording(id,"QA V1.5 · $case",derived.path,backend=app.models.asrId,expectedSpeakers=1))
   assertTrue("No transcript may exist before actual Worker inference",dao.segmentList(id).isEmpty())
   foreground(id)
   ProcessingWorker.enqueue(app,id)
   withTimeout(10*60*1000L) {
    while(true) {
     val recording=dao.recording(id)!!
     if(recording.status in setOf("READY","ERROR","CANCELLED")) {
      val finished=withContext(Dispatchers.IO) { work.getWorkInfosForUniqueWork("replika-$id").get().all { it.state.isFinished } }
      if(finished) break
     }
     delay(200)
    }
   }
   val recording=dao.recording(id)!!
   val rows=dao.segmentList(id)
   report.put("workerStatus",recording.status).put("workerError",recording.error?:JSONObject.NULL)
    .put("storedBackend",recording.backend).put("segmentCount",rows.size)
    .put("diagnostics",if(recording.diagnostics.isBlank()) JSONObject.NULL else JSONObject(recording.diagnostics))
    .put("transcript",JSONObject(Exporter.json(recording.title,rows.map { it.domain() }) { "Участник ${it+1}" }))
   save()
   assertEquals("Worker must complete successfully", "READY",recording.status)
   assertNull("No hidden Worker error",recording.error)
   assertEquals(app.models.asrId,recording.backend)
   val diagnostic=JSONObject(recording.diagnostics)
   assertEquals("single",diagnostic.getString("clusteringMode"))
   assertEquals(0L,diagnostic.getJSONObject("stagesMs").getLong("diarizationLoadMs"))
   assertEquals(0L,diagnostic.getJSONObject("stagesMs").getLong("diarizationInferenceMs"))
   if(silence) {
    assertEquals(0,diagnostic.getJSONArray("vadSpans").length())
    assertEquals(1.0,diagnostic.getDouble("recognitionInputGain"),0.0)
    assertEquals(0,rows.size)
    assertEquals(0,diagnostic.getJSONArray("asrSlices").length())
    assertEquals("Silence must not allocate the native ASR engine",0L,diagnostic.getJSONObject("stagesMs").getLong("asrLoadMs"))
    assertEquals(0L,diagnostic.getJSONObject("stagesMs").getLong("asrInferenceMs"))
   } else {
    assertTrue("Quiet input must exercise actual bounded gain",diagnostic.getDouble("recognitionInputGain")>1)
    assertTrue(diagnostic.getDouble("recognitionInputGain")<=QuietAudioGain.MAX_GAIN)
    assertTrue("Real VAD must find speech in the transformed recording",diagnostic.getJSONArray("vadSpans").length()>0)
    assertTrue(rows.isNotEmpty())
    assertTrue(rows.all { it.text.isNotBlank() && it.source.contains("GigaAM") && it.startMs>=0 && it.endMs>it.startMs && it.endMs<=recording.durationMs && !it.edited })
    assertTrue("Known real prefix must survive the actual quiet pipeline",rows.first().text.trimStart().lowercase(Locale.ROOT).startsWith("ничьих"))
   }
   // Re-query Room rather than trusting an in-memory result from the recognizer.
   app.db.openHelper.readableDatabase.query("SELECT status,backend FROM recordings WHERE id = ?",arrayOf(id)).use { cursor ->
    assertTrue(cursor.moveToFirst());assertEquals("READY",cursor.getString(0));assertEquals(app.models.asrId,cursor.getString(1))
   }
   app.db.openHelper.readableDatabase.query("SELECT COUNT(*) FROM segments WHERE recordingId = ?",arrayOf(id)).use { cursor ->
    assertTrue(cursor.moveToFirst());assertEquals(rows.size,cursor.getInt(0))
   }
   assertEquals(SOURCE_SHA256,sha256(source))
   if(!silence) assertEquals(SOURCE_SHA256,sha256(sourceCopy))
   report.put("sourceUnchanged",true).put("roomReadBackVerified",true).put("status","PASS");save()
  } catch(error: Throwable) {
   report.put("status","FAILED").put("testError",error.message?:error.javaClass.simpleName);save();throw error
  } finally {
   withContext(NonCancellable) {
    withContext(Dispatchers.IO) { work.cancelUniqueWork("replika-$id").result.get() }
    // Cancellation is not a native abort: wait for any returning native call before removing QA files.
    app.models.gate.withLock { }
    dao.deleteSpeakers(id);dao.deleteRecording(id)
    assertNull(dao.recording(id));assertTrue(dao.segmentList(id).isEmpty())
    temporary.deleteRecursively()
    report.put("qaRowsRemoved",true).put("qaTemporaryFilesRemoved",!temporary.exists());save()
    assertFalse("Dedicated QA audio copies must be removed after the Worker returns",temporary.exists())
    instrumentation.runOnMainSync {
     ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).filterIsInstance<MainActivity>().forEach { it.finish() }
    }
   }
  }
 }

 @Test fun quietPcm16Minus40dBThroughRealWorker(): Unit=runBlocking { runCase(silence=false) }
 @Test fun digitalSilenceCreatesNoFabricatedSpeech(): Unit=runBlocking { runCase(silence=true) }

 companion object {
  private const val SOURCE_SHA256="d8aaaa18a5098d7c6de0595ae7ac1e64cacd0d4022af3595213bdaf23be77e69"
 }
}
