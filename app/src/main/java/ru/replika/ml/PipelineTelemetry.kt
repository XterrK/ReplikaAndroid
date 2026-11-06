package ru.replika.ml

import android.content.Context
import android.os.Build
import android.os.Debug
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import org.json.JSONArray
import org.json.JSONObject
import ru.replika.domain.MlPolicy
import java.util.UUID

/** Allowlisted numeric/configuration telemetry only. Never accepts titles, audio paths or hypotheses. */
class PipelineTelemetry(context: Context): AutoCloseable {
 private val started=SystemClock.elapsedRealtime()
 private val run=UUID.randomUUID().toString()
 private val pm=context.getSystemService(PowerManager::class.java)
 val times=linkedMapOf("thermalWaitMs" to 0L)
 private val thermal=JSONArray()
 private var observedMaxPssKb=0
 private val listener=if(Build.VERSION.SDK_INT>=29) PowerManager.OnThermalStatusChangedListener { status ->
  synchronized(this) { thermal.put(JSONObject().put("elapsedMs",SystemClock.elapsedRealtime()-started).put("status",status)) }
  event("thermal",status=status)
 } else null
 init {
  if(Build.VERSION.SDK_INT>=29 && listener!=null) pm.addThermalStatusListener(context.mainExecutor,listener)
  event("start")
 }
 fun thermalStatus(): Int = if(Build.VERSION.SDK_INT>=29) pm.currentThermalStatus else -1
 @Synchronized private fun event(stage: String, elapsedMs: Long=0,status: Int=thermalStatus(),outcome: String="ok") {
  val memory=Debug.MemoryInfo();Debug.getMemoryInfo(memory)
  observedMaxPssKb=maxOf(observedMaxPssKb,memory.totalPss)
  Log.i("ReplikaPerf",JSONObject().put("run",run).put("stage",stage).put("ms",elapsedMs)
   .put("pssKb",memory.totalPss).put("javaUsedBytes",Runtime.getRuntime().totalMemory()-Runtime.getRuntime().freeMemory())
   .put("thermalStatus",status).put("outcome",outcome).toString())
 }
 suspend fun <T> measure(stage: String, block: suspend ()->T): T {
  val start=SystemClock.elapsedRealtime();var outcome="interrupted"
  try { return block().also { outcome="ok" } }
  finally {
   val elapsed=SystemClock.elapsedRealtime()-start
   times[stage]=(times[stage]?:0)+elapsed;event(stage,elapsed,outcome=outcome)
  }
 }
 fun config(backend: String,threads: Int,audioMs: Long,mode: String) {
  // Backend and mode are validated constants, never data derived from transcript content.
  require(backend in setOf("giga-v2","giga-v3"));require(mode in setOf("single","fixed","automatic"))
  Log.i("ReplikaPerf",JSONObject().put("run",run).put("stage","config").put("backend",backend)
   .put("threads",threads).put("vadThreads",1).put("audioMs",audioMs).put("mode",mode).toString())
 }
 suspend fun cool(onWaiting: suspend ()->Unit): Long {
  val elapsed=ThermalGate.await(::thermalStatus,onWaiting)
  if(elapsed>0) { times["thermalWaitMs"]=(times["thermalWaitMs"]?:0)+elapsed;event("cooling",elapsed) }
  return elapsed
 }
 @Synchronized fun snapshot(): JSONObject = JSONObject().put("run",run).put("elapsedMs",SystemClock.elapsedRealtime()-started)
  .put("stagesMs",JSONObject(times as Map<*,*>)).put("observedMaxPssKb",observedMaxPssKb)
  .put("memoryScope","stage boundary PSS snapshots; not continuous peak memory")
  .put("thermalStatus",thermalStatus()).put("thermalEvents",JSONArray(thermal.toString()))
  .put("thermalApiSupported",Build.VERSION.SDK_INT>=29)
 override fun close() {
  if(Build.VERSION.SDK_INT>=29 && listener!=null) pm.removeThermalStatusListener(listener)
  event("finish",SystemClock.elapsedRealtime()-started)
 }
}

object ThermalGate {
 suspend fun await(read: ()->Int,onWaiting: suspend ()->Unit,pause: suspend ()->Unit={delay(3000)}): Long {
  val start=SystemClock.elapsedRealtime();var waited=false
  while(MlPolicy.coolingRequired(read())) {
   currentCoroutineContext().ensureActive()
   if(!waited) { onWaiting();waited=true }
   pause()
  }
  currentCoroutineContext().ensureActive()
  return if(waited) (SystemClock.elapsedRealtime()-start).coerceAtLeast(1) else 0
 }
}
