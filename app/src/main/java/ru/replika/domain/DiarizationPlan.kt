package ru.replika.domain

/** Explicit opt-in C2 policy; absent historical WorkData always means the original V1.6 path.
 * ERES2NET_WINDOW_CHUNKED_V1 is C2 for recordings up to [chunkConfig].minDurationMs and the
 * step-6 bounded-memory windowed C2 for longer ones. */
enum class DiarizationPlan(val wireId: String,val refined: Boolean) {
 LEGACY("v16",false),
 ERES2NET_WINDOW_V1("eres2net_window_v1",true),
 ERES2NET_WINDOW_CHUNKED_V1("eres2net_window_chunked_v1",true);

 // Both plans use the original seven-file pack, including the same ERes2Net embedding bytes.
 val embeddingPath get()="diar/embedding.onnx"
 val segmentationPath get()="diar/segmentation.onnx"
 val clusterThreshold get()=if(refined) .3f else .5f
 val segmentationWindowShiftRatio get()=.1f
 val diarMinDurationOnSec get()=.2f
 val diarMinDurationOffSec get()=.5f
 val windowConfig: WindowSpeakerRefiner.Config? get()=if(!refined) null else WindowSpeakerRefiner.Config(
  tau=.36,method="average",gridMs=125,maxSpeakers=8,reassignSmall=true)

 /** Non-null only for the chunked plan; short recordings still take the exact C2 path. */
 val chunkConfig: ChunkedDiarization.Config? get()=if(this==ERES2NET_WINDOW_CHUNKED_V1) ChunkedDiarization.Config() else null
 fun chunkedFor(durationMs: Long): ChunkedDiarization.Config? = chunkConfig?.takeIf { ChunkedDiarization.isChunked(durationMs,it) }
 /** A requested manual/single/fixed K must never be silently converted to C2 automatic refinement. */
 fun forExpectedSpeakers(expectedSpeakers: Int): DiarizationPlan {
  require(expectedSpeakers==-1 || expectedSpeakers in 1..20)
  return if(expectedSpeakers==-1) this else LEGACY
 }
 fun requirePairedAsr(asrPlan: AsrPlan) {
  require(!refined || asrPlan==AsrPlan.VAD_WORDS_CONTEXT600) { "Профиль C2 требует ASR context600" }
 }
 companion object {
  fun fromPersistedId(value: String?): DiarizationPlan = if(value==null) LEGACY else entries.firstOrNull { it.wireId==value }
   ?: error("Неизвестный профиль говорящих: $value")
 }
}
