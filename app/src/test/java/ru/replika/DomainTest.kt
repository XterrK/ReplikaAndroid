package ru.replika
import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.*
import ru.replika.data.SegmentRow
class DomainTest {
 @Test fun downsamplingFilterPreservesVoiceAndRejectsAliases() {
  fun rms(hz: Double): Double { val filter=PcmLowPass(48000);var energy=0.0;for(i in 0 until 4800) { val v=filter.accept(kotlin.math.sin(2*kotlin.math.PI*hz*i/48000).toFloat());if(i>=800) energy+=v*v };return kotlin.math.sqrt(energy/4000) }
  assertTrue(rms(1000.0)>0.65);assertTrue(rms(12000.0)<0.03)
  assertEquals(31,PcmLowPass(48000).delaySamples);assertEquals(0,PcmLowPass(16000).delaySamples)
 }
 @Test fun mergeIntervals() { assertEquals(listOf(Span(0,30),Span(40,50)),Alignment.merge(listOf(Span(20,30),Span(0,20),Span(40,50),Span(7,7)))) }
 @Test fun stableSpeakerIds() { assertEquals(listOf(0,1,0),Alignment.stable(listOf(Turn(30,40,8),Turn(0,10,8),Turn(10,30,2))).map { it.speaker }) }
 @Test fun unknownIdsStayUnknown() { assertEquals(-1,Alignment.stable(listOf(Turn(0,10,-1))).single().speaker) }
 @Test fun noRandomTextAssignmentAtOverlap() {
  val s=Alignment.slices(listOf(Span(0,3000)),listOf(Turn(0,2000,0),Turn(1000,3000,1)))
  assertEquals(listOf(0,-1,1),s.map { it.speaker });assertTrue(s[1].reasons.any { "Пересечение" in it });assertEquals(3000,s.sumOf { it.endMs-it.startMs })
 }
 @Test fun noOverlappingChunksOrDuplicates() {
  val s=Alignment.slices(listOf(Span(0,25000),Span(20000,30000)),listOf(Turn(0,30000,0)))
  assertEquals(2,s.size);assertEquals(s[0].endMs,s[1].startMs);assertEquals(30000,s.sumOf { it.endMs-it.startMs })
 }
 @Test fun shortTurnAndUnknownWarningsAreComputed() { val s=Alignment.slices(listOf(Span(100,400)),emptyList()).single();assertEquals(-1,s.speaker);assertEquals(2,s.reasons.size) }
 @Test fun contextClampsToFileAndMergesCloseSpeech() {
  assertEquals(listOf(Span(0,1000)),Alignment.context(listOf(Span(50,400),Span(500,950)),1000,100,100))
  assertEquals(listOf(Span(0,100)),Alignment.context(listOf(Span(-10,60)),100,50,500))
  assertTrue(Alignment.context(listOf(Span(500,600)),100).isEmpty())
 }
 @Test fun contextPreservesOriginalClockAndSpeakerChanges() {
  val spans=Alignment.context(listOf(Span(1000,3000),Span(3100,4000)),5000,100,100)
  val slices=Alignment.slices(spans,listOf(Turn(900,2500,0),Turn(2500,4100,1)))
  assertEquals(listOf(900L,2500L),slices.map { it.startMs });assertEquals(4100L,slices.last().endMs)
  assertEquals(listOf(0,1),slices.map { it.speaker });assertEquals(3200L,slices.sumOf { it.endMs-it.startMs })
 }
 @Test fun sameSpeakerBoundariesDoNotFragmentAsr() {
  val slices=Alignment.slices(listOf(Span(0,3000)),listOf(Turn(0,1000,0),Turn(1000,2000,0),Turn(2000,3000,0)))
  assertEquals(1,slices.size);assertEquals(3000L,slices.single().endMs);assertTrue(slices.single().reasons.isEmpty())
 }
 @Test fun contextNeverCreatesDuplicateChunks() {
  val slices=Alignment.slices(Alignment.context(listOf(Span(0,20000),Span(19500,30000)),30000,200,200),listOf(Turn(0,30000,0)))
  assertEquals(30000L,slices.sumOf { it.endMs-it.startMs });assertEquals(slices[0].endMs,slices[1].startMs)
 }
 @Test fun manualCorrectionsPersistInRowRoundtrip() {
  val s=Segment(startMs=2,endMs=8,speakerId=0,text="исходное",source="real",reasons=listOf("граница"))
  val edited=SegmentRow.from("record",s).copy(text="исправлено",speakerId=2,edited=true,reviewed=true).domain()
  assertEquals(s.id,edited.id);assertEquals(2,edited.speakerId);assertEquals("исправлено",edited.text);assertTrue(edited.edited);assertTrue(edited.reviewed);assertEquals(s.reasons,edited.reasons)
 }
 @Test fun exportsPreserveTimesTextNames() {
  val s=listOf(Segment(id="id",startMs=1234,endMs=5678,speakerId=0,text="Привет\nмир",source="GigaAM",edited=true))
  assertTrue(Exporter.txt("Title",s) { "Анна" }.contains("00:00:01.234"))
  val srt=Exporter.srt(s) { "Анна" };assertTrue(srt.contains("00:00:01,234 --> 00:00:05,678"));assertTrue(srt.contains("Анна: Привет мир"))
  val j=org.json.JSONObject(Exporter.json("Title",s) { "Анна" }).getJSONArray("segments").getJSONObject(0)
  assertEquals(1234,j.getLong("startMs"));assertTrue(j.getBoolean("edited"));assertFalse(j.has("confidence"))
 }
 @Test fun ratesRequireGroundTruth() { assertNull(Benchmark.wer("","hello"));assertNull(Benchmark.cer("","hello"));assertEquals(0.5,Benchmark.wer("один два","один три")!!,1e-10);assertEquals(0.0,Benchmark.cer("Ёж!","еж")!!,1e-10) }
 @Test fun derOptimalPermutationAndOverlap() { val r=listOf(Turn(0,1000,0),Turn(500,1500,1));val h=listOf(Turn(0,1000,8),Turn(500,1500,9));assertEquals(0.0,Benchmark.der(r,h,1500).rate!!,1e-9) }
 @Test fun derMissAndFalseAlarm() { val d=Benchmark.der(listOf(Turn(0,1000,0)),listOf(Turn(500,1500,2)),1500);assertEquals(500.0,d.missMs,0.0);assertEquals(500.0,d.falseAlarmMs,0.0);assertEquals(1.0,d.rate!!,0.0) }
 @Test fun derConfusion() { val d=Benchmark.der(listOf(Turn(0,1000,0),Turn(1000,2000,1)),listOf(Turn(0,2000,4)),2000);assertEquals(0.5,d.rate!!,0.0) }
 @Test fun contextualCropUsesOriginalClockAcrossDiarizationBoundary() {
  val spans=Alignment.context(listOf(Span(102,8550)),11290,100,0)
  assertEquals(listOf(Span(2,8550)),spans)
  val slices=Alignment.slices(spans,listOf(Turn(31,8485,0)))
  assertEquals(listOf(Slice(2,31,-1,listOf("Неоднозначный говорящий","Короткая реплика возле границы")),Slice(31,8485,0,emptyList()),Slice(8485,8550,-1,listOf("Неоднозначный говорящий","Короткая реплика возле границы"))),slices)
  assertTrue(slices.zipWithNext().all { (a,b) -> a.endMs==b.startMs })
 }

}
