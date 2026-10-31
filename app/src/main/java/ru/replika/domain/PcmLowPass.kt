package ru.replika.domain
import kotlin.math.*
/** Causal windowed-sinc anti-alias FIR. Callers compensate delaySamples on the audio timeline. */
class PcmLowPass(inputRate: Int,outputRate: Int=16000) {
 val delaySamples=if(inputRate>outputRate) 31 else 0
 private val taps=if(delaySamples==0) doubleArrayOf(1.0) else DoubleArray(63) { i ->
  val k=i-delaySamples;val fc=0.45*outputRate/inputRate
  val sinc=if(k==0) 2*fc else sin(2*PI*fc*k)/(PI*k)
  sinc*(0.54-0.46*cos(2*PI*i/62))
 }.also { a -> val sum=a.sum();for(i in a.indices) a[i]/=sum }
 private val ring=FloatArray(taps.size);private var head=0
 fun accept(sample: Float): Float {
  ring[head]=sample;var value=0.0;var index=head
  for(i in taps.indices) { value+=taps[i]*ring[index];index--;if(index<0) index=ring.lastIndex }
  head=(head+1)%ring.size;return value.toFloat()
 }
}
