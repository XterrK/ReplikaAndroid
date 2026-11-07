package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.ui.breakableTitle

class BreakableTitleTest {
 @Test fun fileNamesGetBreakOpportunitiesAndNormalTitlesStayUntouched() {
  val shown=breakableTitle("dialog-two-speakers.wav")
  assertEquals("dialog-two-speakers.wav",shown.replace("​",""))
  assertEquals("dialog-​two-​speakers​.wav",shown)
  assertEquals("Запись 07.11 14:35",breakableTitle("Запись 07.11 14:35"))
  assertEquals("rec_​01​.m4a",breakableTitle("rec_01.m4a"))
  assertEquals("v1.2.3",breakableTitle("v1.2.3").replace("​",""))
  assertEquals("",breakableTitle(""))
 }
}
