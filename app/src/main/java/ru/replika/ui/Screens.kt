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
 val selected by vm.selected.collectAsStateWithLifecycle();val error by vm.error.collectAsStateWithLifecycle();val notice by vm.notice.collectAsStateWithLifecycle()
 var screen by rememberSaveable { mutableStateOf("library") };val context=LocalContext.current;val snackbar=remember { SnackbarHostState() }
 val import=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { it?.let(vm::importAudio) }
 val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { if(it) { screen="recording";vm.startRecording() } else vm.error.value="Для записи разрешите доступ к микрофону в настройках приложения. Аудиофайл можно импортировать без этого разрешения." }
 val notifications=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
 LaunchedEffect(Unit) { if(Build.VERSION.SDK_INT>=33) notifications.launch(Manifest.permission.POST_NOTIFICATIONS) }
 LaunchedEffect(notice) { notice?.let { message ->
  val result=snackbar.showSnackbar(message,if(vm.undoAvailable.value) "Отменить правку" else null,withDismissAction=true,duration=SnackbarDuration.Long)
  if(result==SnackbarResult.ActionPerformed) vm.undoLastEdit()
  if(vm.notice.value==message) vm.clearNotice()
 } }
 BackHandler(enabled=selected!=null || screen!="library") {
  if(selected!=null) vm.selected.value=null else { if(screen=="recording" && vm.isRecording.value) vm.stopRecording(true);screen="library" }
 }
 Scaffold(containerColor=Ink,snackbarHost={SnackbarHost(snackbar,Modifier.testTag("app-notice"))},bottomBar={ if(selected==null && screen!="recording") NavigationBar(containerColor=Ink,tonalElevation=0.dp) {
  NavigationBarItem(selected=screen=="library",onClick={screen="library"},icon={Icon(Icons.Outlined.GraphicEq,null)},label={Text("Записи")})
  NavigationBarItem(selected=screen=="models",onClick={screen="models";vm.refreshModels()},icon={Icon(Icons.Outlined.Memory,null)},label={Text("Модели")})
 } }) { padding ->
  Box(Modifier.fillMaxSize().padding(padding)) {
   val rec=recordings.firstOrNull { it.id==selected }
   when {
    rec!=null -> Workspace(vm,rec,onBack={vm.selected.value=null})
    selected!=null && !loaded -> LoadingContent("Открываем запись…")
    selected!=null -> Column(Modifier.fillMaxSize().padding(24.dp),verticalArrangement=Arrangement.Center) { Text("Запись недоступна",style=MaterialTheme.typography.headlineSmall);Text("Она могла быть удалена. Остальные записи доступны в библиотеке.",color=Muted);Button(onClick={vm.selected.value=null}) { Text("В библиотеку") } }
    screen=="recording" -> RecordingScreen(vm) { if(vm.isRecording.value) vm.stopRecording(true);screen="library" }
    screen=="models" -> ModelsScreen(vm,recordings)
    else -> Library(vm,recordings,loaded=loaded,onImport={import.launch(arrayOf("audio/*","application/octet-stream"))},onRecord={
     if(ContextCompat.checkSelfPermission(context,Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED) { screen="recording";vm.startRecording() } else permission.launch(Manifest.permission.RECORD_AUDIO)
    })
   }
  }
 }
 if(error!=null) AlertDialog(onDismissRequest={vm.error.value=null},title={Text("Не удалось завершить действие")},text={Text(error!!)},confirmButton={TextButton(onClick={vm.error.value=null}) { Text("Понятно") }})
}
@Composable fun LoadingContent(label: String) { Column(Modifier.fillMaxSize().padding(24.dp).testTag("loading-content"),verticalArrangement=Arrangement.Center,horizontalAlignment=Alignment.CenterHorizontally) { CircularProgressIndicator(Modifier.size(28.dp),strokeWidth=2.dp);Spacer(Modifier.height(16.dp));Text(label,color=Muted) } }
@Composable fun Eyebrow(text: String) { Text(text,style=MaterialTheme.typography.labelMedium,color=Mint,letterSpacing=1.sp) }
@Composable fun Library(vm: AppViewModel,records: List<Recording>,loaded: Boolean,onImport: ()->Unit,onRecord: ()->Unit) {
 var query by rememberSaveable { mutableStateOf("") };var matching by remember { mutableStateOf(emptyList<String>()) };var matchingQuery by remember { mutableStateOf<String?>(null) }
 var menu by remember { mutableStateOf<String?>(null) };var deleting by remember { mutableStateOf<Recording?>(null) };var renaming by remember { mutableStateOf<Recording?>(null) };var deletingBusy by remember { mutableStateOf(false) }
 LaunchedEffect(query) {
  val needle=query
  if(needle.isBlank()) { matching=emptyList();matchingQuery=needle }
  else { delay(180);vm.dao.searchFlow(needle).collect { matching=it;matchingQuery=needle } }
 }
 val searchPending=query.isNotBlank() && matchingQuery!=query
 val shown=records.filter { query.isBlank() || it.title.contains(query,true) || (matchingQuery==query && it.id in matching) }
 LazyColumn(Modifier.fillMaxSize().testTag("library-list"),contentPadding=PaddingValues(start=20.dp,end=20.dp,top=20.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
  item { Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically) {
   Column { Text("REPLIKA",style=MaterialTheme.typography.labelMedium,color=Muted,letterSpacing=2.sp);Spacer(Modifier.height(4.dp));Text("Библиотека",style=MaterialTheme.typography.headlineLarge,fontWeight=FontWeight.SemiBold) }
   Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(5.dp)) { Icon(Icons.Outlined.PhonelinkLock,null,Modifier.size(16.dp),tint=Mint);Text("Локально",style=MaterialTheme.typography.labelMedium,color=Mint) }
  } }
  item { Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(10.dp)) {
   Button(onClick=onRecord,modifier=Modifier.weight(1f).heightIn(min=50.dp)) { Icon(Icons.Outlined.Mic,null,Modifier.size(20.dp));Spacer(Modifier.width(6.dp));Text("Записать") }
   FilledTonalButton(onClick=onImport,modifier=Modifier.weight(1f).heightIn(min=50.dp)) { Icon(Icons.Outlined.Add,null,Modifier.size(20.dp));Spacer(Modifier.width(6.dp));Text("Импорт") }
  } }
  item { OutlinedTextField(query,{query=it},Modifier.fillMaxWidth().testTag("library-search"),placeholder={Text("Название или слова в записи")},leadingIcon={Icon(Icons.Outlined.Search,null)},trailingIcon={if(query.isNotEmpty()) IconButton(onClick={query=""}) { Icon(Icons.Outlined.Close,"Очистить поиск") }},singleLine=true,shape=RoundedCornerShape(12.dp)) }
  item { Text(if(searchPending) "Поиск по стенограммам…" else if(loaded) "${shown.size} ${when { shown.size%100 in 11..14->"записей";shown.size%10==1->"запись";shown.size%10 in 2..4->"записи";else->"записей" }}" else "Загружаем библиотеку…",style=MaterialTheme.typography.labelLarge,color=Muted) }
  if(loaded && shown.isEmpty() && !searchPending) item { Column(Modifier.padding(vertical=36.dp)) { Icon(Icons.Outlined.AudioFile,null,tint=Muted);Spacer(Modifier.height(12.dp));Text(if(query.isBlank()) "Пока нет записей" else "Ничего не найдено",style=MaterialTheme.typography.titleLarge);Spacer(Modifier.height(8.dp));Text(if(query.isBlank()) "Запишите разговор или импортируйте WAV, MP3, M4A. Звук и стенограмма останутся на устройстве." else "Попробуйте другое слово или очистите поиск.",color=Muted) } }
  items(shown,key={it.id}) { r ->
   Row(Modifier.fillMaxWidth().testTag("recording-${r.id}").clickable { vm.selected.value=r.id }.padding(vertical=4.dp),verticalAlignment=Alignment.Top,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
    Box(Modifier.padding(top=3.dp).size(40.dp).clip(RoundedCornerShape(12.dp)).background(SurfaceBase),contentAlignment=Alignment.Center) { Icon(if(r.status=="READY") Icons.Outlined.GraphicEq else if(r.status=="ERROR") Icons.Outlined.ErrorOutline else Icons.Outlined.AudioFile,null,tint=if(r.status=="ERROR") MaterialTheme.colorScheme.error else Blue,modifier=Modifier.size(22.dp)) }
    Column(Modifier.weight(1f).padding(vertical=2.dp)) {
     Text(r.title,style=MaterialTheme.typography.titleMedium,maxLines=2,overflow=TextOverflow.Ellipsis)
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
@Composable fun RecordingScreen(vm: AppViewModel,onBack: ()->Unit) {
 val running by vm.isRecording.collectAsStateWithLifecycle();val paused by vm.paused.collectAsStateWithLifecycle();val elapsed by vm.elapsed.collectAsStateWithLifecycle();val levels by vm.levels.collectAsStateWithLifecycle()
 Column(Modifier.fillMaxSize()) {
  Row(Modifier.fillMaxWidth().padding(horizontal=8.dp,vertical=4.dp),verticalAlignment=Alignment.CenterVertically) { IconButton(onClick=onBack) { Icon(Icons.Outlined.ArrowBack,"Назад") };Text("Новая запись",style=MaterialTheme.typography.titleLarge) }
  Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal=24.dp,vertical=24.dp),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(20.dp)) {
   Text(if(paused) "На паузе" else if(running) "Идёт запись" else "Готово к записи",color=if(paused) Muted else Mint,style=MaterialTheme.typography.titleMedium)
   Text(clock(elapsed),fontSize=56.sp,fontWeight=FontWeight.Light,modifier=Modifier.testTag("recording-timer"))
   RecordingHistory(levels,paused,Modifier.fillMaxWidth().height(100.dp))
   Text(if(paused) "Продолжите, когда будете готовы" else if((levels.lastOrNull()?:0f)<=0f) "Ожидание сигнала микрофона" else "Уровень микрофона",color=Muted,style=MaterialTheme.typography.bodyMedium)
   Text("Звук сохраняется на устройстве. При уходе в фон запись автоматически ставится на паузу.",color=Muted,style=MaterialTheme.typography.bodySmall)
  }
  Column(Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=12.dp),verticalArrangement=Arrangement.spacedBy(8.dp),horizontalAlignment=Alignment.CenterHorizontally) {
   if(running) {
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(10.dp)) {
     FilledTonalButton(onClick=vm::pauseRecording,modifier=Modifier.weight(1f).heightIn(min=52.dp)) { Text(if(paused) "Продолжить" else "Пауза") }
     Button(onClick=onBack,modifier=Modifier.weight(1f).heightIn(min=52.dp)) { Text("Сохранить") }
    }
   } else Button(onClick=vm::startRecording,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)) { Text("Записать") }
   TextButton(onClick={vm.stopRecording(false);onBack()},modifier=Modifier.heightIn(min=48.dp)) { Text("Отменить запись",color=Muted) }
  }
 }
}
@Composable private fun RecordingHistory(levels: List<Float>,paused: Boolean,modifier: Modifier) {
 Canvas(modifier.testTag("recording-level-history")) {
  val slots=70;val step=size.width/slots;val stroke=(step*.55f).coerceIn(1f,3.dp.toPx());val mid=size.height/2
  drawLine(SurfaceLine,Offset(0f,mid),Offset(size.width,mid),1f)
  levels.takeLast(slots).forEachIndexed { i,amp -> val h=(amp.coerceIn(0f,1f)*size.height*.9f).coerceAtLeast(1f);val x=(i+.5f)*step
   drawLine(if(paused) Muted else Mint,Offset(x,mid-h/2),Offset(x,mid+h/2),strokeWidth=stroke,cap=StrokeCap.Round)
  }
 }
}
@Composable fun Waveform(peaks: List<Float>,position: Float,modifier: Modifier,color: Color=Blue,onSeek: (Float)->Unit) {
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
  if(shown.isEmpty()) drawLine(Muted.copy(alpha=.25f),Offset(0f,mid),Offset(size.width,mid),1f)
  drawLine(playheadColor.copy(alpha=.8f),Offset(size.width*position.coerceIn(0f,1f),0f),Offset(size.width*position.coerceIn(0f,1f),size.height),1.dp.toPx())
 }
}
