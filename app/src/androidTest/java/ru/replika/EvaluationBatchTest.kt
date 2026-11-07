package ru.replika

import ru.replika.domain.CpuPlan

import android.content.Intent
import android.os.Build
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.work.WorkManager
import androidx.work.WorkInfo
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.data.Recording
import ru.replika.domain.JuryJson
import ru.replika.domain.MlPolicy
import ru.replika.domain.AsrPlan
import ru.replika.domain.DiarizationPlan
import ru.replika.ml.ProcessingWorker
import ru.replika.ml.DiarizationEvidence
import ru.replika.ml.AudioDecoder
import ru.replika.ml.GigaAmEngine
import java.io.File
import java.security.MessageDigest
import java.util.UUID

/** QA bridge only: stages audio hashes, never reference text/counts, through the production Worker.
 * Explicitly selected with tools/eval/pull_and_score.py; not bundled into the application APK.
 */
@RunWith(AndroidJUnit4::class)
class EvaluationBatchTest {
 private fun sha(file: File): String {
  val hash=MessageDigest.getInstance("SHA-256")
  file.inputStream().buffered().use { input ->
   val buffer=ByteArray(128*1024)
   while(true) { val size=input.read(buffer);if(size<0) break;hash.update(buffer,0,size) }
  }
  return hash.digest().joinToString("") { "%02x".format(it) }
 }

 @Test fun stagedAudioDecoderEvidence(): Unit=runBlocking {
  val app=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
  val arguments=InstrumentationRegistry.getArguments()
  val runName=arguments.getString("evalRun")?:"not-staged"
  val caseId=arguments.getString("evalCase")?:"not-staged"
  require(Regex("[A-Za-z0-9_-]+").matches(runName) && Regex("[A-Za-z0-9_-]+").matches(caseId))
  val root=File(app.filesDir,"evaluation/$runName")
  val source=File(root,"audio/$caseId.wav")
  Assume.assumeTrue("Stage a canonical input with the evaluation driver",source.isFile)
  val output=File(root,"decoder-$caseId")
  check(!output.exists() && output.mkdir()) { "Keep prior decoded evidence; use a fresh staged run" }
  val before=sha(source)
  val decoded=withContext(Dispatchers.IO) { AudioDecoder.decode(source.path,File(output,"decoded.pcm")) }
  assertEquals(before,sha(source))
  File(output,"metadata.json").writeText(JSONObject().put("input_sha256",before).put("samples",decoded.samples)
   .put("duration_ms",decoded.durationMs).put("peaks",JSONArray(decoded.peaks)).put("newModelInference",false)
   .put("pcmFormat","big-endian IEEE Float32 from unmodified production AudioDecoder").toString(2),Charsets.UTF_8)
 }

 @Test fun stagedFreshAsrSliceEvidence(): Unit=runBlocking {
  val app=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
  val arguments=InstrumentationRegistry.getArguments()
  val runName=arguments.getString("evalRun")?:"not-staged"
  val caseId=arguments.getString("evalCase")?:"not-staged"
  require(Regex("[A-Za-z0-9_-]+").matches(runName) && Regex("[A-Za-z0-9_-]+").matches(caseId))
  val start=arguments.getString("evalStartMs")?.toLong()?:0L
  val end=arguments.getString("evalEndMs")?.toLong()?:0L
  require(start>=0 && end>start && end<=Int.MAX_VALUE/16)
  val root=File(app.filesDir,"evaluation/$runName/decoder-$caseId")
  val pcm=File(root,"decoded.pcm")
  Assume.assumeTrue("Capture the actual decoded input first",pcm.isFile)
  val output=File(root,"fresh-asr-$start-$end.json")
  check(!output.exists()) { "Keep existing probe evidence" }
  app.models.requireReady()
  val samples=AudioDecoder.read(pcm,(start*16).toInt(),((end-start)*16).toInt())
  val begin=SystemClock.elapsedRealtime()
  val text=withContext(Dispatchers.Default) { GigaAmEngine(app.models,2).use { it.recognize(samples) } }
  output.writeText(JSONObject().put("start_ms",start).put("end_ms",end).put("text",text)
   .put("processing_ms",SystemClock.elapsedRealtime()-begin).put("threads",2).put("newModelInference",true)
   .put("scope","Fresh production GigaAmEngine on a slice of actual Android PCM; no reference/VAD/diarization hints")
   .toString(2),Charsets.UTF_8)
 }

 @Test fun stagedCanonicalInputsThroughProductionWorker(): Unit=runBlocking {
  val instrumentation=InstrumentationRegistry.getInstrumentation()
  val app=instrumentation.targetContext.applicationContext as ReplikaApp
  val arguments=InstrumentationRegistry.getArguments()
  val collectEvidence=when(arguments.getString("evalCollectEvidence")?:"true") {
   "true" -> true
   "false" -> false
   else -> error("evalCollectEvidence must be exactly true or false")
  }
  val processId=android.os.Process.myPid()
  val runName=arguments.getString("evalRun")?:"not-staged"
  require(Regex("[A-Za-z0-9_-]+").matches(runName))
  val root=File(app.filesDir,"evaluation/$runName")
  val manifest=File(root,"batch.json")
  Assume.assumeTrue("Explicitly stage an evaluation run with tools/eval/pull_and_score.py",manifest.isFile)
  val batch=JSONObject(manifest.readText(Charsets.UTF_8))
  assertEquals(setOf("schema_version","run","cases"),batch.keys().asSequence().toSet())
  assertEquals(1,batch.getInt("schema_version"));assertEquals(runName,batch.getString("run"))
  val rows=batch.getJSONArray("cases")
  val identifiers=(0 until rows.length()).map { rows.getJSONObject(it).getString("id") }
  require(identifiers.isNotEmpty() && identifiers.distinct().size==identifiers.size) { "Empty or duplicate case IDs" }
  val output=File(root,"output")
  check(!output.exists() && output.mkdir()) { "Choose a fresh evalRun; previous evidence must remain intact" }
  val requestedThreads=arguments.getString("evalThreads")?.toInt()?:2
  val asrPlan=AsrPlan.fromPersistedId(arguments.getString("evalAsrPlan"))
  // Explicit QA selection is independent of the installed APK's defaults.
  val requestedDiarPlan=DiarizationPlan.fromPersistedId(arguments.getString("evalDiarPlan"))
  val cpuPlan=CpuPlan.fromPersistedId(arguments.getString("evalCpuPlan"))
  // Step 14: explicit old/new pipeline selection on the same APK; absent means the production default.
  val parallelAsrDiar=when(arguments.getString("evalParallel")) {
   null -> ru.replika.domain.ParallelAsrDiarPolicy.DEFAULT_ENABLED
   "true" -> true
   "false" -> false
   else -> error("evalParallel must be exactly true or false")
  }
  val speakers=arguments.getString("evalExpectedSpeakers")?.toInt()?:-1
  MlPolicy.mode(speakers)
  val diarPlan=requestedDiarPlan.forExpectedSpeakers(speakers)
  diarPlan.requirePairedAsr(asrPlan)
  val cpu=cpuPlan.resolve(requestedThreads,Runtime.getRuntime().availableProcessors(),diarPlan.refined)
  val threads=cpu.asrThreads
  withTimeout(10*60*1000L) { app.bundledModels.awaitReady() }
  app.models.requireReady(app.models.asrId,speakers!=1)
  assertEquals("giga-v3",app.models.asrId)
  val cases=JSONArray()
  val report=JSONObject().put("status","RUNNING").put("run",runName).put("cases",cases)
   .put("scope","Actual Android production Worker; independent reference text/counts are not staged or passed to recognition")
   .put("api",Build.VERSION.SDK_INT).put("supportedAbis",JSONArray(Build.SUPPORTED_ABIS.toList()))
   .put("collectEvidence",collectEvidence).put("processId",processId).put("parallelAsrDiarizationRequested",parallelAsrDiar)
   .put("threads",threads).put("requestedThreads",requestedThreads).put("cpuPlan",cpuPlan.wireId)
   .put("cpuPolicy",DiarizationEvidence.jsonObject(cpu.asMap())).put("expectedSpeakers",speakers).put("newModelInference",true)
   .put("asrPlan",asrPlan.wireId).put("asrPolicy",ProcessingWorker.asrPolicyJson(asrPlan))
   .put("diarizationPlanRequested",requestedDiarPlan.wireId).put("diarizationPlan",diarPlan.wireId)
   .put("diarizationPolicy",DiarizationEvidence.jsonObject(ProcessingWorker.diarizationPolicy(diarPlan)))
  fun save() {
   val temporary=File(output,"report.json.tmp")
   temporary.writeText(report.toString(2),Charsets.UTF_8)
   check(temporary.renameTo(File(output,"report.json")))
  }
  save()
  try {
   for(index in 0 until rows.length()) {
    val fixture=rows.getJSONObject(index)
    assertEquals(setOf("id","audio","sha256"),fixture.keys().asSequence().toSet())
    val caseId=fixture.getString("id")
    require(Regex("[A-Za-z0-9_-]+").matches(caseId))
    val audio=File(root,fixture.getString("audio")).canonicalFile
    require(audio.path.startsWith(root.canonicalPath+File.separator))
    val before=sha(audio);assertEquals(fixture.getString("sha256"),before)
    val recordId="qa-evaluation-${UUID.randomUUID()}"
    app.db.dao().insert(Recording(recordId,"Evaluation · $caseId",audio.path,backend=app.models.asrId,expectedSpeakers=speakers))
    var complete=false
    try {
     app.startActivity(Intent(app,MainActivity::class.java).putExtra("recordingId",recordId)
      .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
     withTimeout(30000) {
      while(true) {
       var resumed=false
       instrumentation.runOnMainSync { resumed=ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).any { it is MainActivity } }
       if(resumed) break
       delay(100)
      }
     }
     val wallStart=SystemClock.elapsedRealtime()
     ProcessingWorker.enqueue(app,recordId,requestedThreads.takeUnless { it==0 },asrPlan,collectWordEvidence=collectEvidence,diarizationPlan=requestedDiarPlan,cpuPlan=cpuPlan,parallelAsrDiarization=parallelAsrDiar)
     withTimeout(20*60*1000L) {
      while(true) {
       val current=app.db.dao().recording(recordId)?:error("Evaluation record disappeared")
       check(current.status !in setOf("ERROR","CANCELLED")) { "Worker failed: ${current.status} ${current.error}" }
       if(current.status=="READY") break
       delay(200)
      }
     }
     app.models.gate.withLock { }
     val perfWorkInfo: WorkInfo?=if(collectEvidence) null else withTimeout(30000L) {
      var succeeded: WorkInfo?=null
      while(succeeded==null) {
       val infos=withContext(Dispatchers.IO) { WorkManager.getInstance(app).getWorkInfosByTag(recordId).get() }
       check(infos.size==1) { "Expected exactly one WorkInfo for this QA recording" }
       val info=infos.single()
       check(recordId in info.tags) { "WorkInfo tag does not match this QA recording" }
       check(info.state !in setOf(WorkInfo.State.FAILED,WorkInfo.State.CANCELLED)) { "Worker ended as ${info.state}" }
       if(info.state==WorkInfo.State.SUCCEEDED) succeeded=info else delay(50)
      }
      checkNotNull(succeeded)
     }
     val current=app.db.dao().recording(recordId)!!
     val diagnostic=JSONObject(current.diagnostics)
     assertEquals(asrPlan.wireId,diagnostic.getString("asrPlan"))
     assertEquals(requestedDiarPlan.wireId,diagnostic.getString("diarizationPlanRequested"))
     assertEquals(diarPlan.wireId,diagnostic.getString("diarizationPlan"))
     val actualCpu=diagnostic.getJSONObject("cpuPolicy")
     val expectedCpu=cpuPlan.resolve(requestedThreads,actualCpu.getInt("availableCores"),diarPlan.refined)
     val expectedCpuJson=DiarizationEvidence.jsonObject(expectedCpu.asMap())
     assertEquals(expectedCpuJson.keys().asSequence().toSet(),actualCpu.keys().asSequence().toSet())
     for(key in expectedCpuJson.keys()) assertEquals("CPU policy $key",expectedCpuJson.get(key),actualCpu.get(key))
     assertEquals(expectedCpu.asrThreads,diagnostic.getInt("threads"))
     assertEquals(collectEvidence,diagnostic.get("wordEvidenceRequested"))
     if(!collectEvidence && diagnostic.has("diarizationEvidenceRequested")) {
      assertEquals(false,diagnostic.get("diarizationEvidenceRequested"))
     }
     val segments=app.db.dao().segmentList(recordId).map { it.domain() }
     assertTrue(segments.none { it.edited })
     File(output,"$caseId.hypothesis.json").writeText(JuryJson.encode(segments),Charsets.UTF_8)
     File(output,"$caseId.diagnostics.json").writeText(diagnostic.toString(2),Charsets.UTF_8)
     assertEquals(before,sha(audio))
     val result=JSONObject().put("id",caseId).put("status","COMPLETE").put("audio_sha256",before)
      .put("duration_ms",current.durationMs).put("processing_ms",diagnostic.getLong("totalMs"))
      .put("worker_wall_ms",SystemClock.elapsedRealtime()-wallStart).put("segments",segments.size)
      .put("newModelInference",true).put("recordingId",recordId)
      .put("collectEvidence",collectEvidence).put("processId",processId)
      .put("parallelAsrDiarization",diagnostic.optJSONObject("parallelAsrDiarization")?:JSONObject.NULL)
      .put("stagesMs",diagnostic.optJSONObject("stagesMs")?:JSONObject.NULL)
     if(perfWorkInfo!=null) {
      result.put("workId",perfWorkInfo.id.toString()).put("workManagerState",perfWorkInfo.state.name)
     }
     if(diarPlan.refined && collectEvidence) {
      assertTrue(diagnostic.getBoolean("diarizationRefinementAccepted"))
      assertTrue(diagnostic.getJSONObject("diarizationRefinement").getBoolean("nativeResourcesReleasedBeforeRefiner"))
      val counts=diagnostic.getJSONObject("diarizationEmbeddingCounts")
      assertTrue(counts.getInt("measuredWindows")>0)
      assertEquals(512,counts.getInt("embeddingDimension"))
      assertEquals(1,counts.getInt("extractorLoads"))
      for(key in listOf("plannedWindows","readWindows","createdStreams","releasedStreams","computeAttempts","embeddingForwardCalls")) {
       assertEquals(key,counts.getInt("measuredWindows"),counts.getInt(key))
      }
      assertTrue(diagnostic.getBoolean("diarizationEvidenceRequested"))
      assertFalse(diagnostic.getBoolean("diarizationEvidenceTruncated"))
      assertTrue(diagnostic.isNull("diarizationEvidenceOmittedReason"))
      val relative=diagnostic.getString("diarizationEvidenceFile")
      require(Regex("diarization-qa/diarization-[0-9a-f-]{36}\\.json").matches(relative))
      val evidence=File(app.filesDir,relative).canonicalFile
      require(evidence.parentFile==File(app.filesDir,"diarization-qa").canonicalFile)
      val evidenceSha=sha(evidence)
      assertEquals(diagnostic.getLong("diarizationEvidenceBytes"),evidence.length())
      assertTrue(evidence.length() in 1L..DiarizationEvidence.DEFAULT_MAX_BYTES.toLong())
      assertEquals(diagnostic.getString("diarizationEvidenceSha256"),evidenceSha)
      val payload=JSONObject(evidence.readText(Charsets.UTF_8))
      assertEquals(1,payload.getInt("schema_version"));assertFalse(payload.getBoolean("truncated"))
      assertEquals(recordId,payload.getString("recording_id"))
      val workId=UUID.fromString(payload.getString("work_id")).toString()
      assertEquals("diarization-qa/diarization-$workId.json",relative)
      val metadata=payload.getJSONObject("metadata")
      assertEquals(before,metadata.getString("inputAudioSha256"))
      assertEquals(current.durationMs,metadata.getLong("audioMs"))
      assertEquals(diarPlan.wireId,metadata.getString("diarizationPlan"))
      assertTrue(metadata.getBoolean("accepted"))
      assertEquals(counts.getInt("measuredWindows"),payload.getJSONArray("windows").length())
      val captured=File(output,"$caseId.diarization-evidence.json")
      check(!captured.exists())
      evidence.copyTo(captured,overwrite=false)
      assertEquals(evidenceSha,sha(captured))
      result.put("workId",workId).put("diarizationEvidenceSha256",evidenceSha)
       .put("diarizationEvidenceBytes",captured.length()).put("diarizationEvidenceFile",captured.name)
     }
     cases.put(result);File(output,"$caseId.case.json").writeText(result.toString(2),Charsets.UTF_8);save()
     complete=true
    } finally {
     // Only completed QA rows are removed; failed jobs/inputs remain available for diagnosis.
     if(complete) app.models.gate.withLock {
      app.db.dao().deleteSpeakers(recordId);app.db.dao().clearSegments(recordId);app.db.dao().deleteRecording(recordId)
     }
     else withContext(NonCancellable) {
      report.put("failedRecordId",recordId).put("cancellationRequested",true)
       .put("cancellationScope","Request for own QA job only; current JNI call may still need to return")
      runCatching { WorkManager.getInstance(app).cancelUniqueWork("replika-$recordId") }
       .onFailure { report.put("cancellationRequestError",it.toString()) }
     }
    }
   }
   report.put("status","COMPLETE");save()
  } catch(error: Throwable) {
   report.put("status","FAILED").put("error",error.stackTraceToString());save();throw error
  } finally {
   instrumentation.runOnMainSync {
    ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).filterIsInstance<MainActivity>().forEach { it.finish() }
   }
  }
 }
}
