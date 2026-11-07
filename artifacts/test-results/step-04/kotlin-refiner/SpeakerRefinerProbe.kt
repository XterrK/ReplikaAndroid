import java.nio.file.Files
import java.nio.file.Path
import org.json.JSONArray
import org.json.JSONObject
import ru.replika.domain.SpeakerRefiner
import ru.replika.domain.Turn

private fun vector(a: JSONArray): DoubleArray=DoubleArray(a.length()) { i ->
 val value=a.get(i)
 when(value) { is Number -> value.toDouble(); "NaN" -> Double.NaN; "Inf" -> Double.POSITIVE_INFINITY; "-Inf" -> Double.NEGATIVE_INFINITY; else -> Double.NaN }
}
private fun jsonValue(value: Any?): Any = when(value) {
 null -> JSONObject.NULL
 is Map<*,*> -> JSONObject().also { out -> for((key,item) in value) out.put(key.toString(),jsonValue(item)) }
 is Iterable<*> -> JSONArray().also { out -> for(item in value) out.put(jsonValue(item)) }
 is DoubleArray -> JSONArray().also { out -> for(item in value) out.put(item) }
 else -> value
}
private fun config(j: JSONObject)=SpeakerRefiner.Config(
 mergeThreshold=j.optDouble("merge_threshold",.85),maxSpeakers=j.optInt("max_speakers",8),minClusterMs=j.optLong("min_cluster_ms",2000),
 minClusterFraction=j.optDouble("min_cluster_fraction",.03),smoothMs=j.optLong("smooth_ms",500),mergeSimilar=j.optBoolean("merge_similar",true),
 useEigengap=j.optBoolean("use_eigengap",true),reassignSmall=j.optBoolean("reassign_small",true),smooth=j.optBoolean("smooth",true),
 completeLinkGuard=j.optBoolean("complete_link_guard",false),minimumReassignmentSimilarity=if(j.has("minimum_reassignment_similarity") && !j.isNull("minimum_reassignment_similarity")) j.getDouble("minimum_reassignment_similarity") else null,
 smallMissingCentroidPolicy=j.optString("small_missing_centroid_policy","retain"))
fun main(args: Array<String>) {
 val input=JSONArray(Files.readString(Path.of(args[0])));val output=JSONArray()
 for(i in 0 until input.length()) {
  val item=input.getJSONObject(i);val row=JSONObject().put("id",item.getString("id"))
  try {
   val cfg=config(item.optJSONObject("config")?:JSONObject())
   if(item.optString("kind")=="estimate") {
    val values=item.getJSONArray("centroids");val vectors=(0 until values.length()).map { vector(values.getJSONArray(it)) }
    row.put("diagnostics",jsonValue(SpeakerRefiner.estimateSpeakers(vectors,cfg.mergeThreshold,cfg.maxSpeakers)))
   } else {
    val ts=item.getJSONArray("turns");val turns=(0 until ts.length()).map { k -> val t=ts.getJSONObject(k);Turn(t.getLong("start_ms"),t.getLong("end_ms"),t.getInt("speaker")) }
    val ws=item.getJSONArray("windows");val windows=(0 until ws.length()).map { k -> val w=ws.getJSONObject(k);SpeakerRefiner.EmbeddingWindow(w.getLong("start_ms"),w.getLong("end_ms"),w.getInt("speaker"),vector(w.getJSONArray("embedding")),w.optBoolean("clean",true)) }
    val result=SpeakerRefiner.refine(turns,windows,item.getLong("duration_ms"),cfg)
    row.put("accepted",result.accepted).put("diagnostics",jsonValue(result.diagnostics))
    row.put("turns",JSONArray(result.turns.map { linkedMapOf("start_ms" to it.startMs,"end_ms" to it.endMs,"speaker" to it.speaker) }))
   }
  } catch(ex: Exception) { row.put("error",true).put("error_type",ex.javaClass.simpleName).put("reason",ex.message) }
  output.put(row)
 }
 Files.writeString(Path.of(args[1]),output.toString())
}
