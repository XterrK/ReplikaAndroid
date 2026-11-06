@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package ru.replika.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.*
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.delay
import ru.replika.data.Recording
import java.text.SimpleDateFormat
import java.util.*

fun clock(ms: Long)="%02d:%02d".format(Locale.ROOT,ms.coerceAtLeast(0)/60000,ms.coerceAtLeast(0)/1000%60)
@Composable fun ReplikaRoot(vm: AppViewModel) {
 val library by vm.library.collectAsStateWithLifecycle();val recordings=library.records;val loaded=library.loaded
 val phase by vm.recordingPhase.collectAsStateWithLifecycle()
 val importing by vm.importProgress.collectAsStateWithLifecycle()
 val sessionLive=phase in setOf(RecordingPhase.STARTING,RecordingPhase.RECORDING,RecordingPhase.PAUSED,RecordingPhase.STOPPING)
 var exportPicker by remember { mutableStateOf(false) };var exportRecord by remember { mutableStateOf<Recording?>(null) }
 val selected by vm.selected.collectAsStateWithLifecycle();val error by vm.error.collectAsStateWithLifecycle();val notice by vm.notice.collectAsStateWithLifecycle()
 var screen by rememberSaveable { mutableStateOf("home") };var settingsOrigin by rememberSaveable { mutableStateOf("home") };val context=LocalContext.current;val snackbar=remember { SnackbarHostState() }
 val import=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { it?.let(vm::importAudio) }
 val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { if(it) vm.startRecording() else { vm.requireMicrophonePermission();vm.error.value="Для записи разрешите доступ к микрофону в настройках приложения. Аудиофайл можно импортировать без этого разрешения." } }
 var exitRecording by rememberSaveable { mutableStateOf(false) }
 var resumeAfterDecision by rememberSaveable { mutableStateOf(false) }
 fun leaveRecording() {
  if(vm.recordingPhase.value==RecordingPhase.STOPPING) return
  if(vm.isRecording.value || vm.recordingPhase.value==RecordingPhase.STARTING) {
   if(!exitRecording) {
    resumeAfterDecision=vm.recordingPhase.value in setOf(RecordingPhase.RECORDING,RecordingPhase.STARTING)
    if(vm.recordingPhase.value==RecordingPhase.RECORDING) vm.pauseRecording()
    exitRecording=true
   }
  } else screen="home"
 }
 // The recorder can finish starting after Back was pressed. Pause it before asking the decision.
 LaunchedEffect(exitRecording,phase) { if(exitRecording && phase==RecordingPhase.RECORDING) vm.pauseRecording() }
 fun dismissRecordingDecision() {
  exitRecording=false
  if(resumeAfterDecision && vm.recordingPhase.value==RecordingPhase.PAUSED) vm.pauseRecording()
  resumeAfterDecision=false
 }
 fun startRecording() { if(ContextCompat.checkSelfPermission(context,Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED) vm.startRecording() else { vm.requireMicrophonePermission();permission.launch(Manifest.permission.RECORD_AUDIO) } }
 LaunchedEffect(Unit) { if(screen=="recording") screen="home" }
 val notifications=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
 var notificationRequested by rememberSaveable { mutableStateOf(false) }
 val processingActive=recordings.any { it.status in setOf("QUEUED","PROCESSING") }
 LaunchedEffect(processingActive) {
  if(processingActive && !notificationRequested && Build.VERSION.SDK_INT>=33 && ContextCompat.checkSelfPermission(context,Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED) {
   notificationRequested=true;notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
  }
 }
 LaunchedEffect(notice) { notice?.let { message ->
  val result=snackbar.showSnackbar(message,if(vm.undoAvailable.value) "Отменить правку" else null,withDismissAction=true,duration=SnackbarDuration.Long)
  if(result==SnackbarResult.ActionPerformed) vm.undoLastEdit()
  if(vm.notice.value==message) vm.clearNotice()
 } }
 BackHandler(enabled=selected!=null || screen!="home" || sessionLive) {
  if(selected!=null) { vm.selected.value=null;screen="library" } else if(screen=="home" && sessionLive) leaveRecording() else if(screen=="settings") screen=settingsOrigin else screen="home"
 }
 Scaffold(containerColor=Ink,snackbarHost={SnackbarHost(snackbar,Modifier.testTag("app-notice"))},bottomBar={ if(selected==null && !sessionLive) NavigationBar(containerColor=Ink,tonalElevation=0.dp) {
  NavigationBarItem(selected=screen=="home",onClick={screen="home"},icon={Icon(Icons.Outlined.MicNone,null)},label={Text("Запись")})
  NavigationBarItem(selected=screen=="library",onClick={screen="library"},icon={Icon(Icons.Outlined.GraphicEq,null)},label={Text("Записи")})
  NavigationBarItem(selected=screen=="models",onClick={screen="models";vm.refreshModels()},icon={Icon(Icons.Outlined.Memory,null)},label={Text("Модели")})
 } }) { padding ->
  Box(Modifier.fillMaxSize().padding(padding)) {
   val rec=recordings.firstOrNull { it.id==selected }
   when {
    rec!=null -> Workspace(vm,rec,onBack={vm.selected.value=null;screen="library"})
    selected!=null && !loaded -> LoadingContent("Открываем запись…")
    selected!=null -> Column(Modifier.fillMaxSize().padding(24.dp),verticalArrangement=Arrangement.Center) { Text("Запись недоступна",style=MaterialTheme.typography.headlineSmall);Text("Она могла быть удалена. Остальные записи доступны в библиотеке.",color=Muted);Button(shape=ProductShape.control,onClick={vm.selected.value=null}) { Text("В библиотеку") } }
    screen=="settings" -> AppearanceSettings(vm) { screen=settingsOrigin }
    screen=="models" -> ModelsScreen(vm,recordings)
    screen=="library" -> Library(vm,recordings,loaded=loaded,onSettings={settingsOrigin="library";screen="settings"},onImport={if(importing==null) import.launch(arrayOf("audio/*","video/*","application/octet-stream"))},onRecord={ screen="home";startRecording() })
    else -> RecordingScreen(vm,onBack={leaveRecording()},onStart={startRecording()},onSettings={settingsOrigin="home";screen="settings"},onImport={if(importing==null) import.launch(arrayOf("audio/*","video/*","application/octet-stream"))},onExport={exportPicker=true},importing=importing)

   }
  }
 }
 if(importing!=null) AlertDialog(onDismissRequest={},title={Text("Подготовка файла")},text={Column(verticalArrangement=Arrangement.spacedBy(12.dp)) { LinearProgressIndicator(Modifier.fillMaxWidth());Text(importing!!) }},confirmButton={TextButton(onClick=vm::cancelImport) { Text("Отменить") }})
 if(exportPicker) HomeExportPicker(recordings.filter { it.status=="READY" },onChoose={exportPicker=false;exportRecord=it},onDismiss={exportPicker=false})
 exportRecord?.let { record -> TranscriptExport(vm,record) { exportRecord=null } }
 if(exitRecording) RecordingDecisionSheet(
  ready=phase==RecordingPhase.PAUSED,
  onDismiss=::dismissRecordingDecision,
  onSave={exitRecording=false;resumeAfterDecision=false;vm.stopRecording(true)},
  onDiscard={exitRecording=false;resumeAfterDecision=false;vm.stopRecording(false);screen="home"}
 )
 if(error!=null) AlertDialog(onDismissRequest={vm.error.value=null},title={Text("Не удалось завершить действие")},text={Text(error!!)},confirmButton={TextButton(onClick={vm.error.value=null}) { Text("Понятно") }})
}
/** Two explicit outcomes. Dismissing the sheet returns to the previous recording state. */
@Composable private fun RecordingDecisionSheet(ready: Boolean,onDismiss: ()->Unit,onSave: ()->Unit,onDiscard: ()->Unit) {
 ModalBottomSheet(onDismissRequest=onDismiss,containerColor=SurfaceBase,
  sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),modifier=Modifier.testTag("recording-decision")) {
  DarkSheetSystemBars()
  Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal=24.dp).padding(bottom=24.dp).navigationBarsPadding(),verticalArrangement=Arrangement.spacedBy(12.dp)) {
   Text("Сохранить запись?",style=MaterialTheme.typography.headlineMedium)
   Text(if(ready) "Запись на паузе. Выберите, что с ней сделать." else "Включаем микрофон…",style=MaterialTheme.typography.bodyMedium,color=Muted,modifier=Modifier.padding(bottom=8.dp))
   Button(onClick=onSave,enabled=ready,shape=ProductShape.control,modifier=Modifier.fillMaxWidth().heightIn(min=56.dp).testTag("recording-save")) { Text("Сохранить запись") }
   FilledTonalButton(onClick=onDiscard,shape=ProductShape.control,colors=ButtonDefaults.filledTonalButtonColors(containerColor=MaterialTheme.colorScheme.errorContainer,contentColor=MaterialTheme.colorScheme.onErrorContainer),modifier=Modifier.fillMaxWidth().heightIn(min=56.dp).testTag("recording-discard")) { Text("Удалить запись") }
  }
 }
}
@Composable fun LoadingContent(label: String) { Column(Modifier.fillMaxSize().padding(24.dp).testTag("loading-content"),verticalArrangement=Arrangement.Center,horizontalAlignment=Alignment.CenterHorizontally) { CircularProgressIndicator(Modifier.size(28.dp),strokeWidth=2.dp);Spacer(Modifier.height(16.dp));Text(label,color=Muted) } }
@Composable fun Eyebrow(text: String) { Text(text,style=MaterialTheme.typography.labelMedium,color=Mint,letterSpacing=1.sp) }
@Composable fun Library(vm: AppViewModel,records: List<Recording>,loaded: Boolean,onImport: ()->Unit,onRecord: ()->Unit,onSettings: ()->Unit={}) {
 var query by rememberSaveable { mutableStateOf("") };var matching by remember { mutableStateOf(emptyList<String>()) };var matchingQuery by remember { mutableStateOf<String?>(null) }
 var menu by remember { mutableStateOf<String?>(null) };var deleting by remember { mutableStateOf<Recording?>(null) };var renaming by remember { mutableStateOf<Recording?>(null) };var deletingBusy by remember { mutableStateOf(false) }
 LaunchedEffect(query) {
  val needle=query
  if(needle.isBlank()) { matching=emptyList();matchingQuery=needle }
  else { delay(180);vm.dao.searchFlow(needle).collect { matching=it;matchingQuery=needle } }
 }
 val searchPending=query.isNotBlank() && matchingQuery!=query
 val shown=records.filter { query.isBlank() || it.title.contains(query,true) || (matchingQuery==query && it.id in matching) }
 LazyColumn(Modifier.fillMaxSize().testTag("library-list"),contentPadding=PaddingValues(start=20.dp,end=20.dp,top=20.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
  item { Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically) {
   Column { Text("REPLIKA",style=MaterialTheme.typography.labelMedium,color=Muted,letterSpacing=2.sp);Spacer(Modifier.height(4.dp));Text("Библиотека",style=MaterialTheme.typography.headlineLarge) }
   IconButton(onClick=onSettings,modifier=Modifier.testTag("appearance-settings")) { Icon(Icons.Outlined.Tune,"Настройки",tint=Muted) }
  } }
  item { Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(10.dp)) {
   Button(shape=ProductShape.control,onClick=onRecord,modifier=Modifier.weight(1f).heightIn(min=50.dp)) { Icon(Icons.Outlined.Mic,null,Modifier.size(20.dp));Spacer(Modifier.width(6.dp));Text("Записать") }
   FilledTonalButton(shape=ProductShape.control,onClick=onImport,modifier=Modifier.weight(1f).heightIn(min=50.dp)) { Icon(Icons.Outlined.Add,null,Modifier.size(20.dp));Spacer(Modifier.width(6.dp));Text("Импорт") }
  } }
  item { OutlinedTextField(query,{query=it},Modifier.fillMaxWidth().testTag("library-search"),placeholder={Text("Найти запись")},leadingIcon={Icon(Icons.Outlined.Search,null)},trailingIcon={if(query.isNotEmpty()) IconButton(onClick={query=""}) { Icon(Icons.Outlined.Close,"Очистить поиск") }},singleLine=true,shape=RoundedCornerShape(12.dp)) }
  item { Text(if(searchPending) "Поиск по стенограммам…" else if(loaded) "${shown.size} ${when { shown.size%100 in 11..14->"записей";shown.size%10==1->"запись";shown.size%10 in 2..4->"записи";else->"записей" }}" else "Загружаем библиотеку…",style=MaterialTheme.typography.labelLarge,color=Muted) }
  if(loaded && shown.isEmpty() && !searchPending) item { Column(Modifier.padding(vertical=36.dp)) { Icon(Icons.Outlined.AudioFile,null,tint=Muted);Spacer(Modifier.height(12.dp));Text(if(query.isBlank()) "Пока нет записей" else "Ничего не найдено",style=MaterialTheme.typography.titleLarge);Spacer(Modifier.height(8.dp));Text(if(query.isBlank()) "Запишите голос или добавьте аудио и видео. Всё останется на устройстве." else "Попробуйте другое слово или очистите поиск.",color=Muted) } }
  items(shown,key={it.id}) { r ->
   Row(Modifier.fillMaxWidth().testTag("recording-${r.id}").clickable { vm.selected.value=r.id }.padding(vertical=4.dp),verticalAlignment=Alignment.Top,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
    Box(Modifier.padding(top=3.dp).size(40.dp).clip(RoundedCornerShape(12.dp)).background(SurfaceBase),contentAlignment=Alignment.Center) { Icon(if(r.status=="READY") Icons.Outlined.GraphicEq else if(r.status=="ERROR") Icons.Outlined.ErrorOutline else Icons.Outlined.AudioFile,null,tint=if(r.status=="ERROR") MaterialTheme.colorScheme.error else Blue,modifier=Modifier.size(22.dp)) }
    Column(Modifier.weight(1f).padding(vertical=2.dp)) {
     Text(r.title,style=MaterialTheme.typography.titleMedium,maxLines=1,overflow=TextOverflow.Ellipsis)
     Spacer(Modifier.height(5.dp));Text("${if(r.durationMs>0) audioClock(r.durationMs)+" · " else ""}${SimpleDateFormat("dd MMM · HH:mm",Locale("ru")).format(Date(r.createdAt))}",color=Muted,style=MaterialTheme.typography.bodySmall)
     Spacer(Modifier.height(5.dp));Text(if(r.status=="READY") "Готово · ${backendName(r.backend)}" else r.phase,color=if(r.status=="READY") Mint else if(r.status=="ERROR") MaterialTheme.colorScheme.error else Muted,style=MaterialTheme.typography.labelMedium,maxLines=2)
    }
    Box { IconButton(onClick={menu=r.id},modifier=Modifier.size(48.dp).testTag("recording-menu-${r.id}")) { Icon(Icons.Outlined.MoreVert,"Действия с записью ${r.title}",tint=Muted) }
     DropdownMenu(expanded=menu==r.id,onDismissRequest={menu=null}) {
      DropdownMenuItem(text={Text("Переименовать")},onClick={menu=null;renaming=r})
      DropdownMenuItem(text={Text(if(r.status in setOf("PROCESSING","QUEUED","CANCELLING")) "Сначала отмените обработку" else "Удалить запись")},enabled=r.status !in setOf("PROCESSING","QUEUED","CANCELLING"),onClick={menu=null;deleting=r})
     }
    }
   };HorizontalDivider(Modifier.padding(top=12.dp),color=SurfaceLine)
  }
 }
 if(deleting!=null) AlertDialog(onDismissRequest={if(!deletingBusy) deleting=null},title={Text("Удалить запись?")},text={Text("«${deleting!!.title}»\n\nУдалятся стенограмма и принадлежащая записи локальная копия аудио. Исходник импорта и модели сохранятся.")},confirmButton={TextButton(enabled=!deletingBusy,onClick={deletingBusy=true;vm.deleteRecording(deleting!!.id) { ok -> deletingBusy=false;if(ok) deleting=null }},modifier=Modifier.testTag("confirm-delete-recording")) { Text(if(deletingBusy) "Удаляем…" else "Удалить",color=MaterialTheme.colorScheme.error) }},dismissButton={TextButton(enabled=!deletingBusy,onClick={deleting=null}) { Text("Отмена") }})
 if(renaming!=null) { var value by remember(renaming!!.id) { mutableStateOf(renaming!!.title) };AlertDialog(onDismissRequest={renaming=null},title={Text("Название записи")},text={OutlinedTextField(value,{value=it},label={Text("Название")},modifier=Modifier.testTag("recording-title-editor"))},confirmButton={TextButton(onClick={vm.title(renaming!!.id,value);renaming=null}) { Text("Сохранить") }},dismissButton={TextButton(onClick={renaming=null}) { Text("Отмена") }}) }
}
@Composable fun Waveform(peaks: List<Float>,position: Float,modifier: Modifier,color: Color=Blue,onSeek: (Float)->Unit) {
 val muted=Muted
 val seek by rememberUpdatedState(onSeek);val playheadColor=MaterialTheme.colorScheme.onSurface
 var pixelWidth by remember { mutableIntStateOf(1) };val barPixels=with(LocalDensity.current) { 3.dp.toPx() }
 val shown=remember(peaks,pixelWidth,barPixels) {
  val maxBars=(pixelWidth/barPixels).toInt().coerceAtLeast(1);val stride=kotlin.math.ceil(peaks.size.toDouble()/maxBars).toInt().coerceAtLeast(1)
  peaks.chunked(stride).map { it.maxOrNull()?:0f }
 }
 Canvas(modifier.onSizeChanged { pixelWidth=it.width }.pointerInput(Unit) { detectTapGestures { seek((it.x/size.width.coerceAtLeast(1)).coerceIn(0f,1f)) } }) {
  val step=size.width/shown.size.coerceAtLeast(1);val mid=size.height/2
  shown.forEachIndexed { i,amp -> val h=(amp.coerceIn(0f,1f)*size.height).coerceAtLeast(1f);val x=(i+.5f)*step
   drawLine(if(i.toFloat()/shown.size<=position) color else color.copy(alpha=.32f),Offset(x,mid-h/2),Offset(x,mid+h/2),strokeWidth=(step*.55f).coerceIn(1f,3.dp.toPx()),cap=StrokeCap.Round)
  }
  if(shown.isEmpty()) drawLine(muted.copy(alpha=.25f),Offset(0f,mid),Offset(size.width,mid),1f)
  drawLine(playheadColor.copy(alpha=.8f),Offset(size.width*position.coerceIn(0f,1f),0f),Offset(size.width*position.coerceIn(0f,1f),size.height),1.dp.toPx())
 }
}
