package ru.replika.ml

import android.app.*
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.*
import androidx.core.app.NotificationCompat
import androidx.work.*
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
  val cancel=WorkManager.getInstance(applicationContext).createCancelPendingIntent(id)
  val notification=NotificationCompat.Builder(applicationContext,"processing").setSmallIcon(ru.replika.R.drawable.ic_replika).setContentTitle("REPLIKA · локальная обработка").setContentText("Аудио остаётся на устройстве").setOngoing(true).addAction(0,"Отменить",cancel).build()
  return if(Build.VERSION.SDK_INT>=29) ForegroundInfo(42,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC) else ForegroundInfo(42,notification)
 }
 override suspend fun doWork(): Result = withContext(Dispatchers.Default) {
  val pcm=File(applicationContext.cacheDir,"$recordingId.pcm")
  try {
   setForeground(getForegroundInfo())
   app.models.gate.withLock {
    phase("Проверка моделей")
    val rec=dao.recording(recordingId)?:return@withLock
    app.models.requireReady(rec.backend)
    val start=android.os.SystemClock.elapsedRealtime();val times=linkedMapOf<String,Long>()
    phase("Подготовка · декодирование PCM 16 kHz")
    val decoded=withContext(Dispatchers.IO) { AudioDecoder.decode(rec.audioPath,pcm) }
    times["decodeMs"]=android.os.SystemClock.elapsedRealtime()-start
    dao.insert((dao.recording(recordingId)?:rec).copy(status="PROCESSING",phase="VAD",durationMs=decoded.durationMs,peaks=decoded.peaks.joinToString(",")))
    phase("Поиск речи · Silero VAD")
    var stage=android.os.SystemClock.elapsedRealtime()
    val vad=Vad(config=VadModelConfig(sileroVadModelConfig=SileroVadModelConfig(model=app.models.file("vad/silero_vad.onnx").path,maxSpeechDuration=20f)))
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
    val sd=OfflineSpeakerDiarization(config=OfflineSpeakerDiarizationConfig(
     segmentation=OfflineSpeakerSegmentationModelConfig(pyannote=OfflineSpeakerSegmentationPyannoteModelConfig(app.models.file("diar/segmentation.onnx").path),numThreads=2),
     embedding=SpeakerEmbeddingExtractorConfig(model=app.models.file("diar/embedding.onnx").path,numThreads=2),
     clustering=FastClusteringConfig(numClusters=rec.expectedSpeakers)))
    val job=currentCoroutineContext()[Job]!!
    val turns=try {
     val samples=AudioDecoder.read(pcm,0,decoded.samples)
     val result=sd.processWithCallback(samples,{ _,_,_ -> if(job.isActive) 0 else 1 })
     ensureActive()
     Alignment.stable(result.map { Turn((it.start*1000).roundToLong(),(it.end*1000).roundToLong(),it.speaker) })
    } finally { sd.release() }
    times["diarizationMs"]=android.os.SystemClock.elapsedRealtime()-stage
    phase("Сопоставление временных интервалов")
    val slices=Alignment.slices(spans.map { Span(it.startMs.coerceAtLeast(0),min(it.endMs,decoded.durationMs)) },turns)
    stage=android.os.SystemClock.elapsedRealtime()
    val segments=mutableListOf<Segment>()
    val engine: AsrEngine = when(rec.backend) { "giga-v2" -> GigaAmEngine(app.models); "whisper-tiny" -> WhisperEngine(app.models); else -> error("Backend недоступен: ${rec.backend}") }
    engine.use { engine ->
     for((i,s) in slices.withIndex()) {
      ensureActive();phase("Распознавание · ${engine.source.substringBefore(" /")} · ${i+1}/${slices.size}")
      val pm=applicationContext.getSystemService(PowerManager::class.java)
      if(Build.VERSION.SDK_INT>=29 && pm.currentThermalStatus>=PowerManager.THERMAL_STATUS_SEVERE) {
       phase("Устройство перегрето · ожидание охлаждения")
       while(pm.currentThermalStatus>=PowerManager.THERMAL_STATUS_SEVERE) { delay(3000);ensureActive() }
      }
      val a=(s.startMs*16).toInt();val b=min((s.endMs*16).toInt(),decoded.samples)
      val text=engine.recognize(AudioDecoder.read(pcm,a,(b-a).coerceAtLeast(0)))
      ensureActive()
      if(text.isNotBlank()) segments+=Segment(startMs=s.startMs,endMs=s.endMs,speakerId=s.speaker,text=text,source=engine.source,reasons=s.reasons)
     }
    }
    times["asrMs"]=android.os.SystemClock.elapsedRealtime()-stage
    val total=android.os.SystemClock.elapsedRealtime()-start
    val mem=Debug.MemoryInfo();Debug.getMemoryInfo(mem)
    val diagnostics=org.json.JSONObject().put("device","${Build.MANUFACTURER} ${Build.MODEL}").put("android",Build.VERSION.SDK_INT).put("runtime","sherpa-onnx 2.0.1").put("backend",engine.source).put("threads",2).put("audioMs",decoded.durationMs).put("totalMs",total).put("pipelineRtf",total.toDouble()/decoded.durationMs.coerceAtLeast(1)).put("asrRtf",times["asrMs"]!!.toDouble()/decoded.durationMs.coerceAtLeast(1)).put("finalPssKb",mem.totalPss).put("peakMemory","N/A").put("stagesMs",org.json.JSONObject(times as Map<*,*>)).put("diarizationTurns",org.json.JSONArray().also { array -> turns.forEach { t -> array.put(org.json.JSONObject().put("startMs",t.startMs).put("endMs",t.endMs).put("speakerId",t.speaker)) } }).put("modelBytes",app.models.statuses().sumOf { it.bytes }).toString(2)
    dao.complete((dao.recording(recordingId)?:rec).copy(status="READY",phase=if(segments.isEmpty()) "Речь не найдена" else "Готово",durationMs=decoded.durationMs,peaks=decoded.peaks.joinToString(","),diagnostics=diagnostics),segments.map { SegmentRow.from(recordingId,it) })
   }
   Result.success()
  } catch(e: CancellationException) { withContext(NonCancellable) { dao.status(recordingId,"CANCELLED","Обработка отменена") };throw e }
   catch(e: OutOfMemoryError) { dao.status(recordingId,"ERROR","Не хватает памяти","Разделите аудио на части и повторите обработку");Result.failure() }
   catch(e: Throwable) { dao.status(recordingId,"ERROR","Обработка прервана",e.message?:e.javaClass.simpleName);Result.failure() }
   finally { pcm.delete() }
 }
 private suspend fun phase(text: String) { currentCoroutineContext().ensureActive();dao.status(recordingId,"PROCESSING",text) }
 companion object {
  fun enqueue(context: Context,id: String) {
   val request=OneTimeWorkRequestBuilder<ProcessingWorker>().setInputData(workDataOf("recordingId" to id)).addTag(id).build()
   WorkManager.getInstance(context).enqueueUniqueWork("replika-pipeline",ExistingWorkPolicy.APPEND_OR_REPLACE,request)
  }
 }
}
