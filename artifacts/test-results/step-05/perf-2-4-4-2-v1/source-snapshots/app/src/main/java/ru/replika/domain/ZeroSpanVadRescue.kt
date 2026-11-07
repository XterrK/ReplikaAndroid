package ru.replika.domain

import kotlin.math.sqrt

/** A second detector pass after zero speech spans. Its gain must never reach ASR or stored PCM. */
object ZeroSpanVadRescue {
 const val TARGET_RMS=.02
 const val MAX_GAIN=20f
 const val PEAK_HEADROOM=.95
 const val MIN_GAIN_RATIO=1.01

 data class Decision(val shouldRetry: Boolean,val detectorGain: Float,val reason: String)

 private fun skipReason(primarySpanCount: Int,peak: Float,recognitionGain: Float): String? = when {
  primarySpanCount>0 -> "primary_nonempty"
  primarySpanCount<0 -> "invalid_primary_span_count"
  !peak.isFinite() || peak<0f -> "invalid_peak"
  peak<=QuietAudioGain.SILENCE_FLOOR -> "silence_or_near_silence"
  !recognitionGain.isFinite() || recognitionGain<1f || recognitionGain>MAX_GAIN -> "invalid_recognition_gain"
  recognitionGain>=MAX_GAIN -> "gain_at_cap"
  else -> null
 }

 /** Nonempty primary VAD and digital silence do not incur even an RMS file scan. */
 fun needsRms(primarySpanCount: Int,peak: Float,recognitionGain: Float): Boolean =
  skipReason(primarySpanCount,peak,recognitionGain)==null

 fun decide(primarySpanCount: Int,peak: Float,recognitionGain: Float,rms: Double?): Decision {
  val unchanged=recognitionGain.takeIf { it.isFinite() && it in 1f..MAX_GAIN }?:1f
  skipReason(primarySpanCount,peak,recognitionGain)?.let { return Decision(false,unchanged,it) }
  if(rms==null || !rms.isFinite() || rms<=0.0 || rms>peak.toDouble()*1.00001)
   return Decision(false,unchanged,"invalid_or_empty_rms")
  val gain=maxOf(recognitionGain.toDouble(),minOf(TARGET_RMS/rms,MAX_GAIN.toDouble(),PEAK_HEADROOM/peak.toDouble()))
  if(gain<=recognitionGain*MIN_GAIN_RATIO) return Decision(false,unchanged,"no_meaningful_gain")
  return Decision(true,gain.toFloat(),"retry_requested")
 }

 /** Constant memory, double-precision sum; input values are read without altering their bits. */
 class RmsAccumulator {
  var samples=0L;private set
  private var squares=0.0
  private var valid=true
  fun add(value: Float) {
   samples++
   if(!value.isFinite()) valid=false
   else { val v=value.toDouble();squares+=v*v }
  }
  fun value(): Double? = if(valid && samples>0 && squares.isFinite()) sqrt(squares/samples) else null
 }
}
