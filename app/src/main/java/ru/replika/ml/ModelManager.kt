package ru.replika.ml

import android.content.Context
import android.net.Uri
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.apache.commons.compress.compressors.bzip2.BZip2CompressorInputStream
import java.io.*
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.zip.ZipInputStream

data class ModelFile(val group: String,val path: String,val url: String,val member: String?,val size: Long,val sha256: String)
data class ModelStatus(val id: String,val title: String,val installed: Boolean,val bytes: Long,val expected: Long)
class ModelManager(private val context: Context) {
 val gate=Mutex()
 val root=File(context.filesDir,"models").apply { mkdirs() }
 private val files: List<ModelFile> by lazy {
  val j=JSONObject(context.assets.open("models-lock.json").bufferedReader().use { it.readText() }).getJSONArray("files")
  List(j.length()) { i -> j.getJSONObject(i).let { ModelFile(it.getString("group"),it.getString("path"),it.getString("url"),if(it.isNull("archiveMember")) null else it.getString("archiveMember"),it.getLong("size"),it.getString("sha256")) } }
 }
 fun file(path: String)=File(root,path)
 fun specifications(): List<ModelFile> = files.toList()
 private fun hash(f: File): String {
  val md=MessageDigest.getInstance("SHA-256")
  f.inputStream().buffered().use { s -> val b=ByteArray(128*1024);while(true) { val n=s.read(b);if(n<0) break;md.update(b,0,n) } }
  return md.digest().joinToString("") { "%02x".format(it) }
 }
 fun valid(spec: ModelFile): Boolean { val f=file(spec.path);return f.isFile && f.length()==spec.size && hash(f)==spec.sha256 }
 val asrId: String get()=files.map { it.group }.distinct().single { it.startsWith("giga-") }
 fun resolveBackend(legacyId: String?): String = if(legacyId==asrId) legacyId else asrId
 /** Optional language groups (pack v1.6). Their absence never blocks Russian processing. */
 fun groupReady(group: String): Boolean { val selected=files.filter { it.group==group };return selected.isNotEmpty() && selected.all { valid(it) } }
 fun requireEnglishReady()=require(groupReady(ENGLISH_GROUP)) { "Для английской записи установите модель Parakeet (English) в разделе «Модели»" }
 fun statuses(): List<ModelStatus> = (listOf(asrId to (if(asrId=="giga-v3") "GigaAM v3" else "GigaAM v2"), "diar" to "Разделение говорящих", "vad" to "Silero VAD")+
  listOf(ENGLISH_GROUP to "Parakeet TDT v2 · English", LID_GROUP to "Определение языка · Whisper tiny").filter { (id,_) -> files.any { it.group==id } }).map { (id,title) ->
  val selected=files.filter { it.group==id };ModelStatus(id,title,selected.isNotEmpty() && selected.all { valid(it) },selected.sumOf { file(it.path).takeIf(File::isFile)?.length()?:0 },selected.sumOf { it.size })
 }
 fun requireReady(backend: String = asrId, includeDiarization: Boolean = true) {
  require(backend==asrId) { "Выбранная модель больше не поддерживается. Используйте GigaAM." }
  val groups=if(includeDiarization) setOf(backend,"vad","diar") else setOf(backend,"vad")
  val required=files.filter { it.group in groups };require(required.isNotEmpty() && required.all { valid(it) }) { "Установите и проверьте GigaAM, VAD и модели говорящих в разделе «Модели»" }
 }
 /** Retire only the app-owned removed weight; recordings and external packs are untouched. Call under gate. */
 fun removeRetiredWhisperFiles() {
  val retired=File(root,"whisper-tiny/ggml-tiny.bin")
  if(retired.exists() && retired.canonicalFile.toPath().startsWith(root.canonicalFile.toPath())) {
   check(retired.delete()) { "Не удалось удалить файл снятой модели" }
   retired.parentFile?.let { if(it.listFiles().orEmpty().isEmpty()) it.delete() }
  }
 }
 companion object {
  const val LID_GROUP="lid-whisper-tiny"
  const val ENGLISH_GROUP="parakeet-en-v2"
 }
 suspend fun delete(group: String)=gate.withLock { withContext(Dispatchers.IO) { files.filter { it.group==group }.forEach { file(it.path).delete() } } }
 suspend fun download(group: String, progress: (String)->Unit)=gate.withLock { withContext(Dispatchers.IO) {
  val selected=files.filter { it.group==group };require(selected.isNotEmpty())
  for((url,specs) in selected.groupBy { it.url }) {
   if(specs.all { valid(it) }) continue
   val cache=File(context.cacheDir,"model-downloads").apply { mkdirs() }
   val part=File(cache,url.substringAfterLast('/')+".part")
   val connection=URL(url).openConnection() as HttpURLConnection
   connection.connectTimeout=30000;connection.readTimeout=30000
   val existing=part.length();if(existing>0) connection.setRequestProperty("Range","bytes=$existing-")
   try {
    val code=connection.responseCode
    if(code==416 && existing>0) {
     val remoteSize=connection.getHeaderField("Content-Range")?.substringAfter("*/","")?.toLongOrNull()
     if(remoteSize!=existing) { part.delete();error("Размер прерванной загрузки изменился. Повторите загрузку с начала.") }
     // Complete archive survived process death before installation. Validate its members below.
    } else {
     require(code==200 || code==206) { "Ошибка загрузки HTTP $code" }
     val append=code==206 && existing>0
     if(code==206) require(connection.getHeaderField("Content-Range")?.startsWith("bytes $existing-")==true) { "Неверный диапазон загрузки" }
     val expectedPayload=connection.contentLengthLong
     connection.inputStream.use { input -> FileOutputStream(part,append).use { output ->
      val buf=ByteArray(128*1024);var total=if(append) existing else 0;var received=0L
      while(true) { currentCoroutineContext().ensureActive();val n=input.read(buf);if(n<0) break;output.write(buf,0,n);total+=n;received+=n;progress("Загрузка: ${total/1024/1024} МБ") }
      require(expectedPayload<0 || received==expectedPayload) { "Соединение прервано. Файл сохранён для продолжения загрузки." }
     } }
    }
   } finally { connection.disconnect() }
   progress("Проверка файлов…")
   try {
    if(specs.first().member==null) part.inputStream().use { install(it,specs.first()) }
    else TarArchiveInputStream(BZip2CompressorInputStream(part.inputStream().buffered())).use { tar ->
     while(true) { currentCoroutineContext().ensureActive();val entry=tar.nextEntry?:break
      specs.firstOrNull { it.member==entry.name.substringAfterLast('/') }?.let { install(tar,it) }
     }
    }
    require(specs.all { valid(it) }) { "Неполный комплект модели" }
    part.delete()
   } catch(e: Throwable) { part.delete();throw e }
  }
 } }
 private fun install(input: InputStream,spec: ModelFile) {
  val target=file(spec.path);target.parentFile!!.mkdirs();val tmp=File(target.path+".installing")
  try {
   tmp.outputStream().buffered().use { out -> val b=ByteArray(128*1024);var total=0L
    while(true) { val n=input.read(b);if(n<0) break;total+=n;require(total<=spec.size) { "Размер модели превышает манифест" };out.write(b,0,n) }
   }
   require(tmp.length()==spec.size && hash(tmp)==spec.sha256) { "Контрольная сумма ${spec.path} не совпадает" }
   check(tmp.renameTo(target)) { "Не удалось установить ${spec.path}" }
  } finally { tmp.delete() }
 }
 suspend fun importPack(uri: Uri,progress: (String)->Unit)=gate.withLock { withContext(Dispatchers.IO) {
  context.contentResolver.openInputStream(uri)!!.use { input -> ZipInputStream(input.buffered()).use { zip ->
   while(true) { currentCoroutineContext().ensureActive();val e=zip.nextEntry?:break
    files.firstOrNull { it.path==e.name }?.let { progress("Проверка ${it.path}");install(zip,it) }
    zip.closeEntry()
   }
  } };requireReady()
 } }
}
