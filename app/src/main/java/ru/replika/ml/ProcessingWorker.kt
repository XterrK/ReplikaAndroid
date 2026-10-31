package ru.replika.ml

import android.app.*
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.*
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import androidx.work.*
import androidx.room.withTransaction
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.withLock
import com.k2fsa.sherpa.onnx.*
import ru.replika.*
import ru.replika.data.*
import ru.replika.domain.*
import java.io.File
import kotlin.math.*

class ProcessingWorker(context: Context,params: WorkerParameters): CoroutineWorker(context,params) {
 private val app=context.applicationContext as ReplikaApp
 private val dao=app.db.dao()
 private val recordingId=inputData.getString("recordingId")!!
 override suspend fun getForegroundInfo(): ForegroundInfo {
  val nm=applicationContext.getSystemService(NotificationManager::class.java)
  nm.createNotificationChannel(NotificationChannel("processing","Обработка аудио",NotificationManager.IMPORTANCE_LOW))
  val open=PendingIntent.getActivity(applicationContext,recordingId.hashCode(),android.content.Intent(applicationContext,MainActivity::class.java).putExtra("recordingId",recordingId).addFlags(android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP or android.content.Intent.FLAG_ACTIVITY_SINGLE_TOP),PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
  val notification=NotificationCompat.Builder(applicationContext,"processing").setSmallIcon(ru.replika.R.drawable.ic_replika).setContentIntent(open).setContentTitle("REPLIKA · локальная обработка").setContentText("Аудио остаётся на устройстве").setOngoing(true).build()
  return if(Build.VERSION.SDK_INT>=29) ForegroundInfo(recordingId.hashCode() and 0x7fffffff,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC) else ForegroundInfo(recordingId.hashCode() and 0x7fffffff,notification)
 }
 override suspend fun doWork(): Result = withContext(Dispatchers.Default) {
  val pcm=File(applicationContext.cacheDir,"$recordingId-$id.pcm")
  try {
   setForeground(getForegroundInfo())
   app.models.gate.withLock {
    try {
    phase("Проверка моделей")
    val rec=dao.recording(recordingId)?:return@withLock
    val start=SystemClock.elapsedRealtime();val times=linkedMapOf<String,Long>()
    app.models.requireReady(rec.backend)
    times["validationMs"]=SystemClock.elapsedRealtime()-start
    phase("Подготовка · декодирование PCM 16 kHz")
    var stage=SystemClock.elapsedRealtime()
    val decoded=withContext(Dispatchers.IO) { AudioDecoder.decode(rec.audioPath,pcm) }
    times["decodeMs"]=SystemClock.elapsedRealtime()-stage
    app.db.withTransaction {
     ensureActive();val current=dao.recording(recordingId)?:rec
     if(current.status=="CANCELLING") throw CancellationException("User requested cancellation")
     dao.insert(current.copy(status="PROCESSING",phase="VAD",durationMs=decoded.durationMs,peaks=decoded.peaks.joinToString(",")))
    }
    phase("Поиск речи · Silero VAD")
    stage=SystemClock.elapsedRealtime()
    val vad=Vad(config=VadModelConfig(sileroVadModelConfig=SileroVadModelConfig(model=app.models.file("vad/silero_vad.onnx").path,maxSpeechDuration=20f)))
    times["vadLoadMs"]=SystemClock.elapsedRealtime()-stage
    val spans=mutableListOf<Span>()
    try {
     fun drain() { while(!vad.empty()) { val s=vad.front();spans+=Span(s.start*1000/16000,(s.start+s.samples.size)*1000/16000);vad.pop() } }
     java.io.DataInputStream(pcm.inputStream().buffered()).use { input ->
      var read=0
      while(read<decoded.samples) {
       ensureActive();val n=min(512,decoded.samples-read);val block=FloatArray(512);repeat(n) { block[it]=input.readFloat() };vad.acceptWaveform(block);read+=n;drain()
      }
     };vad.flush();drain()
    } finally { vad.release() }
    times["vadMs"]=android.os.SystemClock.elapsedRealtime()-stage
    phase("Диаризация · Pyannote + 3D-Speaker")
    stage=android.os.SystemClock.elapsedRealtime()
    // Native diarization currently requires a contiguous recording. Refuse before OOM.
    val required=decoded.samples.toLong()*4
    val available=Runtime.getRuntime().maxMemory()-(Runtime.getRuntime().totalMemory()-Runtime.getRuntime().freeMemory())
    require(required < available/2) { "Недостаточно памяти для диаризации этой записи. Разделите исходное аудио на части." }
    val diarLoadStart=SystemClock.elapsedRealtime()
    val sd=OfflineSpeakerDiarization(config=OfflineSpeakerDiarizationConfig(
     segmentation=OfflineSpeakerSegmentationModelConfig(pyannote=OfflineSpeakerSegmentationPyannoteModelConfig(app.models.file("diar/segmentation.onnx").path),numThreads=2),
     embedding=SpeakerEmbeddingExtractorConfig(model=app.models.file("diar/embedding.onnx").path,numThreads=2),
     clustering=FastClusteringConfig(numClusters=rec.expectedSpeakers)))
    times["diarizationLoadMs"]=SystemClock.elapsedRealtime()-diarLoadStart
    val turns=try {
     val readStart=SystemClock.elapsedRealtime()
     val samples=AudioDecoder.read(pcm,0,decoded.samples)
     times["diarizationReadMs"]=SystemClock.elapsedRealtime()-readStart
     val inferenceStart=SystemClock.elapsedRealtime()
     val result=sd.process(samples)
     times["diarizationInferenceMs"]=SystemClock.elapsedRealtime()-inferenceStart
     ensureActive()
     Alignment.stable(result.map { Turn((it.start*1000).roundToLong(),(it.end*1000).roundToLong(),it.speaker) })
    } finally { sd.release() }
    times["diarizationMs"]=android.os.SystemClock.elapsedRealtime()-stage
    phase("Сопоставление временных интервалов")
    val boundedSpans=Alignment.context(spans,decoded.durationMs,PRE_ROLL_MS,POST_ROLL_MS)
    val slices=Alignment.slices(boundedSpans,turns)
    val sliceResults=org.json.JSONArray()
    stage=android.os.SystemClock.elapsedRealtime()
    val segments=mutableListOf<Segment>()
    val asrLoadStart=SystemClock.elapsedRealtime()
    var asrReadMs=0L;var asrInferenceMs=0L;var thermalWaitMs=0L
    val engine: AsrEngine = when(rec.backend) { "giga-v2" -> GigaAmEngine(app.models); "whisper-tiny" -> WhisperEngine(app.models); else -> error("Backend недоступен: ${rec.backend}") }
    times["asrLoadMs"]=SystemClock.elapsedRealtime()-asrLoadStart
    engine.use { engine ->
     for((i,s) in slices.withIndex()) {
      ensureActive();phase("Распознавание · ${engine.source.substringBefore(" /")} · ${i+1}/${slices.size}")
      val pm=applicationContext.getSystemService(PowerManager::class.java)
      if(Build.VERSION.SDK_INT>=29 && pm.currentThermalStatus>=PowerManager.THERMAL_STATUS_SEVERE) {
       val thermalStart=SystemClock.elapsedRealtime()
       phase("Устройство перегрето · ожидание охлаждения")
       while(pm.currentThermalStatus>=PowerManager.THERMAL_STATUS_SEVERE) { delay(3000);ensureActive() }
       thermalWaitMs+=SystemClock.elapsedRealtime()-thermalStart
      }
      val a=(s.startMs*16).toInt();val b=min((s.endMs*16).toInt(),decoded.samples)
      var asrStep=SystemClock.elapsedRealtime()
      val samples=AudioDecoder.read(pcm,a,(b-a).coerceAtLeast(0))
      asrReadMs+=SystemClock.elapsedRealtime()-asrStep
      asrStep=SystemClock.elapsedRealtime()
      val text=engine.recognize(samples)
      val inferenceMs=SystemClock.elapsedRealtime()-asrStep;asrInferenceMs+=inferenceMs
      sliceResults.put(org.json.JSONObject().put("startMs",s.startMs).put("endMs",s.endMs).put("speakerId",s.speaker).put("text",text).put("blank",text.isBlank()).put("inferenceMs",inferenceMs).put("warnings",org.json.JSONArray(s.reasons)))
      ensureActive()
      if(text.isNotBlank()) segments+=Segment(startMs=s.startMs,endMs=s.endMs,speakerId=s.speaker,text=text,source=engine.source,reasons=s.reasons)
     }
    }
    times["asrMs"]=SystemClock.elapsedRealtime()-stage
    times["asrReadMs"]=asrReadMs;times["asrInferenceMs"]=asrInferenceMs;times["thermalWaitMs"]=thermalWaitMs
    val total=android.os.SystemClock.elapsedRealtime()-start
    val mem=Debug.MemoryInfo();Debug.getMemoryInfo(mem)
    val diagnostics=org.json.JSONObject().put("device","${Build.MANUFACTURER} ${Build.MODEL}").put("android",Build.VERSION.SDK_INT).put("runtime","sherpa-onnx 2.0.1").put("backend",engine.source).put("threads",2).put("vadThreads",1).put("sampleRate",16000).put("expectedSpeakers",rec.expectedSpeakers).put("clusterThreshold",0.5).put("vadThreshold",0.5).put("maxAsrSegmentMs",20000).put("audioMs",decoded.durationMs).put("totalMs",total).put("pipelineRtf",total.toDouble()/decoded.durationMs.coerceAtLeast(1)).put("pipelineTimingScope","model validation through ASR release; excludes final Room commit and diagnostics serialization").put("asrStageRtf",times["asrMs"]!!.toDouble()/decoded.durationMs.coerceAtLeast(1)).put("asrInferenceRtf",asrInferenceMs.toDouble()/decoded.durationMs.coerceAtLeast(1)).put("runCondition","not classified; no cache flush or temperature control").put("finalPssKb",mem.totalPss).put("peakMemory","N/A").put("stagesMs",org.json.JSONObject(times as Map<*,*>)).put("diarizationTurns",org.json.JSONArray().also { array -> turns.forEach { t -> array.put(org.json.JSONObject().put("startMs",t.startMs).put("endMs",t.endMs).put("speakerId",t.speaker)) } }).put("clusteringMode",if(rec.expectedSpeakers>0) "fixed" else "automatic").put("clusterThresholdApplied",rec.expectedSpeakers<=0)
     .put("segmentationWindowShiftRatio",0.1).put("diarMinDurationOnSec",0.2).put("diarMinDurationOffSec",0.5)
     .put("vadMinSpeechSec",0.25).put("vadMinSilenceSec",0.25).put("vadWindowSamples",512).put("vadMaxSpeechSec",20)
     .put("preRollMs",PRE_ROLL_MS).put("postRollMs",POST_ROLL_MS).put("vadSpans",spanJson(spans)).put("asrSpeechSpans",spanJson(boundedSpans)).put("asrSlices",sliceResults)
     .put("modelBytes",app.models.statuses().sumOf { it.bytes }).toString(2)
    app.db.withTransaction {
     ensureActive();val current=dao.recording(recordingId)?:rec
     if(current.status=="CANCELLING") throw CancellationException("User requested cancellation")
     dao.complete(current.copy(status="READY",phase=if(segments.isEmpty()) "Речь не найдена" else "Готово",durationMs=decoded.durationMs,peaks=decoded.peaks.joinToString(","),diagnostics=diagnostics),segments.map { SegmentRow.from(recordingId,it) })
    }
    } catch(e: CancellationException) {
     // Finalize before releasing the native gate: a retry cannot be overwritten by this attempt.
     withContext(NonCancellable) { dao.status(recordingId,"CANCELLED","Обработка отменена") }
     throw e
    }
   }
   Result.success()
  } catch(e: CancellationException) { throw e }
   catch(e: OutOfMemoryError) { dao.status(recordingId,"ERROR","Не хватает памяти","Разделите аудио на части и повторите обработку");Result.failure() }
   catch(e: Throwable) { dao.status(recordingId,"ERROR","Обработка прервана",e.message?:e.javaClass.simpleName);Result.failure() }
   finally { pcm.delete() }
 }
 private suspend fun phase(text: String) {
  currentCoroutineContext().ensureActive()
  app.db.withTransaction {
   if(dao.recording(recordingId)?.status=="CANCELLING") throw CancellationException("User requested cancellation")
   currentCoroutineContext().ensureActive();dao.status(recordingId,"PROCESSING",text)
  }
 }
 private fun spanJson(spans: List<Span>)=org.json.JSONArray().also { a -> spans.forEach { a.put(org.json.JSONObject().put("startMs",it.startMs).put("endMs",it.endMs)) } }
 companion object {
  // 100 ms pre-roll restored the clipped prefix in raw/VAD/aligned comparative Android tests.
  // Extend VAD spans on the original clock, merge overlaps, and keep diarization transitions.
  const val PRE_ROLL_MS=100L
  const val POST_ROLL_MS=0L
  fun enqueue(context: Context,id: String) {
   val request=OneTimeWorkRequestBuilder<ProcessingWorker>().setInputData(workDataOf("recordingId" to id)).addTag(id).build()
   WorkManager.getInstance(context).enqueueUniqueWork("replika-$id",ExistingWorkPolicy.KEEP,request)
  }
 }
}
