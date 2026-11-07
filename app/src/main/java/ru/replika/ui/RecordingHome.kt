package ru.replika.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map

/**
 * Home and live recording. The bubble, timer and status share one centre; particles are an overlay
 * that never takes layout space. Live controls: ✕ delete · ⏸/▶ pause/resume · ✓ save.
 */
@Composable fun RecordingScreen(vm: AppViewModel,onBack: ()->Unit,onStart: ()->Unit=vm::startRecording,onSettings: ()->Unit={},onImport: ()->Unit={},importing: String?=null,onDelete: ()->Unit=onBack,onSave: ()->Unit={vm.stopRecording(true)}) {
 val phase by vm.recordingPhase.collectAsStateWithLifecycle()
 val live=phase in setOf(RecordingPhase.STARTING,RecordingPhase.RECORDING,RecordingPhase.PAUSED,RecordingPhase.STOPPING)
 val seconds=remember(vm) { vm.elapsed.map { it/1000*1000 }.distinctUntilChanged() }
 val elapsed by seconds.collectAsStateWithLifecycle(0L)
 val orb=rememberOrbState()
 val status=when(phase) {
  RecordingPhase.IDLE,RecordingPhase.SAVED->"Коснитесь пузыря, чтобы начать запись"
  RecordingPhase.PERMISSION_REQUIRED->"Разрешите микрофон, чтобы начать запись"
  RecordingPhase.STARTING->"Включаем микрофон…"
  RecordingPhase.RECORDING->"Идёт запись"
  RecordingPhase.PAUSED->"На паузе"
  RecordingPhase.STOPPING->"Сохраняем запись…"
  RecordingPhase.ERROR->"Не удалось записать. Коснитесь, чтобы повторить"
 }
 Box(Modifier.fillMaxSize().testTag("recording-home")) {
  VoiceParticleField(orb,vm.voiceLevel,phase,Modifier.matchParentSize())
  Column(Modifier.fillMaxSize()) {
   Row(Modifier.fillMaxWidth().padding(start=if(live) 8.dp else 20.dp,end=8.dp).heightIn(min=56.dp),verticalAlignment=Alignment.CenterVertically) {
    if(live) IconButton(onClick=onBack,enabled=phase!=RecordingPhase.STOPPING,modifier=Modifier.testTag("recording-exit")) { Icon(Icons.Outlined.ArrowBack,"Выйти из записи") }
    else Wordmark()
    Spacer(Modifier.weight(1f))
    if(!live) IconButton(onClick=onSettings,modifier=Modifier.testTag("appearance-settings")) { Icon(Icons.Outlined.Settings,"Настройки оформления",tint=Muted) }
   }
   BoxWithConstraints(Modifier.weight(1f).fillMaxWidth().padding(horizontal=16.dp)) {
    val fontScale=LocalDensity.current.fontScale.coerceAtLeast(1f)
    val textBudget=(if(live) 128.dp else 64.dp)*fontScale
    val orbSize=minOf(maxWidth,maxHeight-textBudget).coerceIn(80.dp,380.dp)
    Column(Modifier.fillMaxSize(),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.Center) {
     Box(Modifier.fillMaxWidth().height(orbSize),contentAlignment=Alignment.Center) {
      LiquidVoiceOrb(phase,vm.voiceLevel,onStart,Modifier.size(orbSize),state=orb)
     }
     if(live) Text(clock(elapsed),style=MaterialTheme.typography.displaySmall.copy(fontSize=48.sp,lineHeight=64.sp,fontWeight=FontWeight.SemiBold,fontFeatureSettings="tnum",brush=Brush.horizontalGradient(if(LocalReplikaDark.current) Brand.colors else Brand.strong)),
      modifier=Modifier.padding(top=8.dp).testTag("recording-timer"))
     Text(status,style=MaterialTheme.typography.bodyLarge,textAlign=TextAlign.Center,
      color=when(phase) { RecordingPhase.ERROR->MaterialTheme.colorScheme.error;RecordingPhase.RECORDING->Pink;else->Muted },
      modifier=Modifier.padding(top=if(live) 4.dp else 12.dp,start=16.dp,end=16.dp).testTag("recording-status"))
    }
   }
   Column(Modifier.fillMaxWidth().padding(horizontal=20.dp).padding(top=8.dp,bottom=16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
    when(phase) {
     RecordingPhase.RECORDING,RecordingPhase.PAUSED -> RecordingControls(phase==RecordingPhase.PAUSED,onDelete=onDelete,onPause=vm::pauseRecording,onSave=onSave)
     RecordingPhase.STARTING,RecordingPhase.STOPPING -> Box(Modifier.fillMaxWidth().height(104.dp),contentAlignment=Alignment.Center) { LinearProgressIndicator(Modifier.fillMaxWidth()) }
     else -> {
      GradientButton("Импорт аудио или видео",Icons.Outlined.Add,onImport,enabled=importing==null,modifier=Modifier.fillMaxWidth().testTag("home-import"))
      Row(Modifier.align(Alignment.CenterHorizontally),verticalAlignment=Alignment.Top,horizontalArrangement=Arrangement.spacedBy(6.dp)) {
       Icon(Icons.Outlined.Lock,null,Modifier.padding(top=2.dp).size(14.dp),tint=Muted)
       Text("Обработка на устройстве, без интернета",style=MaterialTheme.typography.bodySmall,color=Muted)
      }
     }
    }
   }
  }
 }
}

/** The product name in Onest Bold with the brand ramp; the only logo treatment in the app. */
@Composable fun Wordmark(modifier: Modifier=Modifier) {
 Text("REPLIKA",modifier=modifier.semantics { heading() },style=MaterialTheme.typography.titleLarge.copy(fontWeight=FontWeight.Bold,letterSpacing=2.sp,
  brush=Brush.horizontalGradient(if(LocalReplikaDark.current) Brand.colors else Brand.strong)))
}

/**
 * ✕ · ⏸/▶ · ✓ in one row, labels under each button. Labels cap their scale so the row never breaks.
 * The merged slot speaks its content description (it takes precedence over the visible label).
 */
@Composable private fun RecordingControls(paused: Boolean,onDelete: ()->Unit,onPause: ()->Unit,onSave: ()->Unit) {
 val fontScale=LocalDensity.current.fontScale
 val labelSize=13.sp*(minOf(fontScale,1.5f)/fontScale.coerceAtLeast(.5f))
 Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceEvenly,verticalAlignment=Alignment.Top) {
  ControlSlot("Удалить","Удалить запись",labelSize,onDelete,Modifier.weight(1f).testTag("recording-delete")) {
   Box(Modifier.size(56.dp).clip(CircleShape).background(SurfaceRaised),contentAlignment=Alignment.Center) {
    Icon(Icons.Outlined.Close,null,Modifier.size(26.dp),tint=MaterialTheme.colorScheme.onSurface)
   }
  }
  ControlSlot(if(paused) "Продолжить" else "Пауза",if(paused) "Продолжить запись" else "Поставить запись на паузу",labelSize,onPause,Modifier.weight(1f).testTag("recording-pause")) {
   Box(Modifier.size(72.dp).clip(CircleShape).background(Brush.linearGradient(Brand.strong)),contentAlignment=Alignment.Center) {
    Icon(if(paused) Icons.Outlined.PlayArrow else Icons.Outlined.Pause,null,Modifier.size(36.dp),tint=Color.White)
   }
  }
  ControlSlot("Сохранить","Сохранить запись",labelSize,onSave,Modifier.weight(1f).testTag("recording-stop")) {
   Box(Modifier.size(56.dp).clip(CircleShape).border(2.dp,Brush.linearGradient(Brand.colors),CircleShape).background(SurfaceBase),contentAlignment=Alignment.Center) {
    Icon(Icons.Outlined.Check,null,Modifier.size(28.dp),tint=Blue)
   }
  }
 }
}

@Composable private fun ControlSlot(label: String,description: String,labelSize: androidx.compose.ui.unit.TextUnit,onClick: ()->Unit,modifier: Modifier,button: @Composable ()->Unit) {
 Column(modifier.clip(MaterialTheme.shapes.medium).clickable(role=Role.Button,onClickLabel=description,onClick=onClick)
  .semantics(mergeDescendants=true) { contentDescription=description }.padding(vertical=6.dp),
  horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(8.dp)) {
  Box(Modifier.height(72.dp),contentAlignment=Alignment.Center) { button() }
  Text(label,style=MaterialTheme.typography.labelMedium.copy(fontSize=labelSize,lineHeight=labelSize*1.4f),color=Muted,maxLines=1,softWrap=false,overflow=TextOverflow.Visible,
   modifier=Modifier.testTag("control-label"))
 }
}

/** Primary call to action: brand gradient, white text (≥ 4.5:1 on every stop), 56 dp target. */
@Composable fun GradientButton(text: String,icon: ImageVector?,onClick: ()->Unit,modifier: Modifier=Modifier,enabled: Boolean=true,height: Dp=56.dp) {
 Box(modifier.heightIn(min=height).clip(ProductShape.control)
  .background(if(enabled) Brush.horizontalGradient(Brand.strong) else Brush.horizontalGradient(listOf(SurfaceRaised,SurfaceRaised)))
  .clickable(enabled=enabled,role=Role.Button,onClick=onClick).padding(horizontal=20.dp,vertical=14.dp),contentAlignment=Alignment.Center) {
  Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(10.dp)) {
   val content=if(enabled) Color.White else Muted
   if(icon!=null) Icon(icon,null,Modifier.size(22.dp),tint=content)
   Text(text,style=MaterialTheme.typography.titleMedium,color=content,textAlign=TextAlign.Center)
  }
 }
}
