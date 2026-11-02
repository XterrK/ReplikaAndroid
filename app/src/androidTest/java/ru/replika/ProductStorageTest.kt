package ru.replika

import android.content.Context
import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.first
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.data.*
import ru.replika.domain.Exporter
import ru.replika.domain.Segment
import java.io.File
import java.util.UUID

/** Isolated storage fixtures; no real audio, user records, models or native inference. */
@RunWith(AndroidJUnit4::class)
class ProductStorageTest {
 private data class Session(val context: Context,val name: String,var db: ReplikaDatabase,val root: File) {
  val audio=File(root,"audio").apply { mkdirs() }
  val store get()=ProductStorage(db,audio)
  suspend fun row(id: String,path: String,status: String="READY"): SegmentRow {
   db.dao().insert(Recording(id,"Storage regression",path,status=status))
   val row=SegmentRow.from(id,Segment(id="$id-segment",startMs=30,endMs=1500,speakerId=0,text="Исходный текст",source="explicit storage fixture"))
   db.dao().insertSegments(listOf(row));return row
  }
  fun reopen() { db.close();db=Room.databaseBuilder(context,ReplikaDatabase::class.java,name).build() }
 }
 private suspend fun isolated(block: suspend (Session)->Unit) {
  val context=InstrumentationRegistry.getInstrumentation().targetContext
  val name="product-${UUID.randomUUID()}.db"
  val root=File(context.cacheDir,"product-${UUID.randomUUID()}").apply { mkdirs() }
  val session=Session(context,name,Room.databaseBuilder(context,ReplikaDatabase::class.java,name).build(),root)
  try { block(session) } finally { session.db.close();context.deleteDatabase(name);root.deleteRecursively() }
 }

 @Test fun editAndUndoArePersistedAndExported()=runBlocking { isolated { e ->
  val before=e.row("edit","unused.wav")
  val change=e.store.edit(before,"Исправленный текст",12,true)
  assertTrue(change.after.edited);assertTrue(change.after.reviewed)
  e.reopen();assertEquals(change.after,e.db.dao().segment(before.id))
  val savedExport=JSONObject(Exporter.json("Storage",e.db.dao().segmentList("edit").map { it.domain() }) { "Speaker $it" }).getJSONArray("segments").getJSONObject(0)
  assertEquals("Исправленный текст",savedExport.getString("text"));assertEquals(12,savedExport.getInt("speakerId"))
  e.store.undo(change);e.reopen();assertEquals(before,e.db.dao().segment(before.id))
  val undone=JSONObject(Exporter.json("Storage",e.db.dao().segmentList("edit").map { it.domain() }) { "Speaker $it" }).getJSONArray("segments").getJSONObject(0)
  assertEquals(before.text,undone.getString("text"));assertFalse(undone.getBoolean("edited"));assertFalse(undone.getBoolean("reviewed"))
 } }

 @Test fun staleUndoAndStaleEditorNeverOverwriteNewerData()=runBlocking { isolated { e ->
  val before=e.row("stale","unused.wav");val change=e.store.edit(before,"Первое исправление",1,true)
  val newer=change.after.copy(text="Более новая версия",speakerId=2)
  e.db.dao().updateSegment(newer)
  var undoRejected=false;try { e.store.undo(change) } catch(_: ProductOperationException) { undoRejected=true }
  var editRejected=false;try { e.store.edit(before,"Устаревшая форма",3,false) } catch(_: ProductOperationException) { editRejected=true }
  assertTrue(undoRejected);assertTrue(editRejected);assertEquals(newer,e.db.dao().segment(before.id))
  e.db.dao().clearSegments("stale")
  var missingRejected=false;try { e.store.edit(newer,"После удаления",0,false) } catch(_: ProductOperationException) { missingRejected=true }
  assertTrue(missingRejected);assertTrue(e.db.dao().segmentList("stale").isEmpty())
 } }

 @Test fun deletingOwnedAudioRemovesOnlyItsRowsAndFile()=runBlocking { isolated { e ->
  val source=File(e.audio,"owned.audio").apply { writeText("owned fixture bytes") }
  e.row("owned",source.path);e.db.dao().speaker(SpeakerRow("owned",0,"Длинная подпись участника"))
  val other=File(e.audio,"other.audio").apply { writeText("other fixture") };val kept=e.row("other",other.path)
  val result=e.store.deleteRecording("owned")
  assertTrue(result.audioRemoved);assertFalse(result.cleanupPending);assertFalse(source.exists())
  assertNull(e.db.dao().recording("owned"));assertTrue(e.db.dao().segmentList("owned").isEmpty());assertTrue(e.db.dao().speakers("owned").first().isEmpty())
  assertTrue(other.exists());assertEquals(kept,e.db.dao().segment(kept.id))
 } }

 @Test fun externalAndSharedAudioArePreserved()=runBlocking { isolated { e ->
  val external=File(e.root,"external.wav").apply { writeText("external fixture") };e.row("external",external.path)
  val externalResult=e.store.deleteRecording("external");assertTrue(externalResult.audioPreserved);assertTrue(external.exists())
  val shared=File(e.audio,"shared.audio").apply { writeText("shared fixture") };e.row("first",shared.path);val second=e.row("second",File(e.audio,"./shared.audio").path)
  val sharedResult=e.store.deleteRecording("first");assertTrue(sharedResult.audioPreserved);assertTrue(shared.exists());assertEquals(second,e.db.dao().segment(second.id))
  assertTrue(e.store.deleteRecording("second").audioRemoved);assertFalse(shared.exists())
 } }

 @Test fun symlinkOutsideOwnedDirectoryIsNeverDeleted()=runBlocking { isolated { e ->
  val external=File(e.root,"do-not-delete.wav").apply { writeText("external target") }
  val link=File(e.audio,"link.audio")
  java.nio.file.Files.createSymbolicLink(link.toPath(),external.toPath())
  e.row("symlink",link.path)
  assertNull(e.store.ownedAudio(link.path));assertTrue(e.store.deleteRecording("symlink").audioPreserved)
  assertTrue(external.exists());assertEquals("external target",external.readText())
 } }

 @Test fun busyDeletionIsRejectedWithoutChangingData()=runBlocking { isolated { e ->
  val audio=File(e.audio,"busy.audio").apply { writeText("busy fixture") };val before=e.row("busy",audio.path,"PROCESSING")
  var rejected=false;try { e.store.deleteRecording("busy") } catch(_: ProductOperationException) { rejected=true }
  var editRejected=false;try { e.store.edit(before,"Недопустимая правка во время обработки",1,true) } catch(_: ProductOperationException) { editRejected=true }
  assertTrue(rejected);assertTrue(editRejected);assertTrue(audio.exists());assertEquals(before,e.db.dao().segment(before.id));assertEquals("PROCESSING",e.db.dao().recording("busy")!!.status)
 } }

 @Test fun deletionStagingRecoversBothSidesOfDatabaseCommit()=runBlocking { isolated { e ->
  val audio=File(e.audio,"recover.audio").apply { writeText("recover fixture") };e.row("recover",audio.path)
  val trash=File(e.audio,".deleting").apply { mkdirs() }
  val pending=File(trash,"${UUID.randomUUID()}--${audio.name}");assertTrue(audio.renameTo(pending))
  val unrelated=File(trash,"unrelated-file.txt").apply { writeText("must remain") }
  e.reopen();e.store.recoverPendingDeletions();assertTrue(audio.exists());assertFalse(pending.exists());assertTrue(unrelated.exists())
  assertTrue(audio.renameTo(pending));e.db.dao().deleteSpeakers("recover");e.db.dao().clearSegments("recover");e.db.dao().deleteRecording("recover")
  e.reopen();e.store.recoverPendingDeletions();assertFalse(audio.exists());assertFalse(pending.exists());assertTrue(unrelated.exists())
 } }
}
