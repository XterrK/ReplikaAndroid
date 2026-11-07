package ru.replika.domain

import org.junit.Assert.*
import org.junit.Test

class MeetingStatsTest {
 private fun seg(id: Int,s: Long,e: Long)=StatSegment(id,s,e)

 @Test fun emptyTranscript() {
  val st=MeetingStats.compute(emptyList(),10_000)
  assertTrue(st.isEmpty);assertEquals(0,st.speechMs);assertEquals(10_000,st.pauseMs);assertNull(st.longest)
 }

 @Test fun singleSpeakerIsHundredPercent() {
  val st=MeetingStats.compute(listOf(seg(0,0,2000),seg(0,4000,6000)),8000)
  assertEquals(1,st.speakers.size);assertEquals(1f,st.speakers[0].share,1e-6f)
  assertEquals(2,st.speakers[0].turns);assertEquals(4000,st.speechMs);assertEquals(4000,st.pauseMs)
 }

 @Test fun overlapsNeverExceedHundredPercent() {
  val st=MeetingStats.compute(listOf(seg(0,0,5000),seg(1,1000,6000),seg(1,2000,3000)),6000)
  assertEquals(1f,st.speakers.sumOf { it.share.toDouble() }.toFloat(),1e-5f)
  assertTrue(st.speakers.all { it.share<=1f })
  assertEquals(6000,st.speechMs);assertEquals(0,st.pauseMs)
  assertEquals(5000,st.speakers.first { it.speakerId==1 }.speechMs)
 }

 @Test fun pausesAndLongestMonologue() {
  val st=MeetingStats.compute(listOf(seg(0,0,1000),seg(0,1500,4000),seg(1,5000,6000),seg(0,9000,9500)),10_000)
  assertEquals(2,st.speakers.size);assertEquals(0,st.speakers[0].speakerId)
  assertEquals(4,st.turns);assertEquals(5000,st.speechMs);assertEquals(5000,st.pauseMs)
  assertEquals(Monologue(0,4000),st.longest)
 }

 @Test fun invalidSegmentsIgnoredAndDurationFallsBackToLastEnd() {
  val st=MeetingStats.compute(listOf(seg(0,3000,3000),seg(0,1000,2000)))
  assertEquals(1,st.turns);assertEquals(2000,st.totalMs);assertEquals(1000,st.pauseMs)
 }
}
