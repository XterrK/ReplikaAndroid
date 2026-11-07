package ru.replika.ml

import android.os.SystemClock
import androidx.work.CoroutineWorker
import androidx.work.workDataOf
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import ru.replika.domain.ProcessingEta
import ru.replika.domain.ProcessingSnapshot
import ru.replika.domain.ProcessingStage

/**
 * Publishes stage, processed share of the audio and remaining time through WorkManager.setProgress.
 * Stage hooks are plain non-suspending calls, safe from native callbacks and tight loops: they only
 * update volatile fields. A child coroutine publishes at most once per second.
 */
class ProcessingProgressReporter(private val worker: CoroutineWorker,private val clock: ()->Long = SystemClock::elapsedRealtime) {
 private val eta=ProcessingEta()
 private val completed=mutableListOf<ProcessingEta.Completed>()
 @Volatile private var stage: ProcessingStage?=null
 @Volatile private var stageStart=0L
 @Volatile private var audioMs=0L
 @Volatile private var processedMs=0L
 @Volatile private var fraction: Float?=null
 @Volatile private var speakers=true
 private var job: Job?=null
 private var published: ProcessingSnapshot?=null

 fun start(scope: CoroutineScope) {
  job=scope.launch {
   while(isActive) { publish();delay(1000) }
  }
 }
 fun close() { job?.cancel();job=null }

 /** Starts a stage. [speakers]=false removes the speaker stage from the remaining-time estimate. */
 @Synchronized fun stage(next: ProcessingStage,durationMs: Long,speakers: Boolean=this.speakers) {
  val now=clock()
  stage?.let { previous -> if(previous!=next) completed+=ProcessingEta.Completed(previous,now-stageStart) }
  if(stage!=next) stageStart=now
  stage=next;audioMs=durationMs.coerceAtLeast(0);processedMs=0;fraction=if(durationMs>0) 0f else null;this.speakers=speakers
 }
 /** Audio processed by the current stage, in milliseconds of the original recording. */
 fun processed(ms: Long,totalMs: Long=-1) {
  if(totalMs>0) audioMs=totalMs
  val total=audioMs;processedMs=ms.coerceIn(0,total.coerceAtLeast(0))
  fraction=if(total>0) (processedMs.toDouble()/total).toFloat() else null
 }
 /** For stages that count work units instead of audio time (native diarization chunks). */
 fun units(done: Int,total: Int) {
  if(total<=0) return
  val f=(done.toFloat()/total).coerceIn(0f,1f);fraction=f;processedMs=(audioMs*f).toLong()
 }
 /** The stage continues, but its share is not measurable (for example speaker refinement). */
 fun indeterminate() { fraction=null }

 @Synchronized fun snapshot(): ProcessingSnapshot? {
  val current=stage?:return null
  val remaining=ProcessingEta.stagesFor(speakers).dropWhile { it!=current }
  val estimate=eta.estimate(current,fraction,clock()-stageStart,audioMs,completed.toList(),remaining)
  return ProcessingSnapshot(current,fraction,processedMs,audioMs,estimate)
 }
 private suspend fun publish() {
  val next=snapshot()?:return
  if(next==published) return
  try { worker.setProgress(workDataOf(*next.toMap().map { it.key to it.value }.toTypedArray())) }
  catch(e: kotlinx.coroutines.CancellationException) { throw e }
  catch(_: Exception) { return /* Progress is advisory; retry on the next tick. */ }
  published=next
 }
}
