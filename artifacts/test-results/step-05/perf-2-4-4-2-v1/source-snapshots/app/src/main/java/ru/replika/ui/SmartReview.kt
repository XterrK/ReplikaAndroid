@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package ru.replika.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import ru.replika.data.SegmentRow

data class ReviewIssue(val title: String,val explanation: String)

/** Presentation of persisted objective flags. No probability or inferred model confidence. */
fun reviewIssues(row: SegmentRow): List<ReviewIssue> {
 val raw=runCatching { row.domain().reasons }.getOrDefault(emptyList())
 // Duration-only flags survive in legacy storage/exports, never assert the merged row was short.
 val issues=raw.filterNot { it.contains("Короткая",ignoreCase=true) }.map { reason ->
  when {
   reason.contains("Пересечение",ignoreCase=true) -> ReviewIssue("Пересечение голосов","В интервале отмечено несколько голосов. Слова участников не разделены.")
   reason.contains("Неоднознач",ignoreCase=true) -> ReviewIssue(if(row.speakerId<0) "Говорящий не определён" else "Проверить назначение", "Исходный анализ не смог однозначно назначить говорящего. Сверьте текущее назначение со звуком.")
   reason.contains("Разрез",ignoreCase=true) -> ReviewIssue("Граница длинной реплики","Речь разделена на части. Проверьте слова рядом с границей.")
   else -> ReviewIssue("Нужна проверка",reason)
  }
 }.toMutableList()
 // Unknown is an actual persisted assignment, including a manual reassignment to Unknown.
 if(row.speakerId<0 && issues.none { it.title=="Говорящий не определён" || it.title=="Проверить назначение" }) {
  issues.add(0,ReviewIssue("Говорящий не определён","У реплики нет назначенного участника. Прослушайте её и при необходимости выберите говорящего."))
 }
 return issues.distinctBy { it.title }
}

@Composable fun SmartReviewQueue(
 rows: List<SegmentRow>,name: (Int)->String,modifier: Modifier=Modifier,
 onListen: (SegmentRow)->Unit,onEdit: (SegmentRow)->Unit,
 onReviewed: (SegmentRow,(Boolean)->Unit)->Unit,
 onTranscript: ()->Unit,onListenRecording: ()->Unit
) {
 var showReviewed by remember { mutableStateOf(false) }
 var savingId by remember { mutableStateOf<String?>(null) }
 val flagged=remember(rows) { rows.filter { reviewIssues(it).isNotEmpty() } }
 val pending=flagged.filter { !it.reviewed }
 val shown=if(showReviewed) flagged.filter { it.reviewed } else pending
 LazyColumn(
  modifier.fillMaxWidth().testTag("review-queue"),
  contentPadding=PaddingValues(start=20.dp,end=20.dp,top=8.dp,bottom=24.dp),
  verticalArrangement=Arrangement.spacedBy(12.dp)
 ) {
  item {
   Column(verticalArrangement=Arrangement.spacedBy(6.dp)) {
    Text("Проверка фрагментов",style=MaterialTheme.typography.titleMedium)
    Text("Проверьте участника и отмеченные границы на слух.",style=MaterialTheme.typography.bodySmall,color=Muted)
    if(flagged.isNotEmpty()) FlowRow(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
     Text(pending.size.toString()+" к проверке · "+(flagged.size-pending.size)+" проверено",style=MaterialTheme.typography.labelSmall,color=Muted)
     TextButton(onClick={showReviewed=!showReviewed},modifier=Modifier.heightIn(min=48.dp)) { Text(if(showReviewed) "К очереди" else "Проверенные",maxLines=1,softWrap=false) }
    }
   }
  }
  if(shown.isEmpty()) item {
   ProductEmptyState(
    title=if(showReviewed) "Пока нет проверенных фрагментов" else if(flagged.isNotEmpty()) "Эта очередь проверена" else "Автоматических меток нет",
    body=if(showReviewed) "После прослушивания отметьте фрагмент как проверенный — он появится здесь." else "Это не гарантия правильного распознавания. Прослушайте запись и сверяйте текст с исходным звуком.",
    modifier=Modifier.testTag("review-empty")
   ) {
    TextButton(onClick=onTranscript,modifier=Modifier.heightIn(min=48.dp)) { Text("К полной стенограмме") }
    OutlinedButton(shape=ProductShape.control,onClick=onListenRecording,modifier=Modifier.heightIn(min=48.dp)) { Icon(Icons.Outlined.PlayArrow,null);Text("Прослушать запись") }
   }
  }
  items(shown,key={it.id}) { row ->
   val issues=remember(row.reasons,row.speakerId) { reviewIssues(row) }
   Column(
    Modifier.fillMaxWidth().background(SurfaceBase,ProductShape.panel).padding(16.dp).testTag("review-"+row.id),
    verticalArrangement=Arrangement.spacedBy(10.dp)
   ) {
    Row(verticalAlignment=Alignment.Top,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
     Icon(if(row.reviewed) Icons.Outlined.CheckCircle else Icons.Outlined.FactCheck,null,Modifier.size(20.dp),tint=if(row.reviewed) Mint else Amber)
     Text(issues.joinToString(" · ") { it.title },style=MaterialTheme.typography.titleSmall,color=if(row.reviewed) Mint else Amber,modifier=Modifier.weight(1f))
    }
    Text(segmentIntervalLabel(row.startMs,row.endMs)+" · "+name(row.speakerId),style=MaterialTheme.typography.labelSmall,color=Muted)
    issues.forEach { Text(it.explanation,style=MaterialTheme.typography.bodySmall,color=Muted) }
    Text(row.text,style=MaterialTheme.typography.bodyLarge,maxLines=3,overflow=TextOverflow.Ellipsis)
    FlowRow(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(6.dp),verticalArrangement=Arrangement.spacedBy(4.dp)) {
     IconButton(onClick={onListen(row)},modifier=Modifier.testTag("review-listen-"+row.id)) { Icon(Icons.Outlined.PlayArrow,"Прослушать предупреждение") }
     TextButton(onClick={onEdit(row)},modifier=Modifier.heightIn(min=48.dp).testTag("review-edit-"+row.id)) { Text("Исправить") }
     if(!row.reviewed) TextButton(
      onClick={savingId=row.id;onReviewed(row) { savingId=null }},
      enabled=savingId!=row.id,modifier=Modifier.heightIn(min=48.dp).testTag("review-done-"+row.id)
     ) { Text(if(savingId==row.id) "Сохраняем…" else "Проверено") }
     else Text("Проверено",style=MaterialTheme.typography.labelSmall,color=Mint,fontWeight=FontWeight.Medium)
    }
   }
  }
 }
}
