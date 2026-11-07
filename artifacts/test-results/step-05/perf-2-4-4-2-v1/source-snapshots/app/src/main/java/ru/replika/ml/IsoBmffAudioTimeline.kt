package ru.replika.ml

import java.io.IOException
import java.math.BigInteger
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileChannel

/** Small, seek-only ISO-BMFF timeline reader. It never reads mdat or decodes media.
 * Android 9 ignores a two-entry elst while newer extractors expose its empty edit in PTS.
 * The selected audio track is matched by tkhd track_ID, not MediaExtractor track index.
 */
object IsoBmffAudioTimeline {
 class UnsupportedTimeline(message: String): IOException(message)
 interface Source {
  val length: Long
  fun readAt(offset: Long,count: Int): ByteArray
 }
 class ChannelSource(private val channel: FileChannel,private val base: Long,override val length: Long): Source {
  init { demand(base>=0 && length>=0 && base<=Long.MAX_VALUE-length,"Invalid source range") }
  override fun readAt(offset: Long,count: Int): ByteArray {
   demand(offset>=0 && count>=0 && offset<=length-count,"Metadata read outside source")
   val buffer=ByteBuffer.allocate(count)
   while(buffer.hasRemaining()) {
    val read=channel.read(buffer,base+offset+buffer.position())
    if(read<=0) throw UnsupportedTimeline("Source metadata cannot be read with bounded seeks")
   }
   return buffer.array()
  }
 }
 data class Edit(val movieDuration: Long,val mediaTime: Long,val rateInteger: Int,val rateFraction: Int)
 data class Track(val id: Long,val handler: String,val mediaTimescale: Long,val mediaDuration: Long?,val edits: List<Edit>,val firstCompositionOffset: Long)
 data class Timing(val leadingEmptyUs: Long,val additionalOffsetUs: Long)
 data class Movie(val movieTimescale: Long,val tracks: List<Track>,val fragmented: Boolean) {
  fun timing(trackId: Long?,firstSampleTimeUs: Long): Timing {
   val audio=tracks.filter { it.handler=="soun" }
   val selected=if(trackId!=null) audio.singleOrNull { it.id==trackId }
    else audio.singleOrNull()
   demand(selected!=null,"Cannot identify the selected MP4 audio track")
   val track=selected!!
   val edits=track.edits
   if(edits.isEmpty()) return Timing(0,0)
   demand(edits.size<=2 && edits.all { it.rateInteger==1 && it.rateFraction==0 },"Non-unit or multiple MP4 audio edits")
   // A single positive media_time is normal AAC priming/gapless metadata. The platform
   // already supplies codec delay/padding; subtracting it here would trim audio twice.
   if(edits.size==1 && edits[0].mediaTime>=0) return Timing(0,0)
   demand(edits.size==2 && edits[0].mediaTime== -1L && edits[1].mediaTime==0L,
    "Only an initial empty edit followed by untrimmed audio is supported")
   if(edits[0].movieDuration==0L) return Timing(0,0)
   demand(!fragmented && track.firstCompositionOffset==0L,
    "Delayed fragmented/composition-offset MP4 audio needs an unsupported timeline mapping")
   demand(movieTimescale>0 && track.mediaTimescale>0,"Missing MP4 timeline timescale")
   if(edits[1].movieDuration>0) {
    val requested=scale(edits[1].movieDuration,movieTimescale,track.mediaTimescale,true)
    val original=track.mediaDuration
    // Movie clocks commonly round AAC ends to milliseconds. Permit one movie tick
    // (plus one media tick), capped at 2 ms; never interpret a real end trim as full media.
    val tolerance=(track.mediaTimescale+movieTimescale-1)/movieTimescale+1
    demand(tolerance<=maxOf(1L,track.mediaTimescale/500),"Movie clock is too coarse to verify the audio edit")
    demand(original!=null && (if(requested>=original) requested-original else original-requested)<=tolerance,
     "A delayed MP4 audio edit also trims or extends the media")
   }
   // Match AOSP: round movie ticks to media ticks, then convert the timestamp to us.
   val mediaTicks=scale(edits[0].movieDuration,movieTimescale,track.mediaTimescale,true)
   val leadingUs=scale(mediaTicks,track.mediaTimescale,1_000_000,false)
   if(leadingUs==0L) return Timing(0,0)
   val alreadyApplied=firstSampleTimeUs>=0 &&
    (if(firstSampleTimeUs>=leadingUs) firstSampleTimeUs-leadingUs else leadingUs-firstSampleTimeUs)<=2L
   val missing=when {
    alreadyApplied -> 0L
    firstSampleTimeUs==0L -> leadingUs
    else -> throw UnsupportedTimeline("Extractor timestamps do not match the MP4 edit list")
   }
   return Timing(leadingUs,missing)
  }
 }

 fun read(source: Source,checkpoint: ()->Unit = {}): Movie? = Parser(source,checkpoint).read()

 private data class Box(val type: String,val body: Long,val end: Long)
 private class Parser(private val source: Source,private val checkpoint: ()->Unit) {
  private var bytesRead=0
  private var boxesRead=0
  private fun bytes(offset: Long,count: Int): ByteArray {
   checkpoint()
   demand(count>=0 && count<=256 && bytesRead<=MAX_METADATA_BYTES-count,"MP4 metadata read budget exceeded")
   demand(offset>=0 && offset<=source.length-count,"Truncated MP4 metadata")
   bytesRead+=count
   return source.readAt(offset,count).also { demand(it.size==count,"Truncated MP4 metadata") }
  }
  private fun u32(offset: Long)=ByteBuffer.wrap(bytes(offset,4)).order(ByteOrder.BIG_ENDIAN).int.toLong() and 0xffffffffL
  private fun i64(offset: Long)=ByteBuffer.wrap(bytes(offset,8)).order(ByteOrder.BIG_ENDIAN).long
  private fun u64(offset: Long)=i64(offset).also { demand(it>=0,"Unsigned MP4 value exceeds supported range") }
  private fun type(offset: Long)=String(bytes(offset,4),Charsets.ISO_8859_1)
  private fun children(begin: Long,end: Long,visit: (Box)->Unit) {
   var position=begin
   while(position<end) {
    checkpoint();demand(++boxesRead<=MAX_BOXES,"Too many MP4 metadata boxes")
    demand(end-position>=8,"Truncated MP4 box header")
    val size=u32(position);val kind=type(position+4)
    val header=if(size==1L) 16L else 8L
    demand(end-position>=header,"Truncated extended MP4 box header")
    val length=when(size) { 0L->end-position;1L->u64(position+8);else->size }
    demand(length>=header && length<=end-position,"Invalid MP4 box bounds")
    val box=Box(kind,position+header,position+length)
    visit(box);position=box.end
   }
  }
  private fun within(box: Box,offset: Long,count: Long) {
   demand(offset>=box.body && count>=0 && offset<=box.end-count,"Truncated ${box.type} metadata")
  }
  private fun version(box: Box): Int {
   within(box,box.body,4);return bytes(box.body,1)[0].toInt() and 255
  }
  private fun timescale(box: Box): Long {
   val offset=when(version(box)) { 0->12L;1->20L;else->throw UnsupportedTimeline("Unsupported ${box.type} version") }
   within(box,box.body+offset,4)
   return u32(box.body+offset).also { demand(it>0,"Zero MP4 timescale") }
  }
  private fun trackId(box: Box): Long {
   val offset=when(version(box)) { 0->12L;1->20L;else->throw UnsupportedTimeline("Unsupported tkhd version") }
   within(box,box.body+offset,4)
   return u32(box.body+offset).also { demand(it>0,"Zero MP4 track ID") }
  }
  private fun duration(box: Box): Long? {
   val version=version(box)
   val offset=when(version) { 0->16L;1->24L;else->throw UnsupportedTimeline("Unsupported ${box.type} version") }
   within(box,box.body+offset,if(version==0) 4 else 8)
   val value=if(version==0) u32(box.body+offset).let { if(it==0xffffffffL) -1L else it } else i64(box.body+offset)
   demand(value>=0 || value== -1L,"Unsigned MP4 duration exceeds supported range")
   return value.takeIf { it>0 }
  }
  private fun edits(box: Box): List<Edit> {
   val version=version(box);demand(version==0 || version==1,"Unsupported elst version")
   within(box,box.body+4,4);val count=u32(box.body+4)
   demand(count<=MAX_EDITS,"Too many MP4 edits")
   val stride=if(version==0) 12L else 20L
   within(box,box.body+8,count*stride)
   return List(count.toInt()) { index ->
    val start=box.body+8+index*stride
    val duration=if(version==0) u32(start) else u64(start)
    val media=if(version==0) u32(start+4).toInt().toLong() else i64(start+8)
    val rate=ByteBuffer.wrap(bytes(start+stride-4,4)).order(ByteOrder.BIG_ENDIAN)
    Edit(duration,media,rate.short.toInt(),rate.short.toInt())
   }
  }
  private fun firstCompositionOffset(box: Box): Long {
   val version=version(box);demand(version==0 || version==1,"Unsupported ctts version")
   within(box,box.body+4,4);val count=u32(box.body+4)
   within(box,box.body+8,count*8)
   if(count==0L) return 0
   demand(u32(box.body+8)>0,"Empty first MP4 composition run")
   val offset=u32(box.body+12)
   return if(version==0) offset else offset.toInt().toLong()
  }
  private fun track(box: Box): Track {
   var id: Long?=null;var handler="";var scale=0L;var mediaDuration: Long?=null;var editList: List<Edit>?=null;var composition=0L
   children(box.body,box.end) { child -> when(child.type) {
    "tkhd" -> { demand(id==null,"Duplicate MP4 track header");id=trackId(child) }
    "edts" -> children(child.body,child.end) { edit -> if(edit.type=="elst") {
     demand(editList==null,"Duplicate MP4 edit list");editList=edits(edit)
    } }
    "mdia" -> children(child.body,child.end) { media -> when(media.type) {
     "mdhd" -> { demand(scale==0L,"Duplicate media header");scale=timescale(media);mediaDuration=duration(media) }
     "hdlr" -> { within(media,media.body+8,4);handler=type(media.body+8) }
     "minf" -> children(media.body,media.end) { info -> if(info.type=="stbl") children(info.body,info.end) { sample ->
      if(sample.type=="ctts") composition=firstCompositionOffset(sample)
     } }
    } }
   } }
   demand(id!=null,"Missing MP4 track header")
   return Track(id!!,handler,scale,mediaDuration,editList.orEmpty(),composition)
  }
  fun read(): Movie? {
   if(source.length<8) return null
   // MP4/MOV may start with free/mdat before a tail moov. Non-ISO formats retain the
   // existing system-extractor path (e.g. WebM/Opus); extension/MIME are not guessed.
   val firstType=type(4)
   if(firstType !in setOf("ftyp","moov","mdat","free","skip","wide","pdin","sidx","uuid","styp","pnot")) {
    if(type(0) in setOf("RIFF","RIFX","OggS","fLaC")) return null
    val firstSize=u32(0)
    val plausibleBox=firstType.all { it.code in 32..126 } &&
     (firstSize==0L || firstSize==1L && source.length>=16 || firstSize in 8..source.length)
    if(!plausibleBox) return null
    // ISO permits unknown top-level boxes. Do not silently lose an edit just because
    // such a box precedes ftyp/moov; walk only its checked header, never its payload.
   }
   var movie: Movie?=null
   children(0,source.length) { box -> if(box.type=="moov") {
    demand(movie==null,"Multiple MP4 movie headers")
    var scale=0L;var fragmented=false;val tracks=mutableListOf<Track>()
    children(box.body,box.end) { child -> when(child.type) {
     "mvhd" -> { demand(scale==0L,"Duplicate movie header");scale=timescale(child) }
     "mvex" -> fragmented=true
     "trak" -> { demand(tracks.size<MAX_TRACKS,"Too many MP4 tracks");tracks+=track(child) }
    } }
    demand(scale>0 && tracks.map { it.id }.distinct().size==tracks.size,"Missing movie clock or duplicate track IDs")
    movie=Movie(scale,tracks,fragmented)
   } }
   return movie?:throw UnsupportedTimeline("MP4 movie metadata is unavailable")
  }
 }
 private fun scale(ticks: Long,from: Long,to: Long,round: Boolean): Long {
  demand(ticks>=0 && from>0 && to>0,"Invalid MP4 clock conversion")
  var value=BigInteger.valueOf(ticks).multiply(BigInteger.valueOf(to))
  if(round) value=value.add(BigInteger.valueOf(from/2))
  value=value.divide(BigInteger.valueOf(from))
  demand(value.bitLength()<=63,"MP4 timeline exceeds supported range")
  return value.toLong()
 }
 private fun demand(condition: Boolean,message: String) { if(!condition) throw UnsupportedTimeline(message) }
 private const val MAX_METADATA_BYTES=256*1024
 private const val MAX_BOXES=4096
 private const val MAX_TRACKS=64
 private const val MAX_EDITS=16L
}
