package ru.replika

import android.graphics.Bitmap
import android.graphics.Color
import android.view.WindowInsets
import androidx.core.graphics.ColorUtils
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import android.os.Build
import android.view.View
import android.view.WindowInsetsController
import android.view.inspector.WindowInspector
import androidx.test.filters.SdkSuppress
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.espresso.Espresso
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.data.AppearancePreferences
import ru.replika.data.ThemeMode
import ru.replika.ui.AppViewModel
import java.io.File

/** Manual app appearance must control actual window flags even when Android's theme differs.
 * Uses the real app export sheet, its actual focused window, focus return and Activity recreation.
 * V1.7: export left the home screen, so the sheet is opened from a transcript fixture.
 * Public WindowInspector starts at API29; no hidden-API reflection or fake bar controller.
 */
@RunWith(AndroidJUnit4::class)
@SdkSuppress(minSdkVersion=29)
class ThemeBarsV15Test {
 @get:Rule val compose=createAndroidComposeRule<MainActivity>()
 private val instrumentation get()=InstrumentationRegistry.getInstrumentation()
 private val app get()=instrumentation.targetContext.applicationContext as ReplikaApp
 private var original=ThemeMode.SYSTEM
 private val rows=JSONArray()
 private lateinit var folder: File
 private val fixture="v17-theme-bars-fixture"
 @Before fun prepare(): Unit {
  original=runBlocking { AppearancePreferences(app).mode.first() }
  if(BuildConfig.BUNDLED_MODELS) runBlocking { app.bundledModels.awaitReady() }
  folder=File(app.filesDir,"theme-bars-v15/${System.currentTimeMillis()}").apply { mkdirs() }
  saveReport("RUNNING")
  val source=File(app.filesDir,"integration-example.wav");assertTrue(source.isFile)
  runBlocking {
   app.db.dao().insert(ru.replika.data.Recording(fixture,"Системные панели · UI fixture",source.path,status="READY",durationMs=11290))
   app.db.dao().clearSegments(fixture)
   app.db.dao().insertSegments(listOf(ru.replika.data.SegmentRow("$fixture-a",fixture,0,11000,0,"Проверяем системные панели.","Controlled UI fixture, no ASR claim")))
  }
  compose.activityRule.scenario.onActivity { ViewModelProvider(it)[AppViewModel::class.java].selected.value=null }
  compose.waitUntil(30000) { compose.onAllNodesWithTag("recording-home").fetchSemanticsNodes().isNotEmpty() }
 }
 @After fun restoreAppPreference(): Unit {
  compose.activityRule.scenario.onActivity { ViewModelProvider(it)[AppViewModel::class.java].selected.value=null }
  runBlocking { app.db.dao().deleteRecording(fixture) }
  runBlocking { AppearancePreferences(app).select(original) }
 }
 private data class Flags(val statusLight: Boolean,val navigationLight: Boolean,val focused: Boolean,val nativeAppearance: Int)
 @Suppress("DEPRECATION")
 private fun flagsFor(decor: View): Flags {
  // Read platform API directly. Compat getters on some older versions have a setter workaround.
  val bits=if(Build.VERSION.SDK_INT>=30) decor.windowInsetsController!!.systemBarsAppearance else decor.systemUiVisibility
  val statusMask=if(Build.VERSION.SDK_INT>=30) WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS else View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
  val navMask=if(Build.VERSION.SDK_INT>=30) WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS else View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
  return Flags(bits and statusMask!=0,bits and navMask!=0,decor.hasWindowFocus(),bits)
 }
 private fun actualFlags(dialog: Boolean): Flags? {
  var result: Flags?=null
  compose.activityRule.scenario.onActivity { activity ->
   val activityDecor=activity.window.decorView
   val target=if(dialog) WindowInspector.getGlobalWindowViews().lastOrNull {
    it!==activityDecor && it.isAttachedToWindow && it.hasWindowFocus()
   } else activityDecor
   result=target?.let(::flagsFor)
  }
  return result
 }
 @Suppress("DEPRECATION")
 private fun assertAppearance(mode: ThemeMode,checkpoint: String,dialog: Boolean=false) {
  val light=mode==ThemeMode.LIGHT
  compose.waitUntil(10000) { actualFlags(dialog)?.let { it.focused && it.statusLight==light && it.navigationLight==light }==true }
  compose.waitForIdle()
  // Ensure the result remains stable through another rendered frame, not just a setter callback.
  instrumentation.waitForIdleSync();Thread.sleep(200)
  val actual=actualFlags(dialog)?:error("Focused dialog window was not found after $checkpoint")
  assertTrue("Inspected window must own focus after $checkpoint",actual.focused)
  assertEquals("Actual status bar flag after $mode/$checkpoint",light,actual.statusLight)
  assertEquals("Actual navigation bar flag after $mode/$checkpoint",light,actual.navigationLight)
  val row=JSONObject().put("theme",mode.name).put("checkpoint",checkpoint).put("statusLight",actual.statusLight)
   .put("navigationLight",actual.navigationLight).put("nativeAppearance",actual.nativeAppearance).put("windowFocused",actual.focused).put("window",if(dialog) "focused-dialog" else "activity")
  val frame=CountDownLatch(1)
  var top=0;var bottom=0;var density=1f
  compose.activityRule.scenario.onActivity { activity ->
   val decor=if(dialog) WindowInspector.getGlobalWindowViews().last { it!==activity.window.decorView && it.hasWindowFocus() } else activity.window.decorView
   decor.viewTreeObserver.registerFrameCommitCallback { frame.countDown() };decor.postInvalidateOnAnimation()
   val insets=activity.window.decorView.rootWindowInsets
   if(Build.VERSION.SDK_INT>=30) { top=insets.getInsets(WindowInsets.Type.statusBars()).top;bottom=insets.getInsets(WindowInsets.Type.navigationBars()).bottom }
   else { top=insets.systemWindowInsetTop;bottom=insets.systemWindowInsetBottom }
   density=activity.resources.displayMetrics.density
  }
  frame.await(3,TimeUnit.SECONDS);Thread.sleep(800)
  val bitmap=instrumentation.uiAutomation.takeScreenshot()?:error("No Android screenshot")
  File(folder,"${mode.name}-$checkpoint.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }
  try { assertPixels(bitmap,mode,dialog,top,bottom,density,row) }
  finally { bitmap.recycle();rows.put(row);saveReport("RUNNING") }

 }
 @Test fun manualLightAndDarkBarsSurviveSheetDismissalAndActivityRecreation(): Unit {
  for(mode in listOf(ThemeMode.LIGHT,ThemeMode.DARK)) {
   compose.activityRule.scenario.onActivity { ViewModelProvider(it)[AppViewModel::class.java].selectTheme(mode) }
   compose.waitUntil(10000) { runBlocking { AppearancePreferences(app).mode.first()==mode } }
   assertAppearance(mode,"before-dialog")
   compose.activityRule.scenario.onActivity { ViewModelProvider(it)[AppViewModel::class.java].selected.value=fixture }
   compose.waitUntil(10000) { compose.onAllNodesWithTag("workspace-export").fetchSemanticsNodes().isNotEmpty() }
   compose.onNodeWithTag("workspace-export").performClick()
   compose.onNodeWithTag("transcript-export").assertIsDisplayed()
   assertAppearance(mode,"during-dialog",dialog=true)
   Espresso.pressBack()
   compose.waitUntil(10000) { compose.onAllNodesWithTag("transcript-export").fetchSemanticsNodes().isEmpty() }
   assertAppearance(mode,"after-dialog")
   compose.activityRule.scenario.onActivity { ViewModelProvider(it)[AppViewModel::class.java].selected.value=null }
   compose.waitUntil(10000) { compose.onAllNodesWithTag("recording-home").fetchSemanticsNodes().isNotEmpty() }
   compose.activityRule.scenario.recreate()
   compose.waitUntil(30000) { compose.onAllNodesWithTag("recording-home").fetchSemanticsNodes().isNotEmpty() }
   assertAppearance(mode,"after-recreation")
  }
  saveReport("PASS")
 }
 private fun saveReport(status: String) {
  val report=JSONObject().put("api",Build.VERSION.SDK_INT).put("device","${Build.MANUFACTURER} ${Build.MODEL}")
   .put("systemNightMode",app.resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK)
   .put("status",status).put("scope","Actual Activity/dialog flags plus screenshot background and glyph-contrast checks; public window inspection requires API29+")
   .put("snapshots",rows).put("folder",folder.name)
  File(folder,"flags.json").writeText(report.toString(2))
  File(app.filesDir,"theme-bars-v15/latest.json").writeText(report.toString(2))
 }
 private fun assertPixels(bitmap: Bitmap,mode: ThemeMode,dialog: Boolean,top: Int,bottom: Int,density: Float,row: JSONObject) {
  assertTrue("Visible status/navigation bar bounds are required",top>0 && bottom>0)
  val status=bitmap.getPixel(bitmap.width/2,(top/2).coerceIn(0,bitmap.height-1))
  val navigation=bitmap.getPixel(bitmap.width/8,(bitmap.height-bottom/2).coerceIn(0,bitmap.height-1))
  row.put("statusPixel",String.format("#%06X",status and 0xffffff)).put("navigationPixel",String.format("#%06X",navigation and 0xffffff))
  if(!dialog) {
   val expected=if(mode==ThemeMode.DARK) Color.rgb(14,15,19) else Color.rgb(246,247,251)
   for((name,actual) in listOf("status" to status,"navigation" to navigation)) {
    assertTrue("$mode $name background must follow the manual app theme",kotlin.math.abs(Color.red(actual)-Color.red(expected))<=4 && kotlin.math.abs(Color.green(actual)-Color.green(expected))<=4 && kotlin.math.abs(Color.blue(actual)-Color.blue(expected))<=4)
   }
  } else {
   // A modal dim layer and the sheet surface legitimately change exact background tokens.
   for(pixel in listOf(status,navigation)) assertTrue("Dialog system bars must stay in the selected theme",if(mode==ThemeMode.DARK) maxOf(Color.red(pixel),Color.green(pixel),Color.blue(pixel))<70 else minOf(Color.red(pixel),Color.green(pixel),Color.blue(pixel))>135)
  }
  var clockContrast=1.0
  val left=(8*density).toInt();val right=minOf((54*density).toInt(),bitmap.width-1)
  for(y in 2 until (top-2).coerceAtLeast(3)) for(x in left..right) clockContrast=maxOf(clockContrast,ColorUtils.calculateContrast(bitmap.getPixel(x,y),status))
  row.put("clockGlyphMaxContrast",clockContrast)
  assertTrue("Status clock glyphs must remain visible against the actual background",clockContrast>=3.0)
  if(bottom>=40*density) {
   val home=bitmap.getPixel(bitmap.width/2,bitmap.height-bottom/2)
   val contrast=ColorUtils.calculateContrast(home,navigation);row.put("homeGlyphContrast",contrast)
   assertTrue("Three-button Home glyph must contrast with its background",contrast>=3.0)
  } else {
   var handleContrast=1.0
   for(y in (bitmap.height-bottom).coerceAtLeast(0) until bitmap.height) for(x in bitmap.width/4..bitmap.width*3/4) {
    handleContrast=maxOf(handleContrast,ColorUtils.calculateContrast(bitmap.getPixel(x,y),navigation))
   }
   row.put("gestureHandleMaxContrast",handleContrast)
   assertTrue("Gesture handle must contrast with the actual navigation background",handleContrast>=3.0)
  }
 }
}
