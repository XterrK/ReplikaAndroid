@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
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
 val rowsById=remember(rows) { rows.associateBy { it.id } }
 val shownGroups=remember(groups,filter) { groups.filter { filter==null || it.speakerId==filter } }
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
   player.setMediaItem(MediaItem.fromUri(Uri.fromFile(File(rec.audioPath))))
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
   val index=shownGroups.indexOfFirst { group -> group.parts.any { it.id==active.id } }
   if(index>=0) listState.animateScrollToItem(index)
  }
 }
 BoxWithConstraints(Modifier.fillMaxSize()) {
  val compact=maxHeight<680.dp || LocalDensity.current.fontScale>=1.25f
  Column(Modifier.fillMaxSize().testTag("workspace")) {
   Row(Modifier.fillMaxWidth().padding(horizontal=8.dp,vertical=4.dp),verticalAlignment=Alignment.CenterVertically) {
    IconButton(onClick=onBack) { Icon(Icons.Outlined.ArrowBack,"Библиотека") }
    Column(Modifier.weight(1f).clickable { titleEditing=true }.padding(vertical=6.dp).testTag("workspace-title")) {
     Text(rec.title,style=MaterialTheme.typography.titleMedium,maxLines=1,overflow=TextOverflow.Ellipsis)
     Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
      Text(if(rec.durationMs>0) audioClock(rec.durationMs) else "Аудиофайл",style=MaterialTheme.typography.labelSmall,color=Muted)
      LocalOnlyLabel()
      if(ready) Text(if(rec.backend=="whisper-tiny") "Whisper" else "GigaAM",style=MaterialTheme.typography.labelSmall,color=Muted)
     }
    }
    if(ready) IconButton(onClick={exporting=true},modifier=Modifier.testTag("workspace-export")) { Icon(Icons.Outlined.IosShare,"Экспорт") }
   }
   if(!ready) {
    ProcessingPane(vm,rec,Modifier.weight(1f))
   } else {
    AudioDock(
     peaks,rows,rec.durationMs,position,playing,speed,stopAt,compact,
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
    if(!reading) Row(Modifier.fillMaxWidth().padding(start=20.dp,end=8.dp),verticalAlignment=Alignment.CenterVertically) {
     Text(if(filter==null) "Диалог" else name(filter!!),style=MaterialTheme.typography.titleSmall,maxLines=1,overflow=TextOverflow.Ellipsis,modifier=Modifier.weight(1f))
     IconButton(onClick={choosingFilter=true}) { Icon(Icons.Outlined.FilterList,"Фильтр говорящих",tint=if(filter!=null) Blue else Muted) }
     IconToggleButton(checked=follow,onCheckedChange={follow=it}) { Icon(Icons.Outlined.Sync,"Следовать за воспроизведением",tint=if(follow) Blue else Muted) }
     TextButton(onClick={review=!review},modifier=Modifier.heightIn(min=48.dp).testTag("smart-review-toggle")) {
      Icon(Icons.Outlined.FactCheck,null,Modifier.size(18.dp));Spacer(Modifier.width(6.dp))
      Text("Smart Review"+if(pending>0) " · "+pending else "",style=MaterialTheme.typography.labelMedium,color=if(review) Mint else Blue)
     }
    }
    HorizontalDivider(color=SurfaceLine.copy(alpha=.65f))
    when {
     !loaded -> Column(Modifier.fillMaxWidth().weight(1f).padding(24.dp).testTag("transcript-loading"),verticalArrangement=Arrangement.spacedBy(12.dp)) {
      LinearProgressIndicator(Modifier.fillMaxWidth());Text("Загружаем стенограмму…",style=MaterialTheme.typography.bodyMedium,color=Muted)
     }
     reading -> LazyColumn(Modifier.weight(1f).testTag("reading-text"),contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(20.dp)) {
      items(groups,key={it.id}) { group ->
       SelectionContainer { Text(group.text,style=MaterialTheme.typography.bodyLarge,modifier=Modifier.fillMaxWidth().testTag("reading-paragraph-"+group.id)) }
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
     ) { OutlinedButton(onClick={listenAll()},modifier=Modifier.heightIn(min=48.dp)) { Text("Прослушать запись") } }
     visible.isEmpty() -> ProductEmptyState(
      "У этого участника нет реплик","Выберите другого участника или вернитесь к полному диалогу.",
      Modifier.weight(1f)
     ) { TextButton(onClick={filter=null}) { Text("Все участники") } }
     else -> LazyColumn(
      state=listState,modifier=Modifier.weight(1f).testTag("transcript-list"),
      contentPadding=PaddingValues(top=8.dp,bottom=24.dp)
     ) {
      itemsIndexed(shownGroups,key={_,group -> group.id}) { index,group ->
       val parts=group.parts.mapNotNull { rowsById[it.id] }
       if(parts.size==1) {
        val row=parts.single()
        DialogueRow(row,::name,active?.id==row.id,index<shownGroups.lastIndex,onPlay={play(row)},onEdit={editing=row},onRename={renaming=row.speakerId})
       } else LogicalDialogue(group,parts,::name,active?.id,onPlay={play(it)},onEdit={editing=it},onRename={renaming=group.speakerId})
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

@Composable private fun AudioDock(
 peaks: List<Float>,rows: List<SegmentRow>,duration: Long,position: Long,playing: Boolean,speed: Float,stopAt: Long?,compact: Boolean,
 onSeek: (Long)->Unit,onToggle: ()->Unit,onBack: ()->Unit,onForward: ()->Unit,onSpeed: ()->Unit
) {
 Column(Modifier.fillMaxWidth().padding(horizontal=16.dp,vertical=4.dp).background(SurfaceBase,ProductShape.panel).padding(horizontal=12.dp,vertical=10.dp)) {
  val currentSeek by rememberUpdatedState(onSeek)
  Box(
   Modifier.fillMaxWidth().height(if(compact) 56.dp else 64.dp).testTag("audio-waveform")
    .semantics {
     contentDescription="Аудиодорожка и участники. Цвета совпадают с метками говорящих в тексте."
     progressBarRangeInfo=ProgressBarRangeInfo((position.toFloat()/duration.coerceAtLeast(1)).coerceIn(0f,1f),0f..1f)
     setProgress { value -> currentSeek((value.coerceIn(0f,1f)*duration).toLong());true }
    }.pointerInput(duration) { detectTapGestures { currentSeek((it.x/size.width*duration).toLong()) } }
  ) {
   Waveform(peaks,position.toFloat()/duration.coerceAtLeast(1),Modifier.fillMaxWidth().height(if(compact) 44.dp else 52.dp).clearAndSetSemantics {},Blue) { currentSeek((it*duration).toLong()) }
   Box(Modifier.fillMaxWidth().align(Alignment.BottomCenter)) { SpeakerTimeline(rows,duration,position) }
  }
  Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
   Column(Modifier.weight(1f)) {
    Text(if(compact) audioClock(position,duration) else audioClock(position,duration)+" / "+audioClock(duration),style=MaterialTheme.typography.labelSmall,color=Muted,maxLines=1,modifier=Modifier.testTag("playback-clock"))
    if(stopAt!=null) Text("До "+formatElapsed(stopAt),style=MaterialTheme.typography.labelSmall,color=Blue,maxLines=1)
    else if(!compact) Text("Цвет — участник",style=MaterialTheme.typography.labelSmall,color=Muted,maxLines=1)
   }
   IconButton(onClick=onBack) { Icon(Icons.Outlined.Replay10,"Назад 10 секунд") }
   FilledIconButton(onClick=onToggle,modifier=Modifier.size(48.dp)) { Icon(if(playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,if(playing) "Пауза" else "Воспроизвести") }
   IconButton(onClick=onForward) { Icon(Icons.Outlined.Forward10,"Вперёд 10 секунд") }
   TextButton(onClick=onSpeed,modifier=Modifier.widthIn(min=48.dp).heightIn(min=48.dp).testTag("playback-speed"),contentPadding=PaddingValues(horizontal=4.dp)) { Text(speed.toString()+"×",style=MaterialTheme.typography.labelMedium) }
  }
 }
}

@Composable private fun SpeakerTimeline(rows: List<SegmentRow>,duration: Long,position: Long) {
 Canvas(
  Modifier.fillMaxWidth().height(6.dp).clip(ProductShape.control).background(SurfaceLine)
   .testTag("speaker-timeline").clearAndSetSemantics {}
 ) {
  rows.forEach { row ->
   val a=(row.startMs.toFloat()/duration.coerceAtLeast(1)).coerceIn(0f,1f)*size.width
   val b=(row.endMs.toFloat()/duration.coerceAtLeast(1)).coerceIn(0f,1f)*size.width
   drawRect(speakerColor(row.speakerId),Offset(a,0f),Size((b-a).coerceAtLeast(0f),size.height))
  }
  val x=(position.toFloat()/duration.coerceAtLeast(1)).coerceIn(0f,1f)*size.width
  drawLine(Blue,Offset(x,0f),Offset(x,size.height),2.dp.toPx())
 }
}

@Composable private fun LogicalDialogue(group: LogicalTurn,parts: List<SegmentRow>,name: (Int)->String,activeId: String?,onPlay: (SegmentRow)->Unit,onEdit: (SegmentRow)->Unit,onRename: ()->Unit) {
 Column(Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=12.dp).testTag("logical-turn-"+group.id)) {
  Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(10.dp)) {
   SpeakerAvatar(group.speakerId)
   Text(name(group.speakerId),style=MaterialTheme.typography.labelMedium,color=speakerColor(group.speakerId),modifier=Modifier.weight(1f).heightIn(min=48.dp).clickable(onClick=onRename).wrapContentHeight())
   Text(segmentIntervalLabel(group.startMs,group.endMs),style=MaterialTheme.typography.labelSmall,color=Muted)
  }
  parts.forEach { row ->
   Row(Modifier.fillMaxWidth().background(if(activeId==row.id) Blue.copy(alpha=.09f) else Ink).testTag("segment-"+row.id).semantics { selected=activeId==row.id }.clickable { onPlay(row) },verticalAlignment=Alignment.CenterVertically) {
    Column(Modifier.weight(1f)) {
     Text(row.text,style=MaterialTheme.typography.bodyLarge)
     Text(segmentIntervalLabel(row.startMs,row.endMs)+(if(row.edited) " · Изменено" else "")+(if(row.reviewed) " · Проверено" else if(reviewIssues(row).isNotEmpty()) " · Нужна проверка" else ""),style=MaterialTheme.typography.labelSmall,color=Muted)
    }
    IconButton(onClick={onEdit(row)},modifier=Modifier.size(48.dp)) { Icon(Icons.Outlined.MoreHoriz,"Изменить реплику",tint=Muted) }
   }
  }
 }
}

@Composable private fun DialogueRow(row: SegmentRow,name: (Int)->String,active: Boolean,hasNext: Boolean,onPlay: ()->Unit,onEdit: ()->Unit,onRename: ()->Unit) {
 val issues=remember(row.reasons,row.speakerId) { reviewIssues(row) }
 Row(
  Modifier.fillMaxWidth().background(if(active) Blue.copy(alpha=.09f) else Ink)
   .drawBehind {
    if(active) drawRect(Blue,Offset.Zero,Size(3.dp.toPx(),size.height))
    if(hasNext) drawLine(SurfaceLine.copy(alpha=.7f),Offset(32.dp.toPx(),34.dp.toPx()),Offset(32.dp.toPx(),size.height),1.dp.toPx())
   }.testTag("segment-"+row.id).semantics { selected=active }.clickable(onClick=onPlay).padding(start=20.dp,end=12.dp,top=12.dp,bottom=12.dp),
  horizontalArrangement=Arrangement.spacedBy(12.dp),verticalAlignment=Alignment.Top
 ) {
  SpeakerAvatar(row.speakerId,Modifier.padding(top=4.dp))
  Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(5.dp)) {
   Row(verticalAlignment=Alignment.CenterVertically) {
    Text(name(row.speakerId),style=MaterialTheme.typography.labelMedium,color=speakerColor(row.speakerId),modifier=Modifier.weight(1f).heightIn(min=48.dp).clickable(onClick=onRename).wrapContentHeight(Alignment.CenterVertically),maxLines=2,overflow=TextOverflow.Ellipsis)
    IconButton(onClick=onEdit,modifier=Modifier.size(48.dp)) { Icon(Icons.Outlined.MoreHoriz,"Изменить реплику",Modifier.size(20.dp),tint=Muted) }
   }
   Text(segmentIntervalLabel(row.startMs,row.endMs),style=MaterialTheme.typography.labelSmall,color=if(active) Blue else Muted)
   Text(row.text,style=MaterialTheme.typography.bodyLarge)
   if(row.edited || row.reviewed || issues.isNotEmpty()) {
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(10.dp),verticalAlignment=Alignment.CenterVertically) {
     if(row.reviewed) Text("Проверено",style=MaterialTheme.typography.labelSmall,color=Mint)
     if(row.edited) Text("Изменено",style=MaterialTheme.typography.labelSmall,color=Muted)
     if(!row.reviewed && issues.isNotEmpty()) Text("Нужна проверка",style=MaterialTheme.typography.labelSmall,color=Amber)
    }
   }
  }
 }
}

@Composable private fun ProcessingPane(vm: AppViewModel,rec: Recording,modifier: Modifier=Modifier) {
 var speakerMode by rememberSaveable(rec.id) { mutableStateOf(if(rec.expectedSpeakers==1) "single" else if(rec.expectedSpeakers>1) "fixed" else "automatic") }
 var threads by rememberSaveable(rec.id) { mutableIntStateOf(2) }
 var count by rememberSaveable(rec.id) { mutableStateOf(if(rec.expectedSpeakers>0) rec.expectedSpeakers.toString() else "2") }
 var details by remember(rec.id) { mutableStateOf(false) }
 val busy=rec.status in setOf("QUEUED","PROCESSING","CANCELLING")
 Column(modifier.fillMaxWidth().testTag("processing-pane").imePadding().verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(20.dp)) {
  Spacer(Modifier.height(8.dp))
  when {
   busy -> {
    Text(if(rec.status=="CANCELLING") "Отмена запрошена" else "Создаём стенограмму",style=MaterialTheme.typography.headlineMedium)
    Column(Modifier.fillMaxWidth().background(SurfaceBase,ProductShape.panel).padding(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
     Text(rec.phase,style=MaterialTheme.typography.titleMedium,modifier=Modifier.testTag("processing-phase"))
     LinearProgressIndicator(Modifier.fillMaxWidth())
     Text(if(rec.status=="CANCELLING") "Текущую нативную операцию нельзя прервать мгновенно. Завершаем её; запись останется в библиотеке." else "Аудио обрабатывается на устройстве. Можно вернуться к библиотеке — задание продолжится.",style=MaterialTheme.typography.bodyMedium,color=Muted)
    }
    if(rec.status!="CANCELLING") OutlinedButton(onClick={vm.cancel(rec.id)},modifier=Modifier.heightIn(min=48.dp)) { Text("Отменить обработку") }
   }
   else -> {
    Text(if(rec.status=="ERROR") "Не удалось обработать аудио" else if(rec.status=="CANCELLED") "Обработка остановлена" else "Готово к обработке",style=MaterialTheme.typography.headlineMedium)
    Text(if(rec.status=="ERROR") vm.errorMessage("Обработка",rec.error) else "Выберите число участников. Аудио и стенограмма сохраняются только на устройстве.",style=MaterialTheme.typography.bodyMedium,color=Muted)
    if(rec.status=="ERROR" && !rec.error.isNullOrBlank()) {
     TextButton(onClick={details=!details}) { Text(if(details) "Скрыть подробности" else "Технические подробности") }
     if(details) Text(rec.error.orEmpty(),style=MaterialTheme.typography.bodySmall,color=Muted,modifier=Modifier.testTag("processing-technical-error"))
    }
    Column(Modifier.fillMaxWidth().background(SurfaceBase,ProductShape.panel).padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
     Text("Количество говорящих",style=MaterialTheme.typography.titleMedium)
     listOf("single" to "Один говорящий", "fixed" to "Фиксированное число говорящих", "automatic" to "Автоматически").forEach { (key,label) ->
      Row(Modifier.fillMaxWidth().heightIn(min=48.dp).selectable(speakerMode==key,role=Role.RadioButton) { speakerMode=key }.testTag("speakers-"+key),verticalAlignment=Alignment.CenterVertically) { RadioButton(speakerMode==key,null);Text(label,style=MaterialTheme.typography.bodyMedium) }
     }
     if(speakerMode=="single") Text("Для монолога. Все фрагменты будут у одного участника; обработка быстрее.",style=MaterialTheme.typography.bodySmall,color=Muted)
     if(speakerMode=="automatic") Text("Число участников может быть неточным. Для известного состава выберите другой режим.",style=MaterialTheme.typography.bodySmall,color=Muted)
     if(speakerMode=="fixed") OutlinedTextField(count,{count=it.filter(Char::isDigit).take(2)},label={Text("Число говорящих")},supportingText={Text("От 2 до 20 участников.")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Number),singleLine=true,isError=count.toIntOrNull()?.let { it in 2..20 }!=true,modifier=Modifier.fillMaxWidth().testTag("speaker-count"))
     Text("Нагрузка на процессор",style=MaterialTheme.typography.labelLarge)
     Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
      FilterChip(selected=threads==1,onClick={threads=1},label={Text("Умеренная")})
      FilterChip(selected=threads==2,onClick={threads=2},label={Text("Обычная")})
     }
    }
    Button(onClick={vm.process(rec.id,when(speakerMode) { "single"->1;"fixed"->count.toInt();else->-1 },threads)},enabled=speakerMode!="fixed" || count.toIntOrNull()?.let { it in 2..20 }==true,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)) { Text(if(rec.status=="IMPORTED") "Создать стенограмму" else "Повторить обработку") }
    Text("Нужны выбранная модель распознавания и VAD; для нескольких участников — модели говорящих. Управление установкой — в разделе «Модели».",style=MaterialTheme.typography.bodySmall,color=Muted)
   }
  }
 }
}

@Composable private fun TranscriptExport(vm: AppViewModel,rec: Recording,onDismiss: ()->Unit) {
 val context=LocalContext.current
 val app=context.applicationContext as ReplikaApp
 val scope=rememberCoroutineScope()
 var saving by remember(rec.id) { mutableStateOf(false) }
 ModalBottomSheet(onDismissRequest=onDismiss,containerColor=SurfaceBase,sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),modifier=Modifier.testTag("transcript-export")) {
  DarkSheetSystemBars()
  Column(Modifier.fillMaxWidth().navigationBarsPadding().verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
   Text("Экспорт стенограммы",style=MaterialTheme.typography.titleLarge)
   Text("С текущими именами, метками времени и сохранёнными исправлениями.",style=MaterialTheme.typography.bodyMedium,color=Muted)
   listOf("txt" to "Текст для чтения","srt" to "Субтитры с временными метками","json" to "Реплики и диагностика").forEach { (format,description) ->
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
        val content=when(format) {
         "txt" -> Exporter.txt(saved.title,segments,::label)
         "srt" -> Exporter.srt(segments,::label)
         else -> org.json.JSONObject(Exporter.json(saved.title,segments,::label)).put("recordingId",saved.id).put("diagnostics",if(saved.diagnostics.isNotBlank()) org.json.JSONObject(saved.diagnostics) else org.json.JSONObject()).toString(2)
        }
        val file=withContext(Dispatchers.IO) { File(context.cacheDir,"exports").apply { mkdirs() }.let { File(it,"replika-"+rec.id+"."+format).apply { writeText(content) } } }
        val uri=FileProvider.getUriForFile(context,context.packageName+".files",file)
        context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType(if(format=="json") "application/json" else "text/plain").putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),"Передать стенограмму"))
        onDismiss()
       } catch(e: CancellationException) { throw e }
       catch(e: Exception) { vm.reportError("Экспорт",e) }
       finally { saving=false }
      }
     }
    ) {
     Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(3.dp)) { Text(format.uppercase(),style=MaterialTheme.typography.titleMedium);Text(description,style=MaterialTheme.typography.bodySmall,color=Muted) }
     Icon(Icons.Outlined.ArrowOutward,null,Modifier.size(20.dp))
    }
   }
  }
 }
}
