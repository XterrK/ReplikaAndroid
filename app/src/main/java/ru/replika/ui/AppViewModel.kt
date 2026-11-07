package ru.replika.ui

import android.app.Application
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import androidx.lifecycle.*
import androidx.work.WorkManager
import androidx.room.withTransaction
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.sync.withLock
import ru.replika.ReplikaApp
import ru.replika.BuildConfig
import ru.replika.data.*
import ru.replika.ml.*
import ru.replika.domain.ProductErrors
import java.util.concurrent.TimeUnit
import java.io.File
import java.util.UUID

data class LibraryState(val loaded: Boolean = false,val records: List<Recording> = emptyList())
data class TranscriptState(val recordingId: String? = null,val loaded: Boolean = false,val rows: List<SegmentRow> = emptyList(),val speakers: List<SpeakerRow> = emptyList(),val recordingStatus: String? = null)

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class AppViewModel(application: Application): AndroidViewModel(application) {
 private val app=application as ReplikaApp
 val dao=app.db.dao()
 private val appearance=AppearancePreferences(app)
 val themeMode=appearance.mode.stateIn(viewModelScope,SharingStarted.Eagerly,ThemeMode.SYSTEM)
 fun selectTheme(mode: ThemeMode) { viewModelScope.launch { try { appearance.select(mode) } catch(e: Exception) { reportError("Сохранение темы",e) } } }
 val library=MutableStateFlow(LibraryState())
 val recordings=library.map { it.records }.stateIn(viewModelScope,SharingStarted.Eagerly,emptyList())
 val recordingsLoaded=library.map { it.loaded }.stateIn(viewModelScope,SharingStarted.Eagerly,false)
 val error=MutableStateFlow<String?>(null)
 val notice=MutableStateFlow<String?>(null)
 val technicalError=MutableStateFlow<String?>(null)
 val undoAvailable=MutableStateFlow(false)
 val deleting=MutableStateFlow<Set<String>>(emptySet())
 val selected=MutableStateFlow<String?>(null)
 private val transcriptRows=selected.flatMapLatest { id ->
  if(id==null) flowOf(TranscriptState()) else dao.transcriptSnapshot(id).map { snapshot ->
   TranscriptState(id,true,snapshot?.rows.orEmpty().sortedWith(compareBy<SegmentRow> { it.startMs }.thenBy { it.endMs }),snapshot?.speakers.orEmpty(),snapshot?.recording?.status)
  }.onStart { emit(TranscriptState(recordingId=id)) }
 }
 val transcript=combine(transcriptRows,library) { state,collection ->
  val status=collection.records.firstOrNull { it.id==state.recordingId }?.status
  state.copy(loaded=state.loaded && collection.loaded && status==state.recordingStatus)
 }.stateIn(viewModelScope,SharingStarted.Eagerly,TranscriptState())
 val segments=transcript.map { it.rows }.stateIn(viewModelScope,SharingStarted.Eagerly,emptyList())
 val speakers=transcript.map { it.speakers }.stateIn(viewModelScope,SharingStarted.Eagerly,emptyList())
 private val storage=ProductStorage(app.db,File(app.filesDir,"audio"))
 private var lastEdit: SegmentUndo?=null
 private val errorLogGate=kotlinx.coroutines.sync.Mutex()
 val models=MutableStateFlow<List<ModelStatus>>(emptyList())
 val backend=MutableStateFlow(app.models.resolveBackend(app.getSharedPreferences("settings",0).getString("backend",null)))
 fun selectBackend(id: String) { val current=app.models.resolveBackend(id);backend.value=current;app.getSharedPreferences("settings",0).edit().putString("backend",current).apply() }
 val importProgress=MutableStateFlow<String?>(null)
 private var importJob: Job?=null
 fun cancelImport() { importJob?.cancel() }
 val modelProgress=MutableStateFlow<String?>(null)
 private var modelJob: Job?=null
 private var recorder: MediaRecorder?=null
 private var recordingFile: File?=null
 val isRecording=MutableStateFlow(false)
 val paused=MutableStateFlow(false)
 val elapsed=MutableStateFlow(0L)
 val levels=MutableStateFlow<List<Float>>(emptyList())
 val voiceLevel=MutableStateFlow(0f)
 val recordingPhase=MutableStateFlow(RecordingPhase.IDLE)
 private val envelope=VoiceEnvelope()
 private var stopAfterStart: Boolean?=null
 private var pauseAfterStart=false
 fun onRecordingBackgrounded() { if(recordingPhase.value==RecordingPhase.STARTING) pauseAfterStart=true else if(isRecording.value && !paused.value) pauseRecording() }
 fun requireMicrophonePermission() { if(!isRecording.value) recordingPhase.value=RecordingPhase.PERMISSION_REQUIRED }
 private var meterJob: Job?=null
 private val processingRequests=mutableSetOf<String>()
 private val cancellingRequests=mutableSetOf<String>()
 init {
  selectBackend(backend.value) // Migrate retired backend preferences without rewriting historical transcripts.
  viewModelScope.launch(Dispatchers.IO) { runCatching { app.models.gate.withLock { app.models.removeRetiredWhisperFiles() } } }
  refreshModels()
  viewModelScope.launch(Dispatchers.IO) { app.importJournal.recover(dao::audioPathsReferenced) }
  viewModelScope.launch {
   dao.recordings().collect { rows -> library.value=LibraryState(true,rows) }
  }
  viewModelScope.launch {
   selected.collect { id -> if(lastEdit?.before?.recordingId!=id) clearUndo() }
  }
  viewModelScope.launch(Dispatchers.IO) {
   runCatching { File(app.filesDir,"diagnostics/last-ui-error.json").takeIf { it.isFile }?.readText() }.getOrNull()?.let { technicalError.compareAndSet(null,it) }
   runCatching { app.models.gate.withLock { storage.recoverPendingDeletions() } }.onFailure { if(it is CancellationException) throw it else reportError("Восстановление аудио",ProductOperationException("Не удалось завершить восстановление аудио. Файлы сохранены в приложении; перезапустите его и повторите действие.","Pending audio recovery failed",it)) }
  }
  viewModelScope.launch {
   while(isActive) {
    runCatching { reconcileProcessing() }.onFailure { if(it is CancellationException) throw it }
    delay(2000)
   }
  }
 }
 /** Repair persisted progress after process death or cancellation of a queued WorkRequest. */
 internal suspend fun reconcileProcessing() {
  val manager=WorkManager.getInstance(app)
  for(rec in dao.recordings().first().filter { it.status in setOf("QUEUED","PROCESSING","CANCELLING") }) {
   if(rec.id in processingRequests || rec.id in cancellingRequests) continue
   val work=withContext(Dispatchers.IO) { manager.getWorkInfosForUniqueWork("replika-${rec.id}").get() }
   if(work.any { !it.state.isFinished }) continue
   // A CANCELLED WorkInfo can coexist with a still-returning JNI call in this process.
   app.models.gate.withLock {
    if(rec.id in processingRequests || rec.id in cancellingRequests) return@withLock
    val latestWork=withContext(Dispatchers.IO) { manager.getWorkInfosForUniqueWork("replika-${rec.id}").get() }
    if(latestWork.any { !it.state.isFinished }) return@withLock
    app.db.withTransaction {
     val current=dao.recording(rec.id)?:return@withTransaction
     if(current.status !in setOf("QUEUED","PROCESSING","CANCELLING")) return@withTransaction
     if(current.status=="CANCELLING" || latestWork.any { it.state==androidx.work.WorkInfo.State.CANCELLED }) {
      dao.status(rec.id,"CANCELLED","Обработка отменена")
     } else {
      dao.status(rec.id,"ERROR","Обработка прервана","Фоновое задание завершилось без результата. Исходное аудио и сохранённые исправления доступны; повторите обработку.")
     }
    }
   }
  }
 }
 fun refreshModels() { viewModelScope.launch(Dispatchers.IO) { runCatching { app.models.statuses() }.onSuccess { models.value=it }.onFailure { reportError("Проверка моделей",it) } } }
 /** Audio and video share the platform document picker; heavy recognition starts only on explicit request. */
 fun importAudio(uri: Uri) {
  if(importJob?.isActive==true) return
  importProgress.value="Открытие файла…"
  importJob=viewModelScope.launch {
   val id=UUID.randomUUID().toString();val folder=File(app.filesDir,"audio")
   try {
    val imported=app.importJournal.runImport(id,dao::audioPathsReferenced) {
     val result=MediaImporter(app).importMedia(uri,folder,id) { importProgress.value=it }
     ensureActive()
     dao.insert(Recording(id,result.title,result.file.path,durationMs=result.durationMs,backend=backend.value))
     result
    }
    selected.value=id
    if(imported.audioTrackCount>1) notice.value="В файле ${imported.audioTrackCount} звуковые дорожки. Импортирована основная дорожка; если основная не указана — первая."
    else if(imported.fromVideo) notice.value="Звук из видео готов к расшифровке. Исходное видео сохранено."
   } catch(e: Throwable) {
    if(e is CancellationException) { notice.value="Импорт отменён";throw e }
    if(e is Exception) reportError("Импорт аудио и видео",e) else throw e
   } finally { importProgress.value=null }
  }
 }

 fun process(id: String,count: Int,threads: Int=if(BuildConfig.DEFAULT_CPU_PLAN=="auto_v1") 0 else 2) {
  if(id in deleting.value || !processingRequests.add(id)) return
  viewModelScope.launch {
   try {
    if(threads==0) require(ru.replika.domain.CpuPlan.fromPersistedId(BuildConfig.DEFAULT_CPU_PLAN)==ru.replika.domain.CpuPlan.AUTO_V1)
    else ru.replika.domain.MlPolicy.threads(threads)
    if(count!=-1 && count !in 1..20) throw ProductOperationException("Укажите от 1 до 20 говорящих.","Invalid speaker count $count")
    val queued=app.db.withTransaction {
     val rec=dao.recording(id)?:return@withTransaction false
     if(rec.status in setOf("QUEUED","PROCESSING","CANCELLING")) return@withTransaction false
     dao.insert(rec.copy(expectedSpeakers=count,backend=backend.value,status="QUEUED",phase="Ожидание обработки",error=null))
     true
    }
    if(queued) { clearUndo();ProcessingWorker.enqueue(app,id,threads.takeUnless { it==0 }) }
   } catch(e: CancellationException) { throw e } catch(e: Exception) { reportError("Запуск обработки",e) }
   finally { processingRequests.remove(id) }
  }
 }
 fun cancel(id: String) {
  if(!cancellingRequests.add(id)) return
  viewModelScope.launch {
   try {
    val requested=app.db.withTransaction {
     val rec=dao.recording(id)?:return@withTransaction false
     if(rec.status !in setOf("QUEUED","PROCESSING","CANCELLING")) return@withTransaction false
     dao.status(id,"CANCELLING","Отмена запрошена · завершаем текущую операцию")
     true
    }
    if(!requested) return@launch
    withContext(Dispatchers.IO) { WorkManager.getInstance(app).cancelAllWorkByTag(id).result.get() }
    // WorkManager cancellation acknowledges the request before JNI necessarily returns.
    // Wait for the shared native gate before enabling a retry, including cancelled queued jobs.
    app.models.gate.withLock {
     app.db.withTransaction {
      if(dao.recording(id)?.status=="CANCELLING") dao.status(id,"CANCELLED","Обработка отменена")
     }
    }
   } catch(e: CancellationException) { throw e } catch(e: Exception) { reportError("Отмена обработки",e) }
   finally { cancellingRequests.remove(id) }
  }
 }
 fun clearNotice() { notice.value=null }
 private fun clearUndo() { lastEdit=null;undoAvailable.value=false }
 fun edit(row: SegmentRow,text: String,speaker: Int,reviewed: Boolean,onComplete: (Boolean)->Unit = {}) { viewModelScope.launch {
  clearUndo()
  try {
   if(row.recordingId in deleting.value) throw ProductOperationException("Запись удаляется. Дождитесь завершения действия.","Edit during deletion")
   val change=storage.edit(row,text,speaker,reviewed)
   lastEdit=change.takeIf { it.before!=it.after };undoAvailable.value=lastEdit!=null
   notice.value="Изменения сохранены";onComplete(true)
  } catch(e: CancellationException) { throw e } catch(e: Exception) { reportError("Сохранение фрагмента",e);onComplete(false) }
 } }
 fun undoLastEdit(onComplete: (Boolean)->Unit = {}) { viewModelScope.launch {
  val change=lastEdit
  if(change==null) { onComplete(false);return@launch }
  try {
   storage.undo(change);clearUndo();notice.value="Последнее исправление отменено";onComplete(true)
  } catch(e: CancellationException) { throw e } catch(e: Exception) { clearUndo();reportError("Отмена исправления",e);onComplete(false) }
 } }
 fun rename(id: String,speaker: Int,name: String) { viewModelScope.launch {
  clearUndo()
  try {
   app.db.withTransaction {
    if(dao.recording(id)==null || id in deleting.value) throw ProductOperationException("Запись больше недоступна.","Rename unavailable recording $id")
    dao.speaker(SpeakerRow(id,speaker,name.trim().ifBlank { if(speaker<0) "Неизвестный" else "Участник ${speaker+1}" }))
   }
   clearUndo();notice.value="Имя участника сохранено"
  } catch(e: CancellationException) { throw e } catch(e: Exception) { reportError("Переименование участника",e) }
 } }
 fun title(id: String,title: String) { viewModelScope.launch {
  clearUndo()
  try {
   app.db.withTransaction {
    val row=dao.recording(id)?:throw ProductOperationException("Запись больше недоступна.","Rename unavailable recording $id")
    if(id in deleting.value) throw ProductOperationException("Запись удаляется.","Rename during deletion")
    dao.insert(row.copy(title=title.trim().ifBlank { row.title }))
   }
   clearUndo();notice.value="Название сохранено"
  } catch(e: CancellationException) { throw e } catch(e: Exception) { reportError("Переименование записи",e) }
 } }
 fun deleteRecording(id: String,onComplete: (Boolean)->Unit = {}) {
  if(id in deleting.value) { onComplete(false);return }
  clearUndo();deleting.value=deleting.value+id
  viewModelScope.launch {
   try {
    val rec=dao.recording(id)?:throw ProductOperationException("Запись уже удалена.","Missing recording $id")
    if(rec.status in setOf("QUEUED","PROCESSING","CANCELLING") || id in processingRequests || id in cancellingRequests) throw ProductOperationException("Сначала отмените обработку и дождитесь её завершения.","Delete busy recording $id")
    val result=app.models.gate.withLock {
     val work=withContext(Dispatchers.IO) { WorkManager.getInstance(app).getWorkInfosForUniqueWork("replika-$id").get(10,TimeUnit.SECONDS) }
     if(work.any { !it.state.isFinished }) throw ProductOperationException("Фоновая обработка ещё не завершена. Отмените её или повторите удаление позже.","Delete with active WorkRequest for $id")
     storage.deleteRecording(id)
    }
    clearUndo();if(selected.value==id) selected.value=null
    notice.value=when {
     result.cleanupPending -> "Запись удалена. Очистка локального аудио пока не завершена."
     result.audioPreserved -> "Запись удалена. Общие и внешние аудиофайлы не затронуты."
     else -> "Запись и локальное аудио удалены"
    }
    if(result.cleanupPending) reportTechnicalError("Очистка удалённого аудио",id,java.io.IOException("Owned audio cleanup is pending"),showUserMessage=false)
    onComplete(true)
   } catch(e: CancellationException) { throw e } catch(e: Exception) { reportError("Удаление записи",e);onComplete(false) }
   finally { deleting.value=deleting.value-id }
  }
 }
 fun errorMessage(context: String,detail: String?): String = ProductErrors.message(context,detail)
 fun reportError(context: String,error: Throwable) { reportTechnicalError(context,null,error) }
 fun reportPlaybackError(id: String,error: Throwable) { reportTechnicalError("Воспроизведение",id,error) }
 private fun reportTechnicalError(context: String,recordingId: String?,cause: Throwable,showUserMessage: Boolean = true) {
  val friendly=if(cause is ProductOperationException) cause.userMessage else ProductErrors.fromThrowable(context,cause)
  if(showUserMessage) error.value=friendly
  val data=org.json.JSONObject().put("atMs",System.currentTimeMillis()).put("context",context).put("recordingId",recordingId?:org.json.JSONObject.NULL)
   .put("exceptionClass",cause.javaClass.name).put("message",cause.message?:org.json.JSONObject.NULL).put("stackTrace",cause.stackTraceToString())
  if(cause is androidx.media3.common.PlaybackException) data.put("playbackErrorCode",cause.errorCode)
  val raw=data.toString(2);technicalError.value=raw
  viewModelScope.launch(Dispatchers.IO) {
   errorLogGate.withLock {
   if(technicalError.value!=raw) return@withLock
   runCatching {
    val folder=File(app.filesDir,"diagnostics").apply { mkdirs() }
    val temporary=File(folder,"last-ui-error.json.part");temporary.writeText(raw)
    check(temporary.renameTo(File(folder,"last-ui-error.json")))
   }
   }
  }
 }
 fun download(id: String) { modelOperation { app.models.download(id) { modelProgress.value=it } } }
 fun deleteModel(id: String) { modelOperation { app.models.delete(id) } }
 fun importPack(uri: Uri) { modelOperation { app.models.importPack(uri) { modelProgress.value=it } } }
 private fun modelOperation(block: suspend ()->Unit) {
  if(modelJob?.isActive==true) return
  modelJob=viewModelScope.launch { modelProgress.value="Подготовка…";try { withContext(Dispatchers.IO) { block() } } catch(e: CancellationException) { throw e } catch(e: Exception) { reportError("Установка моделей",e) } finally { modelProgress.value=null;refreshModels() } }
 }
 fun cancelModelDownload() { modelJob?.cancel() }
 fun startRecording() {
  if(isRecording.value || recordingPhase.value in setOf(RecordingPhase.STARTING,RecordingPhase.STOPPING)) return
  if(androidx.core.content.ContextCompat.checkSelfPermission(app,android.Manifest.permission.RECORD_AUDIO)!=android.content.pm.PackageManager.PERMISSION_GRANTED) { requireMicrophonePermission();return }
  recordingPhase.value=RecordingPhase.STARTING;stopAfterStart=null;pauseAfterStart=false;elapsed.value=0;levels.value=emptyList();voiceLevel.value=0f;envelope.reset()
  viewModelScope.launch {
   var r: MediaRecorder?=null;var f: File?=null
   try {
    withContext(Dispatchers.IO) {
     val folder=File(app.filesDir,"audio").apply { mkdirs() };val reserve=8L*1024*1024
     require(folder.usableSpace>reserve) { "Недостаточно места для записи" }
     f=File(folder,"${UUID.randomUUID()}.m4a")
     val media=if(Build.VERSION.SDK_INT>=31) MediaRecorder(app) else @Suppress("DEPRECATION") MediaRecorder()
     r=media
     media.setAudioSource(MediaRecorder.AudioSource.MIC);media.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);media.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
     media.setAudioSamplingRate(48000);media.setAudioEncodingBitRate(128000);media.setOutputFile(f!!.path)
     media.setMaxFileSize((folder.usableSpace-reserve).coerceAtLeast(1))
     media.setOnInfoListener { _,what,_ -> if(what==MediaRecorder.MEDIA_RECORDER_INFO_MAX_FILESIZE_REACHED) viewModelScope.launch { stopRecording(true);notice.value="Свободное место заканчивается. Запись остановлена." } }
     media.setOnErrorListener { _,what,extra -> viewModelScope.launch { stopRecording(false);reportError("Запись",IllegalStateException("MediaRecorder error what=$what extra=$extra")) } }
     media.prepare();media.start()
    }
    recorder=r;recordingFile=f;isRecording.value=true;paused.value=false;recordingPhase.value=RecordingPhase.RECORDING
    val media=r!!
    meterJob=viewModelScope.launch {
     var last=android.os.SystemClock.elapsedRealtime()
     while(isActive) {
      delay(50);val now=android.os.SystemClock.elapsedRealtime();val delta=now-last;last=now
      if(!paused.value) {
       elapsed.value+=delta
       val amp=runCatching { media.maxAmplitude/32768f }.getOrDefault(0f)
       voiceLevel.value=envelope.sample(amp,delta/1000f)
       levels.value=(levels.value+amp).takeLast(70)
      }
     }
    }
    if(pauseAfterStart) pauseRecording()
    stopAfterStart?.let { stopRecording(it) }
   } catch(e: CancellationException) {
    withContext(NonCancellable+Dispatchers.IO) { runCatching { r?.stop() };runCatching { r?.release() };f?.delete() };throw e
   } catch(e: Exception) {
    withContext(Dispatchers.IO) { runCatching { r?.release() };f?.delete() }
    recordingPhase.value=RecordingPhase.ERROR;reportError("Запись",e)
   }
  }
 }
 fun pauseRecording() {
  if(!isRecording.value || recordingPhase.value==RecordingPhase.STOPPING) return
  runCatching {
   if(paused.value) recorder?.resume() else recorder?.pause()
   paused.value=!paused.value;envelope.reset();voiceLevel.value=0f
   recordingPhase.value=if(paused.value) RecordingPhase.PAUSED else RecordingPhase.RECORDING
  }.onFailure { reportError("Запись",it) }
 }
 fun stopRecording(save: Boolean,persistAfterClear: Boolean=false) {
  if(recordingPhase.value==RecordingPhase.STARTING) { stopAfterStart=save;return }
  if(recordingPhase.value==RecordingPhase.STOPPING || recorder==null) return
  recordingPhase.value=RecordingPhase.STOPPING;meterJob?.cancel();voiceLevel.value=0f
  val f=recordingFile;val r=recorder;val duration=elapsed.value
  recorder=null;recordingFile=null;isRecording.value=false;paused.value=false
  val persistenceScope=if(persistAfterClear) CoroutineScope(Dispatchers.IO) else viewModelScope
  persistenceScope.launch {
   try {
    withContext(NonCancellable+Dispatchers.IO) {
     try { r?.stop() } catch(e: Exception) { f?.delete();throw e } finally { r?.release() }
     check(f!=null && f.exists()) { "Аудиофайл записи недоступен" }
     if(f!=null) {
      if(save) {
       val id=UUID.randomUUID().toString()
       val savedDuration=if(duration>0) duration else {
        val metadata=android.media.MediaMetadataRetriever()
        try { metadata.setDataSource(f.path);metadata.extractMetadata(android.media.MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()?:0L } finally { metadata.release() }
       }
       check(savedDuration>0) { "Запись слишком короткая. Попробуйте записать ещё раз" }
       dao.insert(Recording(id,"Запись ${java.text.SimpleDateFormat("dd.MM HH:mm",java.util.Locale.ROOT).format(java.util.Date())}",f.path,durationMs=savedDuration,backend=backend.value))
       // Give the physical shell time to settle while the database commit finishes.
       elapsed.value=0;levels.value=emptyList();envelope.reset();recordingPhase.value=RecordingPhase.SAVED;selected.value=id;notice.value="Запись сохранена"
      } else { check(f.delete()) { "Не удалось удалить черновик записи" };elapsed.value=0;levels.value=emptyList();envelope.reset();if(recordingPhase.value!=RecordingPhase.ERROR) recordingPhase.value=RecordingPhase.IDLE }
     }
    }
   } catch(e: Exception) { recordingPhase.value=RecordingPhase.ERROR;reportError("Сохранение записи",e) }
  }
 }
 override fun onCleared() { if(isRecording.value) stopRecording(true,persistAfterClear=true);super.onCleared() }
}
