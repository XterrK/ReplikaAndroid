package ru.replika

import android.graphics.Bitmap
import android.os.Build
import androidx.compose.foundation.layout.width
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.*
import ru.replika.data.ThemeMode
import ru.replika.ui.*
import java.io.File

/** Renderer fixtures only. Injected envelopes are never labelled microphone evidence. */
class OrbRendererV14Test {
 @get:Rule val compose=createComposeRule()
 @Test fun agslCompilesAndAcceptsUniforms() {
  Assume.assumeTrue(Build.VERSION.SDK_INT>=33)
  if(Build.VERSION.SDK_INT>=33) compose.runOnUiThread {
   // V1.7 soap-bubble film: compiles, accepts the contour harmonics, and survives a dented contour.
   val dynamics=OrbDynamics();val contour=OrbContourGeometry()
   AgslBubbleSurface().brush(Offset(150f,150f),100f,dynamics,true)
   dynamics.impact(1.2f,.9f);repeat(8) { dynamics.step(1f/60,.5f,true) };contour.update(dynamics)
   AgslBubbleSurface().brush(Offset(150f,150f),100f,dynamics,false,contour)
  }
 }
 @Test fun canvasFallbackAndAgslRenderBothThemesWithoutRuntimeErrors() {
  val theme=androidx.compose.runtime.mutableStateOf(ThemeMode.LIGHT)
  val fallback=androidx.compose.runtime.mutableStateOf(false)
  val phase=androidx.compose.runtime.mutableStateOf(RecordingPhase.IDLE)
  val fixtureLevel=MutableStateFlow(0f)
  compose.setContent { ReplikaTheme(theme.value) { LiquidVoiceOrb(phase.value,fixtureLevel,{},Modifier.width(300.dp),forceCanvas=fallback.value) } }
  for(t in listOf(ThemeMode.LIGHT,ThemeMode.DARK)) for(canvas in listOf(false,true)) {
   compose.runOnIdle { theme.value=t;fallback.value=canvas;phase.value=RecordingPhase.IDLE }
   compose.onNodeWithTag("liquid-voice-orb").assertExists()
   val dir=File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,"human-review-v1.4").apply { mkdirs() }
   compose.onNodeWithTag("liquid-voice-orb").captureToImage().asAndroidBitmap().let { bitmap ->
    File(dir,"renderer-fixture-${t.name}-${if(canvas) "canvas" else "agsl"}.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }
   }
   compose.runOnIdle { phase.value=RecordingPhase.RECORDING;fixtureLevel.value=.8f }
   compose.onNodeWithTag("liquid-voice-orb").assert(SemanticsMatcher.expectValue(androidx.compose.ui.semantics.SemanticsProperties.StateDescription,"RECORDING"))
   compose.runOnIdle { phase.value=RecordingPhase.PAUSED;fixtureLevel.value=0f }
  }
 }
}
