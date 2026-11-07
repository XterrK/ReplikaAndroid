package ru.replika.domain

import java.io.FileNotFoundException

/** Recoverable user copy. Original exception details are retained separately by AppViewModel. */
object ProductErrors {
 fun message(context: String,detail: String?,missingFile: Boolean = false,denied: Boolean = false): String {
  val text=detail.orEmpty().lowercase(java.util.Locale.ROOT)
  val operation=context.lowercase(java.util.Locale.ROOT)
  // Messages already written for the user (storage budget, Android time limit, missing original).
  if(VERBATIM_PREFIXES.any { text.startsWith(it) }) return detail.orEmpty()
  if(text.contains("enospc") || text.contains("no space left") || text.contains("недостаточно места") || text.contains("свободное место")) return "Не хватает свободного места. Освободите место на устройстве и повторите действие."
  if(text.contains("outofmemory") || text.contains("недостаточно памяти") || text.contains("не хватает памяти")) return "Для этой записи не хватает памяти. Закройте другие приложения или разделите аудио на более короткие части."
  if(denied || text.contains("permission denied")) return if(operation=="запись" || operation=="остановка записи" || operation.contains("микроф")) "Нет доступа к микрофону. Разрешите запись в настройках приложения или импортируйте аудиофайл." else "Нет доступа к файлу. Выберите его заново через «Импорт»."
  if(missingFile || text.contains("no such file") || text.contains("file not found")) return "Исходное аудио недоступно. Импортируйте файл заново; сохранённая стенограмма остаётся в библиотеке."
  if(operation.contains("воспроиз") || operation.contains("декод") || text.contains("extractor") || text.contains("setdatasource failed") || text.contains("неподдерживаемый pcm") || text.contains("повреждённый аудиофайл") || text.contains("source error") || text.contains("нет аудиодорожки") || text.contains("повреждённый аудио")) return "Не удалось прочитать аудио. Файл может быть повреждён или его формат не поддерживается. Импортируйте другую копию WAV, MP3 или M4A."
  if(operation.contains("модел")) return if(text.contains("контрольная сумма") || text.contains("checksum") || text.contains("sha-256")) "Файлы модели повреждены или не совпадают с набором REPLIKA. Импортируйте проверенный offline pack заново." else "Не удалось подготовить модели. Проверьте свободное место и импортируйте проверенный offline pack заново."
  if(operation.contains("импорт")) return "Не удалось импортировать файл. Проверьте, что он доступен и содержит аудио, затем выберите его заново."
  if(operation.contains("удал")) return "Не удалось удалить запись. Она сохранена; повторите попытку."
  if(operation.contains("остановка записи")) return "Запись слишком короткая или была прервана. Попробуйте записать ещё раз."
  if(operation.contains("запис") || operation.contains("микроф")) return "Не удалось начать или продолжить запись. Проверьте доступ к микрофону и свободное место, затем повторите попытку."
  if(operation.contains("сохран") || operation.contains("отмен") || operation.contains("переимен")) return "Не удалось сохранить изменения. Повторите действие; прежние данные сохранены."
  if(text.startsWith("установите") || text.startsWith("укажите от") || text.startsWith("разделите")) return detail.orEmpty()
  return "Не удалось завершить действие. Повторите попытку. Исходное аудио и сохранённые данные остаются в приложении."
 }
 private val VERBATIM_PREFIXES=listOf("недостаточно места:","android остановил","исходный файл недоступен")
 fun causes(error: Throwable): List<Throwable> = generateSequence(error) { it.cause?.takeIf { cause -> cause!==it } }.take(12).toList()
 fun fromThrowable(context: String,error: Throwable): String {
  val causes=causes(error)
  return message(context,causes.joinToString("\n") { "${it.javaClass.simpleName}: ${it.message.orEmpty()}" },causes.any { it is FileNotFoundException },causes.any { it is SecurityException })
 }
}
