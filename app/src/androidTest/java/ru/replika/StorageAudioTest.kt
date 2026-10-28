package ru.replika
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.room.Room
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import ru.replika.data.*
import ru.replika.ml.AudioDecoder
import ru.replika.domain.*
import java.io.File

@RunWith(AndroidJUnit4::class)
class StorageAudioTest {
 private val context get()=InstrumentationRegistry.getInstrumentation().targetContext
 @Test fun sessionSurvivesDatabaseReopen()=runBlocking {
  val name="test-${System.nanoTime()}.db"
  var db=Room.databaseBuilder(context,ReplikaDatabase::class.java,name).build()
  try {
   db.dao().insert(Recording("r","Test","local.wav"))
   val row=SegmentRow.from("r",Segment(id="s",startMs=100,endMs=200,speakerId=0,text="до",source="test fixture"))
   db.dao().insertSegments(listOf(row));db.dao().insert(Recording("r","Renamed","local.wav"));assertEquals(1,db.dao().segmentList("r").size);db.dao().updateSegment(row.copy(text="после",speakerId=1,edited=true,reviewed=true));db.dao().speaker(SpeakerRow("r",1,"Мария"));db.close()
   db=Room.databaseBuilder(context,ReplikaDatabase::class.java,name).build()
   assertEquals("Renamed",db.dao().recording("r")!!.title);val saved=db.dao().segmentList("r").single();assertEquals("после",saved.text);assertEquals(1,saved.speakerId);assertTrue(saved.edited);assertEquals("Мария",db.dao().speakers("r").first().single().name)
  } finally { db.close();context.deleteDatabase(name) }
 }
 @Test fun stereo48kNormalizesTo16kWithoutTimeDrift()=runBlocking {
  val source=File(context.cacheDir,"stereo48.wav");val dest=File(context.cacheDir,"stereo48.pcm")
  java.io.DataOutputStream(source.outputStream().buffered()).use { out ->
   fun le16(n: Int) { out.writeByte(n and 255);out.writeByte((n ushr 8) and 255) }
   fun le32(n: Int) { le16(n and 65535);le16(n ushr 16) }
   val count=48000;out.writeBytes("RIFF");le32(36+count*4);out.writeBytes("WAVEfmt ");le32(16);le16(1);le16(2);le32(48000);le32(48000*4);le16(4);le16(16);out.writeBytes("data");le32(count*4)
   repeat(count) { i -> val sample=(16000*kotlin.math.sin(2*kotlin.math.PI*1000*i/48000)).toInt();le16(sample);le16(sample) }
  }
  try {
   val audio=AudioDecoder.decode(source.path,dest);assertTrue(kotlin.math.abs(audio.samples-16000)<=1);assertTrue(kotlin.math.abs(audio.durationMs-1000)<=1)
   val pcm=AudioDecoder.read(dest,1000,1000);val rms=kotlin.math.sqrt(pcm.sumOf { (it*it).toDouble() }/pcm.size);assertTrue(rms>0.30 && rms<0.40);assertTrue(audio.peaks.isNotEmpty())
  } finally { source.delete();dest.delete() }
 }
 @Test fun corruptedImportReturnsErrorAndRemovesPcm()=runBlocking {
  val source=File(context.cacheDir,"corrupted.mp3").apply { writeText("not audio") };val dest=File(context.cacheDir,"corrupted.pcm")
  try { var failed=false;try { AudioDecoder.decode(source.path,dest) } catch(e: Exception) { failed=true };assertTrue(failed);assertFalse(dest.exists()) } finally { source.delete();dest.delete() }
 }
 @Test fun realModelValidationAndAsr()=runBlocking {
  // Opt-in: models and official test audio must be staged on this Android device.
  val app=context.applicationContext as ReplikaApp
  val audio=File(context.filesDir,"integration-example.wav")
  org.junit.Assume.assumeTrue("Stage real models + integration-example.wav first",audio.exists())
  app.models.requireReady();val decoded=AudioDecoder.decode(audio.path,File(context.cacheDir,"integration.pcm"))
  try { ru.replika.ml.GigaAmEngine(app.models).use { engine -> val text=engine.recognize(AudioDecoder.read(decoded.file,0,decoded.samples));assertTrue("Real ASR returned empty text",text.isNotBlank());File(context.filesDir,"integration-result.txt").writeText(text) } } finally { decoded.file.delete() }
 }
}
