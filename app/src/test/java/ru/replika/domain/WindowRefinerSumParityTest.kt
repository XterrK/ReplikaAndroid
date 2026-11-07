package ru.replika.domain

import org.junit.Assert.assertEquals
import org.junit.Test
import kotlin.math.abs
import kotlin.random.Random

/** The primitive fsum must return exactly the bits of the original boxed implementation. */
class WindowRefinerSumParityTest {
 /** Verbatim copy of the pre-step-6 boxed implementation (reference only). */
 private fun boxedSum(values: Iterable<Double>): Double {
  val partials=mutableListOf<Double>()
  for(value in values) {
   var x=value;var next=0
   for(original in partials.toList()) {
    var y=original
    if(abs(x)<abs(y)) { val swap=x;x=y;y=swap }
    val high=x+y;val low=y-(high-x)
    if(low!=0.0) { partials[next]=low;next++ }
    x=high
   }
   while(partials.size>next) partials.removeAt(partials.lastIndex)
   partials+=x
  }
  if(partials.isEmpty()) return 0.0
  var n=partials.size-1;var high=partials[n];var low=0.0
  while(n>0) {
   val x=high;val y=partials[--n]
   high=x+y;low=y-(high-x)
   if(low!=0.0) break
  }
  if(n>0 && ((low<0 && partials[n-1]<0) || (low>0 && partials[n-1]>0))) {
   val y=low*2;val x=high+y
   if(y==x-high) high=x
  }
  return high
 }

 @Test fun primitiveSumIsBitIdenticalOnRandomAndAdversarialInputs() {
  val rnd=Random(20261107)
  val cases=mutableListOf<DoubleArray>()
  cases+=doubleArrayOf();cases+=doubleArrayOf(1.0);cases+=doubleArrayOf(1e308,1e308,-1e308)
  cases+=doubleArrayOf(1.0,1e100,1.0,-1e100);cases+=doubleArrayOf(.1,.2,.3,-.6)
  cases+=doubleArrayOf(1e16,1.0,-1e16,1e-16,2.0.let { it*0.5 })
  cases+=DoubleArray(40) { if(it%2==0) 1e20 else -1e20+it }
  repeat(3000) {
   val n=rnd.nextInt(1,700)
   val scale=Math.pow(10.0,rnd.nextInt(-30,30).toDouble())
   cases+=DoubleArray(n) {
    when(rnd.nextInt(4)) {
     0 -> rnd.nextDouble(-1.0,1.0)*scale
     1 -> rnd.nextDouble(-1.0,1.0)*rnd.nextDouble(-1.0,1.0)
     2 -> (if(rnd.nextBoolean()) 1 else -1)*Math.pow(2.0,rnd.nextInt(-60,60).toDouble())
     else -> rnd.nextDouble()*1e-3
    }
   }
  }
  for(values in cases) {
   val expected=boxedSum(values.toList())
   assertEquals(expected.toRawBits(),WindowSpeakerRefiner.sum(values).toRawBits())
  }
 }

 @Test fun cosineMatchesBoxedProductsSum() {
  val rnd=Random(5)
  repeat(500) {
   val a=DoubleArray(512) { rnd.nextDouble(-1.0,1.0) };val b=DoubleArray(512) { rnd.nextDouble(-1.0,1.0) }
   val expected=boxedSum(a.indices.map { a[it]*b[it] }).coerceIn(-1.0,1.0)
   assertEquals(expected.toRawBits(),WindowSpeakerRefiner.cosine(a,b).toRawBits())
  }
 }
}
