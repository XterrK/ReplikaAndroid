package ru.replika.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.sin
import kotlin.random.Random

class NoiseGateTest {
 private fun white(n: Int,amplitude: Double,seed: Int=1): FloatArray {
  val r=Random(seed);return FloatArray(n) { (r.nextDouble(-1.0,1.0)*amplitude).toFloat() }
 }

 @Test fun whiteNoiseIsFlatAndAToneIsNot() {
  val noise=white(NoiseGate.FRAME,0.1)
  val tone=FloatArray(NoiseGate.FRAME) { (0.3*sin(2*PI*440*it/16000)).toFloat() }
  assertTrue(NoiseGate.flatness(noise)>0.4)
  assertTrue(NoiseGate.flatness(tone)<0.1)
 }

 @Test fun snrComparesLoudestQuarterWithQuietestTenth() {
  val energies=DoubleArray(100) { if(it<10) 1e-6 else 1e-2 }
  val (snr,quiet)=NoiseGate.snr(energies)
  assertEquals(40.0,snr,0.01)
  assertEquals(10,quiet.size)
 }

 @Test fun ruleFiresOnlyForLoudFlatBackground() {
  assertTrue(NoiseGate.decide(13.0,0.57).apply)    // white noise 10 dB on the stand
  assertFalse(NoiseGate.decide(33.0,0.14).apply)   // babble: voices are not flat
  assertFalse(NoiseGate.decide(66.0,1.0).apply)    // clean: digital silence between phrases
  assertFalse(NoiseGate.decide(15.0,0.2).apply)    // loud but tonal/voice-like background
  assertFalse(NoiseGate.decide(13.0,0.99).apply)   // dither/constant, not a real noise floor
 }

 @Test fun speechOverWhiteNoiseIsDetected() {
  // 6 s: speech-like bursts (tone) every other 0.5 s over white noise ~13 dB below.
  val samples=FloatArray(6*16000) { i -> val burst=(i/8000)%2==0; (if(burst) 0.3*sin(2*PI*300*i/16000) else 0.0).toFloat() }
  val noise=white(samples.size,0.05)
  for(i in samples.indices) samples[i]+=noise[i]
  val frames=samples.size/NoiseGate.FRAME
  val energies=DoubleArray(frames) { NoiseGate.energy(samples,it*NoiseGate.FRAME) }
  val (snr,quiet)=NoiseGate.snr(energies)
  val flat=NoiseGate.median(quiet.map { NoiseGate.flatness(samples,it*NoiseGate.FRAME) })
  assertTrue("snr $snr",snr<20)
  assertTrue("flatness $flat",NoiseGate.decide(snr,flat).apply)
 }
}
