package ru.replika.domain

import org.json.JSONArray
import org.json.JSONObject

/** Submission-only projection. Does not change stored speaker assignments or recognition text. */
object JuryJson {
 fun encode(segments: List<Segment>): String {
  val ordered=segments.filter { it.text.isNotBlank() }
   .sortedWith(compareBy<Segment> { it.startMs }.thenBy { it.endMs })
  require(ordered.all { it.startMs>=0 && it.endMs>=it.startMs }) { "Некорректные временные метки стенограммы" }
  val known=ordered.filter { it.speakerId>=0 }
  val numbers=linkedMapOf<Int,Int>()
  val transcript=JSONArray()
  for(segment in ordered) {
   // Distance between intervals, not their midpoints: a long overlapping interval is nearby.
   // Equal distances use the earlier known interval; blank rows never create export identities.
   val speaker=if(segment.speakerId>=0) segment.speakerId else known.minWithOrNull(
    compareBy<Segment> { candidate -> maxOf(0L,candidate.startMs-segment.endMs,segment.startMs-candidate.endMs) }
     .thenBy { it.startMs }.thenBy { it.endMs }
   )?.speakerId?:0
   // With no known speaker at all, the strict schema still needs a valid ID. All such rows
   // share speaker_1; the diagnostic export retains the unknown IDs and warnings.
   val number=numbers.getOrPut(speaker) { numbers.size+1 }
   transcript.put(JSONObject().put("speaker_id","speaker_$number")
    .put("start_ms",segment.startMs).put("end_ms",segment.endMs).put("text",segment.text))
  }
  return JSONObject().put("transcript",transcript).toString(2)
 }
}
