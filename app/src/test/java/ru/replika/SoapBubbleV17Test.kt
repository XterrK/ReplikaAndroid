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
 @Test fun particlesFollowTheRealLevelAndStopInSilenceAndPause() {
  val boundary={ _: Float -> 120f }
  fun run(level: Float,active: Boolean,seconds: Float): VoiceParticleSystem {
   val p=VoiceParticleSystem()
   repeat((seconds*60).toInt()) { p.step(1f/60,level,active,1080f,2000f,2.75f,540f,800f,boundary) { _,_ -> } }
   return p
  }
  assertEquals("Silence fabricates nothing",0,run(0f,true,3f).spawned)
  assertEquals("Below the silence threshold nothing is launched",0,run(.02f,true,3f).spawned)
  assertEquals("Paused recorder launches nothing",0,run(.9f,false,3f).spawned)
  val quiet=run(.12f,true,3f).spawned;val loud=run(.9f,true,3f).spawned
  assertTrue("Quiet speech is still visible: $quiet",quiet>=8)
  assertTrue("Louder speech launches more particles: $quiet vs $loud",loud>quiet*3)
  val p=VoiceParticleSystem()
  assertTrue(p.speed(.9f)>p.speed(.1f)*2)
  assertTrue(p.rate(Float.NaN)==0f && p.speed(Float.NaN)==p.speed(0f))
 }
 @Test fun particlesFlyFromTheBottomEdgeAndHitTheBubble() {
  val p=VoiceParticleSystem(capacity=24)
  val hits=mutableListOf<Pair<Float,Float>>()
  var minY=Float.MAX_VALUE
  repeat(240) {
   p.step(1f/60,.8f,true,1080f,2000f,2.75f,540f,800f,{ 150f }) { a,s -> hits+=a to s }
   for(i in 0 until p.capacity) if(p.alive[i]) { assertTrue(p.x[i].isFinite() && p.y[i].isFinite());minY=min(minY,p.y[i]) }
   assertTrue(p.count<=p.capacity)
  }
  assertTrue("Particles must reach the bubble",hits.isNotEmpty())
  assertEquals(hits.size,p.hits)
  // Coming from below, hits land on the lower half of the bubble (screen y down: angle in 0..pi).
  assertTrue(hits.count { (a,_) -> sin(a)>0f }>=hits.size*.8f)
  assertTrue(hits.all { (_,s) -> s in 0f..1f })
  assertTrue("Particles stop at the bubble, never fly past its centre",minY>=800f-150f-60f)
  p.reset();assertEquals(0,p.count)
 }
}
