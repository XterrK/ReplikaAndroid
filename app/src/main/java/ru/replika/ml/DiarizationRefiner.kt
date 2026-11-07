package ru.replika.ml

import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractor
import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractorConfig
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import ru.replika.domain.SpeakerRefiner
import ru.replika.domain.CpuPlan
import ru.replika.domain.Turn
import ru.replika.domain.WindowSpeakerRefiner

/** Sequential C2 clean-window inference. The caller releases SD before entering
 * this adapter and starts ASR after it returns. No model/session cache or storage. */
object DiarizationRefiner {
    val SELECTED_CONFIG = WindowSpeakerRefiner.Config(
        tau = .36, method = "average", reassignSmall = true,
    )

    fun interface EmbeddingFactory {
        fun open(modelPath: String, threads: Int): EmbeddingSession
    }

    interface EmbeddingSession : AutoCloseable {
        val dimension: Int
        fun createStream(): EmbeddingStream
    }

    interface EmbeddingStream : AutoCloseable {
        fun acceptWaveform(samples: FloatArray, sampleRate: Int)
        fun inputFinished()
        fun isReady(): Boolean
        fun compute(): FloatArray
    }

    data class Counts(
        val plannedWindows: Int,
        val extractorLoads: Int,
        val readWindows: Int,
        val createdStreams: Int,
        val releasedStreams: Int,
        val computeAttempts: Int,
        val embeddingForwardCalls: Int,
        val measuredWindows: Int,
        val embeddingDimension: Int?,
    )

    data class Result(
        val turns: List<Turn>,
        /** Computational support, separate from diarization quality acceptance. */
        val accepted: Boolean,
        val diagnostics: Map<String, Any?>,
        /** Actual Float32 outputs promoted to Double; present only for explicit QA or retainWindows. */
        val measuredWindowsQA: List<SpeakerRefiner.EmbeddingWindow>?,
        val timingsMs: Map<String, Double>,
        val counts: Counts,
    )

    private class InvalidMeasurement(val reason: String) : Exception(reason)

    /** Wrap the real SDK only when open() is called; JVM fakes never initialize JNI. */
    private object NativeFactory : EmbeddingFactory {
        override fun open(modelPath: String, threads: Int): EmbeddingSession {
            val extractor = SpeakerEmbeddingExtractor(config = SpeakerEmbeddingExtractorConfig(
                model = modelPath, numThreads = threads, provider = "cpu", debug = false,
            ))
            return object : EmbeddingSession {
                private var closed = false
                override val dimension: Int get() = extractor.dim()
                override fun createStream(): EmbeddingStream {
                    check(!closed)
                    val stream = extractor.createStream()
                    return object : EmbeddingStream {
                        private var released = false
                        override fun acceptWaveform(samples: FloatArray, sampleRate: Int) =
                            stream.acceptWaveform(samples, sampleRate)
                        override fun inputFinished() = stream.inputFinished()
                        override fun isReady() = extractor.isReady(stream)
                        override fun compute() = extractor.compute(stream)
                        override fun close() {
                            if (!released) { released = true; stream.release() }
                        }
                    }
                }
                override fun close() {
                    if (!closed) { closed = true; extractor.release() }
                }
            }
        }
    }

    suspend fun refineOriginalPcm(
        turns: List<Turn>,
        durationMs: Long,
        modelPath: String,
        threads: Int,
        readOriginalWindow: suspend (Long, Long) -> FloatArray,
        collectEvidence: Boolean = false,
        config: WindowSpeakerRefiner.Config = SELECTED_CONFIG,
        isStopped: () -> Boolean = { false },
        embeddingFactory: EmbeddingFactory = NativeFactory,
        cpuPlan: CpuPlan = CpuPlan.LEGACY,
        /** Return measured vectors to the caller (step-6 window centroids) without QA storage. */
        retainWindows: Boolean = false,
    ): Result {
        require(config == SELECTED_CONFIG) { "Only the frozen C2 window policy is supported" }
        cpuPlan.requireRefinementThreads(threads)
        require(modelPath.isNotBlank()) { "An explicit validated embedding model path is required" }
        val native = turns.toList()
        val began = System.nanoTime()
        val stages = linkedMapOf<String, Double>()
        val measured = mutableListOf<SpeakerRefiner.EmbeddingWindow>()
        var plannedCount = 0
        var loads = 0
        var reads = 0
        var streams = 0
        var releasedStreams = 0
        var sessionReleased = true
        var attempts = 0
        var forwards = 0
        var dimension: Int? = null
        var failure: String? = null
        var failureClass: String? = null
        var stage = "planning"
        var windowIndex: Int? = null

        suspend fun checkpoint() {
            currentCoroutineContext().ensureActive()
            if (isStopped()) throw CancellationException("Diarization refinement stopped")
        }
        fun elapsed(start: Long) = (System.nanoTime() - start) / 1_000_000.0
        fun addTime(key: String, start: Long) { stages[key] = (stages[key] ?: 0.0) + elapsed(start) }
        fun counts() = Counts(plannedCount, loads, reads, streams, releasedStreams, attempts, forwards, measured.size, dimension)
        fun result(output: List<Turn>, accepted: Boolean, pure: Map<String, Any?>): Result {
            val diagnostics = linkedMapOf<String, Any?>(
                "algorithm" to "window-overcluster-v1", "config" to config.asMap(),
                "cpuPlan" to cpuPlan.wireId, "embeddingThreads" to threads,
                "status" to (pure["status"] ?: "UNSUPPORTED"),
                "computationalSupport" to accepted, "qualityAcceptance" to "not evaluated by this adapter",
                "originalPcm" to true, "sampleRate" to 16000,
                "cleanWindowMs" to 1500, "cleanWindowStepMs" to 750, "cleanMinimumIslandMs" to 1000,
                "embeddingInferenceCompleted" to (forwards > 0),
                "embeddingScope" to "Original decoded PCM; no gain, resampling, padding or normalization",
                "nativeResourcesReleasedBeforeRefiner" to (sessionReleased && streams == releasedStreams),
                "retainedNativeModelCache" to false, "refiner" to pure,
            )
            if (pure["reason"] != null) diagnostics["reason"] = pure["reason"]
            if (failure != null) {
                diagnostics["reason"] = failure
                diagnostics["failureStage"] = stage
                diagnostics["failureClass"] = failureClass
                diagnostics["failureWindowIndex"] = windowIndex
            }
            val evidence = if (collectEvidence || retainWindows) measured.toList() else null
            val finalCounts = counts()
            measured.clear()
            stages["totalMs"] = elapsed(began)
            return Result(output.toList(), accepted, diagnostics, evidence, stages.toMap(), finalCounts)
        }

        checkpoint()
        val embeddingStart = System.nanoTime()
        try {
            if (durationMs < 0 || native.any {
                    it.startMs < 0 || it.endMs <= it.startMs || it.endMs > durationMs || it.speaker < 0
                }) throw InvalidMeasurement("invalid_native_turns")
            val planned = SpeakerRefiner.cleanWindows(native, durationMs)
            plannedCount = planned.size
            if (plannedCount > 2048) throw InvalidMeasurement("too_many_windows_for_quadratic_hc")
            if (planned.isNotEmpty()) {
                stage = "extractor_load"
                checkpoint()
                val loadStart = System.nanoTime()
                val session = try { embeddingFactory.open(modelPath, threads) }
                    finally { addTime("embeddingLoadMs", loadStart) }
                loads++
                sessionReleased = false
                val managedSession = AutoCloseable { session.close(); sessionReleased = true }
                managedSession.use {
                    val extractor = session
                    dimension = extractor.dimension
                    if (dimension == null || dimension!! <= 0) throw InvalidMeasurement("invalid_embedding_dimension")
                    for ((index, window) in planned.withIndex()) {
                        windowIndex = index
                        checkpoint()
                        stage = "read_original_window"
                        val readStart = System.nanoTime()
                        val pcm = try { readOriginalWindow(window.startMs, window.endMs) }
                            finally { addTime("embeddingReadMs", readStart) }
                        reads++
                        checkpoint()
                        val expectedSamples = Math.multiplyExact(window.endMs - window.startMs, 16L)
                        if (pcm.size.toLong() != expectedSamples) throw InvalidMeasurement("invalid_pcm_sample_count")
                        if (pcm.any { !it.isFinite() }) throw InvalidMeasurement("nonfinite_original_pcm")
                        stage = "embedding_stream"
                        val computeStart = System.nanoTime()
                        try {
                            val stream = extractor.createStream()
                            streams++
                            val managedStream = AutoCloseable { stream.close(); releasedStreams++ }
                            managedStream.use {
                                stream.acceptWaveform(pcm, 16000)
                                stream.inputFinished()
                                checkpoint()
                                if (!stream.isReady()) throw InvalidMeasurement("extractor_not_ready")
                                checkpoint()
                                attempts++
                                val vector = stream.compute()
                                forwards++
                                checkpoint()
                                if (vector.size != dimension) throw InvalidMeasurement("embedding_dimension_mismatch")
                                if (vector.any { !it.isFinite() }) throw InvalidMeasurement("nonfinite_embedding")
                                var norm = 0.0
                                for (value in vector) norm = Math.hypot(norm, value.toDouble())
                                if (norm <= 1e-12) throw InvalidMeasurement("zero_embedding")
                                measured += window.copy(embedding = DoubleArray(vector.size) { vector[it].toDouble() })
                            }
                        } finally { addTime("embeddingComputeMs", computeStart) }
                    }
                }
            }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (invalid: InvalidMeasurement) {
            failure = invalid.reason
            failureClass = invalid.javaClass.simpleName
        } catch (error: Exception) {
            failure = "embedding_stage_failure"
            failureClass = error.javaClass.simpleName
        } catch (error: LinkageError) {
            failure = "native_link_failure"
            failureClass = error.javaClass.simpleName
        } finally { stages["embeddingStageMs"] = elapsed(embeddingStart) }

        checkpoint()
        if (failure != null) return result(native, false, mapOf("status" to "UNSUPPORTED", "reason" to failure))
        // Every stream and the extractor have left use{} before pure clustering.
        stage = "pure_refiner"
        val pureStart = System.nanoTime()
        val refined = try { WindowSpeakerRefiner.overcluster(native, measured, durationMs, config) }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) {
            failure = "pure_refiner_failure"
            failureClass = error.javaClass.simpleName
            null
        } finally { stages["refinerMs"] = elapsed(pureStart) }
        checkpoint()
        if (refined == null) return result(native, false, mapOf("status" to "UNSUPPORTED", "reason" to failure))
        // Centroids are derived biometric vectors too. Return them only in explicit QA.
        val pure = if (collectEvidence) refined.diagnostics else refined.diagnostics.filterKeys { it != "cluster_centroids" }
        return result(refined.turns, refined.accepted, pure)
    }
}
