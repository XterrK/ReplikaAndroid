package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.*

class RecoveryV13Test {
 private fun s(id: String,a: Long,b: Long,speaker: Int=0,text: String=id)=Segment(id,a,b,speaker,text,"fixture")
 @Test fun reclaimDiarizationMarginsWithoutChangingPreroll() {
  val speech=Alignment.context(listOf(Span(102,8550)),11290,100,0)
  val planned=RecognitionPlanner.plan(speech,listOf(Turn(31,8485,0)))
  assertEquals(1,planned.size);assertEquals(2L,planned.single().startMs);assertEquals(8550L,planned.single().endMs)
  assertEquals(0,planned.single().speaker);assertTrue(planned.single().reasons.isNotEmpty())
 }
 @Test fun neverBorrowAcrossSpeakerChangeOrOverlap() {
  val spans=listOf(Span(0,3000))
  assertEquals(listOf(0,-1,1),RecognitionPlanner.plan(spans,listOf(Turn(0,1000,0),Turn(1100,3000,1))).map { it.speaker })
  assertEquals(listOf(0,-1,1),RecognitionPlanner.plan(spans,listOf(Turn(0,1500,0),Turn(1000,3000,1))).map { it.speaker })
 }
 @Test fun doNotAssignLongUnknownGap() {
  assertEquals(listOf(-1,0),RecognitionPlanner.plan(listOf(Span(0,2000)),listOf(Turn(500,2000,0))).map { it.speaker })
 }
 @Test fun allLongRecordingSamplesCoveredExactlyOnce() {
  val spans=Alignment.context(listOf(Span(0,100000),Span(99900,240001)),240000,100,0)
  val slices=RecognitionPlanner.plan(spans,listOf(Turn(0,240000,0)))
  assertEquals(12,slices.size);assertEquals(240000L,slices.sumOf { it.endMs-it.startMs })
  assertTrue(slices.zipWithNext().all { (a,b)->a.endMs==b.startMs });assertTrue(slices.all { it.startMs>=0 && it.endMs<=240000 && it.speaker==0 })
 }
 @Test(expected=IllegalArgumentException::class) fun rejectInvalidChunkLimit() { RecognitionPlanner.plan(emptyList(),emptyList(),0) }
 @Test fun pausesGroupSourceIdsAndManualCorrectionsWithoutMutation() {
  val a=s("a",0,500,text="первое");val b=s("b",900,1800,text="исправленное").copy(edited=true)
  val groups=TranscriptPresentation.groups(listOf(b,a))
  assertEquals(1,groups.size);assertEquals(listOf(a,b),groups.single().parts)
  assertEquals("первое исправленное",groups.single().text);assertTrue(groups.single().parts.last().edited)
 }
 @Test fun longPauseAndChangedSpeakerRemainSeparate() {
  val rows=listOf(s("a",0,500),s("b",2000,2500),s("c",2600,3000,1),s("d",3100,3500))
  assertEquals(4,TranscriptPresentation.groups(rows).size)
 }
 @Test fun noMergingAcrossFilteredSpeakerOrUnknownOrOverlap() {
  assertEquals(3,TranscriptPresentation.groups(listOf(s("a",0,500),s("b",600,700,1),s("c",800,900))).size)
  assertEquals(2,TranscriptPresentation.groups(listOf(s("a",0,500,-1),s("b",600,800,-1))).size)
  assertEquals(2,TranscriptPresentation.groups(listOf(s("a",0,700),s("b",600,800))).size)
 }
 @Test fun plainTextUsesSameEditsAndRetainsRepeatedSpokenWords() {
  val rows=listOf(s("a",0,500,text="да"),s("b",600,800,text="да"))
  assertEquals("да да",TranscriptPresentation.plain(rows))
  assertEquals("да исправлено",TranscriptPresentation.plain(rows.map { if(it.id=="b") it.copy(text="исправлено",edited=true) else it }))
 }
 @Test fun readingParagraphsRespectSpeakerAndLongPause() {
  assertEquals("а б\n\nв\n\nг",TranscriptPresentation.plain(listOf(s("a",0,500,text="а"),s("b",700,900,text="б"),s("c",1000,1200,1,"в"),s("d",4000,4500,1,"г"))))
 }
 @Test fun thermalPolicyRetainsSevereAndHigherProtection() {
  assertFalse(MlPolicy.coolingRequired(-1));assertFalse(MlPolicy.coolingRequired(0));assertFalse(MlPolicy.coolingRequired(2))
  for(status in 3..6) assertTrue(MlPolicy.coolingRequired(status))
 }
 @Test fun explicitModesAndAllowedThreads() {
  assertEquals("single",MlPolicy.mode(1));assertEquals("fixed",MlPolicy.mode(4));assertEquals("automatic",MlPolicy.mode(-1))
  listOf(1,2,4).forEach { assertEquals(it,MlPolicy.threads(it)) }
 }
 @Test(expected=IllegalArgumentException::class) fun invalidThreadCountRejected() { MlPolicy.threads(32) }
}
