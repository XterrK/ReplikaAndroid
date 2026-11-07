@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class,androidx.compose.material3.ExperimentalMaterial3Api::class)
package ru.replika.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.common.*
import androidx.media3.exoplayer.ExoPlayer
import androidx.room.withTransaction
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import ru.replika.ReplikaApp
import ru.replika.data.*
import ru.replika.domain.Exporter
import ru.replika.domain.TranscriptPresentation
import ru.replika.domain.LogicalTurn
import java.io.File

// Retain the exact version opened by the editor so recreation cannot bypass stale-edit checks.
private val EditorRowSaver=listSaver<SegmentRow?,Any>(
 save={ row -> if(row==null) emptyList() else listOf(row.id,row.recordingId,row.startMs,row.endMs,row.speakerId,row.text,row.source,row.edited,row.reasons,row.reviewed) },
 restore={ values -> if(values.isEmpty()) null else SegmentRow(values[0] as String,values[1] as String,values[2] as Long,values[3] as Long,values[4] as Int,values[5] as String,values[6] as String,values[7] as Boolean,values[8] as String,values[9] as Boolean) }
)

@Composable fun Workspace(vm: AppViewModel,rec: Recording,onBack: ()->Unit) {
 val transcript by vm.transcript.collectAsStateWithLifecycle()
 val loaded=transcript.loaded && transcript.recordingId==rec.id
 val rows=if(loaded) transcript.rows else emptyList()
 val speakers=if(loaded) transcript.speakers else emptyList()
 val context=LocalContext.current
 val lifecycle=LocalLifecycleOwner.current.lifecycle
 val durationNow by rememberUpdatedState(rec.durationMs)
 val player=remember(rec.id) { ExoPlayer.Builder(context).build() }
 var position by rememberSaveable(rec.id) { mutableLongStateOf(0L) }
 var playing by remember(rec.id) { mutableStateOf(false) }
 var speed by rememberSaveable(rec.id) { mutableFloatStateOf(1f) }
 var stopAt by rememberSaveable(rec.id) { mutableStateOf<Long?>(null) }
 var prepared by remember(rec.id) { mutableStateOf(false) }
 var reading by rememberSaveable(rec.id) { mutableStateOf(false) }
 var review by rememberSaveable(rec.id) { mutableStateOf(false) }
 var filter by rememberSaveable(rec.id) { mutableStateOf<Int?>(null) }
 var follow by rememberSaveable(rec.id) { mutableStateOf(false) }
 var editing by rememberSaveable(rec.id,stateSaver=EditorRowSaver) { mutableStateOf<SegmentRow?>(null) }
 var renaming by remember(rec.id) { mutableStateOf<Int?>(null) }
 var titleEditing by remember(rec.id) { mutableStateOf(false) }
 var choosingFilter by remember(rec.id) { mutableStateOf(false) }
 var exporting by remember(rec.id) { mutableStateOf(false) }
 val listState=rememberLazyListState()
 val ready=rec.status=="READY"
 val peaks=remember(rec.peaks) { rec.peaks.split(',').mapNotNull { it.toFloatOrNull() } }
 fun name(id: Int)=speakers.firstOrNull { it.speakerId==id }?.name?:if(id<0) "Неизвестный" else "Участник "+(id+1)
 val choices=remember(rows,speakers) {
  (listOf(-1)+rows.map { it.speakerId }+speakers.map { it.speakerId }).distinct().sorted().map { id ->
   SpeakerChoice(id,speakers.firstOrNull { it.speakerId==id }?.name?:if(id<0) "Неизвестный" else "Участник "+(id+1))
  }
 }
 val clipboard=LocalClipboardManager.current
 val groups=remember(rows) { TranscriptPresentation.groups(rows.map { it.domain() }) }
 val visible=remember(rows,filter) { rows.filter { filter==null || it.speakerId==filter } }
 val pending=remember(rows) { rows.count { !it.reviewed && reviewIssues(it).isNotEmpty() } }
 val active=rows.firstOrNull { position>=it.startMs && position<it.endMs }
 fun seek(ms: Long) { stopAt=null;position=ms.coerceIn(0,rec.durationMs.coerceAtLeast(0));player.seekTo(position) }
 fun play(row: SegmentRow) { if(!ready) return;seek(row.startMs);stopAt=row.endMs.coerceAtMost(rec.durationMs);player.play() }
 fun listenAll() { seek(0);player.play() }
 DisposableEffect(player,lifecycle) {
  val listener=object: Player.Listener {
   override fun onIsPlayingChanged(isPlaying: Boolean) { playing=isPlaying }
   override fun onPlayerError(error: PlaybackException) { playing=false;vm.reportPlaybackError(rec.id,error) }
  }
  val observer=LifecycleEventObserver { _,event -> if(event==Lifecycle.Event.ON_STOP) { position=player.currentPosition;player.pause() } }
  player.addListener(listener);lifecycle.addObserver(observer)
  onDispose { lifecycle.removeObserver(observer);player.removeListener(listener);player.release() }
 }
 LaunchedEffect(player,ready,rec.audioPath) {
  if(ready && !prepared) {
   // Large imports reference the original document (content URI) instead of an app-owned copy.
   player.setMediaItem(MediaItem.fromUri(if(ru.replika.ml.AudioDecoder.isContentUri(rec.audioPath)) Uri.parse(rec.audioPath) else Uri.fromFile(File(rec.audioPath))))
   player.setPlaybackSpeed(speed);player.seekTo(position.coerceIn(0,rec.durationMs.coerceAtLeast(0)));player.prepare();prepared=true
  } else if(!ready) { player.pause();stopAt=null }
 }
 LaunchedEffect(player) {
  while(isActive) {
   position=player.currentPosition.coerceIn(0,durationNow.coerceAtLeast(0));playing=player.isPlaying
   stopAt?.let { end -> if(position>=end) { player.pause();stopAt=null } }
   delay(100)
  }
 }
 LaunchedEffect(active?.id,follow,filter,review,reading) {
  if(follow && !review && !reading && active!=null) {
   val index=visible.indexOfFirst { it.id==active.id }
   if(index>=0) listState.animateScrollToItem(index)
  }
 }
 BoxWithConstraints(Modifier.fillMaxSize()) {
  val compact=maxHeight<680.dp || LocalDensity.current.fontScale>=1.25f
  Column(Modifier.fillMaxSize().testTag("workspace")) {
   // Title gets the full width; language, duration and "local" live in the metadata line below.
   Row(Modifier.fillMaxWidth().padding(start=4.dp,end=4.dp,top=4.dp,bottom=8.dp),verticalAlignment=Alignment.Top) {
    IconButton(onClick=onBack) { Icon(Icons.Outlined.ArrowBack,"Назад в библиотеку") }
    Column(Modifier.weight(1f).padding(top=10.dp,start=4.dp,end=4.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
     Text(rec.title,style=MaterialTheme.typography.titleLarge,maxLines=3,overflow=TextOverflow.Ellipsis,
      modifier=Modifier.clickable(onClickLabel="Переименовать запись") { titleEditing=true }.testTag("workspace-title"))
     FlowRow(horizontalArrangement=Arrangement.spacedBy(12.dp),verticalArrangement=Arrangement.spacedBy(6.dp),itemVerticalAlignment=Alignment.CenterVertically,modifier=Modifier.testTag("workspace-meta")) {
      Text(if(rec.durationMs>0) audioClock(rec.durationMs) else "Аудиофайл",style=MaterialTheme.typography.labelMedium,color=Muted)
      if(ready && rec.backend!="whisper-tiny") TranscriptLanguageAction(vm,rec)
      else if(ready) Text("Whisper",style=MaterialTheme.typography.labelMedium,color=Muted)
      LocalOnlyLabel()
     }
    }
    if(ready) IconButton(onClick={exporting=true},modifier=Modifier.testTag("workspace-export")) { Icon(Icons.Outlined.IosShare,"Экспорт стенограммы") }
   }
   if(!ready) {
    ProcessingPane(vm,rec,Modifier.weight(1f))
   } else {
    AudioDock(
     peaks,rows,rec.durationMs,position,playing,speed,stopAt,compact,minimal=reading || review,
     onSeek={seek(it)},onToggle={if(playing || player.playWhenReady) player.pause() else player.play()},
     onBack={seek(position-10000)},onForward={seek(position+10000)},
     onSpeed={speed=when(speed) { 1f->1.25f;1.25f->1.5f;1.5f->2f;else->1f };player.setPlaybackSpeed(speed)}
    )
    Row(Modifier.fillMaxWidth().padding(horizontal=20.dp),verticalAlignment=Alignment.CenterVertically) {
     SingleChoiceSegmentedButtonRow(Modifier.weight(1f)) {
      SegmentedButton(selected=!reading,onClick={reading=false},shape=SegmentedButtonDefaults.itemShape(0,2),modifier=Modifier.testTag("mode-dialogue")) { Text("Диалог") }
      SegmentedButton(selected=reading,onClick={reading=true;review=false;filter=null},shape=SegmentedButtonDefaults.itemShape(1,2),modifier=Modifier.testTag("mode-reading")) { Text("Чтение") }
     }
     if(reading) IconButton(onClick={clipboard.setText(AnnotatedString(TranscriptPresentation.plain(rows.map { it.domain() })))},modifier=Modifier.testTag("copy-plain-text")) { Icon(Icons.Outlined.ContentCopy,"Копировать чистый текст") }
    }
    // Every tool is labelled: who is shown, auto-scroll during playback, review queue.
    // One scrollable line keeps the transcript high on screen at any font size.
    if(!reading) Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal=20.dp),horizontalArrangement=Arrangement.spacedBy(8.dp),verticalAlignment=Alignment.CenterVertically) {
     FilterChip(selected=filter!=null,onClick={choosingFilter=true},label={Text(if(filter==null) "Все участники" else name(filter!!),maxLines=1,overflow=TextOverflow.Ellipsis,modifier=Modifier.widthIn(max=180.dp))},
      leadingIcon={Icon(Icons.Outlined.FilterList,null,Modifier.size(18.dp))},modifier=Modifier.testTag("speaker-filter"))
     FilterChip(selected=follow,onClick={follow=!follow},label={Text("Автопрокрутка",maxLines=1)},
      leadingIcon={Icon(if(follow) Icons.Outlined.Check else Icons.Outlined.Sync,null,Modifier.size(18.dp))},modifier=Modifier.testTag("follow-playback"))
     FilterChip(selected=review,onClick={review=!review},label={Text("Проверка"+if(pending>0) " · "+pending else "",maxLines=1)},
      leadingIcon={Icon(Icons.Outlined.FactCheck,null,Modifier.size(18.dp))},modifier=Modifier.testTag("smart-review-toggle"))
    }
    HorizontalDivider(color=SurfaceLine.copy(alpha=.65f))
    when {
     !loaded -> Column(Modifier.fillMaxWidth().weight(1f).padding(24.dp).testTag("transcript-loading"),verticalArrangement=Arrangement.spacedBy(12.dp)) {
      LinearProgressIndicator(Modifier.fillMaxWidth());Text("Загружаем стенограмму…",style=MaterialTheme.typography.bodyMedium,color=Muted)
     }
     reading -> LazyColumn(Modifier.weight(1f).testTag("reading-text"),contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(20.dp)) {
      items(groups,key={it.id}) { group ->
       SelectionContainer { Text(group.text,style=MaterialTheme.typography.bodyLarge.copy(fontSize=18.sp,lineHeight=29.sp),modifier=Modifier.fillMaxWidth().testTag("reading-paragraph-"+group.id)) }
      }
     }
     review -> SmartReviewQueue(
      visible,::name,Modifier.weight(1f),onListen={play(it)},onEdit={editing=it},
      onReviewed={row,done -> vm.edit(row,row.text,row.speakerId,true,done)},
      onTranscript={review=false;filter=null},onListenRecording={listenAll()}
     )
     rows.isEmpty() -> ProductEmptyState(
      "В стенограмме нет реплик","Послушайте исходное аудио. Пустой результат не доказывает отсутствия речи.",
      Modifier.weight(1f).testTag("transcript-empty")
     ) { OutlinedButton(shape=ProductShape.control,onClick={listenAll()},modifier=Modifier.heightIn(min=48.dp)) { Text("Прослушать запись") } }
     visible.isEmpty() -> ProductEmptyState(
      "У этого участника нет реплик","Выберите другого участника или вернитесь к полному диалогу.",
      Modifier.weight(1f)
     ) { TextButton(onClick={filter=null}) { Text("Все участники") } }
     else -> LazyColumn(
      state=listState,modifier=Modifier.weight(1f).testTag("transcript-list"),
      contentPadding=PaddingValues(top=8.dp,bottom=24.dp)
     ) {
      itemsIndexed(visible,key={_,row -> row.id}) { index,row ->
       DialogueRow(row,::name,active?.id==row.id,index<visible.lastIndex,onPlay={play(row)},onEdit={editing=row},onRename={renaming=row.speakerId})
      }
     }
    }
   }
  }
 }
 if(editing!=null) TranscriptEditor(vm,editing!!,choices,onListen={val row=editing!!;if(stopAt==row.endMs.coerceAtMost(rec.durationMs) && position>=row.startMs && position<row.endMs) player.play() else play(row)},onPause={player.pause()},playing=playing && stopAt==editing!!.endMs.coerceAtMost(rec.durationMs),onDismiss={editing=null})
 if(choosingFilter) SpeakerPickerDialog(choices,filter,allowAll=true,onChoose={filter=it;choosingFilter=false},onDismiss={choosingFilter=false})
 if(renaming!=null) {
  val id=renaming!!;var value by remember(id) { mutableStateOf(name(id)) }
  AlertDialog(onDismissRequest={renaming=null},containerColor=SurfaceRaised,title={Text("Имя участника")},text={
   Column(verticalArrangement=Arrangement.spacedBy(12.dp)) {
    Text("Это ваша подпись, не идентификация по голосу.",style=MaterialTheme.typography.bodySmall,color=Muted)
    OutlinedTextField(value,{value=it},label={Text("Имя")},singleLine=true,modifier=Modifier.testTag("speaker-rename-text"))
   }
  },confirmButton={TextButton(onClick={vm.rename(rec.id,id,value);renaming=null}) { Text("Сохранить") }},dismissButton={TextButton(onClick={renaming=null}) { Text("Отмена") }})
 }
 if(titleEditing) {
  var value by remember(rec.id) { mutableStateOf(rec.title) }
  AlertDialog(onDismissRequest={titleEditing=false},containerColor=SurfaceRaised,title={Text("Название записи")},text={OutlinedTextField(value,{value=it},label={Text("Название")})},confirmButton={TextButton(onClick={vm.title(rec.id,value);titleEditing=false}) { Text("Сохранить") }},dismissButton={TextButton(onClick={titleEditing=false}) { Text("Отмена") }})
 }
 if(exporting) TranscriptExport(vm,rec,onDismiss={exporting=false})
}

@Composable private fun SpeakerTimeline(rows: List<SegmentRow>,duration: Long,position: Long) {
 val colors=rows.map { speakerColor(it.speakerId) };val blue=Blue
 Canvas(
  Modifier.fillMaxWidth().height(4.dp).clip(ProductShape.control).background(SurfaceLine)
   .testTag("speaker-timeline").clearAndSetSemantics {}
 ) {
  rows.forEachIndexed { index,row ->
   val a=(row.startMs.toFloat()/duration.coerceAtLeast(1)).coerceIn(0f,1f)*size.width
   val b=(row.endMs.toFloat()/duration.coerceAtLeast(1)).coerceIn(0f,1f)*size.width
   drawRect(colors[index],Offset(a,0f),Size((b-a).coerceAtLeast(0f),size.height))
  }
  val x=(position.toFloat()/duration.coerceAtLeast(1)).coerceIn(0f,1f)*size.width
  drawLine(blue,Offset(x,0f),Offset(x,size.height),2.dp.toPx())
 }
}

@Composable private fun DialogueRow(row: SegmentRow,name: (Int)->String,active: Boolean,hasNext: Boolean,onPlay: ()->Unit,onEdit: ()->Unit,onRename: ()->Unit) {
 val blue=Blue;val line=SurfaceLine;val largeFont=LocalDensity.current.fontScale>=1.2f
 val issues=remember(row.reasons,row.speakerId) { reviewIssues(row) }
 Column(Modifier.fillMaxWidth().background(if(active) Blue.copy(alpha=.09f) else Ink)
  .drawBehind { if(active) drawRect(blue,Offset.Zero,Size(3.dp.toPx(),size.height)) }
  .testTag("segment-"+row.id).semantics { selected=active }.clickable(onClick=onPlay).padding(horizontal=20.dp)) {
  Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
   SpeakerAvatar(row.speakerId,Modifier.size(22.dp))
   Column(Modifier.weight(1f).heightIn(min=48.dp).clickable(onClick=onRename),verticalArrangement=Arrangement.Center) {
    Text(name(row.speakerId),style=MaterialTheme.typography.labelMedium,color=speakerColor(row.speakerId),maxLines=2,overflow=TextOverflow.Ellipsis)
    if(largeFont) Text(segmentIntervalLabel(row.startMs,row.endMs),style=MaterialTheme.typography.labelSmall,color=Muted)
   }
   if(!largeFont) Text(segmentIntervalLabel(row.startMs,row.endMs),style=MaterialTheme.typography.labelSmall,color=Muted)
   IconButton(onClick=onEdit,modifier=Modifier.size(48.dp)) { Icon(Icons.Outlined.MoreHoriz,"Изменить реплику",Modifier.size(20.dp),tint=Muted) }
  }
  Text(row.text,style=MaterialTheme.typography.bodyLarge)
  if(row.edited || row.reviewed || issues.isNotEmpty()) {
   Row(Modifier.padding(top=6.dp),horizontalArrangement=Arrangement.spacedBy(10.dp)) {
    if(row.reviewed) Text("Проверено",style=MaterialTheme.typography.labelSmall,color=Mint)
    if(row.edited) Text("Изменено",style=MaterialTheme.typography.labelSmall,color=Muted)
    if(!row.reviewed && issues.isNotEmpty()) Text("Нужна проверка",style=MaterialTheme.typography.labelSmall,color=Amber)
   }
  }
  Spacer(Modifier.height(12.dp))
  if(hasNext) HorizontalDivider(color=line)
 }
}

/** Stage · percent of audio processed · remaining time. Indeterminate until the Worker reports. */
@Composable private fun ProcessingProgressBlock(vm: AppViewModel,rec: Recording) {
 val flow=remember(rec.id) { vm.processingProgress(rec.id) }
 val snapshot by flow.collectAsStateWithLifecycle(null)
 val current=snapshot.takeIf { rec.status=="PROCESSING" }
 val fraction=current?.fraction
 if(fraction!=null) LinearProgressIndicator(progress={ fraction },modifier=Modifier.fillMaxWidth().testTag("processing-progress-bar"))
 else LinearProgressIndicator(Modifier.fillMaxWidth())
 if(current!=null) Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically) {
  Text(current.stage.title+(current.percent?.let { " · $it %" }?:""),style=MaterialTheme.typography.labelLarge,modifier=Modifier.testTag("processing-progress-stage"))
  ru.replika.domain.ProcessingEta.format(current.etaMs)?.let { Text("Осталось $it",style=MaterialTheme.typography.labelLarge,color=Muted,modifier=Modifier.testTag("processing-eta")) }
 }
 if(current!=null && current.audioMs>0 && current.fraction!=null) Text("Обработано ${audioClock(current.processedMs)} из ${audioClock(current.audioMs)}",style=MaterialTheme.typography.bodySmall,color=Muted,modifier=Modifier.testTag("processing-progress-audio"))
}

@Composable private fun ProcessingPane(vm: AppViewModel,rec: Recording,modifier: Modifier=Modifier) {
 var speakerMode by rememberSaveable(rec.id) { mutableStateOf(if(rec.expectedSpeakers==1) "single" else if(rec.expectedSpeakers>1) "fixed" else "automatic") }
 val ordinaryThreads=if(ru.replika.BuildConfig.DEFAULT_CPU_PLAN=="auto_v1") 0 else 2
 var threads by rememberSaveable(rec.id) { mutableIntStateOf(ordinaryThreads) }
 var count by rememberSaveable(rec.id) { mutableStateOf(if(rec.expectedSpeakers>0) rec.expectedSpeakers.toString() else "2") }
 var language by rememberSaveable(rec.id) { mutableStateOf(ru.replika.BuildConfig.DEFAULT_LANGUAGE_MODE) }
 var perSegmentLanguage by rememberSaveable(rec.id) { mutableStateOf(false) }
 var details by remember(rec.id) { mutableStateOf(false) }
 val busy=rec.status in setOf("QUEUED","PROCESSING","CANCELLING")
 Column(modifier.fillMaxWidth().testTag("processing-pane").imePadding().verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(20.dp)) {
  Spacer(Modifier.height(8.dp))
  when {
   busy -> {
    Text(if(rec.status=="CANCELLING") "Отмена запрошена" else "Создаём стенограмму",style=MaterialTheme.typography.headlineMedium)
    Column(Modifier.fillMaxWidth().background(SurfaceBase,ProductShape.panel).padding(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
     Text(rec.phase,style=MaterialTheme.typography.titleMedium,modifier=Modifier.testTag("processing-phase"))
     ProcessingProgressBlock(vm,rec)
     Text(if(rec.status=="CANCELLING") "Текущую нативную операцию нельзя прервать мгновенно. Завершаем её; запись останется в библиотеке." else "Аудио обрабатывается на устройстве. Можно вернуться к библиотеке — задание продолжится.",style=MaterialTheme.typography.bodyMedium,color=Muted)
    }
    if(rec.status!="CANCELLING") OutlinedButton(shape=ProductShape.control,onClick={vm.cancel(rec.id)},modifier=Modifier.heightIn(min=48.dp)) { Text("Отменить обработку") }
   }
   else -> {
    Text(if(rec.status=="ERROR") "Не удалось обработать аудио" else if(rec.status=="CANCELLED") "Обработка остановлена" else "Готово к обработке",style=MaterialTheme.typography.headlineMedium)
    Text(if(rec.status=="ERROR") vm.errorMessage("Обработка",rec.error) else "Выберите число участников. Аудио и стенограмма сохраняются только на устройстве.",style=MaterialTheme.typography.bodyMedium,color=Muted)
    if(rec.status=="ERROR" && !rec.error.isNullOrBlank()) {
     TextButton(onClick={details=!details}) { Text(if(details) "Скрыть подробности" else "Технические подробности") }
     if(details) Text(rec.error.orEmpty(),style=MaterialTheme.typography.bodySmall,color=Muted,modifier=Modifier.testTag("processing-technical-error"))
    }
    Column(Modifier.fillMaxWidth().background(SurfaceBase,ProductShape.panel).padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
     Text("Количество говорящих",style=MaterialTheme.typography.titleMedium)
     Column {
      listOf("automatic" to "Автоматически", "single" to "Один говорящий", "fixed" to "Фиксированное число говорящих").forEach { (key,label) ->
       Row(Modifier.fillMaxWidth().heightIn(min=48.dp).selectable(speakerMode==key,role=Role.RadioButton) { speakerMode=key }.testTag("speakers-"+key),verticalAlignment=Alignment.CenterVertically) { RadioButton(speakerMode==key,null);Spacer(Modifier.width(8.dp));Text(label,style=MaterialTheme.typography.bodyLarge) }
      }
     }
     if(speakerMode=="single") Text("Для монолога. Все фрагменты будут у одного участника; обработка быстрее.",style=MaterialTheme.typography.bodySmall,color=Muted)
     if(speakerMode=="automatic") Text("Число участников может быть неточным. Для известного состава выберите другой режим.",style=MaterialTheme.typography.bodySmall,color=Muted)
     if(speakerMode=="fixed") OutlinedTextField(count,{count=it.filter(Char::isDigit).take(2)},label={Text("Число говорящих")},supportingText={Text("От 2 до 20 участников.")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Number),singleLine=true,isError=count.toIntOrNull()?.let { it in 2..20 }!=true,modifier=Modifier.fillMaxWidth().testTag("speaker-count"))
     LanguageChoice(ru.replika.domain.LanguageMode.fromPersistedId(language),perSegmentLanguage,onLanguage={language=it.wireId},onPerSegment={perSegmentLanguage=it})
     Text("Нагрузка на процессор",style=MaterialTheme.typography.labelLarge)
     Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
      FilterChip(selected=threads==1,onClick={threads=1},label={Text("Умеренная")})
      FilterChip(selected=threads!=1,onClick={threads=ordinaryThreads},label={Text("Обычная")})
     }
    }
    GradientButton(if(rec.status=="IMPORTED") "Создать стенограмму" else "Повторить обработку",Icons.Outlined.AutoAwesome,onClick={vm.process(rec.id,when(speakerMode) { "single"->1;"fixed"->count.toInt();else->-1 },if(threads==1) 1 else ordinaryThreads,
      ru.replika.domain.LanguageMode.fromPersistedId(language),perSegmentLanguage)},enabled=speakerMode!="fixed" || count.toIntOrNull()?.let { it in 2..20 }==true,modifier=Modifier.fillMaxWidth().testTag("create-transcript"))
    Text("Нужны выбранная модель распознавания и VAD; для нескольких участников — модели говорящих. Управление установкой — в разделе «Модели».",style=MaterialTheme.typography.bodySmall,color=Muted)
   }
  }
 }
}

@Composable fun TranscriptExport(vm: AppViewModel,rec: Recording,onDismiss: ()->Unit) {
 val context=LocalContext.current
 val app=context.applicationContext as ReplikaApp
 val scope=rememberCoroutineScope()
 var saving by remember(rec.id) { mutableStateOf(false) }
 ModalBottomSheet(onDismissRequest=onDismiss,containerColor=SurfaceBase,sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),modifier=Modifier.testTag("transcript-export")) {
  DarkSheetSystemBars()
  Column(Modifier.fillMaxWidth().navigationBarsPadding().verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
   Text("Экспорт стенограммы",style=MaterialTheme.typography.titleLarge)
   Text("С сохранёнными исправлениями и метками времени. JSON использует номера участников.",style=MaterialTheme.typography.bodyMedium,color=Muted)
   listOf("txt" to "Текст для чтения","srt" to "Субтитры с временными метками","json" to "Стенограмма в формате жюри","diagnostic-json" to "Имена, исправления и подробности обработки").forEach { (format,description) ->
    TextButton(
     enabled=!saving,modifier=Modifier.fillMaxWidth().heightIn(min=56.dp).testTag("export-"+format),
     onClick={
      saving=true
      scope.launch {
       try {
        val snapshot=withContext(Dispatchers.IO) {
         app.db.withTransaction {
          val saved=vm.dao.recording(rec.id)?:error("Запись недоступна")
          Triple(saved,vm.dao.segmentList(rec.id).map { it.domain() },vm.dao.speakers(rec.id).first())
         }
        }
        val saved=snapshot.first;val segments=snapshot.second;val names=snapshot.third
        fun label(id: Int)=names.firstOrNull { it.speakerId==id }?.name?:if(id<0) "Неизвестный" else "Участник "+(id+1)
        val content=withContext(Dispatchers.Default) { when(format) {
         "txt" -> Exporter.txt(saved.title,segments,::label)
         "srt" -> Exporter.srt(segments,::label)
         "json" -> ru.replika.domain.JuryJson.encode(segments)
         else -> org.json.JSONObject(Exporter.json(saved.title,segments,::label)).put("recordingId",saved.id).put("diagnostics",if(saved.diagnostics.isNotBlank()) org.json.JSONObject(saved.diagnostics) else org.json.JSONObject()).toString(2)
        } }
        val extension=if(format=="diagnostic-json") "diagnostic.json" else format
        val file=withContext(Dispatchers.IO) { File(context.cacheDir,"exports").apply { mkdirs() }.let { File(it,"replika-"+rec.id+"."+extension).apply { writeText(content,Charsets.UTF_8) } } }
        val uri=FileProvider.getUriForFile(context,context.packageName+".files",file)
        context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType(if(extension.endsWith("json")) "application/json" else "text/plain").putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),"Передать стенограмму"))
        onDismiss()
       } catch(e: CancellationException) { throw e }
       catch(e: Exception) { vm.reportError("Экспорт",e) }
       finally { saving=false }
      }
     }
    ) {
     Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(3.dp)) { Text(if(format=="diagnostic-json") "Диагностический JSON" else format.uppercase(),style=MaterialTheme.typography.titleMedium);Text(description,style=MaterialTheme.typography.bodySmall,color=Muted) }
     Icon(Icons.Outlined.ArrowOutward,null,Modifier.size(20.dp))
    }
   }
  }
 }
}
