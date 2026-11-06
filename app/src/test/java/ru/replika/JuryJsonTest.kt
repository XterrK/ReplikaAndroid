package ru.replika

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.JuryJson
import ru.replika.domain.Segment

class JuryJsonTest {
 private fun segment(start: Long,end: Long,speaker: Int,text: String="Реплика.") =
  Segment(startMs=start,endMs=end,speakerId=speaker,text=text,source="Contract fixture; no model inference",edited=true,reviewed=true,reasons=listOf("Проверка"))
 private fun rows(vararg segments: Segment)=JSONObject(JuryJson.encode(segments.toList())).getJSONArray("transcript")

 @Test fun strictSchemaSortsByTimeAndNumbersByFirstAppearance() {
  val root=JSONObject(JuryJson.encode(listOf(segment(900,1000,7),segment(200,400,9),segment(0,100,7))))
  assertEquals(setOf("transcript"),root.keys().asSequence().toSet())
  val out=root.getJSONArray("transcript")
  assertEquals(listOf(0L,200L,900L),(0 until out.length()).map { out.getJSONObject(it).getLong("start_ms") })
  assertEquals(listOf("speaker_1","speaker_2","speaker_1"),(0 until out.length()).map { out.getJSONObject(it).getString("speaker_id") })
  for(i in 0 until out.length()) assertEquals(setOf("speaker_id","start_ms","end_ms","text"),out.getJSONObject(i).keys().asSequence().toSet())
 }

 @Test fun unknownUsesNearestIntervalRatherThanNearestMidpoint() {
  val before=segment(0,100,8)
  val unknown=segment(110,120,-1)
  val after=segment(121,100000,4)
  val out=rows(after,unknown,before)
  assertEquals("speaker_2",out.getJSONObject(1).getString("speaker_id"))
  assertEquals("speaker_2",out.getJSONObject(2).getString("speaker_id"))
  assertEquals(-1,unknown.speakerId)
 }

 @Test fun unknownBeforeAnyKnownSpeakerParticipatesInFirstAppearanceNumbering() {
  val out=rows(segment(20,30,55),segment(0,10,-1),segment(100,110,7))
  assertEquals(listOf("speaker_1","speaker_1","speaker_2"),(0 until out.length()).map { out.getJSONObject(it).getString("speaker_id") })
 }

 @Test fun equalDistancePrefersEarlierKnownIntervalAndOverlapHasZeroDistance() {
  val tie=rows(segment(0,10,8),segment(20,30,-1),segment(40,50,3))
  assertEquals("speaker_1",tie.getJSONObject(1).getString("speaker_id"))
  val overlap=rows(segment(0,1000,8),segment(500,600,-1),segment(601,610,3))
  assertEquals("speaker_1",overlap.getJSONObject(1).getString("speaker_id"))
 }

 @Test fun noKnownSpeakerProducesOneValidIdentityAndEmptyInputProducesEmptyArray() {
  val out=rows(segment(0,10,-1),segment(20,30,-1))
  assertEquals(2,out.length())
  assertEquals("speaker_1",out.getJSONObject(0).getString("speaker_id"))
  assertEquals("speaker_1",out.getJSONObject(1).getString("speaker_id"))
  assertEquals(0,rows().length())
 }

 @Test fun blankTextDoesNotExportOrAnchorASpeaker() {
  val out=rows(segment(0,10,8," \n\t"),segment(20,30,-1),segment(40,50,9,"Добрый день!"))
  assertEquals(2,out.length())
  assertEquals("speaker_1",out.getJSONObject(0).getString("speaker_id"))
  assertEquals("speaker_1",out.getJSONObject(1).getString("speaker_id"))
 }

 @Test fun exactTextSurvivesQuotesNewlinesUnicodeAndUtf8RoundtripWithoutBom() {
  val text="  Кот сказал: \"Да!\"\nЁж, 25% — 🐈.\t\\  "
  val encoded=JuryJson.encode(listOf(segment(1250,4380,0,text)))
  val bytes=encoded.toByteArray(Charsets.UTF_8)
  assertFalse(bytes.take(3)==listOf(0xef.toByte(),0xbb.toByte(),0xbf.toByte()))
  assertEquals(text,JSONObject(bytes.toString(Charsets.UTF_8)).getJSONArray("transcript").getJSONObject(0).getString("text"))
 }

 @Test fun integerMillisecondsArePreservedBeyondIntRange() {
  val out=rows(segment(3_000_000_000L,3_000_000_123L,42)).getJSONObject(0)
  assertEquals(3_000_000_000L,out.getLong("start_ms"))
  assertEquals(3_000_000_123L,out.getLong("end_ms"))
  assertTrue(out.get("start_ms") is Long)
 }

 @Test fun invalidTimesAreRejectedRatherThanSilentlyRewritten() {
  for(s in listOf(segment(-1,10,0),segment(20,10,0))) {
   assertThrows(IllegalArgumentException::class.java) { JuryJson.encode(listOf(s)) }
  }
 }
}
