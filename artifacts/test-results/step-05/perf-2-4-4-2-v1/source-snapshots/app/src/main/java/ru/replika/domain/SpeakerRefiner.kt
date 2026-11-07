package ru.replika.domain

import java.math.BigInteger
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/** Pure port of speaker_refiner.py SHA4f52854185c9ad4b2e54b9679a9670b5415d5a9fcc1c16d0c5f392eb6aa69eb1.
 * Computational support is not diarization quality/release acceptance. No audio, model, reference,
 * expected speaker count or text enters this object. All native endpoints/activity are retained.
 * This is a thresholded-centroid eigengap heuristic, not published NME-SC. */
object SpeakerRefiner {
 data class EmbeddingWindow(val startMs: Long,val endMs: Long,val speaker: Int,
  val embedding: DoubleArray=doubleArrayOf(),val clean: Boolean=true)
 data class Config(val mergeThreshold: Double=.85,val maxSpeakers: Int=8,
  val minClusterMs: Long=2000,val minClusterFraction: Double=.03,val smoothMs: Long=500,
  val mergeSimilar: Boolean=true,val useEigengap: Boolean=true,val reassignSmall: Boolean=true,
  val smooth: Boolean=true,val completeLinkGuard: Boolean=false,
  val minimumReassignmentSimilarity: Double?=null,val smallMissingCentroidPolicy: String="retain") {
  fun asMap(): Map<String,Any?> = linkedMapOf("merge_threshold" to mergeThreshold,"max_speakers" to maxSpeakers,
   "min_cluster_ms" to minClusterMs,"min_cluster_fraction" to minClusterFraction,"smooth_ms" to smoothMs,
   "merge_similar" to mergeSimilar,"use_eigengap" to useEigengap,"reassign_small" to reassignSmall,
   "smooth" to smooth,"complete_link_guard" to completeLinkGuard,
   "minimum_reassignment_similarity" to minimumReassignmentSimilarity,"small_missing_centroid_policy" to smallMissingCentroidPolicy)
 }
 data class Result(val turns: List<Turn>,val accepted: Boolean,val diagnostics: Map<String,Any?>)
 private data class Interval(val start: Long,val end: Long)
 private data class WindowKey(val start: Long,val end: Long,val speaker: Int)
 private data class Observation(val vector: DoubleArray,val weight: Long)
 private data class Prepared(val vector: DoubleArray,val index: Int)
 private data class Best(val similarity: Double,val left: Int,val right: Int)
 private data class Planned(val key: Int,val target: Int,val similarity: Double?,val distance: Double?)
 private data class Temporal(val distance: BigInteger,val candidateStart: Long,val rank: Int,val sourceStart: Long,val anchor: Int)
 private val turnOrder=compareBy<Turn> { it.startMs }.thenBy { it.endMs }.thenBy { it.speaker }
 private val windowOrder=compareBy<WindowKey> { it.start }.thenBy { it.end }.thenBy { it.speaker }

 private fun validate(config: Config) {
  require(config.mergeThreshold.isFinite() && config.mergeThreshold > -1 && config.mergeThreshold < 1) { "merge_threshold must be finite and strictly between -1 and 1" }
  require(config.maxSpeakers in 1..8) { "max_speakers must be in 1..8" }
  require(config.minClusterMs>=0 && config.smoothMs>=0)
  require(config.minClusterFraction.isFinite() && config.minClusterFraction in 0.0..1.0)
  require(config.minimumReassignmentSimilarity==null || (config.minimumReassignmentSimilarity.isFinite() && config.minimumReassignmentSimilarity in -1.0..1.0))
  require(config.smallMissingCentroidPolicy in setOf("retain","temporal"))
 }
 private fun validTurns(turns: List<Turn>,durationMs: Long): Pair<List<Turn>,Int> {
  val valid=turns.filter { it.startMs>=0 && it.endMs>it.startMs && it.endMs<=durationMs && it.speaker>=-1 }.sortedWith(turnOrder)
  return valid to turns.size-valid.size
 }
 private fun union(intervals: List<Interval>): List<Interval> {
  val result=mutableListOf<Interval>()
  for(value in intervals.sortedWith(compareBy<Interval> { it.start }.thenBy { it.end })) {
   val previous=result.lastOrNull()
   if(previous!=null && value.start<=previous.end) result[result.lastIndex]=Interval(previous.start,max(previous.end,value.end))
   else result+=value
  }
  return result
 }
 private fun exclusive(turns: List<Turn>,speaker: Int): List<Interval> {
  val own=union(turns.filter { it.speaker==speaker }.map { Interval(it.startMs,it.endMs) })
  val other=union(turns.filter { it.speaker!=speaker }.map { Interval(it.startMs,it.endMs) })
  val result=mutableListOf<Interval>()
  for(interval in own) {
   var cursor=interval.start
   for(block in other) {
    if(block.end<=cursor) continue
    if(block.start>=interval.end) break
    if(block.start>cursor) result+=Interval(cursor,min(block.start,interval.end))
    cursor=max(cursor,block.end)
    if(cursor>=interval.end) break
   }
   if(cursor<interval.end) result+=Interval(cursor,interval.end)
  }
  return result
 }
 fun cleanWindows(turns: List<Turn>,durationMs: Long,windowMs: Long=1500,stepMs: Long=750,minCleanMs: Long=1000): List<EmbeddingWindow> {
  require(durationMs>=0 && windowMs>0 && stepMs>0 && minCleanMs>0 && minCleanMs<=windowMs)
  val (native,invalid)=validTurns(turns,durationMs)
  require(invalid==0) { "invalid native turns" }
  val result=mutableListOf<EmbeddingWindow>()
  for(speaker in native.map { it.speaker }.filter { it>=0 }.distinct().sorted()) {
   for(interval in exclusive(native,speaker)) {
    if(interval.end-interval.start<minCleanMs) continue
    if(interval.end-interval.start<windowMs) result+=EmbeddingWindow(interval.start,interval.end,speaker)
    else {
     var start=interval.start
     while(interval.end-start>=windowMs) {
      result+=EmbeddingWindow(start,start+windowMs,speaker)
      if(stepMs>interval.end-start) break
      start+=stepMs
     }
    }
   }
  }
  return result.sortedWith(compareBy<EmbeddingWindow> { it.startMs }.thenBy { it.endMs }.thenBy { it.speaker })
 }

 /** Nonoverlapping expansion summation, with half-even final correction as in math.fsum. */
 private fun sum(values: Iterable<Double>): Double {
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
 private fun norm(values: DoubleArray): Double {
  if(values.isEmpty()) return 0.0
  if(values.size==1) return abs(values[0])
  if(values.size==2) return Math.hypot(values[0],values[1])
  val scale=values.maxOf { abs(it) }
  if(scale==0.0) return 0.0
  return scale*sqrt(sum(values.map { val value=it/scale;value*value }))
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
 private fun cosine(a: DoubleArray,b: DoubleArray): Double = sum(a.indices.map { a[it]*b[it] }).coerceIn(-1.0,1.0)
 private fun mean(observations: List<Observation>): DoubleArray? {
  if(observations.isEmpty()) return null
  val total=sum(observations.map { it.weight.toDouble() })
  val result=DoubleArray(observations.first().vector.size) { i -> sum(observations.map { it.vector[i]*(it.weight.toDouble()/total) }) }
  return if(norm(result)<=1e-12) null else unit(result)
 }

 /** Symmetric cyclic Jacobi. Bounded <=256, <=80 sweeps, absolute off-diagonal tolerance1e-13. */
 private fun eigenvalues(matrix: Array<DoubleArray>): List<Double> {
  val n=matrix.size
  require(n<=256 && matrix.all { it.size==n && it.all(Double::isFinite) })
  val a=Array(n) { matrix[it].clone() }
  if(n<2) return if(n==0) emptyList() else listOf(a[0][0])
  var converged=false
  for(sweep in 0 until 80) {
   var largest=0.0
   for(p in 0 until n) for(q in p+1 until n) largest=max(largest,abs(a[p][q]))
   if(largest<=1e-13) { converged=true;break }
   for(p in 0 until n) for(q in p+1 until n) {
    val off=a[p][q]
    if(abs(off)<=1e-14) continue
    val theta=(a[q][q]-a[p][p])/(2*off)
    val tangent=if(theta>=0) 1.0/(theta+Math.hypot(1.0,theta)) else -1.0/(-theta+Math.hypot(1.0,theta))
    val c=1.0/sqrt(1+tangent*tangent);val s=tangent*c
    a[p][p]-=tangent*off;a[q][q]+=tangent*off;a[p][q]=0.0;a[q][p]=0.0
    for(k in 0 until n) if(k!=p && k!=q) {
     val ap=a[k][p];val aq=a[k][q]
     a[k][p]=c*ap-s*aq;a[p][k]=a[k][p]
     a[k][q]=s*ap+c*aq;a[q][k]=a[k][q]
    }
   }
  }
  if(!converged) {
   var largest=0.0
   for(p in 0 until n) for(q in p+1 until n) largest=max(largest,abs(a[p][q]))
   converged=largest<=1e-13
  }
  check(converged) { "bounded symmetric eigensolver did not converge" }
  return (0 until n).map { a[it][it] }.sorted()
 }
 fun estimateSpeakers(centroids: List<DoubleArray>,threshold: Double=.85,maxSpeakers: Int=8): Map<String,Any?> {
  validate(Config(mergeThreshold=threshold,maxSpeakers=maxSpeakers))
  require(centroids.size<=256) { "centroid count exceeds 256" }
  val vectors=centroids.map { requireNotNull(unit(it)) { "valid nonzero finite centroids required" } }
  require(vectors.map { it.size }.distinct().size<=1) { "same-dimensional centroids required" }
  val count=vectors.size
  if(count<2) return linkedMapOf("estimated_k" to count,"eigenvalues" to List(count) { 0.0 },"gaps" to emptyList<Any>(),
   "reason" to if(count==0) "empty" else "single_centroid","affinity_threshold" to threshold)
  val affinity=Array(count) { DoubleArray(count) }
  for(i in 0 until count) for(j in 0 until i) {
   val v=max(0.0,(cosine(vectors[i],vectors[j])-threshold)/(1-threshold));affinity[i][j]=v;affinity[j][i]=v
  }
  val degree=DoubleArray(count) { sum(affinity[it].asList()) }
  val inverse=DoubleArray(count) { if(degree[it]>0) 1.0/sqrt(degree[it]) else 0.0 }
  val laplacian=Array(count) { i -> DoubleArray(count) { j -> if(i==j) { if(degree[i]>0) 1.0 else 0.0 } else -affinity[i][j]*inverse[i]*inverse[j] } }
  val values=eigenvalues(laplacian).map { if(abs(it)<1e-12) 0.0 else it }
  val candidates=(1..min(maxSpeakers,count-1)).map { it to max(0.0,values[it]-values[it-1]) }
  val largest=candidates.maxOf { it.second }
  val flat=largest<=1e-9
  val chosen=if(flat) min(count,maxSpeakers) else candidates.filter { largest-it.second<=1e-9 }.maxOf { it.first }
  return linkedMapOf("estimated_k" to chosen,"eigenvalues" to values,"gaps" to candidates.map { linkedMapOf("k" to it.first,"gap" to it.second) },
   "reason" to if(flat) "flat_spectrum_retain" else "largest_gap_larger_k_tie","affinity_threshold" to threshold,"isolated_centroids" to degree.count { it<=0 })
 }
 private fun coalesce(turns: List<Turn>): MutableList<Turn> {
  val result=mutableListOf<Turn>()
  for(speaker in turns.map { it.speaker }.distinct().sorted()) {
   result+=union(turns.filter { it.speaker==speaker }.map { Interval(it.startMs,it.endMs) }).map { Turn(it.start,it.end,speaker) }
  }
  return result.sortedWith(turnOrder).toMutableList()
 }
 private fun duration(native: List<Turn>,members: Set<Int>): Long = union(native.filter { it.speaker in members }.map { Interval(it.startMs,it.endMs) }).sumOf { it.end-it.start }
 private fun overlap(native: List<Turn>,left: Set<Int>,right: Set<Int>): Long {
  val a=union(native.filter { it.speaker in left }.map { Interval(it.startMs,it.endMs) })
  val b=union(native.filter { it.speaker in right }.map { Interval(it.startMs,it.endMs) })
  var result=0L
  for(x in a) for(y in b) result+=max(0L,min(x.end,y.end)-max(x.start,y.start))
  return result
 }
 private fun midpointSum(t: Turn): BigInteger=BigInteger.valueOf(t.startMs).add(BigInteger.valueOf(t.endMs))
 private fun temporalBefore(a: Temporal,b: Temporal): Boolean {
  val distance=a.distance.compareTo(b.distance)
  return if(distance!=0) distance<0 else if(a.candidateStart!=b.candidateStart) a.candidateStart<b.candidateStart
   else if(a.rank!=b.rank) a.rank<b.rank else if(a.sourceStart!=b.sourceStart) a.sourceStart<b.sourceStart else a.anchor<b.anchor
 }

 fun refine(turns: List<Turn>,windows: List<EmbeddingWindow>,durationMs: Long,config: Config=Config()): Result {
  require(durationMs>=0);validate(config)
  val (native,invalid)=validTurns(turns,durationMs)
  val badWindows=mutableListOf<Map<String,Any?>>()
  val merges=mutableListOf<Map<String,Any?>>()
  val small=mutableListOf<Map<String,Any?>>()
  val smoothing=mutableListOf<Map<String,Any?>>()
  var forced=0;var low=0;var collapsed=BigInteger.ZERO
  val diagnostic=linkedMapOf<String,Any?>("algorithm" to "centroid-eigengap-v1","config" to config.asMap(),"duration_ms" to durationMs,
   "invalid_turns" to invalid,"invalid_windows" to badWindows,"merges" to merges,"small_reassignments" to small,"smoothing" to smoothing,
   "forced_cap_merges" to forced,"low_similarity_merges" to low,"overlap_collapses_ms" to collapsed)
  fun unsupported(reason: String): Result {
   diagnostic["status"]="UNSUPPORTED";diagnostic["reason"]=reason;diagnostic["output_clusters"]=native.map { it.speaker }.filter { it>=0 }.distinct().size
   return Result(native.toList(),false,diagnostic)
  }
  if(invalid>0) return unsupported("invalid_native_turns")
  val order=native.map { it.speaker }.filter { it>=0 }.distinct().sortedWith(compareBy<Int> { speaker -> native.filter { it.speaker==speaker }.minOf { it.startMs } }.thenBy { it })
  val rank=order.withIndex().associate { it.value to it.index }
  diagnostic["input_clusters"]=order.size
  if(order.isEmpty()) {
   diagnostic["status"]=if(native.isEmpty()) "EMPTY" else "UNKNOWN_ONLY";diagnostic["output_clusters"]=0
   return Result(native.toList(),true,diagnostic)
  }
  if(order.size>256) return unsupported("too_many_native_clusters")
  val allowed=cleanWindows(native,durationMs).map { WindowKey(it.startMs,it.endMs,it.speaker) }.toSet()
  val observed=order.associateWith { mutableListOf<Observation>() }
  val prepared=mutableMapOf<WindowKey,MutableList<Prepared>>()
  for((index,window) in windows.withIndex()) {
   val key=WindowKey(window.startMs,window.endMs,window.speaker);val vector=unit(window.embedding)
   if(key !in allowed || !window.clean || vector==null) badWindows+=linkedMapOf("index" to index,"reason" to "invalid_or_nonclean_window")
   else prepared.getOrPut(key) { mutableListOf() }+=Prepared(vector,index)
  }
  if(prepared.values.flatMap { entries -> entries.map { it.vector.size } }.distinct().size>1) return unsupported("embedding_dimension_mismatch")
  for((key,entries) in prepared.toSortedMap(windowOrder)) {
   if(entries.any { !equivalent(it.vector,entries.first().vector) }) {
    badWindows+=entries.map { linkedMapOf("index" to it.index,"reason" to "conflicting_duplicate_window") };continue
   }
   observed.getValue(key.speaker)+=Observation(entries.first().vector,key.end-key.start)
  }
  val original=order.associateWith { mean(observed.getValue(it)) }
  val missing=order.filter { original[it]==null }
  diagnostic["window_counts"]=order.map { linkedMapOf("speaker" to it,"count" to observed.getValue(it).size) }
  diagnostic["missing_centroid_labels"]=missing;diagnostic["fully_acoustic_supported"]=missing.isEmpty()
  diagnostic["centroids"]=order.filter { original[it]!=null }.map { linkedMapOf("speaker" to it,"embedding" to original.getValue(it)!!.toList()) }
  if(original.values.all { it==null } && order.size<=config.maxSpeakers) return unsupported("no_measured_centroids")
  val eigengap=estimateSpeakers(order.mapNotNull { original[it] },config.mergeThreshold,config.maxSpeakers)
  diagnostic["eigengap"]=eigengap
  val groups=linkedMapOf<Int,MutableSet<Int>>()
  for(speaker in order) groups[speaker]=mutableSetOf(speaker)
  fun centroid(key: Int): DoubleArray? = mean(groups.getValue(key).sortedBy { rank.getValue(it) }.flatMap { observed.getValue(it) })
  fun pair(): Best? {
   val keys=groups.keys.sortedBy { rank.getValue(it) };val values=keys.associateWith { centroid(it) };var best: Best?=null
   for((i,left) in keys.withIndex()) for(right in keys.drop(i+1)) {
    val a=values[left]?:continue;val b=values[right]?:continue
    if(config.completeLinkGuard && groups.getValue(left).any { x -> groups.getValue(right).any { y -> cosine(original.getValue(x)!!,original.getValue(y)!!)<=config.mergeThreshold } }) continue
    val candidate=Best(cosine(a,b),left,right)
    if(best==null || candidate.similarity>best.similarity) best=candidate
   }
   return best
  }
  fun merge(best: Best,stage: String) {
   val crossed=overlap(native,groups.getValue(best.left),groups.getValue(best.right))
   merges+=linkedMapOf("stage" to stage,"left" to groups.getValue(best.left).sorted(),"right" to groups.getValue(best.right).sorted(),"cosine" to best.similarity,"simultaneous_ms" to crossed)
   collapsed=collapsed.add(BigInteger.valueOf(crossed));low+=if(best.similarity<=config.mergeThreshold) 1 else 0;forced+=if(stage=="forced_cap") 1 else 0
   diagnostic["overlap_collapses_ms"]=collapsed;diagnostic["low_similarity_merges"]=low;diagnostic["forced_cap_merges"]=forced
   groups.getValue(best.left).addAll(groups.remove(best.right)!!)
  }
  if(config.mergeSimilar) while(true) { val best=pair()?:break;if(best.similarity<=config.mergeThreshold) break;merge(best,"cosine") }
  if(config.useEigengap) {
   val target=eigengap.getValue("estimated_k") as Int
   while(groups.keys.count { centroid(it)!=null }>target) { val best=pair()?:break;if(best.similarity<=0) break;merge(best,"eigengap") }
   diagnostic["eigengap_target_reached"]=groups.keys.count { centroid(it)!=null }<=target
  }
  val cutoff=max(config.minClusterMs.toDouble(),config.minClusterFraction*durationMs.toDouble())
  diagnostic["small_cluster_cutoff_ms"]=cutoff
  if(config.reassignSmall && groups.size>1) {
   val durations=groups.mapValues { duration(native,it.value) }
   var anchors=groups.keys.filter { durations.getValue(it).toDouble()>=cutoff && centroid(it)!=null }
   if(anchors.isEmpty()) {
    val available=groups.keys.filter { centroid(it)!=null }
    if(available.isNotEmpty()) {
     anchors=listOf(available.minWith(compareByDescending<Int> { durations.getValue(it) }.thenBy { rank.getValue(it) }))
     diagnostic[if(durations.values.all { it.toDouble()<cutoff }) "all_small_anchor" else "no_large_measured_anchor"]=anchors.first()
    }
   }
   val anchorCentroids=anchors.associateWith { centroid(it) }
   val planned=mutableListOf<Planned>()
   for(key in groups.keys.sortedBy { rank.getValue(it) }) {
    if(key in anchors || durations.getValue(key).toDouble()>=cutoff) continue
    val vector=centroid(key)
    if(vector==null) {
     if(config.smallMissingCentroidPolicy=="retain" || anchors.isEmpty()) {
      small+=linkedMapOf("source" to groups.getValue(key).sorted(),"target" to null,"cosine" to null,"method" to "retain","applied" to false,"reason" to if(anchors.isNotEmpty()) "missing_centroid" else "no_measured_anchor")
      continue
     }
     var best: Temporal?=null
     for(anchor in anchors) for(candidate in native.filter { it.speaker in groups.getValue(anchor) }) for(source in native.filter { it.speaker in groups.getValue(key) }) {
      val value=Temporal(midpointSum(source).subtract(midpointSum(candidate)).abs(),candidate.startMs,rank.getValue(anchor),source.startMs,anchor)
      if(best==null || temporalBefore(value,best)) best=value
     }
     planned+=Planned(key,best!!.anchor,null,best.distance.toDouble()/2)
     continue
    }
    if(anchors.isEmpty()) continue
    var bestTarget=anchors.first();var bestSimilarity=Double.NEGATIVE_INFINITY
    for(anchor in anchors) {
     val similarity=cosine(vector,anchorCentroids[anchor]!!)
     if(similarity>bestSimilarity || (similarity==bestSimilarity && rank.getValue(anchor)<rank.getValue(bestTarget))) { bestSimilarity=similarity;bestTarget=anchor }
    }
    val guard=config.minimumReassignmentSimilarity
    if(guard!=null && bestSimilarity<guard) small+=linkedMapOf("source" to groups.getValue(key).sorted(),"target" to bestTarget,"cosine" to bestSimilarity,"method" to "centroid","applied" to false,"reason" to "minimum_similarity_guard")
    else planned+=Planned(key,bestTarget,bestSimilarity,null)
   }
   for(plan in planned) {
    val crossed=overlap(native,groups.getValue(plan.key),groups.getValue(plan.target))
    small+=linkedMapOf("source" to groups.getValue(plan.key).sorted(),"target" to plan.target,"cosine" to plan.similarity,"method" to if(plan.similarity==null) "temporal" else "centroid","midpoint_distance_ms" to plan.distance,"applied" to true,"simultaneous_ms" to crossed)
    collapsed=collapsed.add(BigInteger.valueOf(crossed));diagnostic["overlap_collapses_ms"]=collapsed
    groups.getValue(plan.target).addAll(groups.remove(plan.key)!!)
   }
  }
  while(groups.size>config.maxSpeakers) {
   val keys=groups.keys.sortedBy { rank.getValue(it) };val values=keys.associateWith { centroid(it) };var best: Best?=null
   for((i,left) in keys.withIndex()) for(right in keys.drop(i+1)) {
    val a=values[left]?:continue;val b=values[right]?:continue;val candidate=Best(cosine(a,b),left,right)
    if(best==null || candidate.similarity>best.similarity) best=candidate
   }
   if(best==null) return unsupported("hard_cap_without_valid_centroids")
   merge(best,"forced_cap")
  }
  val mapping=mutableMapOf<Int,Int>();for((key,members) in groups) for(speaker in members) mapping[speaker]=key
  diagnostic["source_mapping_before_smoothing"]=order.map { linkedMapOf("source" to it,"target" to mapping.getValue(it)) }
  var output=coalesce(native.map { Turn(it.startMs,it.endMs,mapping[it.speaker]?:-1) })
  if(config.smooth && config.smoothMs>0) {
   var changed=true
   while(changed) {
    changed=false
    for(i in 1 until output.lastIndex) {
     val left=output[i-1];val middle=output[i];val right=output[i+1]
     if(left.speaker<0 || middle.speaker<0 || left.speaker!=right.speaker || middle.speaker==left.speaker || middle.endMs-middle.startMs>=config.smoothMs || left.endMs!=middle.startMs || middle.endMs!=right.startMs) continue
     if(output.withIndex().any { (j,t) -> j!=i && t.speaker!=middle.speaker && t.startMs<middle.endMs && t.endMs>middle.startMs }) continue
     smoothing+=linkedMapOf("start_ms" to middle.startMs,"end_ms" to middle.endMs,"source" to middle.speaker,"target" to left.speaker)
     output[i]=Turn(middle.startMs,middle.endMs,left.speaker);output=coalesce(output);changed=true;break
    }
   }
  }
  val stable=linkedMapOf<Int,Int>()
  for(turn in output) if(turn.speaker>=0) stable.getOrPut(turn.speaker) { stable.size }
  output=output.map { Turn(it.startMs,it.endMs,stable[it.speaker]?:-1) }.toMutableList()
  diagnostic["status"]=if(missing.isEmpty()) "SUPPORTED" else "PARTIAL_ACOUSTIC";diagnostic["output_clusters"]=stable.size
  diagnostic["output_label_mapping"]=stable.map { linkedMapOf("source" to it.key,"target" to it.value) }
  return Result(output.toList(),true,diagnostic)
 }
}
