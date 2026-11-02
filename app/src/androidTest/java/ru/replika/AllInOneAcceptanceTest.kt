package ru.replika

import android.os.Build
import android.os.Process
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest

/**
 * Actual bundled-model acceptance, separate from the tiny isolated installer fixtures.
 * Stage only the public Russian WAV as files/integration-example.wav, never an external pack/models.
 * Run this class OR PipelineTest's two complete Worker tests to avoid duplicate expensive inference.
 */
@RunWith(AndroidJUnit4::class)
class AllInOneAcceptanceTest {
    private val app: ReplikaApp
        get() = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as ReplikaApp

    @Test
    fun preparedBundleHashesAndNoExtractionOnRepeatedLaunch() = runBlocking {
        Assume.assumeTrue("Requires an All-in-One variant", BuildConfig.BUNDLED_MODELS)
        withTimeout(10 * 60 * 1000L) { app.bundledModels.awaitReady() }
        val manifest = JSONObject(app.assets.open("models-lock.json").bufferedReader().use { it.readText() })
        val specs = manifest.getJSONArray("files")
        assertEquals("Every bundled backend and its dependencies must be installed", 8, specs.length())
        assertTrue(app.models.statuses().all { it.installed })
        app.models.requireReady("giga-v2")
        app.models.requireReady("whisper-tiny")

        val baseline = File(app.filesDir, "all-in-one-prepared-models.json")
        val previous = if (baseline.isFile) JSONObject(baseline.readText()) else null
        val rows = JSONArray()
        val before = linkedMapOf<String, Long>()
        val groups = linkedSetOf<String>()
        var bytes = 0L
        for (index in 0 until specs.length()) {
            val spec = specs.getJSONObject(index)
            val path = spec.getString("path")
            val model = app.models.file(path)
            assertTrue("Prepared model is absent: $path", model.isFile)
            assertEquals("Prepared model has the wrong size: $path", spec.getLong("size"), model.length())
            val actualHash = hash(model)
            assertEquals("Prepared model failed SHA-256: $path", spec.getString("sha256"), actualHash)
            val modified = model.lastModified()
            assertTrue("Missing modification timestamp: $path", modified > 0)
            before[path] = modified
            groups += spec.getString("group")
            bytes += model.length()
            rows.put(JSONObject().put("path", path).put("group", spec.getString("group"))
                .put("bytes", model.length()).put("sha256", actualHash).put("modifiedAtMs", modified))
        }
        assertEquals(setOf("giga-v2", "diar", "vad", "whisper-tiny"), groups)

        // A second readiness request must leave verified files untouched. This alone is not a cold restart.
        app.bundledModels.awaitReady()
        before.forEach { (path, modified) ->
            assertEquals("Verified model was unexpectedly rewritten: $path", modified, app.models.file(path).lastModified())
        }
        if (previous != null) {
            val previousRows = previous.getJSONArray("models")
            assertEquals(rows.length(), previousRows.length())
            val previousByPath = (0 until previousRows.length()).associate { index ->
                previousRows.getJSONObject(index).let { it.getString("path") to it }
            }
            for (index in 0 until rows.length()) {
                val current = rows.getJSONObject(index)
                val path = current.getString("path")
                val old = previousByPath[path] ?: error("Previously accepted model is missing: $path")
                assertEquals("Model bytes changed between acceptance launches: $path", old.getString("sha256"), current.getString("sha256"))
                assertEquals("Model was re-extracted between acceptance launches: $path", old.getLong("modifiedAtMs"), current.getLong("modifiedAtMs"))
            }
        }
        val evidence = device().put("models", rows).put("modelBytes", bytes).put("pid", Process.myPid())
            .put("previousSnapshotCompared", previous != null)
            .put("differentProcessObserved", previous != null && previous.optInt("pid", -1) != Process.myPid())
            .put("repeatReadinessPreservedModificationTimes", true)
            .put("scope", "Full prepared-file SHA-256 checks; rerun after an external force-stop/relaunch for a different-process comparison")
        baseline.writeText(evidence.toString(2))
    }

    @Test
    fun bothRealWorkerBackendsUseAutomaticallyPreparedBundle() {
        Assume.assumeTrue("Requires an All-in-One variant", BuildConfig.BUNDLED_MODELS)
        runBlocking { withTimeout(10 * 60 * 1000L) { app.bundledModels.awaitReady() } }
        val audio = File(app.filesDir, "integration-example.wav")
        assertTrue("Stage the official public Russian WAV as ${app.packageName}/files/integration-example.wav; do not stage models", audio.isFile)
        val started = SystemClock.elapsedRealtime()

        // Reuse the existing actual Worker regressions, including Room/export and the 100 ms pre-roll check.
        // No direct-ASR third run, no fixture text and no alternative ML implementation are introduced here.
        PipelineTest().completeRealGigaPipeline()
        PipelineTest().completeRealWhisperPipeline()

        val runs = JSONArray()
        runBlocking {
            for ((id, backend) in listOf("integration-real-giga" to "giga-v2", "integration-real-whisper" to "whisper-tiny")) {
                val recording = app.db.dao().recording(id) ?: error("Worker result was not persisted: $id")
                assertEquals("READY", recording.status)
                assertEquals(backend, recording.backend)
                val segments = app.db.dao().segmentList(id)
                assertTrue("Real Worker must persist actual nonblank transcript text", segments.isNotEmpty())
                assertTrue(segments.all { it.text.isNotBlank() && it.startMs >= 0 && it.endMs > it.startMs && it.endMs <= recording.durationMs })
                val diagnostics = JSONObject(recording.diagnostics)
                assertTrue("Real VAD did not report speech", diagnostics.getJSONArray("vadSpans").length() > 0)
                assertTrue("Real diarization did not report turns", diagnostics.getJSONArray("diarizationTurns").length() > 0)
                assertTrue("No actual ASR slices were recorded", diagnostics.getJSONArray("asrSlices").length() > 0)
                assertEquals(100, diagnostics.getInt("preRollMs"))
                runs.put(JSONObject().put("recordingId", id).put("backend", backend)
                    .put("segments", segments.size).put("diagnostics", diagnostics))
            }
        }
        val evidence = device().put("audioSha256", hash(audio)).put("audioFile", audio.name)
            .put("inputKind", "official public Russian single-speaker smoke fixture; not Russian multispeaker acceptance")
            .put("acceptanceElapsedMs", SystemClock.elapsedRealtime() - started)
            .put("elapsedScope", "Both sequential existing Worker tests including activity startup, Room and test polling; not pure ASR inference")
            .put("runs", runs).put("WER", "N/A: no independent manual reference")
            .put("physicalArm64Validation", "Not established by this instrumentation test; inspect recorded runtime ABI/device")
        File(app.filesDir, "all-in-one-real-worker-acceptance.json").writeText(evidence.toString(2))
    }

    private fun device() = JSONObject().put("package", app.packageName)
        .put("device", "${Build.MANUFACTURER} ${Build.MODEL}").put("api", Build.VERSION.SDK_INT)
        .put("abis", JSONArray(Build.SUPPORTED_ABIS.toList())).put("processIs64Bit", Process.is64Bit())

    private fun hash(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered(128 * 1024).use { input ->
            val buffer = ByteArray(128 * 1024)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
