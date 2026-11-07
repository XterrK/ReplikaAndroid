package ru.replika.domain

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.sin

/**
 * Decides whether to run speech enhancement (GTCRN) before the pipeline.
 *
 * Stand (docs/STEP_15_NOISE.md): enhancement helps only for steady broadband noise
 * (white noise 10 dB: raw WER 31.2% -> 25.6%, DER0 56.1% -> 40.1%) and hurts clean speech,
 * babble and telephone audio. So it runs only when the quiet frames are loud relative to the
 * speech (SNR below [MAX_SNR_DB]) AND their spectrum is flat (steady hiss/fan, not voices).
 * On the stand the rule fires on every white-noise file and on no clean, babble or phone file.
 * Mirrors the stand script in tools/eval (noise features).
 */
object NoiseGate {
 const val FRAME=512
 const val MAX_SNR_DB=20.0
 const val MIN_FLATNESS=0.40
 const val MAX_FLATNESS=0.95 // ~1.0 means digital silence or dither, not noise
 const val MAX_ANALYSED_FRAMES=18_750 // first ~10 minutes at 16 kHz
 const val MAX_SPECTRA=200
 private const val BIN_FROM=8
 private const val BIN_TO=200

 data class Decision(val snrDb: Double,val flatness: Double,val apply: Boolean)

 private val window=DoubleArray(FRAME) { 0.5-0.5*cos(2*PI*it/(FRAME-1)) }

 fun energy(frame: FloatArray,offset: Int=0): Double {
  var sum=0.0
  for(i in 0 until FRAME) { val v=frame[offset+i]*window[i];sum+=v*v }
  return sum/FRAME+1e-12
 }

 /** Spectral flatness (geometric / arithmetic mean of power) over ~250 Hz..6 kHz. */
 fun flatness(frame: FloatArray,offset: Int=0): Double {
  var logSum=0.0;var sum=0.0
  for(k in BIN_FROM until BIN_TO) {
   var re=0.0;var im=0.0
   for(n in 0 until FRAME) {
    val v=frame[offset+n]*window[n];val a=2*PI*k*n/FRAME
    re+=v*cos(a);im-=v*sin(a)
   }
   val p=re*re+im*im+1e-12
   logSum+=ln(p);sum+=p
  }
  val bins=BIN_TO-BIN_FROM
  return exp(logSum/bins)/(sum/bins)
 }

 /** Indices of the quietest 10% and the loudest 25% frames, and the resulting SNR in dB. */
 fun snr(energies: DoubleArray): Pair<Double,IntArray> {
  require(energies.isNotEmpty())
  val order=energies.indices.sortedBy { energies[it] }
  val quiet=order.take(maxOf(1,energies.size/10))
  val loud=order.takeLast(maxOf(1,energies.size/4))
  val snr=10*log10(loud.sumOf { energies[it] }/loud.size/(quiet.sumOf { energies[it] }/quiet.size))
  return snr to quiet.toIntArray()
 }

 fun decide(snrDb: Double,flatnessMedian: Double)=Decision(snrDb,flatnessMedian,
  snrDb<MAX_SNR_DB && flatnessMedian>MIN_FLATNESS && flatnessMedian<MAX_FLATNESS)

 fun median(values: List<Double>): Double {
  require(values.isNotEmpty());val s=values.sorted();val m=s.size/2
  return if(s.size%2==1) s[m] else (s[m-1]+s[m])/2
 }
}
