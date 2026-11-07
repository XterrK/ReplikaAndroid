package ru.replika.ml

import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.MlPolicy

/** Fake platform reads/listeners and monotonic clock; no Android service or native inference. */
class ThermalGatePlan19Test {
    @Test fun noneUnavailableAndUnknownStatusesNeverWait() = runBlocking {
        for (status in listOf(-1, 0, 1, 2, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
            assertEquals(0L, ThermalGate.await({ status }, { error("Must not wait") },
                { error("Must not pause") }, { 123L }))
            assertFalse(MlPolicy.coolingRequired(status))
        }
        for (status in 3..6) assertTrue(MlPolicy.coolingRequired(status))
    }

    @Test fun knownSevereWaitsUntilModerateAndCallbackOccursOnce() = runBlocking {
        var reads = 0; var callbacks = 0; var pauses = 0; var now = 0L
        val result = ThermalGate.await({ listOf(3, 4, 2)[reads++] }, { callbacks++ },
            { pauses++; now += 3000 }, { now })
        assertEquals(6000L, result)
        assertEquals(1, callbacks)
        assertEquals(2, pauses)
    }

    @Test fun getterFailureOrLossOfStatusCannotCauseAnInfiniteCoolingWait() = runBlocking {
        assertEquals(0L, ThermalGate.await({ throw IllegalStateException("service unavailable") },
            { error("Must not wait") }, { error("Must not pause") }, { 0L }))
        var status = 3; var now = 0L
        assertEquals(3000L, ThermalGate.await({ status }, {}, { status = -1; now += 3000 }, { now }))
    }

    @Test fun realSevereRemainsCancellableAndDoesNotAdvanceToInference() = runBlocking {
        val waiting = CompletableDeferred<Unit>()
        var inference = false
        val job = launch {
            ThermalGate.await({ 6 }, { waiting.complete(Unit) }, { awaitCancellation() }, { 0L })
            inference = true
        }
        waiting.await()
        assertFalse(job.isCompleted)
        assertFalse(inference)
        job.cancelAndJoin()
        assertTrue(job.isCancelled)
        assertFalse(inference)
    }

    @Test fun cancellationIsCheckedBeforeTheFirstPlatformReadAndNeverSwallowed() {
        var reads = 0
        assertThrows(CancellationException::class.java) {
            runBlocking {
                currentCoroutineContext()[Job]!!.cancel()
                ThermalGate.await({ reads++; 0 }, {}, clock = { 0L })
            }
        }
        assertEquals(0, reads)
        assertThrows(CancellationException::class.java) {
            runBlocking { ThermalGate.await({ throw CancellationException("cancelled") }, {}, clock = { 0L }) }
        }
    }

    @Test fun unsupportedApiNeverReadsOrRegistersAndPreservesUnavailableReason() {
        val source = ThermalStatusSource(false, { error("No getter") }, { error("No registration") },
            { error("No removal") }, "api_below_29")
        source.start()
        assertEquals(-1, source.status())
        assertEquals(-1, source.observe(3))
        assertFalse(source.listenerRegistered)
        assertEquals("api_below_29", source.unavailableReason)
        source.close()
    }

    @Test fun sourceGetterFailureAndUnknownCodeRecoverToValidSevereOnNextRead() {
        var fail = true; var value = 3
        val source = ThermalStatusSource(true, { if (fail) throw SecurityException("unavailable") else value })
        assertEquals(-1, source.status())
        assertEquals("read_failed", source.unavailableReason)
        fail = false; value = Int.MAX_VALUE
        assertEquals(-1, source.status())
        assertEquals("unknown_status", source.unavailableReason)
        value = 3
        assertEquals(3, source.status())
        assertNull(source.unavailableReason)
        source.close()
    }

    @Test fun failedListenerRegistrationStillPollsSevereUntilModerateAndDoesNotRemove() = runBlocking {
        var reads = 0; var removes = 0; var value = 3; var now = 0L; var waited = false
        val source = ThermalStatusSource(true, { reads++; value }, { throw IllegalStateException("unavailable") }, { removes++ })
        source.start(); source.start()
        assertFalse(source.listenerRegistered)
        assertTrue(source.listenerRegistrationFailed)
        assertEquals("listener_registration_failed", source.listenerFailureReason)
        assertEquals(3000L, ThermalGate.await(source::status, { waited = true },
            { assertTrue(waited); value = 2; now += 3000 }, { now }))
        assertEquals(2, reads)
        assertNull(source.unavailableReason)
        source.close()
        assertEquals(0, removes)
    }

    @Test fun listenerCloseIsIdempotentAndRemovalFailureCannotMaskProcessingResult() {
        var adds = 0; var removes = 0
        val source = ThermalStatusSource(true, { 0 }, { adds++ }, { removes++; throw IllegalStateException("gone") })
        source.start(); source.start()
        assertTrue(source.listenerRegistered)
        assertEquals(0, source.status())
        source.close(); source.close()
        assertFalse(source.listenerRegistered)
        assertEquals(1, adds)
        assertEquals(1, removes)
        assertEquals(-1, source.status())
        assertEquals("closed", source.unavailableReason)
        assertEquals("listener_removal_failed", source.listenerFailureReason)
    }

    @Test fun sourcePreservesCancellationAndDoesNotSwallowFatalErrors() {
        val source = ThermalStatusSource(true, { throw CancellationException("cancelled") })
        assertThrows(CancellationException::class.java) { source.status() }
        val fatal = ThermalStatusSource(true, { throw AssertionError("fatal") })
        assertThrows(AssertionError::class.java) { fatal.status() }
    }
}
