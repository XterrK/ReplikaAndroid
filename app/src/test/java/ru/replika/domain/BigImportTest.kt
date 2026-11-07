package ru.replika.domain

import org.junit.Assert.*
import org.junit.Test

class StorageBudgetTest {
 private val GB=1_000_000_000L
 private val hour=3_600_000L

 @Test fun pcmMatchesDecoderFloat32At16kHz() {
  assertEquals(64_000L,StorageBudget.pcmBytes(1000))
  // 8 h × 3600 s × 16 000 samples × 4 bytes.
  assertEquals(1_843_200_000L,StorageBudget.pcmBytes(8*hour))
  assertEquals(0L,StorageBudget.pcmBytes(0));assertEquals(0L,StorageBudget.pcmBytes(-5))
  assertEquals(64L,StorageBudget.pcmBytes(1)) // rounds up, never under-estimates
 }
 @Test fun reserveIsAtLeast64MiBAndFivePercentOfLargePayloads() {
  assertEquals(64L*1024*1024,StorageBudget.reserveBytes(10_000_000))
  assertEquals(GB/20*7,StorageBudget.reserveBytes(7*GB))
 }
 @Test fun fiveGigabyteEightHourFileNeedsCopyPcmAndReserve() {
  val e=StorageBudget.estimate(5*GB,8*hour)
  assertEquals(5*GB,e.copyBytes);assertEquals(1_843_200_000L,e.pcmBytes)
  assertEquals((5*GB+1_843_200_000L)/20,e.reserveBytes)
  assertEquals(e.copyBytes+e.pcmBytes+e.reserveBytes,e.totalBytes)
  val v=StorageBudget.check(5*GB,8*hour,3*GB)
  assertFalse(v.fits);assertEquals(e.totalBytes-3*GB,v.shortBytes)
  assertTrue(StorageBudget.check(5*GB,8*hour,8*GB).fits)
 }
 @Test fun smallFilesAreCopiedWhenTheyFit() {
  val d=StorageBudget.choose(30_000_000,3*60_000,4*GB,canReference=true)
  assertEquals(StorageBudget.Strategy.COPY,d.strategy);assertTrue(d.fits)
 }
 @Test fun largeFilesAreReferencedWhenAndroidGrantsDurableAccess() {
  val d=StorageBudget.choose(5*GB,8*hour,3*GB,canReference=true)
  assertEquals(StorageBudget.Strategy.REFERENCE,d.strategy);assertTrue(d.fits)
  assertEquals(0L,d.verdict.estimate.copyBytes)
 }
 @Test fun smallFileThatDoesNotFitAsCopyFallsBackToReference() {
  // 400 MB WAV, 2 h: copy+PCM does not fit in 700 MB, PCM alone does.
  val d=StorageBudget.choose(400_000_000,2*hour,700_000_000,canReference=true)
  assertEquals(StorageBudget.Strategy.REFERENCE,d.strategy);assertTrue(d.fits)
 }
 @Test fun withoutDurableGrantLargeFileIsCopiedOnlyIfItFits() {
  assertEquals(StorageBudget.Strategy.COPY,StorageBudget.choose(2*GB,3*hour,10*GB,canReference=false).strategy)
  assertTrue(StorageBudget.choose(2*GB,3*hour,10*GB,canReference=false).fits)
  val tight=StorageBudget.choose(2*GB,3*hour,2*GB,canReference=false)
  assertEquals(StorageBudget.Strategy.COPY,tight.strategy);assertFalse(tight.fits)
 }
 @Test fun referenceThatStillDoesNotFitIsReportedAsShortage() {
  val d=StorageBudget.choose(5*GB,8*hour,1*GB,canReference=true)
  assertEquals(StorageBudget.Strategy.REFERENCE,d.strategy);assertFalse(d.fits)
  assertTrue(d.verdict.shortBytes>800_000_000)
 }
 @Test fun unknownSizeCopiesWithIncrementalChecks() {
  val d=StorageBudget.choose(-1,hour,GB,canReference=true)
  assertEquals(StorageBudget.Strategy.COPY,d.strategy);assertEquals(0L,d.verdict.estimate.copyBytes)
 }
 @Test fun bytesAreFormattedLikeAndroidSettings() {
  assertEquals("1,8 ГБ",StorageBudget.formatBytes(1_843_200_000))
  assertEquals("5,0 ГБ",StorageBudget.formatBytes(5*GB))
  assertEquals("350 МБ",StorageBudget.formatBytes(350_000_000))
  assertEquals("12 КБ",StorageBudget.formatBytes(12_000))
  assertEquals("0 Б",StorageBudget.formatBytes(-3))
 }
 @Test fun shortageMessagesNameEveryPartAndAreShownVerbatim() {
  val v=StorageBudget.check(5*GB,8*hour,3*GB)
  val text=StorageBudget.importShortage(v)
  assertTrue(text,text.startsWith("Недостаточно места: нужно около 7,2 ГБ"))
  assertTrue(text,text.contains("копия файла 5,0 ГБ"));assertTrue(text,text.contains("временные данные распознавания 1,8 ГБ"))
  assertTrue(text,text.contains("свободно 3,0 ГБ"));assertTrue(text,text.contains("Освободите ещё 4,2 ГБ"))
  assertEquals(text,ProductErrors.message("Импорт аудио и видео",text))
  val processing=StorageBudget.processingShortage(StorageBudget.check(0,8*hour,GB))
  assertTrue(processing.startsWith("Недостаточно места: для обработки нужно около 1,9 ГБ"))
  assertEquals(processing,ProductErrors.message("Обработка",processing))
  // Older technical disk errors keep the generic advice.
  assertEquals("Не хватает свободного места. Освободите место на устройстве и повторите действие.",ProductErrors.message("Обработка","write failed: ENOSPC (No space left on device)"))
 }
}

class ProcessingEtaTest {
 private val eta=ProcessingEta()
 private val all=ProcessingEta.stagesFor(speakers=true)

 @Test fun currentStageIsExtrapolatedFromItsMeasuredSpeed() {
  // Recognition: 25 % done after 60 s -> 180 s left, nothing after recognition.
  val ms=eta.estimate(ProcessingStage.RECOGNITION,.25f,60_000,3_600_000,emptyList(),listOf(ProcessingStage.RECOGNITION))
  assertEquals(180_000L,ms)
 }
 @Test fun priorsAreUsedUntilTheStageHasMeasurableWork() {
  val audio=600_000L
  val early=eta.estimate(ProcessingStage.DECODING,.001f,500,audio,emptyList(),all)!!
  val priors=ProcessingEta.DEFAULT_PRIORS.values.sum()*audio
  assertEquals(priors,early.toDouble(),audio*.011)
 }
 @Test fun laterStagesAreScaledByObservedDeviceSpeed() {
  val audio=3_600_000L
  // Decoding and VAD took 4× their priors: the device is slow, so later priors are scaled 4×.
  val done=listOf(ProcessingEta.Completed(ProcessingStage.DECODING,(.01*audio*4).toLong()),
   ProcessingEta.Completed(ProcessingStage.SPEECH,(.02*audio*4).toLong()))
  val ms=eta.estimate(ProcessingStage.SPEAKERS,0f,0,audio,done,all.drop(2))!!
  assertEquals((.45+.10)*audio*4,ms.toDouble(),audio*.01)
 }
 @Test fun slowDecodingAloneDoesNotInflateLaterStages() {
  val audio=3_000_000L
  // 48 kHz stereo decoding at 3x its prior: later stages keep their priors.
  val ms=eta.estimate(ProcessingStage.DECODING,.5f,(.01*audio*3*.5).toLong().coerceAtLeast(3000),audio,emptyList(),all)!!
  val decodingLeft=(.01*audio*3*.5)
  assertEquals(decodingLeft+(.02+.45+.10)*audio,ms.toDouble(),audio*.01)
 }
 @Test fun singleSpeakerModeSkipsTheSpeakerStage() {
  assertEquals(listOf(ProcessingStage.DECODING,ProcessingStage.SPEECH,ProcessingStage.RECOGNITION),ProcessingEta.stagesFor(false))
  val audio=600_000L
  val withSpeakers=eta.estimate(ProcessingStage.SPEECH,0f,0,audio,emptyList(),all.drop(1))!!
  val single=eta.estimate(ProcessingStage.SPEECH,0f,0,audio,emptyList(),ProcessingEta.stagesFor(false).drop(1))!!
  assertTrue(withSpeakers>single)
 }
 @Test fun calibrationIsBoundedAndUnknownDurationHasNoEstimate() {
  val audio=600_000L
  val absurd=listOf(ProcessingEta.Completed(ProcessingStage.SPEECH,10_000_000))
  val ms=eta.estimate(ProcessingStage.SPEAKERS,0f,0,audio,absurd,all.drop(2))!!
  assertEquals(((.45+.10)*audio*ProcessingEta.MAX_CALIBRATION),ms.toDouble(),2.0)
  assertNull(eta.estimate(ProcessingStage.SPEECH,.5f,10_000,0,emptyList(),all))
  // Indeterminate stage (speaker refinement) still gets a prior-based estimate.
  assertNotNull(eta.estimate(ProcessingStage.SPEAKERS,null,30_000,audio,emptyList(),all.drop(2)))
 }
 @Test fun etaIsFormattedInWholeMinutesRoundedUp() {
  assertNull(ProcessingEta.format(null));assertNull(ProcessingEta.format(-1))
  assertEquals("меньше минуты",ProcessingEta.format(59_000))
  assertEquals("≈ 1 мин",ProcessingEta.format(60_000))
  assertEquals("≈ 2 мин",ProcessingEta.format(61_000))
  assertEquals("≈ 1 ч 05 мин",ProcessingEta.format(65*60_000L))
  assertEquals("≈ 8 ч 00 мин",ProcessingEta.format(8*3_600_000L))
 }
 @Test fun snapshotSurvivesWorkManagerDataRoundTrip() {
  val s=ProcessingSnapshot(ProcessingStage.SPEAKERS,.4f,1_440_000,3_600_000,95_000)
  assertEquals(40,s.percent)
  assertEquals(s,ProcessingSnapshot.fromValues(s.toMap()))
  val unknown=ProcessingSnapshot(ProcessingStage.SPEAKERS,null,0,3_600_000,null)
  assertEquals(unknown,ProcessingSnapshot.fromValues(unknown.toMap()))
  assertNull(unknown.percent)
  assertNull(ProcessingSnapshot.fromValues(mapOf("progressStage" to "NOPE")))
  assertNull(ProcessingSnapshot.fromValues(emptyMap()))
 }
}

class ProcessingStopPolicyTest {
 private val P=ProcessingStopPolicy
 @Test fun userCancelAlwaysWins() {
  assertEquals(ProcessingStopPolicy.Outcome.CANCELLED,P.classify(true,true,P.STOP_REASON_FOREGROUND_SERVICE_TIMEOUT))
  assertEquals(ProcessingStopPolicy.Outcome.CANCELLED,P.classify(true,false,P.STOP_REASON_NOT_STOPPED))
 }
 @Test fun androidForegroundTimeoutBecomesAnExplainedError() {
  assertEquals(ProcessingStopPolicy.Outcome.FOREGROUND_TIMEOUT,P.classify(false,true,-128))
  assertTrue(P.TIMEOUT_MESSAGE.startsWith("Android остановил"))
  assertEquals(P.TIMEOUT_MESSAGE,ProductErrors.message("Обработка",P.TIMEOUT_MESSAGE))
 }
 @Test fun rescheduledAttemptDoesNotHideTheTimeoutError() {
  assertTrue(P.keepsTimeoutError("ERROR",P.TIMEOUT_PHASE,false))
  assertFalse(P.keepsTimeoutError("ERROR",P.TIMEOUT_PHASE,true))
  assertFalse(P.keepsTimeoutError("ERROR","Обработка прервана",false))
  assertFalse(P.keepsTimeoutError("QUEUED","Ожидание обработки",false)) // user pressed retry
 }
 @Test fun appCancellationAndInternalCancellationStayCancelled() {
  assertEquals(ProcessingStopPolicy.Outcome.CANCELLED,P.classify(false,true,P.STOP_REASON_CANCELLED_BY_APP))
  assertEquals(ProcessingStopPolicy.Outcome.CANCELLED,P.classify(false,false,P.STOP_REASON_NOT_STOPPED))
 }
 @Test fun otherSystemStopsAreRetriedByWorkManager() {
  for(reason in listOf(2,3,4,10,12,14,-512)) assertEquals(ProcessingStopPolicy.Outcome.SYSTEM_RETRY,P.classify(false,true,reason))
 }
 @Test fun mediaProcessingOnAndroid15AndDataSyncBefore() {
  assertEquals(1,P.foregroundServiceType(29));assertEquals(1,P.foregroundServiceType(34))
  assertEquals(0x2000,P.foregroundServiceType(35));assertEquals(0x2000,P.foregroundServiceType(36))
 }
 @Test fun failureMessageKeepsTechnicalTextExceptForTheForegroundLimit() {
  assertEquals("boom",P.failureMessage(IllegalStateException("boom")))
  assertEquals("IllegalStateException",P.failureMessage(IllegalStateException()))
  assertEquals(P.FOREGROUND_START_MESSAGE,ProductErrors.message("Обработка",P.FOREGROUND_START_MESSAGE))
 }
}
