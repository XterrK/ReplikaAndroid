@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package ru.replika.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import ru.replika.domain.MeetingStats

/** Компактная аналитика встречи: доли речи, реплики, самый длинный монолог, речь/паузы. */
@Composable fun MeetingStatsSheet(stats: MeetingStats,name: (Int)->String,onDismiss: ()->Unit) {
 ModalBottomSheet(onDismissRequest=onDismiss,containerColor=SurfaceRaised,modifier=Modifier.testTag("meeting-stats-sheet")) {
  Column(Modifier.fillMaxWidth().padding(horizontal=20.dp).padding(bottom=24.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
   Text("Аналитика встречи",style=MaterialTheme.typography.titleMedium)
   if(stats.isEmpty) { Text("В стенограмме нет реплик.",color=Muted,style=MaterialTheme.typography.bodyMedium);return@Column }
   stats.speakers.forEach { s ->
    val color=speakerColor(s.speakerId)
    Column(verticalArrangement=Arrangement.spacedBy(4.dp)) {
     Row(verticalAlignment=Alignment.CenterVertically) {
      Text(name(s.speakerId),Modifier.weight(1f),color=color,style=MaterialTheme.typography.labelLarge,maxLines=1,overflow=TextOverflow.Ellipsis)
      Text("${Math.round(s.share*100)}%",fontWeight=FontWeight.SemiBold,style=MaterialTheme.typography.labelLarge)
     }
     Box(Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)).background(color.copy(alpha=.16f))) {
      Box(Modifier.fillMaxWidth(s.share.coerceIn(.02f,1f)).fillMaxHeight().clip(RoundedCornerShape(4.dp)).background(color))
     }
     Text("${plural(s.turns)} · ${audioClock(s.speechMs,0)} речи",color=Muted,style=MaterialTheme.typography.labelMedium)
    }
   }
   HorizontalDivider(color=SurfaceLine.copy(alpha=.65f))
   stats.longest?.let { Row { Text("Самый длинный монолог",Modifier.weight(1f),color=Muted,style=MaterialTheme.typography.bodyMedium);Text(name(it.speakerId)+" · "+audioClock(it.durationMs,0),style=MaterialTheme.typography.bodyMedium,maxLines=1,overflow=TextOverflow.Ellipsis,modifier=Modifier.weight(1f,false)) } }
   Row { Text("Речь",Modifier.weight(1f),color=Muted,style=MaterialTheme.typography.bodyMedium);Text(audioClock(stats.speechMs,0),style=MaterialTheme.typography.bodyMedium) }
   Row { Text("Паузы",Modifier.weight(1f),color=Muted,style=MaterialTheme.typography.bodyMedium);Text(audioClock(stats.pauseMs,0),style=MaterialTheme.typography.bodyMedium) }
  }
 }
}

private fun plural(n: Int): String {
 val m=n%100;val d=n%10
 return "$n "+if(m in 11..14) "реплик" else when(d) { 1->"реплика";2,3,4->"реплики";else->"реплик" }
}
