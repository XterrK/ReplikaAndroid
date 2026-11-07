package ru.replika.domain

/** Bounded gain for extremely low-level recognition input. Original PCM is never rewritten.
 *
 * A recording with a peak at or above -40 dBFS is passed through exactly. This is a
 * level repair, not whisper synthesis, denoising or recovery of inaudible phonemes.
 * One fixed gain per recording avoids pumping at pauses and changing speaker timbre.
 */
object QuietAudioGain {
 const val TRIGGER_PEAK=.01f
 const val TARGET_PEAK=.1f
 const val MAX_GAIN=20f
 const val SILENCE_FLOOR=1e-6f

 fun forPeak(peak: Float): Float =
  if(!peak.isFinite() || peak<=SILENCE_FLOOR || peak>=TRIGGER_PEAK) 1f
  else minOf(MAX_GAIN,TARGET_PEAK/peak)

 /** Only temporary VAD/ASR arrays belong here; waveform, playback and diarization stay original. */
 fun apply(samples: FloatArray,gain: Float) {
  require(gain.isFinite() && gain in 1f..MAX_GAIN)
  if(gain==1f) return
  for(i in samples.indices) samples[i]*=gain
 }
}
