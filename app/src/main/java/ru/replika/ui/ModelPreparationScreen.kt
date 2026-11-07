package ru.replika.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import ru.replika.ml.BundledModelCoordinator.Phase
import ru.replika.ml.BundledModelCoordinator.State

/** First launch of the All-in-One build: the bundled models are unpacked and verified on the device. */
@Composable fun ModelPreparationScreen(state: State,onRetry: ()->Unit) {
 val title = when(state.phase) {
  Phase.CHECKING -> "Проверяем офлайн-комплект"
  Phase.PREPARING -> "Подготавливаем офлайн-модели"
  Phase.VERIFYING -> "Проверяем целостность"
  Phase.COMPLETE,Phase.READY -> "Всё готово"
  Phase.NO_SPACE -> "Недостаточно места"
  Phase.NO_MEMORY -> "Недостаточно памяти"
  Phase.ERROR -> "Подготовка не завершена"
 }
 Surface(Modifier.fillMaxSize().testTag("model-preparation"),color=Ink) {
  Column(Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp),verticalArrangement=Arrangement.Center) {
   Wordmark()
   Spacer(Modifier.height(36.dp))
   Box(Modifier.size(64.dp).clip(CircleShape).background(if(state.failed) Brush.linearGradient(listOf(SurfaceRaised,SurfaceRaised)) else Brush.linearGradient(Brand.strong)),contentAlignment=Alignment.Center) {
    Icon(if(state.failed) Icons.Outlined.Info else if(state.phase==Phase.COMPLETE) Icons.Outlined.Check else Icons.Outlined.Memory,null,tint=if(state.failed) Amber else Color.White,modifier=Modifier.size(30.dp))
   }
   Spacer(Modifier.height(24.dp))
   Text(title,style=MaterialTheme.typography.headlineLarge)
   Spacer(Modifier.height(12.dp))
   Text(state.message ?: when(state.phase) {
    Phase.CHECKING -> "Проверяем сохранённые файлы. Готовые модели останутся на месте."
    Phase.PREPARING -> "Всё необходимое уже в APK. Подготовка проходит на устройстве, без интернета."
    Phase.VERIFYING -> "Сверяем SHA-256 каждого файла перед запуском распознавания."
    else -> "Офлайн-модели проверены. Открываем приложение."
   },color=Muted,style=MaterialTheme.typography.bodyLarge)
   Spacer(Modifier.height(28.dp))
   if(state.failed) {
    GradientButton("Повторить подготовку",Icons.Outlined.Refresh,onRetry,modifier=Modifier.fillMaxWidth().testTag("retry-preparation"))
    Spacer(Modifier.height(12.dp))
    Text("Записи и уже проверенные модели сохранены.",color=Muted,style=MaterialTheme.typography.bodySmall)
   } else {
    if(state.totalBytes>0) {
     val fraction=(state.processedBytes.toDouble()/state.totalBytes).toFloat().coerceIn(0f,1f)
     // Brand-gradient progress; semantics keep the exact fraction for accessibility services.
     Box(Modifier.fillMaxWidth().height(8.dp).clip(CircleShape).background(SurfaceRaised).semantics { progressBarRangeInfo=ProgressBarRangeInfo(fraction,0f..1f) }) {
      Box(Modifier.fillMaxHeight().fillMaxWidth(fraction).clip(CircleShape).background(Brand.horizontal))
     }
     Spacer(Modifier.height(10.dp))
     Text("${formatBytes(state.processedBytes)} / ${formatBytes(state.totalBytes)}",style=MaterialTheme.typography.labelMedium,color=Muted)
    } else LinearProgressIndicator(Modifier.fillMaxWidth(),color=Blue,trackColor=SurfaceRaised)
    state.path?.let { Spacer(Modifier.height(8.dp));Text(it.substringAfterLast('/'),style=MaterialTheme.typography.bodySmall,color=Muted) }
    Spacer(Modifier.height(28.dp));HorizontalDivider(color=SurfaceLine);Spacer(Modifier.height(20.dp))
    Text("Локальное распознавание · полный комплект моделей",style=MaterialTheme.typography.titleSmall)
    Spacer(Modifier.height(8.dp))
    Text("RU · GigaAM v3   EN · Parakeet TDT v2\nАвтоязык · Silero VAD · Pyannote · 3D-Speaker",style=MaterialTheme.typography.bodySmall,color=Muted)
    Spacer(Modifier.height(20.dp))
    Row(horizontalArrangement=Arrangement.spacedBy(8.dp),verticalAlignment=Alignment.CenterVertically) {
     Icon(Icons.Outlined.Lock,null,tint=Muted,modifier=Modifier.size(16.dp))
     Text("Аудио и текст остаются на устройстве",color=Muted,style=MaterialTheme.typography.bodySmall)
    }
   }
  }
 }
}
