package ru.replika.domain

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/** Step 6: bounded-memory diarization of long recordings (pure part).
 *
 * Long audio is split into equal windows no longer than [Config.windowMs] with an exact
 * [Config.overlapMs] overlap. Every window gets the unchanged SD + C2 path on its own PCM
 * (read from disk), then each final local speaker becomes one centroid: the duration-
 * weighted mean of its unit clean-window embeddings. Centroids are clustered globally with
 * average linkage on cosine distance and a cannot-link between labels of the same window;
 * windows are stitched at one cut per overlap, the instant nearest to the midpoint between
 * window centres where neither window has speech (else the midpoint itself).
 *
 * Python twin: tools/eval/long_diar.py (plan_windows, window_centroids, global_clusters,
 * resolve_labels, stitch_points, stitch). Recordings not longer than [Config.minDurationMs]
 * never reach this object: the caller keeps the original single-pass path byte for byte.
 */
object ChunkedDiarization {
 data class Config(val minDurationMs: Long=15*60_000L,val windowMs: Long=10*60_000L,val overlapMs: Long=30_000L,
  val globalTau: Double=.5,val maxSpeakers: Int=8,val stitchSearchMs: Long=10_000L) {
  init {
   require(windowMs>0 && overlapMs>=0 && overlapMs<windowMs) { "overlap must be shorter than the window" }
   require(minDurationMs>=windowMs) { "only recordings longer than one window are chunked" }
   require(globalTau.isFinite() && globalTau> -1 && globalTau<1 && maxSpeakers in 1..20 && stitchSearchMs>=0)
  }
  fun asMap(): Map<String,Any?> = linkedMapOf("min_duration_ms" to minDurationMs,"window_ms" to windowMs,
   "overlap_ms" to overlapMs,"global_tau" to globalTau,"max_speakers" to maxSpeakers,"stitch_search_ms" to stitchSearchMs)
 }
 data class Window(val startMs: Long,val endMs: Long) { val durationMs get()=endMs-startMs }
 class Centroid(val window: Int,val label: Int,val vector: DoubleArray,val speechMs: Long)

 fun isChunked(durationMs: Long,config: Config): Boolean = durationMs>config.minDurationMs

 /** Equal windows no longer than W that cover [0,D) with overlap exactly O. */
 fun planWindows(durationMs: Long,config: Config): List<Window> {
  require(durationMs>=0)
  if(!isChunked(durationMs,config)) return listOf(Window(0,durationMs))
  val w=config.windowMs;val o=config.overlapMs
  val count=ceilDiv(durationMs-o,w-o)
  val length=ceilDiv(durationMs+(count-1)*o,count)
  val step=length-o
  return (0 until count).map { k ->
   val start=k*step
   Window(start,if(k==count-1) durationMs else min(durationMs,start+length))
  }
 }
 private fun ceilDiv(a: Long,b: Long): Long = -Math.floorDiv(-a,b)

 private fun unit(values: DoubleArray): DoubleArray? {
  val norm=sqrt(WindowSpeakerRefiner.sum(DoubleArray(values.size) { values[it]*values[it] }))
  if(!norm.isFinite() || norm<=1e-12) return null
  return DoubleArray(values.size) { values[it]/norm }
 }

 /** One centroid per final local label that owns at least one measured clean window.
  * A window belongs to the label covering most of its span (ties: smaller label). */
 fun windowCentroids(window: Int,turns: List<Turn>,measured: List<SpeakerRefiner.EmbeddingWindow>): List<Centroid> {
  val sums=sortedMapOf<Int,DoubleArray>()
  for(item in measured) {
   val cover=sortedMapOf<Int,Long>()
   for(turn in turns) {
    val overlap=min(turn.endMs,item.endMs)-max(turn.startMs,item.startMs)
    if(overlap>0) cover[turn.speaker]=(cover[turn.speaker]?:0L)+overlap
   }
   if(cover.isEmpty()) continue
   val label=cover.entries.minWith(compareByDescending<Map.Entry<Int,Long>> { it.value }.thenBy { it.key }).key
   val vector=unit(item.embedding)?:continue
   val weight=(item.endMs-item.startMs).toDouble()
   val acc=sums.getOrPut(label) { DoubleArray(vector.size) }
   for(i in vector.indices) acc[i]+=vector[i]*weight
  }
  val speech=mutableMapOf<Int,Long>()
  for(turn in turns) speech[turn.speaker]=(speech[turn.speaker]?:0L)+turn.endMs-turn.startMs
  return sums.mapNotNull { (label,acc) -> unit(acc)?.let { Centroid(window,label,it,speech[label]?:0L) } }
 }

 /** Average linkage over cosine distance with cannot-link inside a window. Merges the closest
  * allowed pair while distance <= 1 - tau, then keeps merging the closest allowed pair while
  * more than maxSpeakers remain. Ties: smallest (i, j). Labels are 0..K-1 in (window, label) order. */
 fun globalClusters(centroids: List<Centroid>,config: Config): IntArray {
  val n=centroids.size
  if(n==0) return IntArray(0)
  val dist=Array(n) { DoubleArray(n) }
  for(i in 0 until n) for(j in 0 until i) {
   val d=(1.0-WindowSpeakerRefiner.cosine(centroids[i].vector,centroids[j].vector)).coerceIn(0.0,2.0)
   dist[i][j]=d;dist[j][i]=d
  }
  val members=sortedMapOf<Int,MutableList<Int>>()
  val windows=mutableMapOf<Int,MutableSet<Int>>()
  for(i in 0 until n) { members[i]=mutableListOf(i);windows[i]=mutableSetOf(centroids[i].window) }
  val cut=1.0-config.globalTau
  while(members.size>1) {
   var bestD=Double.NaN;var bestA=-1;var bestB=-1
   val keys=members.keys.toList()
   for(x in keys.indices) for(y in x+1 until keys.size) {
    val a=keys[x];val b=keys[y]
    if(windows.getValue(a).any { it in windows.getValue(b) }) continue
    val d=dist[a][b]
    if(bestA<0 || d<bestD) { bestD=d;bestA=a;bestB=b }
   }
   if(bestA<0) break
   if(bestD>cut && members.size<=config.maxSpeakers) break
   val na=members.getValue(bestA).size.toDouble();val nb=members.getValue(bestB).size.toDouble()
   for(c in members.keys) if(c!=bestA && c!=bestB) {
    val value=(na*dist[bestA][c]+nb*dist[bestB][c])/(na+nb)
    dist[bestA][c]=value;dist[c][bestA]=value
   }
   members.getValue(bestA).addAll(members.remove(bestB)!!)
   windows.getValue(bestA).addAll(windows.remove(bestB)!!)
  }
  val owner=IntArray(n)
  for((key,items) in members) for(item in items) owner[item]=key
  val order=(0 until n).sortedWith(compareBy<Int> { centroids[it].window }.thenBy { centroids[it].label })
  val stable=linkedMapOf<Int,Int>()
  for(i in order) stable.getOrPut(owner[i]) { stable.size }
  return IntArray(n) { stable.getValue(owner[it]) }
 }

 /** Global label for every local label; a label without centroid follows the temporally
  * nearest turn with a centroid in its window, else the global cluster with most speech. */
 fun resolveLabels(localTurns: List<List<Turn>>,centroids: List<Centroid>,labels: IntArray): List<Map<Int,Int>> {
  val mapping=List(localTurns.size) { mutableMapOf<Int,Int>() }
  val speech=sortedMapOf<Int,Long>()
  for((i,c) in centroids.withIndex()) { mapping[c.window][c.label]=labels[i];speech[labels[i]]=(speech[labels[i]]?:0L)+c.speechMs }
  val dominant=speech.entries.minWithOrNull(compareByDescending<Map.Entry<Int,Long>> { it.value }.thenBy { it.key })?.key?:0
  for(k in localTurns.indices) {
   val known=localTurns[k].filter { it.speaker in mapping[k] }
   for(turn in localTurns[k]) {
    if(turn.speaker in mapping[k]) continue
    mapping[k][turn.speaker]=if(known.isEmpty()) dominant else {
     val near=known.minWith(compareBy<Turn> { abs((it.startMs+it.endMs)-(turn.startMs+turn.endMs)) }.thenBy { it.startMs })
     mapping[k].getValue(near.speaker)
    }
   }
  }
  return mapping
 }

 /** One cut per adjacent pair (absolute ms). Local turns are relative to their window. */
 fun stitchPoints(windows: List<Window>,localTurns: List<List<Turn>>,config: Config): List<Long> = (0 until windows.size-1).map { k ->
  val (s0,e0)=windows[k];val (s1,e1)=windows[k+1]
  val mid=(s0+e0+s1+e1)/4
  val lo=max(s1,mid-config.stitchSearchMs);val hi=min(e0,mid+config.stitchSearchMs)
  val busy=(localTurns[k].map { (it.startMs+s0) to (it.endMs+s0) }+localTurns[k+1].map { (it.startMs+s1) to (it.endMs+s1) })
   .sortedWith(compareBy<Pair<Long,Long>> { it.first }.thenBy { it.second })
  val merged=mutableListOf<LongArray>()
  for((a,b) in busy) {
   if(b<=lo || a>=hi) continue
   if(merged.isNotEmpty() && a<=merged.last()[1]) merged.last()[1]=max(merged.last()[1],b) else merged+=longArrayOf(a,b)
  }
  val free=mutableListOf<Pair<Long,Long>>();var cursor=lo
  for(span in merged) { if(span[0]>cursor) free+=cursor to span[0];cursor=max(cursor,span[1]) }
  if(cursor<hi) free+=cursor to hi
  var best: Long?=null
  for((a,b) in free) {
   val point=min(max(mid,a),b)
   if(b-a>=1 && (best==null || abs(point-mid)<abs(best-mid) || (abs(point-mid)==abs(best-mid) && point<best))) best=point
  }
  best?:mid
 }

 /** Clip each window's globally relabelled turns to its core and coalesce touching turns. */
 fun stitch(windows: List<Window>,localTurns: List<List<Turn>>,labels: List<Map<Int,Int>>,cuts: List<Long>): List<Turn> {
  val out=mutableListOf<Turn>()
  for((k,window) in windows.withIndex()) {
   val lo=if(k==0) window.startMs else cuts[k-1]
   val hi=if(k==windows.lastIndex) window.endMs else cuts[k]
   for(turn in localTurns[k]) {
    val a=max(turn.startMs+window.startMs,lo);val b=min(turn.endMs+window.startMs,hi)
    if(b>a) out+=Turn(a,b,labels[k].getValue(turn.speaker))
   }
  }
  val order=compareBy<Turn> { it.startMs }.thenBy { it.endMs }.thenBy { it.speaker }
  out.sortWith(order)
  val merged=mutableListOf<Turn>()
  for(turn in out) {
   var same=-1
   var i=merged.lastIndex
   while(i>max(-1,merged.size-9)) {
    if(merged[i].speaker==turn.speaker && merged[i].endMs>=turn.startMs) { same=i;break }
    i--
   }
   if(same>=0) merged[same]=Turn(merged[same].startMs,max(merged[same].endMs,turn.endMs),turn.speaker) else merged+=turn
  }
  return merged.sortedWith(order)
 }

}
