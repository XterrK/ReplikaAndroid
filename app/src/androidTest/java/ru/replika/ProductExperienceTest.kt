package ru.replika

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.os.SystemClock
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.text.AnnotatedString
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.data.ProductStorage
import ru.replika.data.Recording
import ru.replika.data.SegmentRow
import ru.replika.data.SpeakerRow
import ru.replika.ui.AppViewModel
import java.io.File
import java.security.MessageDigest
import java.util.UUID

/** UI-only copies of actual PipelineTest output. No ASR text, turns or warning reasons are invented. */
@RunWith(AndroidJUnit4::class)
class ProductExperienceTest {
 @get:Rule val compose=createAndroidComposeRule<MainActivity>()
 private val instrumentation get()=InstrumentationRegistry.getInstrumentation()
 private val app get()=instrumentation.targetContext.applicationContext as ReplikaApp
 private lateinit var fixture: Recording
 private lateinit var before: SegmentRow
 private lateinit var ownedAudio: File
 private lateinit var originalAudio: File
 private lateinit var originalHash: String
 private lateinit var originalRecording: Recording
 private var observedLoading=false
 private val profile get()=compose.activity.resources.configuration.let {
  (if(it.fontScale>=1.25f) "compact130-" else "base-")+it.screenWidthDp+"x"+it.screenHeightDp
 }
 private fun sha(file: File): String {
  val digest=MessageDigest.getInstance("SHA-256")
  file.inputStream().buffered().use { input -> val b=ByteArray(65536);while(true) { val n=input.read(b);if(n<0) break;digest.update(b,0,n) } }
  return digest.digest().joinToString("") { "%02x".format(it) }
 }
 private fun participant(id: Int)="Тестовый участник ${id+1} · Длинная подпись для проверки полного имени"
 private fun row()=runBlocking { app.db.dao().segmentList(fixture.id).first { it.id==before.id } }
 private fun hideKeyboard() { androidx.test.espresso.Espresso.closeSoftKeyboard();compose.mainClock.advanceTimeBy(500);compose.waitForIdle() }
 private fun capture(base: String) {
  compose.waitForIdle()
  Thread.sleep(500) // Compose idleness does not wait for the native dialog fade/compositor.
  compose.waitForIdle()
  InstrumentationRegistry.getInstrumentation().waitForIdleSync()
  Thread.sleep(100)
  val folder=File(app.filesDir,"human-review-v1.2").apply { mkdirs() }
  val target=File(folder,"$base-$profile.png")
  if(target.exists()) check(target.renameTo(File(folder,"$base-$profile-${System.nanoTime()}.png")))
  val bitmap=instrumentation.uiAutomation.takeScreenshot()?:error("No actual Android screenshot returned")
  target.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) };bitmap.recycle()
 }
 private fun proof(case: String,detail: JSONObject) {
  val data=JSONObject().put("case",case).put("profile",profile)
   .put("fontScale",compose.activity.resources.configuration.fontScale)
   .put("sourceRecordingId",originalRecording.id).put("sourceAudioSha256",originalHash)
   .put("uiFixtureRecordingId",fixture.id).put("uiOnlyCopyOfActualInference",true)
   .put("newInferencePerformed",false).put("manuallyCreatedSpeakerRoster",12)
   .put("noWarningReasonsInjected",true).put("observedLoadingTag",observedLoading).put("detail",detail)
  val target=File(app.filesDir,"product-experience-v12-$profile-$case.json")
  if(target.exists()) check(target.renameTo(File(app.filesDir,"product-experience-v12-$profile-$case-${System.nanoTime()}.json")))
  target.writeText(data.toString(2))
 }

 @Before fun copyActualInferenceForUiOnly()=runBlocking {
  val dao=app.db.dao()
  originalRecording=dao.recording("integration-real-giga")?:error("Run the real PipelineTest before ProductExperienceTest")
  assertEquals("The source must be a completed real pipeline", "READY",originalRecording.status)
  val actualRows=dao.segmentList(originalRecording.id)
  assertTrue("Do not replace absent real inference with demonstration text",actualRows.isNotEmpty())
  assertTrue(actualRows.all { it.source.contains("GigaAM") && it.text.isNotBlank() })
  originalAudio=File(originalRecording.audioPath);assertTrue(originalAudio.isFile)
  originalHash=sha(originalAudio)
  assertEquals("Only the public QA source may be copied",PUBLIC_SOURCE_SHA,originalHash)
  val id="ui-product-${UUID.randomUUID()}"
  ownedAudio=File(File(app.filesDir,"audio").apply { mkdirs() },"$id.wav")
  originalAudio.copyTo(ownedAudio)
  val diagnostics=if(originalRecording.diagnostics.isBlank()) JSONObject() else JSONObject(originalRecording.diagnostics)
  diagnostics.put("uiFixture",true).put("copiedFromRecordingId",originalRecording.id).put("newInferencePerformed",false)
  fixture=originalRecording.copy(id=id,title="UI-проверка · копия реальной стенограммы",audioPath=ownedAudio.path,
   createdAt=System.currentTimeMillis(),status="READY",phase="Готово · UI-проверка",diagnostics=diagnostics.toString())
  dao.insert(fixture)
  val copied=actualRows.mapIndexed { index,row -> row.copy(id="$id-segment-$index",recordingId=id) }
  dao.insertSegments(copied);before=copied.first()
  repeat(12) { dao.speaker(SpeakerRow(id,it,participant(it))) }
 }

 @After fun removeOnlyOwnedUiFixture() {
  if(!::fixture.isInitialized) return
  compose.activityRule.scenario.onActivity { activity ->
   val vm=ViewModelProvider(activity)[AppViewModel::class.java]
   if(vm.selected.value==fixture.id) vm.selected.value=null
   vm.clearNotice()
  }
  runBlocking {
   app.models.gate.withLock {
    if(app.db.dao().recording(fixture.id)!=null) ProductStorage(app.db,File(app.filesDir,"audio")).deleteRecording(fixture.id)
   }
  }
  assertTrue("The original QA input must survive fixture cleanup",originalAudio.isFile)
  assertEquals(originalHash,sha(originalAudio))
 }

 private fun findFixtureInLibrary() {
  compose.waitUntil(10000) { compose.onAllNodesWithTag("library-list").fetchSemanticsNodes().isNotEmpty() }
  compose.waitUntil(10000) {
   var present=false
   compose.activityRule.scenario.onActivity { activity -> present=ViewModelProvider(activity)[AppViewModel::class.java].recordings.value.any { it.id==fixture.id } }
   present
  }
  compose.onNodeWithTag("library-search").performTextReplacement("UI-проверка")
  hideKeyboard()
  compose.onNodeWithTag("library-list").performScrollToNode(hasTestTag("recording-${fixture.id}"))
 }
 private fun openFixture() {
  findFixtureInLibrary()
  compose.onNodeWithTag("recording-${fixture.id}").performClick()
  awaitActualRows()
 }
 private fun awaitActualRows() {
  compose.waitUntil(10000) {
   assertTrue("Ready data must not flash a false empty transcript",compose.onAllNodesWithTag("transcript-empty").fetchSemanticsNodes().isEmpty())
   observedLoading=observedLoading || compose.onAllNodesWithTag("transcript-loading").fetchSemanticsNodes().isNotEmpty()
   compose.onAllNodesWithTag("segment-${before.id}").fetchSemanticsNodes().isNotEmpty()
  }
  compose.onNodeWithTag("transcript-empty").assertDoesNotExist()
  compose.onNodeWithTag("segment-${before.id}").assertIsDisplayed()
 }
 private fun openEditor() {
  compose.onAllNodesWithContentDescription("Изменить реплику").onFirst().performClick()
  compose.onNodeWithTag("transcript-editor").assertIsDisplayed()
 }

 @Test fun editorLongRosterSaveUndoAndDiscard() {
  openFixture();capture("22-product-workspace")
  openEditor()
  compose.onNodeWithTag("editor-save").assertIsNotEnabled()
  compose.onNodeWithTag("editor-listen").performClick()
  compose.waitUntil(5000) { compose.onAllNodesWithContentDescription("Пауза").fetchSemanticsNodes().isNotEmpty() }
  compose.onNodeWithTag("editor-listen").assertTextEquals("Пауза").performClick()
  compose.waitUntil(5000) { compose.onNodeWithTag("editor-listen").fetchSemanticsNode().config[SemanticsProperties.Text].joinToString { it.text }.contains("Прослушать") }
  compose.onNodeWithTag("editor-speaker").performScrollTo().performClick()
  compose.onNodeWithTag("speaker-search").performClick().performTextReplacement("12")
  capture("29-product-speaker-picker-keyboard")
  compose.onNodeWithTag("speaker-option-11").assertIsDisplayed()
  hideKeyboard()
  compose.onNodeWithTag("speaker-option-11").assertIsDisplayed()
  capture("20-product-editor-longnames")
  compose.onNodeWithTag("speaker-option-11").performClick()
  compose.onNodeWithText(participant(11)).assertExists()
  val draft=before.text+" [UI-проверка V1.2]"
  compose.onNodeWithTag("editor-text").performScrollTo().performClick().performTextReplacement(draft)
  compose.onNodeWithTag("editor-text").assertIsDisplayed()
  compose.onNodeWithTag("editor-save").assertIsDisplayed()
  capture("23-product-editor-keyboard")
  hideKeyboard()
  if(!before.reviewed) compose.onNodeWithTag("editor-reviewed").performScrollTo().performClick()
  compose.onNodeWithTag("editor-save-state").assertTextEquals("Есть несохранённые изменения")
  compose.activityRule.scenario.recreate()
  compose.onNodeWithTag("transcript-editor").assertIsDisplayed()
  compose.onNodeWithTag("editor-text").assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText,AnnotatedString(draft)))
  compose.onNodeWithTag("editor-reviewed").assertIsOn()
  compose.onNodeWithText(participant(11)).assertExists()
  compose.onNodeWithTag("editor-save-state").assertTextEquals("Есть несохранённые изменения")
  compose.onNodeWithTag("editor-save").assertIsEnabled().performClick()
  compose.waitUntil(10000) { row().let { it.text==draft && it.speakerId==11 && it.reviewed && it.edited } }
  compose.onNodeWithTag("transcript-editor").assertDoesNotExist()
  val saved=row()
  assertEquals(before.startMs,saved.startMs);assertEquals(before.endMs,saved.endMs);assertEquals(before.source,saved.source)
  compose.waitUntil(3000) { compose.onAllNodesWithText("Отменить правку").fetchSemanticsNodes().isNotEmpty() }
  capture("24-product-saved-undo")
  compose.onNodeWithText("Отменить правку").performClick()
  compose.waitUntil(10000) { row()==before }
  openEditor()
  val unsaved=before.text+" [НЕ СОХРАНЯТЬ]"
  compose.onNodeWithTag("editor-text").performScrollTo().performTextReplacement(unsaved)
  hideKeyboard()
  // Back must use the same dirty-state protection as the explicit close button.
  assertTrue(instrumentation.uiAutomation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
  compose.waitUntil(5000) { runCatching { compose.onNodeWithText("Не сохранять изменения?").assertIsDisplayed();true }.getOrDefault(false) }
  capture("21-product-discard")
  assertEquals(before,row())
  compose.onNodeWithText("Продолжить редактирование").performClick()
  compose.onNodeWithTag("editor-text").assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText,AnnotatedString(unsaved)))
  compose.onNodeWithContentDescription("Закрыть редактор").performClick()
  compose.onNodeWithText("Не сохранять").performClick()
  compose.onNodeWithTag("transcript-editor").assertDoesNotExist();assertEquals(before,row())
  compose.activityRule.scenario.recreate();awaitActualRows();assertEquals(before,row())
  proof("editor",JSONObject().put("savePersisted",true).put("speakerIdAfterSave",11).put("originalTimesAndSourcePreserved",true)
   .put("undoRestoredExactRow",true).put("backRequestedDiscardConfirmation",true).put("continueKeptDraft",true)
   .put("discardKeptSavedRow",true).put("activityRecreationKeptSavedRow",true).put("realPlayerStarted",true).put("dirtyDraftSurvivedActivityRecreation",true))
 }

 @Test fun workspaceSeekSpeedAndBackgroundPause() {
  openFixture()
  compose.onNodeWithText(before.text).performClick()
  compose.waitUntil(5000) { compose.onAllNodesWithContentDescription("Пауза").fetchSemanticsNodes().isNotEmpty() }
  compose.onNodeWithTag("segment-${before.id}").assertIsSelected()
  compose.onNodeWithContentDescription("Пауза").performClick()
  fun fraction()=compose.onNodeWithTag("audio-waveform").fetchSemanticsNode().config[SemanticsProperties.ProgressBarRangeInfo].current
  compose.onNodeWithTag("audio-waveform").performSemanticsAction(SemanticsActions.SetProgress) { it(.9f) }
  compose.waitUntil(5000) { fraction() in .88f.. .92f }
  compose.onNodeWithContentDescription("Вперёд 10 секунд").performClick()
  compose.waitUntil(5000) { fraction()>=.99f }
  compose.onNodeWithContentDescription("Назад 10 секунд").performClick()
  compose.waitUntil(5000) { fraction() in .10f.. .14f }
  compose.onNodeWithTag("playback-speed").performClick()
  compose.onNodeWithTag("playback-speed").assertTextEquals("1.25×")
  compose.onNodeWithContentDescription("Воспроизвести").performClick()
  compose.waitUntil(5000) { compose.onAllNodesWithContentDescription("Пауза").fetchSemanticsNodes().isNotEmpty() }
  compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.CREATED)
  compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.RESUMED)
  compose.onNodeWithContentDescription("Воспроизвести").assertIsDisplayed()
  capture("28-product-player-seek")
  val exported=File(app.cacheDir,"exports/replika-${fixture.id}.json")
  assertFalse("This must be a fresh export of the isolated QA record",exported.exists())
  compose.onNodeWithContentDescription("Экспорт").performClick()
  compose.onNodeWithTag("export-txt").assertIsDisplayed()
  compose.onNodeWithTag("export-srt").assertIsDisplayed()
  compose.onNodeWithTag("export-json").assertIsDisplayed()
  capture("36-product-export-options")
  compose.onNodeWithTag("export-json").performClick()
  compose.waitUntil(10000) { exported.exists() && exported.length()>0 }
  val saved=JSONObject(exported.readText()).getJSONArray("segments")
  val item=(0 until saved.length()).map { saved.getJSONObject(it) }.single { it.getString("id")==before.id }
  assertEquals(before.text,item.getString("text"));assertEquals(before.speakerId,item.getInt("speakerId"))
  assertEquals(before.startMs,item.getLong("startMs"));assertEquals(before.endMs,item.getLong("endMs"))
  assertEquals(before.edited,item.getBoolean("edited"));assertEquals(before.reviewed,item.getBoolean("reviewed"))
  assertEquals(participant(before.speakerId),item.getString("speakerName"))
  instrumentation.uiAutomation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
  compose.waitForIdle()
  proof("player",JSONObject().put("freshUiExportMatchesSavedRows",true).put("allExportFormatsVisible",true).put("segmentTapSelectedCorrectRow",true).put("waveformSeekFraction",.9)
   .put("forwardClampAtEnd",true).put("replay10ReturnedToExpectedPosition",true).put("speedUi",1.25)
   .put("backgroundPausedActualPlayer",true).put("physicalAudioOutputVerified",false))
 }
 @Test fun libraryDeleteConfirmationRemovesOnlyOwnedCopy() {
  findFixtureInLibrary()
  val idsBefore=runBlocking { app.db.dao().recordingList().map { it.id }.toSet() }
  val sourceRowsBefore=runBlocking { app.db.dao().segmentList(originalRecording.id) }
  val sourceNamesBefore=runBlocking { app.db.dao().speakers(originalRecording.id).first() }
  fun requestDelete() {
   compose.onNodeWithTag("recording-menu-${fixture.id}").performClick()
   compose.onNodeWithText("Удалить запись").performClick()
   compose.onNodeWithTag("confirm-delete-recording").assertIsDisplayed()
  }
  requestDelete();assertTrue(ownedAudio.exists());assertNotNull(runBlocking { app.db.dao().recording(fixture.id) })
  compose.onNodeWithText("Отмена").performClick()
  assertTrue(ownedAudio.exists());assertEquals(before,row())
  requestDelete();capture("25-product-delete-confirmation")
  compose.onNodeWithTag("confirm-delete-recording").performClick()
  compose.waitUntil(10000) { runBlocking { app.db.dao().recording(fixture.id)==null } && !ownedAudio.exists() }
  val idsAfter=runBlocking { app.db.dao().recordingList().map { it.id }.toSet() }
  assertEquals(idsBefore-fixture.id,idsAfter)
  assertTrue(runBlocking { app.db.dao().segmentList(fixture.id).isEmpty() })
  assertTrue(runBlocking { app.db.dao().speakers(fixture.id).first().isEmpty() })
  assertEquals(sourceRowsBefore,runBlocking { app.db.dao().segmentList(originalRecording.id) })
  assertEquals(sourceNamesBefore,runBlocking { app.db.dao().speakers(originalRecording.id).first() })
  assertTrue(originalAudio.exists());assertEquals(originalHash,sha(originalAudio))
  compose.onNodeWithTag("recording-${fixture.id}").assertDoesNotExist()
  compose.onNodeWithTag("library-search").performTextClearance();hideKeyboard()
  capture("26-product-library-after-delete")
  proof("delete",JSONObject().put("confirmationRequired",true).put("cancelPreservedDataAndAudio",true)
   .put("confirmedDeletionRemovedOwnedAudio",true).put("segmentsAndSpeakerNamesRemoved",true)
   .put("allOtherRecordingIdsPreserved",true).put("originalPublicAudioUnchanged",true))
 }

 @Test fun corruptImportedFixtureDoesNotPrematurelyPreparePlayer() {
  // This is an explicit bad-container storage fixture, never an ASR result.
  ownedAudio.writeText("Explicit corrupt audio fixture for pre-processing UI")
  fixture=fixture.copy(status="IMPORTED",phase="Готово к обработке",durationMs=0,peaks="",diagnostics="")
  runBlocking { app.db.dao().insert(fixture) }
  findFixtureInLibrary()
  compose.onNodeWithTag("recording-${fixture.id}").performClick()
  compose.waitUntil(10000) { compose.onAllNodesWithText("Создать стенограмму").fetchSemanticsNodes().isNotEmpty() }
  val observedAt=SystemClock.elapsedRealtime()
  compose.waitUntil(5000) {
   assertTrue("Imported media must not trigger a hidden eager-player error",compose.onAllNodesWithText("Не удалось завершить действие").fetchSemanticsNodes().isEmpty())
   assertTrue(compose.onAllNodesWithText("Source error",substring=true).fetchSemanticsNodes().isEmpty())
   SystemClock.elapsedRealtime()-observedAt>=1200
  }
  assertEquals("IMPORTED",runBlocking { app.db.dao().recording(fixture.id)!!.status })
  assertEquals(before,row())
  capture("27-product-corrupt-before-processing")
  proof("corrupt-imported",JSONObject().put("explicitCorruptContainerFixture",true).put("workerNotStarted",true)
   .put("noPrematurePlaybackErrorDialog",true).put("savedRowsUnaffected",true).put("observedMs",SystemClock.elapsedRealtime()-observedAt))
 }

 @Test fun corruptedWorkerExplainsRecoveryAndKeepsSavedRows() {
  val broken=fixture.copy(status="IMPORTED",phase="Ожидание обработки",diagnostics="")
  ownedAudio.writeText("REPLIKA explicit invalid audio container for UI regression")
  runBlocking { app.db.dao().insert(broken) }
  findFixtureInLibrary();compose.onNodeWithTag("recording-${fixture.id}").performClick()
  compose.waitUntil(10000) { compose.onAllNodesWithText("Создать стенограмму").fetchSemanticsNodes().isNotEmpty() }
  compose.onNodeWithText("Создать стенограмму").performScrollTo().performClick()
  compose.waitUntil(120000) { runBlocking { app.db.dao().recording(fixture.id)?.status=="ERROR" } }
  compose.onNodeWithText("Не удалось обработать аудио").assertIsDisplayed()
  compose.onNodeWithText("Импортируйте другую копию",substring=true).assertExists()
  compose.onNodeWithText("Source error",substring=true).assertDoesNotExist()
  assertEquals(before,row())
  val error=runBlocking { app.db.dao().recording(fixture.id)!!.error };assertFalse(error.isNullOrBlank())
  capture("34-product-corrupt-worker-recovery")
  proof("corrupt-worker",JSONObject().put("explicitCorruptContainerFixture",true).put("productionWorkerReachedError",true)
   .put("userRecoveryExplained",true).put("originalError",error).put("previousSavedRowPreserved",true).put("newAsrInferencePerformed",false))
 }

 companion object {
  private const val PUBLIC_SOURCE_SHA="d8aaaa18a5098d7c6de0595ae7ac1e64cacd0d4022af3595213bdaf23be77e69"
 }
}
