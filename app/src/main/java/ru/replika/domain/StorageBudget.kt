package ru.replika.domain

import java.util.Locale
import kotlin.math.max

/**
 * Disk budget for importing and processing one file. Pure arithmetic, so it is JVM-tested.
 *
 * Import keeps either an app-owned copy of the source or only a reference to it. Processing later
 * writes a temporary Float32 16 kHz mono PCM file (64 000 bytes per second; 8 h ≈ 1.84 GB) to the
 * cache on the same /data partition. Both have to fit before work starts, plus a reserve for Room,
 * the import journal and the system itself.
 */
object StorageBudget {
 const val PCM_BYTES_PER_SECOND=16000L*4
 const val MIN_RESERVE_BYTES=64L*1024*1024
 /** Above this size the original is not copied when a durable read grant is available. */
 const val COPY_LIMIT_BYTES=512L*1024*1024

 enum class Strategy { COPY, REFERENCE }

 data class Estimate(val copyBytes: Long,val pcmBytes: Long,val reserveBytes: Long) {
  val totalBytes get()=copyBytes+pcmBytes+reserveBytes
 }
 data class Verdict(val estimate: Estimate,val freeBytes: Long) {
  val fits get()=freeBytes>=estimate.totalBytes
  val shortBytes get()=(estimate.totalBytes-freeBytes).coerceAtLeast(0)
 }
 data class Decision(val strategy: Strategy,val verdict: Verdict) { val fits get()=verdict.fits }

 /** Exact size of the temporary PCM written by [ru.replika.ml.AudioDecoder]; 0 when unknown. */
 fun pcmBytes(durationMs: Long): Long = if(durationMs<=0) 0 else Math.multiplyExact(durationMs,PCM_BYTES_PER_SECOND).let { (it+999)/1000 }
 /** At least 64 MiB, or 5 % of the payload for very large files. */
 fun reserveBytes(payloadBytes: Long): Long = max(MIN_RESERVE_BYTES,payloadBytes.coerceAtLeast(0)/20)
 fun estimate(copyBytes: Long,durationMs: Long): Estimate {
  val copy=copyBytes.coerceAtLeast(0);val pcm=pcmBytes(durationMs)
  return Estimate(copy,pcm,reserveBytes(copy+pcm))
 }
 fun check(copyBytes: Long,durationMs: Long,freeBytes: Long)=Verdict(estimate(copyBytes,durationMs),freeBytes)

 /**
  * Small files are copied (the recording survives deletion of the original). Large files are read
  * from the original when Android grants durable access; a large copy is used only if it fits.
  * [sourceBytes] < 0 means the provider did not report a size: copy with incremental checks.
  */
 fun choose(sourceBytes: Long,durationMs: Long,freeBytes: Long,canReference: Boolean): Decision {
  val copy=check(sourceBytes,durationMs,freeBytes)
  if(sourceBytes<0) return Decision(Strategy.COPY,copy)
  val reference=check(0,durationMs,freeBytes)
  return when {
   sourceBytes<=COPY_LIMIT_BYTES && copy.fits -> Decision(Strategy.COPY,copy)
   canReference -> Decision(Strategy.REFERENCE,reference)
   else -> Decision(Strategy.COPY,copy)
  }
 }

 /** Russian decimal units, matching what Android's storage settings show. */
 fun formatBytes(bytes: Long): String {
  val b=bytes.coerceAtLeast(0)
  return when {
   b>=1_000_000_000L -> String.format(Locale.ROOT,"%.1f ГБ",b/1e9).replace('.',',')
   b>=1_000_000L -> "${(b+500_000)/1_000_000} МБ"
   b>=1_000L -> "${(b+500)/1_000} КБ"
   else -> "$b Б"
  }
 }

 /** Message starts with "Недостаточно места:" so ProductErrors shows it verbatim. */
 fun importShortage(verdict: Verdict): String {
  val e=verdict.estimate
  val parts=buildList {
   if(e.copyBytes>0) add("копия файла ${formatBytes(e.copyBytes)}")
   if(e.pcmBytes>0) add("временные данные распознавания ${formatBytes(e.pcmBytes)}")
   add("запас ${formatBytes(e.reserveBytes)}")
  }
  return "Недостаточно места: нужно около ${formatBytes(e.totalBytes)} (${parts.joinToString(", ")}), " +
   "свободно ${formatBytes(verdict.freeBytes)}. Освободите ещё ${formatBytes(verdict.shortBytes)} и повторите импорт."
 }
 fun processingShortage(verdict: Verdict): String =
  "Недостаточно места: для обработки нужно около ${formatBytes(verdict.estimate.totalBytes)} " +
   "(временные данные распознавания ${formatBytes(verdict.estimate.pcmBytes)} и запас), свободно ${formatBytes(verdict.freeBytes)}. " +
   "Освободите ещё ${formatBytes(verdict.shortBytes)} и повторите обработку."
}
