package ru.replika
import android.content.ContextWrapper
import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import ru.replika.ml.ModelManager
import java.io.File
@RunWith(AndroidJUnit4::class)
class ModelPackTest {
 @Before fun stopPreviousIntegrationWork() {
  val context=InstrumentationRegistry.getInstrumentation().targetContext
  androidx.work.WorkManager.getInstance(context).cancelAllWork().result.get(15,java.util.concurrent.TimeUnit.SECONDS)
 }

 @Test fun importRealOfflinePack()=runBlocking {
  val app=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
  val pack=File(app.filesDir,"integration-model-pack.zip")
  Assume.assumeTrue("Stage offline ZIP with tools/stage_android.py --pack",pack.exists())
  app.models.importPack(Uri.fromFile(pack)) { }
  assertTrue(app.models.statuses().all { it.installed })
 }
 @Test fun corruptPackCannotReplaceVerifiedModel()=runBlocking {
  val app=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
  Assume.assumeTrue("Import real pack first",app.models.statuses().all { it.installed })
  val target=app.models.file("giga-v2/encoder.int8.onnx")
  val originalSize=target.length()
  val pack=File(app.cacheDir,"corrupt-test-pack.zip")
  java.util.zip.ZipOutputStream(pack.outputStream()).use { z ->
   z.putNextEntry(java.util.zip.ZipEntry("giga-v2/encoder.int8.onnx"));z.write("corrupt model fixture".toByteArray());z.closeEntry()
  }
  try {
   var rejected=false
   try { app.models.importPack(Uri.fromFile(pack)) { } } catch(e: IllegalArgumentException) { rejected=true }
   assertTrue(rejected);assertEquals(originalSize,target.length());app.models.requireReady()
   assertFalse(File(target.path+".installing").exists())
  } finally { pack.delete() }
 }
 @Test fun incompleteModelsCannotReachInference() {
  val context=InstrumentationRegistry.getInstrumentation().targetContext
  val isolated=File(context.cacheDir,"model-safety-${System.nanoTime()}").apply { mkdirs() }
  val wrapped=object: ContextWrapper(context) { override fun getFilesDir()=isolated }
  try {
   val manager=ModelManager(wrapped)
   manager.file("giga-v2/encoder.int8.onnx").apply { parentFile!!.mkdirs();writeText("incomplete fixture") }
   var rejected=false
   try { manager.requireReady() } catch(e: IllegalArgumentException) { rejected=true }
   assertTrue(rejected);assertFalse(manager.statuses().any { it.installed })
  } finally { isolated.deleteRecursively() }
 }
}
