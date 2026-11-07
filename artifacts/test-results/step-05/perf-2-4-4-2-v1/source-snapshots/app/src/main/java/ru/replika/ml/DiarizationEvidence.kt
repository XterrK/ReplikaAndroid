package ru.replika.ml

import org.json.JSONObject
import ru.replika.domain.SpeakerRefiner
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream
import java.io.OutputStreamWriter
import java.io.Writer
import java.io.InterruptedIOException
import java.math.BigInteger
import java.nio.channels.FileChannel
import java.nio.file.FileAlreadyExistsException
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.security.MessageDigest
import java.util.IdentityHashMap
import java.util.UUID

/** Explicit local-QA evidence only. The caller supplies an app-private directory and immutable
 * inputs; this helper has no Context, Room, audio, native runtime or model dependency.
 *
 * Writes actual measured windows, without projection or invented vectors. JSON is streamed into
 * a bounded temporary file. Cooperating writers use one JVM mutex plus a persistent directory
 * file lock, recheck the destination under both locks, then atomically rename the complete temp.
 * The directory is private and all publishers must use this protocol: ATOMIC_MOVE alone does
 * not guarantee no-overwrite against a writer that ignores the lock. No non-atomic fallback.
 */
object DiarizationEvidence {
    const val DEFAULT_MAX_BYTES = 8 * 1024 * 1024
    const val MAX_WINDOWS = 8192
    const val MAX_DIMENSION = 4096
    const val PUBLICATION_LOCK_FILE_NAME = ".diarization-publication.lock"
    private const val MAX_DEPTH = 64
    private const val MAX_VALUES = 2_000_000
    private val workIdPattern = Regex("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    private val publicationMutex = Any()

    data class Info(
        val relativeFileName: String?,
        val sha256: String?,
        val bytes: Long,
        val truncated: Boolean,
        val reason: String? = null,
    )

    /** Invalid identities/data throw IllegalArgumentException. Existing targets and I/O failures
     * throw without replacing prior evidence. A budget refusal returns no filename/hash and zero
     * published bytes; no apparently complete partial sidecar is left behind.
     * Optional metadata audioMs/inputAudioMs/durationMs/duration_ms and embeddingDimension/
     * embedding_dimension are checked against every window when supplied.
     */
    fun write(
        directory: File,
        workId: String,
        recordingId: String,
        metadata: Map<String, Any?>,
        windows: List<SpeakerRefiner.EmbeddingWindow>,
        diagnostics: Map<String, Any?>,
        maxBytes: Int = DEFAULT_MAX_BYTES,
    ): Info {
        require(workIdPattern.matches(workId)) { "workId must be a full UUID" }
        val canonicalWorkId = UUID.fromString(workId).toString()
        require(recordingId.isNotBlank() && recordingId.length <= 4096) { "Invalid recordingId" }
        require(maxBytes in 1..DEFAULT_MAX_BYTES) { "maxBytes must be within 1..8MiB" }
        require(directory.isDirectory) { "Caller must supply an existing private directory" }
        val target = directory.toPath().resolve("diarization-$canonicalWorkId.json")
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) throw FileAlreadyExistsException(target.toString())
        if (windows.size > MAX_WINDOWS) return refused("window_limit_exceeded")
        validateWindows(windows, metadata)
        val temporary = Files.createTempFile(directory.toPath(), ".diarization-$canonicalWorkId-", ".tmp")
        try {
            val digest = MessageDigest.getInstance("SHA-256")
            var count = 0L
            FileOutputStream(temporary.toFile()).use { file ->
                val bounded = BoundedOutput(file, maxBytes, digest)
                val writer = OutputStreamWriter(bounded, Charsets.UTF_8)
                JsonEncoder(writer, maxBytes).value(linkedMapOf(
                    "schema_version" to 1,
                    "work_id" to canonicalWorkId,
                    "recording_id" to recordingId,
                    "metadata" to metadata,
                    "windows" to windows,
                    "diagnostics" to diagnostics,
                    "truncated" to false,
                ))
                writer.write("\n")
                writer.flush()
                file.fd.sync()
                count = bounded.count
            }
            publish(directory.toPath(), temporary, target)
            return Info(target.fileName.toString(), digest.digest().joinToString("") { "%02x".format(it) }, count, false)
        } catch (error: BudgetExceeded) {
            return refused(error.message ?: "budget_exceeded")
        } finally {
            Files.deleteIfExists(temporary)
        }
    }

    private fun publish(directory: Path, temporary: Path, target: Path) {
        fun checkInterrupted() {
            if (Thread.currentThread().isInterrupted) throw InterruptedIOException("QA publication interrupted")
        }
        checkInterrupted()
        synchronized(publicationMutex) {
            checkInterrupted()
            // Never unlink this file: another process could still hold a lock on its old inode.
            val lockPath = directory.resolve(PUBLICATION_LOCK_FILE_NAME)
            FileChannel.open(lockPath, StandardOpenOption.CREATE, StandardOpenOption.WRITE).use { channel ->
                channel.lock().use {
                    checkInterrupted()
                    if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) throw FileAlreadyExistsException(target.toString())
                    // Same-directory atomic rename is supported on app-private filesystems;
                    // all cooperating publishers are excluded between this check and rename.
                    Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE)
                }
            }
        }
    }

    /** Compact diagnostic reuse: every nested null is encoded as JSON null and consequently
     * becomes JSONObject.NULL, preserving keys that JSONObject(Map) may otherwise discard.
     * The same finite/type/cycle/depth checks and 8MiB cap apply. Not for building vector copies.
     */
    fun jsonObject(values: Map<String, Any?>): JSONObject {
        val output = ByteArrayOutputStream()
        val writer = OutputStreamWriter(BoundedOutput(output, DEFAULT_MAX_BYTES, null), Charsets.UTF_8)
        JsonEncoder(writer).value(values)
        writer.flush()
        return JSONObject(output.toString(Charsets.UTF_8.name()))
    }

    private fun refused(reason: String) = Info(null, null, 0, true, reason)

    private fun integer(value: Any?, key: String): Long {
        require(value is Byte || value is Short || value is Int || value is Long) { "$key must be an integer" }
        return (value as Number).toLong()
    }

    private fun validateWindows(windows: List<SpeakerRefiner.EmbeddingWindow>, metadata: Map<String, Any?>) {
        val clocks = listOf("audioMs", "inputAudioMs", "durationMs", "duration_ms")
            .filter { metadata.containsKey(it) }.map { integer(metadata[it], it) }
        require(clocks.all { it >= 0 } && clocks.distinct().size <= 1) { "Inconsistent/negative recording clock" }
        val dimensions = listOf("embeddingDimension", "embedding_dimension")
            .filter { metadata.containsKey(it) }.map { integer(metadata[it], it) }
        require(dimensions.all { it in 1..MAX_DIMENSION.toLong() } && dimensions.distinct().size <= 1) { "Invalid embedding dimension" }
        val dimension = dimensions.firstOrNull() ?: windows.firstOrNull()?.embedding?.size?.toLong()
        for (window in windows) {
            require(window.startMs >= 0 && window.endMs > window.startMs && window.speaker >= 0) { "Invalid window clock/speaker" }
            require(clocks.isEmpty() || window.endMs <= clocks.first()) { "Window exceeds original recording clock" }
            require(window.embedding.size in 1..MAX_DIMENSION && window.embedding.size.toLong() == dimension) { "Missing/inconsistent embedding dimension" }
            require(window.embedding.all { it.isFinite() } && window.embedding.any { it != 0.0 }) { "Nonfinite/zero embedding" }
        }
    }

    private class BudgetExceeded(reason: String) : IllegalArgumentException(reason)

    private class BoundedOutput(
        private val output: OutputStream,
        private val limit: Int,
        private val digest: MessageDigest?,
    ) : OutputStream() {
        var count = 0L
            private set

        override fun write(value: Int) {
            if (count >= limit) throw BudgetExceeded("budget_exceeded")
            output.write(value)
            digest?.update(value.toByte())
            count++
        }

        override fun write(bytes: ByteArray, offset: Int, length: Int) {
            if (length.toLong() > limit - count) throw BudgetExceeded("budget_exceeded")
            output.write(bytes, offset, length)
            digest?.update(bytes, offset, length)
            count += length
        }

        override fun flush() = output.flush()
    }

    private class JsonEncoder(private val writer: Writer, private val byteLimit: Int = DEFAULT_MAX_BYTES) {
        private val active = IdentityHashMap<Any, Boolean>()
        private var values = 0

        fun value(value: Any?, depth: Int = 0) {
            require(depth <= MAX_DEPTH) { "JSON nesting exceeds limit" }
            if (++values > MAX_VALUES) throw BudgetExceeded("value_limit_exceeded")
            when (value) {
                null, JSONObject.NULL -> writer.write("null")
                is String -> string(value)
                is Char -> string(value.toString())
                is Boolean -> writer.write(if (value) "true" else "false")
                is Byte, is Short, is Int, is Long -> writer.write(value.toString())
                is BigInteger -> {
                    // log10(2) < 30103/100000: refuse oversized integer conversion before
                    // allocating its decimal string. The actual byte writer still bounds the
                    // whole document, including signs, UTF8, punctuation and other fields.
                    val digitsUpperBound = value.abs().bitLength().toLong() * 30103 / 100000 + 1
                    if (digitsUpperBound + (if (value.signum() < 0) 1 else 0) > byteLimit) {
                        throw BudgetExceeded("budget_exceeded")
                    }
                    writer.write(value.toString())
                }
                is Float -> { require(value.isFinite()) { "Nonfinite JSON number" }; writer.write(value.toString()) }
                is Double -> { require(value.isFinite()) { "Nonfinite JSON number" }; writer.write(value.toString()) }
                is Map<*, *> -> container(value) {
                    writer.write("{")
                    var first = true
                    for ((key, child) in value) {
                        require(key is String) { "JSON map key must be a string" }
                        if (!first) writer.write(",")
                        first = false
                        string(key)
                        writer.write(":")
                        value(child, depth + 1)
                    }
                    writer.write("}")
                }
                is SpeakerRefiner.EmbeddingWindow -> value(linkedMapOf(
                    "start_ms" to value.startMs, "end_ms" to value.endMs, "speaker" to value.speaker,
                    "embedding" to value.embedding, "clean" to value.clean,
                ), depth + 1)
                is Iterable<*> -> container(value) { array(value.iterator(), depth) }
                is Array<*> -> container(value) { array(value.iterator(), depth) }
                is DoubleArray -> array(value.iterator(), depth)
                is FloatArray -> array(value.iterator(), depth)
                is LongArray -> array(value.iterator(), depth)
                is IntArray -> array(value.iterator(), depth)
                is ShortArray -> array(value.iterator(), depth)
                is ByteArray -> array(value.iterator(), depth)
                is BooleanArray -> array(value.iterator(), depth)
                else -> throw IllegalArgumentException("Unsupported JSON value type: ${value.javaClass.name}")
            }
        }

        private fun array(iterator: Iterator<*>, depth: Int) {
            writer.write("[")
            var first = true
            while (iterator.hasNext()) {
                if (!first) writer.write(",")
                first = false
                value(iterator.next(), depth + 1)
            }
            writer.write("]")
        }

        private inline fun container(identity: Any, body: () -> Unit) {
            require(active.put(identity, true) == null) { "Cyclic JSON input" }
            try { body() } finally { active.remove(identity) }
        }

        private fun string(value: String) {
            writer.write("\"")
            for (character in value) {
                when (character) {
                    '\\' -> writer.write("\\\\")
                    '"' -> writer.write("\\\"")
                    '\b' -> writer.write("\\b")
                    '\u000c' -> writer.write("\\f")
                    '\n' -> writer.write("\\n")
                    '\r' -> writer.write("\\r")
                    '\t' -> writer.write("\\t")
                    else -> if (character.code < 0x20 || character.isSurrogate()) {
                        writer.write("\\u" + character.code.toString(16).padStart(4, '0'))
                    } else writer.write(character.code)
                }
            }
            writer.write("\"")
        }
    }
}
