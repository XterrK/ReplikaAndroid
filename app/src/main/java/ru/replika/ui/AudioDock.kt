package ru.replika.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.*
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import ru.replika.data.SegmentRow
import kotlin.math.*

/** Transport geometry is symmetric: clocks/speed never participate in the play-button centering. */
@Composable internal fun AudioDock(peaks: List<Float>,rows: List<SegmentRow>,duration: Long,position: Long,playing: Boolean,speed: Float,stopAt: Long?,compact: Boolean,minimal: Boolean,onSeek: (Long)->Unit,onToggle: ()->Unit,onBack: ()->Unit,onForward: ()->Unit,onSpeed: ()->Unit) {
 val currentSeek by rememberUpdatedState(onSeek)
 val mono=rows.isNotEmpty() && rows.first().speakerId>=0 && rows.map { it.speakerId }.distinct().size==1
 val accent=Blue
 Column(Modifier.fillMaxWidth().padding(horizontal=16.dp,vertical=8.dp).background(SurfaceBase,ProductShape.sheet).padding(horizontal=16.dp,vertical=if(minimal) 6.dp else if(compact) 8.dp else 12.dp).testTag("audio-player")) {
  if(minimal) {
   Box(Modifier.fillMaxWidth().height(56.dp),contentAlignment=Alignment.Center) {
    Text(audioClock(position,duration),style=MaterialTheme.typography.labelSmall,color=Muted,modifier=Modifier.align(Alignment.CenterStart).testTag("playback-clock"))
    FilledIconButton(onClick=onToggle,modifier=Modifier.size(48.dp),shape=CircleShape) { Icon(if(playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,if(playing) "Пауза" else "Воспроизвести") }
    TextButton(onClick=onSpeed,modifier=Modifier.align(Alignment.CenterEnd).size(48.dp).testTag("playback-speed"),contentPadding=PaddingValues(0.dp)) { Text(speed.toString()+"×") }
   }
  } else {
   val waveHeight=if(compact) 82.dp else 112.dp
   val waveformDescription=if(mono) "Звуковая дорожка одного участника" else "Звуковая дорожка. Цвет соответствует участнику"
   Box(Modifier.fillMaxWidth().height(waveHeight).testTag("audio-waveform")
    .semantics { contentDescription=waveformDescription;progressBarRangeInfo=ProgressBarRangeInfo((position.toFloat()/duration.coerceAtLeast(1)).coerceIn(0f,1f),0f..1f);setProgress { value -> currentSeek((value.coerceIn(0f,1f)*duration).toLong());true } }
    .pointerInput(duration) {
     awaitEachGesture {
      val down=awaitFirstDown();down.consume()
      currentSeek((down.position.x/size.width.coerceAtLeast(1)*duration).toLong())
      do {
       val event=awaitPointerEvent()
       event.changes.firstOrNull { it.id==down.id }?.let { change -> currentSeek((change.position.x/size.width.coerceAtLeast(1)*duration).toLong().coerceIn(0,duration));change.consume() }
      } while(event.changes.any { it.pressed })
     }
    }) {
    PlayerWaveform(peaks,rows,duration,position,mono,Modifier.fillMaxSize().clearAndSetSemantics {})
   }
   Row(Modifier.fillMaxWidth().padding(top=4.dp),verticalAlignment=Alignment.CenterVertically) {
    Text(audioClock(position,duration),style=MaterialTheme.typography.labelSmall.copy(fontFamily=FontFamily.Monospace),color=MaterialTheme.colorScheme.onSurface,modifier=Modifier.weight(1f).testTag("playback-clock"))
    if(stopAt!=null) Text("До "+formatElapsed(stopAt),style=MaterialTheme.typography.labelSmall,color=accent)
    else Text(audioClock(duration),style=MaterialTheme.typography.labelSmall.copy(fontFamily=FontFamily.Monospace),color=Muted)
   }
   Box(Modifier.fillMaxWidth().height(if(compact) 72.dp else 76.dp),contentAlignment=Alignment.Center) {
    Row(horizontalArrangement=Arrangement.spacedBy(if(compact) 12.dp else 18.dp),verticalAlignment=Alignment.CenterVertically) {
     FilledTonalIconButton(onClick=onBack,modifier=Modifier.size(48.dp),shape=CircleShape) { Icon(Icons.Outlined.Replay10,"Назад 10 секунд",Modifier.size(26.dp)) }
     FilledIconButton(onClick=onToggle,modifier=Modifier.size(64.dp).testTag("player-main-play"),shape=CircleShape) { Icon(if(playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,if(playing) "Пауза" else "Воспроизвести",Modifier.size(34.dp)) }
     FilledTonalIconButton(onClick=onForward,modifier=Modifier.size(48.dp),shape=CircleShape) { Icon(Icons.Outlined.Forward10,"Вперёд 10 секунд",Modifier.size(26.dp)) }
    }
    if(compact) TextButton(onClick=onSpeed,modifier=Modifier.align(Alignment.CenterEnd).size(48.dp).testTag("playback-speed"),contentPadding=PaddingValues(0.dp)) { Text(speed.toString()+"×",style=MaterialTheme.typography.labelSmall,maxLines=1,softWrap=false) }
   }
   if(!compact) Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
    Text(if(rows.isEmpty()) "Исходное аудио" else if(mono) "Один участник" else if(rows.none { it.speakerId>=0 }) "Говорящий не назначен" else "Участники · "+rows.map { it.speakerId }.filter { it>=0 }.distinct().size,style=MaterialTheme.typography.labelSmall,color=Muted,modifier=Modifier.weight(1f))
    TextButton(onClick=onSpeed,modifier=Modifier.heightIn(min=48.dp).widthIn(min=64.dp).testTag("playback-speed"),contentPadding=PaddingValues(horizontal=8.dp)) { Text(speed.toString()+"×",style=MaterialTheme.typography.labelMedium) }
   }
  }
 }
}

@Composable private fun PlayerWaveform(peaks: List<Float>,rows: List<SegmentRow>,duration: Long,position: Long,singleSpeaker: Boolean,modifier: Modifier) {
 val dark=LocalReplikaDark.current
 val cyan=if(dark) Color(0xFF93D6FF) else Color(0xFF6699D7)
 val pink=if(dark) Color(0xFFF0A9D9) else Color(0xFFC677AF)
 val muted=Muted;val foreground=MaterialTheme.colorScheme.onSurface
 val speakerColors=rows.map { speakerColor(it.speakerId) }
 var width by remember { mutableIntStateOf(1) }
 val barWidth=with(LocalDensity.current) { 4.dp.toPx() }
 val samples=remember(peaks,width,barWidth) {
  val bars=(width/barWidth).toInt().coerceAtLeast(1)
  val stride=ceil(peaks.size.toDouble()/bars).toInt().coerceAtLeast(1)
  val maximum=(peaks.maxOrNull()?:0f).coerceAtLeast(.00001f)
  peaks.chunked(stride).map { ((it.maxOrNull()?:0f)/maximum).coerceIn(0f,1f).pow(.7f) }
 }
 val colors=remember(samples.size,rows,speakerColors,duration,muted) { List(samples.size) { i -> val ms=(i.toDouble()/samples.size.coerceAtLeast(1)*duration).toLong();val index=rows.indexOfFirst { ms>=it.startMs && ms<it.endMs };speakerColors.getOrElse(index) { muted } } }
 Canvas(modifier.onSizeChanged { width=it.width }) {
  val step=size.width/samples.size.coerceAtLeast(1);val progress=(position.toFloat()/duration.coerceAtLeast(1)).coerceIn(0f,1f)
  val gradient=Brush.horizontalGradient(listOf(cyan,pink))
  samples.forEachIndexed { i,amplitude ->
   val h=(amplitude*(size.height-8.dp.toPx())).coerceAtLeast(3.dp.toPx());val x=(i+.5f)*step
   val alpha=if(i.toFloat()/samples.size<=progress) 1f else .5f
   val start=Offset(x,(size.height-h)/2);val end=Offset(x,(size.height+h)/2);val stroke=(step*.58f).coerceIn(1f,3.dp.toPx())
   if(singleSpeaker) drawLine(gradient,start,end,strokeWidth=stroke,cap=StrokeCap.Round,alpha=alpha)
   else drawLine(colors[i].copy(alpha=alpha),start,end,strokeWidth=stroke,cap=StrokeCap.Round)
  }
  if(samples.isEmpty()) drawLine(muted.copy(alpha=.35f),Offset(0f,size.height/2),Offset(size.width,size.height/2),1.dp.toPx())
  val x=size.width*progress
  drawLine(foreground.copy(alpha=.6f),Offset(x,1.dp.toPx()),Offset(x,size.height-1.dp.toPx()),1.dp.toPx())
  drawCircle(if(singleSpeaker) cyan else foreground,2.5.dp.toPx(),Offset(x,size.height/2))
 }
}
