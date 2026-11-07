package ru.replika.ml

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.SpeakerRefiner
import ru.replika.domain.Turn

/** All native entry points are replaced; these tests never initialize sherpa JNI. */
class DiarizationRefinerTest {
    private val turns = listOf(Turn(0, 3000, 0), Turn(3000, 6000, 1))
    private val planned get() = SpeakerRefiner.cleanWindows(turns, 6000)

    private class FakeFactory : DiarizationRefiner.EmbeddingFactory {
        val events = mutableListOf<String>()
        val inputs = mutableListOf<FloatArray>()
        var dimension = 2
        var ready = true
        var opened = 0
        var streams = 0
        var streamCloses = 0
        var sessionCloses = 0
        var failOpen = false
        var failCompute = false
        var failStreamClose = false
        var failSessionClose = false
        var onCompute: () -> Unit = {}
        var vector: (Int) -> FloatArray = { if (it < 3) floatArrayOf(1f, 0f) else floatArrayOf(0f, 1f) }

        override fun open(modelPath: String, threads: Int): DiarizationRefiner.EmbeddingSession {
            assertEquals("controlled-model.onnx", modelPath)
            assertEquals(2, threads)
            events += "open"
            if (failOpen) throw IllegalStateException("controlled open failure")
            opened++
            return object : DiarizationRefiner.EmbeddingSession {
                override val dimension: Int get() = this@FakeFactory.dimension
                override fun createStream(): DiarizationRefiner.EmbeddingStream {
                    assertEquals(0, sessionCloses)
                    assertEquals(streams, streamCloses)
                    val index = streams++
                    events += "stream:$index"
                    return object : DiarizationRefiner.EmbeddingStream {
                        var finished = false
                        override fun acceptWaveform(samples: FloatArray, sampleRate: Int) {
                            assertEquals(16000, sampleRate)
                            assertFalse(finished)
                            inputs += samples.copyOf()
                            events += "accept:$index"
                        }
                        override fun inputFinished() { finished = true; events += "finished:$index" }
                        override fun isReady(): Boolean { assertTrue(finished); return ready }
                        override fun compute(): FloatArray {
                            assertTrue(finished)
                            events += "compute:$index"
                            onCompute()
                            if (failCompute) throw IllegalStateException("controlled compute failure")
                            return vector(index)
                        }
                        override fun close() {
                            streamCloses++
                            events += "stream_close:$index"
                            if (failStreamClose) throw IllegalStateException("controlled stream close failure")
                        }
                    }
                }
                override fun close() {
                    sessionCloses++
                    events += "session_close"
                    if (failSessionClose) throw IllegalStateException("controlled session close failure")
                }
            }
        }
    }

    private fun pcm(start: Long, end: Long) = FloatArray(((end - start) * 16).toInt()) {
        start.toFloat() / 10000f + it.toFloat() / 1_000_000f
    }

    private fun invoke(factory: FakeFactory, evidence: Boolean = false,
        reader: suspend (Long, Long) -> FloatArray = ::pcm): DiarizationRefiner.Result = runBlocking {
        DiarizationRefiner.refineOriginalPcm(turns, 6000, "controlled-model.onnx", 2,
            reader, collectEvidence = evidence, embeddingFactory = factory)
    }

    @Test fun oneSessionEachPlannedWindowOriginalSamplesAndClosedResources() {
        val factory = FakeFactory()
        val reads = mutableListOf<Pair<Long, Long>>()
        val result = invoke(factory, evidence = true) { start, end ->
            reads += start to end
            pcm(start, end)
        }
        assertTrue(result.accepted)
        assertEquals(planned.map { it.startMs to it.endMs }, reads)
        assertEquals(1, factory.opened)
        assertEquals(planned.size, factory.streams)
        assertEquals(factory.streams, factory.streamCloses)
        assertEquals(1, factory.sessionCloses)
        assertEquals("session_close", factory.events.last())
        for ((i, window) in planned.withIndex()) assertArrayEquals(pcm(window.startMs, window.endMs), factory.inputs[i], 0f)
        assertEquals(planned.size, result.counts.embeddingForwardCalls)
        assertEquals(planned.size, result.counts.measuredWindows)
        assertEquals(planned.size, result.counts.releasedStreams)
        assertEquals(2, result.counts.embeddingDimension)
        assertEquals(planned.size, result.measuredWindowsQA!!.size)
        assertArrayEquals(doubleArrayOf(1.0, 0.0), result.measuredWindowsQA.first().embedding, 0.0)
        assertEquals(true, result.diagnostics["nativeResourcesReleasedBeforeRefiner"])
        assertEquals("SUPPORTED", result.diagnostics["status"])
        assertTrue(result.timingsMs.getValue("totalMs") >= result.timingsMs.getValue("embeddingStageMs"))
    }

    @Test fun normalResultsRetainNoRawOrCentroidEmbeddingVectors() {
        val result = invoke(FakeFactory())
        assertTrue(result.accepted)
        assertNull(result.measuredWindowsQA)
        val refiner = result.diagnostics.getValue("refiner") as Map<*, *>
        assertFalse(refiner.containsKey("cluster_centroids"))
        assertEquals("not evaluated by this adapter", result.diagnostics["qualityAcceptance"])
    }

    @Test fun cancellationDuringReadClosesSessionBeforeCreatingAnyStream() {
        val factory = FakeFactory()
        assertThrows(CancellationException::class.java) {
            runBlocking {
                DiarizationRefiner.refineOriginalPcm(turns, 6000, "controlled-model.onnx", 2,
                    { start, end -> currentCoroutineContext()[Job]!!.cancel(); pcm(start, end) },
                    embeddingFactory = factory)
            }
        }
        assertEquals(0, factory.streams)
        assertEquals(1, factory.sessionCloses)
    }

    @Test fun cancellationAfterComputeClosesStreamAndSessionAndPreservesCancellation() {
        val factory = FakeFactory().also { it.failStreamClose = true }
        val error = assertThrows(CancellationException::class.java) {
            runBlocking {
                val job = currentCoroutineContext()[Job]!!
                factory.onCompute = { job.cancel() }
                DiarizationRefiner.refineOriginalPcm(turns, 6000, "controlled-model.onnx", 2,
                    ::pcm, embeddingFactory = factory)
            }
        }
        assertEquals(1, factory.streamCloses)
        assertEquals(1, factory.sessionCloses)
        assertTrue(error.suppressed.any { it is IllegalStateException })
    }

    @Test fun workerStoppedAfterReadIsCancellationAndDoesNotAdvanceToNativeCompute() {
        val factory = FakeFactory()
        var stopped = false
        assertThrows(CancellationException::class.java) {
            runBlocking {
                DiarizationRefiner.refineOriginalPcm(turns, 6000, "controlled-model.onnx", 2,
                    { start, end -> stopped = true; pcm(start, end) }, isStopped = { stopped },
                    embeddingFactory = factory)
            }
        }
        assertEquals(0, factory.streams)
        assertEquals(1, factory.sessionCloses)
    }

    @Test fun malformedOriginalWindowCannotBecomePaddedOrGainedSpeech() {
        for ((samples, reason) in listOf(FloatArray(1) to "invalid_pcm_sample_count",
                FloatArray(24000) { Float.NaN } to "nonfinite_original_pcm")) {
            val factory = FakeFactory()
            val result = invoke(factory) { _, _ -> samples }
            assertFalse(result.accepted)
            assertEquals(turns, result.turns)
            assertEquals(reason, result.diagnostics["reason"])
            assertEquals(0, factory.streams)
            assertEquals(1, factory.sessionCloses)
        }
    }

    @Test fun invalidOrUnreadyEmbeddingsAreExplicitlyUnsupportedWithCleanup() {
        val variants = listOf(
            Pair(FakeFactory().also { it.ready = false }, "extractor_not_ready"),
            Pair(FakeFactory().also { it.vector = { floatArrayOf(1f) } }, "embedding_dimension_mismatch"),
            Pair(FakeFactory().also { it.vector = { floatArrayOf(Float.NaN, 0f) } }, "nonfinite_embedding"),
            Pair(FakeFactory().also { it.vector = { floatArrayOf(0f, 0f) } }, "zero_embedding"),
        )
        for ((factory, reason) in variants) {
            val result = invoke(factory, evidence = true)
            assertFalse(result.accepted)
            assertEquals(reason, result.diagnostics["reason"])
            assertEquals(turns, result.turns)
            assertTrue(result.measuredWindowsQA!!.isEmpty())
            assertEquals(1, factory.streamCloses)
            assertEquals(1, factory.sessionCloses)
        }
    }

    @Test fun computeAndCloseFailuresDoNotClaimComputationalSupport() {
        for (factory in listOf(FakeFactory().also { it.failCompute = true },
                FakeFactory().also { it.failSessionClose = true })) {
            val result = invoke(factory)
            assertFalse(result.accepted)
            assertEquals(turns, result.turns)
            assertEquals("embedding_stage_failure", result.diagnostics["reason"])
            assertEquals(1, factory.sessionCloses)
            if (factory.failSessionClose) assertEquals(false, result.diagnostics["nativeResourcesReleasedBeforeRefiner"])
        }
        val unopened = FakeFactory().also { it.failOpen = true }
        assertFalse(invoke(unopened).accepted)
        assertEquals(0, unopened.streams)
    }

    @Test fun emptyOrNoCleanActivityDoesNotLoadAnEmbeddingModel() = runBlocking {
        val factory = FakeFactory()
        val empty = DiarizationRefiner.refineOriginalPcm(emptyList(), 0, "controlled-model.onnx", 2,
            { _, _ -> error("No PCM read expected") }, embeddingFactory = factory)
        assertTrue(empty.accepted)
        assertEquals("EMPTY", empty.diagnostics["status"])
        val short = DiarizationRefiner.refineOriginalPcm(listOf(Turn(0, 500, 0)), 500,
            "controlled-model.onnx", 2, { _, _ -> error("No PCM read expected") }, embeddingFactory = factory)
        assertFalse(short.accepted)
        assertEquals(0, factory.opened)
    }

    @Test fun frozenConfigurationAndThreadPolicyFailBeforeModelAccess() {
        val factory = FakeFactory()
        assertThrows(IllegalArgumentException::class.java) {
            runBlocking { DiarizationRefiner.refineOriginalPcm(turns, 6000, "controlled-model.onnx", 1,
                ::pcm, embeddingFactory = factory) }
        }
        assertThrows(IllegalArgumentException::class.java) {
            runBlocking { DiarizationRefiner.refineOriginalPcm(turns, 6000, "controlled-model.onnx", 2,
                ::pcm, config = DiarizationRefiner.SELECTED_CONFIG.copy(tau = .35), embeddingFactory = factory) }
        }
        assertEquals(0, factory.opened)
    }
}
