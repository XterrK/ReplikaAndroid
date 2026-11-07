package ru.replika

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeFalse
import org.junit.Test
import ru.replika.domain.SpeakerRefiner
import ru.replika.domain.Turn
import ru.replika.domain.WindowSpeakerRefiner
import ru.replika.ml.DiarizationEvidence
import java.io.File
import java.math.BigDecimal
import java.math.BigInteger
import java.nio.file.FileAlreadyExistsException
import java.nio.file.Files
import java.nio.channels.FileChannel
import java.nio.file.StandardOpenOption
import java.security.MessageDigest
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

class DiarizationEvidenceTest {
    private val id = "12345678-1234-5678-9012-123456789abc"
    private fun window(start: Long = 0, end: Long = 1500, speaker: Int = 2,
                       vector: DoubleArray = doubleArrayOf(.25, -.75), clean: Boolean = true) =
        SpeakerRefiner.EmbeddingWindow(start, end, speaker, vector, clean)
    private fun metadata() = linkedMapOf<String, Any?>("audioMs" to 2000L, "embeddingDimension" to 2,
        "model" to "реальная модель", "optional" to null)
    private fun hash(file: File) = MessageDigest.getInstance("SHA-256").digest(file.readBytes())
        .joinToString("") { "%02x".format(it) }
    private fun payloadFiles(directory: File) = directory.listFiles()!!.filter {
        it.name != DiarizationEvidence.PUBLICATION_LOCK_FILE_NAME
    }
    private inline fun temporary(test: (File) -> Unit) {
        val directory = Files.createTempDirectory("diar-evidence-test-").toFile()
        try { test(directory) } finally { directory.deleteRecursively() }
    }
    private inline fun invalid(block: () -> Unit) {
        try { block(); fail("Expected invalid input") } catch (_: IllegalArgumentException) { }
    }
    private fun waitUntil(message: String, condition: () -> Boolean) {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10)
        while (!condition()) {
            if (System.nanoTime() >= deadline) fail(message)
            Thread.sleep(10)
        }
    }
    private fun child(mode: String, directory: File, recording: String, coordination: File): Process {
        val binary = if (System.getProperty("os.name").startsWith("Windows")) "java.exe" else "java"
        // Gradle's test worker may expose only its bootstrap JAR in java.class.path.
        val classpath = (System.getProperty("java.class.path").split(File.pathSeparator) +
            listOf(DiarizationEvidenceProcessProbe::class.java, DiarizationEvidence::class.java,
                SpeakerRefiner::class.java, JSONObject::class.java, Unit::class.java).mapNotNull {
                it.protectionDomain?.codeSource?.location?.toURI()?.let(::File)?.path
            }).distinct().joinToString(File.pathSeparator)
        return ProcessBuilder(File(System.getProperty("java.home"), "bin/$binary").path,
            "-Xmx48m", "-XX:ActiveProcessorCount=1", "-cp", classpath,
            "ru.replika.DiarizationEvidenceProcessProbe", mode, directory.path, id, recording, coordination.path)
            .redirectErrorStream(true).start()
    }

    @Test fun writesActualUtf8VectorsAndRetainsRecursiveNulls() = temporary { directory ->
        val diagnostic = linkedMapOf<String, Any?>("reason" to null,
            "nested" to linkedMapOf("minimum_similarity" to null, "items" to listOf(null, "да 😀\n\"\\")))
        val info = DiarizationEvidence.write(directory, id.uppercase(), "запись/не путь", metadata(),
            listOf(window(), window(1500, 2000, 7, doubleArrayOf(-1.0, .125), false)), diagnostic)
        assertFalse(info.truncated)
        assertNull(info.reason)
        assertEquals("diarization-$id.json", info.relativeFileName)
        val file = File(directory, info.relativeFileName!!)
        assertEquals(file.length(), info.bytes)
        assertEquals(hash(file), info.sha256)
        val raw = file.readText(Charsets.UTF_8)
        assertTrue(raw.contains("реальная модель"))
        val json = JSONObject(raw)
        assertEquals(id, json.getString("work_id"))
        assertEquals("запись/не путь", json.getString("recording_id"))
        assertTrue(json.getJSONObject("metadata").has("optional"))
        assertSame(JSONObject.NULL, json.getJSONObject("metadata").get("optional"))
        val nested = json.getJSONObject("diagnostics").getJSONObject("nested")
        assertTrue(nested.has("minimum_similarity"))
        assertSame(JSONObject.NULL, nested.get("minimum_similarity"))
        assertEquals("да 😀\n\"\\", nested.getJSONArray("items").getString(1))
        val words = json.getJSONArray("windows")
        assertEquals(2, words.length())
        val first = words.getJSONObject(0)
        assertEquals(setOf("start_ms", "end_ms", "speaker", "embedding", "clean"), first.keys().asSequence().toSet())
        assertEquals(0L, first.getLong("start_ms"))
        assertEquals(1500L, first.getLong("end_ms"))
        assertEquals(2, first.getInt("speaker"))
        assertEquals(-.75, first.getJSONArray("embedding").getDouble(1), 0.0)
        assertFalse(words.getJSONObject(1).getBoolean("clean"))
        assertFalse(json.getBoolean("truncated"))
        assertEquals(listOf(info.relativeFileName), payloadFiles(directory).map { it.name })
    }

    @Test fun compactJsonRetainsNullKeysAndPrimitiveArrays() {
        val json = DiarizationEvidence.jsonObject(linkedMapOf("null" to null,
            "nested" to linkedMapOf("null" to null), "array" to arrayOf(null, "я"),
            "ints" to intArrayOf(1, 2), "floats" to floatArrayOf(.5f), "bools" to booleanArrayOf(true)))
        assertTrue(json.has("null"))
        assertSame(JSONObject.NULL, json.get("null"))
        assertTrue(json.getJSONObject("nested").has("null"))
        assertSame(JSONObject.NULL, json.getJSONArray("array").get(0))
        assertEquals(2, json.getJSONArray("ints").getInt(1))
        assertTrue(json.getJSONArray("bools").getBoolean(0))
    }

    @Test fun actualWindowRefinerDiagnosticsPreserveIntegerCountersAndNulls() = temporary { directory ->
        val turns = listOf(Turn(0, 3000, 0), Turn(1000, 4000, 1))
        val windows = SpeakerRefiner.cleanWindows(turns, 4000).map {
            it.copy(embedding = doubleArrayOf(1.0, 0.0))
        }
        val result = WindowSpeakerRefiner.overcluster(turns, windows, 4000,
            WindowSpeakerRefiner.Config(tau = .36, method = "average", reassignSmall = true))
        assertTrue(result.accepted)
        val diagnostic = result.diagnostics
        assertEquals(BigInteger("6000"), diagnostic["original_speaker_time_ms"])
        assertEquals(BigInteger("4000"), diagnostic["output_speaker_time_ms"])
        assertEquals(BigInteger("2000"), diagnostic["speaker_time_collapsed_ms"])
        val assignments = diagnostic["assignment_method_speaker_ms"] as Map<*, *>
        assertTrue(assignments.isNotEmpty())
        assertTrue(assignments.values.all { it is BigInteger })
        val compact = DiarizationEvidence.jsonObject(diagnostic)
        assertEquals(6000L, compact.getLong("original_speaker_time_ms"))
        assertEquals(2000L, compact.getLong("speaker_time_collapsed_ms"))
        assertTrue(compact.getJSONObject("config").has("minimum_reassignment_similarity"))
        assertSame(JSONObject.NULL, compact.getJSONObject("config").get("minimum_reassignment_similarity"))
        val info = DiarizationEvidence.write(directory, id, "actual-refiner", mapOf("audioMs" to 4000,
            "embeddingDimension" to 2), windows, diagnostic)
        assertFalse(info.truncated)
        val raw = File(directory, info.relativeFileName!!).readText(Charsets.UTF_8)
        assertTrue(raw.contains("\"original_speaker_time_ms\":6000"))
        assertTrue(raw.contains("\"speaker_time_collapsed_ms\":2000"))
        val saved = JSONObject(raw).getJSONObject("diagnostics")
        val savedAssignments = saved.getJSONObject("assignment_method_speaker_ms")
        for ((method, duration) in assignments) assertEquals(duration.toString(), savedAssignments.get(method as String).toString())
        assertSame(JSONObject.NULL, saved.getJSONObject("config").get("minimum_reassignment_similarity"))
        assertEquals(hash(File(directory, info.relativeFileName!!)), info.sha256)
    }

    @Test fun largeIntegersKeepExactDecimalBytesAndRemainBudgetBounded() = temporary { directory ->
        val digits = "123456789012345678901234567890123456789012345678901234567890"
        val huge = BigInteger(digits)
        val info = DiarizationEvidence.write(directory, id, "integers", metadata(), listOf(window()),
            mapOf("positive" to huge, "negative" to huge.negate(), "zero" to BigInteger.ZERO))
        val file = File(directory, info.relativeFileName!!)
        val raw = file.readText(Charsets.UTF_8)
        assertTrue(raw.contains("\"positive\":$digits"))
        assertTrue(raw.contains("\"negative\":-$digits"))
        assertTrue(raw.contains("\"zero\":0"))
        assertFalse(raw.contains("\"positive\":\""))
        assertEquals(file.length(), info.bytes)
        file.delete()
        val refused = DiarizationEvidence.write(directory, id, "integers", metadata(), listOf(window()),
            mapOf("oversized" to BigInteger.ONE.shiftLeft(200000)), maxBytes = 512)
        assertTrue(refused.truncated)
        assertEquals("budget_exceeded", refused.reason)
        assertNull(refused.relativeFileName)
        assertTrue(payloadFiles(directory).isEmpty())
        invalid { DiarizationEvidence.jsonObject(mapOf("unknownNumber" to BigDecimal("1.25"))) }
    }

    @Test fun budgetIncludesUtf8AndPublishesNoPartialFile() = temporary { directory ->
        val info = DiarizationEvidence.write(directory, id, "recording", metadata(), listOf(window()),
            mapOf("large" to "я".repeat(5000)), maxBytes = 1000)
        assertTrue(info.truncated)
        assertEquals("budget_exceeded", info.reason)
        assertNull(info.relativeFileName)
        assertNull(info.sha256)
        assertEquals(0L, info.bytes)
        assertTrue(payloadFiles(directory).isEmpty())
    }

    @Test fun exactActualByteBudgetSucceedsAndOneLessRefuses() = temporary { directory ->
        val info = DiarizationEvidence.write(directory, id, "recording", metadata(), listOf(window()), emptyMap())
        val raw = File(directory, info.relativeFileName!!).readBytes()
        File(directory, info.relativeFileName!!).delete()
        val exact = DiarizationEvidence.write(directory, id, "recording", metadata(), listOf(window()), emptyMap(), raw.size)
        assertFalse(exact.truncated)
        assertArrayEquals(raw, File(directory, exact.relativeFileName!!).readBytes())
        File(directory, exact.relativeFileName!!).delete()
        val refused = DiarizationEvidence.write(directory, id, "recording", metadata(), listOf(window()), emptyMap(), raw.size - 1)
        assertTrue(refused.truncated)
        assertTrue(payloadFiles(directory).isEmpty())
    }

    @Test fun hardWindowLimitRefusesBeforeVectorCopies() = temporary { directory ->
        val repeated = List(DiarizationEvidence.MAX_WINDOWS + 1) { window() }
        val info = DiarizationEvidence.write(directory, id, "recording", metadata(), repeated, emptyMap())
        assertTrue(info.truncated)
        assertEquals("window_limit_exceeded", info.reason)
        assertTrue(payloadFiles(directory).isEmpty())
    }

    @Test fun existingFileAndSymlinkAreNeverOverwritten() = temporary { directory ->
        // Creating symlinks needs Developer Mode or admin rights on Windows; Android and Linux hosts run it.
        assumeFalse(isWindowsHost)
        val target = File(directory, "diarization-$id.json")
        target.writeText("original evidence")
        try {
            DiarizationEvidence.write(directory, id, "recording", metadata(), listOf(window()), emptyMap())
            fail("Existing file must reject")
        } catch (_: FileAlreadyExistsException) { }
        assertEquals("original evidence", target.readText())
        target.delete()
        val outside = Files.createTempFile("diar-sentinel-", ".json")
        try {
            Files.write(outside, "outside".toByteArray())
            Files.createSymbolicLink(target.toPath(), outside)
            try {
                DiarizationEvidence.write(directory, id, "recording", metadata(), listOf(window()), emptyMap())
                fail("Existing symlink must reject")
            } catch (_: FileAlreadyExistsException) { }
            assertEquals("outside", String(Files.readAllBytes(outside)))
        } finally { Files.deleteIfExists(outside) }
    }

    @Test fun concurrentSameWorkPublishesExactlyOneCompleteFile() = temporary { directory ->
        val executor = Executors.newFixedThreadPool(2)
        val start = CountDownLatch(1)
        try {
            val jobs = (1..2).map { number -> executor.submit<Boolean> {
                start.await()
                try {
                    val info = DiarizationEvidence.write(directory, id, "recording-$number", metadata(), listOf(window()), emptyMap())
                    assertFalse(info.truncated)
                    true
                } catch (_: FileAlreadyExistsException) { false }
            } }
            start.countDown()
            assertEquals(1, jobs.count { it.get() })
            val only = payloadFiles(directory).single()
            assertEquals("diarization-$id.json", only.name)
            assertTrue(JSONObject(only.readText()).getString("recording_id") in listOf("recording-1", "recording-2"))
        } finally { executor.shutdownNow() }
    }

    @Test fun twoRealProcessesCollideWithoutOverwritingTheWinningBytes() = temporary { directory ->
        val coordination = Files.createTempDirectory("diar-evidence-process-coordination-").toFile()
        val children = mutableListOf<Process>()
        try {
            children += child("write", directory, "writer-one", coordination)
            children += child("write", directory, "writer-two", coordination)
            waitUntil("Both process writers must reach the barrier") {
                File(coordination, "ready-writer-one").isFile && File(coordination, "ready-writer-two").isFile
            }
            File(coordination, "go").writeText("publish")
            val output = children.map { process ->
                assertTrue("Child writer timeout", process.waitFor(15, TimeUnit.SECONDS))
                val text = process.inputStream.bufferedReader().readText()
                assertEquals(text, 0, process.exitValue())
                text
            }
            val written = output.single { it.contains("WRITTEN ") }.trim().split(" ")
            assertEquals(1, output.count { it.contains("EXISTS ") })
            val file = payloadFiles(directory).single()
            val bytes = file.readBytes()
            assertEquals(written[2], hash(file))
            assertEquals(written[1], JSONObject(file.readText()).getString("recording_id"))
            try {
                DiarizationEvidence.write(directory, id, "later-loser", metadata(), listOf(window()), emptyMap())
                fail("Later writer must reject")
            } catch (_: FileAlreadyExistsException) { }
            assertArrayEquals(bytes, file.readBytes())
            assertEquals(written[2], hash(file))
            assertEquals(0L, File(directory, DiarizationEvidence.PUBLICATION_LOCK_FILE_NAME).length())
        } finally {
            children.forEach { if (it.isAlive) it.destroyForcibly() }
            children.forEach { it.waitFor(5, TimeUnit.SECONDS) }
            coordination.deleteRecursively()
        }
    }

    @Test fun lateExistingTargetRefusalReleasesBothPublicationLocks() = temporary { directory ->
        var winner: DiarizationEvidence.Info? = null
        val publishDuringEncoding = object : Iterable<String> {
            override fun iterator() = object : Iterator<String> {
                var available = true
                override fun hasNext() = available
                override fun next(): String {
                    available = false
                    // A cooperating writer publishes while the outer producer is still encoding.
                    winner = DiarizationEvidence.write(directory, id, "winner", metadata(), listOf(window()), emptyMap())
                    return "winner already published"
                }
            }
        }
        try {
            DiarizationEvidence.write(directory, id, "loser", metadata(), listOf(window()), mapOf("race" to publishDuringEncoding))
            fail("Target recheck under the lock must reject")
        } catch (_: FileAlreadyExistsException) { }
        val original = File(directory, winner!!.relativeFileName!!)
        assertEquals("winner", JSONObject(original.readText()).getString("recording_id"))
        assertEquals(winner!!.sha256, hash(original))
        val next = DiarizationEvidence.write(directory, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "next-work",
            metadata(), listOf(window()), emptyMap())
        assertFalse(next.truncated)
        assertEquals(winner!!.sha256, hash(original))
        assertTrue(payloadFiles(directory).none { it.name.endsWith(".tmp") })
    }

    @Test fun interruptedCrossProcessFileLockWaitCleansTempAndReleasesJvmMutex() = temporary { directory ->
        // The two-process barrier relies on POSIX lock timing; Windows hosts skip it, Android and Linux run it.
        assumeFalse(isWindowsHost)
        val coordination = Files.createTempDirectory("diar-evidence-lock-coordination-").toFile()
        val holder = child("hold-lock", directory, "holder", coordination)
        val failure = AtomicReference<Throwable?>()
        val writer = Thread {
            try {
                DiarizationEvidence.write(directory, id, "cancelled-writer", metadata(), listOf(window()), emptyMap())
            } catch (error: Throwable) { failure.set(error) }
        }.apply { isDaemon = true }
        try {
            waitUntil("Other process must hold the directory lock") { File(coordination, "ready-holder").isFile }
            writer.start()
            waitUntil("Writer must block on the cross-process file lock") {
                writer.stackTrace.any { it.methodName == "lock" && it.className.contains("FileChannel") }
            }
            writer.interrupt()
            writer.join(5000)
            assertFalse("Interrupted writer must terminate", writer.isAlive)
            assertTrue("Interrupt must propagate as I/O failure", failure.get() is java.io.IOException)
            assertTrue(payloadFiles(directory).isEmpty())
            File(coordination, "go").writeText("release")
            assertTrue(holder.waitFor(10, TimeUnit.SECONDS))
            assertEquals(holder.inputStream.bufferedReader().readText(), 0, holder.exitValue())
            val next = DiarizationEvidence.write(directory, id, "after-cancel", metadata(), listOf(window()), emptyMap())
            assertFalse(next.truncated)
            assertEquals("after-cancel", JSONObject(File(directory, next.relativeFileName!!).readText()).getString("recording_id"))
            assertTrue(payloadFiles(directory).none { it.name.endsWith(".tmp") })
        } finally {
            if (holder.isAlive) holder.destroyForcibly()
            holder.waitFor(5, TimeUnit.SECONDS)
            writer.interrupt()
            writer.join(5000)
            coordination.deleteRecursively()
        }
    }

    @Test fun pathTraversalAndNonCanonicalUuidShapesReject() = temporary { directory ->
        for (bad in listOf("../$id", "$id/other", "1-1-1-1-1", "", "$id.json", "$id\n")) {
            invalid { DiarizationEvidence.write(directory, bad, "recording", metadata(), listOf(window()), emptyMap()) }
        }
        assertTrue(payloadFiles(directory).isEmpty())
    }

    @Test fun invalidWindowsRejectWithoutInventedVectorsOrFiles() = temporary { directory ->
        val bad = listOf(window(-1), window(end = 0), window(end = 2001), window(speaker = -1),
            window(vector = doubleArrayOf()), window(vector = doubleArrayOf(0.0, -0.0)),
            window(vector = doubleArrayOf(Double.NaN, 1.0)), window(vector = doubleArrayOf(1.0, Double.POSITIVE_INFINITY)),
            window(vector = doubleArrayOf(1.0)), window(vector = DoubleArray(DiarizationEvidence.MAX_DIMENSION + 1) { 1.0 }))
        for (entry in bad) invalid {
            DiarizationEvidence.write(directory, id, "recording", metadata(), listOf(entry), emptyMap())
        }
        invalid { DiarizationEvidence.write(directory, id, "recording", emptyMap(), listOf(window(), window(vector = doubleArrayOf(1.0))), emptyMap()) }
        assertTrue(payloadFiles(directory).isEmpty())
    }

    @Test fun invalidClockDimensionAndBudgetMetadataReject() = temporary { directory ->
        for (bad in listOf(mapOf("audioMs" to -1), mapOf("audioMs" to 2000.0),
            mapOf("audioMs" to null), mapOf("audioMs" to 2000, "inputAudioMs" to 3000),
            mapOf("embeddingDimension" to 0), mapOf("embeddingDimension" to 3))) invalid {
            DiarizationEvidence.write(directory, id, "recording", bad, listOf(window()), emptyMap())
        }
        for (budget in listOf(0, -1, DiarizationEvidence.DEFAULT_MAX_BYTES + 1)) invalid {
            DiarizationEvidence.write(directory, id, "recording", metadata(), listOf(window()), emptyMap(), budget)
        }
        assertTrue(payloadFiles(directory).isEmpty())
    }

    @Test fun invalidNestedValuesAbortTempAndCompactConversionRejectsCycles() = temporary { directory ->
        val cyclic = linkedMapOf<String, Any?>()
        cyclic["self"] = cyclic
        for (bad in listOf(mapOf("bad" to Double.NaN), mapOf("bad" to Float.NEGATIVE_INFINITY),
            mapOf("bad" to Any()), mapOf("bad" to mapOf(1 to "nonstring")), cyclic)) invalid {
            DiarizationEvidence.write(directory, id, "recording", metadata(), listOf(window()), bad)
        }
        invalid { DiarizationEvidence.jsonObject(cyclic) }
        var deep: Any? = null
        repeat(70) { deep = listOf(deep) }
        invalid { DiarizationEvidence.jsonObject(mapOf("too_deep" to deep)) }
        assertTrue(payloadFiles(directory).isEmpty())
    }

    @Test fun emptyMeasuredWindowsRemainEmptyAndMissingDirectoryFails() = temporary { directory ->
        val info = DiarizationEvidence.write(directory, id, "silence", mapOf("audioMs" to 0), emptyList(), mapOf("accepted" to false, "reason" to null))
        val json = JSONObject(File(directory, info.relativeFileName!!).readText())
        assertEquals(0, json.getJSONArray("windows").length())
        assertFalse(json.getJSONObject("diagnostics").getBoolean("accepted"))
        invalid { DiarizationEvidence.write(File(directory, "absent"), id, "recording", metadata(), listOf(window()), emptyMap()) }
    }
}

/** Fresh JVMs exercise the actual OS file lock, not another lock in the parent's JVM. */
object DiarizationEvidenceProcessProbe {
    @JvmStatic fun main(args: Array<String>) {
        val mode = args[0]
        val directory = File(args[1])
        val workId = args[2]
        val recording = args[3]
        val coordination = File(args[4])
        fun readyAndAwaitGo() {
            File(coordination, "ready-$recording").writeText("ready")
            val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20)
            while (!File(coordination, "go").isFile) {
                check(System.nanoTime() < deadline) { "Process barrier timeout" }
                Thread.sleep(10)
            }
        }
        if (mode == "hold-lock") {
            FileChannel.open(File(directory, DiarizationEvidence.PUBLICATION_LOCK_FILE_NAME).toPath(),
                StandardOpenOption.CREATE, StandardOpenOption.WRITE).use { channel ->
                channel.lock().use { readyAndAwaitGo() }
            }
            println("RELEASED")
        } else {
            check(mode == "write")
            readyAndAwaitGo()
            try {
                val info = DiarizationEvidence.write(directory, workId, recording,
                    mapOf("audioMs" to 2000, "embeddingDimension" to 2),
                    listOf(SpeakerRefiner.EmbeddingWindow(0, 1500, 0, doubleArrayOf(.25, -.75))), emptyMap())
                check(!info.truncated)
                println("WRITTEN $recording ${info.sha256}")
            } catch (_: FileAlreadyExistsException) {
                println("EXISTS $recording")
            }
        }
    }
}

private val isWindowsHost: Boolean = System.getProperty("os.name").orEmpty().startsWith("Windows")
