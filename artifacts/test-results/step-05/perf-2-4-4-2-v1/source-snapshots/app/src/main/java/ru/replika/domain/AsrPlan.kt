package ru.replika.domain

/** Explicit, reproducible experimental profiles. Missing historical WorkData always means V1.6. */
enum class AsrPlan(val wireId: String,val wordTimestamps: Boolean,val seamPunctuation: Boolean,
 val vadThreshold: Float=.5f,val vadMinSpeechSec: Float=.25f,val vadMinSilenceSec: Float=.25f,
 val preRollMs: Long=100L) {
 LEGACY("v16",false,false),
 VAD_WORDS("vad_words_none",true,false),
 VAD_WORDS_SEAM("vad_words_seam",true,true),
 VAD_WORDS_SHORT15("vad_words_short15",true,false,vadMinSpeechSec=.15f,vadMinSilenceSec=.20f),
 VAD_WORDS_SHORT10("vad_words_short10",true,false,vadMinSpeechSec=.10f,vadMinSilenceSec=.12f),
 VAD_WORDS_SENSITIVE("vad_words_sensitive",true,false,vadThreshold=.35f,vadMinSpeechSec=.15f),
 VAD_WORDS_SHORT10_SEAM("vad_words_short10_seam",true,true,vadMinSpeechSec=.10f,vadMinSilenceSec=.12f),
 VAD_WORDS_SENSITIVE_SHORT10("vad_words_sensitive_short10",true,false,vadThreshold=.35f,vadMinSpeechSec=.10f,vadMinSilenceSec=.12f),
 VAD_WORDS_CONTEXT300("vad_words_context300",true,false,preRollMs=300L),
 VAD_WORDS_CONTEXT600("vad_words_context600",true,false,preRollMs=600L);

 val pipeline get()=if(wordTimestamps) "vad_words_v1" else "v16"
 val punctuationMode get()=if(seamPunctuation) "seam" else "none"

 companion object {
  fun fromPersistedId(value: String?): AsrPlan = if(value==null) LEGACY else entries.firstOrNull { it.wireId==value }
   ?: error("Неизвестный профиль распознавания: $value")
 }
}
