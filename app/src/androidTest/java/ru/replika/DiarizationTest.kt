package ru.replika
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.k2fsa.sherpa.onnx.*
import kotlinx.coroutines.runBlocking
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import org.json.*
import ru.replika.ml.AudioDecoder
import java.io.File
@RunWith(AndroidJUnit4::class)
class DiarizationTest {
 @Test fun realAutomaticMultispeakerDiarization()=runBlocking {
  val app=InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp
  val source=File(app.filesDir,"integration-multispeaker.wav")
  Assume.assumeTrue("Stage the official 0-four-speakers-zh.wav first",source.exists())
  app.models.requireReady()
  val pcm=AudioDecoder.decode(source.path,File(app.cacheDir,"multispeaker.pcm"))
  val start=android.os.SystemClock.elapsedRealtime()
  val sd=OfflineSpeakerDiarization(config=OfflineSpeakerDiarizationConfig(
   segmentation=OfflineSpeakerSegmentationModelConfig(pyannote=OfflineSpeakerSegmentationPyannoteModelConfig(app.models.file("diar/segmentation.onnx").path),numThreads=2),
   embedding=SpeakerEmbeddingExtractorConfig(model=app.models.file("diar/embedding.onnx").path,numThreads=2),
   clustering=FastClusteringConfig(numClusters=-1,threshold=0.5f)))
  try {
   val turns=sd.process(AudioDecoder.read(pcm.file,0,pcm.samples))
   val elapsed=android.os.SystemClock.elapsedRealtime()-start
   assertTrue(turns.isNotEmpty());assertTrue(turns.map { it.speaker }.distinct().size>=2)
   assertTrue(turns.all { it.start>=0 && it.end>it.start })
   val out=JSONObject().put("source","official sherpa 0-four-speakers-zh.wav").put("language","zh").put("numClustersConfig",-1).put("threshold",0.5).put("speakers",turns.map { it.speaker }.distinct().size).put("audioMs",pcm.durationMs).put("diarizationMsIncludingLoad",elapsed).put("DER","N/A").put("turns",JSONArray().also { a -> turns.forEach { a.put(JSONObject().put("startMs",(it.start*1000).toLong()).put("endMs",(it.end*1000).toLong()).put("speakerId",it.speaker)) } })
   File(app.filesDir,"android-diarization.json").writeText(out.toString(2))
  } finally { sd.release();pcm.file.delete() }
 }
}
