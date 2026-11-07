package ru.replika.domain

/**
 * What a cancelled ProcessingWorker means for its recording.
 *
 * WorkManager reports why it stopped a worker (`ListenableWorker.getStopReason()`); the numeric
 * values below are WorkManager's `WorkInfo.STOP_REASON_*` constants, copied so the policy stays a
 * pure JVM-tested function.
 */
object ProcessingStopPolicy {
 const val STOP_REASON_FOREGROUND_SERVICE_TIMEOUT=-128
 const val STOP_REASON_NOT_STOPPED=-256
 const val STOP_REASON_CANCELLED_BY_APP=1

 enum class Outcome {
  /** User pressed cancel (or the app cancelled the work): the recording becomes CANCELLED. */
  CANCELLED,
  /** Android 15+ foreground-service time limit (6 h per 24 h in the background) was reached. */
  FOREGROUND_TIMEOUT,
  /** Any other system stop: WorkManager reschedules the same request; keep the recording QUEUED. */
  SYSTEM_RETRY
 }

 fun classify(userRequested: Boolean,workerStopped: Boolean,stopReason: Int): Outcome = when {
  userRequested -> Outcome.CANCELLED
  !workerStopped -> Outcome.CANCELLED
  stopReason==STOP_REASON_FOREGROUND_SERVICE_TIMEOUT -> Outcome.FOREGROUND_TIMEOUT
  stopReason==STOP_REASON_CANCELLED_BY_APP -> Outcome.CANCELLED
  else -> Outcome.SYSTEM_RETRY
 }

 /**
  * After a timeout WorkManager reschedules the stopped request before the Worker's own cancel lands;
  * that short-lived second attempt must not replace the explained timeout error with CANCELLED.
  */
 fun keepsTimeoutError(status: String?,phase: String?,userRequested: Boolean)=!userRequested && status=="ERROR" && phase==TIMEOUT_PHASE
 const val TIMEOUT_PHASE="Остановлено системой"
 /** Starts with "Android остановил" so ProductErrors shows it verbatim. */
 const val TIMEOUT_MESSAGE="Android остановил долгую фоновую обработку: в фоне система разрешает её не дольше 6 часов в сутки. " +
  "Откройте запись и нажмите «Повторить обработку» — она начнётся заново. Чтобы лимит не закончился снова, держите приложение открытым на экране: так счётчик Android сбрасывается."
 /** Shown when Android refuses to start the foreground service because today's limit is used up. */
 const val FOREGROUND_START_MESSAGE="Android остановил запуск фоновой обработки: дневной лимит фоновой работы (6 часов) исчерпан. " +
  "Откройте приложение на экране и нажмите «Повторить обработку»."
 /** ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC and FOREGROUND_SERVICE_TYPE_MEDIA_PROCESSING (API 35). */
 const val FGS_TYPE_DATA_SYNC=1
 const val FGS_TYPE_MEDIA_PROCESSING=0x2000
 /** Android 15+ has mediaProcessing for transcoding-like work, with its own 6 h budget separate from dataSync. */
 fun foregroundServiceType(sdk: Int)=if(sdk>=35) FGS_TYPE_MEDIA_PROCESSING else FGS_TYPE_DATA_SYNC
 /** Error text stored on the recording; ProductErrors turns unknown technical text into generic advice. */
 fun failureMessage(error: Throwable): String = when(error.javaClass.name) {
  "android.app.ForegroundServiceStartNotAllowedException" -> FOREGROUND_START_MESSAGE
  else -> error.message?:error.javaClass.simpleName
 }
 const val RETRY_PHASE="Android приостановил обработку · задание продолжится автоматически"
}
