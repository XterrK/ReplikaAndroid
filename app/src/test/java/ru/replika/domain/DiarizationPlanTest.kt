package ru.replika.domain

import org.junit.Assert.*
import org.junit.Test

class DiarizationPlanTest {
 @Test fun historicalMissingDataRemainsLegacyAndWireIDsAreExplicit() {
  assertEquals(DiarizationPlan.LEGACY,DiarizationPlan.fromPersistedId(null))
  assertEquals(DiarizationPlan.LEGACY,DiarizationPlan.fromPersistedId("v16"))
  assertEquals(DiarizationPlan.ERES2NET_WINDOW_V1,DiarizationPlan.fromPersistedId("eres2net_window_v1"))
  assertEquals(setOf("v16","eres2net_window_v1"),DiarizationPlan.entries.map { it.wireId }.toSet())
 }
 @Test fun unknownIDsRejectRatherThanSilentlySelectCandidate() {
  for(id in listOf("","resnet34_c1","eres2net_window","future")) {
   try { DiarizationPlan.fromPersistedId(id);fail("unknown id") } catch(expected: IllegalStateException) { }
  }
 }
 @Test fun onlyAutomaticNegativeOneActivatesWindowRefinement() {
  val candidate=DiarizationPlan.ERES2NET_WINDOW_V1
  assertEquals(candidate,candidate.forExpectedSpeakers(-1))
  for(k in 1..20) assertEquals(DiarizationPlan.LEGACY,candidate.forExpectedSpeakers(k))
  for(k in listOf(-1,1,2,20)) assertEquals(DiarizationPlan.LEGACY,DiarizationPlan.LEGACY.forExpectedSpeakers(k))
 }
 @Test fun invalidExpectedCountsReject() {
  for(k in listOf(-2,0,21,Int.MAX_VALUE)) {
   try { DiarizationPlan.ERES2NET_WINDOW_V1.forExpectedSpeakers(k);fail("invalid count") } catch(expected: IllegalArgumentException) { }
  }
 }
 @Test fun candidateRequiresTheExactContext600AsrPair() {
  DiarizationPlan.ERES2NET_WINDOW_V1.requirePairedAsr(AsrPlan.VAD_WORDS_CONTEXT600)
  for(asr in AsrPlan.entries.filter { it!=AsrPlan.VAD_WORDS_CONTEXT600 }) {
   try { DiarizationPlan.ERES2NET_WINDOW_V1.requirePairedAsr(asr);fail("unpaired") } catch(expected: IllegalArgumentException) { }
  }
  for(asr in AsrPlan.entries) DiarizationPlan.LEGACY.requirePairedAsr(asr)
 }
 @Test fun originalModelPathsAndLegacyNativeNumbersAreRetained() {
  for(plan in DiarizationPlan.entries) {
   assertEquals("diar/embedding.onnx",plan.embeddingPath);assertEquals("diar/segmentation.onnx",plan.segmentationPath)
   assertEquals(.1f,plan.segmentationWindowShiftRatio);assertEquals(.2f,plan.diarMinDurationOnSec);assertEquals(.5f,plan.diarMinDurationOffSec)
  }
  assertEquals(.5f,DiarizationPlan.LEGACY.clusterThreshold);assertNull(DiarizationPlan.LEGACY.windowConfig)
  assertEquals(.3f,DiarizationPlan.ERES2NET_WINDOW_V1.clusterThreshold)
 }
 @Test fun selectedWindowPolicyUsesDoubleTauAndExactFrozenDefaults() {
  val cfg=DiarizationPlan.ERES2NET_WINDOW_V1.windowConfig!!
  assertEquals(.36,cfg.tau,0.0);assertEquals("average",cfg.method);assertTrue(cfg.reassignSmall)
  assertEquals(125L,cfg.gridMs);assertEquals(8,cfg.maxSpeakers);assertEquals(2000L,cfg.minClusterMs)
  assertEquals(.03,cfg.minClusterFraction,0.0);assertNull(cfg.minimumReassignmentSimilarity);assertTrue(cfg.smooth);assertEquals(500L,cfg.smoothMs)
 }
}
