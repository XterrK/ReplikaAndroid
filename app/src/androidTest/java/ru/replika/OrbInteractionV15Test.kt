package ru.replika

import androidx.compose.foundation.layout.width
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import ru.replika.ui.*

/** Gesture fixtures only: they do not claim microphone/phone performance or recorded audio. */
class OrbInteractionV15Test {
 @get:Rule val compose=createComposeRule()
 @Test fun idleStartsOnceAndPlayingDuringRecordingNeverCallsStartAgain() {
  val phase=mutableStateOf(RecordingPhase.IDLE)
  val realLevelFixture=MutableStateFlow(.35f)
  var starts=0
  val orb=OrbState()
  compose.setContent { ReplikaTheme { LiquidVoiceOrb(phase.value,realLevelFixture,{starts++},Modifier.width(300.dp),state=orb) } }
  compose.onNodeWithTag("liquid-voice-orb").performClick()
  compose.runOnIdle { assertEquals(1,starts);phase.value=RecordingPhase.RECORDING }
  val impacts=orb.dynamics.impacts
  compose.onNodeWithTag("liquid-voice-orb").performClick()
  compose.runOnIdle { assertTrue("A tap dents the jelly film",orb.dynamics.impacts>impacts) }
  compose.onNodeWithTag("liquid-voice-orb").performTouchInput {
   down(center);moveTo(center+Offset(70f,-35f));up()
  }
  compose.onNodeWithTag("liquid-voice-orb").performSemanticsAction(SemanticsActions.OnClick) { it.invoke() }
  compose.onNodeWithTag("liquid-voice-orb").assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription,"RECORDING"))
  compose.runOnIdle { assertEquals(1,starts);assertEquals(.35f,realLevelFixture.value,0f);phase.value=RecordingPhase.PAUSED }
  compose.onNodeWithTag("liquid-voice-orb").performClick()
  compose.runOnIdle { assertEquals(1,starts);assertEquals(RecordingPhase.PAUSED,phase.value) }
 }

 /** V1.7c: a real tap gesture near any side dents the film on that side (not an isotropic spread). */
 @Test fun aTapGestureOnEachSideDentsTheFilmOnThatSide() {
  val orb=OrbState()
  compose.setContent { ReplikaTheme { LiquidVoiceOrb(RecordingPhase.PAUSED,MutableStateFlow(0f),{},Modifier.width(300.dp),state=orb) } }
  val sides=listOf("right" to 0f,"bottom" to (Math.PI/2).toFloat(),"left" to Math.PI.toFloat(),"top" to (-Math.PI/2).toFloat())
  for((name,angle) in sides) {
   compose.runOnIdle { orb.dynamics.step(5f,0f,false);repeat(400) { orb.dynamics.step(1f/60,0f,false) } } // settle to a circle
   compose.onNodeWithTag("liquid-voice-orb").performTouchInput {
    val r=width*.3f
    val point=center+Offset(kotlin.math.cos(angle)*r,kotlin.math.sin(angle)*r)
    down(point);up()
   }
   compose.runOnIdle {
    // The frame loop is paused by the test clock policy; advance the shared physics directly.
    repeat(3) { orb.dynamics.step(1f/60,0f,false) }
    var deepest=0f;var lowest=Float.MAX_VALUE
    for(i in 0 until 360) { val a=Math.toRadians(i.toDouble()).toFloat();val u=orb.dynamics.shellAt(a);if(u<lowest) { lowest=u;deepest=a } }
    val error=kotlin.math.abs(kotlin.math.atan2(kotlin.math.sin(deepest-angle),kotlin.math.cos(deepest-angle)))
    assertTrue("Tap on the $name side must dent that side (error ${Math.toDegrees(error.toDouble())}°)",error<=Math.toRadians(15.0))
    assertTrue("The dent is visible",lowest< -.03f)
   }
  }
 }
}
