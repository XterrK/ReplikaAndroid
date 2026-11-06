package ru.replika.ml

import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import ru.replika.BuildConfig
import ru.replika.ReplikaApp
import java.io.File
import java.io.IOException
import java.util.UUID

/** Application-scoped IO job; activity recreation never restarts or duplicates extraction. */
class BundledModelCoordinator(private val app: ReplikaApp) {
 enum class Phase { CHECKING, PREPARING, VERIFYING, COMPLETE, READY, NO_SPACE, NO_MEMORY, ERROR }
 data class State(val phase: Phase, val processedBytes: Long = 0, val totalBytes: Long = 0,
                  val path: String? = null, val message: String? = null) {
  val failed get() = phase in setOf(Phase.NO_SPACE, Phase.NO_MEMORY, Phase.ERROR)
 }
 private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
 private val mutableState = MutableStateFlow(State(if(BuildConfig.BUNDLED_MODELS) Phase.CHECKING else Phase.READY))
 val state: StateFlow<State> = mutableState.asStateFlow()
 private var job: Job? = null

 @Synchronized fun start(forceCheck: Boolean = false) {
  if(!BuildConfig.BUNDLED_MODELS || job?.isActive == true || (!forceCheck && state.value.phase == Phase.READY)) return
  mutableState.value = State(Phase.CHECKING)
  job = scope.launch {
   val started = SystemClock.elapsedRealtime()
   val runId = UUID.randomUUID().toString()
   var lastProgress = 0L
   var lastPhase: Phase? = null
   var phaseStarted=started
   val stageTimes=linkedMapOf<String,Long>()
   val diagnostic = JSONObject().put("runId",runId).put("version",BuildConfig.VERSION_NAME)
    .put("asset",BuildConfig.EMBEDDED_MODEL_ASSET).put("startedAtUtc",java.time.Instant.now().toString())
   val folder = File(app.filesDir,"provisioning-diagnostics").apply { mkdirs() }
   fun persist() {
    runCatching {
     val temp = File(folder,"latest.json.part")
     temp.writeText(diagnostic.toString(2));check(temp.renameTo(File(folder,"latest.json")))
    }.onFailure { Log.w("ReplikaProvision","Cannot write diagnostics",it) }
   }
   try {
    val context = currentCoroutineContext()
    val gateStarted=SystemClock.elapsedRealtime()
    val report = app.models.gate.withLock {
     stageTimes["nativeGateWaitMs"]=SystemClock.elapsedRealtime()-gateStarted
     phaseStarted=SystemClock.elapsedRealtime()
     val specs = app.models.specifications()
     val stage = File(app.filesDir,"bundled-model-staging/${BundledModelInstaller.manifestFingerprint(specs)}")
     BundledModelInstaller(specs,app.models.root,stage,
      openPack = { app.assets.open(BuildConfig.EMBEDDED_MODEL_ASSET) },
      checkCancelled = { context.ensureActive() },
      progress = { value ->
       val phase = when(value.phase) {
        BundledModelInstaller.Phase.CHECKING -> Phase.CHECKING
        BundledModelInstaller.Phase.PREPARING -> Phase.PREPARING
        BundledModelInstaller.Phase.VERIFYING -> Phase.VERIFYING
        BundledModelInstaller.Phase.READY -> Phase.COMPLETE
       }
       val now = SystemClock.elapsedRealtime()
       if(phase != lastPhase || now-lastProgress >= 80 || value.processedBytes == value.totalBytes) {
        mutableState.value = State(phase,value.processedBytes,value.totalBytes,value.path)
        // Persist transitions, rather than writing JSON for every 128 KiB read.
        if(phase != lastPhase) {
         lastPhase?.let { previous -> stageTimes[previous.name]=(stageTimes[previous.name]?:0)+(now-phaseStarted) }
         phaseStarted=now
         diagnostic.put("stagesMs",JSONObject(stageTimes as Map<*,*>)).put("phase",phase.name).put("processedBytes",value.processedBytes)
          .put("totalBytes",value.totalBytes).put("elapsedMs",now-started)
         persist();Log.i("ReplikaProvision",JSONObject().put("run",runId).put("phase",phase.name).put("elapsedMs",now-started).put("bytes",value.processedBytes).put("totalBytes",value.totalBytes).put("stagesMs",JSONObject(stageTimes as Map<*,*>)).toString())
        }
        lastPhase = phase;lastProgress = now
       }
      }).install().also {
       runCatching { app.models.removeRetiredWhisperFiles() }.onFailure { Log.w("ReplikaProvision","Cannot retire removed model weight",it) }
      }
    }
    lastPhase?.let { previous -> stageTimes[previous.name]=(stageTimes[previous.name]?:0)+(SystemClock.elapsedRealtime()-phaseStarted) }
    diagnostic.put("stagesMs",JSONObject(stageTimes as Map<*,*>)).put("phase","READY").put("elapsedMs",SystemClock.elapsedRealtime()-started)
     .put("validSkipped",report.validSkipped).put("reusedStage",report.reusedStage)
     .put("extracted",report.extracted).put("published",report.published).put("modelBytes",report.modelBytes)
    persist()
    runCatching { File(folder,"$runId.json").writeText(diagnostic.toString(2)) }
    // A brief verified completion state; the Library opens automatically.
    delay(400)
    mutableState.value = State(Phase.READY,report.modelBytes,report.modelBytes)
   } catch(e: CancellationException) { throw e
   } catch(e: Throwable) {
    val (phase,message) = when(e) {
     is BundledModelInstaller.InsufficientSpaceException -> Phase.NO_SPACE to
      "Освободите место во внутреннем хранилище и повторите. Нужно ещё ${megabytes(e.requiredBytes)} МБ, доступно ${megabytes(e.availableBytes)} МБ."
     is OutOfMemoryError -> Phase.NO_MEMORY to "Закройте другие приложения и повторите подготовку. Не хватило оперативной памяти."
     is IOException -> if(e.message.orEmpty().contains("ENOSPC",ignoreCase=true) || e.message.orEmpty().contains("No space left",ignoreCase=true))
      Phase.NO_SPACE to "Во время подготовки закончилось место. Освободите внутреннее хранилище и повторите попытку. Проверенные файлы сохранены."
      else Phase.ERROR to "Не удалось прочитать или проверить встроенный комплект. Повторите подготовку. При повторной ошибке установите актуальный APK поверх приложения."
     else -> Phase.ERROR to "Не удалось проверить или подготовить встроенные модели. Повторите попытку. Если ошибка повторится, переустановите актуальный APK поверх приложения."
    }
    diagnostic.put("phase",phase.name).put("errorType",e.javaClass.name).put("error",e.message)
     .put("elapsedMs",SystemClock.elapsedRealtime()-started)
    persist();Log.e("ReplikaProvision","Provisioning failed",e)
    mutableState.value = State(phase,message=message)
   }
  }
 }

 suspend fun awaitReady() {
  start()
  val result = state.first { it.phase == Phase.READY || it.failed }
  if(result.failed) throw IOException(result.message ?: "Не удалось подготовить офлайн-модели")
 }
 private fun megabytes(bytes: Long) = (bytes+1048575)/1048576
}
