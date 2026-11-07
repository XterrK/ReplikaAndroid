@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package ru.replika.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.delay
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.distinctUntilChanged
import ru.replika.data.Recording
import kotlin.math.*

@Composable fun RecordingScreen(vm: AppViewModel,onBack: ()->Unit,onStart: ()->Unit=vm::startRecording,onSettings: ()->Unit={},onImport: ()->Unit={},onExport: ()->Unit={},importing: String?=null) {
 val phase by vm.recordingPhase.collectAsStateWithLifecycle()
 val live=phase in setOf(RecordingPhase.STARTING,RecordingPhase.RECORDING,RecordingPhase.PAUSED,RecordingPhase.STOPPING)
 val seconds=remember(vm) { vm.elapsed.map { it/1000*1000 }.distinctUntilChanged() }
 val elapsed by seconds.collectAsStateWithLifecycle(0L)
 val status=when(phase) {
  RecordingPhase.IDLE->"Готово к записи"
  RecordingPhase.PERMISSION_REQUIRED->"Нужен доступ к микрофону"
  RecordingPhase.STARTING->"Включаем микрофон…"
  RecordingPhase.RECORDING->"Идёт запись"
  RecordingPhase.PAUSED->"На паузе"
  RecordingPhase.STOPPING->"Завершаем…"
  RecordingPhase.SAVED->"Готово к записи"
  RecordingPhase.ERROR->"Не удалось записать"
 }
 Box(Modifier.fillMaxSize().testTag("recording-home")) {
  LiveMicrophoneMeter(vm.voiceLevel,phase,Modifier.align(Alignment.CenterEnd).width(64.dp).fillMaxHeight(.88f))
  Column(Modifier.fillMaxSize()) {
  Row(Modifier.fillMaxWidth().padding(start=20.dp,end=8.dp).heightIn(min=56.dp),verticalAlignment=Alignment.CenterVertically) {
   if(live) IconButton(onClick=onBack,enabled=phase!=RecordingPhase.STOPPING,modifier=Modifier.testTag("recording-exit")) { Icon(Icons.Outlined.ArrowBack,"Выйти из записи") }
   Text(if(live) "Запись" else "REPLIKA",style=if(live) MaterialTheme.typography.titleMedium else MaterialTheme.typography.headlineMedium,modifier=Modifier.weight(1f))
   if(!live) IconButton(onClick=onSettings,modifier=Modifier.testTag("appearance-settings")) { Icon(Icons.Outlined.Tune,"Настройки") }
  }
  BoxWithConstraints(Modifier.weight(1f).fillMaxWidth().padding(horizontal=16.dp)) {
   val textBudget=(if(live) 132.dp else 92.dp)*LocalDensity.current.fontScale.coerceAtLeast(1f)
   val orbSize=minOf(maxWidth,maxHeight-textBudget).coerceIn(80.dp,360.dp)
   Column(Modifier.fillMaxSize(),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.Center) {
    Text(status,style=MaterialTheme.typography.titleMedium,color=when(phase) { RecordingPhase.ERROR->MaterialTheme.colorScheme.error;RecordingPhase.RECORDING->Mint;else->Blue },modifier=Modifier.testTag("recording-status"))
    Box(Modifier.fillMaxWidth().height(orbSize),contentAlignment=Alignment.Center) {
     LiquidVoiceOrb(phase,vm.voiceLevel,onStart,Modifier.size(orbSize))
    }
    if(live) Text(clock(elapsed),style=MaterialTheme.typography.bodyLarge.copy(fontSize=44.sp,lineHeight=54.sp,fontWeight=FontWeight.Light,fontFeatureSettings="tnum"),color=Blue,modifier=Modifier.testTag("recording-timer"))
    Text(when(phase) { RecordingPhase.RECORDING->"Говорите, мы слушаем";RecordingPhase.PAUSED->"Продолжите, когда будете готовы";RecordingPhase.PERMISSION_REQUIRED->"Разрешите микрофон, чтобы начать";else->"Нажмите на шар для записи" },style=MaterialTheme.typography.bodySmall,color=Muted,modifier=Modifier.padding(top=6.dp))
   }
  }
  Column(Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=12.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
   when(phase) {
    RecordingPhase.RECORDING,RecordingPhase.PAUSED -> RecordingControls(phase==RecordingPhase.PAUSED,vm::pauseRecording,onBack)
    RecordingPhase.STARTING,RecordingPhase.STOPPING -> LinearProgressIndicator(Modifier.fillMaxWidth().padding(vertical=24.dp))
    else -> Row(horizontalArrangement=Arrangement.spacedBy(12.dp)) {
     FilledTonalButton(shape=ProductShape.control,onClick=onImport,enabled=importing==null,modifier=Modifier.weight(1f).heightIn(min=52.dp).testTag("home-import")) { Icon(Icons.Outlined.Add,null,Modifier.size(20.dp));Spacer(Modifier.width(8.dp));Text("Импорт") }
     OutlinedButton(shape=ProductShape.control,onClick=onExport,modifier=Modifier.weight(1f).heightIn(min=52.dp).testTag("home-export")) { Icon(Icons.Outlined.IosShare,null,Modifier.size(20.dp));Spacer(Modifier.width(8.dp));Text("Экспорт") }
    }
   }
   if(!live) Text("Аудио и видео · всё на устройстве",style=MaterialTheme.typography.bodySmall,color=Muted,modifier=Modifier.align(Alignment.CenterHorizontally))
  }
 }
 }
}

/** Keep the full action names at the user's font size; icons yield space before text does. */
@Composable private fun RecordingControls(paused: Boolean,onPause: ()->Unit,onStop: ()->Unit) {
 val fontScale=LocalDensity.current.fontScale
 BoxWithConstraints(Modifier.fillMaxWidth()) {
  val stacked=fontScale>1.5f || maxWidth<300.dp
  val showIcons=stacked || fontScale<=1.15f
  val pauseLabel=if(paused) "Продолжить" else "Пауза"
  val pauseIcon=if(paused) Icons.Outlined.PlayArrow else Icons.Outlined.Pause
  if(stacked) Column(verticalArrangement=Arrangement.spacedBy(8.dp)) {
   RecordingControl(pauseLabel,if(showIcons) pauseIcon else null,false,onPause,Modifier.fillMaxWidth())
   RecordingControl("Завершить",if(showIcons) Icons.Outlined.Stop else null,true,onStop,Modifier.fillMaxWidth().testTag("recording-stop"))
  } else Row(horizontalArrangement=Arrangement.spacedBy(12.dp)) {
   RecordingControl(pauseLabel,if(showIcons) pauseIcon else null,false,onPause,Modifier.weight(1f))
   RecordingControl("Завершить",if(showIcons) Icons.Outlined.Stop else null,true,onStop,Modifier.weight(1f).testTag("recording-stop"))
  }
 }
}

@Composable private fun RecordingControl(label: String,icon: ImageVector?,primary: Boolean,onClick: ()->Unit,modifier: Modifier) {
 val content: @Composable RowScope.()->Unit = {
  if(icon!=null) { Icon(icon,null,Modifier.size(20.dp));Spacer(Modifier.width(6.dp)) }
  Text(label,maxLines=1,softWrap=false)
 }
 val padding=PaddingValues(horizontal=16.dp,vertical=12.dp)
 if(primary) Button(onClick,modifier.heightIn(min=56.dp),shape=ProductShape.control,contentPadding=padding,content=content)
 else FilledTonalButton(onClick,modifier.heightIn(min=56.dp),shape=ProductShape.control,contentPadding=padding,content=content)
}

/** Edge-rooted amplitude field. Full-height overlay, never a layout gutter or a fake FFT. */
@Composable fun LiveMicrophoneMeter(level: StateFlow<Float>,phase: RecordingPhase,modifier: Modifier=Modifier) {
 val amplitude by level.collectAsStateWithLifecycle()
 val active=phase==RecordingPhase.RECORDING
 val value=if(active) amplitude.coerceIn(0f,1f) else 0f
 val blue=Blue;val violet=Violet
 // A small history gives speech a travelling silhouette. Silence has no fabricated activity.
 val history=remember { FloatArray(48) }
 val tick=remember { mutableIntStateOf(0) }
 val lifecycle=LocalLifecycleOwner.current.lifecycle
 LaunchedEffect(active,lifecycle) {
  history.fill(0f);tick.intValue++
  if(active) lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
   while(true) {
    for(i in history.lastIndex downTo 1) history[i]=history[i-1]
    history[0]=level.value.coerceIn(0f,1f)
    tick.intValue++
    delay(50)
   }
  }
 }
 Canvas(modifier.testTag("microphone-vu").semantics {
  contentDescription="Уровень микрофона"
  stateDescription=if(!active) "Микрофон не записывает" else if(value<.025f) "Тишина" else "Звуковой сигнал"
  progressBarRangeInfo=ProgressBarRangeInfo(value,0f..1f)
 }) {
  tick.intValue
  if(!active) return@Canvas
  val count=(size.height/5.dp.toPx()).toInt().coerceIn(24,180)
  val step=size.height/count
  val signal=value.pow(.68f)
  for(i in 0 until count) {
   val t=(i+.5f)/count
   val taper=sin(PI.toFloat()*t).pow(.55f)
   val old=history[(t*history.lastIndex).toInt()]
   val detail=.28f+.72f*abs(sin(i*1.71f+old*4f)*cos(i*.23f+value*2f))
   val length=1.dp.toPx()+size.width*taper*(signal*.65f+old.pow(.68f)*.35f)*detail
   val y=(i+.5f)*step
   drawLine(Brush.horizontalGradient(listOf(violet.copy(alpha=.14f+signal*.3f),blue.copy(alpha=.35f+signal*.4f)),size.width-length,size.width),Offset(size.width-length,y),Offset(size.width+1f,y),strokeWidth=1.2.dp.toPx(),cap=StrokeCap.Round)
  }
 }
}

@Composable fun HomeExportPicker(records: List<Recording>,onChoose: (Recording)->Unit,onDismiss: ()->Unit) {
 ModalBottomSheet(onDismissRequest=onDismiss,containerColor=SurfaceBase,sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),modifier=Modifier.testTag("home-export-picker")) {
  DarkSheetSystemBars()
  Text("Экспорт стенограммы",style=MaterialTheme.typography.headlineMedium,modifier=Modifier.padding(horizontal=20.dp,vertical=12.dp))
  if(records.isEmpty()) ProductEmptyState("Пока нет готовых стенограмм","Запишите голос или импортируйте аудио и видео, затем создайте стенограмму.")
  else LazyColumn(Modifier.fillMaxWidth().heightIn(max=460.dp).navigationBarsPadding(),contentPadding=PaddingValues(horizontal=20.dp,vertical=8.dp)) {
   items(records,key={it.id}) { rec ->
    ListItem(headlineContent={Text(rec.title,maxLines=2)},supportingContent={Text(audioClock(rec.durationMs))},trailingContent={Icon(Icons.Outlined.ChevronRight,null)},colors=ListItemDefaults.colors(containerColor=SurfaceBase),modifier=Modifier.clickable { onChoose(rec) }.heightIn(min=64.dp).testTag("home-export-"+rec.id))
    HorizontalDivider(color=SurfaceLine)
   }
  }
 }
}
