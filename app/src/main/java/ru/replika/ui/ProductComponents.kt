package ru.replika.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.window.DialogWindowProvider
import androidx.core.view.WindowCompat
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable fun LocalOnlyLabel(modifier: Modifier=Modifier) {
 Row(modifier,verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(4.dp)) {
  Icon(Icons.Outlined.Lock,null,Modifier.size(12.dp),tint=Mint)
  Text("Локально",style=MaterialTheme.typography.labelSmall,color=Mint)
 }
}

@Composable fun SpeakerAvatar(id: Int,modifier: Modifier=Modifier) {
 Box(modifier.size(26.dp).clip(CircleShape).background(speakerColor(id).copy(alpha=.14f)),contentAlignment=Alignment.Center) {
  Text(if(id<0) "?" else (id+1).toString(),color=speakerColor(id),style=MaterialTheme.typography.labelSmall,fontWeight=FontWeight.SemiBold)
 }
}

@Composable fun ProductEmptyState(title: String,body: String,modifier: Modifier=Modifier,action: @Composable ColumnScope.()->Unit={}) {
 Column(modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=28.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
  Text(title,style=MaterialTheme.typography.titleMedium)
  Text(body,style=MaterialTheme.typography.bodyMedium,color=Muted)
  action()
 }
}

// Preserve useful boundaries for short review excerpts without implying word timestamps.
fun segmentIntervalLabel(startMs: Long,endMs: Long): String {
 val precise=endMs-startMs<1000 || startMs/1000==endMs/1000
 fun cue(ms: Long): String {
  val n=ms.coerceAtLeast(0)
  return if(precise) "%02d:%02d.%03d".format(java.util.Locale.ROOT,n/60000,n/1000%60,n%1000) else clock(n)
 }
 return cue(startMs)+" — "+cue(endMs)
}

/** Material3 1.3.2 follows system theme for dialog icons; REPLIKA sheets always use dark surfaces. */
@Composable @androidx.compose.runtime.NonRestartableComposable fun DarkSheetSystemBars() {
 val view=LocalView.current
 SideEffect {
  val window=(view.parent as? DialogWindowProvider)?.window
  if(window!=null) view.post {
   if(view.isAttachedToWindow) WindowCompat.getInsetsController(window,window.decorView).isAppearanceLightStatusBars=false
  }
 }
}
