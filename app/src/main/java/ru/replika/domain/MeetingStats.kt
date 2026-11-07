package ru.replika.domain

/** Минимальный вход для аналитики: кто говорил и когда. */
data class StatSegment(val speakerId: Int,val startMs: Long,val endMs: Long)

data class SpeakerStat(val speakerId: Int,val speechMs: Long,val share: Float,val turns: Int)
data class Monologue(val speakerId: Int,val durationMs: Long)

data class MeetingStats(
 val speakers: List<SpeakerStat>,
 val speechMs: Long,
 val pauseMs: Long,
 val totalMs: Long,
 val longest: Monologue?
) {
 val turns get()=speakers.sumOf { it.turns }
 val isEmpty get()=speakers.isEmpty()

 companion object {
  /** Реплики одного участника подряд с паузой не больше этой считаются одним монологом. */
  const val MONOLOGUE_GAP_MS=1500L

  /**
   * Чистый расчёт по готовым сегментам. Доли считаются по объединению интервалов каждого участника
   * и нормируются на сумму, поэтому перекрытия реплик не дают больше 100%.
   * [durationMs] — длительность записи (если 0 — берётся конец последней реплики).
   */
  fun compute(segments: List<StatSegment>,durationMs: Long=0L): MeetingStats {
   val valid=segments.filter { it.endMs>it.startMs && it.startMs>=0 }
   if(valid.isEmpty()) return MeetingStats(emptyList(),0,durationMs.coerceAtLeast(0),durationMs.coerceAtLeast(0),null)
   val perSpeaker=valid.groupBy { it.speakerId }
   val speechById=perSpeaker.mapValues { (_,list) -> union(list.map { it.startMs to it.endMs }) }
   val sum=speechById.values.sum().coerceAtLeast(1L)
   val stats=perSpeaker.map { (id,list) ->
    val ms=speechById.getValue(id)
    SpeakerStat(id,ms,ms.toFloat()/sum,list.size)
   }.sortedWith(compareByDescending<SpeakerStat> { it.speechMs }.thenBy { it.speakerId })
   val speech=union(valid.map { it.startMs to it.endMs })
   val total=maxOf(durationMs,valid.maxOf { it.endMs },speech)
   return MeetingStats(stats,speech,(total-speech).coerceAtLeast(0),total,longestMonologue(valid))
  }

  private fun union(intervals: List<Pair<Long,Long>>): Long {
   var total=0L;var curStart=-1L;var curEnd=-1L
   for((s,e) in intervals.sortedBy { it.first }) {
    if(curEnd<0 || s>curEnd) { if(curEnd>=0) total+=curEnd-curStart;curStart=s;curEnd=e }
    else if(e>curEnd) curEnd=e
   }
   if(curEnd>=0) total+=curEnd-curStart
   return total
  }

  private fun longestMonologue(valid: List<StatSegment>): Monologue? {
   var best: Monologue?=null
   var id=0;var start=0L;var end=0L;var open=false
   fun close() { if(open && (best==null || end-start>best!!.durationMs)) best=Monologue(id,end-start) }
   for(s in valid.sortedBy { it.startMs }) {
    if(open && s.speakerId==id && s.startMs-end<=MONOLOGUE_GAP_MS) { end=maxOf(end,s.endMs) }
    else { close();id=s.speakerId;start=s.startMs;end=s.endMs;open=true }
   }
   close()
   return best
  }
 }
}
