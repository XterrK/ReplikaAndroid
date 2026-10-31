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
import ru.replika.data.*
import ru.replika.ml.*
import java.io.File
import java.util.UUID

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class AppViewModel(application: Application): AndroidViewModel(application) {
 private val app=application as ReplikaApp
 val dao=app.db.dao()
 val recordings=dao.recordings().stateIn(viewModelScope,SharingStarted.Eagerly,emptyList())
 val error=MutableStateFlow<String?>(null)
 val selected=MutableStateFlow<String?>(null)
 val segments=selected.flatMapLatest { if(it==null) flowOf(emptyList()) else dao.segments(it) }.stateIn(viewModelScope,SharingStarted.Eagerly,emptyList())
 val speakers=selected.flatMapLatest { if(it==null) flowOf(emptyList()) else dao.speakers(it) }.stateIn(viewModelScope,SharingStarted.Eagerly,emptyList())
 val models=MutableStateFlow<List<ModelStatus>>(emptyList())
 val backend=MutableStateFlow(app.getSharedPreferences("settings",0).getString("backend","giga-v2")?:"giga-v2")
 fun selectBackend(id: String) { backend.value=id;app.getSharedPreferences("settings",0).edit().putString("backend",id).apply() }
 val modelProgress=MutableStateFlow<String?>(null)
 private var modelJob: Job?=null
 private var recorder: MediaRecorder?=null
 private var recordingFile: File?=null
 val isRecording=MutableStateFlow(false)
 val paused=MutableStateFlow(false)
 val elapsed=MutableStateFlow(0L)
 val levels=MutableStateFlow<List<Float>>(emptyList())
 private var meterJob: Job?=null
 private val processingRequests=mutableSetOf<String>()
 private val cancellingRequests=mutableSetOf<String>()
 init {
  refreshModels()
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
 fun refreshModels() { viewModelScope.launch(Dispatchers.IO) { runCatching { app.models.statuses() }.onSuccess { models.value=it }.onFailure { error.value=it.message } } }
 fun importAudio(uri: Uri) { viewModelScope.launch {
  try {
   val id=UUID.randomUUID().toString();val folder=File(app.filesDir,"audio").apply { mkdirs() }
   val metadata=withContext(Dispatchers.IO) { runCatching { app.contentResolver.query(uri,arrayOf(android.provider.OpenableColumns.DISPLAY_NAME,android.provider.OpenableColumns.SIZE),null,null,null)?.use { if(it.moveToFirst()) it.getString(0) to (if(it.isNull(1)) -1L else it.getLong(1)) else null } }.getOrNull() }
   val title=metadata?.first?:uri.lastPathSegment?:"Новая запись"
   val file=File(folder,"$id.audio")
   try {
    withContext(Dispatchers.IO) {
     val reserve=8L*1024*1024
     require(folder.usableSpace>reserve+(metadata?.second?:0L).coerceAtLeast(0)) { "Недостаточно места для импорта аудио" }
     app.contentResolver.openInputStream(uri)?.use { src -> file.outputStream().use { dst ->
      val buffer=ByteArray(65536);while(true) { ensureActive();val n=src.read(buffer);if(n<0) break;dst.write(buffer,0,n) }
     } }?:error("Файл недоступен")
     require(file.length()>0) { "Файл пуст" }
    }
    dao.insert(Recording(id,title,file.path));selected.value=id
   } catch(t: Throwable) { file.delete();throw t }
  } catch(e: CancellationException) { throw e } catch(e: Exception) { error.value="Не удалось импортировать аудио: ${e.message}" }
 } }
 fun process(id: String,count: Int) {
  if(!processingRequests.add(id)) return
  viewModelScope.launch {
   try {
    require(count==-1 || count in 1..20) { "Укажите от 1 до 20 говорящих" }
    val queued=app.db.withTransaction {
     val rec=dao.recording(id)?:return@withTransaction false
     if(rec.status in setOf("QUEUED","PROCESSING","CANCELLING")) return@withTransaction false
     dao.insert(rec.copy(expectedSpeakers=count,backend=backend.value,status="QUEUED",phase="Ожидание обработки",error=null))
     true
    }
    if(queued) ProcessingWorker.enqueue(app,id)
   } catch(e: CancellationException) { throw e } catch(e: Exception) { error.value=e.message }
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
   } catch(e: CancellationException) { throw e } catch(e: Exception) { error.value="Не удалось отменить обработку: ${e.message}" }
   finally { cancellingRequests.remove(id) }
  }
 }
 fun edit(row: SegmentRow,text: String,speaker: Int,reviewed: Boolean,onComplete: (Boolean)->Unit = {}) { viewModelScope.launch {
  try { dao.updateSegment(row.copy(text=text,speakerId=speaker,edited=row.edited || text!=row.text || speaker!=row.speakerId,reviewed=reviewed));onComplete(true) }
  catch(e: CancellationException) { throw e } catch(e: Exception) { error.value="Не удалось сохранить исправления: ${e.message}";onComplete(false) }
 } }
 fun rename(id: String,speaker: Int,name: String) { viewModelScope.launch { dao.speaker(SpeakerRow(id,speaker,name.trim().ifBlank { "Участник ${speaker+1}" })) } }
 fun title(id: String,title: String) { viewModelScope.launch { app.db.withTransaction { dao.recording(id)?.let { dao.insert(it.copy(title=title.trim().ifBlank { it.title })) } } } }
 fun download(id: String) { modelOperation { app.models.download(id) { modelProgress.value=it } } }
 fun deleteModel(id: String) { modelOperation { app.models.delete(id) } }
 fun importPack(uri: Uri) { modelOperation { app.models.importPack(uri) { modelProgress.value=it } } }
 private fun modelOperation(block: suspend ()->Unit) {
  if(modelJob?.isActive==true) return
  modelJob=viewModelScope.launch { modelProgress.value="Подготовка…";try { withContext(Dispatchers.IO) { block() } } catch(e: CancellationException) { throw e } catch(e: Exception) { error.value=e.message } finally { modelProgress.value=null;refreshModels() } }
 }
 fun cancelModelDownload() { modelJob?.cancel() }
 fun startRecording() {
  if(isRecording.value) return
  try {
   val folder=File(app.filesDir,"audio").apply { mkdirs() }
   val reserve=8L*1024*1024
   require(folder.usableSpace>reserve) { "Недостаточно места для записи" }
   val f=File(folder,"${UUID.randomUUID()}.m4a")
   val r=if(Build.VERSION.SDK_INT>=31) MediaRecorder(app) else @Suppress("DEPRECATION") MediaRecorder()
   try { r.setAudioSource(MediaRecorder.AudioSource.MIC);r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);r.setAudioSamplingRate(48000);r.setAudioEncodingBitRate(128000);r.setOutputFile(f.path)
   r.setMaxFileSize((folder.usableSpace-reserve).coerceAtLeast(1))
   r.setOnInfoListener { _,what,_ -> if(what==MediaRecorder.MEDIA_RECORDER_INFO_MAX_FILESIZE_REACHED) { stopRecording(true);error.value="Запись сохранена: свободное место заканчивается" } }
   r.setOnErrorListener { _,_,_ -> stopRecording(false);error.value="Запись прервана: ошибка микрофона или нехватка места" }
   r.prepare();r.start() } catch(t: Throwable) { r.release();f.delete();throw t }
   recorder=r;recordingFile=f;isRecording.value=true;paused.value=false;elapsed.value=0;levels.value=emptyList()
   meterJob=viewModelScope.launch { var last=android.os.SystemClock.elapsedRealtime();while(isActive) { delay(100);val now=android.os.SystemClock.elapsedRealtime();val delta=now-last;last=now;if(!paused.value) { elapsed.value+=delta;val amp=runCatching { r.maxAmplitude/32768f }.getOrDefault(0f);levels.value=(levels.value+amp).takeLast(70) } } }
  } catch(e: Exception) { error.value="Микрофон: ${e.message}" }
 }
 fun pauseRecording() { runCatching { if(paused.value) recorder?.resume() else recorder?.pause();paused.value=!paused.value }.onFailure { error.value=it.message } }
 fun stopRecording(save: Boolean,persistAfterClear: Boolean=false) {
  meterJob?.cancel();val f=recordingFile;val r=recorder
  recorder=null;isRecording.value=false
  try { r?.stop() } catch(e: Exception) { f?.delete();error.value="Запись слишком короткая или прервана" } finally { r?.release() }
  if(f!=null && f.exists()) {
   if(save) {
    val persistenceScope=if(persistAfterClear) CoroutineScope(Dispatchers.IO) else viewModelScope
    persistenceScope.launch { try { val id=UUID.randomUUID().toString();dao.insert(Recording(id,"Запись ${java.text.SimpleDateFormat("dd.MM HH:mm",java.util.Locale.ROOT).format(java.util.Date())}",f.path));selected.value=id } catch(e: Exception) { error.value="Не удалось сохранить запись: ${e.message}" } }
   } else f.delete()
  };recordingFile=null
 }
 override fun onCleared() { if(isRecording.value) stopRecording(true,persistAfterClear=true);super.onCleared() }
}
