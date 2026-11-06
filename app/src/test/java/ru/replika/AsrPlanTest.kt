package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.AsrPlan

class AsrPlanTest {
 @Test fun historicalRequestsWithoutPlanStayLegacyAlongsideExplicitNewRequests() {
  assertEquals(AsrPlan.VAD_WORDS_CONTEXT600,AsrPlan.fromPersistedId("vad_words_context600"))
  assertEquals(AsrPlan.LEGACY,AsrPlan.fromPersistedId(null))
  assertEquals(AsrPlan.LEGACY,AsrPlan.fromPersistedId("v16"))
 }

 @Test(expected=IllegalStateException::class)
 fun unknownPersistedPlanFailsInsteadOfSilentlySelectingAnotherPipeline() {
  AsrPlan.fromPersistedId("unknown-future-profile")
 }
}
