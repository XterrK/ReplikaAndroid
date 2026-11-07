package ru.replika.ml

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import ru.replika.domain.ChunkedDiarization
import ru.replika.domain.SpeakerRefiner
import ru.replika.domain.Turn

/** Step 6 orchestration: per-window SD + C2 on PCM read from disk, then the pure global
 * clustering/stitching of [ChunkedDiarization]. Only one window of PCM is alive at a time;
 * native SD is released before the C2 extractor opens, exactly as in the single-pass path.
 * Native calls are injected so the orchestration is JVM-testable without JNI. */
object ChunkedDiarizationRunner {
 fun interface WindowSd { suspend fun turns(samples: FloatArray,durationMs: Long): List<Turn> }
 fun interface WindowRefine { suspend fun refine(turns: List<Turn>,durationMs: Long,samples: FloatArray): DiarizationRefiner.Result }

 data class Result(val turns: List<Turn>,val accepted: Boolean,val diagnostics: Map<String,Any?>,val nativeTurnCount: Int)

 suspend fun run(durationMs: Long,totalSamples: Int,config: ChunkedDiarization.Config,
  readPcm: suspend (firstSample: Int,count: Int) -> FloatArray,
  sd: WindowSd,refine: WindowRefine,
  onWindow: suspend (index: Int,count: Int) -> Unit = { _,_ -> }): Result {
  val windows=ChunkedDiarization.planWindows(durationMs,config)
  check(windows.size>1) { "Chunked diarization requires a recording longer than the threshold" }
  val local=mutableListOf<List<Turn>>()
  val centroids=mutableListOf<ChunkedDiarization.Centroid>()
  val perWindow=mutableListOf<Map<String,Any?>>()
  var accepted=true;var nativeCount=0
  for((k,window) in windows.withIndex()) {
   currentCoroutineContext().ensureActive()
   onWindow(k,windows.size)
   val first=window.startMs*16L;val last=minOf(window.endMs*16L,totalSamples.toLong())
   require(first>=0 && last>first && last<=Int.MAX_VALUE)
   val began=System.nanoTime()
   var samples: FloatArray?=readPcm(first.toInt(),(last-first).toInt())
   val windowMs=window.durationMs
   val native=sd.turns(samples!!,windowMs)
   val sdMs=(System.nanoTime()-began)/1_000_000
   currentCoroutineContext().ensureActive()
   val refined=refine.refine(native,windowMs,samples)
   samples=null
   check(refined.diagnostics["nativeResourcesReleasedBeforeRefiner"]==true) { "Не удалось освободить модель говорящих" }
   val measured: List<SpeakerRefiner.EmbeddingWindow> = refined.measuredWindowsQA.orEmpty()
   val found=ChunkedDiarization.windowCentroids(k,refined.turns,measured)
   centroids+=found;local+=refined.turns;nativeCount+=native.size
   accepted=accepted && refined.accepted
   perWindow+=linkedMapOf("startMs" to window.startMs,"endMs" to window.endMs,
    "nativeClusters" to native.map { it.speaker }.distinct().size,"refinedClusters" to refined.turns.map { it.speaker }.distinct().size,
    "accepted" to refined.accepted,"status" to refined.diagnostics["status"],"measuredWindows" to measured.size,
    "centroids" to found.size,"sdMs" to sdMs,"refinerMs" to refined.timingsMs["totalMs"])
  }
  val labels=ChunkedDiarization.globalClusters(centroids,config)
  val mapping=ChunkedDiarization.resolveLabels(local,centroids,labels)
  val cuts=ChunkedDiarization.stitchPoints(windows,local,config)
  val turns=ChunkedDiarization.stitch(windows,local,mapping,cuts)
  // Derived speaker vectors are biometric data: never put centroids into diagnostics.
  return Result(turns,accepted,linkedMapOf("algorithm" to "chunked-window-overcluster-v1","config" to config.asMap(),
   "windows" to perWindow,"cutsMs" to cuts,"centroids" to centroids.size,"globalSpeakers" to turns.map { it.speaker }.distinct().size,
   "singleWindowPcmSamplesMax" to windows.maxOf { it.durationMs }*16),nativeCount)
 }
}
