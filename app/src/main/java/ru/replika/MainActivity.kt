package ru.replika

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import ru.replika.ui.*
class MainActivity: ComponentActivity() {
 private val vm: AppViewModel by viewModels()
 override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState);enableEdgeToEdge(statusBarStyle=androidx.activity.SystemBarStyle.dark(android.graphics.Color.rgb(11,17,32)),navigationBarStyle=androidx.activity.SystemBarStyle.dark(android.graphics.Color.rgb(11,17,32)));if(savedInstanceState==null) intent.getStringExtra("recordingId")?.let { vm.selected.value=it };setContent { ReplikaTheme { ReplikaRoot(vm) } } }
 override fun onNewIntent(intent: android.content.Intent) { super.onNewIntent(intent);setIntent(intent);intent.getStringExtra("recordingId")?.let { vm.selected.value=it } }
 override fun onStop() { if(vm.isRecording.value && !vm.paused.value) vm.pauseRecording();super.onStop() }
}
