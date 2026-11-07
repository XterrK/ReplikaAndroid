package ru.replika.domain

/** Persisted CPU request policy; missing historical WorkData always remains V1.6. */
enum class CpuPlan(val wireId: String) {
    LEGACY("v16"),
    AUTO_V1("auto_v1");

    fun resolve(requestedThreads: Int, availableCores: Int, refined: Boolean): CpuResolution {
        val cores = availableCores.coerceAtLeast(1)
        val chosen = if (requestedThreads == 0) {
            require(this == AUTO_V1) { "Automatic threads require the explicit auto_v1 CPU plan" }
            MlPolicy.automaticThreads(cores)
        } else MlPolicy.threads(requestedThreads)
        val pin = this == LEGACY && refined
        val diarization = if (pin) 2 else chosen
        return CpuResolution(this, requestedThreads, cores, chosen, diarization,
            if (refined) diarization else null, pin, pin)
    }

    /** The adapter default keeps the measured C2 contract; adaptive counts require opt-in. */
    fun requireRefinementThreads(threads: Int) {
        MlPolicy.threads(threads)
        require(this == AUTO_V1 || threads == 2) { "The legacy C2 policy requires two embedding threads" }
    }

    companion object {
        fun fromPersistedId(value: String?): CpuPlan = if (value == null) LEGACY
            else entries.firstOrNull { it.wireId == value } ?: error("Неизвестный профиль CPU: $value")
    }
}

data class CpuResolution(
    val plan: CpuPlan,
    val requestedThreads: Int,
    val availableCores: Int,
    val asrThreads: Int,
    val diarizationThreads: Int,
    val refinementThreads: Int?,
    val diarizationPinned: Boolean,
    val refinementPinned: Boolean,
) {
    fun asMap(): Map<String, Any?> = linkedMapOf(
        "plan" to plan.wireId, "requestedThreads" to requestedThreads, "availableCores" to availableCores,
        "asrThreads" to asrThreads, "diarizationThreads" to diarizationThreads,
        "refinementThreads" to refinementThreads, "diarizationPinned" to diarizationPinned,
        "refinementPinned" to refinementPinned,
    )
}
