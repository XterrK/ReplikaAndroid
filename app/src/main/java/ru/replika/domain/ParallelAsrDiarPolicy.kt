package ru.replika.domain

/**
 * Step 14: run ASR over VAD chunks at the same time as diarization.
 *
 * Allowed only when ASR slicing does not depend on speaker turns (VAD word plans): speakers are then
 * needed only for the final word-to-speaker assignment, which still runs after both stages finish.
 * Pure decision: Android facts (cores, memory, model sizes) are passed in by the Worker.
 */
object ParallelAsrDiarPolicy {
    /**
     * Default for new jobs. Historical WorkData without the key always stays sequential.
     * Off since 08.11: on the ARM phone (vivo, 8 big.LITTLE cores) parallel mode gave no gain on short files
     * (RTF 0.35 -> 0.43 RU, 0.41 -> 0.41 EN) and overheated on 13 min (627 s thermal wait, RTF 0.41 -> 1.06).
     * The -11..-15% gain was measured only on the x86_64 emulator. See docs/STEP_14_PARALLEL_ASR_DIAR.md.
     */
    const val DEFAULT_ENABLED = false
    /** Native model working set is estimated from file size; ORT arenas and buffers add the rest. */
    const val MEMORY_FACTOR = 1.5
    const val MEMORY_MARGIN_BYTES = 256L shl 20

    data class Decision(
        val requested: Boolean,
        val enabled: Boolean,
        val reason: String,
        val availableCores: Int,
        val asrThreads: Int,
        val diarizationThreads: Int,
        val refinementThreads: Int?,
        val requiredBytes: Long,
        val availableBytes: Long,
    ) {
        fun asMap(): Map<String, Any?> = linkedMapOf(
            "requested" to requested, "enabled" to enabled, "reason" to reason,
            "availableCores" to availableCores, "asrThreads" to asrThreads,
            "diarizationThreads" to diarizationThreads, "refinementThreads" to refinementThreads,
            "requiredBytes" to requiredBytes, "availableBytes" to availableBytes,
        )
    }

    const val MIN_CORES = 4

    /** One core stays free for the system, VAD/JVM work and the UI, as in [MlPolicy.automaticThreads]. */
    const val RESERVED_CORES = 1

    /**
     * ASR threads beside a diarizer that keeps [diarizationThreads]. Diarization is the critical path
     * (about 4x ASR), so it is never slowed; ASR only has to finish before it and takes the largest
     * validated count that fits into the remaining cores:
     * 8 cores -> diarization 4 + ASR 2, 6..7 -> 4 + 1 (5 -> sequential), 4 -> 2 + 1; fewer -> sequential.
     */
    fun asrShare(cores: Int, diarizationThreads: Int, asrThreads: Int): Int? {
        if (cores < MIN_CORES) return null
        val budget = minOf(cores - RESERVED_CORES - diarizationThreads, asrThreads)
        return listOf(4, 2, 1).firstOrNull { it <= budget }
    }

    /** Extra resident bytes while the recognizer and the diarizer are loaded at the same time. */
    fun requiredBytes(asrModelBytes: Long, diarizationModelBytes: Long): Long =
        (MEMORY_FACTOR * (asrModelBytes.coerceAtLeast(0) + diarizationModelBytes.coerceAtLeast(0))).toLong() +
            MEMORY_MARGIN_BYTES

    fun decide(
        requested: Boolean,
        speakerIndependentSlicing: Boolean,
        diarization: Boolean,
        cpu: CpuResolution,
        availableBytes: Long,
        lowMemory: Boolean,
        asrModelBytes: Long,
        diarizationModelBytes: Long,
    ): Decision {
        val cores = cpu.availableCores.coerceAtLeast(1)
        val required = requiredBytes(asrModelBytes, diarizationModelBytes)
        fun sequential(reason: String) = Decision(requested, false, reason, cores, cpu.asrThreads,
            cpu.diarizationThreads, cpu.refinementThreads, required, availableBytes)
        if (!requested) return sequential("not_requested")
        if (!speakerIndependentSlicing) return sequential("speaker_dependent_slicing")
        if (!diarization) return sequential("no_diarization")
        // Diarization and C2 keep the resolved (or pinned) threads; ASR never exceeds its resolved count.
        val asr = asrShare(cores, cpu.diarizationThreads, cpu.asrThreads) ?: return sequential("too_few_cores")
        if (lowMemory) return sequential("low_memory")
        if (availableBytes < required) return sequential("insufficient_memory")
        return Decision(requested, true, "parallel", cores, MlPolicy.threads(asr), cpu.diarizationThreads,
            cpu.refinementThreads, required, availableBytes)
    }
}
