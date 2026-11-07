package ru.replika

import org.junit.Assert.*
import org.junit.Test
import ru.replika.ui.*
import kotlin.math.*

/** V1.7 soap bubble: jelly membrane, shader boundary and voice particles. Display-only logic. */
class SoapBubbleV17Test {
 @Test fun impactDentsTheFilmLocallyBulgesTheSidesAndRingsOut() {
  val d=OrbDynamics();val g=OrbContourGeometry()
  val bottom=(PI/2).toFloat()
  d.impact(bottom,.8f)
  repeat(5) { d.step(1f/60,0f,true) }
  g.update(d)
  val dent=d.radiusAt(bottom)*g.areaScale
  val side=d.radiusAt(0f)*g.areaScale
  assertTrue("The hit point must be pushed in, got $dent",dent<.97f)
  assertTrue("Area conservation pushes the sides out, got $side",side>1f)
  assertEquals(1,d.impacts)
  // The dent travels: some time later the opposite side moves, then everything settles.
  var maxTop=0f
  repeat(90) { d.step(1f/60,0f,true);maxTop=max(maxTop,abs(d.ringAt(-bottom))) }
  assertTrue("The wave must reach the far side of the contour",maxTop>.002f)
  repeat(400) { d.step(1f/60,0f,true) }
  assertFalse("Jelly oscillation must decay",d.ringMotion)
  assertFalse(d.hasInteractionMotion)
 }
 @Test fun tapNearTheEdgeDentsWhereTheFingerIsAndMembraneStaysBounded() {
  val d=OrbDynamics()
  repeat(300) { i ->
   d.impact(i*.37f,1.6f)
   if(i%7==0) d.poke(cos(i.toFloat()),sin(i.toFloat()))
   d.step(if(i%11==0) .9f else 1f/60,1f,true)
   assertTrue(d.ring.all { it.isFinite() && abs(it)<=OrbDynamics.RING_LIMIT+1e-6f })
   for(a in 0..24) { val r=d.radiusAt(a*.26f);assertTrue("radius $r",r.isFinite() && r>.4f) }
  }
  val e=OrbDynamics();e.press(.95f,0f)
  repeat(4) { e.step(1f/60,0f,true) }
  assertTrue("Pressing the right edge dents the right side first",e.ringAt(0f)<e.ringAt(PI.toFloat()))
 }
 @Test fun reducedMotionDropsTheMembraneWobble() {
  val d=OrbDynamics();d.impact(0f,1f)
  d.step(1f/60,.5f,true,reduced=true)
  assertTrue(d.ring.all { it==0f })
  assertFalse(d.ringMotion)
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
