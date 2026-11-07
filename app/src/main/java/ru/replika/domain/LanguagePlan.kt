package ru.replika.domain

/** Recognition language of one ASR chunk. Russian is priority 1 and the fallback for every doubt. */
enum class AsrLanguage(val wireId: String, val label: String) {
    RU("ru", "Русский"),
    EN("en", "English");

    companion object {
        /** Whisper returns ISO codes of ~100 languages; everything that is not English is Russian. */
        fun fromWhisper(code: String?): AsrLanguage = if (code?.trim()?.lowercase() == "en") EN else RU
        fun fromWireId(value: String?): AsrLanguage? = entries.firstOrNull { it.wireId == value }
    }
}

/** Persisted user request. Historical WorkData without a key stays Russian (V1.6 behaviour). */
enum class LanguageMode(val wireId: String, val label: String) {
    AUTO("auto", "Авто"),
    RU("ru", "Русский"),
    EN("en", "English");

    val forced: AsrLanguage? get() = when (this) { AUTO -> null; RU -> AsrLanguage.RU; EN -> AsrLanguage.EN }

    companion object {
        fun fromPersistedId(value: String?): LanguageMode = if (value == null) RU
            else entries.firstOrNull { it.wireId == value } ?: error("Неизвестный режим языка: $value")
    }
}

/** Pure decision rules mirrored by tools/eval/language_id.py (host stand). */
object LanguagePlan {
    const val SPEECH_BUDGET_MS = 30_000L
    const val PROBE_MAX_MS = 10_000L
    const val PROBE_MIN_MS = 1_000L
    const val MAX_PROBES = 3
    const val SEGMENT_MIN_MS = 1_500L

    /** Up to three probes of up to 10 s each, cut from the first 30 s of VAD speech in order.
     *  Speech of neighbouring chunks is concatenated; a final probe shorter than 1 s is dropped. */
    fun probes(chunks: List<Span>): List<List<Span>> {
        val probes = mutableListOf<List<Span>>()
        var current = mutableListOf<Span>()
        var currentMs = 0L
        var used = 0L
        for (chunk in chunks) {
            var start = chunk.startMs
            while (start < chunk.endMs && used < SPEECH_BUDGET_MS && probes.size < MAX_PROBES) {
                val take = minOf(chunk.endMs - start, PROBE_MAX_MS - currentMs, SPEECH_BUDGET_MS - used)
                current += Span(start, start + take)
                currentMs += take; used += take; start += take
                if (currentMs >= PROBE_MAX_MS) { probes += current; current = mutableListOf(); currentMs = 0 }
            }
            if (used >= SPEECH_BUDGET_MS || probes.size >= MAX_PROBES) break
        }
        if (current.isNotEmpty() && currentMs >= PROBE_MIN_MS && probes.size < MAX_PROBES) probes += current
        return probes
    }

    /** English only on a strict majority of English probes; ties, silence and errors are Russian. */
    fun vote(labels: List<AsrLanguage>): AsrLanguage =
        if (labels.isNotEmpty() && labels.count { it == AsrLanguage.EN } * 2 > labels.size) AsrLanguage.EN else AsrLanguage.RU

    /** Experimental per-chunk mode: chunks too short for a reliable label inherit the file decision. */
    fun segmentLanguage(label: AsrLanguage?, durationMs: Long, fileLanguage: AsrLanguage): AsrLanguage =
        if (label == null || durationMs < SEGMENT_MIN_MS) fileLanguage else label

    /** Chunk indices grouped by language (Russian pass first) so one recognizer is resident at a time.
     *  A single-language plan keeps the original chronological order exactly. */
    fun recognitionOrder(languages: List<AsrLanguage>): List<Int> =
        AsrLanguage.entries.flatMap { language -> languages.indices.filter { languages[it] == language } }
}

/** Outcome stored in diagnostics and shown in the transcript header. */
data class LanguageDecision(
    val mode: LanguageMode,
    val perSegment: Boolean,
    val fileLanguage: AsrLanguage,
    val chunkLanguages: List<AsrLanguage>,
    val probeLabels: List<String> = emptyList(),
    val reason: String,
) {
    val languages: Set<AsrLanguage> get() = chunkLanguages.toSet().ifEmpty { setOf(fileLanguage) }
    val mixed: Boolean get() = languages.size > 1
    /** Wire value for the transcript badge: "ru", "en" or "mixed". */
    val summary: String get() = if (mixed) "mixed" else languages.single().wireId
}

/** Transcript header badge. Reads the stored diagnostics without org.json (pure, JVM-testable). */
object TranscriptLanguage {
    private val pattern = Regex(""""asrLanguage"\s*:\s*"(ru|en|mixed)"""")
    /** "ru", "en", "mixed", or null for recordings processed before task 07 (they are Russian/GigaAM). */
    fun fromDiagnostics(diagnostics: String): String? = pattern.find(diagnostics)?.groupValues?.get(1)
    fun badge(summary: String?): String = when (summary) { "en" -> "EN · Parakeet"; "mixed" -> "RU + EN"; else -> "RU · GigaAM" }
    /** Re-run targets offered for a finished transcript: the other forced language(s) plus Auto. */
    fun rerunTargets(summary: String?): List<LanguageMode> = when (summary) {
        "en" -> listOf(LanguageMode.RU, LanguageMode.AUTO)
        "mixed" -> listOf(LanguageMode.RU, LanguageMode.EN)
        else -> listOf(LanguageMode.EN, LanguageMode.AUTO)
    }
}
