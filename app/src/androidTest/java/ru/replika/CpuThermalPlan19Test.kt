package ru.replika

import android.os.Build
import android.os.PowerManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.domain.CpuPlan
import ru.replika.ml.PipelineTelemetry
import ru.replika.ml.ThermalGate
import java.io.File

/** Real PowerManager contract checks only. No audio, model, Worker or neural calls. */
@RunWith(AndroidJUnit4::class)
class CpuThermalPlan19Test {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private val pm get() = context.getSystemService(PowerManager::class.java)
    private fun status() = if (Build.VERSION.SDK_INT >= 29) pm.currentThermalStatus else -1
    private fun shell(command: String) = instrumentation.uiAutomation.executeShellCommand(command).use { fd ->
        java.io.FileInputStream(fd.fileDescriptor).bufferedReader().readText()
    }
    private suspend fun awaitStatus(expected: Int) {
        withTimeout(5000) { while (status() != expected) delay(50) }
    }
    private fun save(name: String, value: JSONObject) = File(context.filesDir, name).writeText(value.toString(2))

    @Test fun actualPowerManagerNoneSevereResumeCancellationAndReset(): Unit = runBlocking {
        assumeTrue("Thermal override is dedicated-emulator only", Build.VERSION.SDK_INT >= 29 &&
            Build.HARDWARE in listOf("ranchu", "goldfish"))
        val before = status()
        val trace = PipelineTelemetry(context)
        val jobs = mutableListOf<Job>()
        val proof = JSONObject().put("scope", "Real emulator PowerManager behavior; no NN/phone heat or speed acceptance")
            .put("api", Build.VERSION.SDK_INT).put("thermalBefore", before).put("newModelInference", false)
        try {
            shell("cmd thermalservice override-status 0")
            awaitStatus(0)
            val noneWait = withTimeout(1000) { trace.cool { error("NONE must not wait") } }
            assertEquals(0L, noneWait)
            assertTrue(trace.snapshot().getBoolean("thermalStatusAvailable"))

            shell("cmd thermalservice override-status 3")
            awaitStatus(3)
            val waiting = CompletableDeferred<Unit>()
            var advanced = false
            val hot = async { trace.cool { waiting.complete(Unit) }; advanced = true }
            jobs += hot
            withTimeout(5000) { waiting.await() }
            assertFalse(advanced)
            assertFalse(hot.isCompleted)
            shell("cmd thermalservice override-status 2")
            awaitStatus(2)
            withTimeout(6000) { hot.await() }
            assertTrue(advanced)

            shell("cmd thermalservice override-status 4")
            awaitStatus(4)
            val criticalWaiting = CompletableDeferred<Unit>()
            var cancelledAdvanced = false
            val critical = launch {
                ThermalGate.await(::status, { criticalWaiting.complete(Unit) })
                cancelledAdvanced = true
            }
            jobs += critical
            withTimeout(5000) { criticalWaiting.await() }
            critical.cancelAndJoin()
            assertTrue(critical.isCancelled)
            assertFalse(cancelledAdvanced)
            val cores = Runtime.getRuntime().availableProcessors()
            proof.put("noneWaitMs", noneWait).put("blockedAtSevere", true).put("resumedAtModerate", true)
                .put("criticalCancellationPreserved", true).put("telemetry", trace.snapshot())
                .put("cpuPolicy", JSONObject(CpuPlan.AUTO_V1.resolve(0, cores, true).asMap()))
        } finally {
            withContext(NonCancellable) {
                jobs.forEach { it.cancel() }; jobs.joinAll()
                try {
                    shell("cmd thermalservice reset")
                    proof.put("overrideResetRequested", true).put("thermalAfterReset", status())
                } finally {
                    trace.close()
                    save("cpu-thermal-plan19-api29plus.json", proof)
                }
            }
        }
    }

    @Test fun pre29TelemetryIsUnavailableWithoutCoolingWait(): Unit = runBlocking {
        assumeTrue("Use a real API26-28 device/emulator", Build.VERSION.SDK_INT < 29)
        val trace = PipelineTelemetry(context)
        try {
            assertEquals(-1, trace.thermalStatus())
            val elapsed = withTimeout(1000) { trace.cool { error("Unavailable API must not wait") } }
            assertEquals(0L, elapsed)
            val snapshot = trace.snapshot()
            assertFalse(snapshot.getBoolean("thermalApiSupported"))
            assertFalse(snapshot.getBoolean("thermalStatusAvailable"))
            assertFalse(snapshot.getBoolean("thermalListenerRegistered"))
            assertEquals("api_below_29", snapshot.getString("thermalUnavailableReason"))
            save("cpu-thermal-plan19-pre29.json", JSONObject().put("api", Build.VERSION.SDK_INT)
                .put("waitMs", elapsed).put("newModelInference", false).put("telemetry", snapshot))
        } finally { trace.close() }
    }
}
