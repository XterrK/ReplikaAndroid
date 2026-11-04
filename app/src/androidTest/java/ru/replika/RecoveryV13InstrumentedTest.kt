package ru.replika

import android.os.Build
import android.os.PowerManager
import android.os.SystemClock
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.data.Recording
import ru.replika.ml.*
import ru.replika.domain.*
import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

@RunWith(AndroidJUnit4::class)
class RecoveryV13InstrumentedTest {
 private val instrumentation get()=InstrumentationRegistry.getInstrumentation()
 private val app get()=instrumentation.targetContext.applicationContext as ReplikaApp
 private fun save(name: String,j: JSONObject)=File(app.filesDir,name).writeText(j.toString(2))
 private fun thermal()=app.getSystemService(PowerManager::class.java).currentThermalStatus
 private fun shell(command: String): String = instrumentation.uiAutomation.executeShellCommand(command).use { p ->
  java.io.FileInputStream(p.fileDescriptor).bufferedReader().readText()
 }
 @Test fun bufferedPcmReadMatchesEverySampleAndOriginalClock() {
  val file=File(app.cacheDir,"v13-io.pcm")
  try {
   java.io.DataOutputStream(file.outputStream().buffered()).use { o -> repeat(320000) { o.writeFloat((it%1701-850)/1000f) } }
   val legacyStart=SystemClock.elapsedRealtime()
   val legacy=RandomAccessFile(file,"r").use { f -> FloatArray(320000) { f.readFloat() } }
   val oldMs=SystemClock.elapsedRealtime()-legacyStart
   val start=SystemClock.elapsedRealtime();val current=AudioDecoder.read(file,0,320000)
   val newMs=SystemClock.elapsedRealtime()-start
   assertArrayEquals(legacy,current,0f)
   assertArrayEquals(legacy.copyOfRange(16380,16412),AudioDecoder.read(file,16380,32),0f)
   assertEquals(0,AudioDecoder.read(file,320000,0).size)
   assertTrue(runCatching { AudioDecoder.read(file,319999,2) }.isFailure)
   save("v13-pcm-read.json",JSONObject().put("platform","Android ${Build.VERSION.SDK_INT} ${Build.SUPPORTED_ABIS.joinToString()}")
    .put("samples",320000).put("audioMs",20000).put("legacyUnbufferedMs",oldMs).put("bufferedMs",newMs)
    .put("sampleEquality",true).put("cacheCondition","legacy first then buffered; not a cold-cache benchmark"))
  } finally { file.delete() }
 }
 @Test fun thermalGateWaitResumeAndCancellationWithActualPowerManager()=runBlocking {
  assumeTrue("Overrides allowed ONLY on Android emulator",Build.HARDWARE in listOf("ranchu","goldfish") && Build.VERSION.SDK_INT>=29)
  val before=thermal();val trace=PipelineTelemetry(app)
  try {
   shell("cmd thermalservice override-status 3")
   withTimeout(5000) { while(thermal()!=3) delay(50) }
   var waiting=false;var inferenceStarted=false
   val job=async { trace.cool { waiting=true };inferenceStarted=true }
   withTimeout(5000) { while(!waiting) delay(50) }
   delay(150);assertFalse(inferenceStarted)
   shell("cmd thermalservice override-status 2")
   withTimeout(6000) { job.await() };assertTrue(inferenceStarted)
   shell("cmd thermalservice override-status 4")
   withTimeout(5000) { while(thermal()!=4) delay(50) }
   val cancelled=async { ThermalGate.await(::thermal,{}) }
   delay(150);cancelled.cancelAndJoin();assertTrue(cancelled.isCancelled)
   save("v13-thermal.json",JSONObject().put("emulatorOnlyOverride",true).put("before",before).put("blockedAtSevere",true)
    .put("resumedAtModerate",true).put("cancelledAtCritical",true).put("telemetry",trace.snapshot()))
  } finally { shell("cmd thermalservice reset");trace.close() }
 }
 @Test fun gigaThreadsOneTwoFourSequentialWithIdenticalInput()=runBlocking {
  val source=File(app.filesDir,"integration-example.wav");assertTrue(source.isFile)
  app.models.gate.withLock {
   val pcm=AudioDecoder.decode(source.path,File(app.cacheDir,"v13-threads.pcm"))
   try {
    val samples=AudioDecoder.read(pcm.file,0,pcm.samples);val runs=JSONArray()
    var reference: String?=null
    // Reverse order in pass two to expose warm/cache ordering effects; no concurrent ML.
    for((pass,order) in listOf(listOf(1,2,4),listOf(4,2,1)).withIndex()) for(threads in order) {
     if(Build.VERSION.SDK_INT>=29 && thermal()>=3) throw AssertionError("No benchmark inference while severe thermal status")
     val start=SystemClock.elapsedRealtime();val engine=GigaAmEngine(app.models,threads);val load=SystemClock.elapsedRealtime()-start
     engine.use {
      val t=SystemClock.elapsedRealtime();val text=engine.recognize(samples);val elapsed=SystemClock.elapsedRealtime()-t
      assertTrue(text.isNotBlank());if(reference==null) reference=text else assertEquals("Thread count must not change this fixture hypothesis",reference,text)
      val mem=android.os.Debug.MemoryInfo();android.os.Debug.getMemoryInfo(mem)
      runs.put(JSONObject().put("pass",pass).put("threads",threads).put("loadMs",load).put("inferenceMs",elapsed)
       .put("rtf",elapsed.toDouble()/pcm.durationMs).put("pssKb",mem.totalPss).put("thermalStatus",if(Build.VERSION.SDK_INT>=29) thermal() else -1)
       .put("hypothesisMatches",text==reference))
     }
    }
    save("v13-thread-comparison.json",JSONObject().put("device",Build.MODEL).put("abi",Build.SUPPORTED_ABIS.joinToString())
     .put("audioMs",pcm.durationMs).put("scope","sequential GigaAM CPU; load plus first inference each new engine; caches uncontrolled")
     .put("hypothesisEqualityOnThisFixtureOnly",true).put("runs",runs))
   } finally { pcm.file.delete() }
  }
 }
 @Test fun fourMinuteAutomaticDiarizationRetainsOneSpeakerOnControlledRepeat()=runBlocking {
  val source=File(app.filesDir,"integration-example.wav");assertTrue(source.isFile)
  app.models.gate.withLock {
   val pcm=AudioDecoder.decode(source.path,File(app.cacheDir,"v13-long-auto.pcm"))
   try {
    val original=AudioDecoder.read(pcm.file,0,pcm.samples);val stride=original.size+8000
    val repeated=FloatArray(stride*21)
    repeat(21) { original.copyInto(repeated,it*stride) }
    if(Build.VERSION.SDK_INT>=29 && thermal()>=3) throw AssertionError("No long native probe while severe thermal status")
    val start=SystemClock.elapsedRealtime()
    val sd=com.k2fsa.sherpa.onnx.OfflineSpeakerDiarization(config=ProcessingWorker.diarizationConfig(app.models,-1,2))
    val load=SystemClock.elapsedRealtime()-start
    try {
     val t=SystemClock.elapsedRealtime();val raw=sd.process(repeated);val elapsed=SystemClock.elapsedRealtime()-t
     val duration=repeated.size/16L
     val turns=Alignment.stable(raw.map { Turn((it.start*1000).toLong().coerceIn(0,duration),(it.end*1000).toLong().coerceIn(0,duration),it.speaker) }.filter { it.endMs>it.startMs })
     val count=turns.map { it.speaker }.filter { it>=0 }.distinct().size
     save("v13-long-auto-diarization.json",JSONObject().put("audioMs",duration).put("controlledRepeatNotIndependent",true)
      .put("backend","native Pyannote + 3D-Speaker").put("threads",2).put("threshold",ProcessingWorker.AUTO_CLUSTER_THRESHOLD)
      .put("loadMs",load).put("inferenceMs",elapsed).put("speakers",count).put("turnCount",turns.size)
      .put("turns",JSONArray().also { a -> turns.forEach { a.put(JSONObject().put("startMs",it.startMs).put("endMs",it.endMs).put("speakerId",it.speaker)) } }))
     assertTrue(turns.isNotEmpty());assertEquals("Fixture-specific long mono regression, NOT independent acceptance",1,count)
     assertTrue(turns.all { it.speaker==0 && it.startMs>=0 && it.endMs<=duration })
    } finally { sd.release() }
   } finally { pcm.file.delete() }
  }
 }
 @Test fun fourMinuteSingleSpeakerWorkerSkipsDiarizationAndKeepsBounds()=runBlocking {
  val source=File(app.filesDir,"integration-example.wav");assertTrue(source.isFile)
  val decoded=AudioDecoder.decode(source.path,File(app.cacheDir,"v13-long-source.pcm"))
  val wave=File(app.filesDir,"v13-controlled-repeat.wav")
  val id="v13-long-single"
  val activity=ActivityScenario.launch(MainActivity::class.java)
  try {
   val samples=AudioDecoder.read(decoded.file,0,decoded.samples)
   val repeats=21;val silence=8000;val count=(samples.size+silence)*repeats
   val header=ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
   header.put("RIFF".toByteArray()).putInt(36+count*2).put("WAVEfmt ".toByteArray()).putInt(16).putShort(1).putShort(1)
    .putInt(16000).putInt(32000).putShort(2).putShort(16).put("data".toByteArray()).putInt(count*2)
   wave.outputStream().buffered().use { output ->
    output.write(header.array())
    val block=ByteBuffer.allocate((samples.size+silence)*2).order(ByteOrder.LITTLE_ENDIAN)
    samples.forEach { block.putShort((it.coerceIn(-1f,1f)*32767).toInt().toShort()) };repeat(silence) { block.putShort(0) }
    repeat(repeats) { output.write(block.array()) }
   }
   assertTrue(count/16>=240000)
   app.db.dao().insert(Recording(id,"Controlled repeat; NOT independent real four-minute monologue",wave.path,expectedSpeakers=1))
   ProcessingWorker.enqueue(app,id,2)
   withTimeout(12*60*1000L) {
    while(true) {
     delay(250);val r=app.db.dao().recording(id)!!
     if(r.status=="ERROR") fail(r.error)
     if(r.status=="READY") break
    }
   }
   // READY is published before the diagnostics-only final commit.
   withTimeout(10000) { while(!JSONObject(app.db.dao().recording(id)!!.diagnostics).has("telemetry")) delay(50) }
   val record=app.db.dao().recording(id)!!;val j=JSONObject(record.diagnostics)
   val rows=app.db.dao().segmentList(id)
   assertTrue(rows.isNotEmpty());assertEquals(setOf(0),rows.map { it.speakerId }.toSet())
   assertTrue(rows.all { it.startMs>=0 && it.endMs<=record.durationMs && it.endMs>it.startMs })
   assertTrue(rows.zipWithNext().all { (a,b)->a.endMs<=b.startMs })
   assertEquals(0,j.getJSONObject("stagesMs").getLong("diarizationInferenceMs"))
   assertEquals("single",j.getString("clusteringMode"));assertFalse(j.getBoolean("clusterThresholdApplied"))
   j.put("controlledRepeatNotIndependent",true).put("assertedSingleSpeaker",true).put("segmentCount",rows.size)
   save("v13-long-single-diagnostics.json",j)
   save("v13-long-single-transcript.json",JSONObject(Exporter.json("Controlled repeated public fixture",rows.map { it.domain() }) { "speaker-$it" }))
  } finally {
   activity.close();decoded.file.delete()
   // Keep controlled waveform in app-private QA storage for bounded playback review.
  }
 }
}
