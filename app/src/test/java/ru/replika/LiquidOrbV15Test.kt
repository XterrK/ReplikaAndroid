package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.ui.*
import kotlin.math.*

class LiquidOrbV15Test {
 @Test fun quietRealSignalHasUsefulDisplayRangeWithoutAnimatingSilence() {
  val envelope=VoiceEnvelope()
  repeat(100) { envelope.sample(.0002f) }
  assertTrue(envelope.level<.002f)
  repeat(12) { envelope.sample(.008f) }
  val quiet=envelope.level
  assertTrue("Quiet speech peak should remain visible",quiet>.10f)
  repeat(12) { envelope.sample(.6f) }
  assertTrue(envelope.level>quiet+.35f)
  repeat(100) { envelope.sample(0f) }
  assertTrue(envelope.level<.002f)
 }
 @Test fun sustainedQuietInputIsNotLearnedAwayAsBackgroundNoise() {
  val envelope=VoiceEnvelope()
  repeat(100) { envelope.sample(.0002f) }
  repeat(12) { envelope.sample(.008f) }
  val onset=envelope.level
  repeat(1200) { envelope.sample(.008f) }
  assertTrue("A minute of genuine quiet input must remain visible",envelope.level>.10f)
  assertTrue(envelope.level>=onset*.85f)
  repeat(100) { envelope.sample(0f) }
  assertTrue(envelope.level<.002f)
 }
 @Test fun draggingStretchesTheContourAndReleaseSettlesWithoutChangingVoiceEnergy() {
  val dynamics=OrbDynamics()
  repeat(100) { dynamics.step(1f/60,.3f,true) }
  val previousVoice=dynamics.voiceEnergy
  dynamics.press(.9f,.05f)
  repeat(35) { dynamics.step(1f/60,.3f,true) }
  assertTrue(dynamics.radiusAt(dynamics.touchAngle)>dynamics.radiusAt(dynamics.touchAngle+PI.toFloat()/2)*1.35f)
  assertEquals(previousVoice,dynamics.voiceEnergy,.00001f)
  assertTrue(dynamics.centerX>.05f)
  dynamics.release()
  repeat(300) { dynamics.step(1f/60,.3f,true) }
  assertTrue(abs(dynamics.stretch)<.001f)
  assertTrue(abs(dynamics.centerX)<.001f)
  assertFalse(dynamics.hasInteractionMotion)
 }
 @Test fun tapHasAnInertialReboundEvenWhenTheFingerIsReleasedImmediately() {
  val dynamics=OrbDynamics();dynamics.poke()
  repeat(6) { dynamics.step(1f/60,0f,true) }
  assertTrue("A short tap must make a visible non-circular shape",abs(dynamics.stretch)>.08f)
  assertFalse(dynamics.isTouching)
  repeat(240) { dynamics.step(1f/60,0f,true) }
  assertTrue(abs(dynamics.stretch)<.001f)
 }
 @Test fun contourKeepsItsAreaWhileVoiceAndTouchChangeTheBoundary() {
  val dynamics=OrbDynamics();val contour=OrbContourGeometry()
  for(i in 0..500) {
   if(i%90==0) dynamics.press(sin(i.toFloat()),cos(i.toFloat()))
   if(i%90==35) dynamics.release()
   dynamics.step(1f/60,if(i%120<60) .9f else .04f,true)
   contour.update(dynamics)
   val area=(0 until contour.count).sumOf { (contour.x[it]*contour.x[it]+contour.y[it]*contour.y[it]).toDouble() }/contour.count
   assertEquals(1.0,area,.0001)
   assertTrue(contour.maximumRadius in .9f..1.8f)
   assertTrue(contour.x.all { it.isFinite() });assertTrue(contour.y.all { it.isFinite() })
  }
 }
 @Test fun repeatedStrongTouchesAndDroppedFramesRemainBounded() {
  val dynamics=OrbDynamics()
  repeat(2500) { i ->
   if(i%9==0) dynamics.press(1f,-1f)
   if(i%9==3) dynamics.release()
   dynamics.step(if(i%3==0) .9f else .008f,if(i%5==0) 1f else 0f,true)
   assertTrue(dynamics.expansion in -.025f.. .235f)
   assertTrue(dynamics.stretch in -.16f.. .43f)
   for(a in 0..12) assertTrue(dynamics.radiusAt(a*.5f).isFinite() && dynamics.radiusAt(a*.5f)>.4f)
  }
 }
 @Test fun reducedMotionRemovesToyAndVoiceWobbleWhileRetainingRealLevel() {
  val dynamics=OrbDynamics();dynamics.press(.8f,.5f)
  repeat(10) { dynamics.step(1f/60,.6f,true,true) }
  assertEquals(.6f,dynamics.voiceEnergy,0f)
  assertTrue(dynamics.modes.all { it==0f })
  assertEquals(0f,dynamics.stretch,0f);assertEquals(0f,dynamics.centerX,0f)
  assertEquals(dynamics.radiusAt(0f),dynamics.radiusAt(PI.toFloat()),.00001f)
 }
}
