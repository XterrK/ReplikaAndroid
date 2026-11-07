package ru.replika.data

import androidx.room.withTransaction
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID

class ProductOperationException(val userMessage: String, detail: String, cause: Throwable? = null): IllegalStateException(detail,cause)
data class SegmentUndo(val before: SegmentRow,val after: SegmentRow)
data class DeleteOutcome(val audioRemoved: Boolean,val audioPreserved: Boolean,val cleanupPending: Boolean = false)

/** Database and owned-file operations. No source file outside files/audio can be removed. */
class ProductStorage(private val db: ReplikaDatabase,private val audioDirectory: File) {
 private val dao get()=db.dao()
 private val trashDirectory get()=File(audioDirectory,".deleting")
 private suspend fun requireEditable(id: String) {
  val record=dao.recording(id)?:throw ProductOperationException("Запись больше недоступна.","Missing recording $id")
  if(record.status in setOf("QUEUED","PROCESSING","CANCELLING")) throw ProductOperationException("Дождитесь завершения обработки, чтобы изменить фрагмент.","Edit during ${record.status} for $id")
 }

 suspend fun edit(expected: SegmentRow,text: String,speaker: Int,reviewed: Boolean): SegmentUndo = db.withTransaction {
  requireEditable(expected.recordingId)
  if(speaker< -1) throw ProductOperationException("Выберите участника из списка.","Invalid speaker ID $speaker")
  val current=dao.segment(expected.id) ?: throw ProductOperationException("Фрагмент больше недоступен. Откройте стенограмму заново.","Segment ${expected.id} no longer exists")
  if(current!=expected) throw ProductOperationException("Фрагмент уже изменился. Откройте его заново, чтобы сохранить актуальную версию.","Stale edit for segment ${expected.id}")
  val after=current.copy(text=text,speakerId=speaker,edited=current.edited || text!=current.text || speaker!=current.speakerId,reviewed=reviewed)
  check(dao.updateSegment(after)==1) { "Expected exactly one updated segment" }
  SegmentUndo(current,after)
 }

 suspend fun undo(change: SegmentUndo) = db.withTransaction {
  requireEditable(change.after.recordingId)
  val current=dao.segment(change.after.id)
  if(current!=change.after) throw ProductOperationException("После этого исправления данные изменились. Отмена недоступна, чтобы сохранить новую версию.","Stale undo for segment ${change.after.id}")
  check(dao.updateSegment(change.before)==1) { "Expected exactly one restored segment" }
 }

 private fun ownedRoot(): File? {
  val root=audioDirectory.canonicalFile
  val expectedParent=audioDirectory.absoluteFile.parentFile?.canonicalFile
  return root.takeIf { it.parentFile==expectedParent && it.name==audioDirectory.name }
 }
 fun ownedAudio(path: String): File? {
  val root=ownedRoot()?:return null
  val candidate=File(path).canonicalFile
  return candidate.takeIf { it.parentFile==root && it!=root && it.isFile }
 }

 private fun sameAudio(path: String,target: File)=runCatching { File(path).canonicalFile==target }.getOrDefault(false)

 /** Call after checking WorkManager and while holding the application's native gate. */
 suspend fun deleteRecording(id: String): DeleteOutcome = withContext(Dispatchers.IO) {
  var original: File?=null
  var staged: File?=null
  var preserved=false
  try {
   db.withTransaction {
    val rec=dao.recording(id) ?: throw ProductOperationException("Запись уже удалена.","Recording $id no longer exists")
    if(rec.status in setOf("QUEUED","PROCESSING","CANCELLING")) throw ProductOperationException("Сначала отмените обработку и дождитесь её завершения.","Cannot delete busy recording $id (${rec.status})")
    val target=ownedAudio(rec.audioPath)
    val shared=target!=null && dao.recordingList().any { it.id!=id && sameAudio(it.audioPath,target) }
    preserved=target==null || shared
    if(target!=null && !shared) {
     check(trashDirectory.canonicalFile.parentFile==ownedRoot() && trashDirectory.canonicalFile.name==".deleting") { "Unsafe audio deletion staging directory" }
     check(trashDirectory.isDirectory || trashDirectory.mkdirs()) { "Cannot create audio deletion staging directory" }
     val pending=File(trashDirectory,"${UUID.randomUUID()}--${target.name}")
     if(!target.renameTo(pending)) throw ProductOperationException("Не удалось удалить локальное аудио. Запись сохранена; повторите попытку.","Cannot stage owned audio ${target.path}")
     original=target;staged=pending
    }
    dao.deleteSpeakers(id)
    dao.clearSegments(id)
    check(dao.deleteRecording(id)==1) { "Expected exactly one deleted recording" }
   }
  } catch(t: Throwable) {
   val pending=staged;val target=original
   if(pending!=null && target!=null && pending.exists() && !target.exists() && !pending.renameTo(target)) {
    throw ProductOperationException("Удаление не завершено. Аудио сохранено в приложении; откройте его заново для восстановления.","Cannot roll back staged audio ${pending.path} to ${target.path}",t)
   }
   throw t
  }
  val pending=staged
  val removed=pending?.let { !it.exists() || it.delete() }?:false
  DeleteOutcome(audioRemoved=removed,audioPreserved=preserved,cleanupPending=pending!=null && !removed)
 }

 /** Recover a process death between file staging and SQLite commit; ignores unrelated files. */
 suspend fun recoverPendingDeletions() = withContext(Dispatchers.IO) {
  val root=ownedRoot()?:return@withContext
  val trash=trashDirectory
  if(!trash.isDirectory || trash.canonicalFile.parentFile!=root || trash.canonicalFile.name!=".deleting") return@withContext
  val references=dao.recordingList()
  for(pending in trash.listFiles().orEmpty()) {
   if(!pending.isFile || pending.canonicalFile.parentFile!=trash.canonicalFile) continue
   val match=Regex("^[0-9a-fA-F-]{36}--(.+)$").matchEntire(pending.name)?:continue
   if(runCatching { UUID.fromString(pending.name.substring(0,36)) }.isFailure) continue
   val name=match.groupValues[1]
   if(name!=File(name).name) continue
   val target=File(root,name).canonicalFile
   if(target.parentFile!=root) continue
   val referenced=references.any { sameAudio(it.audioPath,target) }
   if(referenced && !target.exists()) {
    check(pending.renameTo(target)) { "Cannot restore staged audio ${pending.path}" }
   } else if(!referenced) {
    check(pending.delete()) { "Cannot remove staged deleted audio ${pending.path}" }
   }
  }
 }
}
