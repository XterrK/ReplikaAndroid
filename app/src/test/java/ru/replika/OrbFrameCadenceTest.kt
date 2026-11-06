package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.ui.OrbDynamics
import ru.replika.ui.OrbFrameCadence
import kotlin.math.abs

class OrbFrameCadenceTest {
 @Test fun quietRecordingIsUniformThirtyOnSixtyAndOneTwentyHz() {
  for(hz in listOf(60,120)) {
   val policy=OrbFrameCadence();val draws=mutableListOf<Long>()
   repeat(hz*10) { i ->
    val now=i*1_000_000_000L/hz
    if(policy.shouldDraw(now,0f,false,false)) draws+=now
   }
   assertEquals("Quiet draws on ${hz}Hz",300,draws.size)
   assertTrue(draws.zipWithNext().all { (a,b) -> b-a in 32_000_000L..35_000_000L })
  }
 }
 @Test fun genuineQuietSpeechKeepsTheExistingSixtyFrameCap() {
  for(hz in listOf(60,120)) {
   val policy=OrbFrameCadence();var frames=0
   repeat(hz*10) { i -> if(policy.shouldDraw(i*1_000_000_000L/hz,.10f,false,false)) frames++ }
   assertEquals("Speech draws on ${hz}Hz",600,frames)
  }
 }
 @Test fun speechOnsetIsObservedOnSkippedVsyncAndWakesWithinFastFrameBudget() {
  val policy=OrbFrameCadence()
  assertTrue(policy.shouldDraw(0L,0f,false,false))
  assertFalse(policy.shouldDraw(8_333_333L,.10f,false,false)) // The existing fast cap still applies.
  assertTrue(policy.fastFrames)
  assertTrue(policy.shouldDraw(16_666_666L,.10f,false,false)) // Quiet cadence would still skip this.
 }
 @Test fun releaseHasAFastTailButQuietEventuallyReturnsToThirty() {
  val policy=OrbFrameCadence()
  policy.shouldDraw(0L,.10f,false,false)
  policy.shouldDraw(700_000_000L,0f,false,false);assertTrue(policy.fastFrames)
  policy.shouldDraw(900_000_000L,0f,false,false);assertFalse(policy.fastFrames)
  policy.shouldDraw(1_000_000_000L,0f,true,false);assertTrue(policy.fastFrames)
  assertEquals(0L,policy.restMillis(active=false,reducedMotion=false,powerLimitMillis=0))
  policy.shouldDraw(1_700_000_000L,0f,false,false);assertTrue(policy.fastFrames)
  policy.shouldDraw(1_900_000_000L,0f,false,false);assertFalse(policy.fastFrames)
  assertEquals(70L,policy.restMillis(active=false,reducedMotion=false,powerLimitMillis=0))
 }
 @Test fun transitionsAndThermalReducedMotionCapsRemainAuthoritative() {
  val policy=OrbFrameCadence()
  policy.shouldDraw(0L,0f,false,true);assertTrue(policy.fastFrames)
  assertTrue(policy.shouldDraw(16_666_667L,0f,false,true))
  for(active in listOf(false,true)) {
   assertEquals(80L,policy.restMillis(active,false,80))
   assertEquals(120L,policy.restMillis(active,true,80))
   assertEquals(250L,policy.restMillis(active,true,250))
  }
 }
 @Test fun droppedFramesDoNotCauseCatchUpDrawBurstsAndInvalidInputDoesNotWake() {
  val policy=OrbFrameCadence()
  assertTrue(policy.shouldDraw(0L,Float.NaN,false,false));assertFalse(policy.fastFrames)
  assertTrue(policy.shouldDraw(5_000_000_000L,Float.POSITIVE_INFINITY,false,false))
  assertFalse(policy.shouldDraw(5_001_000_000L,0f,false,false))
  assertFalse(policy.shouldDraw(5_010_000_000L,0f,false,false))
  assertTrue(policy.shouldDraw(5_033_333_333L,0f,false,false))
 }
 @Test fun quietDrawCadencePreservesTheSameElapsedSpringMotion() {
  val sixty=OrbDynamics();val thirty=OrbDynamics();val policy=OrbFrameCadence();var previous=0L
  for(i in 0..600) {
   val now=i*1_000_000_000L/60
   sixty.step(if(i==0) 1f/60 else 1f/60,0f,true)
   if(policy.shouldDraw(now,0f,false,false)) {
    thirty.step(if(now==0L) 1f/60 else (now-previous)/1_000_000_000f,0f,true);previous=now
   }
  }
  assertEquals(sixty.expansion,thirty.expansion,.0001f)
  assertTrue(abs(sixty.time-thirty.time)<.001f)
  for(i in 0..24) assertEquals(sixty.radiusAt(i*.25f),thirty.radiusAt(i*.25f),.0001f)
 }
}
