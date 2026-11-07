package ru.replika

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.*
import org.junit.Assert.*
import ru.replika.data.ThemeMode
import ru.replika.ui.*
import kotlin.math.*

/**
 * Real-time visual fixture for screen recordings of the V1.7d particles. The envelope is scripted
 * (silence → room noise → speech → silence); it is never presented as microphone evidence.
 * Run alone with `adb shell screenrecord` to capture the effect at normal speed.
 */
class ParticleShowcaseV17Test {
 @get:Rule val compose=createComposeRule()
 @Test fun scriptedVoiceShowsGlowingCometsOnlyAboveTheGate() {
  val animator=android.provider.Settings.Global.getFloat(InstrumentationRegistry.getInstrumentation().targetContext.contentResolver,android.provider.Settings.Global.ANIMATOR_DURATION_SCALE,1f)
  Assume.assumeTrue("Particles are intentionally off under reduced motion",animator!=0f)
  compose.mainClock.autoAdvance=false
  val input=MutableStateFlow(0f)
  val orb=OrbState();val particles=VoiceParticleSystem()
  compose.setContent {
   ReplikaTheme(ThemeMode.DARK) {
    Surface(Modifier.fillMaxSize(),color=Ink) {
     Box(Modifier.fillMaxSize()) {
      VoiceParticleField(orb,input,RecordingPhase.RECORDING,Modifier.matchParentSize(),system=particles)
      Column(Modifier.align(Alignment.Center).fillMaxWidth(),horizontalAlignment=Alignment.CenterHorizontally) {
       LiquidVoiceOrb(RecordingPhase.RECORDING,input,{},Modifier.fillMaxWidth().sizeIn(maxWidth=360.dp,maxHeight=360.dp),state=orb)
       Text("Витрина · заданная огибающая, не микрофон",style=MaterialTheme.typography.bodySmall,color=Muted)
      }
     }
    }
   }
  }
  fun play(seconds: Float,level: (Float)->Float) {
   val frames=(seconds*60).toInt()
   for(f in 0 until frames) {
    val t=f/60f
    compose.runOnUiThread { input.value=level(t).coerceIn(0f,1f) }
    compose.mainClock.advanceTimeBy(16)
    Thread.sleep(14) // Real-time pacing so a screen recording shows normal speed.
   }
  }
  play(1.5f) { 0f }
  play(2.5f) { .1f+.03f*sin(it*9f) }
  assertEquals("Silence and room noise launch nothing",0,particles.spawned)
  // Speech: syllables at ~4 Hz, getting louder, with a short breath in the middle.
  play(6f) { t -> if(t in 2.6f..3.1f) .05f else (.35f+.5f*(t/6f))*(.65f+.35f*abs(sin(t*PI.toFloat()*4f))) }
  assertTrue("Speech launches comets",particles.spawned>=15)
  assertTrue("…which are absorbed by the film",particles.hits>0)
  val spoken=particles.spawned
  play(3f) { 0f }
  assertTrue("After the voice the stream stops within the release time",particles.spawned-spoken<=6)
 }
}
