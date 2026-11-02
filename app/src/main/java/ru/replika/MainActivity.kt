package ru.replika

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.*
import ru.replika.ml.BundledModelCoordinator
import ru.replika.ui.*
class MainActivity: ComponentActivity() {
 private val vm: AppViewModel by viewModels()
 private var openedVm: AppViewModel? = null
 private var pendingRecordingId: String? = null
 private var initialSelectionApplied = false
 override fun onCreate(savedInstanceState: Bundle?) {
  super.onCreate(savedInstanceState)
  enableEdgeToEdge(statusBarStyle=androidx.activity.SystemBarStyle.dark(android.graphics.Color.rgb(11,17,32)),navigationBarStyle=androidx.activity.SystemBarStyle.dark(android.graphics.Color.rgb(11,17,32)))
  pendingRecordingId = if(savedInstanceState?.containsKey("selectedRecordingId")==true) savedInstanceState.getString("selectedRecordingId") else intent.getStringExtra("recordingId")
  val preparation = (application as ReplikaApp).bundledModels
  setContent { ReplikaTheme {
   val state by preparation.state.collectAsState()
   if(state.phase == BundledModelCoordinator.Phase.READY) {
    val returningAfterPreparation = initialSelectionApplied
    val readyVm = vm
    openedVm = readyVm
    LaunchedEffect(Unit) { if(returningAfterPreparation) readyVm.refreshModels() }
    if(!initialSelectionApplied) {
     if(readyVm.selected.value == null) readyVm.selected.value = pendingRecordingId
     initialSelectionApplied = true
    }
    ReplikaRoot(readyVm)
   } else ModelPreparationScreen(state,onRetry={preparation.start()})
  } }
 }
 override fun onSaveInstanceState(outState: Bundle) {
  outState.putString("selectedRecordingId",if(openedVm!=null) openedVm!!.selected.value else pendingRecordingId)
  super.onSaveInstanceState(outState)
 }
 override fun onNewIntent(intent: android.content.Intent) {
  super.onNewIntent(intent);setIntent(intent)
  intent.getStringExtra("recordingId")?.let { pendingRecordingId=it;openedVm?.selected?.value=it }
 }
 override fun onStop() { openedVm?.let { if(it.isRecording.value && !it.paused.value) it.pauseRecording() };super.onStop() }
}
