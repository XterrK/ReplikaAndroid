package ru.replika.data

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.LinkOption

/** A tiny ownership journal, published before any import output exists. No general orphan scan.
 * The Application's single gate serializes recovery with imports through their Room commit.
 */
class ImportJournal(private val audioDirectory: File,private val gate: Mutex) {
 internal data class Entry(val id: String)
 data class Recovery(val inspected: Int=0,val cleaned: Int=0,val referenced: Int=0,val deferred: Int=0,val invalid: Int=0)
 private enum class Settlement { CLEANED, REFERENCED, DEFERRED, INVALID }
 private val suffixes=listOf("audio","m4a","wav")
 private fun root(): File {
  val canonical=audioDirectory.canonicalFile
  check(canonical.parentFile==audioDirectory.absoluteFile.parentFile?.canonicalFile && canonical.name==audioDirectory.name) { "Redirected audio directory" }
  return canonical
 }
 private fun directory(): File {
  val directory=File(audioDirectory,".pending-imports")
  check(!Files.isSymbolicLink(directory.toPath()) && directory.canonicalFile==File(root(),directory.name)) { "Redirected import journal" }
  return directory
 }
 private fun outputs(id: String)=suffixes.map { File(audioDirectory,"$id.$it") }
 private fun marker(id: String)=File(directory(),"$id.pending")
 private fun exists(file: File)=Files.exists(file.toPath(),LinkOption.NOFOLLOW_LINKS)
 private fun body(id: String)="$MAGIC\n$id\n"
 private fun validId(id: String)=ID.matches(id)

 /** Internal entry point also permits an isolated interrupted-process fixture. Call while gated. */
 internal fun begin(id: String): Entry {
  require(validId(id)) { "Invalid import UUID" }
  check(audioDirectory.isDirectory || audioDirectory.mkdirs()) { "Cannot create audio directory" }
  val journal=directory();check(journal.isDirectory || journal.mkdirs()) { "Cannot create import journal" }
  val target=marker(id);val partial=File(journal,"$id.pending.new")
  if(exists(target) || exists(partial) || outputs(id).any(::exists)) throw ProductOperationException("Не удалось начать импорт. Выберите файл ещё раз.","Import UUID collides with existing owned files")
  var created=false
  try {
   check(partial.createNewFile()) { "Import marker collision" };created=true
   FileOutputStream(partial).use { stream -> stream.write(body(id).toByteArray(Charsets.US_ASCII));stream.fd.sync() }
   check(!exists(target) && partial.renameTo(target)) { "Cannot publish import marker" }
   return Entry(id)
  } finally { if(created) partial.delete() }
 }
 private fun read(file: File): Entry? {
  val name=file.name.removeSuffix(".pending")
  if(!file.name.endsWith(".pending") || !validId(name) || Files.isSymbolicLink(file.toPath()) || !file.isFile || file.canonicalFile!=File(directory().canonicalFile,file.name)) return null
  // Bounded read even if another writer changes its length between stat and read.
  if(file.length()>MAX_MARKER_BYTES) return null
  val bytes=ByteArray(MAX_MARKER_BYTES+1)
  val count=file.inputStream().use { input -> var n=0;while(n<bytes.size) { val next=input.read(bytes,n,bytes.size-n);if(next<0) break;n+=next };n }
  return Entry(name).takeIf { count<=MAX_MARKER_BYTES && String(bytes,0,count,Charsets.US_ASCII)==body(name) }
 }
 private suspend fun settle(entry: Entry,isReferenced: suspend (List<String>)->Boolean): Settlement {
  try {
   if(read(marker(entry.id))!=entry) return Settlement.INVALID
   val root=root();val files=outputs(entry.id)
   // Refuse redirects, directories and substituted links, including broken links.
   if(files.any { exists(it) && (Files.isSymbolicLink(it.toPath()) || !it.isFile || it.canonicalFile!=File(root,it.name)) }) return Settlement.DEFERRED
   val paths=files.flatMap { listOf(it.absolutePath,it.canonicalPath) }.distinct()
   val referenced=try { isReferenced(paths) } catch(e: CancellationException) { throw e } catch(_: Exception) { return Settlement.DEFERRED }
   if(!referenced) for(file in files) if(exists(file) && !file.delete()) return Settlement.DEFERRED
   if(!marker(entry.id).delete()) return Settlement.DEFERRED
   return if(referenced) Settlement.REFERENCED else Settlement.CLEANED
  } catch(e: CancellationException) { throw e } catch(_: Exception) { return Settlement.DEFERRED }
 }

 /** The action includes extraction and Room insertion. A failed begin never grants cleanup rights. */
 suspend fun <T> runImport(id: String,isReferenced: suspend (List<String>)->Boolean,action: suspend ()->T): T = gate.withLock {
  var entry: Entry?=null
  try {
   withContext(Dispatchers.IO) { entry=begin(id) }
   currentCoroutineContext().ensureActive()
   val result=action()
   withContext(NonCancellable+Dispatchers.IO) { settle(entry!!,isReferenced) }
   entry=null
   result
  } catch(error: Throwable) {
   entry?.let { owned -> withContext(NonCancellable+Dispatchers.IO) { settle(owned,isReferenced) } }
   throw error
  }
 }

 /** Only valid pending UUIDs and their three fixed outputs are considered; cap IO per startup. */
 suspend fun recover(isReferenced: suspend (List<String>)->Boolean): Recovery = gate.withLock { withContext(Dispatchers.IO) {
  var report=Recovery()
  try {
   val journal=directory();if(!journal.isDirectory) return@withContext report
   Files.newDirectoryStream(journal.toPath(),"*.pending").use { entries ->
    for(path in entries) {
     currentCoroutineContext().ensureActive();if(report.inspected>=MAX_RECOVERY_ENTRIES) break
     report=report.copy(inspected=report.inspected+1)
     val entry=runCatching { read(path.toFile()) }.getOrNull()
     if(entry==null) { report=report.copy(invalid=report.invalid+1);continue }
     report=when(settle(entry,isReferenced)) {
      Settlement.CLEANED -> report.copy(cleaned=report.cleaned+1)
      Settlement.REFERENCED -> report.copy(referenced=report.referenced+1)
      Settlement.DEFERRED -> report.copy(deferred=report.deferred+1)
      Settlement.INVALID -> report.copy(invalid=report.invalid+1)
     }
    }
   }
  } catch(e: CancellationException) { throw e } catch(_: Exception) { report=report.copy(deferred=report.deferred+1) }
  report
 } }
 companion object {
  private const val MAGIC="REPLIKA-IMPORT-1"
  private const val MAX_MARKER_BYTES=96
  internal const val MAX_RECOVERY_ENTRIES=128
  private val ID=Regex("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
 }
}
