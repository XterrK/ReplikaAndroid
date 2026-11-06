package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.Span
import ru.replika.domain.Turn
import ru.replika.domain.VadWordPlanner
import ru.replika.domain.VadWordPlanner.AssignedWord
import ru.replika.domain.VadWordPlanner.Word

/** Controlled token/time fixtures, not claims of actual model inference or acoustic alignment. */
class VadWordPlannerTest {
 private fun words(text: String,tokens: List<String?>,vararg seconds: Float) =
  VadWordPlanner.words(text,tokens,seconds,Span(1000,5000))
 private fun interval(word: Word)=Span(word.startMs,word.endMs)
 private fun assigned(a: Long,b: Long,speaker: Int,text: String)=AssignedWord(a,b,text,speaker,emptyList())

 @Test fun asciiPrefixesStandaloneSpaceAndPunctuationReconstructExactly() {
  val result=words("Важно знать. Да!",listOf(" В","а","жно"," ","знать","."," Да","!"),
   .08f,.16f,.24f,.40f,.48f,.72f,.80f,1.20f)
  assertTrue(result.reason,result.supported)
  assertEquals(listOf("Важно","знать.","Да!"),result.words.map { it.text })
  assertEquals(listOf(Span(1080,1280),Span(1480,1520),Span(1800,1840)),result.words.map(::interval))
  assertEquals("Важно знать. Да!",result.words.joinToString(" ") { it.text })
 }

 @Test fun sentencePieceBoundaryAlsoWorksWithoutAssumingItIsRequired() {
  val result=words("Кот спит.",listOf("▁К","от","▁сп","ит","."),.08f,.16f,.40f,.56f,.80f)
  assertTrue(result.reason,result.supported)
  assertEquals(listOf("Кот","спит."),result.words.map { it.text })
  assertEquals(listOf(Span(1080,1200),Span(1400,1600)),result.words.map(::interval))
 }

 @Test fun punctuationOnlyRunsPreserveSpacesButDoNotExtendWordTime() {
  val result=words("— Да — нет!",listOf("—"," Да"," —"," нет","!"),.0f,.08f,.48f,.80f,1.20f)
  assertTrue(result.reason,result.supported)
  assertEquals(listOf("— Да —","нет!"),result.words.map { it.text })
  assertEquals(listOf(Span(1080,1120),Span(1800,1840)),result.words.map(::interval))
 }

 @Test fun punctuationSubstringOfLaterLexicalTokenDoesNotExtendPreviousWord() {
  val result=words("кот! собака",listOf("кот","! собака"),.08f,.40f)
  assertTrue(result.reason,result.supported)
  assertEquals(listOf("кот!","собака"),result.words.map { it.text })
  assertEquals(listOf(Span(1080,1120),Span(1400,1440)),result.words.map(::interval))
 }

 @Test fun repeatedWordsAreNotDeduplicatedAndFloatClockUsesIntegerMilliseconds() {
  val result=words("Кот кот кот.",listOf(" Кот"," кот"," кот","."),.079999998f,.239999994f,.399999976f,.8f)
  assertTrue(result.reason,result.supported)
  assertEquals(listOf("Кот","кот","кот."),result.words.map { it.text })
  assertEquals(listOf(1080L,1240L,1400L),result.words.map { it.startMs })
 }

 @Test fun sameFrameWordsRetainRealEmissionFramesAndHaveExplicitWarnings() {
  val result=words("Да нет",listOf(" Да"," нет"),.08f,.08f)
  assertTrue(result.reason,result.supported)
  assertEquals(listOf(Span(1080,1120),Span(1080,1120)),result.words.map(::interval))
  assertTrue(result.words.all { VadWordPlanner.SAME_FRAME in it.reasons })
 }

 @Test fun nextEmissionCanCapPreviousEstimateWithoutInventingUniformWordTimes() {
  val result=words("Кот нет",listOf(" К","от"," нет"),.08f,.16f,.16f)
  assertTrue(result.reason,result.supported)
  assertEquals(listOf(Span(1080,1160),Span(1160,1200)),result.words.map(::interval))
 }

 @Test fun chunkEndClampsTheLastFrameAndZeroWidthWordsAreUnsupported() {
  val clamped=VadWordPlanner.words("Кот",listOf(" Кот"),floatArrayOf(.08f),Span(1000,1100))
  assertTrue(clamped.reason,clamped.supported)
  assertEquals(Span(1080,1100),interval(clamped.words.single()))
  val noRoom=VadWordPlanner.words("Кот",listOf(" Кот"),floatArrayOf(.08f),Span(1000,1080))
  assertFalse(noRoom.supported);assertTrue(noRoom.words.isEmpty())
  assertEquals("word_outside_chunk",noRoom.reason)
 }

 @Test fun missingInvalidOrUnsupportedTokenTimesNeverProduceUniformSubstitutes() {
  val invalid=listOf(
   words("Кот",emptyList()),
   words("Кот",listOf(" Кот")),
   words("Кот",listOf(null),.08f),
   words("Кот",listOf(" Кот"),Float.NaN),
   words("Кот",listOf(" Кот"),Float.POSITIVE_INFINITY),
   words("Кот",listOf(" Кот"),-.04f),
   words("Кот",listOf(" Кот"),4.04f),
   words("Кот",listOf(" Кот"),.10f),
   words("Кот нет",listOf(" Кот"," нет"),.16f,.08f),
   words("Кот",listOf(" собака"),.08f),
   words("Кот нет",listOf(" Кот нет"),.08f),
   VadWordPlanner.words("Кот",listOf(" Кот"),floatArrayOf(.08f),Span(1,1)),
   VadWordPlanner.words("Кот",listOf(" Кот"),floatArrayOf(.08f),Span(0,1000),frameStrideMs=0)
  )
  invalid.forEach { assertFalse(it.reason,it.supported);assertTrue(it.reason,it.words.isEmpty()) }
 }

 @Test fun emptyResultIsDistinctFromUnsupportedAlignment() {
  val result=words(" \n\t",emptyList())
  assertTrue(result.supported);assertEquals("empty_result",result.reason);assertTrue(result.words.isEmpty())
  val punctuation=words("!",listOf("!"),.08f)
  assertFalse(punctuation.supported);assertEquals("no_lexical_words",punctuation.reason)
 }

 @Test fun energyCutUsesGlobalWindowCenterAndEarliestEqualMinimum() {
  val examined=mutableListOf<Span>()
  val chunks=VadWordPlanner.planChunks(listOf(Span(3000,45000)),energy={a,b ->
   examined+=Span(a,b)
   if(a==19080L || a==19120L) 0.0 else 1.0
  })
  assertEquals(19100L,chunks.first().endMs)
  assertEquals(Span(19000,19040),examined.first())
  assertTrue(examined.contains(Span(22960,23000)))
  assertEquals(3000L,chunks.first().startMs);assertEquals(45000L,chunks.last().endMs)
  assertEquals(42000L,chunks.sumOf { it.endMs-it.startMs })
  assertTrue(chunks.zipWithNext().all { (a,b)->a.endMs==b.startMs })
  assertTrue(chunks.all { it.endMs>it.startMs && it.endMs-it.startMs<=20000 })
 }

 @Test fun vadCoverageMergesOverlapsButKeepsRealPausesAndFinalPartialChunk() {
  val spans=listOf(Span(100,25100),Span(20000,40101),Span(41000,41123))
  val chunks=VadWordPlanner.planChunks(spans,energy={_,_->1.0})
  assertEquals(Span(41000,41123),chunks.last())
  assertEquals(40001L+123,chunks.sumOf { it.endMs-it.startMs })
  assertEquals(100L,chunks.first().startMs)
  assertTrue(chunks.none { it.startMs<41000 && it.endMs>40101 })
 }

 @Test fun hardCutFallbackAndShortChunksNeverReadAnEnergyWindow() {
  val chunks=VadWordPlanner.planChunks(listOf(Span(0,40001)),energy={_,_->error("Energy callback must not run")},energySplit=false)
  assertEquals(listOf(Span(0,20000),Span(20000,40000),Span(40000,40001)),chunks)
  val exact=VadWordPlanner.planChunks(listOf(Span(7,20007)),energy={_,_->error("No split needed")})
  assertEquals(listOf(Span(7,20007)),exact)
 }

 @Test fun invalidEnergyIsRejectedRatherThanSelectedAsAQuietBoundary() {
  for(value in listOf(Double.NaN,Double.POSITIVE_INFINITY,-1.0)) {
   assertThrows(IllegalArgumentException::class.java) { VadWordPlanner.planChunks(listOf(Span(0,25000)),energy={_,_->value}) }
  }
  assertThrows(IllegalArgumentException::class.java) { VadWordPlanner.planChunks(emptyList(),energy={_,_->0.0},maxMs=0) }
 }

 @Test fun maximalUnionOverlapWinsWithoutDoubleCountingRepeatedTurns() {
  val word=Word(0,100,"Кот")
  val assigned=VadWordPlanner.assignWords(listOf(word),listOf(Turn(0,60,3),Turn(0,60,3),Turn(0,100,8))).single()
  assertEquals(8,assigned.speaker)
  assertTrue(VadWordPlanner.OVERLAP in assigned.reasons)
 }

 @Test fun equalSpeakerEvidenceStaysUnknownAndDistinguishesTransitionFromOverlap() {
  val word=Word(0,100,"Да")
  val boundary=VadWordPlanner.assignWords(listOf(word),listOf(Turn(0,50,0),Turn(50,100,1))).single()
  assertEquals(-1,boundary.speaker)
  assertTrue(VadWordPlanner.TIED_SPEAKER in boundary.reasons)
  assertTrue(VadWordPlanner.SPEAKER_BOUNDARY in boundary.reasons)
  assertFalse(VadWordPlanner.OVERLAP in boundary.reasons)
  val overlap=VadWordPlanner.assignWords(listOf(word),listOf(Turn(0,100,0),Turn(0,100,1))).single()
  assertEquals(-1,overlap.speaker);assertTrue(VadWordPlanner.OVERLAP in overlap.reasons)
 }

 @Test fun missingOrUnknownNativeEvidenceDoesNotInventSpeakerIdentity() {
  val assigned=VadWordPlanner.assignWords(listOf(Word(0,40,"Да")),listOf(Turn(0,40,-1),Turn(40,80,1))).single()
  assertEquals(-1,assigned.speaker)
  assertEquals(listOf(VadWordPlanner.NO_SPEAKER),assigned.reasons)
 }

 @Test fun groupingKeepsRepeatedWordsSpeakerChangesSourceAndWarnings() {
  val words=listOf(assigned(0,40,0,"Кот"),assigned(80,120,0,"кот,"),assigned(160,200,1,"Да!"),
   AssignedWord(240,280,"Нет?",0,listOf("Причина")))
  val segments=VadWordPlanner.groupWords(words,"Controlled fixture")
  assertEquals(listOf("Кот кот,","Да!","Нет?"),segments.map { it.text })
  assertEquals(listOf(0,1,0),segments.map { it.speakerId })
  assertEquals(0L,segments.first().startMs);assertEquals(120L,segments.first().endMs)
  assertTrue(segments.all { it.source=="Controlled fixture" })
  assertEquals(listOf("Причина"),segments.last().reasons)
  assertEquals(2,VadWordPlanner.groupWords(words.take(2),"chunk1").size+
   VadWordPlanner.groupWords(words.take(2),"chunk2").size)
 }

 @Test fun seamRulesDoNotRewriteASingleUnsplitNativeChunk() {
  val words=listOf(assigned(0,40,0,"да,"),assigned(80,120,0,"действительно"))
  val segments=VadWordPlanner.groupWords(words,"Controlled unsplit fixture",seamPunctuation=true)
  assertEquals(1,segments.size)
  assertEquals("да, действительно",segments.single().text)
  assertFalse(VadWordPlanner.SEAM_EDIT in segments.single().reasons)
 }

 @Test fun seamRulesAreOptionalPreserveQuestionsAndDoNotChangeLexicalWords() {
  val words=listOf(assigned(0,40,0,"кот,"),assigned(80,120,1,"«да!»"),assigned(160,200,2,"почему?"),assigned(240,280,3,"нет"))
  assertEquals(listOf("кот,","«да!»","почему?","нет"),VadWordPlanner.groupWords(words,"test").map { it.text })
  val changed=VadWordPlanner.groupWords(words,"test",seamPunctuation=true)
  assertEquals(listOf("Кот.","«Да!»","Почему?","Нет."),changed.map { it.text })
  assertTrue(changed.all { VadWordPlanner.SEAM_EDIT in it.reasons })
  fun lexical(text: String)=text.lowercase().filter { it.isLetterOrDigit() }
  assertEquals(words.map { lexical(it.text) },changed.map { lexical(it.text) })
  assertEquals("Да!",VadWordPlanner.seamText("Да!"))
  assertEquals("Список:",VadWordPlanner.seamText("список:"))
  assertEquals("Далее;",VadWordPlanner.seamText("далее;"))
  assertEquals("«Кот».",VadWordPlanner.seamText("«кот»"))
 }
}
