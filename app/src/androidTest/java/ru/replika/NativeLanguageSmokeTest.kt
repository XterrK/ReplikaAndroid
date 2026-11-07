package ru.replika

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.ml.GigaAmEngine
import ru.replika.ml.LanguageIdentifier
import ru.replika.ml.ModelManager
import ru.replika.ml.ParakeetEngine
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Headless on-device smoke test of the native language paths (no Activity, works behind a locked
 * screen): Whisper-tiny LID, Parakeet (English) and GigaAM (Russian) on real 16 kHz mono PCM16 WAVs.
 * Stage the files with run-as into files/smoke/{en,ru}.wav; the test is skipped when they are absent.
 */
@RunWith(AndroidJUnit4::class)
class NativeLanguageSmokeTest {
 private fun readWav(file: File): FloatArray {
  val bytes=file.readBytes()
  val buffer=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
  var offset=12
  while(offset+8<=bytes.size) {
   val id=String(bytes,offset,4,Charsets.US_ASCII);val size=buffer.getInt(offset+4)
   if(id=="data") {
    val count=size/2;val out=FloatArray(count)
    for(i in 0 until count) out[i]=buffer.getShort(offset+8+2*i)/32768f
    return out
   }
   offset+=8+size+(size and 1)
  }
  error("No data chunk in ${file.name}")
 }

 @Test fun languageIdParakeetAndGigaAmRunOnDevice(): Unit=runBlocking {
  val app=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
  val dir=File(app.filesDir,"smoke")
  val en=File(dir,"en.wav");val ru=File(dir,"ru.wav")
  Assume.assumeTrue("Stage files/smoke/en.wav and ru.wav first",en.isFile && ru.isFile)
  withTimeout(15*60*1000L) { app.bundledModels.awaitReady() }
  assertTrue("LID models ready",app.models.groupReady(ModelManager.LID_GROUP))
  val enAudio=readWav(en);val ruAudio=readWav(ru)
  fun head(a: FloatArray,seconds: Int)=a.copyOfRange(0,minOf(a.size,seconds*16000))
  val result=JSONObject()
  var t=System.nanoTime()
  val labels=LanguageIdentifier(app.models,2).use { lid -> listOf(lid.identify(head(enAudio,10)),lid.identify(head(ruAudio,10))) }
  result.put("lidMs",(System.nanoTime()-t)/1_000_000).put("lidEn",labels[0]).put("lidRu",labels[1])
  t=System.nanoTime()
  val enText=ParakeetEngine(app.models,2).use { it.recognizeDetailed(head(enAudio,15)) }
  result.put("parakeetMs",(System.nanoTime()-t)/1_000_000).put("parakeetText",enText.text)
   .put("parakeetTokens",enText.tokens.size).put("parakeetStrideMs",enText.frameStrideMs)
  t=System.nanoTime()
  val ruText=GigaAmEngine(app.models,2).use { it.recognizeDetailed(head(ruAudio,15)) }
  result.put("gigaamMs",(System.nanoTime()-t)/1_000_000).put("gigaamText",ruText.text).put("gigaamTokens",ruText.tokens.size)
  File(dir,"result.json").writeText(result.toString(2),Charsets.UTF_8)
  Log.i("ReplikaSmoke",result.toString())
  assertEquals("en",labels[0]);assertEquals("ru",labels[1])
  assertTrue("Parakeet produced text",enText.text.isNotBlank() && enText.tokens.isNotEmpty())
  assertTrue("GigaAM produced text",ruText.text.isNotBlank())
 }
}
