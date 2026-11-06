package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.ml.IsoBmffAudioTimeline
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.File
import java.io.FileInputStream
import java.util.concurrent.CancellationException

class IsoBmffAudioTimelineTest {
 private data class Entry(val duration: Long,val media: Long,val rate: Int=1,val fraction: Int=0)
 private fun data(write: DataOutputStream.()->Unit)=ByteArrayOutputStream().also { stream -> DataOutputStream(stream).use { it.write() } }.toByteArray()
 private fun box(name: String,payload: ByteArray,extended: Boolean=false)=data {
  writeInt(if(extended) 1 else payload.size+8);writeBytes(name)
  if(extended) writeLong(payload.size+16L)
  write(payload)
 }
 private fun clock(name: String,scale: Int,version: Int=0,duration: Long=48000)=box(name,data {
  writeInt(version shl 24)
  if(version==0) { writeInt(0);writeInt(0) } else { writeLong(0);writeLong(0) }
  writeInt(scale);if(version==0) writeInt(duration.toInt()) else writeLong(duration)
 })
 private fun track(id: Int,entries: List<Entry>,version: Int=0,compositionOffset: Int?=null,
                   mediaDuration: Long=if(version==0) 48000 else 1000000)=box("trak",
  box("tkhd",data {
   writeInt(version shl 24)
   if(version==0) { writeInt(0);writeInt(0) } else { writeLong(0);writeLong(0) }
   writeInt(id);writeInt(0);if(version==0) writeInt(1000) else writeLong(1000)
  })+box("edts",box("elst",data {
   writeInt(version shl 24);writeInt(entries.size)
   for(e in entries) {
    if(version==0) { writeInt(e.duration.toInt());writeInt(e.media.toInt()) } else { writeLong(e.duration);writeLong(e.media) }
    writeShort(e.rate);writeShort(e.fraction)
   }
  }))+box("mdia",clock("mdhd",if(version==0) 48000 else 1000000,version,mediaDuration)+
   box("hdlr",data { writeInt(0);writeInt(0);writeBytes("soun") })+
   box("minf",box("stbl",if(compositionOffset==null) byteArrayOf() else box("ctts",data {
    writeInt(0);writeInt(1);writeInt(1);writeInt(compositionOffset)
   }))))
 )
 private fun movie(vararg tracks: ByteArray,scale: Int=1000,version: Int=0,fragmented: Boolean=false)=
  box("ftyp","isom\u0000\u0000\u0000\u0000isom".toByteArray())+
   box("moov",clock("mvhd",scale,version,1400)+tracks.fold(byteArrayOf()) { a,b->a+b }+
    if(fragmented) box("mvex",byteArrayOf()) else byteArrayOf(),extended=version==1)
 private fun source(bytes: ByteArray)=object: IsoBmffAudioTimeline.Source {
  override val length=bytes.size.toLong()
  override fun readAt(offset: Long,count: Int)=bytes.copyOfRange(offset.toInt(),offset.toInt()+count)
 }
 private fun parse(bytes: ByteArray)=IsoBmffAudioTimeline.read(source(bytes))!!
 private fun unsupported(action: ()->Unit) {
  try { action();fail("Expected unsupported timeline") }
  catch(expected: IsoBmffAudioTimeline.UnsupportedTimeline) { assertTrue(expected.message!!.isNotBlank()) }
 }

 @Test fun repairsOnlyMissingEmptyEditAndNeverAddsItTwice() {
  val metadata=parse(movie(track(42,listOf(Entry(400,-1),Entry(1000,0)))))
  assertEquals(400000L,metadata.timing(42,0).additionalOffsetUs)
  assertEquals(0L,metadata.timing(42,400000).additionalOffsetUs)
  assertEquals(0L,metadata.timing(42,399999).additionalOffsetUs)
  unsupported { metadata.timing(42,200000) }
 }

 @Test fun movieClockAndMediaClockRemainDistinctWithVersion1AndExtendedBoxes() {
  val delay=8589934592L // Deliberately exceeds unsigned32; movie/media clocks are microseconds.
  val metadata=parse(movie(track(7,listOf(Entry(delay,-1),Entry(1000000,0)),version=1),scale=1000000,version=1))
  assertEquals(delay,metadata.timing(7,0).leadingEmptyUs)
  assertEquals(delay,metadata.timing(7,0).additionalOffsetUs)
 }

 @Test fun ordinaryAacPrimingIsLeftToCodecAndLongerVideoNeverBecomesLeadingSilence() {
  val primed=parse(movie(track(2,listOf(Entry(1000,1024)))))
  assertEquals(0L,primed.timing(2,0).additionalOffsetUs)
  assertEquals(0L,primed.timing(2,-21333).additionalOffsetUs)
  val trailingVideo=parse(movie(track(2,listOf(Entry(1000,0))))) // mvhd1400ms, audio1000ms
  assertEquals(0L,trailingVideo.timing(2,0).leadingEmptyUs)
 }

 @Test fun millisecondMovieClockRoundingIsNotMistakenForAnAudioTrim() {
  val metadata=parse(movie(track(2,listOf(Entry(378,-1),Entry(1021,0)),mediaDuration=49024)))
  assertEquals(378000L,metadata.timing(2,0).additionalOffsetUs)
 }

 @Test fun ignoresAnUnknownBoundedTopLevelBoxBeforeTheMovie() {
  val bytes=box("Xabc",ByteArray(32))+movie(track(2,listOf(Entry(400,-1),Entry(1000,0))))
  assertEquals(400000L,parse(bytes).timing(2,0).additionalOffsetUs)
 }

 @Test fun trackIdMatchingDoesNotConfuseExtractorIndexOrOtherAudioTracks() {
  val metadata=parse(movie(track(22,listOf(Entry(1000,0))),track(99,listOf(Entry(250,-1),Entry(1000,0)))))
  assertEquals(250000L,metadata.timing(99,0).additionalOffsetUs)
  assertEquals(0L,metadata.timing(22,0).additionalOffsetUs)
  unsupported { metadata.timing(1,0) }
  unsupported { metadata.timing(null,0) }
  assertEquals(400000L,parse(movie(track(7,listOf(Entry(400,-1),Entry(1000,0))))).timing(null,0).additionalOffsetUs)
 }

 @Test fun complexEditsFailInsteadOfInventingAnOffset() {
  for(entries in listOf(
   listOf(Entry(400,-1),Entry(1000,1024)),
   listOf(Entry(400,-1),Entry(500,0)),
   listOf(Entry(400,-1),Entry(500,0),Entry(500,24000)),
   listOf(Entry(1000,0,rate=0)),
   listOf(Entry(1000,0,fraction=1)),
   listOf(Entry(1000,-2))
  )) unsupported { parse(movie(track(2,entries))).timing(2,0) }
  unsupported { parse(movie(track(2,listOf(Entry(400,-1),Entry(1000,0))),fragmented=true)).timing(2,0) }
  unsupported { parse(movie(track(2,listOf(Entry(400,-1),Entry(1000,0)),compositionOffset=1024))).timing(2,0) }
  unsupported { parse(movie(track(2,listOf(Entry(1,-1),Entry(1,0)),mediaDuration=95952),scale=1)).timing(2,0) }
 }

 @Test fun seeksAcrossMultiGigabyteMdatWithoutReadingItsPayload() {
  val ftyp=box("ftyp","isom\u0000\u0000\u0000\u0000isom".toByteArray())
  val length=(1L shl 32)+4096
  val header=data { writeInt(1);writeBytes("mdat");writeLong(length) }
  val full=movie(track(2,listOf(Entry(400,-1),Entry(1000,0))))
  val moov=full.copyOfRange(ftyp.size,full.size)
  val movieOffset=ftyp.size+length;var readBytes=0
  val virtual=object: IsoBmffAudioTimeline.Source {
   override val length=movieOffset+moov.size
   override fun readAt(offset: Long,count: Int): ByteArray {
    readBytes+=count;assertTrue(count<=256)
    val piece=when {
     offset<ftyp.size -> 0L to ftyp
     offset<ftyp.size+header.size -> ftyp.size.toLong() to header
     offset>=movieOffset -> movieOffset to moov
     else -> throw AssertionError("mdat payload was read")
    }
    val start=(offset-piece.first).toInt();return piece.second.copyOfRange(start,start+count)
   }
  }
  assertEquals(400000L,IsoBmffAudioTimeline.read(virtual)!!.timing(2,0).additionalOffsetUs)
  assertTrue("Only small metadata fields should be read",readBytes<4096)
 }

 @Test fun rejectsTruncationOverflowAndExcessiveMetadataWithoutAllocatingPayloads() {
  unsupported { parse(data { writeInt(4);writeBytes("moov") }) }
  unsupported { parse(data { writeInt(1);writeBytes("moov");writeLong(-1) }) }
  unsupported { parse(movie(track(2,listOf(Entry(400,-1),Entry(1000,0)))).copyOfRange(0,40)) }
  val tooMany=box("ftyp","isom0000".toByteArray())+(0..4096).fold(byteArrayOf()) { a,_->a+box("free",byteArrayOf()) }
  unsupported { parse(tooMany) }
 }

 @Test fun parserCanBeCancelledAndNonIsoKeepsExistingExtractorPath() {
  var checkpoints=0
  try {
   IsoBmffAudioTimeline.read(source(movie(track(2,listOf(Entry(400,-1),Entry(1000,0)))))) {
    if(++checkpoints==4) throw CancellationException("metadata cancellation")
   }
   fail("Expected cancellation")
  } catch(expected: CancellationException) { assertEquals("metadata cancellation",expected.message) }
  assertNull(IsoBmffAudioTimeline.read(source(byteArrayOf(0x1a,0x45,0xdf.toByte(),0xa3.toByte(),1,2,3,4))))
 }

 @Test fun parsesRealDelayedFixtureAndAProviderSubrangeWithoutReadingWholeVideo() {
  val relative="src/androidTest/assets/media-import/aac-offset.mp4"
  val file=listOf(File(relative),File("app/$relative")).first { it.isFile }
  FileInputStream(file).use { stream ->
   val metadata=IsoBmffAudioTimeline.read(IsoBmffAudioTimeline.ChannelSource(stream.channel,0,file.length()))!!
   assertEquals(48000L,metadata.movieTimescale)
   assertEquals(378666L,metadata.timing(2,0).additionalOffsetUs)
   assertEquals(0L,metadata.timing(2,378666).additionalOffsetUs)
  }
  val priming=File(file.parentFile,"aac-priming.mp4")
  FileInputStream(priming).use { stream ->
   val metadata=IsoBmffAudioTimeline.read(IsoBmffAudioTimeline.ChannelSource(stream.channel,0,priming.length()))!!
   assertEquals(1024L,metadata.tracks.single { it.handler=="soun" }.edits.single().mediaTime)
   assertEquals(0L,metadata.timing(2,0).additionalOffsetUs)
  }
  val subrange=File.createTempFile("iso-timeline-subrange",".bin")
  try {
   subrange.writeBytes(ByteArray(123)+file.readBytes()+ByteArray(57))
   FileInputStream(subrange).use { stream ->
    assertEquals(378666L,IsoBmffAudioTimeline.read(IsoBmffAudioTimeline.ChannelSource(stream.channel,123,file.length()))!!.timing(2,0).additionalOffsetUs)
   }
  } finally { subrange.delete() }
 }
}
