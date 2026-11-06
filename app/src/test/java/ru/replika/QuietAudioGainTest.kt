package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.QuietAudioGain

class QuietAudioGainTest {
 @Test fun ordinaryAudioIsBitExactIncludingPauses() {
  val samples=floatArrayOf(-.22f,-.0007f,-0f,0f,.0004f,.15f)
  val before=samples.map { it.toRawBits() }
  QuietAudioGain.apply(samples,QuietAudioGain.forPeak(.22f))
  assertEquals(before,samples.map { it.toRawBits() })
 }

 @Test fun veryQuietSpeechRetainsItsShapeAndNeverClips() {
  val source=floatArrayOf(-.004f,-.001f,0f,.002f,.003f)
  val temporary=source.copyOf()
  val gain=QuietAudioGain.forPeak(.004f)
  QuietAudioGain.apply(temporary,gain)
  assertArrayEquals(floatArrayOf(-.004f,-.001f,0f,.002f,.003f),source,0f)
  assertEquals(20f,gain,0f)
  assertArrayEquals(floatArrayOf(-.08f,-.02f,0f,.04f,.06f),temporary,.000001f)
  assertTrue(temporary.all { kotlin.math.abs(it)<=QuietAudioGain.TARGET_PEAK })
 }

 @Test fun silenceInvalidPeakAndThresholdDoNotCreateGain() {
  for(peak in listOf(0f,1e-7f,Float.NaN,Float.POSITIVE_INFINITY,-1f,.01f,1f))
   assertEquals(1f,QuietAudioGain.forPeak(peak),0f)
 }
}
