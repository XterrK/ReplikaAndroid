package ru.replika.domain

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.cos
import kotlin.math.sin

class WindowSpeakerRefinerTest {
 private fun measured(turns: List<Turn>,duration: Long,vectors: Map<Int,DoubleArray>)=SpeakerRefiner.cleanWindows(turns,duration).map { it.copy(embedding=vectors.getValue(it.speaker)) }
 private fun activity(turns: List<Turn>)=Alignment.merge(turns.map { Span(it.startMs,it.endMs) })
 @Test fun splitsTwoMeasuredModesInsideOneNativeLabel() {
  val turns=listOf(Turn(0,6000,9));val windows=SpeakerRefiner.cleanWindows(turns,6000).map { it.copy(embedding=if(it.startMs+it.endMs<=6000) doubleArrayOf(1.0,0.0) else doubleArrayOf(0.0,1.0)) }
  val result=WindowSpeakerRefiner.overcluster(turns,windows,6000,WindowSpeakerRefiner.Config(tau=.8,smooth=false))
  assertTrue(result.accepted);assertEquals(2,result.diagnostics["output_clusters"]);assertEquals(activity(turns),activity(result.turns));assertEquals(listOf(0,1),result.turns.map { it.speaker })
  assertEquals(result.turns[0].endMs,result.turns[1].startMs)
  @Suppress("UNCHECKED_CAST") val boundaries=result.diagnostics["new_internal_grid_boundaries_ms"] as List<Long>
  assertTrue(boundaries.isNotEmpty() && boundaries.all { it%125==0L })
 }
 @Test fun canonicalOrderAndIdenticalDuplicatesCannotVoteTwice() {
  val turns=listOf(Turn(0,6000,4));val windows=SpeakerRefiner.cleanWindows(turns,6000).map { it.copy(embedding=if(it.startMs<3000) doubleArrayOf(1.0,0.0) else doubleArrayOf(0.0,1.0)) }
  val a=WindowSpeakerRefiner.overcluster(turns,windows,6000);val b=WindowSpeakerRefiner.overcluster(turns,windows.reversed()+windows.first(),6000)
  assertEquals(a.turns,b.turns);assertEquals(a.diagnostics["window_labels"],b.diagnostics["window_labels"]);assertEquals(1,(b.diagnostics["duplicate_windows"] as List<*>).size)
 }
 @Test fun inclusiveDistanceCutMergesExactThresholdTie() {
  val turns=listOf(Turn(0,1500,3),Turn(2000,3500,7));val windows=measured(turns,3500,mapOf(3 to doubleArrayOf(1.0,0.0),7 to doubleArrayOf(0.0,1.0)))
  assertEquals(1,WindowSpeakerRefiner.overcluster(turns,windows,3500,WindowSpeakerRefiner.Config(tau=0.0)).diagnostics["output_clusters"])
  assertEquals(2,WindowSpeakerRefiner.overcluster(turns,windows,3500,WindowSpeakerRefiner.Config(tau=.000001)).diagnostics["output_clusters"])
 }
 @Test fun completeAndAverageUseDifferentLinkageUpdates() {
  val turns=(0..2).map { Turn(it*2000L,it*2000L+1500,it) };val vectors=(0..2).associateWith { doubleArrayOf(cos(Math.PI*it/6),sin(Math.PI*it/6)) };val windows=measured(turns,5500,vectors)
  assertEquals(2,WindowSpeakerRefiner.overcluster(turns,windows,5500,WindowSpeakerRefiner.Config(tau=.65,method="complete",smooth=false)).diagnostics["output_clusters"])
  assertEquals(1,WindowSpeakerRefiner.overcluster(turns,windows,5500,WindowSpeakerRefiner.Config(tau=.65,method="average",smooth=false)).diagnostics["output_clusters"])
 }
 @Test fun capUsesSameScipyTieTreeWithExplicitForcedMerge() {
  val turns=(0..8).map { Turn(it*2000L,it*2000L+1500,it) };val windows=measured(turns,17500,(0..8).associateWith { i -> DoubleArray(9) { j -> if(i==j) 1.0 else 0.0 } })
  val result=WindowSpeakerRefiner.overcluster(turns,windows,17500,WindowSpeakerRefiner.Config(tau=.9,smooth=false))
  assertEquals(9,result.diagnostics["window_clusters_at_cut"]);assertEquals(8,result.diagnostics["window_clusters_after_cap"]);assertEquals(8,result.diagnostics["output_clusters"])
  val forced=result.diagnostics["forced_cap_merges"] as List<*>;assertEquals(1,forced.size);assertEquals(true,(forced.first() as Map<*,*>)["above_cut"])
  val tree=result.diagnostics["linkage_tree"] as List<*>;val first=tree[0] as List<*>;val second=tree[1] as List<*>
  assertEquals(listOf(0.0,1.0),first.take(2));assertEquals(listOf(2.0,9.0),second.take(2))
 }
 @Test fun nonGridEndpointsAndPausesPreserveExactUnion() {
  val turns=listOf(Turn(13,2151,8),Turn(3003,4599,8));val result=WindowSpeakerRefiner.overcluster(turns,measured(turns,5000,mapOf(8 to doubleArrayOf(1.0,0.0))),5000)
  assertTrue(result.accepted);assertEquals(activity(turns),activity(result.turns));assertEquals(true,result.diagnostics["activity_union_preserved"])
  assertTrue((result.diagnostics["max_assignment_atom_ms"] as Long)<=125)
 }
 @Test fun overlapCollapseCountsSpeakerTimeWithoutChangingSpeechUnion() {
  val turns=listOf(Turn(0,3000,0),Turn(1000,4000,1));val result=WindowSpeakerRefiner.overcluster(turns,measured(turns,4000,mapOf(0 to doubleArrayOf(1.0,0.0),1 to doubleArrayOf(1.0,0.0))),4000)
  assertTrue(result.accepted);assertEquals(activity(turns),activity(result.turns));assertEquals("2000",result.diagnostics["speaker_time_collapsed_ms"].toString())
 }
 @Test fun missingFragmentFallbackIsExplicitAndDoesNotFabricateVector() {
  val turns=listOf(Turn(0,3000,5),Turn(4000,4300,9));val windows=measured(turns,4300,mapOf(5 to doubleArrayOf(1.0,0.0),9 to doubleArrayOf(0.0,1.0)));val result=WindowSpeakerRefiner.overcluster(turns,windows,4300)
  assertTrue(result.accepted);assertEquals("PARTIAL_TEMPORAL",result.diagnostics["status"]);assertEquals(false,result.diagnostics["every_native_label_has_measured_windows"])
  assertEquals(windows.size,result.diagnostics["measured_unique_windows"]);assertEquals(activity(turns),activity(result.turns))
 }
 @Test fun smallGuestStageIsOptionalWithAnExplicitSimilarityGuard() {
  val turns=listOf(Turn(0,5000,0),Turn(6000,7500,1));val windows=measured(turns,7500,mapOf(0 to doubleArrayOf(1.0,0.0),1 to doubleArrayOf(0.0,1.0)))
  val plain=WindowSpeakerRefiner.overcluster(turns,windows,7500);val small=WindowSpeakerRefiner.overcluster(turns,windows,7500,WindowSpeakerRefiner.Config(reassignSmall=true));val guarded=WindowSpeakerRefiner.overcluster(turns,windows,7500,WindowSpeakerRefiner.Config(reassignSmall=true,minimumReassignmentSimilarity=.8))
  assertEquals(2,plain.diagnostics["output_clusters"]);assertEquals(1,small.diagnostics["output_clusters"]);assertEquals(2,guarded.diagnostics["output_clusters"])
 }
 @Test fun invalidVectorsMetadataDimensionsAndConflictsAreUnsupported() {
  val turns=listOf(Turn(0,3000,0));val valid=measured(turns,3000,mapOf(0 to doubleArrayOf(1.0,0.0)))
  val variants=listOf(listOf(valid[0].copy(startMs=1)),listOf(valid[0].copy(clean=false)),listOf(valid[0].copy(embedding=doubleArrayOf(0.0,0.0))),listOf(valid[0].copy(embedding=doubleArrayOf(Double.NaN,0.0))),listOf(valid[0],valid[0].copy(embedding=doubleArrayOf(0.0,1.0))),listOf(valid[0],valid[1].copy(embedding=doubleArrayOf(1.0,0.0,0.0))))
  for(windows in variants) { val result=WindowSpeakerRefiner.overcluster(turns,windows,3000);assertFalse(result.accepted);assertEquals(turns,result.turns) }
 }
 @Test fun emptyAndAllMissingAreDifferentAndBadConfigRejects() {
  assertTrue(WindowSpeakerRefiner.overcluster(emptyList(),emptyList(),0).accepted)
  val missing=WindowSpeakerRefiner.overcluster(listOf(Turn(0,500,4)),emptyList(),500);assertFalse(missing.accepted);assertEquals("no_real_clean_windows",missing.diagnostics["reason"])
  for(cfg in listOf(WindowSpeakerRefiner.Config(tau=Double.NaN),WindowSpeakerRefiner.Config(method="ward"),WindowSpeakerRefiner.Config(maxSpeakers=9),WindowSpeakerRefiner.Config(gridMs=0))) {
   try { WindowSpeakerRefiner.overcluster(emptyList(),emptyList(),0,cfg);fail("bad config") } catch(expected: IllegalArgumentException) { }
  }
 }
 @Test fun longClockGridAndNearestCentersDoNotOverflow() {
  val end=Long.MAX_VALUE;val turns=listOf(Turn(end-5000,end-2000,4),Turn(end-300,end,8));val windows=measured(turns,end,mapOf(4 to doubleArrayOf(1.0,0.0),8 to doubleArrayOf(0.0,1.0)));val result=WindowSpeakerRefiner.overcluster(turns,windows,end)
  assertTrue(result.accepted);assertEquals(activity(turns),activity(result.turns));assertTrue(result.turns.all { it.startMs>=0 && it.endMs<=end })
 }
}
