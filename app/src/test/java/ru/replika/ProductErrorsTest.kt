package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.ProductErrors
import java.io.FileNotFoundException
import java.io.IOException

class ProductErrorsTest {
 @Test fun brokenContainerHasAnActionAndNoRawEnglish() {
  val message=ProductErrors.message("Обработка","Failed to instantiate extractor")
  assertTrue(message.contains("WAV"));assertTrue(message.contains("Импортируйте"));assertFalse(message.contains("extractor"))
  assertTrue(ProductErrors.message("Обработка","setDataSource failed: status = 0x80000000").contains("Импортируйте"))
  assertFalse(ProductErrors.fromThrowable("Воспроизведение",IllegalStateException("Source error")).contains("Source error"))
 }
 @Test fun missingFileAndPermissionFailureHaveDifferentRecoveryActions() {
  val missing=ProductErrors.fromThrowable("Воспроизведение",FileNotFoundException("/private/audio/missing.wav"))
  val denied=ProductErrors.fromThrowable("Импорт",SecurityException("Permission denied: private URI"))
  assertTrue(missing.contains("стенограмма"));assertTrue(denied.contains("Выберите"));assertNotEquals(missing,denied)
  assertFalse(missing.contains("/private"));assertFalse(denied.contains("private URI"))
 }
 @Test fun noSpaceAndMemoryHaveSpecificRemedies() {
  val disk=ProductErrors.fromThrowable("Импорт",IOException("ENOSPC: No space left on device"))
  val memory=ProductErrors.fromThrowable("Обработка",OutOfMemoryError("native allocation"))
  assertTrue(disk.contains("Освободите место"));assertTrue(memory.contains("разделите аудио"));assertNotEquals(disk,memory)
 }
}
