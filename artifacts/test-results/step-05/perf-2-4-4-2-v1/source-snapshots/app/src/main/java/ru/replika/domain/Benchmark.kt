package ru.replika.domain

import java.text.Normalizer
import java.util.Locale
import kotlin.math.*

object Benchmark {
 fun normalize(s: String)=Normalizer.normalize(s.lowercase(Locale.ROOT).replace('ё','е'),Normalizer.Form.NFC).replace(Regex("[^\\p{L}\\p{N}\\s]")," ").trim().replace(Regex("\\s+")," ")
 fun <T> distance(a: List<T>,b: List<T>): Int {
  var previous=IntArray(b.size+1) { it }
  a.forEachIndexed { i,x -> val next=IntArray(b.size+1);next[0]=i+1
   b.forEachIndexed { j,y -> next[j+1]=minOf(next[j]+1,previous[j+1]+1,previous[j]+if(x==y) 0 else 1) };previous=next
  };return previous[b.size]
 }
 fun wer(ref: String,hyp: String): Double? { val r=normalize(ref).split(' ').filter(String::isNotEmpty);val h=normalize(hyp).split(' ').filter(String::isNotEmpty);return if(r.isEmpty()) null else distance(r,h).toDouble()/r.size }
 fun cer(ref: String,hyp: String): Double? { val r=normalize(ref).replace(" ","").toList();val h=normalize(hyp).replace(" ","").toList();return if(r.isEmpty()) null else distance(r,h).toDouble()/r.size }
 // Hungarian minimum assignment, square matrix. Padded zero rows/columns allow unmatched speakers.
 private fun assignment(weights: Array<DoubleArray>): IntArray {
  val n=weights.size;if(n==0) return intArrayOf()
  val u=DoubleArray(n+1);val v=DoubleArray(n+1);val p=IntArray(n+1);val way=IntArray(n+1)
  for(i in 1..n) {
   p[0]=i;var j0=0;val minv=DoubleArray(n+1) { Double.POSITIVE_INFINITY };val used=BooleanArray(n+1)
   do {
    used[j0]=true;val i0=p[j0];var delta=Double.POSITIVE_INFINITY;var j1=0
    for(j in 1..n) if(!used[j]) { val cur= -weights[i0-1][j-1]-u[i0]-v[j];if(cur<minv[j]) { minv[j]=cur;way[j]=j0 };if(minv[j]<delta) { delta=minv[j];j1=j } }
    for(j in 0..n) if(used[j]) { u[p[j]]+=delta;v[j]-=delta } else minv[j]-=delta
    j0=j1
   } while(p[j0]!=0)
   do { val j1=way[j0];p[j0]=p[j1];j0=j1 } while(j0!=0)
  }
  val ans=IntArray(n);for(j in 1..n) ans[p[j]-1]=j-1;return ans
 }
 data class Der(val missMs: Double,val falseAlarmMs: Double,val confusionMs: Double,val referenceSpeakerMs: Double) {
  val rate: Double? get()=if(referenceSpeakerMs==0.0) null else (missMs+falseAlarmMs+confusionMs)/referenceSpeakerMs
 }
 /** Zero collar, includes overlap, all time from 0 through duration, optimal global speaker permutation. */
 fun der(reference: List<Turn>,hypothesis: List<Turn>,durationMs: Long): Der {
  require(durationMs>0)
  val ref=reference.filter { it.endMs>it.startMs };val hyp=hypothesis.filter { it.endMs>it.startMs }
  val rIds=ref.map { it.speaker }.distinct();val hIds=hyp.map { it.speaker }.distinct();val n=max(rIds.size,hIds.size)
  val w=Array(n) { DoubleArray(n) }
  val boundaries=(listOf(0L,durationMs)+(ref+hyp).flatMap { listOf(it.startMs.coerceIn(0,durationMs),it.endMs.coerceIn(0,durationMs)) }).distinct().sorted()
  data class Frame(val ms: Double,val r: Set<Int>,val h: Set<Int>)
  val frames=boundaries.zipWithNext().map { (a,b) ->
   val r=ref.filter { it.startMs<b && it.endMs>a }.map { rIds.indexOf(it.speaker) }.toSet()
   val h=hyp.filter { it.startMs<b && it.endMs>a }.map { hIds.indexOf(it.speaker) }.toSet()
   val d=(b-a).toDouble();for(i in r) for(j in h) w[i][j]+=d
   Frame(d,r,h)
  }
  val map=assignment(w);var miss=0.0;var fa=0.0;var confusion=0.0;var total=0.0
  for(f in frames) {
   val correct=f.r.count { map[it] in f.h };miss+=max(0,f.r.size-f.h.size)*f.ms;fa+=max(0,f.h.size-f.r.size)*f.ms;confusion+=(min(f.r.size,f.h.size)-correct)*f.ms;total+=f.r.size*f.ms
  };return Der(miss,fa,confusion,total)
 }
}
