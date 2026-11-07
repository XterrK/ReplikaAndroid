package ru.replika.domain

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.cos
import kotlin.math.sin

class SpeakerRefinerTest {
 private fun isolated()=SpeakerRefiner.Config(mergeSimilar=false,useEigengap=false,reassignSmall=false,smooth=false)
 private fun measured(turns: List<Turn>,duration: Long,vectors: Map<Int,DoubleArray>)=SpeakerRefiner.cleanWindows(turns,duration).map { it.copy(embedding=vectors.getValue(it.speaker)) }
 @Test fun cleanExclusiveWindowsDoNotCrossOverlapOrPause() {
  val turns=listOf(Turn(0,3000,0),Turn(1000,2000,1),Turn(4000,5000,0))
  val windows=SpeakerRefiner.cleanWindows(turns,5000)
  assertEquals(listOf(0L to 1000L,2000L to 3000L,4000L to 5000L),windows.map { it.startMs to it.endMs })
  assertTrue(windows.all { it.speaker==0 })
 }
 @Test fun emptyUnknownAndNoMeasuredCentroidAreDifferent() {
  assertTrue(SpeakerRefiner.refine(emptyList(),emptyList(),0).accepted)
  val unknown=SpeakerRefiner.refine(listOf(Turn(0,1000,-1)),emptyList(),1000)
  assertTrue(unknown.accepted);assertEquals("UNKNOWN_ONLY",unknown.diagnostics["status"])
  val missing=SpeakerRefiner.refine(listOf(Turn(0,500,0)),emptyList(),500)
  assertFalse(missing.accepted);assertEquals("no_measured_centroids",missing.diagnostics["reason"])
 }
 @Test fun exactCosineThresholdDoesNotMergeAndStableIDsFollowFirstAppearance() {
  val turns=listOf(Turn(0,3000,8),Turn(4000,7000,2));val windows=measured(turns,7000,mapOf(8 to doubleArrayOf(1.0,0.0),2 to doubleArrayOf(0.0,1.0)))
  val result=SpeakerRefiner.refine(turns,windows,7000,isolated().copy(mergeSimilar=true,mergeThreshold=0.0))
  assertEquals(listOf(0,1),result.turns.map { it.speaker })
  assertEquals(emptyList<Any>(),result.diagnostics["merges"])
 }
 @Test fun completeLinkGuardBlocksCentroidChaining() {
  val turns=(0..2).map { Turn(it*4000L,it*4000L+3000,it) }
  val vectors=(0..2).associateWith { doubleArrayOf(cos(Math.PI*it/9),sin(Math.PI*it/9)) }
  val windows=measured(turns,12000,vectors)
  val ordinary=SpeakerRefiner.refine(turns,windows,12000,isolated().copy(mergeSimilar=true))
  val guarded=SpeakerRefiner.refine(turns,windows,12000,isolated().copy(mergeSimilar=true,completeLinkGuard=true))
  assertEquals(1,ordinary.diagnostics["output_clusters"]);assertEquals(2,guarded.diagnostics["output_clusters"])
 }
 @Test fun symmetricCosineTieMatchesPythonFirstAppearanceRatherThanRoundingDrift() {
  val turns=listOf(Turn(0,4000,40),Turn(5000,9000,70),Turn(10000,14000,90))
  val vectors=mapOf(40 to doubleArrayOf(1.0,0.0),70 to doubleArrayOf(0.8191520442889918,0.573576436351046),90 to doubleArrayOf(0.3420201433256688,0.9396926207859083))
  val result=SpeakerRefiner.refine(turns,measured(turns,14000,vectors),14000,isolated().copy(mergeSimilar=true,mergeThreshold=.5,completeLinkGuard=true))
  assertEquals(listOf(0,0,1),result.turns.map { it.speaker })
 }
 @Test fun distinctShortVoiceHasExplicitSimilarityGuard() {
  val turns=listOf(Turn(0,5000,0),Turn(6000,7200,1));val windows=measured(turns,8000,mapOf(0 to doubleArrayOf(1.0,0.0),1 to doubleArrayOf(0.0,1.0)))
  val plain=SpeakerRefiner.refine(turns,windows,8000,isolated().copy(reassignSmall=true))
  val guarded=SpeakerRefiner.refine(turns,windows,8000,isolated().copy(reassignSmall=true,minimumReassignmentSimilarity=.7))
  assertEquals(1,plain.diagnostics["output_clusters"]);assertEquals(2,guarded.diagnostics["output_clusters"])
 }
 @Test fun missingFragmentRetainsOrUsesExplicitTemporalFallback() {
  val turns=listOf(Turn(0,5000,0),Turn(6000,10000,1),Turn(10000,10220,2))
  val vectors=mapOf(0 to doubleArrayOf(1.0,0.0),1 to doubleArrayOf(0.0,1.0))
  val windows=SpeakerRefiner.cleanWindows(turns,11000).filter { it.speaker in vectors }.map { it.copy(embedding=vectors.getValue(it.speaker)) }
  val retain=SpeakerRefiner.refine(turns,windows,11000,isolated().copy(reassignSmall=true))
  val temporal=SpeakerRefiner.refine(turns,windows,11000,isolated().copy(reassignSmall=true,smallMissingCentroidPolicy="temporal"))
  assertEquals(3,retain.diagnostics["output_clusters"]);assertEquals(2,temporal.diagnostics["output_clusters"])
  assertEquals(false,temporal.diagnostics["fully_acoustic_supported"])
 }
 @Test fun eigengapFindsTwoDisconnectedAcousticComponents() {
  val vectors=listOf(doubleArrayOf(1.0,0.0),doubleArrayOf(1.0,0.0),doubleArrayOf(0.0,1.0),doubleArrayOf(0.0,1.0))
  val result=SpeakerRefiner.estimateSpeakers(vectors,.5)
  assertEquals(2,result["estimated_k"])
  val values=result["eigenvalues"] as List<*>
  assertEquals(0.0,values[0] as Double,1e-10);assertEquals(0.0,values[1] as Double,1e-10)
  assertEquals(2.0,values[2] as Double,1e-10);assertEquals(2.0,values[3] as Double,1e-10)
 }
 @Test fun eigengapStageActuallyMergesWhenCosineStageIsDisabled() {
  val turns=listOf(Turn(0,4000,40),Turn(5000,9000,70),Turn(10000,14000,90))
  val windows=measured(turns,14000,mapOf(40 to doubleArrayOf(1.0,0.0),70 to doubleArrayOf(.99,.01),90 to doubleArrayOf(0.0,1.0)))
  val result=SpeakerRefiner.refine(turns,windows,14000,isolated().copy(useEigengap=true))
  assertEquals(listOf(0,0,1),result.turns.map { it.speaker })
  val merges=result.diagnostics["merges"] as List<*>
  assertEquals(1,merges.size);assertEquals("eigengap",(merges.first() as Map<*,*>)["stage"])
 }
 @Test fun flatSpectrumDoesNotInventOneSpeaker() {
  val vectors=(0..4).map { i -> DoubleArray(5) { j -> if(i==j) 1.0 else 0.0 } }
  assertEquals(5,SpeakerRefiner.estimateSpeakers(vectors)["estimated_k"])
 }
 @Test fun invalidAndConflictingWindowsNeverFabricateCentroids() {
  val turns=listOf(Turn(0,3000,0));val window=SpeakerRefiner.EmbeddingWindow(0,1500,0,doubleArrayOf(1.0,0.0))
  val result=SpeakerRefiner.refine(turns,listOf(window,window.copy(embedding=doubleArrayOf(0.0,1.0))),3000)
  assertFalse(result.accepted);assertEquals("no_measured_centroids",result.diagnostics["reason"])
  for(v in listOf(doubleArrayOf(Double.NaN,0.0),doubleArrayOf(0.0,0.0),doubleArrayOf(Double.POSITIVE_INFINITY,0.0))) {
   assertFalse(SpeakerRefiner.refine(turns,listOf(window.copy(embedding=v)),3000).accepted)
  }
 }
 @Test fun extremeFiniteVectorsAndDuplicateZeroSignsStayFinite() {
  val turns=listOf(Turn(0,3000,0))
  for(v in listOf(doubleArrayOf(1e308,1e308),doubleArrayOf(1e-300,1e-300))) {
   val result=SpeakerRefiner.refine(turns,listOf(SpeakerRefiner.EmbeddingWindow(0,1500,0,v)),3000)
   assertTrue(result.accepted)
  }
  val windows=listOf(SpeakerRefiner.EmbeddingWindow(0,1500,0,doubleArrayOf(1.0,0.0)),SpeakerRefiner.EmbeddingWindow(0,1500,0,doubleArrayOf(1.0,-0.0)))
  assertTrue(SpeakerRefiner.refine(turns,windows,3000).accepted)
 }
 @Test fun hardCapReportsLowSimilarityAndNeverUsesMissingCentroids() {
  val turns=(0..8).map { Turn(it*4000L,it*4000L+3000,it) }
  val windows=measured(turns,35000,(0..8).associateWith { i -> DoubleArray(9) { j -> if(i==j) 1.0 else 0.0 } })
  val result=SpeakerRefiner.refine(turns,windows,35000,isolated())
  assertTrue(result.accepted);assertEquals(8,result.diagnostics["output_clusters"]);assertEquals(1,result.diagnostics["forced_cap_merges"])
  val missing=(0..8).map { Turn(it*1000L,it*1000L+220,it) }
  val failed=SpeakerRefiner.refine(missing,emptyList(),9000,isolated())
  assertFalse(failed.accepted);assertEquals("hard_cap_without_valid_centroids",failed.diagnostics["reason"])
 }
 @Test fun exact500msInsertionIsNotSmoothedAndOverlapIsRetained() {
  for(length in listOf(499L,500L)) {
   val turns=listOf(Turn(0,2000,0),Turn(2000,2000+length,1),Turn(2000+length,5000,0),Turn(6000,8000,1))
   val result=SpeakerRefiner.refine(turns,measured(turns,9000,mapOf(0 to doubleArrayOf(1.0,0.0),1 to doubleArrayOf(0.0,1.0))),9000,isolated().copy(smooth=true))
   assertEquals(if(length==499L) 1 else 0,(result.diagnostics["smoothing"] as List<*>).size)
  }
 }
 @Test fun invalidConfigAndOversizedEigensystemReject() {
  for(config in listOf(SpeakerRefiner.Config(mergeThreshold=Double.NaN),SpeakerRefiner.Config(maxSpeakers=9),SpeakerRefiner.Config(smallMissingCentroidPolicy="guess"))) {
   try { SpeakerRefiner.refine(emptyList(),emptyList(),0,config);fail("invalid config") } catch(expected: IllegalArgumentException) { }
  }
  try { SpeakerRefiner.estimateSpeakers(List(257) { doubleArrayOf(1.0,0.0) });fail("bound") } catch(expected: IllegalArgumentException) { }
 }
 @Test fun longClockCleanWindowsAndTemporalMidpointsDoNotOverflow() {
  val end=Long.MAX_VALUE;val turns=listOf(Turn(end-10000,end-5000,7),Turn(end-4000,end-2800,2),Turn(end-200,end,9))
  val windows=SpeakerRefiner.cleanWindows(turns,end).filter { it.speaker!=9 }.map { it.copy(embedding=if(it.speaker==7) doubleArrayOf(1.0,0.0) else doubleArrayOf(0.0,1.0)) }
  val result=SpeakerRefiner.refine(turns,windows,end,isolated().copy(reassignSmall=true,minClusterFraction=0.0,smallMissingCentroidPolicy="temporal"))
  assertTrue(result.accepted);assertTrue(result.turns.all { it.startMs>=0 && it.endMs<=end })
 }
}
