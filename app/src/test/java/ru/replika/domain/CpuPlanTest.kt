package ru.replika.domain

import org.junit.Assert.*
import org.junit.Test

class CpuPlanTest {
    @Test fun missingHistoricalPlanIsLegacyAndUnknownPlansFail() {
        assertEquals(CpuPlan.LEGACY, CpuPlan.fromPersistedId(null))
        assertEquals(CpuPlan.LEGACY, CpuPlan.fromPersistedId("v16"))
        assertEquals(CpuPlan.AUTO_V1, CpuPlan.fromPersistedId("auto_v1"))
        for (invalid in listOf("", "auto", "AUTO_V1", "cpu_future")) {
            assertThrows(IllegalStateException::class.java) { CpuPlan.fromPersistedId(invalid) }
        }
    }

    @Test fun autoMappingUsesValidatedBucketsAndNormalizesUnavailableCoreCounts() {
        for ((cores, expected) in listOf(Int.MIN_VALUE to 1, -1 to 1, 0 to 1, 1 to 1,
                2 to 1, 3 to 2, 4 to 2, 5 to 4, 8 to 4, Int.MAX_VALUE to 4)) {
            val resolved = CpuPlan.AUTO_V1.resolve(0, cores, true)
            assertEquals(expected, MlPolicy.automaticThreads(cores))
            assertEquals(expected, resolved.asrThreads)
            assertEquals(expected, resolved.diarizationThreads)
            assertEquals(expected, resolved.refinementThreads)
            assertEquals(cores.coerceAtLeast(1), resolved.availableCores)
            assertEquals(0, resolved.requestedThreads)
            assertFalse(resolved.diarizationPinned)
            assertFalse(resolved.refinementPinned)
        }
    }

    @Test fun explicitOverridesStayExplicitEvenOnOneCore() {
        for (threads in listOf(1, 2, 4)) {
            val result = CpuPlan.AUTO_V1.resolve(threads, 1, true)
            assertEquals(threads, result.asrThreads)
            assertEquals(threads, result.diarizationThreads)
            assertEquals(threads, result.refinementThreads)
            assertEquals(threads, result.requestedThreads)
        }
    }

    @Test fun legacyRefinedStagesPinTwoWhileRespectingUserAsrThreads() {
        for (requested in listOf(1, 2, 4)) {
            val result = CpuPlan.LEGACY.resolve(requested, 8, true)
            assertEquals(requested, result.asrThreads)
            assertEquals(2, result.diarizationThreads)
            assertEquals(2, result.refinementThreads)
            assertTrue(result.diarizationPinned)
            assertTrue(result.refinementPinned)
        }
        val historical = CpuPlan.fromPersistedId(null).resolve(2, 8, false)
        assertEquals(2, historical.asrThreads)
        assertEquals(2, historical.diarizationThreads)
        assertNull(historical.refinementThreads)
        assertFalse(historical.diarizationPinned)
    }

    @Test fun nonRefinedModesHaveNoRefinementThreadClaimAndRetainNullKey() {
        val result = CpuPlan.AUTO_V1.resolve(0, 8, false)
        assertEquals(4, result.asrThreads)
        assertEquals(4, result.diarizationThreads)
        assertNull(result.refinementThreads)
        assertEquals(setOf("plan", "requestedThreads", "availableCores", "asrThreads", "diarizationThreads",
            "refinementThreads", "diarizationPinned", "refinementPinned"), result.asMap().keys)
        assertTrue(result.asMap().containsKey("refinementThreads"))
        assertNull(result.asMap()["refinementThreads"])
        assertEquals("auto_v1", result.asMap()["plan"])
    }

    @Test fun autoRequiresOptInAndInvalidRequestsNeverBecomeImplicitDefaults() {
        assertThrows(IllegalArgumentException::class.java) { CpuPlan.LEGACY.resolve(0, 8, true) }
        for (plan in CpuPlan.entries) for (value in listOf(-1, 3, 5, Int.MIN_VALUE, Int.MAX_VALUE)) {
            assertThrows(IllegalArgumentException::class.java) { plan.resolve(value, 8, false) }
        }
        for (value in listOf(1, 4)) {
            assertThrows(IllegalArgumentException::class.java) { CpuPlan.LEGACY.requireRefinementThreads(value) }
        }
        CpuPlan.LEGACY.requireRefinementThreads(2)
        for (value in listOf(1, 2, 4)) CpuPlan.AUTO_V1.requireRefinementThreads(value)
        assertThrows(IllegalArgumentException::class.java) { CpuPlan.AUTO_V1.requireRefinementThreads(0) }
    }
}
