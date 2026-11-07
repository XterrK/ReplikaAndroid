package ru.replika.domain

import org.junit.Assert.assertEquals
import org.junit.Test

class NearestSpeakerTest {
 private fun word(start: Long,end: Long,text: String="да")=VadWordPlanner.Word(start,end,text)
 private val turns=listOf(Turn(500,4000,0),Turn(4600,9000,1))

 @Test fun wordBeforeFirstTurnTakesThatTurn() {
  // The "Да," at 400-440 ms seen on the phone: it lands just before speaker 0 starts.
  assertEquals(0,VadWordPlanner.assignWords(listOf(word(400,440)),turns).single().speaker)
 }

 @Test fun gapWordTakesTheCloserTurn() {
  assertEquals(0,VadWordPlanner.nearestSpeaker(word(4050,4100),turns,1500))
  assertEquals(1,VadWordPlanner.nearestSpeaker(word(4450,4500),turns,1500))
 }

 @Test fun farWordStaysUnknownAndZeroLimitDisables() {
  assertEquals(-1,VadWordPlanner.nearestSpeaker(word(12000,12100),turns,1500))
  assertEquals(-1,VadWordPlanner.nearestSpeaker(word(400,440),turns,0))
 }

 @Test fun equallyCloseDifferentSpeakersStayUnknown() {
  assertEquals(-1,VadWordPlanner.nearestSpeaker(word(4250,4350),turns,1500))
 }

 @Test fun tiesAndExplicitUnknownTurnsStayUnknown() {
  val overlapping=listOf(Turn(0,1000,0),Turn(1000,2000,1))
  // Word 950-1050 overlaps each turn by exactly 50 ms: a tie is never resolved by guessing.
  assertEquals(-1,VadWordPlanner.assignWords(listOf(word(950,1050)),overlapping).single().speaker)
  assertEquals(-1,VadWordPlanner.assignWords(listOf(word(400,440)),listOf(Turn(300,450,-1))+turns).single().speaker)
 }

 @Test fun groupingJoinsTheRescuedWordWithItsNeighbour() {
  val assigned=VadWordPlanner.assignWords(listOf(word(400,440,"Да,"),word(600,900,"но"),word(950,1300,"работа.")),turns)
  val segments=VadWordPlanner.groupWords(assigned,"test")
  assertEquals(1,segments.size)
  assertEquals("Да, но работа.",segments.single().text)
  assertEquals(0,segments.single().speakerId)
 }
}
