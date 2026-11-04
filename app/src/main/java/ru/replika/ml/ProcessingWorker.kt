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
import org.json.JSONArray
import org.json.JSONObject
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
  val trace=PipelineTelemetry(applicationContext)
  var diagnostic=JSONObject()
  suspend fun guard(label: String) {
   trace.cool { phase("Android сообщил о сильном нагреве · ожидание охлаждения") }
   phase(label)
  }
  try {
   setForeground(getForegroundInfo())
   trace.measure("provisioningWaitMs") { app.bundledModels.awaitReady() }
   val gateStart=SystemClock.elapsedRealtime()
   app.models.gate.withLock {
    trace.times["nativeGateWaitMs"]=SystemClock.elapsedRealtime()-gateStart
    try {
     val rec=dao.recording(recordingId)?:return@withLock
     val mode=MlPolicy.mode(rec.expectedSpeakers)
     val threads=MlPolicy.threads(inputData.getInt("mlThreads",2))
     guard("Проверка моделей")
     val start=SystemClock.elapsedRealtime()
     trace.measure("validationMs") { withContext(Dispatchers.IO) { app.models.requireReady(rec.backend,mode!="single") } }
     guard("Подготовка · декодирование PCM 16 kHz")
     val decoded=trace.measure("decodeMs") { withContext(Dispatchers.IO) { AudioDecoder.decode(rec.audioPath,pcm) } }
     trace.config(rec.backend,threads,decoded.durationMs,mode)
     trace.measure("metadataPersistenceMs") { app.db.withTransaction {
      ensureActive();val current=dao.recording(recordingId)?:rec
      if(current.status=="CANCELLING") throw CancellationException("User requested cancellation")
      dao.insert(current.copy(status="PROCESSING",phase="VAD",durationMs=decoded.durationMs,peaks=decoded.peaks.joinToString(",")))
     } }
     guard("Поиск речи · Silero VAD")
     val vad=trace.measure("vadLoadMs") { Vad(config=VadModelConfig(sileroVadModelConfig=SileroVadModelConfig(
      model=app.models.file("vad/silero_vad.onnx").path,threshold=.5f,minSilenceDuration=.25f,minSpeechDuration=.25f,maxSpeechDuration=20f),numThreads=1)) }
     val spans=mutableListOf<Span>()
     trace.measure("vadMs") {
      try {
       fun drain() { while(!vad.empty()) { val s=vad.front();spans+=Span(s.start*1000/16000,(s.start+s.samples.size)*1000/16000);vad.pop() } }
       java.io.DataInputStream(pcm.inputStream().buffered()).use { input ->
        var read=0;var nextThermalCheck=16000
        while(read<decoded.samples) {
         ensureActive()
         if(read>=nextThermalCheck) {
          if(trace.cool { phase("Android сообщил о сильном нагреве · ожидание охлаждения") }>0) phase("Поиск речи · Silero VAD")
          nextThermalCheck=read+16000
         }
         val n=min(512,decoded.samples-read);val block=FloatArray(512)
         repeat(n) { block[it]=input.readFloat() };vad.acceptWaveform(block);read+=n;drain()
        }
       };vad.flush();drain()
      } finally { vad.release() }
     }
     // Mode A never loads segmentation/embedding, nor allocates a full-recording float array.
     val turns=if(mode=="single") {
      trace.times["diarizationMs"]=0;trace.times["diarizationLoadMs"]=0;trace.times["diarizationInferenceMs"]=0
      listOf(Turn(0,decoded.durationMs,0))
     } else trace.measure("diarizationMs") {
      guard("Диаризация · Pyannote + 3D-Speaker")
      val required=decoded.samples.toLong()*4
      val available=Runtime.getRuntime().maxMemory()-(Runtime.getRuntime().totalMemory()-Runtime.getRuntime().freeMemory())
      require(required<available/2) { "Недостаточно памяти для диаризации этой записи. Выберите одного говорящего для монолога или разделите аудио." }
      val sd=trace.measure("diarizationLoadMs") { OfflineSpeakerDiarization(config=diarizationConfig(app.models,rec.expectedSpeakers,threads)) }
      try {
       val samples=trace.measure("diarizationReadMs") { AudioDecoder.read(pcm,0,decoded.samples) }
       guard("Диаризация · Pyannote + 3D-Speaker")
       val result=trace.measure("diarizationInferenceMs") { sd.process(samples) }
       ensureActive()
       Alignment.stable(result.map { Turn((it.start*1000).roundToLong().coerceIn(0,decoded.durationMs),(it.end*1000).roundToLong().coerceIn(0,decoded.durationMs),it.speaker) }.filter { it.endMs>it.startMs })
      } finally { sd.release() }
     }
     phase("Сопоставление временных интервалов")
     val boundedSpans=Alignment.context(spans,decoded.durationMs,PRE_ROLL_MS,POST_ROLL_MS)
     val slices=trace.measure("alignmentMs") { RecognitionPlanner.plan(boundedSpans,turns) }
     val sliceResults=JSONArray();val segments=mutableListOf<Segment>()
     guard("Загрузка модели распознавания")
     val engine=trace.measure("asrLoadMs") { when(rec.backend) {
      "giga-v2" -> GigaAmEngine(app.models,threads)
      "whisper-tiny" -> WhisperEngine(app.models,threads)
      else -> error("Backend недоступен")
     } }
     val source=engine.source
     trace.measure("asrMs") { engine.use {
      for((i,s) in slices.withIndex()) {
       ensureActive();guard("Распознавание · ${source.substringBefore(" /")} · ${i+1}/${slices.size}")
       val a=(s.startMs*16).toInt();val b=min((s.endMs*16).toInt(),decoded.samples)
       val samples=trace.measure("asrReadMs") { AudioDecoder.read(pcm,a,(b-a).coerceAtLeast(0)) }
       val inferenceStart=SystemClock.elapsedRealtime()
       val text=trace.measure("asrInferenceMs") { engine.recognize(samples) }
       val inferenceMs=SystemClock.elapsedRealtime()-inferenceStart
       // Private Room diagnostics may contain hypotheses; they are NEVER passed to Logcat.
       sliceResults.put(JSONObject().put("startMs",s.startMs).put("endMs",s.endMs).put("speakerId",s.speaker).put("text",text).put("blank",text.isBlank()).put("inferenceMs",inferenceMs).put("warnings",JSONArray(s.reasons)))
       ensureActive()
       if(text.isNotBlank()) segments+=Segment(startMs=s.startMs,endMs=s.endMs,speakerId=s.speaker,text=text,source=source,reasons=s.reasons)
      }
     } }
     val total=SystemClock.elapsedRealtime()-start
     val finalMemory=Debug.MemoryInfo();Debug.getMemoryInfo(finalMemory)
     diagnostic=JSONObject().put("finalPssKb",finalMemory.totalPss).put("peakMemory","N/A; stage boundary snapshots only").put("device","${Build.MANUFACTURER} ${Build.MODEL}").put("android",Build.VERSION.SDK_INT)
      .put("runtime","sherpa-onnx 2.0.1").put("backend",source).put("threads",threads).put("vadThreads",1).put("sampleRate",16000)
      .put("expectedSpeakers",rec.expectedSpeakers).put("clusterThreshold",AUTO_CLUSTER_THRESHOLD).put("vadThreshold",.5)
      .put("maxAsrSegmentMs",20000).put("audioMs",decoded.durationMs).put("totalMs",total).put("pipelineRtf",total.toDouble()/decoded.durationMs.coerceAtLeast(1))
      .put("pipelineTimingScope","validation through ASR release; persistenceMs and telemetry.elapsedMs reported separately")
      .put("asrStageRtf",(trace.times["asrMs"]?:0).toDouble()/decoded.durationMs.coerceAtLeast(1))
      .put("asrInferenceRtf",(trace.times["asrInferenceMs"]?:0).toDouble()/decoded.durationMs.coerceAtLeast(1))
      .put("runCondition","uncontrolled device caches/temperature; sequential ML stages; CPU provider")
      .put("diarizationTurns",JSONArray().also { a -> turns.forEach { t -> a.put(JSONObject().put("startMs",t.startMs).put("endMs",t.endMs).put("speakerId",t.speaker)) } })
      .put("clusteringMode",mode).put("clusterThresholdApplied",mode=="automatic").put("automaticValidation","not accepted on independent long Russian dialogue")
      .put("segmentationWindowShiftRatio",.1).put("diarMinDurationOnSec",.2).put("diarMinDurationOffSec",.5)
      .put("vadMinSpeechSec",.25).put("vadMinSilenceSec",.25).put("vadWindowSamples",512).put("vadMaxSpeechSec",20)
      .put("preRollMs",PRE_ROLL_MS).put("postRollMs",POST_ROLL_MS).put("vadSpans",spanJson(spans))
      .put("asrSpeechSpans",spanJson(boundedSpans)).put("asrSlices",sliceResults)
      .put("modelBytes",app.models.specifications().sumOf { app.models.file(it.path).length() })
     trace.measure("persistenceMs") { app.db.withTransaction {
      ensureActive();val current=dao.recording(recordingId)?:rec
      if(current.status=="CANCELLING") throw CancellationException("User requested cancellation")
      dao.complete(current.copy(status="READY",phase=if(segments.isEmpty()) "Речь не найдена" else "Готово",durationMs=decoded.durationMs,peaks=decoded.peaks.joinToString(","),diagnostics=diagnostic.toString(2)),segments.map { SegmentRow.from(recordingId,it) })
     } }
     // Only diagnostics are updated after commit; never replace a concurrently edited recording/segment.

    } catch(e: CancellationException) {
     withContext(NonCancellable) { dao.status(recordingId,"CANCELLED","Обработка отменена") }
     throw e
    } finally {
     withContext(NonCancellable) {
      runCatching { dao.diagnostics(recordingId,diagnostic.put("stagesMs",JSONObject(trace.times as Map<*,*>)).put("telemetry",trace.snapshot()).toString(2)) }
     }
    }
   }
   Result.success()
  } catch(e: CancellationException) { throw e }
   catch(e: OutOfMemoryError) { dao.status(recordingId,"ERROR","Не хватает памяти","Разделите аудио на части и повторите обработку");Result.failure() }
   catch(e: Throwable) { dao.status(recordingId,"ERROR","Обработка прервана",e.message?:e.javaClass.simpleName);Result.failure() }
   finally {
    trace.close();pcm.delete()
   }
 }
 private suspend fun phase(text: String) {
  currentCoroutineContext().ensureActive()
  app.db.withTransaction {
   if(dao.recording(recordingId)?.status=="CANCELLING") throw CancellationException("User requested cancellation")
   currentCoroutineContext().ensureActive();dao.status(recordingId,"PROCESSING",text)
  }
 }
 private fun spanJson(spans: List<Span>)=JSONArray().also { a -> spans.forEach { a.put(JSONObject().put("startMs",it.startMs).put("endMs",it.endMs)) } }
 companion object {
  const val PRE_ROLL_MS=100L
  const val POST_ROLL_MS=0L
  const val AUTO_CLUSTER_THRESHOLD=.5f
  fun diarizationConfig(models: ModelManager,count: Int,threads: Int=2): OfflineSpeakerDiarizationConfig {
   require(MlPolicy.mode(count)!="single") { "Single speaker must bypass diarization" }
   return OfflineSpeakerDiarizationConfig(
    segmentation=OfflineSpeakerSegmentationModelConfig(pyannote=OfflineSpeakerSegmentationPyannoteModelConfig(models.file("diar/segmentation.onnx").path,windowShiftRatio=.1f),numThreads=MlPolicy.threads(threads)),
    embedding=SpeakerEmbeddingExtractorConfig(model=models.file("diar/embedding.onnx").path,numThreads=threads),
    clustering=FastClusteringConfig(numClusters=count,threshold=AUTO_CLUSTER_THRESHOLD),minDurationOn=.2f,minDurationOff=.5f)
  }
  fun enqueue(context: Context,id: String,threads: Int=2) {
   val request=OneTimeWorkRequestBuilder<ProcessingWorker>().setInputData(workDataOf("recordingId" to id,"mlThreads" to MlPolicy.threads(threads))).addTag(id).build()
   WorkManager.getInstance(context).enqueueUniqueWork("replika-$id",ExistingWorkPolicy.KEEP,request)
  }
 }
}
