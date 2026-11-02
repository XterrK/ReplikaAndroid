package ru.replika

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import ru.replika.ml.BundledModelInstaller
import ru.replika.ml.ModelFile
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.CancellationException
import java.util.zip.CRC32
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** Tiny ZIP fixtures exercise installer safety, not model inference or ASR quality. */
@RunWith(AndroidJUnit4::class)
class BundledModelInstallerTest {
    private lateinit var directory: File
    private lateinit var root: File
    private lateinit var staging: File
    private lateinit var models: LinkedHashMap<String, ByteArray>
    private lateinit var specs: List<ModelFile>

    @Before fun createIsolatedFiles() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        directory = File(context.cacheDir, "bundled-safety-${System.nanoTime()}").apply { check(mkdirs()) }
        root = File(directory, "models")
        staging = File(directory, "staging")
        models = linkedMapOf(
            "giga-v2/encoder.int8.onnx" to "fixture encoder, not an ML model".toByteArray(),
            "giga-v2/decoder.onnx" to "fixture decoder".toByteArray(),
            "giga-v2/joiner.onnx" to "fixture joiner".toByteArray(),
            "giga-v2/tokens.txt" to "fixture tokens".toByteArray(),
            "diar/segmentation.onnx" to "fixture segmentation".toByteArray(),
            "diar/embedding.onnx" to "fixture embedding".toByteArray(),
            "vad/silero_vad.onnx" to "fixture vad".toByteArray(),
            "whisper-tiny/ggml-tiny.bin" to "fixture whisper".toByteArray(),
        )
        updateSpecs()
    }

    @After fun deleteOnlyIsolatedFiles() { directory.deleteRecursively() }

    @Test fun validModelsAreNotRewrittenAndPackIsNeverOpened() {
        models.forEach { (path, bytes) -> write(root, path, bytes) }
        val times = models.keys.associateWith { File(root, it).lastModified() }
        val events = mutableListOf<BundledModelInstaller.Progress>()
        val report = BundledModelInstaller(specs, root, staging, { error("A valid installation must not open the archive") }, progress = { events += it }).install()
        assertEquals(8, report.validSkipped)
        assertEquals(0, report.extracted)
        assertEquals(0, report.published)
        models.forEach { (path, bytes) ->
            assertArrayEquals(bytes, File(root, path).readBytes())
            assertEquals(times[path], File(root, path).lastModified())
        }
        assertEquals(models.values.sumOf { it.size.toLong() }, events.filter { it.phase == BundledModelInstaller.Phase.CHECKING }.last().processedBytes)
        assertEquals(BundledModelInstaller.Phase.READY, events.last().phase)
    }

    @Test fun completePackPublishesOnlyVerifiedFilesAndReportsActualBytes() {
        val entries = linkedMapOf("manifest.json" to "{}".toByteArray(), "licenses/NOTICE.md" to "fixture notice".toByteArray())
        entries.putAll(models)
        val events = mutableListOf<BundledModelInstaller.Progress>()
        val report = installer(zip(entries), progress = { events += it }).install()
        assertEquals(8, report.extracted)
        assertEquals(8, report.published)
        assertEquals(0, report.validSkipped)
        assertEquals(models.values.sumOf { it.size.toLong() }, report.modelBytes)
        assertEquals(report.modelBytes, events.last { it.phase == BundledModelInstaller.Phase.PREPARING }.processedBytes)
        assertEquals(report.modelBytes, events.last { it.phase == BundledModelInstaller.Phase.VERIFYING }.processedBytes)
        assertModelsInstalled()
        assertFalse(staging.walkTopDown().any { it.name.endsWith(".bundled-part") })
    }

    @Test fun replacingMissingModelsPreservesExistingValidModelsAndScansSkippedEntryBytes() {
        val keep = models.entries.first()
        write(root, keep.key, keep.value)
        val modified = File(root, keep.key).lastModified()
        val events = mutableListOf<BundledModelInstaller.Progress>()
        val report = installer(zip(models), progress = { events += it }).install()
        assertEquals(1, report.validSkipped)
        assertEquals(7, report.extracted)
        assertEquals(7, report.published)
        assertEquals(modified, File(root, keep.key).lastModified())
        assertEquals(report.modelBytes, events.last { it.phase == BundledModelInstaller.Phase.PREPARING }.processedBytes)
        assertModelsInstalled()
    }

    @Test fun wrongHashDoesNotPublishAnythingOrDestroyExistingFiles() {
        val old = "existing invalid model preserved on failure".toByteArray()
        write(root, models.keys.first(), old)
        val changed = LinkedHashMap(models)
        val last = changed.keys.last()
        changed[last] = ByteArray(changed.getValue(last).size) { 42 }
        rejected { installer(zip(changed)).install() }
        assertArrayEquals(old, File(root, models.keys.first()).readBytes())
        assertEquals(1, root.walkTopDown().count { it.isFile })
        assertFalse(staging.walkTopDown().any { it.name.endsWith(".bundled-part") })
    }

    @Test fun crcCorruptionCannotPublishFiles() {
        val packed = zip(models)
        val original = models.values.first()
        val offset = find(packed, original)
        assertTrue(offset >= 0)
        packed[offset] = (packed[offset].toInt() xor 1).toByte()
        rejected { installer(packed).install() }
        assertFalse(root.walkTopDown().any { it.isFile })
    }

    @Test fun unsafeZipPathsAreRejectedWithoutEscapingPrivateDirectories() {
        listOf("../escape.bin", "/absolute.bin", "C:/escape.bin", "folder\\escape.bin", "folder/../escape.bin", "folder/./escape.bin").forEach { path ->
            val entries = LinkedHashMap(models)
            entries[path] = "unsafe".toByteArray()
            rejected { installer(zip(entries)).install() }
            assertFalse(root.walkTopDown().any { it.isFile })
            assertFalse(File(directory, "escape.bin").exists())
        }
    }

    @Test fun unsafeManifestPathsAreRejectedBeforeOpeningPack() {
        val invalid = specs.first().copy(path = "../escape.bin")
        rejected { BundledModelInstaller(listOf(invalid), root, staging, { error("Unsafe manifest must fail first") }).install() }
        assertFalse(File(directory, "escape.bin").exists())
    }

    @Test fun duplicateZipPathsAreRejectedEvenWhenAllStagesWereAlreadyWritten() {
        val entries = LinkedHashMap(models)
        entries["licenses/a.txt"] = "a".toByteArray()
        entries["licenses/b.txt"] = "b".toByteArray()
        val packed = zip(entries)
        replaceEqualLength(packed, "licenses/b.txt", "licenses/a.txt")
        rejected { installer(packed).install() }
        assertFalse(root.walkTopDown().any { it.isFile })
        // A retry must validate the archive again, not publish completed stages from a bad pack.
        rejected { installer(packed).install() }
        assertFalse(root.walkTopDown().any { it.isFile })
    }

    @Test fun missingRequiredFileCannotBeBypassedWithPreexistingStages() {
        val entries = LinkedHashMap(models)
        entries.remove(entries.keys.last())
        models.forEach { (path, bytes) -> write(staging, path, bytes) }
        rejected { installer(zip(entries)).install() }
        assertFalse(root.walkTopDown().any { it.isFile })
    }

    @Test fun oversizedAndUnknownEntriesAreRejectedBeforePublication() {
        val oversized = LinkedHashMap(models)
        val first = oversized.keys.first()
        oversized[first] = oversized.getValue(first) + byteArrayOf(0)
        rejected { installer(zip(oversized)).install() }
        val unknown = LinkedHashMap(models)
        unknown["extra-model.onnx"] = byteArrayOf(0)
        rejected { installer(zip(unknown)).install() }
        assertFalse(root.walkTopDown().any { it.isFile })
    }

    @Test fun boundedMetadataRejectsArchiveBombWithoutPublishingModels() {
        val entries = LinkedHashMap(models)
        entries["licenses/oversized.txt"] = ByteArray(1024 * 1024 + 1)
        rejected { installer(zip(entries)).install() }
        assertFalse(root.walkTopDown().any { it.isFile })
    }

    @Test fun insufficientStorageDoesNotOpenPackOrChangeLiveModel() {
        val old = "existing model".toByteArray()
        write(root, models.keys.first(), old)
        try {
            BundledModelInstaller(specs, root, staging, { error("No space: do not open pack") }, availableSpace = { 0L }).install()
            fail("Expected insufficient storage")
        } catch (error: BundledModelInstaller.InsufficientSpaceException) {
            assertTrue(error.requiredBytes >= models.values.sumOf { it.size.toLong() } + 32L * 1024 * 1024)
            assertEquals(0L, error.availableBytes)
        }
        assertArrayEquals(old, File(root, models.keys.first()).readBytes())
    }

    @Test fun interruptedPreparationRetainsVerifiedStageAndSafelyRetries() {
        val second = models.keys.elementAt(1)
        models[second] = ByteArray(256 * 1024) { (it % 127).toByte() }
        updateSpecs()
        var cancelled = false
        try {
            installer(zip(models), checkCancelled = { if (cancelled) throw CancellationException("fixture interruption") }, progress = {
                if (it.phase == BundledModelInstaller.Phase.PREPARING && it.path == second) cancelled = true
            }).install()
            fail("Expected interruption")
        } catch (_: CancellationException) { }
        assertFalse(root.walkTopDown().any { it.isFile })
        assertArrayEquals(models.values.first(), File(staging, models.keys.first()).readBytes())
        assertFalse(staging.walkTopDown().any { it.name.endsWith(".bundled-part") })
        val report = installer(zip(models)).install()
        assertEquals(1, report.reusedStage)
        assertEquals(7, report.extracted)
        assertEquals(8, report.published)
        assertModelsInstalled()
    }

    @Test fun interruptedPublicationCanExposeOnlyVerifiedFilesAndRetryCompletes() {
        var verifying = false
        var cancelled = false
        try {
            installer(zip(models), checkCancelled = {
                if (verifying && root.walkTopDown().count { it.isFile } == 1) cancelled = true
                if (cancelled) throw CancellationException("fixture publication interruption")
            }, progress = { if (it.phase == BundledModelInstaller.Phase.VERIFYING) verifying = true }).install()
            fail("Expected publication interruption")
        } catch (_: CancellationException) { }
        val installed = root.walkTopDown().filter { it.isFile }.toList()
        assertEquals(1, installed.size)
        assertArrayEquals(models.getValue(installed.single().relativeTo(root).invariantSeparatorsPath), installed.single().readBytes())
        val report = installer(zip(models)).install()
        assertEquals(1, report.validSkipped)
        assertEquals(7, report.reusedStage)
        assertEquals(0, report.extracted)
        assertModelsInstalled()
    }

    @Test fun corruptStageIsReplacedButCompleteVerifiedStageIsReused() {
        val first = models.entries.first()
        write(staging, first.key, first.value)
        val second = models.entries.elementAt(1)
        write(staging, second.key, ByteArray(second.value.size) { 0 })
        val report = installer(zip(models)).install()
        assertEquals(1, report.reusedStage)
        assertEquals(7, report.extracted)
        assertModelsInstalled()
    }

    @Test fun manifestFingerprintIsStableAndChangesWithPinnedWeights() {
        val expected = BundledModelInstaller.manifestFingerprint(specs)
        assertEquals(expected, BundledModelInstaller.manifestFingerprint(specs.reversed()))
        assertNotEquals(expected, BundledModelInstaller.manifestFingerprint(specs.dropLast(1) + specs.last().copy(size = specs.last().size + 1)))
    }

    private fun updateSpecs() {
        specs = models.map { (path, data) -> ModelFile(path.substringBefore('/'), path, "fixture://local", null, data.size.toLong(), sha(data)) }
    }

    private fun installer(
        pack: ByteArray,
        checkCancelled: () -> Unit = {},
        progress: (BundledModelInstaller.Progress) -> Unit = {},
    ) = BundledModelInstaller(specs, root, staging, { ByteArrayInputStream(pack) }, { Long.MAX_VALUE }, checkCancelled, progress)

    private fun assertModelsInstalled() { models.forEach { (path, bytes) -> assertArrayEquals(path, bytes, File(root, path).readBytes()) } }

    private fun write(base: File, path: String, bytes: ByteArray) {
        File(base, path).apply { parentFile!!.mkdirs();writeBytes(bytes) }
    }

    private fun rejected(block: () -> Unit) {
        try { block() } catch (_: IOException) { return } catch (_: IllegalArgumentException) { return }
        fail("Expected unsafe or corrupt pack to be rejected")
    }

    private fun zip(entries: Map<String, ByteArray>): ByteArray {
        val bytes = ByteArrayOutputStream()
        ZipOutputStream(bytes).use { zip ->
            entries.forEach { (name, data) ->
                val entry = ZipEntry(name).apply {
                    method = ZipEntry.STORED
                    size = data.size.toLong()
                    compressedSize = size
                    crc = CRC32().apply { update(data) }.value
                }
                zip.putNextEntry(entry)
                zip.write(data)
                zip.closeEntry()
            }
        }
        return bytes.toByteArray()
    }

    private fun replaceEqualLength(bytes: ByteArray, from: String, to: String) {
        val search = from.toByteArray()
        val replacement = to.toByteArray()
        check(search.size == replacement.size)
        var offset = find(bytes, search)
        while (offset >= 0) {
            replacement.copyInto(bytes, offset)
            offset = find(bytes, search)
        }
    }

    private fun find(bytes: ByteArray, pattern: ByteArray): Int {
        for (index in 0..bytes.size - pattern.size) {
            if (pattern.indices.all { bytes[index + it] == pattern[it] }) return index
        }
        return -1
    }

    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
}
