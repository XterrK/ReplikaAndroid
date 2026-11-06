package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.ZeroSpanVadRescue

class ZeroSpanVadRescueTest {
 @Test fun measuredWhisperWithAnIsolatedPeakGetsDetectorHeadroomWithoutChangingAsrGain() {
  val asrGain=1f
  val decision=ZeroSpanVadRescue.decide(0,.102049887f,asrGain,.0018098881701007485)
  assertTrue(decision.shouldRetry)
  assertEquals(9.309172f,decision.detectorGain,.0001f)
  assertEquals(.95f,decision.detectorGain*.102049887f,.00001f)
  assertEquals(1f,asrGain,0f)
 }

 @Test fun recognizedPrimaryAndSilenceNeverNeedAnotherFileScan() {
  assertFalse(ZeroSpanVadRescue.needsRms(1,.102049887f,1f))
  assertEquals("primary_nonempty",ZeroSpanVadRescue.decide(1,.102049887f,1f,.0018).reason)
  for(peak in listOf(0f,1e-8f,1e-6f)) {
   assertFalse(ZeroSpanVadRescue.needsRms(0,peak,1f))
   assertFalse(ZeroSpanVadRescue.decide(0,peak,1f,1e-8).shouldRetry)
  }
 }

 @Test fun gainCapAndHeadroomPreventUnboundedAmplification() {
  val capped=ZeroSpanVadRescue.decide(0,.001f,1f,.00001)
  assertTrue(capped.shouldRetry);assertEquals(20f,capped.detectorGain,0f)
  val loudPeak=ZeroSpanVadRescue.decide(0,.8f,1f,.01)
  assertTrue(loudPeak.shouldRetry);assertEquals(.95f,loudPeak.detectorGain*.8f,.00001f)
  assertFalse(ZeroSpanVadRescue.decide(0,.96f,1f,.01).shouldRetry)
 }

 @Test fun existingRecognitionGainIsNeverReducedOrBoostedPastItsCap() {
  val alreadyEnough=ZeroSpanVadRescue.decide(0,.1f,5f,.05)
  assertFalse(alreadyEnough.shouldRetry);assertEquals(5f,alreadyEnough.detectorGain,0f)
  assertFalse(ZeroSpanVadRescue.needsRms(0,.001f,20f))
  assertFalse(ZeroSpanVadRescue.decide(0,.001f,20f,.00001).shouldRetry)
 }

 @Test fun invalidStatisticsCannotCreateGainOrNonfiniteDiagnostics() {
  for(peak in listOf(Float.NaN,Float.POSITIVE_INFINITY,-.1f)) {
   assertFalse(ZeroSpanVadRescue.needsRms(0,peak,1f))
   assertFalse(ZeroSpanVadRescue.decide(0,peak,1f,.001).shouldRetry)
  }
  for(gain in listOf(Float.NaN,Float.POSITIVE_INFINITY,.5f,21f)) {
   val decision=ZeroSpanVadRescue.decide(0,.1f,gain,.001)
   assertFalse(ZeroSpanVadRescue.needsRms(0,.1f,gain))
   assertFalse(decision.shouldRetry);assertTrue(decision.detectorGain.isFinite())
  }
  for(rms in listOf(null,Double.NaN,Double.POSITIVE_INFINITY,-.1,0.0,.2))
   assertFalse(ZeroSpanVadRescue.decide(0,.1f,1f,rms).shouldRetry)
 }

 @Test fun negligibleGainDoesNotSpendAnotherDetectorPass() {
  assertFalse(ZeroSpanVadRescue.decide(0,.1f,1f,.02/1.005).shouldRetry)
 }

 @Test fun rmsIsWeightedBySamplesAndPreservesInput() {
  val values=floatArrayOf(.1f,-.1f,0f,0f,0f,0f,0f,0f)
  val before=values.map { it.toRawBits() }
  val rms=ZeroSpanVadRescue.RmsAccumulator()
  values.forEach(rms::add)
  assertEquals(8L,rms.samples);assertEquals(.05,rms.value()!!,.00000001)
  assertEquals(before,values.map { it.toRawBits() })
 }

 @Test fun emptyOrCorruptRmsHasNoNumericResult() {
  val empty=ZeroSpanVadRescue.RmsAccumulator();assertNull(empty.value())
  val corrupt=ZeroSpanVadRescue.RmsAccumulator();corrupt.add(.01f);corrupt.add(Float.NaN)
  assertNull(corrupt.value())
 }
}
