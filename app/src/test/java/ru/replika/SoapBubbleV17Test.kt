package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.ui.*
import kotlin.math.*

/** V1.7c soap bubble: soft directional shell, shader boundary and voice particles. Display-only logic. */
class SoapBubbleV17Test {
 private fun deepestAngle(d: OrbDynamics): Float {
  var best=0f;var lowest=Float.MAX_VALUE
  for(i in 0 until 720) { val a=i*(2f*PI.toFloat()/720);val u=d.shellAt(a);if(u<lowest) { lowest=u;best=a } }
  return best
 }
 private fun angleError(a: Float,b: Float)=abs(atan2(sin(a-b),cos(a-b)))
 private fun radii(g: OrbContourGeometry)=(0 until g.count).map { sqrt(g.x[it]*g.x[it]+g.y[it]*g.y[it]) }

 @Test fun aTapDentsTheFilmThereBulgesTheSidesAndSendsTwoWavesBothWays() {
  val d=OrbDynamics()
  val bottom=(PI/2).toFloat()
  d.impact(bottom,1f)
  var peak=0f
  repeat(20) { d.step(1f/60,0f,false);peak=max(peak,-d.shellAt(bottom)) }
  assertTrue("An ordinary tap dents 8–15 % of the radius, got ${peak*100}%",peak in .08f.. .15f)
  assertEquals(1,d.impacts)
  // Zero-mean shell: the dent pushes the neighbouring film out.
  val fresh=OrbDynamics();fresh.impact(bottom,1f);repeat(4) { fresh.step(1f/60,0f,false) }
  assertTrue("Sides bulge out",(0 until 360).any { fresh.shellAt(it*PI.toFloat()/180)>.02f })
  // Two waves: the shape stays mirror-symmetric about the tap while the dent splits and runs away.
  var travelled=false
  repeat(30) {
   fresh.step(1f/60,0f,false)
   for(k in 1..8) assertEquals(fresh.shellAt(bottom+k*.2f),fresh.shellAt(bottom-k*.2f),1e-4f)
   if(angleError(deepestAngle(fresh),bottom)>.6f) travelled=true
  }
  assertTrue("The dent must leave the tap point as travelling waves",travelled)
  // Lively for ~0.6–1.2 s, then gone.
  val alive=OrbDynamics();alive.impact(bottom,1f)
  repeat(36) { alive.step(1f/60,0f,false) }
  assertTrue("Still visibly wobbling at 0.6 s",(0 until 90).maxOf { abs(alive.shellAt(it*.07f)) }>.01f)
  repeat(84) { alive.step(1f/60,0f,false) }
  repeat(60) { alive.step(1f/60,0f,false) }
  assertTrue("Almost settled at 2 s",(0 until 90).maxOf { abs(alive.shellAt(it*.07f)) }<.01f)
  repeat(240) { alive.step(1f/60,0f,false) }
  assertFalse("Jelly oscillation must decay",alive.shellMotion)
  assertFalse(alive.hasInteractionMotion)
 }

 /** Requested 07.11 night: every click, from any side, dents the film in that direction (±15°). */
 @Test fun aTapFromAnySideDentsTheFilmExactlyOnThatSide() {
  for(k in 0 until 24) {
   val angle=-PI.toFloat()+k*(2f*PI.toFloat()/24)
   for(reach in listOf(.35f,.7f,1f)) {
    val d=OrbDynamics();val g=OrbContourGeometry()
    d.poke(cos(angle)*reach,sin(angle)*reach)
    repeat(3) { d.step(1f/60,0f,true) }
    assertTrue("Tap at ${Math.toDegrees(angle.toDouble()).roundToInt()}°: deepest point ${Math.toDegrees(deepestAngle(d).toDouble()).roundToInt()}°",
     angleError(deepestAngle(d),angle)<=Math.toRadians(15.0).toFloat())
    // The drawn contour (after area normalization) is innermost on the same side.
    g.update(d);val r=radii(g);val i=r.indices.minBy { r[it] }
    assertTrue("Contour is innermost at the tap",angleError(i*(2f*PI.toFloat()/g.count),angle)<=Math.toRadians(15.0).toFloat())
   }
  }
 }

 @Test fun severalTapsAtOnceGiveSeveralDentsAndARapidSeriesHitsHarderButStaysCapped() {
  val d=OrbDynamics()
  d.impact(0f,1f);d.impact(PI.toFloat()*2f/3f,1f);d.impact(-PI.toFloat()*2f/3f,1f)
  repeat(3) { d.step(1f/60,0f,false) }
  for(a in listOf(0f,PI.toFloat()*2f/3f,-PI.toFloat()*2f/3f)) assertTrue("A dent at $a",d.shellAt(a)< -.04f)
  val single=OrbDynamics();single.impact(0f,1f)
  val series=OrbDynamics()
  var one=0f;var many=0f
  repeat(30) { i -> if(i%5==0) series.impact(0f,1f);single.step(1f/60,0f,false);series.step(1f/60,0f,false);one=max(one,-single.shellAt(0f));many=max(many,-series.shellAt(0f)) }
  assertTrue("A quick series dents deeper ($many vs $one)",many>one*1.2f)
  val hammer=OrbDynamics()
  repeat(200) { i -> hammer.impact(i*.37f,2f);hammer.step(1f/120,1f,true)
   for(p in 0 until 360) assertTrue(abs(hammer.shellAt(p*.01745f))<=OrbDynamics.SHELL_LIMIT+.01f) }
 }

 @Test fun theShellStaysBoundedUnderHammeringAndDroppedFrames() {
  val d=OrbDynamics()
  repeat(300) { i ->
   d.impact(i*.37f,1.6f)
   if(i%7==0) d.poke(cos(i.toFloat()),sin(i.toFloat()))
   d.step(if(i%11==0) .9f else 1f/60,1f,true)
   assertTrue(d.shapeA.all { it.isFinite() } && d.shapeB.all { it.isFinite() })
   for(a in 0..24) { val r=d.radiusAt(a*.26f);assertTrue("radius $r",r.isFinite() && r>.4f) }
  }
  assertEquals("Touch never stretches the bubble into an ellipse",0f,d.stretch,0f)
 }

 /** User report 07.11: after many taps the bubble stayed oval. Any tap/hit sequence must settle to a circle. */
 @Test fun twentyToThirtyRapidRandomTapsAndHitsAlwaysSettleBackToACircle() {
  val random=java.util.Random(17)
  for(run in 0 until 12) {
   val d=OrbDynamics();val g=OrbContourGeometry()
   val taps=20+random.nextInt(11)
   repeat(taps) {
    val x=random.nextFloat()*2f-1f;val y=random.nextFloat()*2f-1f
    when(random.nextInt(3)) {
     0 -> d.poke(x,y)
     1 -> { d.press(x,y);repeat(1+random.nextInt(4)) { d.step(1f/60,0f,true) };d.release() }
     else -> d.impact(random.nextFloat()*6.28f,random.nextFloat()*1.6f)
    }
    repeat(random.nextInt(5)) { d.step(1f/60,random.nextFloat(),true) }
   }
   repeat(8*60) { d.step(1f/60,0f,false) }
   g.update(d)
   val r=radii(g);val mean=r.average().toFloat()
   val worst=r.maxOf { abs(it-mean)/mean }
   assertTrue("Run $run ($taps taps): radius deviation ${worst*100}% must be < 1%",worst<.01f)
   assertEquals(0f,d.stretch,0f)
   assertFalse(d.hasInteractionMotion)
  }
 }

 @Test fun theOvalModeCannotBePumpedIntoAPermanentShape() {
  val d=OrbDynamics();val g=OrbContourGeometry()
  // Opposite taps drive mode 2 (the oval) as hard as possible, in rhythm with its own frequency.
  repeat(60) { i -> d.impact(if(i%2==0) 0f else PI.toFloat(),2f);d.impact(if(i%2==0) PI.toFloat() else 0f,2f);repeat(4) { d.step(1f/60,0f,false) } }
  repeat(6*60) { d.step(1f/60,0f,false) }
  assertEquals("Mode 2 decays to zero",0f,abs(d.shapeA[0])+abs(d.shapeB[0]),.002f)
  g.update(d);val r=radii(g)
  assertTrue(r.max()/r.min()<1.01f)
 }

 @Test fun reducedMotionDropsTheShellWobble() {
  val d=OrbDynamics();d.impact(0f,1f)
  d.step(1f/60,.5f,true,reduced=true)
  assertTrue(d.shapeA.all { it==0f } && d.shapeB.all { it==0f })
  assertFalse(d.shellMotion)
 }
 @Test fun shaderHarmonicsReconstructTheDentedContour() {
  val d=OrbDynamics();val g=OrbContourGeometry()
  d.impact(.7f,1f);d.impact(2.9f,.6f);d.press(.4f,-.6f)
  repeat(12) { d.step(1f/60,.6f,true) }
  g.update(d)
  var worst=0f
  for(i in 0 until g.count) {
   val angle=i*(2*PI/g.count).toFloat()
   val exact=sqrt(g.x[i]*g.x[i]+g.y[i]*g.y[i])
   worst=max(worst,abs(exact-g.harmonicRadius(angle)))
  }
  assertTrue("8 harmonics must follow the contour the path draws, error $worst",worst<.03f)
 }
 private fun particles(levels: (Int)->Float,active: Boolean,frames: Int,p: VoiceParticleSystem=VoiceParticleSystem(),hits: MutableList<Pair<Float,Float>>?=null): VoiceParticleSystem {
  repeat(frames) { f -> p.step(1f/60,levels(f),active,1080f,2000f,2.75f,540f,800f,{ 150f }) { a,s -> hits?.add(a to s) } }
  return p
 }

 /** V1.7d: comets exist only during recording and only when the voice gate is open. */
 @Test fun particlesNeedRecordingAndAVoiceAboveTheNoiseGate() {
  assertEquals("Silence fabricates nothing",0,particles({ 0f },true,180).spawned)
  assertEquals("Room noise below the gate launches nothing",0,particles({ .12f+.02f*sin(it*.3f) },true,600).spawned)
  assertEquals("Hovering between close and open never opens the gate",0,particles({ .19f },true,600).spawned)
  assertEquals("Not recording (idle, pause, touches): nothing, however loud",0,particles({ .9f },false,600).spawned)
  // One MediaRecorder sample lasts 50 ms (three frames): a click of that length is not a voice.
  assertEquals("A single loud click is smoothed away",0,particles({ if(it in 10..12) 1f else 0f },true,180).spawned)
  val quiet=particles({ .32f },true,240).spawned;val loud=particles({ .9f },true,240).spawned
  assertTrue("A voice opens the stream: $quiet",quiet>=3)
  assertTrue("Louder voice, more comets: $quiet vs $loud",loud>quiet*2)
  val p=VoiceParticleSystem()
  assertTrue(p.speed(1f)>p.speed(0f)*2f)
  assertEquals(0f,p.rate(Float.NaN),0f);assertEquals(0f,p.rate(0f),0f)
 }

 @Test fun theGateHasHysteresisAndSmoothAttackAndRelease() {
  val g=VoiceGate()
  repeat(3) { g.step(.9f,1f/60,true) }
  assertFalse("Attack is smoothed: three frames are not enough",g.open)
  repeat(60) { g.step(.9f,1f/60,true) }
  assertTrue(g.open);val loud=g.intensity
  repeat(12) { g.step(0f,1f/60,true) }
  assertTrue("Release is slower than attack: still open shortly after the voice stops",g.open && g.intensity<loud)
  repeat(120) { g.step(0f,1f/60,true) }
  assertFalse(g.open);assertEquals(0f,g.intensity,0f)
  repeat(60) { g.step(.9f,1f/60,true) };g.step(.9f,1f/60,false)
  assertFalse("Leaving recording closes the gate at once",g.open)
 }

 @Test fun loudSpeechIsCappedAndSilenceDrainsTheStream() {
  val p=VoiceParticleSystem()
  var peak=0
  repeat(600) { p.step(1f/60,1f,true,1080f,2000f,2.75f,540f,800f,{ 150f }) { _,_ -> };peak=max(peak,p.count) }
  assertTrue("Never more than ${VoiceParticleSystem.MAX_ALIVE} comets",peak<=VoiceParticleSystem.MAX_ALIVE)
  val before=p.spawned
  repeat(8*60) { p.step(1f/60,0f,true,1080f,2000f,2.75f,540f,800f,{ 150f }) { _,_ -> } }
  assertTrue("After the voice stops nothing new appears for long",p.spawned-before<=8)
  assertTrue("…and everything in flight is absorbed or gone",p.idle)
 }

 @Test fun cometsCurveIntoTheBubbleAndAreAbsorbedWithSparks() {
  val hits=mutableListOf<Pair<Float,Float>>()
  var minY=Float.MAX_VALUE;var curved=false
  val p=VoiceParticleSystem()
  repeat(300) { f ->
   p.step(1f/60,.85f,true,1080f,2000f,2.75f,540f,800f,{ 150f }) { a,s -> hits+=a to s }
   for(i in 0 until p.capacity) if(p.alive[i]) {
    assertTrue(p.x[i].isFinite() && p.y[i].isFinite());minY=min(minY,p.y[i])
    // The path is not a straight line to the centre: velocity has a sideways (vortex) part.
    val dx=540f-p.x[i];val dy=800f-p.y[i];val d=sqrt(dx*dx+dy*dy)
    val cross=abs(p.vx[i]*dy/d-p.vy[i]*dx/d)/sqrt(p.vx[i]*p.vx[i]+p.vy[i]*p.vy[i]).coerceAtLeast(1f)
    if(cross>.25f) curved=true
    assertTrue(p.hue[i] in 0f..1f)
   }
   assertTrue(p.count<=p.capacity)
  }
  assertTrue("Comets swirl on their way in",curved)
  assertTrue("Comets reach the bubble",hits.isNotEmpty())
  assertEquals(hits.size,p.hits)
  assertTrue("Coming from below, most land low on the film (below 30° above the equator)",hits.count { (a,_) -> sin(a)>-.5f }>=hits.size*.8f)
  assertTrue(hits.all { (_,s) -> s in 0f..1f })
  assertTrue("Absorbed at the film, never flying through the centre",minY>=800f-150f-80f)
  assertTrue("A hit leaves sparks",p.sparkAge.any { it<VoiceParticleSystem.SPARK_LIFE } || p.flashAge.any { it<VoiceParticleSystem.FLASH_LIFE })
  p.reset();assertEquals(0,p.count);assertTrue(p.idle)
 }
}
