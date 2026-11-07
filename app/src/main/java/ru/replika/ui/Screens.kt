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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
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
 val selected by vm.selected.collectAsStateWithLifecycle();val error by vm.error.collectAsStateWithLifecycle();val notice by vm.notice.collectAsStateWithLifecycle()
 var screen by rememberSaveable { mutableStateOf("home") };var settingsOrigin by rememberSaveable { mutableStateOf("home") };val context=LocalContext.current;val snackbar=remember { SnackbarHostState() }
 val import=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { it?.let(vm::importAudio) }
 val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { if(it) vm.startRecording() else { vm.requireMicrophonePermission();vm.error.value="Для записи разрешите доступ к микрофону в настройках приложения. Аудиофайл можно импортировать без этого разрешения." } }
 var exitRecording by rememberSaveable { mutableStateOf(false) }
 var deleteRecording by rememberSaveable { mutableStateOf(false) }
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
 /** ✕ asks before deleting; the recorder pauses while the question is open, like Back does. */
 fun askDeleteRecording() {
  if(vm.recordingPhase.value==RecordingPhase.STOPPING || deleteRecording || exitRecording) return
  resumeAfterDecision=vm.recordingPhase.value in setOf(RecordingPhase.RECORDING,RecordingPhase.STARTING)
  if(vm.recordingPhase.value==RecordingPhase.RECORDING) vm.pauseRecording()
  deleteRecording=true
 }
 // The recorder can finish starting after Back was pressed. Pause it before asking the decision.
 LaunchedEffect(exitRecording,deleteRecording,phase) { if((exitRecording || deleteRecording) && phase==RecordingPhase.RECORDING) vm.pauseRecording() }
 fun dismissRecordingDecision() {
  exitRecording=false;deleteRecording=false
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
 Scaffold(containerColor=Ink,snackbarHost={SnackbarHost(snackbar,Modifier.testTag("app-notice"))},bottomBar={ if(selected==null && !sessionLive) ReplikaTabBar(screen) { tab ->
  screen=tab;if(tab=="models") vm.refreshModels()
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
    else -> RecordingScreen(vm,onBack={leaveRecording()},onStart={startRecording()},onSettings={settingsOrigin="home";screen="settings"},onImport={if(importing==null) import.launch(arrayOf("audio/*","video/*","application/octet-stream"))},importing=importing,
     onDelete={askDeleteRecording()},onSave={if(vm.recordingPhase.value==RecordingPhase.RECORDING || vm.recordingPhase.value==RecordingPhase.PAUSED) vm.stopRecording(true)})

   }
  }
 }
 if(importing!=null) AlertDialog(onDismissRequest={},title={Text("Подготовка файла")},text={Column(verticalArrangement=Arrangement.spacedBy(12.dp)) { LinearProgressIndicator(Modifier.fillMaxWidth());Text(importing!!) }},confirmButton={TextButton(onClick=vm::cancelImport) { Text("Отменить") }})
 if(exitRecording) RecordingDecisionSheet(
  ready=phase==RecordingPhase.PAUSED,
  onDismiss=::dismissRecordingDecision,
  onSave={exitRecording=false;resumeAfterDecision=false;vm.stopRecording(true)},
  onDiscard={exitRecording=false;resumeAfterDecision=false;vm.stopRecording(false);screen="home"}
 )
 if(deleteRecording) AlertDialog(onDismissRequest=::dismissRecordingDecision,containerColor=SurfaceBase,modifier=Modifier.testTag("recording-delete-dialog"),
  icon={Icon(Icons.Outlined.DeleteOutline,null,tint=MaterialTheme.colorScheme.error)},
  title={Text("Удалить запись?")},text={Text("Записанное аудио будет удалено. Это нельзя отменить.",style=MaterialTheme.typography.bodyMedium)},
  confirmButton={TextButton(enabled=phase==RecordingPhase.PAUSED,onClick={deleteRecording=false;resumeAfterDecision=false;vm.stopRecording(false);screen="home"},modifier=Modifier.heightIn(min=48.dp).testTag("recording-delete-confirm")) { Text("Удалить",color=MaterialTheme.colorScheme.error) }},
  dismissButton={TextButton(onClick=::dismissRecordingDecision,modifier=Modifier.heightIn(min=48.dp).testTag("recording-delete-cancel")) { Text("Отмена") }})
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
   GradientButton("Сохранить запись",null,onSave,enabled=ready,modifier=Modifier.fillMaxWidth().testTag("recording-save"))
   FilledTonalButton(onClick=onDiscard,shape=ProductShape.control,colors=ButtonDefaults.filledTonalButtonColors(containerColor=MaterialTheme.colorScheme.errorContainer,contentColor=MaterialTheme.colorScheme.onErrorContainer),modifier=Modifier.fillMaxWidth().heightIn(min=56.dp).testTag("recording-discard")) { Text("Удалить запись") }
  }
 }
}
@Composable fun LoadingContent(label: String) { Column(Modifier.fillMaxSize().padding(24.dp).testTag("loading-content"),verticalArrangement=Arrangement.Center,horizontalAlignment=Alignment.CenterHorizontally) { CircularProgressIndicator(Modifier.size(28.dp),strokeWidth=2.dp);Spacer(Modifier.height(16.dp));Text(label,color=Muted) } }
@Composable fun Eyebrow(text: String) { Text(text,style=MaterialTheme.typography.labelMedium,color=Mint,letterSpacing=1.sp) }
/** Three tabs. The active tab carries the brand gradient behind its icon and a bold label. */
@Composable fun ReplikaTabBar(screen: String,onSelect: (String)->Unit) {
 // Tab labels grow with the user's font up to 1.3×, so «Библиотека» never truncates; the tab still
 // announces its full name and the icon carries the meaning at any size.
 val fontScale=LocalDensity.current.fontScale
 val labelSize=13.sp*(minOf(fontScale,1.3f)/fontScale.coerceAtLeast(.5f))
 val tabs=listOf(Triple("home","Запись",Icons.Outlined.MicNone),Triple("library","Библиотека",Icons.Outlined.LibraryMusic),Triple("models","Модели",Icons.Outlined.Memory))
 Surface(color=Ink,modifier=Modifier.fillMaxWidth()) {
  Column {
   HorizontalDivider(color=SurfaceLine.copy(alpha=.6f))
   Row(Modifier.fillMaxWidth().navigationBarsPadding().selectableGroup().padding(horizontal=8.dp,vertical=6.dp),horizontalArrangement=Arrangement.SpaceEvenly) {
    tabs.forEach { (id,label,icon) ->
     val active=screen==id || id=="home" && screen !in setOf("library","models")
     Column(Modifier.weight(1f).clip(ProductShape.control).selectable(selected=active,role=androidx.compose.ui.semantics.Role.Tab,onClick={onSelect(id)}).heightIn(min=56.dp).padding(vertical=4.dp).testTag("tab-$id"),
      horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(4.dp)) {
      Box(Modifier.size(width=56.dp,height=30.dp).clip(RoundedCornerShape(15.dp)).background(if(active) Brush.horizontalGradient(Brand.strong) else Brush.horizontalGradient(listOf(Color.Transparent,Color.Transparent))),contentAlignment=Alignment.Center) {
       Icon(icon,null,Modifier.size(20.dp),tint=if(active) Color.White else Muted)
      }
      Text(label,style=MaterialTheme.typography.labelMedium.copy(fontSize=labelSize,lineHeight=labelSize*1.4f),fontWeight=if(active) FontWeight.SemiBold else FontWeight.Medium,color=if(active) MaterialTheme.colorScheme.onSurface else Muted,maxLines=1,overflow=TextOverflow.Ellipsis)
     }
    }
   }
  }
 }
}

private fun speakersLabel(n: Int)=when { n%100 in 11..14->"$n говорящих";n%10==1->"$n говорящий";else->"$n говорящих" }
fun languageShort(summary: String?)=when(summary) { "en"->"EN";"mixed"->"RU + EN";else->"RU" }

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
 LazyColumn(Modifier.fillMaxSize().testTag("library-list"),contentPadding=PaddingValues(start=20.dp,end=20.dp,top=12.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
  item { Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
   Text("Библиотека",style=MaterialTheme.typography.headlineLarge,modifier=Modifier.weight(1f).semantics { heading() })
   IconButton(onClick=onImport,modifier=Modifier.testTag("library-import")) { Icon(Icons.Outlined.Add,"Импорт аудио или видео",tint=Blue) }
   IconButton(onClick=onSettings,modifier=Modifier.testTag("appearance-settings")) { Icon(Icons.Outlined.Settings,"Настройки оформления",tint=Muted) }
  } }
  item { OutlinedTextField(query,{query=it},Modifier.fillMaxWidth().testTag("library-search"),placeholder={Text("Найти запись или слово")},leadingIcon={Icon(Icons.Outlined.Search,null)},trailingIcon={if(query.isNotEmpty()) IconButton(onClick={query=""}) { Icon(Icons.Outlined.Close,"Очистить поиск") }},singleLine=true,shape=ProductShape.control) }
  item { Text(if(searchPending) "Поиск по стенограммам…" else if(loaded) "${shown.size} ${when { shown.size%100 in 11..14->"записей";shown.size%10==1->"запись";shown.size%10 in 2..4->"записи";else->"записей" }}" else "Загружаем библиотеку…",style=MaterialTheme.typography.labelLarge,color=Muted) }
  if(loaded && shown.isEmpty() && !searchPending) item { Column(Modifier.padding(vertical=36.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
   Icon(Icons.Outlined.AudioFile,null,tint=Muted)
   Text(if(query.isBlank()) "Пока нет записей" else "Ничего не найдено",style=MaterialTheme.typography.titleLarge)
   Text(if(query.isBlank()) "Запишите голос на вкладке «Запись» или добавьте аудио и видео. Всё останется на устройстве." else "Попробуйте другое слово или очистите поиск.",style=MaterialTheme.typography.bodyMedium,color=Muted)
   if(query.isBlank()) GradientButton("Импорт аудио или видео",Icons.Outlined.Add,onImport,modifier=Modifier.padding(top=8.dp).fillMaxWidth())
  } }
  items(shown,key={it.id}) { r ->
   LibraryCard(vm,r,menuOpen=menu==r.id,onOpen={vm.selected.value=r.id},onMenu={menu=r.id},onDismissMenu={menu=null},onRename={menu=null;renaming=r},onDelete={menu=null;deleting=r})
  }
 }
 if(deleting!=null) AlertDialog(onDismissRequest={if(!deletingBusy) deleting=null},title={Text("Удалить запись?")},text={Text("«${deleting!!.title}»\n\nУдалятся стенограмма и принадлежащая записи локальная копия аудио. Исходник импорта и модели сохранятся.")},confirmButton={TextButton(enabled=!deletingBusy,onClick={deletingBusy=true;vm.deleteRecording(deleting!!.id) { ok -> deletingBusy=false;if(ok) deleting=null }},modifier=Modifier.testTag("confirm-delete-recording")) { Text(if(deletingBusy) "Удаляем…" else "Удалить",color=MaterialTheme.colorScheme.error) }},dismissButton={TextButton(enabled=!deletingBusy,onClick={deleting=null}) { Text("Отмена") }})
 if(renaming!=null) { var value by remember(renaming!!.id) { mutableStateOf(renaming!!.title) };AlertDialog(onDismissRequest={renaming=null},title={Text("Название записи")},text={OutlinedTextField(value,{value=it},label={Text("Название")},modifier=Modifier.testTag("recording-title-editor"))},confirmButton={TextButton(onClick={vm.title(renaming!!.id,value);renaming=null}) { Text("Сохранить") }},dismissButton={TextButton(onClick={renaming=null}) { Text("Отмена") }}) }
}

/** Title; "02:48 · 2 говорящих · RU"; the first line of text. Status appears only when not ready. */
@Composable private fun LibraryCard(vm: AppViewModel,r: Recording,menuOpen: Boolean,onOpen: ()->Unit,onMenu: ()->Unit,onDismissMenu: ()->Unit,onRename: ()->Unit,onDelete: ()->Unit) {
 val ready=r.status=="READY"
 val segments by remember(r.id,ready) { if(ready) vm.dao.segments(r.id) else kotlinx.coroutines.flow.flowOf(emptyList()) }.collectAsStateWithLifecycle(emptyList())
 val speakers=remember(segments) { segments.map { it.speakerId }.filter { it>=0 }.distinct().size }
 // The opening of the conversation: short first replies ("Да,") are joined with the next ones.
 val firstLine=remember(segments) {
  val text=StringBuilder()
  for(s in segments) { val t=s.text.trim();if(t.isEmpty()) continue;if(text.isNotEmpty()) text.append(' ');text.append(t);if(text.length>=80) break }
  text.toString().take(160).ifEmpty { null }
 }
 val language=remember(r.diagnostics) { languageShort(ru.replika.domain.TranscriptLanguage.fromDiagnostics(r.diagnostics)) }
 val meta=buildList {
  if(r.durationMs>0) add(audioClock(r.durationMs))
  if(ready && speakers>0) add(speakersLabel(speakers))
  if(ready) add(language) else add(SimpleDateFormat("d MMM, HH:mm",Locale("ru")).format(Date(r.createdAt)))
 }.joinToString(" · ")
 val error=r.status=="ERROR"
 Surface(color=SurfaceBase,shape=ProductShape.panel,modifier=Modifier.fillMaxWidth().testTag("recording-${r.id}").clip(ProductShape.panel).clickable(onClick=onOpen)) {
  Row(Modifier.padding(start=16.dp,top=14.dp,bottom=14.dp,end=4.dp),verticalAlignment=Alignment.Top,horizontalArrangement=Arrangement.spacedBy(14.dp)) {
   Box(Modifier.padding(top=2.dp).size(40.dp).clip(CircleShape).background(if(error) SolidColor(MaterialTheme.colorScheme.errorContainer) else Brush.linearGradient(Brand.strong)),contentAlignment=Alignment.Center) {
    Icon(if(ready) Icons.Outlined.GraphicEq else if(error) Icons.Outlined.ErrorOutline else Icons.Outlined.AudioFile,null,tint=if(error) MaterialTheme.colorScheme.error else Color.White,modifier=Modifier.size(20.dp))
   }
   Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
    Text(r.title,style=MaterialTheme.typography.titleMedium,maxLines=2,overflow=TextOverflow.Ellipsis)
    Text(meta,color=Muted,style=MaterialTheme.typography.bodySmall,modifier=Modifier.testTag("recording-meta-${r.id}"))
    if(ready && firstLine!=null) Text(firstLine,color=Muted,style=MaterialTheme.typography.bodyMedium,maxLines=2,overflow=TextOverflow.Ellipsis,modifier=Modifier.testTag("recording-preview-${r.id}"))
    if(!ready) Text(r.phase,color=if(error) MaterialTheme.colorScheme.error else Blue,style=MaterialTheme.typography.labelMedium,maxLines=2)
   }
   Box { IconButton(onClick=onMenu,modifier=Modifier.size(48.dp).testTag("recording-menu-${r.id}")) { Icon(Icons.Outlined.MoreVert,"Действия с записью ${r.title}",tint=Muted) }
    DropdownMenu(expanded=menuOpen,onDismissRequest=onDismissMenu) {
     DropdownMenuItem(text={Text("Переименовать")},onClick=onRename)
     DropdownMenuItem(text={Text(if(r.status in setOf("PROCESSING","QUEUED","CANCELLING")) "Сначала отмените обработку" else "Удалить запись")},enabled=r.status !in setOf("PROCESSING","QUEUED","CANCELLING"),onClick=onDelete)
    }
   }
  }
 }
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
