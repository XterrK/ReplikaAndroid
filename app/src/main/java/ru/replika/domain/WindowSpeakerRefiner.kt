package ru.replika.domain

import java.math.BigInteger
import java.util.BitSet
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/** Pure port of window_overcluster.py SHA23cffbba55b75e69695a2b508093505dcad74c804cb7913fd77356b67196acd4.
 * No model/audio/gold/text input. All speech activity comes from original native intervals.
 * Nearest-neighbor-chain / stable union-find relabel follows SciPy1.18.1 source contract,
 * commit e4e854eaa8f18d807cd3496028e257e36caa93cc. No SciPy runtime dependency.
 * The adapted hierarchy algorithm retains its BSD3notice in scipy-LICENSE.txt alongside this draft.
 */
object WindowSpeakerRefiner {
 data class Config(val tau: Double=.65,val method: String="complete",val gridMs: Long=125,
  val maxSpeakers: Int=8,val reassignSmall: Boolean=false,val minClusterMs: Long=2000,
  val minClusterFraction: Double=.03,val minimumReassignmentSimilarity: Double?=null,
  val smooth: Boolean=true,val smoothMs: Long=500) {
  fun asMap(): Map<String,Any?> = linkedMapOf("tau" to tau,"method" to method,"grid_ms" to gridMs,
   "max_speakers" to maxSpeakers,"reassign_small" to reassignSmall,"min_cluster_ms" to minClusterMs,
   "min_cluster_fraction" to minClusterFraction,"minimum_reassignment_similarity" to minimumReassignmentSimilarity,
   "smooth" to smooth,"smooth_ms" to smoothMs)
 }
 data class Result(val turns: List<Turn>,val accepted: Boolean,val diagnostics: Map<String,Any?>)
 private data class Key(val start: Long,val end: Long,val speaker: Int)
 private data class Observation(val vector: DoubleArray,val weight: Long)
 private data class Interval(val start: Long,val end: Long)
 private data class Row(val left: Int,val right: Int,val distance: Double,val size: Int,val originalIndex: Int)
 private data class Hierarchy(val labels: List<Int>,val centroids: Map<Int,DoubleArray?>)
 private val keyOrder=compareBy<Key> { it.start }.thenBy { it.end }.thenBy { it.speaker }
 private val turnOrder=compareBy<Turn> { it.startMs }.thenBy { it.endMs }.thenBy { it.speaker }
 private fun validate(config: Config,duration: Long) {
  require(duration>=0)
  require(config.tau.isFinite() && config.tau > -1 && config.tau < 1)
  require(config.method in setOf("complete","average"))
  require(config.gridMs in 1..1000 && config.maxSpeakers in 1..8)
  require(config.minClusterMs>=0 && config.smoothMs>=0 && config.minClusterFraction.isFinite() && config.minClusterFraction in 0.0..1.0)
  require(config.minimumReassignmentSimilarity==null || (config.minimumReassignmentSimilarity.isFinite() && config.minimumReassignmentSimilarity in -1.0..1.0))
 }
 /** Nonoverlapping expansion summation, with half-even final correction as in math.fsum.
  * Primitive arrays, no boxing. Partials are rewritten only at indices at or below the one
  * being read, so reading in place equals the former snapshot loop over a boxed list; the
  * correctly rounded result is bit-identical (WindowRefinerSumParityTest). */
 internal fun sum(values: DoubleArray,count: Int=values.size): Double {
  var partials=DoubleArray(8);var size=0
  for(index in 0 until count) {
   var x=values[index];var next=0
   for(j in 0 until size) {
    var y=partials[j]
    if(abs(x)<abs(y)) { val swap=x;x=y;y=swap }
    val high=x+y;val low=y-(high-x)
    if(low!=0.0) { partials[next]=low;next++ }
    x=high
   }
   size=next
   if(size==partials.size) partials=partials.copyOf(size*2)
   partials[size++]=x
  }
  if(size==0) return 0.0
  var n=size-1;var high=partials[n];var low=0.0
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
 private fun norm(values: DoubleArray): Double {
  if(values.isEmpty()) return 0.0
  if(values.size==1) return abs(values[0])
  if(values.size==2) return Math.hypot(values[0],values[1])
  val scale=values.maxOf { abs(it) }
  if(scale==0.0) return 0.0
  return scale*sqrt(sum(DoubleArray(values.size) { val value=values[it]/scale;value*value }))
 }
 private fun unit(values: DoubleArray): DoubleArray? {
  if(values.isEmpty() || values.any { !it.isFinite() }) return null
  val scale=values.maxOf { abs(it) }
  if(scale==0.0) return null
  val length=norm(values)
  if(length.isFinite() && length>0) return DoubleArray(values.size) { values[it]/length }
  val scaled=DoubleArray(values.size) { values[it]/scale }
  val normalized=norm(scaled)
  return DoubleArray(values.size) { scaled[it]/normalized }
 }
 private fun equivalent(a: DoubleArray,b: DoubleArray): Boolean = a.size==b.size && a.indices.all { a[it]==b[it] }
 internal fun cosine(a: DoubleArray,b: DoubleArray): Double {
  val products=DoubleArray(a.size)
  for(i in a.indices) products[i]=a[i]*b[i]
  return sum(products).coerceIn(-1.0,1.0)
 }
 private fun mean(observations: List<Observation>): DoubleArray? {
  if(observations.isEmpty()) return null
  val total=sum(DoubleArray(observations.size) { observations[it].weight.toDouble() })
  val column=DoubleArray(observations.size)
  val result=DoubleArray(observations.first().vector.size) { i ->
   for(j in observations.indices) column[j]=observations[j].vector[i]*(observations[j].weight.toDouble()/total)
   sum(column)
  }
  return if(norm(result)<=1e-12) null else unit(result)
 }

 private fun union(intervals: List<Interval>): List<Interval> {
  val result=mutableListOf<Interval>()
  for(value in intervals.sortedWith(compareBy<Interval> { it.start }.thenBy { it.end })) {
   val previous=result.lastOrNull()
   if(previous!=null && value.start<=previous.end) result[result.lastIndex]=Interval(previous.start,max(previous.end,value.end)) else result+=value
  }
  return result
 }
 private fun coalesce(turns: List<Turn>): MutableList<Turn> {
  val result=mutableListOf<Turn>()
  for(speaker in turns.map { it.speaker }.distinct().sorted()) result+=union(turns.filter { it.speaker==speaker }.map { Interval(it.startMs,it.endMs) }).map { Turn(it.start,it.end,speaker) }
  return result.sortedWith(turnOrder).toMutableList()
 }
 private fun activity(turns: List<Turn>)=union(turns.map { Interval(it.startMs,it.endMs) })
 private fun speakerTime(turns: List<Turn>): BigInteger {
  var result=BigInteger.ZERO
  for(speaker in turns.map { it.speaker }.distinct()) for(interval in union(turns.filter { it.speaker==speaker }.map { Interval(it.startMs,it.endMs) })) result=result.add(BigInteger.valueOf(interval.end-interval.start))
  return result
 }
 private fun indices(bits: BitSet): List<Int> {
  val result=mutableListOf<Int>();var i=bits.nextSetBit(0)
  while(i>=0) { result+=i;i=bits.nextSetBit(i+1) }
  return result
 }
 /** Same mutual-neighbor preference, stable distance sort, and union-find label correction as SciPy. */
 private fun linkage(vectors: List<DoubleArray>,method: String): List<Row> {
  val n=vectors.size
  if(n<2) return emptyList()
  val distances=Array(n) { DoubleArray(n) }
  for(i in 0 until n) for(j in 0 until i) { val d=(1-cosine(vectors[i],vectors[j])).coerceIn(0.0,2.0);distances[i][j]=d;distances[j][i]=d }
  val size=IntArray(n) { 1 };val chain=IntArray(n);var length=0;var y=0;val raw=mutableListOf<Row>()
  for(k in 0 until n-1) {
   if(length==0) { length=1;chain[0]=(0 until n).first { size[it]>0 } }
   var x: Int;var current: Double
   while(true) {
    x=chain[length-1]
    if(length>1) { y=chain[length-2];current=distances[x][y] } else current=Double.POSITIVE_INFINITY
    for(i in 0 until n) if(size[i]>0 && i!=x && distances[x][i]<current) { current=distances[x][i];y=i }
    if(length>1 && y==chain[length-2]) break
    check(length<n) { "invalid nearest-neighbor chain" };chain[length++]=y
   }
   length-=2
   if(x>y) { val swap=x;x=y;y=swap }
   val nx=size[x];val ny=size[y]
   raw+=Row(x,y,current,nx+ny,k);size[x]=0;size[y]=nx+ny
   for(i in 0 until n) if(size[i]>0 && i!=y) {
    val d=if(method=="complete") max(distances[i][x],distances[i][y]) else (nx*distances[i][x]+ny*distances[i][y])/(nx+ny)
    distances[i][y]=d;distances[y][i]=d
   }
  }
  val parent=IntArray(2*n-1) { it };val counts=IntArray(2*n-1) { 1 }
  fun find(value: Int): Int { var x=value;while(parent[x]!=x) x=parent[x];var p=value;while(parent[p]!=x) { val next=parent[p];parent[p]=x;p=next };return x }
  return raw.sortedWith(compareBy<Row> { it.distance }.thenBy { it.originalIndex }).mapIndexed { i,row ->
   val a=find(row.left);val b=find(row.right);val label=n+i;val count=counts[a]+counts[b]
   parent[a]=label;parent[b]=label;counts[label]=count
   Row(min(a,b),max(a,b),row.distance,count,i)
  }
 }
 private fun cluster(windows: List<SpeakerRefiner.EmbeddingWindow>,vectors: List<DoubleArray>,config: Config,diagnostic: MutableMap<String,Any?>): Hierarchy {
  val n=windows.size;val tree=linkage(vectors,config.method)
  diagnostic["scipy_version"]="1.18.1"
  diagnostic["hierarchy_backend"]="pure Kotlin; scipy_version denotes source algorithm contract, not runtime"
  diagnostic["cut_distance"]=1-config.tau;diagnostic["cut_inclusive"]=true;diagnostic["linkage_method"]=config.method
  diagnostic["canonical_window_order"]="start_ms, end_ms, original speaker"
  diagnostic["linkage_tree"]=tree.map { listOf(it.left.toDouble(),it.right.toDouble(),it.distance,it.size.toDouble()) }
  val leaves=arrayOfNulls<BitSet>(2*n-1)
  for(i in 0 until n) leaves[i]=BitSet(n).also { it.set(i) }
  val parent=IntArray(n) { it }
  fun find(value: Int): Int { var x=value;while(parent[x]!=x) x=parent[x];var p=value;while(parent[p]!=x) { val next=parent[p];parent[p]=x;p=next };return x }
  for((i,row) in tree.withIndex()) {
   val members=leaves[row.left]!!.clone() as BitSet;members.or(leaves[row.right]);leaves[n+i]=members
   if(row.distance<=1-config.tau) { val a=find(leaves[row.left]!!.nextSetBit(0));val b=find(leaves[row.right]!!.nextSetBit(0));parent[b]=a }
  }
  val groups=linkedMapOf<Int,BitSet>()
  for(i in 0 until n) groups.getOrPut(find(i)) { BitSet(n) }.set(i)
  diagnostic["window_clusters_at_cut"]=groups.size
  val forced=mutableListOf<Map<String,Any?>>()
  for((rowIndex,row) in tree.withIndex()) {
   if(groups.size<=config.maxSpeakers) break
   val members=leaves[n+rowIndex]!!
   val keys=groups.filterValues { it.intersects(members) }.keys.toList()
   if(keys.size<2) continue
   if(keys.any { val outside=groups.getValue(it).clone() as BitSet;outside.andNot(members);!outside.isEmpty }) continue
   val keep=keys.minBy { groups.getValue(it).nextSetBit(0) };val combined=BitSet(n)
   for(key in keys) combined.or(groups.getValue(key))
   forced+=linkedMapOf("linkage_row" to rowIndex,"window_groups" to keys.map { indices(groups.getValue(it)) },"distance" to row.distance,
    "above_cut" to (row.distance>1-config.tau),"result_window_indices" to indices(combined))
   for(key in keys) if(key!=keep) groups.remove(key)
   groups[keep]=combined
  }
  val ordered=groups.values.sortedBy { it.nextSetBit(0) }
  val labels=(0 until n).map { i -> ordered.indexOfFirst { it[i] } }
  val centroids=ordered.withIndex().associate { (label,members) -> label to mean(indices(members).map { i -> Observation(vectors[i],windows[i].endMs-windows[i].startMs) }) }
  diagnostic["forced_cap_merges"]=forced;diagnostic["window_clusters_after_cap"]=ordered.size
  diagnostic["window_cluster_members"]=ordered.map { indices(it) }
  diagnostic["cluster_centroids"]=centroids.map { linkedMapOf("cluster" to it.key,"embedding" to it.value?.toList()) }
  return Hierarchy(labels,centroids)
 }
 private fun centerDistance(start: Long,end: Long,window: SpeakerRefiner.EmbeddingWindow): BigInteger =
  BigInteger.valueOf(start).add(BigInteger.valueOf(end)).subtract(BigInteger.valueOf(window.startMs)).subtract(BigInteger.valueOf(window.endMs)).abs()
 private fun nearestBefore(a: Int,b: Int,start: Long,end: Long,windows: List<SpeakerRefiner.EmbeddingWindow>): Boolean {
  val distance=centerDistance(start,end,windows[a]).compareTo(centerDistance(start,end,windows[b]))
  if(distance!=0) return distance<0
  val centerA=BigInteger.valueOf(windows[a].startMs).add(BigInteger.valueOf(windows[a].endMs))
  val centerB=BigInteger.valueOf(windows[b].startMs).add(BigInteger.valueOf(windows[b].endMs))
  return if(centerA!=centerB) centerA<centerB else a<b
 }
 private fun assign(native: List<Turn>,windows: List<SpeakerRefiner.EmbeddingWindow>,labels: List<Int>,config: Config,diagnostic: MutableMap<String,Any?>): MutableList<Turn> {
  val bySource=native.map { it.speaker }.distinct().associateWith { source -> windows.indices.filter { windows[it].speaker==source } }
  val atoms=mutableListOf<Map<String,Any?>>()
  val fallbacks=mutableListOf<Map<String,Any?>>()
  val result=mutableListOf<Turn>();val durations=mutableMapOf<String,BigInteger>()
  for(speaker in bySource.keys.sorted()) for(interval in union(native.filter { it.speaker==speaker }.map { Interval(it.startMs,it.endMs) })) {
   var start=interval.start
   while(start<interval.end) {
    val step=min(interval.end-start,config.gridMs-start%config.gridMs);val stop=start+step
    val scores=mutableMapOf<Int,Double>();val votes=mutableListOf<Map<String,Any?>>()
    for(index in bySource.getValue(speaker)) {
     val window=windows[index];val left=max(start,window.startMs);val right=min(stop,window.endMs)
     if(right<=left) continue
     val triangle=1-abs((left-window.startMs)+(right-window.startMs)-(window.endMs-window.startMs)).toDouble()/(window.endMs-window.startMs)
     val weight=(right-left)*max(0.0,triangle);val label=labels[index]
     scores[label]=(scores[label]?:0.0)+weight
     votes+=linkedMapOf("window" to index,"cluster" to label,"overlap_ms" to right-left,"weight" to weight)
    }
    val label: Int;val method: String;val nearest: Int?
    if(scores.isNotEmpty() && scores.values.max()>0) {
     label=scores.keys.minWith(compareByDescending<Int> { scores.getValue(it) }.thenBy { it });method="covering_same_source_vote";nearest=null
    } else {
     val same=bySource.getValue(speaker).isNotEmpty();val candidates=if(same) bySource.getValue(speaker) else windows.indices.toList()
     var best=candidates.first();for(index in candidates.drop(1)) if(nearestBefore(index,best,start,stop,windows)) best=index
     nearest=best;label=labels[best];method=if(same) "nearest_same_source_time" else "nearest_global_time_missing_source_windows"
     fallbacks+=linkedMapOf("start_ms" to start,"end_ms" to stop,"source_speaker" to speaker,"window" to best,"cluster" to label,"method" to method,
      "midpoint_distance_ms" to centerDistance(start,stop,windows[best]).toDouble()/2)
    }
    atoms+=linkedMapOf("start_ms" to start,"end_ms" to stop,"source_speaker" to speaker,"cluster" to label,"method" to method,"nearest_window" to nearest,"votes" to votes)
    durations[method]=(durations[method]?:BigInteger.ZERO).add(BigInteger.valueOf(stop-start))
    result+=Turn(start,stop,label);start=stop
   }
  }
  diagnostic["assignment_atoms"]=atoms.sortedWith(compareBy<Map<String,Any?>> { it.getValue("start_ms") as Long }.thenBy { it.getValue("end_ms") as Long }.thenBy { it.getValue("source_speaker") as Int })
  diagnostic["fallbacks"]=fallbacks;diagnostic["assignment_method_speaker_ms"]=durations.toSortedMap()
  diagnostic["fully_acoustic_supported"]=fallbacks.isEmpty();diagnostic["every_native_label_has_measured_windows"]=bySource.values.all { it.isNotEmpty() }
  return coalesce(result)
 }
 private fun small(turns: List<Turn>,centroids: Map<Int,DoubleArray?>,duration: Long,config: Config,diagnostic: MutableMap<String,Any?>): Pair<MutableList<Turn>,Map<Int,Int>> {
  val cutoff=max(config.minClusterMs.toDouble(),config.minClusterFraction*duration)
  diagnostic["small_cluster_cutoff_ms"]=cutoff
  val decisions=mutableListOf<Map<String,Any?>>()
  diagnostic["small_reassignments"]=decisions
  val labels=turns.map { it.speaker }.distinct().sorted();val mapping=centroids.keys.associateWith { it }.toMutableMap()
  if(!config.reassignSmall || labels.size<2) return turns.toMutableList() to mapping
  val durations=labels.associateWith { label -> union(turns.filter { it.speaker==label }.map { Interval(it.startMs,it.endMs) }).sumOf { it.end-it.start } }
  var anchors=labels.filter { durations.getValue(it).toDouble()>=cutoff }
  if(anchors.isEmpty()) { anchors=listOf(labels.minWith(compareByDescending<Int> { durations.getValue(it) }.thenBy { it }));diagnostic["all_small_anchor"]=anchors.first() }
  for(label in labels) {
   if(label in anchors || durations.getValue(label).toDouble()>=cutoff) continue
   var best=anchors.first();var similarity=Double.NEGATIVE_INFINITY
   for(anchor in anchors) { val value=cosine(centroids[label]!!,centroids[anchor]!!);if(value>similarity || (value==similarity && anchor<best)) { similarity=value;best=anchor } }
   val applied=config.minimumReassignmentSimilarity==null || similarity>=config.minimumReassignmentSimilarity
   decisions+=linkedMapOf("source" to label,"target" to best,"cosine" to similarity,"source_activity_ms" to durations.getValue(label),"applied" to applied,
    "reason" to if(applied) "nearest_measured_window_cluster_centroid" else "minimum_similarity_guard")
   if(applied) mapping[label]=best
  }
  return coalesce(turns.map { Turn(it.startMs,it.endMs,mapping.getValue(it.speaker)) }) to mapping
 }
 private fun smooth(turns: List<Turn>,config: Config,diagnostic: MutableMap<String,Any?>): MutableList<Turn> {
  var result=turns.toMutableList();val decisions=mutableListOf<Map<String,Any?>>()
  diagnostic["smoothing"]=decisions;var changed=config.smooth && config.smoothMs>0
  while(changed) {
   changed=false
   for(i in 1 until result.lastIndex) {
    val left=result[i-1];val middle=result[i];val right=result[i+1]
    if(left.speaker!=right.speaker || middle.speaker==left.speaker || middle.endMs-middle.startMs>=config.smoothMs || left.endMs!=middle.startMs || middle.endMs!=right.startMs) continue
    if(result.withIndex().any { (j,t) -> j!=i && t.startMs<middle.endMs && t.endMs>middle.startMs }) continue
    decisions+=linkedMapOf("start_ms" to middle.startMs,"end_ms" to middle.endMs,"source" to middle.speaker,"target" to left.speaker)
    result[i]=Turn(middle.startMs,middle.endMs,left.speaker);result=coalesce(result);changed=true;break
   }
  }
  return result
 }
 fun refine(turns: List<Turn>,windows: List<SpeakerRefiner.EmbeddingWindow>,durationMs: Long,config: Config=Config()): Result = overcluster(turns,windows,durationMs,config)
 fun overcluster(turns: List<Turn>,windows: List<SpeakerRefiner.EmbeddingWindow>,durationMs: Long,config: Config=Config()): Result {
  validate(config,durationMs)
  val native=turns.filter { it.startMs>=0 && it.startMs<it.endMs && it.endMs<=durationMs && it.speaker>=0 }.sortedWith(turnOrder)
  val invalid=mutableListOf<Int>();val duplicates=mutableListOf<Int>()
  val diagnostic=linkedMapOf<String,Any?>("algorithm" to "window-overcluster-v1","config" to config.asMap(),"duration_ms" to durationMs,"new_neural_inference" to false,"eigengap_applied" to false,
   "boundary_timing_scope" to "Saved-window votes on an activity-confined grid; no forced alignment or true change-point accuracy claim",
   "invalid_windows" to invalid,"duplicate_windows" to duplicates,"native_input_clusters" to native.map { it.speaker }.distinct().size)
  fun unsupported(reason: String): Result {
   diagnostic["status"]="UNSUPPORTED";diagnostic["reason"]=reason;diagnostic["output_clusters"]=native.map { it.speaker }.distinct().size
   return Result(native.toList(),false,diagnostic)
  }
  if(native.size!=turns.size) return unsupported("invalid_native_turns")
  val allowed=SpeakerRefiner.cleanWindows(native,durationMs).map { Key(it.startMs,it.endMs,it.speaker) }.toSet()
  val prepared=mutableMapOf<Key,Pair<SpeakerRefiner.EmbeddingWindow,DoubleArray>>()
  for((index,window) in windows.withIndex()) {
   val key=Key(window.startMs,window.endMs,window.speaker);val vector=unit(window.embedding)
   if(key !in allowed || !window.clean || vector==null) invalid+=index
   else if(key in prepared) { if(!equivalent(prepared.getValue(key).second,vector)) invalid+=index else duplicates+=index }
   else prepared[key]=window to vector
  }
  if(invalid.isNotEmpty()) return unsupported("invalid_or_conflicting_measured_windows")
  val ordered=prepared.toSortedMap(keyOrder).values.toList()
  if(native.isEmpty()) {
   diagnostic["status"]="EMPTY";diagnostic["output_clusters"]=0;diagnostic["activity_union_preserved"]=true;diagnostic["window_labels"]=emptyList<Any>()
   return Result(emptyList(),true,diagnostic)
  }
  if(ordered.isEmpty()) return unsupported("no_real_clean_windows")
  if(ordered.size>2048) return unsupported("too_many_windows_for_quadratic_hc")
  val measured=ordered.map { it.first };val vectors=ordered.map { it.second }
  if(vectors.map { it.size }.distinct().size!=1) return unsupported("embedding_dimension_mismatch")
  val hierarchy=cluster(measured,vectors,config,diagnostic)
  if(hierarchy.centroids.values.any { it==null }) return unsupported("cancelled_measured_cluster_centroid")
  diagnostic["eigengap_diagnostic"]=SpeakerRefiner.estimateSpeakers(hierarchy.centroids.values.map { it!! },config.tau,config.maxSpeakers)
  val assigned=assign(native,measured,hierarchy.labels,config,diagnostic)
  diagnostic["clusters_after_voting"]=assigned.map { it.speaker }.distinct().size
  val (afterSmall,mapping)=small(assigned,hierarchy.centroids,durationMs,config,diagnostic)
  diagnostic["clusters_after_small"]=afterSmall.map { it.speaker }.distinct().size
  val output=smooth(afterSmall,config,diagnostic);val stable=linkedMapOf<Int,Int>()
  for(turn in output) stable.getOrPut(turn.speaker) { stable.size }
  val result=output.map { Turn(it.startMs,it.endMs,stable.getValue(it.speaker)) }
  diagnostic["window_labels"]=measured.mapIndexed { i,w -> linkedMapOf("index" to i,"start_ms" to w.startMs,"end_ms" to w.endMs,"source_speaker" to w.speaker,"cluster" to hierarchy.labels[i],
   "after_small_cluster" to mapping.getValue(hierarchy.labels[i]),"stable_label_if_present" to stable[mapping.getValue(hierarchy.labels[i])]) }
  val originalBounds=native.flatMap { listOf(it.startMs,it.endMs) }.toSet();val newBounds=(result.flatMap { listOf(it.startMs,it.endMs) }.toSet()-originalBounds).sorted()
  diagnostic["status"]=if(diagnostic["fully_acoustic_supported"]==true) "SUPPORTED" else "PARTIAL_TEMPORAL"
  diagnostic["measured_unique_windows"]=measured.size;diagnostic["embedding_dimension"]=vectors.first().size;diagnostic["output_clusters"]=stable.size
  diagnostic["stable_label_mapping"]=stable.map { linkedMapOf("cluster" to it.key,"label" to it.value) }
  diagnostic["original_activity_union_ms"]=activity(native).sumOf { it.end-it.start };diagnostic["output_activity_union_ms"]=activity(result).sumOf { it.end-it.start }
  diagnostic["activity_union_preserved"]=activity(native)==activity(result);diagnostic["original_speaker_time_ms"]=speakerTime(native);diagnostic["output_speaker_time_ms"]=speakerTime(result)
  diagnostic["speaker_time_collapsed_ms"]=speakerTime(native).subtract(speakerTime(result));diagnostic["new_internal_grid_boundaries_ms"]=newBounds
  diagnostic["grid_boundary_resolution_ms"]=config.gridMs
  @Suppress("UNCHECKED_CAST") val atoms=diagnostic.getValue("assignment_atoms") as List<Map<String,Any?>>
  diagnostic["max_assignment_atom_ms"]=atoms.maxOf { (it.getValue("end_ms") as Long)-(it.getValue("start_ms") as Long) }
  if(diagnostic["activity_union_preserved"]!=true) return unsupported("internal_activity_union_changed")
  return Result(result,true,diagnostic)
 }
}
