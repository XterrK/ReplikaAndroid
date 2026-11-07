package ru.replika.domain

import kotlin.math.roundToLong

/** User-facing processing stages, in pipeline order. */
enum class ProcessingStage(val title: String) {
 DECODING("Декодирование"),
 SPEECH("Поиск речи"),
 SPEAKERS("Говорящие"),
 RECOGNITION("Распознавание");
 companion object { fun fromName(name: String?)=entries.firstOrNull { it.name==name } }
}

/**
 * One progress sample published by the Worker through WorkManager.setProgress.
 * [fraction] is the share of the audio duration this stage has processed, or null when the stage
 * cannot measure it (for example the speaker-refinement pass). [etaMs] covers all remaining stages.
 */
data class ProcessingSnapshot(val stage: ProcessingStage,val fraction: Float?,val processedMs: Long,val audioMs: Long,val etaMs: Long?) {
 val percent: Int? get()=fraction?.let { (it*100).toInt().coerceIn(0,100) }
 fun toMap(): Map<String,Any> = mapOf(KEY_STAGE to stage.name,KEY_FRACTION to (fraction?:-1f),
  KEY_PROCESSED to processedMs,KEY_AUDIO to audioMs,KEY_ETA to (etaMs?:-1L))
 companion object {
  const val KEY_STAGE="progressStage"
  const val KEY_FRACTION="progressFraction"
  const val KEY_PROCESSED="progressProcessedMs"
  const val KEY_AUDIO="progressAudioMs"
  const val KEY_ETA="progressEtaMs"
  fun fromValues(values: Map<String,Any?>): ProcessingSnapshot? {
   val stage=ProcessingStage.fromName(values[KEY_STAGE] as? String)?:return null
   val fraction=(values[KEY_FRACTION] as? Number)?.toFloat()?.takeIf { it>=0f }?.coerceAtMost(1f)
   val eta=(values[KEY_ETA] as? Number)?.toLong()?.takeIf { it>=0 }
   return ProcessingSnapshot(stage,fraction,(values[KEY_PROCESSED] as? Number)?.toLong()?:0,(values[KEY_AUDIO] as? Number)?.toLong()?:0,eta)
  }
 }
}

/**
 * Remaining-time estimate. The current stage is extrapolated from its own measured speed once it
 * has done enough work; later stages use per-stage priors (processing ms per audio ms) scaled by
 * how fast this device actually was on the work already done. No priors claim device speed: they
 * only order stages until real measurements exist.
 */
class ProcessingEta(private val priors: Map<ProcessingStage,Double> = DEFAULT_PRIORS) {
 data class Completed(val stage: ProcessingStage,val elapsedMs: Long)

 fun estimate(stage: ProcessingStage,fraction: Float?,stageElapsedMs: Long,audioMs: Long,
              completed: List<Completed>,remaining: List<ProcessingStage>): Long? {
  if(audioMs<=0) return null
  val f=fraction?.toDouble()?.coerceIn(0.0,1.0)
  val measured=f!=null && f>=MIN_FRACTION && stageElapsedMs>=MIN_ELAPSED_MS
  // Calibration: actual / prior time over the ML stages measured so far. Decoding speed is
  // container I/O and resampling (48 kHz stereo decodes several times slower than 16 kHz mono)
  // and does not predict VAD/diarization/ASR speed, so it never calibrates later stages.
  val ml=completed.filter { it.stage!=ProcessingStage.DECODING }
  var actual=ml.sumOf { it.elapsedMs.toDouble() }
  var expected=ml.sumOf { prior(it.stage)*audioMs }
  if(measured && stage!=ProcessingStage.DECODING) { actual+=stageElapsedMs;expected+=prior(stage)*audioMs*f!! }
  val calibration=if(expected>=MIN_CALIBRATION_BASIS_MS && actual>0) (actual/expected).coerceIn(MIN_CALIBRATION,MAX_CALIBRATION) else 1.0
  val current=if(measured) stageElapsedMs*(1-f!!)/f
   else (prior(stage)*audioMs*calibration*(1-(f?:0.0))).coerceAtLeast(0.0)
  val future=remaining.filter { it!=stage }.sumOf { prior(it)*audioMs*calibration }
  return (current+future).roundToLong().coerceAtLeast(0)
 }
 private fun prior(stage: ProcessingStage)=priors[stage]?:0.0

 companion object {
  /** Rough shares from the step-5 telemetry (10 min phone file: SD+refiner ≫ ASR ≫ VAD, decode). */
  val DEFAULT_PRIORS=mapOf(ProcessingStage.DECODING to .01,ProcessingStage.SPEECH to .02,
   ProcessingStage.SPEAKERS to .45,ProcessingStage.RECOGNITION to .10)
  const val MIN_FRACTION=.02
  const val MIN_ELAPSED_MS=3000L
  const val MIN_CALIBRATION_BASIS_MS=1000.0
  const val MIN_CALIBRATION=.2
  const val MAX_CALIBRATION=8.0
  fun stagesFor(speakers: Boolean)=ProcessingStage.entries.filter { speakers || it!=ProcessingStage.SPEAKERS }

  /** "меньше минуты", "≈ 12 мин", "≈ 1 ч 05 мин". Rounded up to whole minutes. */
  fun format(etaMs: Long?): String? {
   if(etaMs==null || etaMs<0) return null
   if(etaMs<60_000) return "меньше минуты"
   val minutes=(etaMs+59_999)/60_000
   return if(minutes<60) "≈ $minutes мин" else String.format(java.util.Locale.ROOT,"≈ %d ч %02d мин",minutes/60,minutes%60)
  }
 }
}
