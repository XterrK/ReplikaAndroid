package ru.replika
import org.junit.Test
import org.junit.Assert.*
import ru.replika.ui.*
class PresentationTest {
 @Test fun smallVerifiedVadHasNonzeroReadableSize() { assertEquals("629 КБ",formatBytes(643854));assertEquals("0 Б",formatBytes(0));assertEquals("1,0 МБ",formatBytes(1048576)) }
 @Test fun absentAndCorruptDiagnosticsDoNotInventMeasurements() { val d=DiagnosticView.parse("not JSON");assertNull(d.totalMs);assertNull(d.time("asrInferenceMs"));assertEquals("—",d.rtf);assertEquals("—",d.memory) }
 @Test fun legacyAsrStageIsNeverReportedAsPureInference() { val d=DiagnosticView.parse("""{"totalMs":16752,"stagesMs":{"asrMs":9616}}""");assertEquals(16752L,d.totalMs);assertNull(d.time("asrInferenceMs"));assertEquals(9616L,d.time("asrMs")) }
 @org.junit.Test fun subsecondAudioHasAVisibleDuration() {
  org.junit.Assert.assertEquals("650 мс",ru.replika.ui.audioClock(650))
  org.junit.Assert.assertEquals("31 мс",ru.replika.ui.audioClock(31,650))
  org.junit.Assert.assertEquals("00:11",ru.replika.ui.audioClock(11290))
 }
}
