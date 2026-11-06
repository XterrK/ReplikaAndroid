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
  compose.setContent { ReplikaTheme { LiquidVoiceOrb(phase.value,realLevelFixture,{starts++},Modifier.width(300.dp)) } }
  compose.onNodeWithTag("liquid-voice-orb").performClick()
  compose.runOnIdle { assertEquals(1,starts);phase.value=RecordingPhase.RECORDING }
  compose.onNodeWithTag("liquid-voice-orb").performClick()
  compose.onNodeWithTag("liquid-voice-orb").performTouchInput {
   down(center);moveTo(center+Offset(70f,-35f));up()
  }
  compose.onNodeWithTag("liquid-voice-orb").performSemanticsAction(SemanticsActions.OnClick) { it.invoke() }
  compose.onNodeWithTag("liquid-voice-orb").assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription,"RECORDING"))
  compose.runOnIdle { assertEquals(1,starts);assertEquals(.35f,realLevelFixture.value,0f);phase.value=RecordingPhase.PAUSED }
  compose.onNodeWithTag("liquid-voice-orb").performClick()
  compose.runOnIdle { assertEquals(1,starts);assertEquals(RecordingPhase.PAUSED,phase.value) }
 }
}
