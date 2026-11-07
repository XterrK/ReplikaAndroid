package ru.replika.domain

import org.junit.Assert.*
import org.junit.Test

class ParallelAsrDiarPolicyTest {
    private val gb = 1L shl 30
    private fun decide(cores: Int, plan: CpuPlan = CpuPlan.AUTO_V1, requested: Boolean = true,
        wordSlicing: Boolean = true, diarization: Boolean = true, available: Long = 2 * gb, low: Boolean = false,
        threads: Int = 0) = ParallelAsrDiarPolicy.decide(requested, wordSlicing, diarization,
        plan.resolve(threads, cores, refined = true), available, low, 240L shl 20, 40L shl 20)

    @Test fun eightCoresKeepDiarizationAtFourAndGiveAsrTwo() {
        val d = decide(8)
        assertTrue(d.enabled); assertEquals("parallel", d.reason)
        assertEquals(2, d.asrThreads); assertEquals(4, d.diarizationThreads); assertEquals(4, d.refinementThreads)
    }

    @Test fun fiveCoresHaveNoSpareCoreForAsr() {
        assertEquals("too_few_cores", decide(5).reason)
    }

    @Test fun diarizationKeepsItsThreadsAndAsrTakesTheRemainingCores() {
        for ((cores, expected) in listOf(4 to (2 to 1), 6 to (4 to 1), 7 to (4 to 2), 9 to (4 to 4), 12 to (4 to 4))) {
            val d = decide(cores)
            assertTrue(d.enabled)
            assertEquals("cores $cores", expected.first, d.diarizationThreads)
            assertEquals("cores $cores", expected.first, d.refinementThreads)
            assertEquals("cores $cores", expected.second, d.asrThreads)
        }
    }

    @Test fun fewerThanFourCoresStaySequentialWithResolvedThreads() {
        for (cores in 1..3) {
            val d = decide(cores)
            assertFalse(d.enabled); assertEquals("too_few_cores", d.reason)
            assertEquals(MlPolicy.automaticThreads(cores), d.asrThreads)
        }
    }

    @Test fun neverExceedsExplicitThreadsAndKeepsLegacyPins() {
        val d = decide(8, plan = CpuPlan.LEGACY, threads = 4)
        assertTrue(d.enabled)
        assertEquals(4, d.asrThreads); assertEquals(2, d.diarizationThreads); assertEquals(2, d.refinementThreads)
        val pinned6 = decide(6, plan = CpuPlan.LEGACY, threads = 4)
        assertEquals(2, pinned6.asrThreads); assertEquals(2, pinned6.diarizationThreads)
        val one = decide(8, plan = CpuPlan.LEGACY, threads = 1)
        assertEquals(1, one.asrThreads)
    }

    @Test fun sequentialReasons() {
        assertEquals("not_requested", decide(8, requested = false).reason)
        assertEquals("speaker_dependent_slicing", decide(8, wordSlicing = false).reason)
        assertEquals("no_diarization", decide(8, diarization = false).reason)
        assertEquals("low_memory", decide(8, low = true).reason)
        assertEquals("insufficient_memory", decide(8, available = 300L shl 20).reason)
        assertFalse(decide(8, available = 300L shl 20).enabled)
    }

    @Test fun memoryEstimateCoversBothModelsWithMargin() {
        val required = ParallelAsrDiarPolicy.requiredBytes(240L shl 20, 40L shl 20)
        assertEquals((1.5 * (280L shl 20)).toLong() + (256L shl 20), required)
        assertTrue(decide(8, available = required).enabled)
        assertFalse(decide(8, available = required - 1).enabled)
    }
}
