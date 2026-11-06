package ru.replika

import android.Manifest
import android.content.pm.PackageManager
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.*
import org.junit.Assert.*
import ru.replika.ui.*

/** Run explicitly after emulator-only pm revoke RECORD_AUDIO, restore permission afterward. */
class RecordingPermissionV14Test {
 @get:Rule val compose=createAndroidComposeRule<MainActivity>()
 @Test fun deniedMicrophoneProducesNoMeterOrRecorderSession() {
  val context=InstrumentationRegistry.getInstrumentation().targetContext
  assertEquals("Revoke RECORD_AUDIO before this test",PackageManager.PERMISSION_DENIED,context.checkSelfPermission(Manifest.permission.RECORD_AUDIO))
  lateinit var vm: AppViewModel
  compose.activityRule.scenario.onActivity {
   vm=ViewModelProvider(it)[AppViewModel::class.java];vm.startRecording()
  }
  assertEquals(RecordingPhase.PERMISSION_REQUIRED,vm.recordingPhase.value)
  assertEquals(0f,vm.voiceLevel.value,0f);assertFalse(vm.isRecording.value);assertTrue(vm.levels.value.isEmpty())
  compose.activityRule.scenario.onActivity { vm.requireMicrophonePermission() }
  compose.onNodeWithText("Нужен доступ к микрофону").assertIsDisplayed()
  compose.onNodeWithText("Разрешите микрофон, чтобы начать").assertIsDisplayed()
  compose.onNodeWithTag("liquid-voice-orb").assertHasClickAction()
  compose.onNodeWithTag("microphone-vu").assertExists()
 }
}
