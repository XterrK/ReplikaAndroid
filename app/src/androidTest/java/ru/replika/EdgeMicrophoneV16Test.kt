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

/** Deterministic visual signal fixture. Never labelled as physical or emulator microphone evidence. */
class EdgeMicrophoneV16Test {
 @get:Rule val compose=createComposeRule()
 @Test fun injectedEnvelopeRendersAtEdgeAndSilenceClearsWithoutChangingCenter() {
  val theme=mutableStateOf(ThemeMode.LIGHT)
  val phase=mutableStateOf(RecordingPhase.RECORDING)
  val input=MutableStateFlow(.8f)
  compose.setContent {
   ReplikaTheme(theme.value) {
    Surface(Modifier.fillMaxSize(),color=Ink) {
     Box(Modifier.fillMaxSize()) {
      LiveMicrophoneMeter(input,phase.value,Modifier.align(Alignment.CenterEnd).width(64.dp).fillMaxHeight(.88f))
      Column(Modifier.align(Alignment.Center).fillMaxWidth(),horizontalAlignment=Alignment.CenterHorizontally) {
       Text("Идёт запись",style=MaterialTheme.typography.titleMedium,color=Mint)
       LiquidVoiceOrb(phase.value,input,{},Modifier.fillMaxWidth().sizeIn(maxWidth=360.dp,maxHeight=360.dp))
       Text("00:24",style=MaterialTheme.typography.headlineLarge,color=Blue)
       Text("Визуальный тест · заданный уровень 80%",style=MaterialTheme.typography.bodySmall,color=Muted)
      }
     }
    }
   }
  }
  compose.mainClock.autoAdvance=false
  for(t in listOf(ThemeMode.LIGHT,ThemeMode.DARK)) {
   compose.runOnUiThread { theme.value=t }
   compose.mainClock.advanceTimeBy(2000)
   Thread.sleep(1500) // Fill the edge field's wall-clock history with the controlled envelope.
   compose.mainClock.advanceTimeBy(100)
   val meter=compose.onNodeWithTag("microphone-vu")
   meter.assert(SemanticsMatcher.expectValue(SemanticsProperties.ProgressBarRangeInfo,ProgressBarRangeInfo(.8f,0f..1f)))
   val orb=compose.onNodeWithTag("liquid-voice-orb").getUnclippedBoundsInRoot()
   val edge=meter.getUnclippedBoundsInRoot()
   assertTrue(kotlin.math.abs((orb.left.value+orb.right.value)/2-edge.right.value/2)<1.1f)
   val directory=File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,"ui-v1.6").apply { mkdirs() }
   compose.onRoot().captureToImage().asAndroidBitmap().let { bitmap ->
    File(directory,"injected-envelope-${t.name}.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }
   }
  }
  compose.runOnUiThread { input.value=0f }
  compose.mainClock.advanceTimeBy(100)
  compose.onNodeWithTag("microphone-vu").assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription,"Тишина"))
  compose.runOnUiThread { phase.value=RecordingPhase.PAUSED;input.value=.8f }
  compose.mainClock.advanceTimeBy(100)
  compose.onNodeWithTag("microphone-vu").assert(SemanticsMatcher.expectValue(SemanticsProperties.ProgressBarRangeInfo,ProgressBarRangeInfo(0f,0f..1f)))
 }
}
