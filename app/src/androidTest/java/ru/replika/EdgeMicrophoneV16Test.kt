package ru.replika

import android.graphics.Bitmap
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.semantics.*
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.*
import org.junit.Assert.*
import ru.replika.data.ThemeMode
import ru.replika.ui.*
import java.io.File

/**
 * Deterministic visual signal fixture. Never labelled as physical or emulator microphone evidence.
 * V1.7: the right-edge meter became particles rising from the microphone edge into the bubble.
 * The same guarantees are checked: the real level drives it, silence and pause add nothing,
 * and the overlay never moves the bubble centre.
 */
class EdgeMicrophoneV16Test {
 @get:Rule val compose=createComposeRule()
 @Test fun injectedEnvelopeLaunchesParticlesThatHitTheBubbleAndSilenceClearsWithoutChangingCenter() {
  val theme=mutableStateOf(ThemeMode.LIGHT)
  val phase=mutableStateOf(RecordingPhase.RECORDING)
  val input=MutableStateFlow(.8f)
  val animator=android.provider.Settings.Global.getFloat(InstrumentationRegistry.getInstrumentation().targetContext.contentResolver,android.provider.Settings.Global.ANIMATOR_DURATION_SCALE,1f)
  Assume.assumeTrue("Particles are intentionally off under reduced motion (animator scale 0)",animator!=0f)
  val orb=OrbState()
  val particles=VoiceParticleSystem()
  // Manual clock before composition: with autoAdvance the test policy cancels infinite frame loops.
  compose.mainClock.autoAdvance=false
  compose.setContent {
   ReplikaTheme(theme.value) {
    Surface(Modifier.fillMaxSize(),color=Ink) {
     Box(Modifier.fillMaxSize()) {
      VoiceParticleField(orb,input,phase.value,Modifier.matchParentSize(),system=particles)
      Column(Modifier.align(Alignment.Center).fillMaxWidth(),horizontalAlignment=Alignment.CenterHorizontally) {
       LiquidVoiceOrb(phase.value,input,{},Modifier.fillMaxWidth().sizeIn(maxWidth=360.dp,maxHeight=360.dp),state=orb)
       Text("00:24",style=MaterialTheme.typography.displaySmall,color=Blue)
       Text("Визуальный тест · заданный уровень 80%",style=MaterialTheme.typography.bodySmall,color=Muted)
      }
     }
    }
   }
  }
  for(t in listOf(ThemeMode.LIGHT,ThemeMode.DARK)) {
   compose.runOnUiThread { theme.value=t }
   val spawnedBefore=particles.spawned;val hitsBefore=particles.hits;val impactsBefore=orb.dynamics.impacts
   repeat(150) { compose.mainClock.advanceTimeBy(16) } // ~2.4 s of frames for the controlled envelope.
   val field=compose.onNodeWithTag("voice-particles")
   field.assert(SemanticsMatcher.expectValue(SemanticsProperties.ProgressBarRangeInfo,ProgressBarRangeInfo(.8f,0f..1f)))
   field.assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription,"Звуковой сигнал"))
   assertTrue("A loud envelope must launch particles",particles.spawned-spawnedBefore>=20)
   assertTrue("Particles must reach the bubble",particles.hits>hitsBefore)
   assertTrue("Each hit must dent the jelly membrane",orb.dynamics.impacts>impactsBefore)
   val orbBounds=compose.onNodeWithTag("liquid-voice-orb").getUnclippedBoundsInRoot()
   val area=field.getUnclippedBoundsInRoot()
   assertTrue("Overlay must not shift the bubble centre",kotlin.math.abs((orbBounds.left.value+orbBounds.right.value)/2-(area.left.value+area.right.value)/2)<1.1f)
   val directory=File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,"ui-v1.7").apply { mkdirs() }
   compose.onRoot().captureToImage().asAndroidBitmap().let { bitmap ->
    File(directory,"injected-particles-${t.name}.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }
   }
  }
  // Silence: no new particles; the meter semantics say so.
  compose.runOnUiThread { input.value=0f }
  repeat(10) { compose.mainClock.advanceTimeBy(16) }
  compose.onNodeWithTag("voice-particles").assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription,"Тишина"))
  // V1.7d: the gate releases smoothly (≈0.6 s), then silence launches nothing at all.
  repeat(60) { compose.mainClock.advanceTimeBy(16) }
  assertFalse("The voice gate closes in silence",particles.gate.open)
  val quiet=particles.spawned
  repeat(120) { compose.mainClock.advanceTimeBy(16) }
  assertEquals("Silence must not fabricate particles",quiet,particles.spawned)
  // Room noise under the gate: still nothing.
  compose.runOnUiThread { input.value=.12f }
  repeat(180) { compose.mainClock.advanceTimeBy(16) }
  assertEquals("Background noise below the gate must not launch particles",quiet,particles.spawned)
  // Pause: level reads zero and nothing new is launched even for a loud fixture value.
  compose.runOnUiThread { phase.value=RecordingPhase.PAUSED;input.value=.8f }
  repeat(10) { compose.mainClock.advanceTimeBy(16) }
  compose.onNodeWithTag("voice-particles").assert(SemanticsMatcher.expectValue(SemanticsProperties.ProgressBarRangeInfo,ProgressBarRangeInfo(0f,0f..1f)))
  val paused=particles.spawned
  repeat(120) { compose.mainClock.advanceTimeBy(16) }
  assertEquals("Pause must stop particles",paused,particles.spawned)
  // Not recording at all (home, idle): nothing, however loud the fixture value is.
  compose.runOnUiThread { phase.value=RecordingPhase.IDLE;input.value=1f }
  repeat(180) { compose.mainClock.advanceTimeBy(16) }
  assertEquals("Without a recording there are no particles",paused,particles.spawned)
  compose.onNodeWithTag("voice-particles").assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription,"Микрофон не записывает"))
 }
}
