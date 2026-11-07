package ru.replika.domain

import java.util.UUID
import org.json.JSONArray
import org.json.JSONObject

data class Turn(val startMs: Long, val endMs: Long, val speaker: Int)
data class Span(val startMs: Long, val endMs: Long)
data class Slice(val startMs: Long, val endMs: Long, val speaker: Int, val reasons: List<String>)
data class Segment(
 val id: String = UUID.randomUUID().toString(), val startMs: Long, val endMs: Long,
 val speakerId: Int, val text: String, val source: String, val edited: Boolean = false,
 val reasons: List<String> = emptyList(), val reviewed: Boolean = false
)

object Alignment {
 fun stable(turns: List<Turn>): List<Turn> {
  val ids = linkedMapOf<Int,Int>()
  return turns.sortedWith(compareBy<Turn> { it.startMs }.thenBy { it.speaker }).map {
   it.copy(speaker = if(it.speaker < 0) -1 else ids.getOrPut(it.speaker) { ids.size })
  }
 }
 fun merge(spans: List<Span>): List<Span> {
  val out = mutableListOf<Span>()
  for(s in spans.filter { it.endMs > it.startMs }.sortedBy { it.startMs }) {
   val p = out.lastOrNull()
   if(p != null && s.startMs <= p.endMs) out[out.lastIndex] = p.copy(endMs = maxOf(p.endMs,s.endMs)) else out += s
  }
  return out
 }
 /** Expand context on the original recording clock, then merge so no sample is recognized twice. */
 fun context(spans: List<Span>, durationMs: Long, preMs: Long = 0, postMs: Long = 0): List<Span> {
  require(durationMs >= 0 && preMs >= 0 && postMs >= 0)
  return merge(spans.filter { it.endMs > it.startMs }.map {
   Span((it.startMs.coerceIn(0,durationMs)-preMs.coerceAtMost(durationMs)).coerceAtLeast(0),
    it.endMs.coerceIn(0,durationMs).let { end -> end + postMs.coerceAtMost(durationMs-end) })
  })
 }
 // Partition on real speaker changes; coalesce adjacent intervals with the same assignment.
 // Each disjoint interval is recognized once. Mixed speech remains unknown.
 fun slices(vad: List<Span>, turns: List<Turn>, maxMs: Long = 20000): List<Slice> {
  require(maxMs > 0)
  val out = mutableListOf<Slice>()
  for(v in merge(vad)) {
   val boundaries = (listOf(v.startMs,v.endMs) + turns.flatMap { listOf(it.startMs,it.endMs) }.filter { it > v.startMs && it < v.endMs }).distinct().sorted()
   val partitions = mutableListOf<Slice>()
   for((a,b) in boundaries.zipWithNext()) {
    val active = turns.filter { it.startMs < b && it.endMs > a }.map { it.speaker }.distinct()
    val speaker = active.singleOrNull() ?: -1
    val reasons = buildList {
     if(active.size > 1) add("Пересечение голосов: слова не разделены")
     if(speaker < 0) add("Неоднозначный говорящий")
    }
    val previous=partitions.lastOrNull()
    if(previous!=null && previous.endMs==a && previous.speaker==speaker && previous.reasons==reasons) {
     partitions[partitions.lastIndex]=previous.copy(endMs=b)
    } else partitions+=Slice(a,b,speaker,reasons)
   }
   for(p in partitions) {
    val reasons=p.reasons + if(p.endMs-p.startMs<700) listOf("Короткая реплика возле границы") else emptyList()
    var start=p.startMs
    while(start<p.endMs) {
     val end=start+minOf(maxMs,p.endMs-start)
     out+=Slice(start,end,p.speaker,reasons + if(end<p.endMs || start>p.startMs) listOf("Разрез длинного интервала: проверьте границу слов") else emptyList())
     start=end
    }
   }
  }
  return out
 }
}
object Exporter {
 fun stamp(ms: Long, srt: Boolean = false): String {
  val n=ms.coerceAtLeast(0)
  return "%02d:%02d:%02d%s%03d".format(java.util.Locale.ROOT,n/3600000,n/60000%60,n/1000%60,if(srt) "," else ".",n%1000)
 }
 fun txt(title: String, segments: List<Segment>, name: (Int)->String): String = title+"\n\n"+segments.joinToString("\n\n") { "[${stamp(it.startMs)} – ${stamp(it.endMs)}] ${name(it.speakerId)}\n${it.text}" }
 fun srt(segments: List<Segment>, name: (Int)->String): String = segments.sortedBy { it.startMs }.mapIndexed { i,s -> "${i+1}\n${stamp(s.startMs,true)} --> ${stamp(s.endMs,true)}\n${name(s.speakerId)}: ${s.text.replace("\n"," ")}\n" }.joinToString("\n")
 fun json(title: String, segments: List<Segment>, name: (Int)->String): String = JSONObject().put("schemaVersion",1).put("title",title).put("timestampPrecision","segment").put("segments", JSONArray().also { a -> segments.forEach { s -> a.put(JSONObject().put("id",s.id).put("startMs",s.startMs).put("endMs",s.endMs).put("speakerId",s.speakerId).put("speakerName",name(s.speakerId)).put("text",s.text).put("source",s.source).put("edited",s.edited).put("reviewed",s.reviewed).put("warnings",JSONArray(s.reasons))) } }).toString(2)
}
