package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.ui.*
import ru.replika.data.SegmentRow

class EditorialV14Test {
 @Test fun staleShortFlagNeverMakesACombinedSegmentShort() {
  val row=SegmentRow("legacy","r",0,16000,0,"Объединённый текст","fixture",reasons="""["Короткая реплика возле границы"]""")
  assertTrue(reviewIssues(row).isEmpty())
  assertEquals("""["Короткая реплика возле границы"]""",row.reasons)
 }
 @Test fun usefulFlagsAndUnknownSurviveDurationFlagFiltering() {
  val row=SegmentRow("legacy","r",0,16000,-1,"Текст","fixture",reasons="""["Пересечение голосов: слова не разделены","Короткая реплика возле границы"]""")
  assertTrue(reviewIssues(row).any { it.title=="Говорящий не определён" })
  assertTrue(reviewIssues(row).any { it.title=="Пересечение голосов" })
  assertFalse(reviewIssues(row).any { it.explanation.contains("700") })
 }
 @Test fun envelopeRespondsToRealPeakMagnitudeAndDecaysSmoothly() {
  val e=VoiceEnvelope();repeat(40) { e.sample(.001f) };assertTrue(e.level<.01f)
  val quiet=(1..8).map { e.sample(.04f) }.last()
  val loud=(1..8).map { e.sample(.75f) }.last()
  assertTrue(quiet>.05f);assertTrue(loud>quiet+.2f)
  val after=e.sample(0f);assertTrue(after<loud);assertTrue(after>loud*.7f)
  repeat(80) { e.sample(0f) };assertTrue(e.level<.01f)
 }
 @Test fun steadySpeechDoesNotBecomeNoiseAndInvalidInputsStayFinite() {
  val e=VoiceEnvelope();repeat(400) { e.sample(.3f) };assertTrue(e.level>.4f);assertTrue(e.noiseFloor<=.018f)
  listOf(Float.NaN,Float.POSITIVE_INFINITY,-10f,5f).forEach { assertTrue(e.sample(it).isFinite()) }
 }
 @Test fun springHasBoundedOvershootAndSettlesAfterLoudSpeech() {
  val d=OrbDynamics();repeat(100) { d.step(1f/60,1f,true) };assertTrue(d.expansion in .18f.. .22f)
  val radii=(0..64).map { d.radiusAt(it*.1f) };assertTrue(radii.max()-radii.min()>.005f)
  repeat(600) { d.step(1f/60,0f,false) };assertTrue(kotlin.math.abs(d.expansion)<.001f)
  for(i in 0..1000) { d.step(if(i%2==0) 2f else .001f,if(i%7==0) 1f else 0f,true);assertTrue(d.expansion in -.025f.. .235f);assertTrue(d.modes.all { it.isFinite() && kotlin.math.abs(it)<=.026f }) }
 }
 @Test fun reducedMotionShowsStateWithoutOscillation() {
  val d=OrbDynamics();repeat(90) { d.step(1f/60,.5f,true,true) }
  assertTrue(d.expansion>.09f);assertTrue(d.modes.all { it==0f })
 }
}
