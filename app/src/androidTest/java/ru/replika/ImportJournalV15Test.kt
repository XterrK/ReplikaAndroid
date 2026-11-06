package ru.replika

import android.database.sqlite.SQLiteException
import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import ru.replika.data.*
import java.io.File
import java.util.UUID

/** Isolated persisted interruption fixtures, actual Room references and a real coroutine gate.
 * New journal instances emulate process restart; this suite does not claim an actual OS hard kill.
 */
@RunWith(AndroidJUnit4::class)
class ImportJournalV15Test {
 private lateinit var directory: File
 private lateinit var audio: File
 private lateinit var database: ReplikaDatabase
 private lateinit var gate: Mutex
 private lateinit var journal: ImportJournal
 private val dao get()=database.dao()
 @Before fun createIsolatedState(): Unit {
  val context=InstrumentationRegistry.getInstrumentation().targetContext
  directory=File(context.cacheDir,"import-journal-${System.nanoTime()}").apply { check(mkdirs()) }
  audio=File(directory,"audio")
  database=Room.inMemoryDatabaseBuilder(context,ReplikaDatabase::class.java).build()
  gate=Mutex();journal=ImportJournal(audio,gate)
 }
 @After fun destroyOnlyIsolatedState(): Unit { database.close();directory.deleteRecursively() }
 private fun newId()=UUID.randomUUID().toString()
 private fun marker(id: String)=File(audio,".pending-imports/$id.pending")
 private fun output(id: String,extension: String="wav")=File(audio,"$id.$extension").apply { parentFile!!.mkdirs();writeText("owned interrupted audio $id") }

 @Test fun interruptedUncommittedOutputIsRemovedButUnmarkedFilesAndSourceRemain(): Unit=runBlocking {
  val id=newId();journal.begin(id);val partial=output(id)
  val unmarked=output(newId());val source=File(directory,"source-video.mp4").apply { writeText("original source") }
  val report=ImportJournal(audio,Mutex()).recover(dao::audioPathsReferenced)
  assertEquals(1,report.cleaned);assertFalse(partial.exists());assertFalse(marker(id).exists())
  assertTrue(unmarked.isFile);assertEquals("original source",source.readText())
 }
 @Test fun committedRoomOutputSurvivesRecoveryAndMarkerIsRemoved(): Unit=runBlocking {
  val id=newId();journal.begin(id);val file=output(id)
  dao.insert(Recording(id,"Committed",file.path))
  val report=ImportJournal(audio,Mutex()).recover(dao::audioPathsReferenced)
  assertEquals(1,report.referenced);assertTrue(file.isFile);assertFalse(marker(id).exists())
  assertEquals(file.path,dao.recording(id)!!.audioPath)
 }
 @Test fun referenceFromAnotherRecordingAlsoPreservesAudio(): Unit=runBlocking {
  val id=newId();journal.begin(id);val file=output(id)
  dao.insert(Recording(newId(),"Shared reference",file.canonicalPath))
  assertEquals(1,journal.recover(dao::audioPathsReferenced).referenced)
  assertTrue(file.isFile);assertFalse(marker(id).exists())
 }
 @Test fun databaseLookupFailureRetainsMarkerAndEveryCandidateUntilRetry(): Unit=runBlocking {
  val id=newId();journal.begin(id);val first=output(id,"audio");val second=output(id,"m4a")
  val report=journal.recover { throw SQLiteException("Controlled lookup failure") }
  assertEquals(1,report.deferred);assertTrue(first.isFile);assertTrue(second.isFile);assertTrue(marker(id).isFile)
  assertEquals(1,ImportJournal(audio,Mutex()).recover(dao::audioPathsReferenced).cleaned)
  assertFalse(first.exists());assertFalse(second.exists());assertFalse(marker(id).exists())
 }
 @Test fun cancellationAfterActualRoomCommitPreservesFile(): Unit=runBlocking {
  val id=newId();var file: File?=null
  val job=launch {
   journal.runImport(id,dao::audioPathsReferenced) {
    file=output(id);dao.insert(Recording(id,"Commit before cancellation",file!!.path))
    currentCoroutineContext().cancel();yield()
   }
  }
  job.join();assertTrue(job.isCancelled);assertTrue(file!!.isFile)
  assertEquals(file!!.path,dao.recording(id)!!.audioPath);assertFalse(marker(id).exists())
 }
 @Test fun failureBeforeCommitCleansOwnedOutputButFailedBeginNeverDeletesCollisions(): Unit=runBlocking {
  val first=newId()
  try { journal.runImport(first,dao::audioPathsReferenced) { output(first);throw IllegalStateException("Controlled extraction failure") };fail("Expected failure") }
  catch(_: IllegalStateException) { }
  assertFalse(File(audio,"$first.wav").exists());assertFalse(marker(first).exists())
  val collision=newId();val existing=output(collision);val text=existing.readText()
  try { journal.runImport(collision,dao::audioPathsReferenced) { fail("A colliding begin must never run the action") };fail("Expected collision") }
  catch(_: ProductOperationException) { }
  assertEquals(text,existing.readText());assertFalse(marker(collision).exists())
  val pending=newId();journal.begin(pending);val prior=output(pending)
  try { journal.runImport(pending,dao::audioPathsReferenced) { fail("Existing marker is not ours") };fail("Expected pending collision") }
  catch(_: ProductOperationException) { }
  assertTrue(prior.isFile);assertTrue(marker(pending).isFile)
 }
 @Test fun recoveryWaitsForLiveImportUsingTheSameProcessGate(): Unit=runBlocking {
  val id=newId();val entered=CompletableDeferred<Unit>();val release=CompletableDeferred<Unit>();var file: File?=null
  val active=launch {
   journal.runImport(id,dao::audioPathsReferenced) {
    file=output(id);entered.complete(Unit);release.await()
    dao.insert(Recording(id,"Live import",file!!.path))
   }
  }
  entered.await();val attempted=CompletableDeferred<Unit>()
  val recovery=async { attempted.complete(Unit);ImportJournal(audio,gate).recover(dao::audioPathsReferenced) }
  attempted.await();delay(50)
  assertTrue(gate.isLocked);assertFalse(recovery.isCompleted);assertTrue(file!!.isFile);assertTrue(marker(id).isFile)
  release.complete(Unit);active.join();recovery.await()
  assertTrue(file!!.isFile);assertFalse(marker(id).exists());assertNotNull(dao.recording(id))
 }
 @Test fun invalidMarkersAndRedirectedOutputsCannotAuthorizeDeletion(): Unit=runBlocking {
  val invalid=newId();journal.begin(invalid);val file=output(invalid)
  marker(invalid).writeText("untrusted marker\n../../source-video.mp4\n")
  val oversized=newId();journal.begin(oversized);val untouched=output(oversized);marker(oversized).writeBytes(ByteArray(1024))
  val redirected=newId();journal.begin(redirected)
  val external=File(directory,"external-source.wav").apply { writeText("external original") }
  java.nio.file.Files.createSymbolicLink(File(audio,"$redirected.wav").toPath(),external.toPath())
  val report=journal.recover(dao::audioPathsReferenced)
  assertEquals(2,report.invalid);assertEquals(1,report.deferred)
  assertTrue(file.isFile);assertTrue(untouched.isFile);assertEquals("external original",external.readText())
  assertTrue(marker(invalid).isFile);assertTrue(marker(oversized).isFile);assertTrue(marker(redirected).isFile)
 }
}
