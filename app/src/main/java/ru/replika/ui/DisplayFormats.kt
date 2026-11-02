package ru.replika.ui

import org.json.JSONObject
import java.util.Locale

fun formatBytes(bytes: Long): String = when {
 bytes <= 0 -> "0 Б"
 bytes < 1024 -> "$bytes Б"
 bytes < 1024*1024 -> "${(bytes/1024.0).let { String.format(Locale("ru"),"%.0f",it) }} КБ"
 else -> "${String.format(Locale("ru"),"%.1f",bytes/1048576.0)} МБ"
}
fun formatElapsed(ms: Long?): String = when {
 ms == null || ms < 0 -> "—"
 ms < 1000 -> "$ms мс"
 ms < 60000 -> "${String.format(Locale("ru"),"%.1f",ms/1000.0)} с"
 else -> clock(ms)
}
fun audioClock(ms: Long,durationMs: Long=ms)=if(durationMs in 1L..999L) formatElapsed(ms.coerceAtLeast(0)) else clock(ms)
fun backendName(id: String)=when(id) { "giga-v2"->"GigaAM v2";"whisper-tiny"->"Whisper tiny";else->id }
data class DiagnosticView(val data: JSONObject?) {
 fun time(key: String): Long?=data?.optJSONObject("stagesMs")?.let { if(it.has(key)) it.optLong(key) else null }
 val audioMs get()=data?.let { if(it.has("audioMs")) it.optLong("audioMs") else null }
 val totalMs get()=data?.let { if(it.has("totalMs")) it.optLong("totalMs") else null }
 val rtf get()=data?.optDouble("pipelineRtf")?.takeIf { it.isFinite() }?.let { String.format(Locale("ru"),"%.2f",it) }?:"—"
 val memory get()=data?.let { if(it.has("finalPssKb")) formatBytes(it.optLong("finalPssKb")*1024) else null }?:"—"
 companion object { fun parse(value: String)=DiagnosticView(runCatching { JSONObject(value) }.getOrNull()) }
}
