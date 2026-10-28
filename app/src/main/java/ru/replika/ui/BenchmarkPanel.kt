package ru.replika.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.ui.unit.sp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.*
import org.json.JSONObject
import ru.replika.data.Recording
import ru.replika.domain.*
import java.io.File

@Composable fun BenchmarkPanel(vm: AppViewModel,records: List<Recording>) {
 val context=LocalContext.current;val scope=rememberCoroutineScope()
 var runs by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
 suspend fun reload() { runs=withContext(Dispatchers.IO) { File(context.filesDir,"benchmarks").listFiles()?.sortedByDescending { it.lastModified() }?.mapNotNull { runCatching { JSONObject(it.readText()) }.getOrNull() }?:emptyList() } }
 LaunchedEffect(Unit) { reload() }
 var result by remember { mutableStateOf("Импортируйте JSON эталона: recordingId, text и turns [{startMs,endMs,speakerId}]. Метрики считаются по сохранённой обработке. Результат сохраняется локально.") }
 val pick=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> if(uri!=null) scope.launch {
  try {
   result=withContext(Dispatchers.IO) {
    val ref=JSONObject(context.contentResolver.openInputStream(uri)!!.bufferedReader().use { it.readText() })
    val id=ref.getString("recordingId");val rec=records.firstOrNull { it.id==id && it.status=="READY" }?:error("Нет готовой записи с recordingId=$id")
    val segments=vm.dao.segmentList(id)
    require(segments.none { it.edited }) { "Строгий benchmark требует исходного ML-результата до ручных исправлений. Экспортируйте его сразу после обработки." }
    val hypothesis=segments.joinToString(" ") { it.text }
    val diagnostics=if(rec.diagnostics.isNotBlank()) JSONObject(rec.diagnostics) else JSONObject()
    val out=JSONObject().put("schemaVersion",1).put("recordingId",id).put("createdAt",System.currentTimeMillis()).put("run",diagnostics)
    fun rate(v: Double?): Any = v?:"N/A"
    out.put("WER",if(ref.has("text")) rate(Benchmark.wer(ref.getString("text"),hypothesis)) else "N/A")
    out.put("CER",if(ref.has("text")) rate(Benchmark.cer(ref.getString("text"),hypothesis)) else "N/A")
    if(ref.has("turns") && diagnostics.has("diarizationTurns")) {
     fun turns(j: org.json.JSONArray)=List(j.length()) { i -> j.getJSONObject(i).let { Turn(it.getLong("startMs"),it.getLong("endMs"),it.getInt("speakerId")) } }
     val der=Benchmark.der(turns(ref.getJSONArray("turns")),turns(diagnostics.getJSONArray("diarizationTurns")),rec.durationMs)
     out.put("DER",rate(der.rate)).put("missMs",der.missMs).put("falseAlarmMs",der.falseAlarmMs).put("confusionMs",der.confusionMs).put("referenceSpeakerMs",der.referenceSpeakerMs)
    } else out.put("DER","N/A")
    out.put("derPolicy","zero collar; overlap included; global optimal permutation; full audio duration")
    val f=File(context.filesDir,"benchmarks").apply { mkdirs() }.let { File(it,"$id-${System.currentTimeMillis()}.json") };f.writeText(out.toString(2))
    out.toString(2)+"\n\nСохранено: ${f.name}"
   }
   reload()
  } catch(e: Exception) { result="Ошибка эталона: ${e.message}" }
 } }
 Column(verticalArrangement=Arrangement.spacedBy(10.dp)) {
  Text("Benchmark Suite",style=MaterialTheme.typography.headlineSmall)
  Text(result,color=Muted,style=MaterialTheme.typography.bodySmall)
  if(runs.isNotEmpty()) Column(Modifier.horizontalScroll(rememberScrollState())) {
   Text("Модель / запись                 WER       CER       DER       RTF",fontSize=12.sp,color=Mint)
   runs.take(20).forEach { run ->
    val diagnostic=run.optJSONObject("run")?:JSONObject()
    fun metric(key: String): String { val value=run.opt(key);return if(value is Number) "%.3f".format(java.util.Locale.ROOT,value.toDouble()) else "N/A" }
    Text("${diagnostic.optString("backend").take(20)} / ${run.optString("recordingId").take(8)}   ${metric("WER")}   ${metric("CER")}   ${metric("DER")}   ${diagnostic.optString("pipelineRtf","N/A").take(5)}",fontSize=12.sp,color=Muted)
   }
  }
  OutlinedButton(onClick={pick.launch(arrayOf("application/json","text/*","application/octet-stream"))}) { Text("Импорт эталона JSON") }
 }
}
