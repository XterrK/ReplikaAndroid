package ru.replika.domain

import kotlin.math.roundToLong

/** Experimental token-emission estimates, not forced alignment or calibrated word timestamps. */
object VadWordPlanner {
 const val SAME_FRAME="Слова в одном кадре модели: проверьте границу"
 const val NO_SPEAKER="Не найден говорящий слова"
 const val TIED_SPEAKER="Неоднозначный говорящий слова"
 const val SPEAKER_BOUNDARY="Смена говорящего на границе слова"
 const val OVERLAP="Пересечение голосов в слове"
 const val SEAM_EDIT="Пунктуация на границе реплики: проверьте текст"

 data class Word(val startMs: Long,val endMs: Long,val text: String,val reasons: List<String> = emptyList())
 data class WordResult(val supported: Boolean,val reason: String,val words: List<Word>)
 data class AssignedWord(val startMs: Long,val endMs: Long,val text: String,val speaker: Int,val reasons: List<String>)

 /** Plan complete disjoint coverage of bounded VAD spans. Energy receives global milliseconds.
  * The caller computes sequential Double mean-square from the original Float32 PCM. */
 fun planChunks(speech: List<Span>,energy: (Long,Long)->Double,maxMs: Long=20000,
  energySplit: Boolean=true,searchMs: Long=4000,windowMs: Long=40): List<Span> {
  require(maxMs>0 && searchMs>0 && windowMs>0)
  val chunks=mutableListOf<Span>()
  for(span in Alignment.merge(speech)) {
   require(span.startMs>=0)
   var start=span.startMs
   while(start<span.endMs) {
    val remaining=span.endMs-start
    val limit=start+minOf(maxMs,remaining)
    var end=limit
    if(energySplit && remaining>maxMs) {
     var candidate=maxOf(start,limit-searchMs)
     val last=limit-windowMs
     var bestEnergy=Double.POSITIVE_INFINITY
     while(candidate<=last) {
      val value=energy(candidate,candidate+windowMs)
      require(value.isFinite() && value>=0) { "Некорректная энергия аудио" }
      if(value<bestEnergy) { bestEnergy=value;end=candidate+windowMs/2 }
      if(last-candidate<windowMs) break
      candidate+=windowMs
     }
    }
    check(end>start && end<=limit)
    chunks+=Span(start,end)
    start=end
   }
  }
  return chunks
 }

 private fun separator(char: Char): Boolean = char.isWhitespace() || char=='\u0085'
 private fun runs(text: String): List<IntRange> {
  val result=mutableListOf<IntRange>()
  var start=0
  while(start<text.length) {
   if(separator(text[start])) { start++;continue }
   var end=start+1
   while(end<text.length && !separator(text[end])) end++
   result+=start until end;start=end
  }
  return result
 }
 private fun normalizedWhitespace(text: String): String = runs(text).joinToString(" ") { text.substring(it) }
 private fun lexical(text: String): Boolean = text.codePoints().anyMatch {
  Character.isLetterOrDigit(it) || Character.getType(it)==Character.LETTER_NUMBER.toInt() || Character.getType(it)==Character.OTHER_NUMBER.toInt()
 }

 /** Tokens and Float seconds come from the recognizer. Missing/invalid alignment is explicit.
  * Float multiplication is deliberate: it matches the Float32 clock exposed by sherpa JNI. */
 fun words(text: String,tokens: List<String?>,timestampsSeconds: FloatArray,chunk: Span,
  frameStrideMs: Long=40): WordResult {
  fun unsupported(reason: String)=WordResult(false,reason,emptyList())
  if(chunk.startMs<0 || chunk.endMs<=chunk.startMs) return unsupported("invalid_chunk")
  if(normalizedWhitespace(text).isEmpty()) return WordResult(true,"empty_result",emptyList())
  if(frameStrideMs<=0) return unsupported("unverified_frame_stride")
  if(tokens.size!=timestampsSeconds.size || tokens.isEmpty()) return unsupported("token_count_mismatch")
  if(tokens.any { it==null }) return unsupported("invalid_token")
  val duration=chunk.endMs-chunk.startMs
  val times=LongArray(timestampsSeconds.size)
  var previous=Float.NEGATIVE_INFINITY
  for(i in timestampsSeconds.indices) {
   val seconds=timestampsSeconds[i]
   if(!seconds.isFinite()) return unsupported("nonfinite_timestamp")
   if(seconds<previous) return unsupported("nonmonotonic_timestamps")
   val scaled=seconds*1000f
   if(!scaled.isFinite()) return unsupported("nonfinite_timestamp")
   val milliseconds=scaled.roundToLong()
   if(seconds<0 || milliseconds<0 || milliseconds>duration) return unsupported("timestamp_out_of_range")
   if(milliseconds%frameStrideMs!=0L) return unsupported("timestamp_off_grid")
   times[i]=milliseconds;previous=seconds
  }
  val pieces=tokens.map { it!!.replace('▁',' ') }
  if(pieces.any { piece -> runs(piece).count { lexical(piece.substring(it)) }>1 }) return unsupported("multiword_token")
  val stream=pieces.joinToString("")
  if(normalizedWhitespace(stream)!=normalizedWhitespace(text)) return unsupported("text_roundtrip_mismatch")
  val origins=IntArray(stream.length)
  val tokenStarts=IntArray(tokens.size)
  val tokenEnds=IntArray(tokens.size)
  var offset=0
  for((index,piece) in pieces.withIndex()) {
   tokenStarts[index]=offset;repeat(piece.length) { origins[offset++]=index };tokenEnds[index]=offset
  }
  data class PendingWord(var text: String,val first: Long,var last: Long)
  val parsed=mutableListOf<PendingWord>()
  val prefix=mutableListOf<String>()
  for(run in runs(stream)) {
   val content=stream.substring(run)
   if(!lexical(content)) {
    if(parsed.isEmpty()) prefix+=content else parsed.last().text+=" "+content
    continue
   }
   val lexicalTokens=run.map { origins[it] }.distinct().filter {
    lexical(stream.substring(maxOf(run.first,tokenStarts[it]),minOf(run.last+1,tokenEnds[it])))
   }
   if(lexicalTokens.isEmpty()) return unsupported("no_lexical_words")
   parsed+=PendingWord((prefix+content).joinToString(" "),times[lexicalTokens.first()],times[lexicalTokens.last()])
   prefix.clear()
  }
  if(parsed.isEmpty()) return unsupported("no_lexical_words")
  if(normalizedWhitespace(parsed.joinToString(" ") { it.text })!=normalizedWhitespace(text))
   return unsupported("text_roundtrip_mismatch")
  val result=mutableListOf<Word>()
  for((index,word) in parsed.withIndex()) {
   var end=word.last+minOf(frameStrideMs,duration-word.last)
   val next=parsed.getOrNull(index+1)
   if(next!=null && next.first>word.first) end=minOf(end,next.first)
   if(end<=word.first) return unsupported("word_outside_chunk")
   val shared=next?.first==word.first || parsed.getOrNull(index-1)?.first==word.first
   result+=Word(chunk.startMs+word.first,chunk.startMs+end,word.text,if(shared) listOf(SAME_FRAME) else emptyList())
  }
  return WordResult(true,"supported",result)
 }

 /** Maximal union-overlap per known native speaker; unknown/tied evidence stays unknown. */
 fun assignWords(words: List<Word>,turns: List<Turn>): List<AssignedWord> {
  require(words.all { it.startMs>=0 && it.endMs>it.startMs && it.text.isNotBlank() })
  require(words.zipWithNext().all { (a,b)->a.startMs<=b.startMs })
  require(turns.all { it.startMs>=0 && it.endMs>=it.startMs })
  return words.map { word ->
   val spans=turns.filter { it.speaker>=0 && it.startMs<word.endMs && it.endMs>word.startMs }
    .groupBy { it.speaker }.mapValues { (_,speakerTurns)->Alignment.merge(speakerTurns.map {
     Span(maxOf(word.startMs,it.startMs),minOf(word.endMs,it.endMs))
    }) }
   val lengths=spans.mapValues { (_,parts)->parts.sumOf { it.endMs-it.startMs } }
   val maximum=lengths.values.maxOrNull()?:0
   val winners=lengths.filterValues { it==maximum && it>0 }.keys
   val speaker=winners.singleOrNull()?:-1
   val different=spans.values.toList()
   val overlap=different.indices.any { i -> (i+1 until different.size).any { j ->
    different[i].any { a -> different[j].any { b -> maxOf(a.startMs,b.startMs)<minOf(a.endMs,b.endMs) } }
   } }
   val reasons=word.reasons+buildList {
    if(winners.isEmpty()) add(NO_SPEAKER) else if(winners.size>1) add(TIED_SPEAKER)
    if(lengths.size>1) add(if(overlap) OVERLAP else SPEAKER_BOUNDARY)
   }
   AssignedWord(word.startMs,word.endMs,word.text,speaker,reasons.distinct())
  }
 }

 /** Invoke separately for every ASR chunk; this function never merges across that boundary. */
 fun groupWords(words: List<AssignedWord>,source: String,seamPunctuation: Boolean=false): List<Segment> {
  require(words.all { it.startMs>=0 && it.endMs>it.startMs && it.text.isNotBlank() })
  require(words.zipWithNext().all { (a,b)->a.startMs<=b.startMs })
  val result=mutableListOf<Segment>()
  for(word in words) {
   val previous=result.lastOrNull()
   if(previous!=null && previous.speakerId==word.speaker) {
    result[result.lastIndex]=previous.copy(endMs=maxOf(previous.endMs,word.endMs),text=previous.text+" "+word.text,
     reasons=(previous.reasons+word.reasons).distinct())
   } else result+=Segment(startMs=word.startMs,endMs=word.endMs,speakerId=word.speaker,text=word.text,source=source,reasons=word.reasons)
  }
  return if(!seamPunctuation || result.size<2) result else result.map { segment ->
   val edited=seamText(segment.text)
   if(edited==segment.text) segment else segment.copy(text=edited,reasons=(segment.reasons+SEAM_EDIT).distinct())
  }
 }

 fun seamText(text: String): String {
  var result=text
  val first=result.indexOfFirst(Char::isLetter)
  if(first>=0) result=result.substring(0,first)+result[first].uppercaseChar()+result.substring(first+1)
  if(result.isEmpty()) return result
  var effective=result.lastIndex
  while(effective>=0 && (result[effective] in "\"'»”’)]}" || separator(result[effective]))) effective--
  if(effective<0) return result
  val last=result[effective]
  if(last in ".!?…:;") return result
  return if(last in ",-—–") result.substring(0,effective)+"."+result.substring(effective+1) else result+"."
 }
}
