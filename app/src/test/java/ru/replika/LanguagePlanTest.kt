package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.*

class LanguagePlanTest {
 private fun ms(probes: List<List<Span>>)=probes.map { probe -> probe.sumOf { it.endMs-it.startMs } }

 @Test fun probesTakeThreeTenSecondPiecesFromTheFirstThirtySecondsOfSpeech() {
  assertEquals(listOf(10_000L,10_000L,10_000L),ms(LanguagePlan.probes(listOf(Span(0,60_000)))))
  assertEquals(listOf(10_000L,10_000L,5_000L),ms(LanguagePlan.probes(listOf(Span(0,25_000)))))
  assertTrue(LanguagePlan.probes(emptyList()).isEmpty())
 }

 @Test fun probesConcatenateNeighbouringChunksAndDropATinyTail() {
  val probes=LanguagePlan.probes(listOf(Span(0,4_000),Span(5_000,9_000),Span(10_000,13_000)))
  assertEquals(listOf(Span(0,4_000),Span(5_000,9_000),Span(10_000,12_000)),probes[0])
  assertEquals(listOf(Span(12_000,13_000)),probes[1])
  assertEquals(listOf(10_000L),ms(LanguagePlan.probes(listOf(Span(0,10_500)))))
  assertTrue(LanguagePlan.probes(listOf(Span(0,900))).isEmpty())
 }

 @Test fun englishNeedsAStrictMajorityAndEveryDoubtIsRussian() {
  val en=AsrLanguage.EN;val ru=AsrLanguage.RU
  assertEquals(ru,LanguagePlan.vote(emptyList()))
  assertEquals(en,LanguagePlan.vote(listOf(en)))
  assertEquals(ru,LanguagePlan.vote(listOf(en,ru)))
  assertEquals(en,LanguagePlan.vote(listOf(en,en,ru)))
  assertEquals(ru,LanguagePlan.vote(listOf(en,ru,ru)))
 }

 @Test fun everyNonEnglishWhisperCodeIsRussian() {
  assertEquals(AsrLanguage.EN,AsrLanguage.fromWhisper("en"))
  assertEquals(AsrLanguage.EN,AsrLanguage.fromWhisper(" EN "))
  listOf("ru","uk","de","zh","",null).forEach { assertEquals(AsrLanguage.RU,AsrLanguage.fromWhisper(it)) }
 }

 @Test fun historicalWorkWithoutLanguageKeyStaysRussian() {
  assertEquals(LanguageMode.RU,LanguageMode.fromPersistedId(null))
  assertEquals(LanguageMode.AUTO,LanguageMode.fromPersistedId("auto"))
  assertEquals(AsrLanguage.EN,LanguageMode.EN.forced)
  assertNull(LanguageMode.AUTO.forced)
 }

 @Test(expected=IllegalStateException::class)
 fun unknownLanguageModeFailsLoudly() { LanguageMode.fromPersistedId("de") }

 @Test fun shortChunksInheritTheFileDecisionInPerSegmentMode() {
  assertEquals(AsrLanguage.RU,LanguagePlan.segmentLanguage(AsrLanguage.EN,1_499,AsrLanguage.RU))
  assertEquals(AsrLanguage.EN,LanguagePlan.segmentLanguage(AsrLanguage.EN,1_500,AsrLanguage.RU))
  assertEquals(AsrLanguage.EN,LanguagePlan.segmentLanguage(null,5_000,AsrLanguage.EN))
 }

 @Test fun singleLanguageKeepsChronologicalOrderAndMixedRunsRussianFirst() {
  val ru=AsrLanguage.RU;val en=AsrLanguage.EN
  assertEquals(listOf(0,1,2,3),LanguagePlan.recognitionOrder(listOf(ru,ru,ru,ru)))
  assertEquals(listOf(0,1,2),LanguagePlan.recognitionOrder(listOf(en,en,en)))
  assertEquals(listOf(1,3,0,2),LanguagePlan.recognitionOrder(listOf(en,ru,en,ru)))
 }

 @Test fun decisionSummaryAndTranscriptBadge() {
  val mixed=LanguageDecision(LanguageMode.AUTO,true,AsrLanguage.RU,listOf(AsrLanguage.RU,AsrLanguage.EN),reason="whisper_vote")
  assertTrue(mixed.mixed);assertEquals("mixed",mixed.summary)
  assertEquals("ru",LanguageDecision(LanguageMode.AUTO,false,AsrLanguage.RU,emptyList(),reason="no_speech").summary)
  assertEquals("en",TranscriptLanguage.fromDiagnostics("{\n  \"asrLanguage\": \"en\",\n  \"x\": 1\n}"))
  assertNull(TranscriptLanguage.fromDiagnostics("{\"backend\":\"GigaAM\"}"))
  assertEquals("RU · GigaAM",TranscriptLanguage.badge(null))
  assertEquals("EN · Parakeet",TranscriptLanguage.badge("en"))
  assertEquals(listOf(LanguageMode.EN,LanguageMode.AUTO),TranscriptLanguage.rerunTargets(null))
  assertEquals(listOf(LanguageMode.RU,LanguageMode.AUTO),TranscriptLanguage.rerunTargets("en"))
 }
}
