package ru.replika.domain

/** A reversible view: source segments, IDs, times and manual flags are never rewritten. */
data class LogicalTurn(val parts: List<Segment>) {
 val id get() = parts.first().id
 val speakerId get() = parts.first().speakerId
 val startMs get() = parts.first().startMs
 val endMs get() = parts.last().endMs
 val text get() = parts.joinToString(" ") { it.text.trim() }
}
object TranscriptPresentation {
 fun groups(segments: List<Segment>, maxPauseMs: Long = 1200): List<LogicalTurn> {
  require(maxPauseMs >= 0)
  val result = mutableListOf<LogicalTurn>()
  for(s in segments.sortedWith(compareBy<Segment> { it.startMs }.thenBy { it.endMs }.thenBy { it.id })) {
   val p=result.lastOrNull()
   // Unknown/overlapping speech and intervening speakers always create a paragraph boundary.
   if(p!=null && s.speakerId>=0 && p.speakerId==s.speakerId &&
    s.startMs>=p.endMs && s.startMs-p.endMs<=maxPauseMs &&
    s.endMs-p.startMs<=45000 && p.text.length+s.text.length<1200) {
    result[result.lastIndex]=LogicalTurn(p.parts+s)
   } else result+=LogicalTurn(listOf(s))
  }
  return result
 }
 fun plain(segments: List<Segment>): String = groups(segments).joinToString("\n\n") { it.text }
}

object RecognitionPlanner {
 const val EDGE_TOLERANCE_MS=300L
 /** Repair small unassigned diarization margins inside a VAD span, never overlaps or speaker changes.
  * No extra audio is added: preserve the bounded original clock, then coalesce before ASR. */
 fun plan(speech: List<Span>, turns: List<Turn>, maxMs: Long=20000): List<Slice> {
  require(maxMs>0)
  val result=mutableListOf<Slice>()
  for(span in Alignment.merge(speech)) {
   val original=Alignment.slices(listOf(span),turns,Long.MAX_VALUE)
   val repaired=original.mapIndexed { i,s ->
    val left=original.getOrNull(i-1)
    val right=original.getOrNull(i+1)
    val candidates=listOfNotNull(left?.speaker,right?.speaker).filter { it>=0 }.distinct()
    val edge=(left==null || left.speaker>=0) && (right==null || right.speaker>=0)
    if(s.speaker<0 && s.endMs-s.startMs<=EDGE_TOLERANCE_MS &&
     s.reasons.none { it.startsWith("Пересечение") } && candidates.size==1 && edge) {
     s.copy(speaker=candidates.single(),reasons=listOf("Короткая граница диаризации: проверьте слова"))
    } else s
   }
   val merged=mutableListOf<Slice>()
   for(s in repaired) {
    val p=merged.lastOrNull()
    if(p!=null && p.endMs==s.startMs && p.speaker==s.speaker) {
     merged[merged.lastIndex]=p.copy(endMs=s.endMs,reasons=(p.reasons+s.reasons).distinct())
    } else merged+=s
   }
   for(s in merged) {
    var a=s.startMs
    while(a<s.endMs) {
     val b=a+minOf(maxMs,s.endMs-a)
     result+=s.copy(startMs=a,endMs=b,reasons=s.reasons+if(a>s.startMs || b<s.endMs) listOf("Разрез длинного интервала: проверьте границу слов") else emptyList())
     a=b
    }
   }
  }
  return result
 }
}

object MlPolicy {
 fun threads(value: Int): Int { require(value in setOf(1,2,4)) { "Допустимо 1, 2 или 4 потока" };return value }
 fun mode(expectedSpeakers: Int): String = when(expectedSpeakers) {
  1 -> "single"
  in 2..20 -> "fixed"
  -1 -> "automatic"
  else -> error("Недопустимое число говорящих")
 }
 fun coolingRequired(status: Int): Boolean = status>=3 // PowerManager.THERMAL_STATUS_SEVERE
}
