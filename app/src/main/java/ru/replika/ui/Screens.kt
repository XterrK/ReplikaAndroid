@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package ru.replika.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
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
import androidx.compose.ui.*
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.*
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.selected
import kotlinx.coroutines.flow.first
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.common.*
import androidx.media3.exoplayer.ExoPlayer
import kotlinx.coroutines.*
import ru.replika.data.*
import ru.replika.domain.Exporter
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

fun clock(ms: Long)="%02d:%02d".format(Locale.ROOT,ms.coerceAtLeast(0)/60000,ms.coerceAtLeast(0)/1000%60)
@Composable fun ReplikaRoot(vm: AppViewModel) {
 val recordings by vm.recordings.collectAsStateWithLifecycle()
 val selected by vm.selected.collectAsStateWithLifecycle()
 val error by vm.error.collectAsStateWithLifecycle()
 var screen by rememberSaveable { mutableStateOf("library") }
 val context=LocalContext.current
 val import=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { it?.let(vm::importAudio) }
 val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { if(it) { screen="recording";vm.startRecording() } else vm.error.value="Для записи нужен доступ к микрофону. Можно импортировать аудиофайл." }
 val notifications=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
 LaunchedEffect(Unit) { if(Build.VERSION.SDK_INT>=33) notifications.launch(Manifest.permission.POST_NOTIFICATIONS) }
 BackHandler(enabled=selected!=null || screen!="library") { if(selected!=null) vm.selected.value=null else if(screen=="recording" && vm.isRecording.value) vm.stopRecording(true) else screen="library" }
 Scaffold(containerColor=Ink,bottomBar={ if(selected==null && screen!="recording") NavigationBar(containerColor=Ink) {
  NavigationBarItem(selected=screen=="library",onClick={screen="library"},icon={Icon(Icons.Outlined.GraphicEq,null)},label={Text("Записи")})
  NavigationBarItem(selected=screen=="models",onClick={screen="models";vm.refreshModels()},icon={Icon(Icons.Outlined.Memory,null)},label={Text("Модели")})
 } }) { padding ->
  Box(Modifier.fillMaxSize().padding(padding)) {
   val rec=recordings.firstOrNull { it.id==selected }
   when {
    rec!=null -> Workspace(vm,rec,onBack={vm.selected.value=null})
    screen=="recording" -> RecordingScreen(vm) { if(vm.isRecording.value) vm.stopRecording(true);screen="library" }
    screen=="models" -> ModelsScreen(vm,recordings)
    else -> Library(vm,recordings,onImport={import.launch(arrayOf("audio/*","application/octet-stream"))},onRecord={
     if(ContextCompat.checkSelfPermission(context,Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED) { screen="recording";vm.startRecording() } else permission.launch(Manifest.permission.RECORD_AUDIO)
    })
   }
  }
 }
 if(error!=null) AlertDialog(onDismissRequest={vm.error.value=null},title={Text("Не удалось завершить действие")},text={Text(error!!)},confirmButton={TextButton(onClick={vm.error.value=null}) { Text("Понятно") }})
}
@Composable fun Eyebrow(text: String) { Text(text,style=MaterialTheme.typography.labelMedium,color=Mint,letterSpacing=2.sp) }
@Composable fun Library(vm: AppViewModel,records: List<Recording>,onImport: ()->Unit,onRecord: ()->Unit) {
 var query by rememberSaveable { mutableStateOf("") };var matching by remember { mutableStateOf(emptyList<String>()) }
 LaunchedEffect(query) { matching=if(query.isBlank()) emptyList() else vm.dao.search(query) }
 val shown=records.filter { query.isBlank() || it.title.contains(query,true) || it.id in matching }
 LazyColumn(contentPadding=PaddingValues(24.dp),verticalArrangement=Arrangement.spacedBy(20.dp)) {
  item { Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically) { Eyebrow("R E P L I K A");Text("●  OFFLINE",color=Muted,style=MaterialTheme.typography.labelSmall) } }
  item { Column { Text("Каждое слово\nможно проверить.",fontSize=34.sp,lineHeight=39.sp,fontWeight=FontWeight.SemiBold);Spacer(Modifier.height(12.dp));Text("Из разговора — в ясный диалог.\nТолько на вашем устройстве.",color=Muted,lineHeight=23.sp) } }
  item { Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Brush.linearGradient(listOf(Color(0xFF223A76),Color(0xFF182346)))).padding(22.dp)) {
   Icon(Icons.Outlined.GraphicEq,null,tint=Blue,modifier=Modifier.size(32.dp));Spacer(Modifier.height(14.dp));Text("Начните с голоса",fontSize=22.sp,fontWeight=FontWeight.Medium);Spacer(Modifier.height(6.dp));Text("Запишите разговор или откройте аудио",color=Muted);Spacer(Modifier.height(20.dp))
   Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) { Button(onClick=onRecord) { Icon(Icons.Outlined.Mic,null);Spacer(Modifier.width(6.dp));Text("Записать") };OutlinedButton(onClick=onImport) { Text("Импорт") } }
  } }
  item { OutlinedTextField(query,{query=it},Modifier.fillMaxWidth(),placeholder={Text("Поиск по записям и словам")},leadingIcon={Icon(Icons.Outlined.Search,null)},singleLine=true,shape=RoundedCornerShape(16.dp)) }
  item { Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) { Text("Библиотека",fontSize=22.sp,fontWeight=FontWeight.SemiBold);Text("${shown.size} записей",color=Muted) } }
  if(shown.isEmpty()) item { Text(if(query.isBlank()) "Здесь появятся ваши разговоры. Исходное аудио и исправления сохраняются локально." else "Ничего не найдено",color=Muted,modifier=Modifier.padding(vertical=16.dp)) }
  items(shown,key={it.id}) { r -> Row(Modifier.fillMaxWidth().clickable { vm.selected.value=r.id }.padding(vertical=10.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(14.dp)) {
   Box(Modifier.size(48.dp).clip(RoundedCornerShape(14.dp)).background(Color(0xFF182641)),contentAlignment=Alignment.Center) { Icon(if(r.status=="READY") Icons.Outlined.GraphicEq else Icons.Outlined.AudioFile,null,tint=Blue) }
   Column(Modifier.weight(1f)) { Text(r.title,maxLines=2,overflow=TextOverflow.Ellipsis,fontWeight=FontWeight.Medium);Spacer(Modifier.height(5.dp));Text("${SimpleDateFormat("dd MMM · HH:mm",Locale("ru")).format(Date(r.createdAt))}  ·  ${clock(r.durationMs)}",color=Muted,style=MaterialTheme.typography.bodySmall);Text(r.phase,color=if(r.status=="READY") Mint else if(r.status=="ERROR") MaterialTheme.colorScheme.error else Blue,style=MaterialTheme.typography.labelSmall) };Icon(Icons.Outlined.ChevronRight,null,tint=Muted)
  };HorizontalDivider(color=Color(0xFF1B263B)) }
 }
}
@Composable fun RecordingScreen(vm: AppViewModel,onBack: ()->Unit) {
 val running by vm.isRecording.collectAsStateWithLifecycle();val paused by vm.paused.collectAsStateWithLifecycle();val elapsed by vm.elapsed.collectAsStateWithLifecycle();val levels by vm.levels.collectAsStateWithLifecycle()
 Column(Modifier.fillMaxSize().padding(24.dp),horizontalAlignment=Alignment.CenterHorizontally) {
  Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) { IconButton(onClick=onBack) { Icon(Icons.Outlined.ArrowBack,"Назад") };Text("Новая запись",fontSize=22.sp) }
  Spacer(Modifier.weight(1f));Eyebrow(if(paused) "ПАУЗА" else if(running) "СЛУШАЕМ ВНИМАТЕЛЬНО" else "ГОТОВО К ЗАПИСИ")
  Spacer(Modifier.height(24.dp));Text(clock(elapsed),fontSize=64.sp,fontWeight=FontWeight.Light)
  Spacer(Modifier.height(32.dp));Waveform(levels,0f,Modifier.fillMaxWidth().height(140.dp),Mint) {}
  Spacer(Modifier.height(24.dp));Text("Реальный уровень микрофона\nПри уходе с экрана запись ставится на паузу",color=Muted,lineHeight=24.sp)
  Spacer(Modifier.weight(1f));Row(horizontalArrangement=Arrangement.spacedBy(16.dp)) {
   if(running) { OutlinedButton(onClick=vm::pauseRecording) { Icon(if(paused) Icons.Outlined.PlayArrow else Icons.Outlined.Pause,null);Text(if(paused) "Продолжить" else "Пауза") };Button(onClick=onBack) { Text("Сохранить") } }
   else Button(onClick=vm::startRecording) { Text("Записать") }
  };Spacer(Modifier.height(16.dp));TextButton(onClick={vm.stopRecording(false);onBack()}) { Text("Отменить запись",color=Muted) }
 }
}
@Composable fun Waveform(peaks: List<Float>,position: Float,modifier: Modifier,color: Color=Blue,onSeek: (Float)->Unit) {
 Canvas(modifier.pointerInput(peaks) { detectTapGestures { onSeek((it.x/size.width).coerceIn(0f,1f)) } }) {
  val n=peaks.size.coerceAtLeast(1);val step=size.width/n
  peaks.forEachIndexed { i,amp -> val h=(amp.coerceIn(0f,1f)*size.height).coerceAtLeast(2f);drawLine(if(i.toFloat()/n<=position) color else color.copy(alpha=0.35f),Offset(i*step,size.height/2-h/2),Offset(i*step,size.height/2+h/2),strokeWidth=(step*0.62f).coerceAtLeast(1f),cap=StrokeCap.Round) }
  if(peaks.isEmpty()) drawLine(Muted.copy(alpha=0.3f),Offset(0f,size.height/2),Offset(size.width,size.height/2),1f)
  if(position>0) drawLine(Color.White,Offset(size.width*position,0f),Offset(size.width*position,size.height),2f)
 }
}
@Composable fun ModelsScreen(vm: AppViewModel,records: List<Recording>) {
 val backend by vm.backend.collectAsStateWithLifecycle()
 val models by vm.models.collectAsStateWithLifecycle();val progress by vm.modelProgress.collectAsStateWithLifecycle()
 val pack=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { it?.let(vm::importPack) }
 var download by remember { mutableStateOf<String?>(null) };var delete by remember { mutableStateOf<String?>(null) }
 LazyColumn(contentPadding=PaddingValues(24.dp),verticalArrangement=Arrangement.spacedBy(20.dp)) {
  item { Eyebrow("ЛОКАЛЬНЫЙ ИНТЕЛЛЕКТ");Spacer(Modifier.height(12.dp));Text("Модели",fontSize=36.sp,fontWeight=FontWeight.SemiBold);Spacer(Modifier.height(8.dp));Text("Одна установка. Дальше — без сети.\nЗаписи никуда не отправляются.",color=Muted,lineHeight=24.sp) }
  item { Text("ASR backend",color=Muted);Spacer(Modifier.height(8.dp));FilterChip(selected=backend=="giga-v2",onClick={vm.selectBackend("giga-v2")},label={Text("GigaAM v2 · русский")});Text("sherpa-onnx 2.0.1 · CPU · 2 потока",color=Muted,style=MaterialTheme.typography.bodySmall);Spacer(Modifier.height(8.dp));FilterChip(selected=backend=="whisper-tiny",onClick={vm.selectBackend("whisper-tiny")},label={Text("Whisper tiny · whisper.cpp · русский")}) }
  if(models.isEmpty()) item { LinearProgressIndicator(Modifier.fillMaxWidth());Text("Проверяем файлы моделей…",color=Muted) }
  items(models) { m -> Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Color(0xFF141F34)).padding(18.dp)) {
   Text(m.title,fontWeight=FontWeight.Medium);Spacer(Modifier.height(6.dp));Text("${m.bytes/1024/1024} / ${m.expected/1024/1024} МБ · ${if(m.installed) "SHA-256 проверен" else "не установлен или повреждён"}",color=if(m.installed) Mint else Muted,style=MaterialTheme.typography.bodySmall)
   Row { TextButton(onClick={download=m.id},enabled=progress==null) { Text(if(m.installed) "Проверить / восстановить" else "Загрузить") };if(m.bytes>0) TextButton(onClick={delete=m.id},enabled=progress==null) { Text("Удалить",color=Muted) } }
  } }
  if(progress!=null) item { LinearProgressIndicator(Modifier.fillMaxWidth());Text(progress!!,color=Blue);TextButton(onClick=vm::cancelModelDownload) { Text("Отменить загрузку") } }
  item { OutlinedButton(onClick={pack.launch(arrayOf("application/zip","application/octet-stream"))},enabled=progress==null) { Icon(Icons.Outlined.FolderOpen,null);Spacer(Modifier.width(8.dp));Text("Импорт offline pack") };Spacer(Modifier.height(8.dp));Text("ZIP проверяется по встроенному манифесту. Неполные веса не запускаются.",color=Muted,style=MaterialTheme.typography.bodySmall) }
  item { BenchmarkPanel(vm,records) }
  item { Text("Диагностика",fontSize=24.sp);Spacer(Modifier.height(10.dp));Text(records.firstOrNull { it.diagnostics.isNotBlank() }?.diagnostics?:"После обработки здесь появятся устройство, время стадий, RTF и размер моделей. WER / CER / DER без эталона: N/A.",color=Muted,style=MaterialTheme.typography.bodySmall) }
 }
 if(download!=null) AlertDialog(onDismissRequest={download=null},title={Text("Загрузить модель?")},text={Text("Весовые файлы будут загружены из официальных releases k2-fsa/sherpa-onnx на GitHub либо из репозитория GGML-моделей автора whisper.cpp на Hugging Face. Может потребоваться до 600 МБ трафика и дополнительное место для распаковки. Аудио остаётся локальным.")},confirmButton={TextButton(onClick={vm.download(download!!);download=null}) { Text("Загрузить") }},dismissButton={TextButton(onClick={download=null}) { Text("Отмена") }})
 if(delete!=null) AlertDialog(onDismissRequest={delete=null},title={Text("Удалить веса модели?")},text={Text("Для следующей обработки потребуется снова установить этот набор.")},confirmButton={TextButton(onClick={vm.deleteModel(delete!!);delete=null}) { Text("Удалить") }},dismissButton={TextButton(onClick={delete=null}) { Text("Отмена") }})
}

@Composable fun Workspace(vm: AppViewModel,rec: Recording,onBack: ()->Unit) {
 val allRows by vm.segments.collectAsStateWithLifecycle();val allSpeakers by vm.speakers.collectAsStateWithLifecycle()
 val rows=allRows.filter { it.recordingId==rec.id };val speakers=allSpeakers.filter { it.recordingId==rec.id }
 val context=LocalContext.current
 val player=remember(rec.id) { ExoPlayer.Builder(context).build().apply { setMediaItem(MediaItem.fromUri(Uri.fromFile(File(rec.audioPath))));prepare() } }
 var position by remember { mutableLongStateOf(0L) };var playing by remember { mutableStateOf(false) };var speed by remember { mutableFloatStateOf(1f) }
 var stopAt by remember { mutableStateOf<Long?>(null) }
 DisposableEffect(player) { val listener=object: Player.Listener { override fun onPlayerError(error: PlaybackException) { vm.error.value="Воспроизведение: ${error.message}" } };player.addListener(listener);onDispose { player.release() } }
 LaunchedEffect(player) { while(isActive) { position=player.currentPosition;playing=player.isPlaying;stopAt?.let { if(position>=it) { player.pause();stopAt=null } };delay(100) } }
 fun seek(ms: Long) { stopAt=null;position=ms.coerceIn(0,rec.durationMs.coerceAtLeast(0));player.seekTo(position) }
 fun playSegment(row: SegmentRow) { seek(row.startMs);stopAt=row.endMs.coerceAtMost(rec.durationMs);player.play() }
 fun name(id: Int)=speakers.firstOrNull { it.speakerId==id }?.name?:if(id<0) "Неизвестный" else "Участник ${id+1}"
 var review by rememberSaveable(rec.id) { mutableStateOf(false) };var filter by rememberSaveable(rec.id) { mutableStateOf<Int?>(null) }
 var edit by remember { mutableStateOf<SegmentRow?>(null) };var rename by remember { mutableStateOf<Int?>(null) };var titleEdit by remember { mutableStateOf(false) }
 var export by remember { mutableStateOf(false) };var expected by rememberSaveable(rec.id) { mutableStateOf(if(rec.expectedSpeakers>0) rec.expectedSpeakers.toString() else "2") };var automatic by rememberSaveable(rec.id) { mutableStateOf(rec.expectedSpeakers<0) }
 val ready=rec.status=="READY"
 val warnings=rows.filter { it.reasons!="[]" && !it.reviewed }
 val visible=rows.filter { (filter==null || filter==it.speakerId) && (!review || (it.reasons!="[]" && !it.reviewed)) }
 val listState=rememberLazyListState();val scope=rememberCoroutineScope()
 val active=rows.firstOrNull { position>=it.startMs && position<it.endMs }
 val peaks=remember(rec.peaks) { rec.peaks.split(',').mapNotNull { it.toFloatOrNull() } }
 var autoFollow by rememberSaveable { mutableStateOf(false) }
 LaunchedEffect(active?.id,autoFollow) { if(autoFollow && active!=null) { val i=visible.indexOfFirst { it.id==active.id };if(i>=0) listState.animateScrollToItem(i+3) } }
 Column(Modifier.fillMaxSize()) {
  Row(Modifier.fillMaxWidth().padding(horizontal=12.dp),verticalAlignment=Alignment.CenterVertically) {
   IconButton(onClick=onBack) { Icon(Icons.Outlined.ArrowBack,"Библиотека") }
   Column(Modifier.weight(1f).clickable { titleEdit=true }) { Text(rec.title,fontSize=18.sp,fontWeight=FontWeight.SemiBold,maxLines=1,overflow=TextOverflow.Ellipsis);Text("${clock(rec.durationMs)}  ·  ${if(ready) "${if(rec.backend=="whisper-tiny") "Whisper tiny" else "GigaAM v2"} · локально" else rec.phase}",style=MaterialTheme.typography.labelSmall,color=Muted) }
   if(ready) IconButton(onClick={export=true}) { Icon(Icons.Outlined.IosShare,"Экспорт") }
  }
  if(!ready) {
   Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(28.dp),verticalArrangement=Arrangement.Center) {
    Eyebrow(if(rec.status=="ERROR") "НУЖНО ВНИМАНИЕ" else "КАЖДОЕ СЛОВО ВАЖНО")
    Spacer(Modifier.height(24.dp));Icon(Icons.Outlined.GraphicEq,null,tint=Blue,modifier=Modifier.size(70.dp));Spacer(Modifier.height(24.dp));Text(rec.phase,fontSize=28.sp,lineHeight=34.sp,fontWeight=FontWeight.Medium)
    Spacer(Modifier.height(16.dp));Text(rec.error?:"Аудио обрабатывается на устройстве. Участники обозначаются условными номерами, а не реальными именами.",color=Muted,lineHeight=24.sp)
    Spacer(Modifier.height(24.dp))
    if(rec.status in setOf("PROCESSING","QUEUED","CANCELLING")) { LinearProgressIndicator(Modifier.fillMaxWidth());Spacer(Modifier.height(16.dp));if(rec.status=="CANCELLING") Text("Текущий нативный этап нельзя прервать мгновенно. Дождитесь завершения операции.",color=Muted) else OutlinedButton(onClick={vm.cancel(rec.id)}) { Text("Отменить обработку") } }
    else {
     Text("Количество говорящих",fontWeight=FontWeight.Medium)
     FilterChip(selected=automatic,onClick={automatic=true},label={Text("Автоматически")})
     FilterChip(selected=!automatic,onClick={automatic=false},label={Text("Указано пользователем")})
     val validCount=expected.toIntOrNull()?.let { it in 1..20 }==true
     if(!automatic) OutlinedTextField(expected,{expected=it.filter(Char::isDigit).take(2)},label={Text("Число говорящих")},supportingText={Text("От 1 до 20. Это подсказка для кластеризации.")},isError=!validCount,singleLine=true,modifier=Modifier.fillMaxWidth())
     Spacer(Modifier.height(16.dp));Button(onClick={vm.process(rec.id,if(automatic) -1 else expected.toInt())},enabled=automatic || validCount,modifier=Modifier.fillMaxWidth().height(52.dp)) { Text(if(rec.status=="IMPORTED") "Создать стенограмму" else "Повторить обработку") }
     Text("Установите выбранный ASR, VAD и диаризацию в разделе «Модели».",color=Muted,modifier=Modifier.padding(top=12.dp),style=MaterialTheme.typography.bodySmall)
    }
   }
  } else {
   Column(Modifier.padding(horizontal=24.dp,vertical=12.dp)) {
    Waveform(peaks,position.toFloat()/rec.durationMs.coerceAtLeast(1),Modifier.fillMaxWidth().height(60.dp)) { seek((it*rec.durationMs).toLong()) }
    Spacer(Modifier.height(10.dp))
    Canvas(Modifier.fillMaxWidth().height(10.dp).clip(RoundedCornerShape(4.dp)).pointerInput(rows) { detectTapGestures { seek((it.x/size.width*rec.durationMs).toLong()) } }) {
     rows.forEach { s -> val start=s.startMs.toFloat()/rec.durationMs.coerceAtLeast(1)*size.width;val end=s.endMs.toFloat()/rec.durationMs.coerceAtLeast(1)*size.width;drawRect(speakerColor(s.speakerId),Offset(start,0f),Size((end-start).coerceAtLeast(1f),size.height)) }
    }
    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.SpaceBetween) {
     Text(clock(position),color=Muted,style=MaterialTheme.typography.labelSmall)
     IconButton(onClick={seek(position-10000)}) { Icon(Icons.Outlined.Replay10,"Назад 10 секунд") }
     FilledIconButton(onClick={if(playing) player.pause() else { stopAt=null;player.play() }},modifier=Modifier.size(48.dp)) { Icon(if(playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,if(playing) "Пауза" else "Воспроизвести") }
     IconButton(onClick={seek(position+10000)}) { Icon(Icons.Outlined.Forward10,"Вперёд 10 секунд") }
     TextButton(onClick={speed=when(speed) { 1f->1.25f;1.25f->1.5f;1.5f->2f;else->1f };player.setPlaybackSpeed(speed)}) { Text("${speed}×") }
    }
   }
   HorizontalDivider(color=Color(0xFF22304A))
   LazyRow(contentPadding=PaddingValues(horizontal=24.dp),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
    item { FilterChip(selected=filter==null,onClick={filter=null},label={Text("Все")}) }
    items(rows.map { it.speakerId }.distinct()) { id -> FilterChip(selected=filter==id,onClick={filter=if(filter==id) null else id},label={Text(name(id),color=speakerColor(id))}) }
   }
   Row(Modifier.fillMaxWidth().padding(horizontal=24.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.SpaceBetween) {
    FilterChip(selected=review,onClick={review=!review},label={Text("Smart Review · ${warnings.size}")},leadingIcon={Icon(Icons.Outlined.FactCheck,null,Modifier.size(18.dp))})
    IconToggleButton(checked=autoFollow,onCheckedChange={autoFollow=it}) { Icon(Icons.Outlined.Sync,"Следовать за воспроизведением",tint=if(autoFollow) Blue else Muted) }
    if(review && visible.isNotEmpty()) IconButton(onClick={val next=visible.firstOrNull { it.startMs>position }?:visible.first();seek(next.startMs);scope.launch { val i=visible.indexOfFirst { it.id==next.id };if(i>=0) listState.animateScrollToItem(i+3) };edit=next}) { Icon(Icons.Outlined.SkipNext,"Следующее предупреждение") }
   }
   LazyColumn(state=listState,modifier=Modifier.weight(1f),contentPadding=PaddingValues(start=24.dp,end=24.dp,bottom=28.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
    item { if(review) Text("Вычисляемые признаки для проверки, не вероятность ошибки.",color=Muted,style=MaterialTheme.typography.bodySmall) }
    item { Spacer(Modifier.height(2.dp)) };item { Spacer(Modifier.height(2.dp)) }
    if(visible.isEmpty()) item { Text(if(review) "Нет непроверенных фрагментов с вычисленными предупреждениями." else "Речь не найдена или отфильтрована.",color=Muted,modifier=Modifier.padding(vertical=30.dp)) }
    items(visible,key={it.id}) { row ->
     Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(if(active?.id==row.id) Color(0xFF1B2D50) else Color(0xFF101A2C)).testTag("segment-${row.id}").semantics { selected=active?.id==row.id }.clickable { playSegment(row) }.padding(16.dp)) {
      Row(verticalAlignment=Alignment.CenterVertically) {
       Text(name(row.speakerId),color=speakerColor(row.speakerId),style=MaterialTheme.typography.labelLarge,modifier=Modifier.weight(1f).clickable { rename=row.speakerId })
       Text(clock(row.startMs),style=MaterialTheme.typography.labelSmall,color=Muted)
       IconButton(onClick={edit=row},modifier=Modifier.size(40.dp)) { Icon(Icons.Outlined.MoreHoriz,"Изменить реплику") }
      }
      Text(row.text,fontSize=17.sp,lineHeight=26.sp)
      if(row.reasons!="[]") { Spacer(Modifier.height(8.dp));Text(if(row.reviewed) "✓ Проверено вручную" else row.domain().reasons.joinToString(" · "),color=if(row.reviewed) Mint else Color(0xFFFFC58A),style=MaterialTheme.typography.bodySmall) }
      if(row.edited) Text("Исправлено вручную",color=Muted,style=MaterialTheme.typography.labelSmall)
     }
    }
   }
  }
 }
 if(edit!=null) {
  val row=edit!!;var text by remember(row.id) { mutableStateOf(row.text) };var speaker by remember(row.id) { mutableIntStateOf(row.speakerId) };var checked by remember(row.id) { mutableStateOf(row.reviewed) };var saving by remember(row.id) { mutableStateOf(false) };val focusManager=LocalFocusManager.current
  ModalBottomSheet(onDismissRequest={edit=null},sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),containerColor=Color(0xFF131E33)) {
   Column(Modifier.fillMaxWidth().imePadding().verticalScroll(rememberScrollState()).padding(24.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
    Text("Проверить фрагмент",fontSize=24.sp,fontWeight=FontWeight.SemiBold);Text("${Exporter.stamp(row.startMs)} — ${Exporter.stamp(row.endMs)}",color=Muted)
    if(row.reasons!="[]") Text(row.domain().reasons.joinToString("\n"),color=Color(0xFFFFC58A))
    OutlinedButton(onClick={playSegment(row)}) { Icon(Icons.Outlined.PlayArrow,null);Text("Прослушать участок") }
    OutlinedTextField(text,{text=it},Modifier.fillMaxWidth().heightIn(max=200.dp),label={Text("Текст реплики")})
    Text("Говорящий",color=Muted)
    LazyRow(horizontalArrangement=Arrangement.spacedBy(8.dp)) { items((listOf(-1)+rows.map { it.speakerId }+((rows.maxOfOrNull { it.speakerId }?:-1)+1)).distinct()) { id -> FilterChip(selected=speaker==id,onClick={speaker=id},label={Text(name(id))}) } }
    Row(verticalAlignment=Alignment.CenterVertically) { Checkbox(checked,{checked=it});Text("Фрагмент проверен") }
    Button(onClick={saving=true;focusManager.clearFocus();vm.edit(row,text,speaker,checked) { ok -> saving=false;if(ok) edit=null }},enabled=!saving,modifier=Modifier.fillMaxWidth().height(50.dp)) { Text(if(saving) "Сохраняем…" else "Сохранить исправления") }
   }
  }
 }
 if(rename!=null) { val id=rename!!;var value by remember(id) { mutableStateOf(name(id)) };AlertDialog(onDismissRequest={rename=null},title={Text("Имя участника")},text={Column { Text("Это ваша подпись, не идентификация по голосу.",color=Muted);OutlinedTextField(value,{value=it},singleLine=true) }},confirmButton={TextButton(onClick={vm.rename(rec.id,id,value);rename=null}) { Text("Сохранить") }},dismissButton={TextButton(onClick={rename=null}) { Text("Отмена") }}) }
 if(titleEdit) { var value by remember { mutableStateOf(rec.title) };AlertDialog(onDismissRequest={titleEdit=false},title={Text("Название записи")},text={OutlinedTextField(value,{value=it})},confirmButton={TextButton(onClick={vm.title(rec.id,value);titleEdit=false}) { Text("Сохранить") }}) }
 if(export) ModalBottomSheet(onDismissRequest={export=false},containerColor=Color(0xFF131E33)) {
  Column(Modifier.padding(24.dp)) { Text("Экспорт стенограммы",fontSize=24.sp);Text("С именами, метками и вашими исправлениями",color=Muted);Spacer(Modifier.height(16.dp))
   listOf("txt","srt","json").forEach { format -> TextButton(onClick={
    scope.launch {
     try {
      val saved=vm.dao.recording(rec.id)?:error("Запись недоступна")
      val savedRows=vm.dao.segmentList(rec.id).map { it.domain() }
      val savedSpeakers=vm.dao.speakers(rec.id).first()
      fun savedName(id: Int)=savedSpeakers.firstOrNull { it.speakerId==id }?.name?:if(id<0) "Неизвестный" else "Участник ${id+1}"
      val content=when(format) { "txt"->Exporter.txt(saved.title,savedRows,::savedName);"srt"->Exporter.srt(savedRows,::savedName);else->org.json.JSONObject(Exporter.json(saved.title,savedRows,::savedName)).put("recordingId",saved.id).put("diagnostics",if(saved.diagnostics.isNotBlank()) org.json.JSONObject(saved.diagnostics) else org.json.JSONObject()).toString(2) }
      val file=withContext(Dispatchers.IO) { File(context.cacheDir,"exports").apply { mkdirs() }.let { File(it,"replika-${rec.id}.$format").apply { writeText(content) } } }
      val uri=FileProvider.getUriForFile(context,"${context.packageName}.files",file)
      context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType(if(format=="json") "application/json" else "text/plain").putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),"Передать стенограмму"));export=false
     } catch(e: Exception) { vm.error.value=e.message }
    }
   },modifier=Modifier.fillMaxWidth()) { Text(format.uppercase(),fontSize=20.sp);Spacer(Modifier.weight(1f));Icon(Icons.Outlined.ArrowOutward,null) } }
  }
 }
}
