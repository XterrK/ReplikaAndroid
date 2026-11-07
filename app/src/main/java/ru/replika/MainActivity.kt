package ru.replika

import android.os.Bundle
import android.os.Build
import android.graphics.drawable.ColorDrawable
import androidx.activity.SystemBarStyle
import android.view.WindowInsetsController
import androidx.core.view.WindowCompat
import androidx.core.view.doOnAttach
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
 private var systemBarsDark: Boolean? = null
 private var systemBarsUpdatePosted = false
 private val systemBarsUpdate = Runnable {
  systemBarsUpdatePosted=false
  if(!isFinishing && !isDestroyed) applySystemBarAppearance()
 }
 /** Apply the app override after attach/focus, not only before the window's first layout. */
 private fun updateSystemBarTheme(dark: Boolean) {
  if(systemBarsDark==dark) return
  systemBarsDark=dark
  val color=if(dark) android.graphics.Color.rgb(14,15,19) else android.graphics.Color.rgb(246,247,251)
  // Activity 1.10.1 uses Api30/Api29 color setters (no ProtectionLayout wrappers).
  // Transparent enforced bars also need the underlying window background to follow the override.
  window.setBackgroundDrawable(ColorDrawable(color))
  val style=if(dark) SystemBarStyle.dark(color) else SystemBarStyle.light(color,color)
  enableEdgeToEdge(statusBarStyle=style,navigationBarStyle=style)
  applySystemBarAppearance()
  scheduleSystemBarAppearance()
 }
 private fun scheduleSystemBarAppearance() {
  if(systemBarsUpdatePosted) return
  systemBarsUpdatePosted=true
  window.decorView.post(systemBarsUpdate)
 }
 @Suppress("DEPRECATION")
 private fun applySystemBarAppearance() {
  val dark=systemBarsDark?:return
  val color=if(dark) android.graphics.Color.rgb(14,15,19) else android.graphics.Color.rgb(246,247,251)
  window.statusBarColor=color;window.navigationBarColor=color
  if(Build.VERSION.SDK_INT>=29) {
   window.isStatusBarContrastEnforced=false
   window.isNavigationBarContrastEnforced=false
  }
  if(Build.VERSION.SDK_INT>=35) {
   // Core 1.16 writes both deprecated systemUiVisibility and native appearance on API 35.
   // Update the two native flags together, without a competing legacy appearance write.
   val mask=WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
   window.insetsController?.setSystemBarsAppearance(if(dark) 0 else mask,mask)
  } else WindowCompat.getInsetsController(window,window.decorView).apply {
   isAppearanceLightStatusBars=!dark;isAppearanceLightNavigationBars=!dark
  }
 }
 override fun onCreate(savedInstanceState: Bundle?) {
  super.onCreate(savedInstanceState)
  enableEdgeToEdge()
  window.decorView.doOnAttach { scheduleSystemBarAppearance() }
  pendingRecordingId = if(savedInstanceState?.containsKey("selectedRecordingId")==true) savedInstanceState.getString("selectedRecordingId") else intent.getStringExtra("recordingId")
  val preparation = (application as ReplikaApp).bundledModels
  setContent {
   val appearance by vm.themeMode.collectAsState()
   ReplikaTheme(appearance) {
    val dark=LocalReplikaDark.current
    SideEffect { updateSystemBarTheme(dark) }
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
 override fun onWindowFocusChanged(hasFocus: Boolean) {
  super.onWindowFocusChanged(hasFocus)
  if(hasFocus) { applySystemBarAppearance();scheduleSystemBarAppearance() }
 }
 override fun onDestroy() {
  window.decorView.removeCallbacks(systemBarsUpdate)
  super.onDestroy()
 }
 override fun onSaveInstanceState(outState: Bundle) {
  outState.putString("selectedRecordingId",if(openedVm!=null) openedVm!!.selected.value else pendingRecordingId)
  super.onSaveInstanceState(outState)
 }
 override fun onNewIntent(intent: android.content.Intent) {
  super.onNewIntent(intent);setIntent(intent)
  intent.getStringExtra("recordingId")?.let { pendingRecordingId=it;openedVm?.selected?.value=it }
 }
 override fun onStop() { openedVm?.onRecordingBackgrounded();super.onStop() }
}
