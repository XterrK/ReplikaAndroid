package ru.replika.ml

import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import ru.replika.domain.Alignment
import ru.replika.domain.ChunkedDiarization
import ru.replika.domain.CpuPlan
import ru.replika.domain.Turn

/** Orchestration with fake SD/extractor (no JNI). PCM encodes the true speaker as a constant
 * level (1, 2, 3; 0 is silence), so local labels are arbitrary per window and only the
 * global centroid clustering can make them consistent across the recording. */
class ChunkedDiarizationRunnerTest {
 private val truth=buildList {
  var t=0L;var s=0
  val order=intArrayOf(0,1,0,2,1,2,0,1)
  while(t<100_000) { add(Turn(t,minOf(100_000,t+3_000+(t/7)%2_000),order[s%order.size]));t+=4_000+(t/11)%1_500;s++ }
 }
 private val pcm=FloatArray(100_000*16).also { a -> truth.forEach { turn -> for(i in (turn.startMs*16).toInt() until (turn.endMs*16).toInt()) a[i]=turn.speaker+1f } }
 private val config=ChunkedDiarization.Config(minDurationMs=30_000,windowMs=20_000,overlapMs=2_000,globalTau=.5)

 /** SD: contiguous constant levels become turns; labels by first appearance inside the window. */
 private val fakeSd=ChunkedDiarizationRunner.WindowSd { samples,durationMs ->
  val out=mutableListOf<Turn>();var start=-1L;var level=0f
  for(ms in 0..durationMs) {
   val v=if(ms<durationMs) samples[(ms*16).toInt()] else 0f
   if(v!=level) { if(level!=0f) out+=Turn(start,ms,(level*7).toInt()%5);start=ms;level=v }
  }
  Alignment.stable(out)
 }
 private class Factory : DiarizationRefiner.EmbeddingFactory {
  override fun open(modelPath: String,threads: Int)=object : DiarizationRefiner.EmbeddingSession {
   override val dimension=3
   override fun createStream()=object : DiarizationRefiner.EmbeddingStream {
    var level=0f
    override fun acceptWaveform(samples: FloatArray,sampleRate: Int) { level=samples.max() }
    override fun inputFinished() {}
    override fun isReady()=true
    override fun compute()=FloatArray(3) { if(it==level.toInt()-1) 1f else .05f }
    override fun close() {}
   }
   override fun close() {}
  }
 }

 @Test fun windowsAreReadOneAtATimeAndSpeakersStayGloballyConsistent() = runBlocking {
  val reads=mutableListOf<Pair<Int,Int>>()
  val result=ChunkedDiarizationRunner.run(100_000,pcm.size,config,
   readPcm={first,count -> reads+=first to count;pcm.copyOfRange(first,first+count)},
   sd=fakeSd,
   refine={turns,durationMs,samples -> DiarizationRefiner.refineOriginalPcm(turns,durationMs,"fake.onnx",2,
    readOriginalWindow={a,b -> samples.copyOfRange((a*16).toInt(),(b*16).toInt())},embeddingFactory=Factory(),
    cpuPlan=CpuPlan.LEGACY,retainWindows=true)})
  val windows=ChunkedDiarization.planWindows(100_000,config)
  assertEquals(windows.map { (it.startMs*16).toInt() to (it.durationMs*16).toInt() },reads)
  assertTrue(reads.all { it.second<=config.windowMs*16 })
  assertTrue(result.accepted)
  assertEquals(3,result.turns.map { it.speaker }.distinct().size)
  // Each output label owns one true speaker; >=97% of speech time is attributed consistently
  // (C2 may still fold a <2 s edge fragment into a neighbour inside one window).
  val time=mutableMapOf<Pair<Int,Int>,Long>()
  for(turn in result.turns) for(ref in truth) {
   val overlap=minOf(turn.endMs,ref.endMs)-maxOf(turn.startMs,ref.startMs)
   if(overlap>0) time[turn.speaker to ref.speaker]=(time[turn.speaker to ref.speaker]?:0L)+overlap
  }
  val owners=result.turns.map { it.speaker }.distinct().associateWith { label -> time.filterKeys { it.first==label }.maxBy { it.value }.key.second }
  assertEquals(setOf(0,1,2),owners.values.toSet())
  val correct=time.filter { owners[it.key.first]==it.key.second }.values.sum()
  assertTrue("consistent ${correct}/${truth.sumOf { it.endMs-it.startMs }}",correct>=.97*truth.sumOf { it.endMs-it.startMs })
  assertEquals(windows.size,(result.diagnostics["windows"] as List<*>).size)
  assertFalse(result.diagnostics.containsKey("centroidVectors"))
 }

 @Test fun shortRecordingIsRejectedSoCallersKeepTheSinglePassPath() = runBlocking {
  try {
   ChunkedDiarizationRunner.run(30_000,30_000*16,config,readPcm={_,_ -> error("no read")},sd=fakeSd,refine={_,_,_ -> error("no refine")})
   fail("short recording must not enter the chunked runner")
  } catch(expected: IllegalStateException) { assertTrue(expected.message!!.contains("longer")) }
 }
}
