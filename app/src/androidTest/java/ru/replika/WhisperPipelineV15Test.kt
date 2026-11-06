package ru.replika

import android.content.Intent
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
import ru.replika.ml.ProcessingWorker
import java.io.File
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID

/** Actual author-labelled studio whisper, never synthetic attenuation or a phone mic claim.
 * Stage tools/stage_whisper_v15.py first; the independent references never enter recognizers.
 */
@RunWith(AndroidJUnit4::class)
class WhisperPipelineV15Test {
 private fun sha(file: File): String {
  val digest=MessageDigest.getInstance("SHA-256")
  file.inputStream().buffered().use { input -> val b=ByteArray(128*1024);while(true) { val n=input.read(b);if(n<0) break;digest.update(b,0,n) } }
  return digest.digest().joinToString("") { "%02x".format(it) }
 }
 private fun words(text: String)=Regex("[\\p{L}\\p{N}_]+").findAll(text.lowercase(Locale.ROOT).replace('ё','е')).map { it.value }.toList()
 private fun <T> distance(a: List<T>,b: List<T>): Int {
  var previous=IntArray(b.size+1) { it }
  for(i in a.indices) {
   val next=IntArray(b.size+1);next[0]=i+1
   for(j in b.indices) next[j+1]=minOf(previous[j+1]+1,next[j]+1,previous[j]+if(a[i]==b[j]) 0 else 1)
   previous=next
  }
  return previous.last()
 }
 @Test fun sevenAuthorWhisperClipsThroughRealWorkerAndZeroSpanRescue(): Unit=runBlocking {
  val instrumentation=InstrumentationRegistry.getInstrumentation()
  val app=instrumentation.targetContext.applicationContext as ReplikaApp
  val fixtures=File(app.filesDir,"ru-whisper-v15")
  val manifest=File(fixtures,"fixtures.json")
  assertTrue("Stage public licensed fixtures with tools/stage_whisper_v15.py",manifest.isFile)
  assertEquals("e136a6af001dd43a9002f20f39dd56d200afa9a6d408e28a625d90c9a0c22143",sha(File(fixtures,"LICENSE.md")))
  val rows=JSONObject(manifest.readText()).getJSONArray("fixtures");assertEquals(7,rows.length())
  withTimeout(10*60*1000L) { app.bundledModels.awaitReady() }
  val dao=app.db.dao();val work=WorkManager.getInstance(app)
  val output=File(app.filesDir,"whisper-v15-evidence").apply { mkdirs() }
  val cases=JSONArray();val report=JSONObject().put("status","RUNNING").put("cases",cases)
   .put("scope","Actual Android Worker on all seven official author-labelled studio whisper test rows; independent author scripts; not vivo microphone/phonation/heat acceptance")
   .put("expectedWords",84).put("expectedSpeakers",1).put("referencesUsedOnlyForScoring",true)
  fun save()=File(output,"acceptance.json").writeText(report.toString(2))
  var errors=0;var totalWords=0;var charErrors=0;var totalChars=0;var rescued=0
  save()
  for(index in 0 until rows.length()) {
   val fixture=rows.getJSONObject(index);val name=fixture.getString("path")
   assertEquals(File(name).name,name)
   val audio=File(fixtures,name);val before=sha(audio)
   assertEquals("Pinned public audio must remain the author's exact bytes",fixture.getString("sha256"),before)
   val id="qa-v15-real-whisper-${UUID.randomUUID()}"
   try {
    dao.insert(Recording(id,"Студийный шёпот · ${fixture.getString("id")}",audio.path,backend=app.models.asrId,expectedSpeakers=1))
    assertTrue(dao.segmentList(id).isEmpty())
    app.startActivity(Intent(app,MainActivity::class.java).putExtra("recordingId",id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
    withTimeout(30000) {
     while(true) {
      var foreground=false
      instrumentation.runOnMainSync { foreground=ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).any { it is MainActivity } }
      if(foreground) break
      delay(100)
     }
    }
    ProcessingWorker.enqueue(app,id)
    withTimeout(10*60*1000L) {
     while(true) {
      val record=dao.recording(id)!!
      if(record.status=="ERROR") fail("Actual whisper Worker error: ${record.error}")
      if(record.status=="CANCELLED") fail("Whisper Worker unexpectedly cancelled")
      if(record.status=="READY") break
      delay(200)
     }
    }
    app.models.gate.withLock { } // Wait for diagnostics commit/native release after READY.
    val record=dao.recording(id)!!;val segments=dao.segmentList(id);val diagnostic=JSONObject(record.diagnostics)
    val hypothesis=segments.joinToString(" ") { it.text };val ref=words(fixture.getString("reference"));val hyp=words(hypothesis)
    val e=distance(ref,hyp);val rchars=ref.joinToString(" ").toList();val hchars=hyp.joinToString(" ").toList();val ce=distance(rchars,hchars)
    errors+=e;totalWords+=ref.size;charErrors+=ce;totalChars+=rchars.size
    val c=JSONObject().put("id",fixture.getString("id")).put("reference",fixture.getString("reference"))
     .put("hypothesis",hypothesis).put("wordErrors",e).put("referenceWords",ref.size).put("charErrors",ce).put("referenceChars",rchars.size)
     .put("originalSha256",before).put("afterSha256",sha(audio)).put("diagnostics",diagnostic)
    cases.put(c);report.put("wordErrors",errors).put("referenceWords",totalWords).put("charErrors",charErrors).put("referenceChars",totalChars);save()
    assertEquals(before,sha(audio));assertEquals("READY",record.status);assertEquals(app.models.asrId,record.backend)
    assertEquals("single",diagnostic.getString("clusteringMode"))
    assertEquals(1.0,diagnostic.getDouble("recognitionInputGain"),.000001)
    assertEquals(0L,diagnostic.getJSONObject("stagesMs").getLong("diarizationInferenceMs"))
    assertTrue(segments.isNotEmpty())
    assertTrue(segments.all { it.speakerId==0 && it.startMs>=0 && it.endMs>it.startMs && it.endMs<=record.durationMs && !it.edited })
    if(fixture.getString("id")=="masha_dima_part11_287") {
     assertEquals(23,ref.size);assertEquals(0,diagnostic.getInt("vadPrimarySpanCount"))
     assertTrue(diagnostic.getBoolean("vadRescueAttempted"));assertTrue(diagnostic.getBoolean("vadRescueApplied"))
     assertTrue(diagnostic.getDouble("vadDetectorGain")>1.0)
     assertTrue("Recover most of the 23 independently scripted words, not just any text",e<=4);rescued++
    } else {
     assertTrue(diagnostic.getInt("vadPrimarySpanCount")>0)
     assertFalse("Existing speech detections must not enter the rescue path",diagnostic.getBoolean("vadRescueAttempted"))
     assertTrue(diagnostic.isNull("vadRescueRms"))
    }
    val exported=Exporter.json(record.title,segments.map { it.domain() }) { "Участник ${it+1}" }
    File(output,"${fixture.getString("id")}-transcript.json").writeText(exported)
    assertEquals(segments.size,JSONObject(exported).getJSONArray("segments").length())
    assertEquals(segments,dao.segmentList(id)) // Fresh Room query, no recognizer result injection.
   } finally {
    withContext(NonCancellable+Dispatchers.IO) { work.cancelUniqueWork("replika-$id").result.get() }
    app.models.gate.withLock { dao.deleteRecording(id) } // Never delete source author fixtures.
   }
  }
  assertEquals(84,totalWords);assertEquals(1,rescued)
  report.put("wer",errors.toDouble()/totalWords).put("cer",charErrors.toDouble()/totalChars).put("rescuedClips",rescued)
  assertTrue("Production rescue must improve over the pre-rescue 31/84 host baseline",errors<=14)
  report.put("status","PASS");save()
 }
}
