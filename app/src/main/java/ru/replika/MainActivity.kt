package ru.replika

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import ru.replika.ui.*
class MainActivity: ComponentActivity() {
 private val vm: AppViewModel by viewModels()
 override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState);enableEdgeToEdge();setContent { ReplikaTheme { ReplikaRoot(vm) } } }
 override fun onStop() { if(vm.isRecording.value && !vm.paused.value) vm.pauseRecording();super.onStop() }
}
