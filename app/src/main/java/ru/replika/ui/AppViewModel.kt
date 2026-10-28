package ru.replika.ui

import android.app.Application
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import androidx.lifecycle.*
import androidx.work.WorkManager
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
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
 init { refreshModels(); viewModelScope.launch { error.value=null } }
 fun refreshModels() { viewModelScope.launch(Dispatchers.IO) { runCatching { app.models.statuses() }.onSuccess { models.value=it }.onFailure { error.value=it.message } } }
 fun importAudio(uri: Uri) { viewModelScope.launch {
  try {
   val id=UUID.randomUUID().toString();val folder=File(app.filesDir,"audio").apply { mkdirs() }
   val title=withContext(Dispatchers.IO) { app.contentResolver.query(uri,arrayOf(android.provider.OpenableColumns.DISPLAY_NAME),null,null,null)?.use { if(it.moveToFirst()) it.getString(0) else null } }?:"Новая запись"
   val file=File(folder,"$id.audio")
   try {
    withContext(Dispatchers.IO) {
     app.contentResolver.openInputStream(uri)?.use { src -> file.outputStream().use { dst -> src.copyTo(dst) } }?:error("Файл недоступен")
     require(file.length()>0) { "Файл пуст" }
    }
    dao.insert(Recording(id,title,file.path));selected.value=id
   } catch(t: Throwable) { file.delete();throw t }
  } catch(e: Exception) { error.value="Не удалось импортировать аудио: ${e.message}" }
 } }
 fun process(id: String,count: Int) { viewModelScope.launch {
  val rec=dao.recording(id)?:return@launch
  dao.insert(rec.copy(expectedSpeakers=count,backend=backend.value,status="QUEUED",phase="Ожидание обработки",error=null))
  ProcessingWorker.enqueue(app,id)
 } }
 fun cancel(id: String) { viewModelScope.launch { withContext(Dispatchers.IO) { WorkManager.getInstance(app).cancelAllWorkByTag(id).result.get() };dao.status(id,"CANCELLED","Обработка отменена") } }
 fun edit(row: SegmentRow,text: String,speaker: Int,reviewed: Boolean) { viewModelScope.launch { dao.updateSegment(row.copy(text=text,speakerId=speaker,edited=row.edited || text!=row.text || speaker!=row.speakerId,reviewed=reviewed)) } }
 fun rename(id: String,speaker: Int,name: String) { viewModelScope.launch { dao.speaker(SpeakerRow(id,speaker,name.trim().ifBlank { "Участник ${speaker+1}" })) } }
 fun title(id: String,title: String) { viewModelScope.launch { dao.recording(id)?.let { dao.insert(it.copy(title=title.trim().ifBlank { it.title })) } } }
 fun download(id: String) { modelOperation { app.models.download(id) { modelProgress.value=it } } }
 fun deleteModel(id: String) { modelOperation { app.models.delete(id) } }
 fun importPack(uri: Uri) { modelOperation { app.models.importPack(uri) { modelProgress.value=it } } }
 private fun modelOperation(block: suspend ()->Unit) {
  if(modelJob?.isActive==true) return
  modelJob=viewModelScope.launch { modelProgress.value="Подготовка…";try { withContext(Dispatchers.IO) { block() } } catch(e: CancellationException) { throw e } catch(e: Exception) { error.value=e.message } finally { modelProgress.value=null;refreshModels() } }
 }
 fun cancelModelDownload() { modelJob?.cancel() }
 fun startRecording() {
  try {
   val folder=File(app.filesDir,"audio").apply { mkdirs() }
   val f=File(folder,"${UUID.randomUUID()}.m4a")
   val r=if(Build.VERSION.SDK_INT>=31) MediaRecorder(app) else @Suppress("DEPRECATION") MediaRecorder()
   r.setAudioSource(MediaRecorder.AudioSource.MIC);r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);r.setAudioSamplingRate(48000);r.setAudioEncodingBitRate(128000);r.setOutputFile(f.path)
   try { r.prepare();r.start() } catch(t: Throwable) { r.release();f.delete();throw t }
   recorder=r;recordingFile=f;isRecording.value=true;paused.value=false;elapsed.value=0;levels.value=emptyList()
   meterJob=viewModelScope.launch { var last=android.os.SystemClock.elapsedRealtime();while(isActive) { delay(100);val now=android.os.SystemClock.elapsedRealtime();val delta=now-last;last=now;if(!paused.value) { elapsed.value+=delta;val amp=runCatching { r.maxAmplitude/32768f }.getOrDefault(0f);levels.value=(levels.value+amp).takeLast(70) } } }
  } catch(e: Exception) { error.value="Микрофон: ${e.message}" }
 }
 fun pauseRecording() { runCatching { if(paused.value) recorder?.resume() else recorder?.pause();paused.value=!paused.value }.onFailure { error.value=it.message } }
 fun stopRecording(save: Boolean) {
  meterJob?.cancel();val f=recordingFile;val r=recorder
  recorder=null;isRecording.value=false
  try { r?.stop() } catch(e: Exception) { f?.delete();error.value="Запись слишком короткая или прервана" } finally { r?.release() }
  if(f!=null && f.exists()) {
   if(save) viewModelScope.launch { val id=UUID.randomUUID().toString();dao.insert(Recording(id,"Запись ${java.text.SimpleDateFormat("dd.MM HH:mm",java.util.Locale.ROOT).format(java.util.Date())}",f.path));selected.value=id } else f.delete()
  };recordingFile=null
 }
 override fun onCleared() { if(isRecording.value) stopRecording(true);super.onCleared() }
}
