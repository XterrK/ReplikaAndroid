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
  val workerContext=currentCoroutineContext()
  var diagnostic=JSONObject()
  suspend fun guard(label: String) {
   trace.cool { phase("Android сообщил о сильном нагреве · ожидание охлаждения") }
   phase(label)
  }
  try {
   // Persisted requests without this key are always V1.6, even after a new APK changes defaults.
   val asrPlan=AsrPlan.fromPersistedId(inputData.getString(ASR_PLAN_KEY))
   val requestedDiarPlan=DiarizationPlan.fromPersistedId(inputData.getString(DIAR_PLAN_KEY))
   val collectWordEvidence=inputData.getBoolean(COLLECT_WORD_EVIDENCE_KEY,false)
   diagnostic.put("asrPlan",asrPlan.wireId).put("asrPolicy",asrPolicyJson(asrPlan))
    .put("diarizationPlanRequested",requestedDiarPlan.wireId)
    .put("wordEvidenceRequested",collectWordEvidence).put("wordEvidenceApplicable",asrPlan.wordTimestamps)
    .put("wordEvidenceLimitBytes",WORD_EVIDENCE_LIMIT_BYTES).put("wordEvidenceBytes",0L)
    .put("wordEvidenceTruncated",false)
   setForeground(getForegroundInfo())
   trace.measure("provisioningWaitMs") { app.bundledModels.awaitReady() }
   val gateStart=SystemClock.elapsedRealtime()
   app.models.gate.withLock {
    trace.times["nativeGateWaitMs"]=SystemClock.elapsedRealtime()-gateStart
    try {
     val rec=dao.recording(recordingId)?:return@withLock
     val mode=MlPolicy.mode(rec.expectedSpeakers)
     // Missing historical WorkData remains legacy. Manual K never enters the automatic refiner.
     val diarPlan=if(requestedDiarPlan.refined && mode=="automatic") requestedDiarPlan.forExpectedSpeakers(-1) else DiarizationPlan.LEGACY
     diarPlan.requirePairedAsr(asrPlan)
     diagnostic.put("diarizationPlan",diarPlan.wireId)
      .put("diarizationPolicy",DiarizationEvidence.jsonObject(diarizationPolicy(diarPlan)))
     // Historical rows keep their original source; reprocessing uses the packaged GigaAM.
     val backend=app.models.resolveBackend(rec.backend)
     val threads=MlPolicy.threads(inputData.getInt("mlThreads",2))
     guard("Проверка моделей")
     val start=SystemClock.elapsedRealtime()
     trace.measure("validationMs") { withContext(Dispatchers.IO) { app.models.requireReady(backend,mode!="single") } }
     guard("Подготовка · декодирование PCM 16 kHz")
     val decoded=trace.measure("decodeMs") { withContext(Dispatchers.IO) { AudioDecoder.decode(rec.audioPath,pcm) } }
     // Only extremely low-level input is boosted. Stored PCM and diarization stay original.
     val inputPeak=decoded.peaks.maxOrNull()?:0f
     val recognitionGain=QuietAudioGain.forPeak(inputPeak)
     trace.config(backend,threads,decoded.durationMs,mode)
     trace.measure("metadataPersistenceMs") { app.db.withTransaction {
      ensureActive();val current=dao.recording(recordingId)?:rec
      if(current.status=="CANCELLING") throw CancellationException("User requested cancellation")
      dao.insert(current.copy(status="PROCESSING",phase="VAD",durationMs=decoded.durationMs,peaks=decoded.peaks.joinToString(",")))
     } }
     guard("Поиск речи · Silero VAD")
     suspend fun detectSpeech(detectorGain: Float,label: String): List<Span> {
      val vad=trace.measure("vadLoadMs") { Vad(config=VadModelConfig(sileroVadModelConfig=SileroVadModelConfig(
       model=app.models.file("vad/silero_vad.onnx").path,threshold=asrPlan.vadThreshold,minSilenceDuration=asrPlan.vadMinSilenceSec,minSpeechDuration=asrPlan.vadMinSpeechSec,maxSpeechDuration=20f),numThreads=1)) }
      val found=mutableListOf<Span>()
      trace.measure("vadMs") {
       try {
        fun drain() { while(!vad.empty()) { val s=vad.front();found+=Span(s.start*1000/16000,(s.start+s.samples.size)*1000/16000);vad.pop() } }
        java.io.DataInputStream(pcm.inputStream().buffered()).use { input ->
         var read=0;var nextThermalCheck=16000
         while(read<decoded.samples) {
          ensureActive()
          if(read>=nextThermalCheck) {
           if(trace.cool { phase("Android сообщил о сильном нагреве · ожидание охлаждения") }>0) phase(label)
           nextThermalCheck=read+16000
          }
          val n=min(512,decoded.samples-read);val block=FloatArray(512)
          repeat(n) { block[it]=input.readFloat() };QuietAudioGain.apply(block,detectorGain);vad.acceptWaveform(block);read+=n;drain()
         }
        };vad.flush();drain()
       } finally { vad.release() }
      }
      return found
     }
     val primarySpans=detectSpeech(recognitionGain,"Поиск речи · Silero VAD")
     var spans=primarySpans
     var rescueRms: Double?=null
     var rescueRmsSamples=0L
     var rescueAttempted=false
     var rescueSpanCount=0
     var detectorGain=recognitionGain
     var rescueDecision=ZeroSpanVadRescue.decide(primarySpans.size,inputPeak,recognitionGain,null)
     // Ordinary nonempty VAD and digital silence skip even this additional disk scan.
     if(ZeroSpanVadRescue.needsRms(primarySpans.size,inputPeak,recognitionGain)) {
      guard("Проверяем тихую речь · Silero VAD")
      rescueRms=trace.measure("vadRescueRmsMs") {
       val rms=ZeroSpanVadRescue.RmsAccumulator()
       java.io.DataInputStream(pcm.inputStream().buffered()).use { input ->
        var read=0;var nextThermalCheck=16000
        while(read<decoded.samples) {
         ensureActive()
         if(read>=nextThermalCheck) {
          if(trace.cool { phase("Android сообщил о сильном нагреве · ожидание охлаждения") }>0) phase("Проверяем тихую речь · Silero VAD")
          nextThermalCheck=read+16000
         }
         val n=min(512,decoded.samples-read)
         repeat(n) { rms.add(input.readFloat()) };read+=n
        }
       }
       rescueRmsSamples=rms.samples;rms.value()
      }
      rescueDecision=ZeroSpanVadRescue.decide(primarySpans.size,inputPeak,recognitionGain,rescueRms)
      if(rescueDecision.shouldRetry) {
       guard("Повторный поиск тихой речи · Silero VAD")
       detectorGain=rescueDecision.detectorGain;rescueAttempted=true
       val rescued=trace.measure("vadRescuePassMs") { detectSpeech(detectorGain,"Повторный поиск тихой речи · Silero VAD") }
       rescueSpanCount=rescued.size
       if(rescued.isNotEmpty()) spans=rescued
      }
     }
     val rescueApplied=rescueAttempted && rescueSpanCount>0
     diagnostic.put("vadPrimarySpanCount",primarySpans.size).put("vadPrimarySpans",spanJson(primarySpans))
      .put("vadRescueAttempted",rescueAttempted).put("vadRescueApplied",rescueApplied)
      .put("vadDetectorGain",detectorGain).put("vadRescueRms",rescueRms?:JSONObject.NULL)
      .put("vadRescueRmsSamples",rescueRmsSamples).put("vadRescueSpanCount",rescueSpanCount)
      .put("vadRescueReason",if(rescueAttempted) { if(rescueApplied) "retry_applied" else "retry_empty" } else rescueDecision.reason)
      .put("vadRescueTargetRms",ZeroSpanVadRescue.TARGET_RMS).put("vadRescueMaxGain",ZeroSpanVadRescue.MAX_GAIN)
      .put("vadRescuePeakHeadroom",ZeroSpanVadRescue.PEAK_HEADROOM).put("vadRescueMinGainRatio",ZeroSpanVadRescue.MIN_GAIN_RATIO)
      .put("vadRescueScope","detector-only empty-primary retry; ASR input, original PCM and diarization unchanged")
     // Mode A never loads segmentation/embedding, nor allocates a full-recording float array.
     var rawDiarizationTurns=emptyList<Turn>()
     val nativeTurns=if(mode=="single") {
      trace.times["diarizationMs"]=0;trace.times["diarizationLoadMs"]=0;trace.times["diarizationInferenceMs"]=0
      listOf(Turn(0,decoded.durationMs,0))
     } else trace.measure("diarizationMs") {
      guard("Диаризация · Pyannote + 3D-Speaker")
      val required=decoded.samples.toLong()*4
      val available=Runtime.getRuntime().maxMemory()-(Runtime.getRuntime().totalMemory()-Runtime.getRuntime().freeMemory())
      require(required<available/2) { "Недостаточно памяти для диаризации этой записи. Выберите одного говорящего для монолога или разделите аудио." }
      val sd=trace.measure("diarizationLoadMs") { OfflineSpeakerDiarization(config=diarizationConfig(app.models,rec.expectedSpeakers,threads,diarPlan)) }
      try {
       val samples=trace.measure("diarizationReadMs") { AudioDecoder.read(pcm,0,decoded.samples) }
       guard("Диаризация · Pyannote + 3D-Speaker")
       val result=trace.measure("diarizationInferenceMs") { sd.process(samples) }
       ensureActive()
       rawDiarizationTurns=result.map { Turn((it.start*1000).roundToLong().coerceIn(0,decoded.durationMs),(it.end*1000).roundToLong().coerceIn(0,decoded.durationMs),it.speaker) }.filter { it.endMs>it.startMs }
       Alignment.stable(rawDiarizationTurns)
      } finally { sd.release() }
     }
     diagnostic.put("rawDiarizationTurns",turnJson(rawDiarizationTurns))
      .put("nativeDiarizationTurns",turnJson(nativeTurns))
      .put("diarizationRefinementApplicable",diarPlan.refined)
      .put("diarizationRefinementAccepted",false)
     val turns=if(!diarPlan.refined) nativeTurns else {
      // The original SD session above is released before the additional extractor opens.
      guard("Уточнение говорящих")
      val refined=trace.measure("diarizationRefinementMs") { DiarizationRefiner.refineOriginalPcm(
       turns=nativeTurns,durationMs=decoded.durationMs,modelPath=app.models.file(diarPlan.embeddingPath).path,
       threads=threads,config=diarPlan.windowConfig!!,collectEvidence=collectWordEvidence,
       isStopped={ this@ProcessingWorker.isStopped },
       readOriginalWindow={startMs,endMs -> withContext(Dispatchers.IO) {
        workerContext.ensureActive()
        val first=startMs*16L;val last=endMs*16L
        require(first>=0 && last>first && last<=decoded.samples.toLong() && last<=Int.MAX_VALUE.toLong())
        // Diarization always sees original PCM, never the temporary ASR/VAD gain.
        AudioDecoder.read(pcm,first.toInt(),(last-first).toInt()).also { workerContext.ensureActive() }
       } }) }
      check(refined.diagnostics["nativeResourcesReleasedBeforeRefiner"]==true) { "Не удалось освободить модель говорящих" }
      diagnostic.put("diarizationRefinementAccepted",refined.accepted)
       .put("diarizationRefinement",DiarizationEvidence.jsonObject(compactRefinerDiagnostic(refined.diagnostics)))
       .put("diarizationRefinementTimingsMs",DiarizationEvidence.jsonObject(refined.timingsMs))
       .put("diarizationEmbeddingCounts",JSONObject().put("plannedWindows",refined.counts.plannedWindows)
        .put("extractorLoads",refined.counts.extractorLoads).put("readWindows",refined.counts.readWindows)
        .put("createdStreams",refined.counts.createdStreams).put("releasedStreams",refined.counts.releasedStreams)
        .put("computeAttempts",refined.counts.computeAttempts).put("embeddingForwardCalls",refined.counts.embeddingForwardCalls)
        .put("measuredWindows",refined.counts.measuredWindows).put("embeddingDimension",refined.counts.embeddingDimension?:JSONObject.NULL))
      // Full vectors/tree are QA-only, bounded, and stored outside Room diagnostics.
      if(collectWordEvidence) {
       diagnostic.put("diarizationEvidenceRequested",true).put("diarizationEvidenceLimitBytes",8*1024*1024)
       try {
        val info=withContext(Dispatchers.IO) { DiarizationEvidence.write(
         directory=File(applicationContext.filesDir,"diarization-qa").apply {
          check(isDirectory || mkdirs()) { "Не удалось создать каталог QA" }
         },workId=id.toString(),recordingId=recordingId,
         metadata=linkedMapOf("audioMs" to decoded.durationMs,"sampleRate" to 16000,
          "inputAudioSha256" to fileSha256(File(rec.audioPath)),"diarizationPlan" to diarPlan.wireId,
          "diarizationPolicy" to diarizationPolicy(diarPlan),"runtime" to "sherpa-onnx 2.0.1",
          "embeddingSha256" to app.models.specifications().first { it.path==diarPlan.embeddingPath }.sha256,
          "rawDiarizationTurns" to turnMaps(rawDiarizationTurns),"nativeDiarizationTurns" to turnMaps(nativeTurns),
          "refinedDiarizationTurns" to turnMaps(refined.turns),"accepted" to refined.accepted),
         windows=refined.measuredWindowsQA.orEmpty(),diagnostics=refined.diagnostics) }
        diagnostic.put("diarizationEvidenceTruncated",info.truncated).put("diarizationEvidenceBytes",info.bytes)
         .put("diarizationEvidenceOmittedReason",info.reason?:JSONObject.NULL)
         .put("diarizationEvidenceFile",info.relativeFileName?.let { "diarization-qa/$it" }?:JSONObject.NULL)
         .put("diarizationEvidenceSha256",info.sha256?:JSONObject.NULL)
       } catch(cancelled: CancellationException) { throw cancelled }
        catch(failed: Exception) {
         // QA storage failure must not turn a useful production transcript into a failed job.
         diagnostic.put("diarizationEvidenceTruncated",true).put("diarizationEvidenceFile",JSONObject.NULL)
          .put("diarizationEvidenceOmittedReason",failed.javaClass.simpleName)
        }
      }
      refined.turns
     }
     if(asrPlan.wordTimestamps) guard("Планирование участков речи") else phase("Сопоставление временных интервалов")
     val preRollMs=if(asrPlan.wordTimestamps) asrPlan.preRollMs else PRE_ROLL_MS
     val boundedSpans=Alignment.context(spans,decoded.durationMs,preRollMs,POST_ROLL_MS)
     val slices=trace.measure("alignmentMs") {
      if(!asrPlan.wordTimestamps) RecognitionPlanner.plan(boundedSpans,turns)
      else withContext(Dispatchers.IO) {
       VadWordPlanner.planChunks(boundedSpans,energy={startMs,endMs ->
        workerContext.ensureActive()
        require(startMs>=0 && endMs>startMs && endMs<=decoded.durationMs) { "Energy window exceeds decoded audio" }
        val first=startMs*16L;val last=endMs*16L
        require(first>=0 && last<=decoded.samples.toLong() && last>first && last<=Int.MAX_VALUE.toLong())
        val block=AudioDecoder.read(pcm,first.toInt(),(last-first).toInt())
        var squares=0.0
        for(sample in block) { val value=sample.toDouble();squares+=value*value }
        workerContext.ensureActive()
        squares/block.size
       }).map { Slice(it.startMs,it.endMs,-1,emptyList()) }
      }
     }
     val sliceResults=JSONArray();val segments=mutableListOf<Segment>()
     var fallbackChunks=0;var wordProcessedChunks=0;var wordEvidenceBytes=0L;var wordEvidenceTruncated=false
     val verifiedFrameStrideMs=if(backend=="giga-v3") 40L else 0L
     diagnostic.put("asrChunks",spanJson(slices.map { Span(it.startMs,it.endMs) }))
      .put("turnsUsedForAsrSlicing",!asrPlan.wordTimestamps)
      .put("wordAssignmentSupported",asrPlan.wordTimestamps && verifiedFrameStrideMs>0)
      .put("wordProcessedChunks",0).put("fallbackChunks",0)
      .put("wordTimestampScope",if(asrPlan.wordTimestamps)
       "Token-emission proxies; pinned GigaAM v3 stride 40ms; not forced alignment or calibrated confidence"
       else "Legacy V1.6 ASR segment intervals; word assignment not requested")
     if(asrPlan.wordTimestamps) {
      // Keep partial QA evidence on cancellation without publishing a partial transcript as READY.
      diagnostic.put("asrSlices",sliceResults).put("energyWindowMs",40).put("energySearchMs",4000)
       .put("energyMetric","sequential Double mean-square of original decoded Float32 PCM")
       .put("fallbackPolicy","Full actual ASR chunk with unknown speaker and warning; no fabricated word times or second ASR pass")
       .put("wordEvidenceBudgetScope","Conservative additional pretty-JSON UTF-8 payload bytes, including nesting allowance; summaries excluded")
     }
     val engine=if(slices.isEmpty()) {
      // Silence/no-speech does not need a 230 MB recognizer. Preserve attribution and Room semantics.
      trace.times["asrLoadMs"]=0;trace.times["asrInferenceMs"]=0;null
     } else {
      guard("Загрузка модели распознавания")
      trace.measure("asrLoadMs") { GigaAmEngine(app.models,threads) }
     }
     val source=engine?.source?:GigaAmEngine.sourceForModel(backend)
     trace.measure("asrMs") { engine?.use { activeEngine ->
      if(!asrPlan.wordTimestamps) {
      for((i,s) in slices.withIndex()) {
       ensureActive();guard("Распознавание · ${source.substringBefore(" /")} · ${i+1}/${slices.size}")
       val a=(s.startMs*16).toInt();val b=min((s.endMs*16).toInt(),decoded.samples)
       val samples=trace.measure("asrReadMs") { AudioDecoder.read(pcm,a,(b-a).coerceAtLeast(0)) }
       QuietAudioGain.apply(samples,recognitionGain)
       val inferenceStart=SystemClock.elapsedRealtime()
       val text=trace.measure("asrInferenceMs") { activeEngine.recognize(samples) }
       val inferenceMs=SystemClock.elapsedRealtime()-inferenceStart
       // Private Room diagnostics may contain hypotheses; they are NEVER passed to Logcat.
       sliceResults.put(JSONObject().put("startMs",s.startMs).put("endMs",s.endMs).put("speakerId",s.speaker).put("text",text).put("blank",text.isBlank()).put("inferenceMs",inferenceMs).put("warnings",JSONArray(s.reasons)))
       ensureActive()
       if(text.isNotBlank()) segments+=Segment(startMs=s.startMs,endMs=s.endMs,speakerId=s.speaker,text=text,source=source,reasons=s.reasons)
      }
      } else {
       for((i,s) in slices.withIndex()) {
        ensureActive();guard("Распознавание · ${source.substringBefore(" /")} · ${i+1}/${slices.size}")
        val first=s.startMs*16L;val last=minOf(s.endMs*16L,decoded.samples.toLong())
        require(first>=0 && last>=first && last<=Int.MAX_VALUE.toLong())
        val samples=trace.measure("asrReadMs") { AudioDecoder.read(pcm,first.toInt(),(last-first).toInt()) }
        QuietAudioGain.apply(samples,recognitionGain)
        val inferenceStart=SystemClock.elapsedRealtime()
        // One recognizer pass. An unsupported word projection reuses this exact returned text.
        val hypothesis=trace.measure("asrInferenceMs") { activeEngine.recognizeDetailed(samples) }
        val inferenceMs=SystemClock.elapsedRealtime()-inferenceStart
        ensureActive()
        val (parsed,assigned,chunkSegments)=trace.measure("wordAssignmentMs") {
         val parsed=VadWordPlanner.words(hypothesis.text,hypothesis.tokens,hypothesis.timestampsSeconds,
          Span(s.startMs,s.endMs),hypothesis.frameStrideMs)
         val assigned=if(parsed.supported) VadWordPlanner.assignWords(parsed.words,turns) else emptyList()
         val grouped=if(parsed.supported) VadWordPlanner.groupWords(assigned,source,asrPlan.seamPunctuation)
          else if(hypothesis.text.isNotBlank()) listOf(Segment(startMs=s.startMs,endMs=s.endMs,
           speakerId=-1,text=hypothesis.text,source=source,reasons=listOf(WORD_FALLBACK_WARNING))) else emptyList()
         Triple(parsed,assigned,grouped)
        }
        ensureActive()
        if(!parsed.supported && hypothesis.text.isNotBlank()) fallbackChunks++
        wordProcessedChunks++
        // Summary fields remain small in production. Full token/word arrays are explicit QA only.
        val summary=JSONObject().put("startMs",s.startMs).put("endMs",s.endMs).put("speakerId",-1)
         .put("text",hypothesis.text).put("blank",hypothesis.text.isBlank()).put("inferenceMs",inferenceMs)
         .put("tokenCount",hypothesis.tokens.size).put("timestampCount",hypothesis.timestampsSeconds.size)
         .put("wordCount",assigned.size).put("frameStrideMs",hypothesis.frameStrideMs)
         .put("wordAssignmentSupported",parsed.supported).put("wordAssignmentReason",parsed.reason)
         .put("timestampUnit","seconds within ASR VAD chunk")
         .put("warnings",JSONArray(if(parsed.supported) emptyList<String>() else listOf(WORD_FALLBACK_WARNING)))
         .put("wordEvidenceIncluded",false)
        when {
         !collectWordEvidence -> summary.put("wordEvidenceOmittedReason","not_requested")
         wordEvidenceTruncated -> summary.put("wordEvidenceOmittedReason","budget_exceeded")
         else -> {
          val payload=wordEvidenceJson(hypothesis,assigned)
          val payloadBytes=conservativeWordEvidenceBytes(payload)
          if(payloadBytes<=WORD_EVIDENCE_LIMIT_BYTES.toLong()-wordEvidenceBytes) {
           for(key in payload.keys()) summary.put(key,payload.get(key))
           wordEvidenceBytes+=payloadBytes
           summary.put("wordEvidenceIncluded",true)
          } else {
           wordEvidenceTruncated=true
           summary.put("wordEvidenceOmittedReason","budget_exceeded")
          }
         }
        }
        sliceResults.put(summary)
        diagnostic.put("wordAssignmentSupported",verifiedFrameStrideMs>0 && fallbackChunks==0)
         .put("wordProcessedChunks",wordProcessedChunks).put("fallbackChunks",fallbackChunks)
         .put("wordEvidenceBytes",wordEvidenceBytes).put("wordEvidenceTruncated",wordEvidenceTruncated)
        ensureActive()
        segments+=chunkSegments
       }
      }
     } }
     val total=SystemClock.elapsedRealtime()-start
     val finalMemory=Debug.MemoryInfo();Debug.getMemoryInfo(finalMemory)
     diagnostic=diagnostic.put("finalPssKb",finalMemory.totalPss).put("peakMemory","N/A; stage boundary snapshots only").put("device","${Build.MANUFACTURER} ${Build.MODEL}").put("android",Build.VERSION.SDK_INT)
      .put("runtime","sherpa-onnx 2.0.1").put("backend",source).put("threads",threads).put("vadThreads",1).put("sampleRate",16000)
      .put("originalPcmPeak",inputPeak).put("recognitionInputGain",recognitionGain)
      .put("quietGainTriggerPeak",QuietAudioGain.TRIGGER_PEAK).put("quietGainMax",QuietAudioGain.MAX_GAIN)
      .put("quietGainScope","temporary VAD and ASR arrays only; original PCM/playback/diarization preserved")
      .put("expectedSpeakers",rec.expectedSpeakers).put("clusterThreshold",diarPlan.clusterThreshold.toDouble()).put("vadThreshold",asrPlan.vadThreshold.toDouble())
      .put("maxAsrSegmentMs",20000).put("audioMs",decoded.durationMs).put("totalMs",total).put("pipelineRtf",total.toDouble()/decoded.durationMs.coerceAtLeast(1))
      .put("pipelineTimingScope","validation through ASR release; persistenceMs and telemetry.elapsedMs reported separately")
      .put("asrStageRtf",(trace.times["asrMs"]?:0).toDouble()/decoded.durationMs.coerceAtLeast(1))
      .put("asrInferenceRtf",(trace.times["asrInferenceMs"]?:0).toDouble()/decoded.durationMs.coerceAtLeast(1))
      .put("runCondition","uncontrolled device caches/temperature; sequential ML stages; CPU provider")
      .put("diarizationTurns",JSONArray().also { a -> turns.forEach { t -> a.put(JSONObject().put("startMs",t.startMs).put("endMs",t.endMs).put("speakerId",t.speaker)) } })
      .put("clusteringMode",mode).put("clusterThresholdApplied",mode=="automatic").put("automaticValidation","not accepted on independent long Russian dialogue")
      .put("segmentationWindowShiftRatio",diarPlan.segmentationWindowShiftRatio.toDouble())
      .put("diarMinDurationOnSec",diarPlan.diarMinDurationOnSec.toDouble()).put("diarMinDurationOffSec",diarPlan.diarMinDurationOffSec.toDouble())
      .put("vadMinSpeechSec",asrPlan.vadMinSpeechSec.toDouble()).put("vadMinSilenceSec",asrPlan.vadMinSilenceSec.toDouble()).put("vadWindowSamples",512).put("vadMaxSpeechSec",20)
      .put("preRollMs",preRollMs).put("postRollMs",POST_ROLL_MS).put("vadSpans",spanJson(spans))
      .put("asrSpeechSpans",spanJson(boundedSpans)).put("asrSlices",sliceResults)
      .put("modelBytes",app.models.specifications().sumOf { app.models.file(it.path).length() })
     trace.measure("persistenceMs") { app.db.withTransaction {
      ensureActive();val current=dao.recording(recordingId)?:rec
      if(current.status=="CANCELLING") throw CancellationException("User requested cancellation")
      dao.complete(current.copy(backend=backend,status="READY",phase=if(segments.isEmpty()) "Речь не найдена" else "Готово",durationMs=decoded.durationMs,peaks=decoded.peaks.joinToString(","),diagnostics=diagnostic.toString(2)),segments.map { SegmentRow.from(recordingId,it) })
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
 private fun turnMaps(turns: List<Turn>)=turns.map { linkedMapOf<String,Any?>("startMs" to it.startMs,"endMs" to it.endMs,"speakerId" to it.speaker) }
 private fun turnJson(turns: List<Turn>)=JSONArray().also { a -> turns.forEach { a.put(JSONObject().put("startMs",it.startMs).put("endMs",it.endMs).put("speakerId",it.speaker)) } }
 private fun compactRefinerDiagnostic(values: Map<String,Any?>): Map<String,Any?> = values.mapNotNull { (key,value) ->
  when {
   key=="config" -> key to value
   key=="refiner" && value is Map<*,*> -> key to compactRefinerDiagnostic(value.entries.associate { it.key.toString() to it.value })
   value==null || value is String || value is Number || value is Boolean -> key to value
   else -> null
  }
 }.toMap()
 private fun fileSha256(file: File): String {
  val hash=java.security.MessageDigest.getInstance("SHA-256")
  file.inputStream().buffered().use { input -> val block=ByteArray(128*1024);while(true) { val read=input.read(block);if(read<0) break;hash.update(block,0,read) } }
  return hash.digest().joinToString("") { "%02x".format(it) }
 }
 private fun wordEvidenceJson(hypothesis: AsrHypothesis,words: List<VadWordPlanner.AssignedWord>): JSONObject {
  val timestamps=JSONArray()
  var nonfinite=false
  for(value in hypothesis.timestampsSeconds) {
   if(value.isFinite()) timestamps.put(value.toDouble()) else { timestamps.put(JSONObject.NULL);nonfinite=true }
  }
  val result=JSONObject().put("tokens",JSONArray(hypothesis.tokens)).put("timestamps",timestamps)
   .put("words",JSONArray().also { rows -> words.forEach { word -> rows.put(JSONObject()
    .put("startMs",word.startMs).put("endMs",word.endMs).put("text",word.text)
    .put("speakerId",word.speaker).put("warnings",JSONArray(word.reasons))) } })
  if(nonfinite) result.put("timestampRawBits",JSONArray(hypothesis.timestampsSeconds.map { it.toRawBits() }))
  return result
 }
 private fun conservativeWordEvidenceBytes(payload: JSONObject): Long {
  val encoded=payload.toString(2)
  // Evidence fields are merged into one asrSlices item (at most six extra indentation spaces).
  // Eight spaces per line and a fixed framing reserve bound additional serialized UTF-8 size.
  return encoded.toByteArray(Charsets.UTF_8).size.toLong()+(encoded.count { it=='\n' }+1L)*8L+128L
 }
 companion object {
  const val ASR_PLAN_KEY="asrPlan"
  const val DIAR_PLAN_KEY="diarizationPlan"
  const val COLLECT_WORD_EVIDENCE_KEY="collectWordEvidence"
  const val WORD_EVIDENCE_LIMIT_BYTES=256*1024
  const val WORD_FALLBACK_WARNING="Время слов недоступно: проверьте говорящего и границы"
  const val PRE_ROLL_MS=100L
  const val POST_ROLL_MS=0L
  const val AUTO_CLUSTER_THRESHOLD=.5f
  fun diarizationConfig(models: ModelManager,count: Int,threads: Int=2,plan: DiarizationPlan=DiarizationPlan.LEGACY): OfflineSpeakerDiarizationConfig {
   require(MlPolicy.mode(count)!="single") { "Single speaker must bypass diarization" }
   return OfflineSpeakerDiarizationConfig(
    segmentation=OfflineSpeakerSegmentationModelConfig(pyannote=OfflineSpeakerSegmentationPyannoteModelConfig(models.file(plan.segmentationPath).path,windowShiftRatio=plan.segmentationWindowShiftRatio),numThreads=MlPolicy.threads(threads)),
    embedding=SpeakerEmbeddingExtractorConfig(model=models.file(plan.embeddingPath).path,numThreads=threads),
    clustering=FastClusteringConfig(numClusters=count,threshold=plan.clusterThreshold),minDurationOn=plan.diarMinDurationOnSec,minDurationOff=plan.diarMinDurationOffSec)
  }
  fun diarizationPolicy(plan: DiarizationPlan): Map<String,Any?> = linkedMapOf("plan" to plan.wireId,
   "algorithm" to if(plan.refined) "window-overcluster-v1" else "legacy-v16",
   "embedding_path" to plan.embeddingPath,"native_threshold" to plan.clusterThreshold.toDouble(),
   "window_shift" to plan.segmentationWindowShiftRatio.toDouble(),"min_duration_on" to plan.diarMinDurationOnSec.toDouble(),
   "min_duration_off" to plan.diarMinDurationOffSec.toDouble(),"window_config" to plan.windowConfig?.asMap())
  fun asrPolicyJson(plan: AsrPlan): JSONObject = JSONObject().put("pipeline",plan.pipeline)
   .put("punctuation_mode",plan.punctuationMode).put("energy_split",plan.wordTimestamps)
   .put("vad_threshold",plan.vadThreshold.toDouble()).put("vad_min_speech_sec",plan.vadMinSpeechSec.toDouble())
   .put("vad_min_silence_sec",plan.vadMinSilenceSec.toDouble()).put("pre_roll_ms",plan.preRollMs)
  fun enqueue(context: Context,id: String,threads: Int=2,
   asrPlan: AsrPlan=AsrPlan.fromPersistedId(BuildConfig.DEFAULT_ASR_PLAN),collectWordEvidence: Boolean=false,
   diarizationPlan: DiarizationPlan=DiarizationPlan.fromPersistedId(BuildConfig.DEFAULT_DIAR_PLAN)) {
   val request=OneTimeWorkRequestBuilder<ProcessingWorker>().setInputData(workDataOf("recordingId" to id,
    "mlThreads" to MlPolicy.threads(threads),ASR_PLAN_KEY to asrPlan.wireId,
    COLLECT_WORD_EVIDENCE_KEY to collectWordEvidence,DIAR_PLAN_KEY to diarizationPlan.wireId)).addTag(id).build()
   WorkManager.getInstance(context).enqueueUniqueWork("replika-$id",ExistingWorkPolicy.KEEP,request)
  }
 }
}
