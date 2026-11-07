package ru.replika.ml

import android.content.Context
import android.os.Build
import android.os.Debug
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import org.json.JSONArray
import org.json.JSONObject
import ru.replika.domain.MlPolicy
import ru.replika.domain.CpuResolution
import java.util.UUID

/** Allowlisted numeric/configuration telemetry only. Never accepts titles, audio paths or hypotheses. */
class PipelineTelemetry(context: Context): AutoCloseable {
 private val started=SystemClock.elapsedRealtime()
 private val run=UUID.randomUUID().toString()
 private val pm=try { context.getSystemService(PowerManager::class.java) }
  catch(error: CancellationException) { throw error } catch(_: RuntimeException) { null }
 val times=linkedMapOf("thermalWaitMs" to 0L)
 private val thermal=JSONArray()
 private var observedMaxPssKb=0
 private val listener: PowerManager.OnThermalStatusChangedListener?=if(Build.VERSION.SDK_INT>=29) PowerManager.OnThermalStatusChangedListener { status ->
  val normalized=thermalSource.observe(status)
  synchronized(this) { thermal.put(JSONObject().put("elapsedMs",SystemClock.elapsedRealtime()-started).put("status",normalized)) }
  event("thermal",status=normalized)
 } else null
 private val thermalSource: ThermalStatusSource=ThermalStatusSource(
  apiSupported=Build.VERSION.SDK_INT>=29 && pm!=null,
  readPlatform={ if(Build.VERSION.SDK_INT>=29) requireNotNull(pm).currentThermalStatus else -1 },
  registerListener={ if(Build.VERSION.SDK_INT>=29 && listener!=null) requireNotNull(pm).addThermalStatusListener(context.mainExecutor,listener) },
  unregisterListener={ if(Build.VERSION.SDK_INT>=29 && listener!=null) requireNotNull(pm).removeThermalStatusListener(listener) },
  unavailableReasonIfUnsupported=if(Build.VERSION.SDK_INT<29) "api_below_29" else "power_service_unavailable",
 )
 init {
  thermalSource.start()
  event("start")
 }
 fun thermalStatus(): Int = thermalSource.status()
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
   add(stage,elapsed);event(stage,elapsed,outcome=outcome)
  }
 }
 /** Stage timers may be written by the parallel ASR and diarization coroutines (step 14). */
 fun add(stage: String,elapsed: Long) { synchronized(times) { times[stage]=(times[stage]?:0)+elapsed } }
 fun put(stage: String,value: Long) { synchronized(times) { times[stage]=value } }
 fun timesJson(): JSONObject = synchronized(times) { JSONObject(times as Map<*,*>) }
 fun config(backend: String,threads: Int,audioMs: Long,mode: String,cpuResolution: CpuResolution?=null) {
  // Backend and mode are validated constants, never data derived from transcript content.
  require(backend in setOf("giga-v2","giga-v3"));require(mode in setOf("single","fixed","automatic"))
  val record=JSONObject().put("run",run).put("stage","config").put("backend",backend)
   .put("threads",threads).put("vadThreads",1).put("audioMs",audioMs).put("mode",mode)
  if(cpuResolution!=null) record.put("cpuPolicy",JSONObject(cpuResolution.asMap().mapValues { it.value?:JSONObject.NULL }))
  Log.i("ReplikaPerf",record.toString())
 }
 suspend fun cool(onWaiting: suspend ()->Unit): Long {
  val elapsed=ThermalGate.await(::thermalStatus,onWaiting)
  if(elapsed>0) { add("thermalWaitMs",elapsed);event("cooling",elapsed) }
  return elapsed
 }
 @Synchronized fun snapshot(): JSONObject {
  val status=thermalStatus()
  return JSONObject().put("run",run).put("elapsedMs",SystemClock.elapsedRealtime()-started)
  .put("stagesMs",timesJson()).put("observedMaxPssKb",observedMaxPssKb)
  .put("memoryScope","stage boundary PSS snapshots; not continuous peak memory")
  .put("thermalStatus",status).put("thermalEvents",JSONArray(thermal.toString()))
  .put("thermalApiSupported",Build.VERSION.SDK_INT>=29)
  .put("thermalPowerServiceAvailable",pm!=null).put("thermalStatusAvailable",status>=0)
  .put("thermalListenerRegistered",thermalSource.listenerRegistered)
  .put("thermalListenerRegistrationFailed",thermalSource.listenerRegistrationFailed)
  .put("thermalListenerFailureReason",thermalSource.listenerFailureReason?:JSONObject.NULL)
  .put("thermalUnavailableReason",thermalSource.unavailableReason?:JSONObject.NULL)
 }
 override fun close() {
  thermalSource.close()
  event("finish",SystemClock.elapsedRealtime()-started)
 }
}

/** Pure lifecycle wrapper for optional platform telemetry; no Android or model calls in tests.
 * Listener failure never disables polling: a valid getter SEVERE must still be protected.
 * Transient getter failures/unknown statuses are retried on the next read.
 */
class ThermalStatusSource(
 private val apiSupported: Boolean,
 private val readPlatform: ()->Int,
 private val registerListener: (() -> Unit)?=null,
 private val unregisterListener: (() -> Unit)?=null,
 private val unavailableReasonIfUnsupported: String="api_unavailable",
): AutoCloseable {
 init { require((registerListener==null)==(unregisterListener==null)) { "Listener lifecycle callbacks must be paired" } }
 @Volatile var listenerRegistered=false
  private set
 @Volatile var unavailableReason: String?=if(apiSupported) null else unavailableReasonIfUnsupported
  private set
 @Volatile var listenerRegistrationFailed=false
  private set
 @Volatile var listenerFailureReason: String?=null
  private set
 private var started=false
 private var closed=false

 @Synchronized fun start() {
  if(started || closed) return
  started=true
  if(!apiSupported || registerListener==null) return
  try { registerListener.invoke();listenerRegistered=true }
  catch(error: CancellationException) { throw error }
  catch(_: RuntimeException) { listenerRegistrationFailed=true;listenerFailureReason="listener_registration_failed" }
 }
 @Synchronized fun status(): Int {
  if(closed) { unavailableReason="closed";return -1 }
  if(!apiSupported) return -1
  return try { observe(readPlatform()) }
  catch(error: CancellationException) { throw error }
  catch(_: RuntimeException) { unavailableReason="read_failed"; -1 }
 }
 @Synchronized fun observe(value: Int): Int {
  if(closed || !apiSupported) return -1
  val status=MlPolicy.thermalStatus(value)
  unavailableReason=if(status<0) "unknown_status" else null
  return status
 }
 @Synchronized override fun close() {
  if(closed) return
  closed=true
  if(listenerRegistered) {
   try { unregisterListener?.invoke() }
   catch(error: CancellationException) { throw error }
   catch(_: RuntimeException) { listenerFailureReason="listener_removal_failed" }
   finally { listenerRegistered=false }
  }
 }
}

object ThermalGate {
 suspend fun await(read: ()->Int,onWaiting: suspend ()->Unit,pause: suspend ()->Unit={delay(3000)},
  clock: ()->Long=SystemClock::elapsedRealtime): Long {
  val start=clock();var waited=false
  while(true) {
   currentCoroutineContext().ensureActive()
   val status=try { MlPolicy.thermalStatus(read()) }
    catch(error: CancellationException) { throw error } catch(_: RuntimeException) { -1 }
   if(!MlPolicy.coolingRequired(status)) break
   if(!waited) { onWaiting();waited=true }
   pause()
  }
  currentCoroutineContext().ensureActive()
  return if(waited) (clock()-start).coerceAtLeast(1) else 0
 }
}
