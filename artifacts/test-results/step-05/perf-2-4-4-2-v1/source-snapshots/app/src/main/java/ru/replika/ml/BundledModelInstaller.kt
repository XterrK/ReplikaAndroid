package ru.replika.ml

import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.security.MessageDigest
import java.util.zip.ZipInputStream

/**
 * Blocking, bounded-memory installer for the pinned pack. Call on an IO dispatcher while holding
 * ModelManager.gate. Neither this class nor a retry may remove an already verified live model.
 * Staging must be private to this manifest and on the same filesystem as root (atomic rename).
 */
class BundledModelInstaller(
    private val specs: List<ModelFile>,
    private val root: File,
    private val staging: File,
    private val openPack: () -> InputStream,
    private val availableSpace: () -> Long = { root.usableSpace },
    private val checkCancelled: () -> Unit = {},
    private val progress: (Progress) -> Unit = {},
) {
    enum class Phase { CHECKING, PREPARING, VERIFYING, READY }
    data class Progress(val phase: Phase, val processedBytes: Long, val totalBytes: Long, val path: String? = null)
    data class Report(
        val validSkipped: Int,
        val reusedStage: Int,
        val extracted: Int,
        val published: Int,
        val modelBytes: Long,
    )
    class InsufficientSpaceException(val requiredBytes: Long, val availableBytes: Long) : IOException(
        "Недостаточно места для офлайн-моделей: нужно $requiredBytes байт, доступно $availableBytes байт",
    )

    private val buffer = ByteArray(BUFFER_SIZE)

    fun install(): Report {
        checkCancelled()
        require(specs.isNotEmpty()) { "Пустой манифест моделей" }
        require(specs.map { it.path }.distinct().size == specs.size) { "Повторяющийся путь в манифесте" }
        specs.forEach {
            validatePath(it.path)
            require(it.size > 0 && SHA256.matches(it.sha256)) { "Неверная запись манифеста: ${it.path}" }
        }
        val rootPath = root.canonicalFile.toPath()
        val stagePath = staging.canonicalFile.toPath()
        require(!rootPath.startsWith(stagePath) && !stagePath.startsWith(rootPath)) { "Каталоги моделей и подготовки должны различаться" }
        ensureDirectory(root)
        ensureDirectory(staging)
        val total = specs.fold(0L) { sum, spec -> Math.addExact(sum, spec.size) }
        var checked = 0L
        progress(Progress(Phase.CHECKING, 0, total))
        val needed = specs.filter { spec ->
            !matches(child(root, spec.path), spec) { count ->
                checked += count
                progress(Progress(Phase.CHECKING, checked, total, spec.path))
            }
        }
        val validSkipped = specs.size - needed.size
        if (needed.isEmpty()) {
            progress(Progress(Phase.READY, total, total))
            return Report(validSkipped, 0, 0, 0, total)
        }

        // Only our expected temporary names are cleaned. Completed staged files survive retry.
        needed.forEach { spec ->
            checkCancelled()
            val part = child(staging, spec.path + PART_SUFFIX)
            if (part.exists() && !part.delete()) throw IOException("Не удалось удалить временный файл: ${spec.path}")
        }
        val reused = needed.filter { spec -> matches(child(staging, spec.path), spec) {} }.map { it.path }.toSet()
        val copySpecs = needed.filter { it.path !in reused }.associateBy { it.path }
        // Invalid files belong only to this private staging generation; live files stay untouched.
        copySpecs.values.forEach { spec ->
            val target = child(staging, spec.path)
            if (target.exists() && !target.delete()) throw IOException("Не удалось заменить временный файл: ${spec.path}")
        }
        val requiredSpace = copySpecs.values.fold(SPACE_RESERVE) { sum, spec -> Math.addExact(sum, spec.size) }
        val free = availableSpace()
        if (free < requiredSpace) throw InsufficientSpaceException(requiredSpace, free)

        var extracted = 0
        var scanned = 0L
        var metadataBytes = 0L
        val seen = mutableSetOf<String>()
        val byPath = specs.associateBy { it.path }
        progress(Progress(Phase.PREPARING, 0, total))
        // Always finish and verify the archive before publishing, including on a staged retry.
        // Otherwise an earlier corrupt/missing final entry could be bypassed by a retry.
        ZipInputStream(openPack().buffered(BUFFER_SIZE)).use { zip ->
            while (true) {
                checkCancelled()
                val entry = zip.nextEntry ?: break
                val name = entry.name
                validatePath(name, entry.isDirectory)
                if (!seen.add(name)) throw IOException("Повторяющийся путь в комплекте: $name")
                if (seen.size > specs.size + MAX_METADATA_ENTRIES) throw IOException("Слишком много файлов в комплекте")
                val spec = byPath[name]
                if (entry.isDirectory) {
                    val prefix = name.removeSuffix("/") + "/"
                    if (prefix != "licenses/" && specs.none { it.path.startsWith(prefix) }) throw IOException("Неизвестный каталог в комплекте: $name")
                    if (zip.read() != -1) throw IOException("Неверная запись каталога: $name")
                } else if (spec != null) {
                    if (entry.size >= 0 && entry.size != spec.size) throw IOException("Неверный размер модели: $name")
                    val md = MessageDigest.getInstance("SHA-256")
                    val part = if (name in copySpecs) child(staging, name + PART_SUFFIX) else null
                    var written = 0L
                    try {
                        part?.parentFile?.let(::ensureDirectory)
                        val output = part?.let { FileOutputStream(it) }
                        try {
                            while (true) {
                                checkCancelled()
                                val count = zip.read(buffer)
                                if (count < 0) break
                                written += count
                                if (written > spec.size) throw IOException("Размер модели превышает манифест: $name")
                                md.update(buffer, 0, count)
                                output?.write(buffer, 0, count)
                                scanned += count
                                progress(Progress(Phase.PREPARING, scanned, total, name))
                            }
                            if (written != spec.size || !digest(md).equals(spec.sha256, ignoreCase = true)) throw IOException("Контрольная сумма модели не совпадает: $name")
                            output?.fd?.sync()
                        } finally {
                            output?.close()
                        }
                        if (part != null) {
                            checkCancelled()
                            val completed = child(staging, name)
                            if (!part.renameTo(completed)) throw IOException("Не удалось сохранить подготовленную модель: $name")
                            extracted++
                        }
                    } finally {
                        part?.delete()
                    }
                } else {
                    if (name != "manifest.json" && !(name.startsWith("licenses/") && name.count { it == '/' } == 1)) throw IOException("Неизвестный файл в комплекте: $name")
                    if (entry.size > MAX_METADATA_BYTES) throw IOException("Слишком большой служебный файл: $name")
                    var entryBytes = 0L
                    while (true) {
                        checkCancelled()
                        val count = zip.read(buffer)
                        if (count < 0) break
                        entryBytes += count
                        metadataBytes += count
                        if (entryBytes > MAX_METADATA_BYTES || metadataBytes > MAX_TOTAL_METADATA_BYTES) throw IOException("Превышен размер служебных файлов")
                    }
                }
                // Reading every entry to EOF also makes ZipInputStream validate its CRC.
                zip.closeEntry()
            }
        }
        if (!byPath.keys.all { it in seen }) throw IOException("Встроенный комплект моделей неполон")

        val verifyTotal = needed.sumOf { it.size }
        var verified = 0L
        progress(Progress(Phase.VERIFYING, 0, verifyTotal))
        needed.forEach { spec ->
            if (!matches(child(staging, spec.path), spec) { count ->
                    verified += count
                    progress(Progress(Phase.VERIFYING, verified, verifyTotal, spec.path))
                }) throw IOException("Подготовленный файл не прошёл проверку: ${spec.path}")
        }
        // No live file changes until the entire archive AND all staged files have passed SHA-256.
        // Each rename is atomic: a killed process can expose only an old file or a verified one.
        var published = 0
        needed.forEach { spec ->
            checkCancelled()
            val target = child(root, spec.path)
            ensureDirectory(target.parentFile!!)
            if (!child(staging, spec.path).renameTo(target)) throw IOException("Не удалось установить модель: ${spec.path}")
            published++
        }
        progress(Progress(Phase.READY, total, total))
        return Report(validSkipped, reused.size, extracted, published, total)
    }

    private fun matches(file: File, spec: ModelFile, bytesRead: (Int) -> Unit): Boolean {
        checkCancelled()
        if (!file.isFile || file.length() != spec.size) return false
        val md = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered(BUFFER_SIZE).use { input ->
            while (true) {
                checkCancelled()
                val count = input.read(buffer)
                if (count < 0) break
                md.update(buffer, 0, count)
                bytesRead(count)
            }
        }
        return digest(md).equals(spec.sha256, ignoreCase = true)
    }

    private fun child(base: File, path: String): File {
        validatePath(path)
        val file = File(base, path)
        if (!file.canonicalFile.toPath().startsWith(base.canonicalFile.toPath())) throw IOException("Путь выходит за пределы каталога: $path")
        return file
    }

    private fun ensureDirectory(directory: File) {
        if (!directory.isDirectory && !directory.mkdirs()) throw IOException("Не удалось создать каталог подготовки")
    }

    companion object {
        private const val BUFFER_SIZE = 128 * 1024
        private const val SPACE_RESERVE = 32L * 1024 * 1024
        private const val MAX_METADATA_BYTES = 1024L * 1024
        private const val MAX_TOTAL_METADATA_BYTES = 4L * 1024 * 1024
        private const val MAX_METADATA_ENTRIES = 256
        private const val PART_SUFFIX = ".bundled-part"
        private val SHA256 = Regex("[0-9a-fA-F]{64}")

        fun manifestFingerprint(specs: List<ModelFile>): String {
            val md = MessageDigest.getInstance("SHA-256")
            specs.sortedBy { it.path }.forEach { spec ->
                md.update("${spec.group}\u0000${spec.path}\u0000${spec.size}\u0000${spec.sha256.lowercase()}\n".toByteArray(Charsets.UTF_8))
            }
            return digest(md)
        }

        private fun digest(md: MessageDigest) = md.digest().joinToString("") { "%02x".format(it) }

        private fun validatePath(path: String, directory: Boolean = false) {
            val normalized = if (directory) path.removeSuffix("/") else path
            if (normalized.isEmpty() || path.startsWith('/') || '\\' in path || ':' in path || '\u0000' in path ||
                normalized.split('/').any { it.isEmpty() || it == "." || it == ".." }) {
                throw IOException("Небезопасный путь в комплекте моделей")
            }
        }
    }
}
