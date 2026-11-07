package ru.replika.ui

import kotlin.math.*

enum class RecordingPhase { IDLE, PERMISSION_REQUIRED, STARTING, RECORDING, PAUSED, STOPPING, SAVED, ERROR }

/** Display-only peak envelope. It does not change microphone samples, the recording or ASR. */
class VoiceEnvelope {
 private val window=FloatArray(80)
 private var count=0
 private var cursor=0
 var noiseFloor=.002f; private set
 var level=0f; private set
 fun reset() { count=0;cursor=0;noiseFloor=.002f;level=0f;window.fill(0f) }
 fun sample(peak: Float,dt: Float=.05f): Float {
  val raw=if(peak.isFinite()) peak.coerceIn(0f,1f) else 0f
  window[cursor]=raw;cursor=(cursor+1)%window.size;count=min(count+1,window.size)
  if(count>=20 && cursor%10==0) {
   val sorted=window.take(count).sorted()
   // A low percentile tracks quiet room tone; a cap prevents adapting sustained speech away.
   val target=sorted[(count*.15f).toInt()].coerceIn(.0003f,.018f)
   // Preserve sustained low-level foreground audio. A level-only meter cannot classify a
   // held vowel versus a newly louder fan, so it must not erase either genuine input.
   val foreground=level>.08f && raw>noiseFloor*2f
   if(target<=noiseFloor || !foreground) noiseFloor+=(target-noiseFloor)*.10f
  }
  val clean=((raw-noiseFloor*1.35f)/(1f-noiseFloor*1.35f)).coerceIn(0f,1f)
  // More detail in quiet voices without treating a zero input as speech.
  val target=(ln(1f+clean*64f)/ln(65f)).coerceIn(0f,1f).pow(.82f)
  val tau=if(target>level) .038f else .32f
  level+=(target-level)*(1f-exp(-dt.coerceIn(.001f,.1f)/tau))
  return level.coerceIn(0f,1f)
 }
}

/**
 * Independent damped modes form a soft body. Voice and touch are separate driving forces;
 * playing with the surface never writes the real microphone envelope or recorder state.
 */
class OrbDynamics {
 var expansion=0f;private set
 private var velocity=0f
 var time=0f;private set
 val modes=FloatArray(5)
 private val speeds=FloatArray(5)
 var voiceEnergy=0f;private set
 /** Kept at 0: the shell never stretches into an ellipse. Read by the Canvas fallback. */
 var stretch=0f;private set
 var touchAngle=0f;private set
 var centerX=0f;private set
 var centerY=0f;private set
 private var centerSpeedX=0f
 private var centerSpeedY=0f
 private var touchX=0f
 private var touchY=0f
 var contactEnergy=0f;private set
 private var contactSpeed=0f
 var isTouching=false;private set
 private var lastLevel=0f
 /** Kept at 0 since V1.7c: a tap is local again. Still part of the drawn radius for compatibility. */
 var spread=0f;private set

 /**
  * The jelly shell: radial displacement u(θ) = Σ aₙ·cos nθ + bₙ·sin nθ for n = [MODE_MIN]..[MODE_MAX].
  * Every harmonic is its own damped spring back to zero, so no shape — the oval mode 2 included — can
  * persist; n = 0 (mean) and n = 1 (shift) are excluded, so the deformation has zero mean and the area
  * is kept. A low-stiffness, string-like dispersion (ω² = K + T·n²) makes a local dent split into two
  * waves that run around the contour in both directions and fade.
  */
 val shapeA=FloatArray(MODE_COUNT)
 val shapeB=FloatArray(MODE_COUNT)
 private val speedA=FloatArray(MODE_COUNT)
 private val speedB=FloatArray(MODE_COUNT)
 private val omega2=FloatArray(MODE_COUNT) { val n=MODE_MIN+it;MODE_STIFFNESS+MODE_TENSION*n*n }
 private val decay=FloatArray(MODE_COUNT) { val n=MODE_MIN+it;MODE_DECAY+MODE_DECAY_N2*n*n }
 /** Footprint of a blow on each harmonic: a Gaussian dent of width [DENT_WIDTH] projected on cos/sin nθ. */
 private val footprint=FloatArray(MODE_COUNT) { val n=MODE_MIN+it;(DENT_WIDTH*sqrt(2.0*PI)/PI*exp(-n*n*DENT_WIDTH*DENT_WIDTH/2.0)).toFloat() }
 private val probeCos=FloatArray(PROBES*MODE_COUNT) { val n=MODE_MIN+it%MODE_COUNT;cos(n*(it/MODE_COUNT)*2*PI/PROBES).toFloat() }
 private val probeSin=FloatArray(PROBES*MODE_COUNT) { val n=MODE_MIN+it%MODE_COUNT;sin(n*(it/MODE_COUNT)*2*PI/PROBES).toFloat() }
 /** Count of particle/tap impacts since creation; display-only telemetry for tests. */
 var impacts=0;private set
 val shellMotion: Boolean get() {
  for(i in 0 until MODE_COUNT) if(abs(shapeA[i])+abs(shapeB[i])>.0015f || abs(speedA[i])+abs(speedB[i])>.02f) return true
  return false
 }
 val hasInteractionMotion get()=isTouching || abs(centerX)+abs(centerY)>.004f || abs(centerSpeedX)+abs(centerSpeedY)>.02f || abs(contactSpeed)>.02f || shellMotion

 /**
  * A blow on the film at screen angle [angle] (y down): an inward velocity impulse with a Gaussian
  * footprint. The dent appears exactly there, the sides bulge (zero mean), and two damped waves run
  * away from the point in both directions. Several blows superpose; the total amplitude is capped.
  */
 fun impact(angle: Float,strength: Float) {
  if(!angle.isFinite() || !strength.isFinite()) return
  val s=strength.coerceIn(0f,2f)*KICK
  impacts++
  for(i in 0 until MODE_COUNT) {
   val n=MODE_MIN+i
   val k=s*footprint[i]
   speedA[i]-=k*cos(n*angle);speedB[i]-=k*sin(n*angle)
  }
  contactSpeed=(contactSpeed+1.2f*strength.coerceIn(0f,2f)).coerceAtMost(5f)
 }

 /** A tap dents the film where the finger is (any side), the waves run off from there. */
 fun press(x: Float=0f,y: Float=0f) {
  isTouching=true
  moveTouch(x,y)
  val distance=sqrt(touchX*touchX+touchY*touchY)
  // A tap in the very middle has no side: it presses the top, like a finger from above.
  val angle=if(distance>.12f) atan2(touchY,touchX) else -PI.toFloat()/2
  touchAngle=angle
  impact(angle,1f)
 }
 /** While held, the finger keeps pressing the film where it is now; dragging moves the dent around. */
 fun moveTouch(x: Float,y: Float) {
  touchX=if(x.isFinite()) x.coerceIn(-1f,1f) else 0f
  touchY=if(y.isFinite()) y.coerceIn(-1f,1f) else 0f
  if(sqrt(touchX*touchX+touchY*touchY)>.12f) touchAngle=atan2(touchY,touchX)
 }
 fun release() { isTouching=false;touchX=0f;touchY=0f }
 fun poke(x: Float=0f,y: Float=0f) { press(x,y);release() }

 fun step(delta: Float,level: Float,active: Boolean,reduced: Boolean=false) {
  val dt=if(delta.isFinite()) delta.coerceIn(0f,.05f) else 0f
  val amplitude=if(active && level.isFinite()) level.coerceIn(0f,1f) else 0f
  val target=(if(active) .09f else 0f)+amplitude*.125f
  voiceEnergy=amplitude
  if(reduced) {
   expansion=target;velocity=0f;modes.fill(0f);speeds.fill(0f)
   centerX=0f;centerY=0f;centerSpeedX=0f;centerSpeedY=0f;contactEnergy=0f;contactSpeed=0f
   shapeA.fill(0f);shapeB.fill(0f);speedA.fill(0f);speedB.fill(0f)
   lastLevel=amplitude;return
  }
  val onset=(amplitude-lastLevel).coerceAtLeast(0f)
  if(onset>.015f) for(j in modes.indices) speeds[j]+=(if(j%2==0) 1f else -1f)*onset*.18f/(j+1)
  lastLevel=amplitude
  val steps=ceil(dt/(1f/120)).toInt().coerceAtLeast(1)
  val h=dt/steps
  repeat(steps) {
   time+=h
   velocity+=(88f*(target-expansion)-11.8f*velocity)*h
   expansion=(expansion+velocity*h).coerceIn(-.025f,.235f)
   for(j in modes.indices) {
    val goal=((if(active) .0015f else .0004f)+amplitude*.016f)/sqrt((j+1).toFloat())*sin(time*(1.65f+j*.43f)+j*1.3f)
    speeds[j]+=((36+j*10)*(goal-modes[j])-5.7f*speeds[j])*h
    modes[j]=(modes[j]+speeds[j]*h).coerceIn(-.026f,.026f)
   }
   val goalX=if(isTouching) touchX*.05f else 0f
   val goalY=if(isTouching) touchY*.05f else 0f
   centerSpeedX+=(72f*(goalX-centerX)-10f*centerSpeedX)*h
   centerSpeedY+=(72f*(goalY-centerY)-10f*centerSpeedY)*h
   centerX=(centerX+centerSpeedX*h).coerceIn(-.19f,.19f)
   centerY=(centerY+centerSpeedY*h).coerceIn(-.19f,.19f)
   contactSpeed+=(-55f*contactEnergy-8.5f*contactSpeed)*h
   contactEnergy=(contactEnergy+contactSpeed*h).coerceIn(-.18f,.55f)
   // A held finger keeps a soft inward pressure at its angle.
   val hold=if(isTouching) HOLD_PRESSURE*h else 0f
   // Semi-implicit Euler per harmonic: ω·h ≤ 0.65 at 120 Hz, every mode is stable and damped.
   for(i in 0 until MODE_COUNT) {
    val n=MODE_MIN+i
    if(hold!=0f) { speedA[i]-=hold*footprint[i]*cos(n*touchAngle);speedB[i]-=hold*footprint[i]*sin(n*touchAngle) }
    speedA[i]+=(-omega2[i]*shapeA[i]-2f*decay[i]*speedA[i])*h
    speedB[i]+=(-omega2[i]*shapeB[i]-2f*decay[i]*speedB[i])*h
    shapeA[i]+=speedA[i]*h;shapeB[i]+=speedB[i]*h
   }
   limitShell()
  }
 }

 /** Caps the largest radial displacement at [SHELL_LIMIT] by scaling the whole shell; nothing piles up. */
 private fun limitShell() {
  var peak=0f
  for(p in 0 until PROBES) {
   var u=0f;val base=p*MODE_COUNT
   for(i in 0 until MODE_COUNT) u+=shapeA[i]*probeCos[base+i]+shapeB[i]*probeSin[base+i]
   peak=max(peak,abs(u))
  }
  if(peak>SHELL_LIMIT) {
   val k=SHELL_LIMIT/peak
   for(i in 0 until MODE_COUNT) { shapeA[i]*=k;shapeB[i]*=k;speedA[i]*=k;speedB[i]*=k }
  }
 }

 /** Radial displacement of the shell along a screen angle. */
 fun shellAt(angle: Float): Float {
  var u=0f
  for(i in 0 until MODE_COUNT) { val n=MODE_MIN+i;u+=shapeA[i]*cos(n*angle)+shapeB[i]*sin(n*angle) }
  return u
 }

 /** Polar radius before per-frame area normalization; always positive and bounded. */
 fun radiusAt(angle: Float): Float {
  var wave=0f
  for(j in modes.indices) wave+=modes[j]*sin(angle*(j+2)+time*.24f+j*1.7f)
  return 1f+((wave*1.4f).coerceIn(-.20f,.20f)+shellAt(angle)).coerceIn(-.30f,.34f)
 }

 companion object {
  const val MODE_MIN=2
  const val MODE_MAX=12
  const val MODE_COUNT=MODE_MAX-MODE_MIN+1
  /** Low stiffness: the oval mode rings at ~2 Hz, a dent travels half way round in ~0.5 s. */
  const val MODE_STIFFNESS=4f
  const val MODE_TENSION=40f
  /** Decay rate per harmonic: visible jelly for ~0.6–1.2 s, fine ripples settle first. */
  const val MODE_DECAY=1.6f
  const val MODE_DECAY_N2=.04f
  const val DENT_WIDTH=.32
  /** One ordinary tap (strength 1) → a dent of ~11–12 % of the radius. */
  const val KICK=5f
  const val HOLD_PRESSURE=26f
  const val SHELL_LIMIT=.24f
  const val PROBES=96
 }
}

/** Reused primitive arrays; constant polar area keeps stretching convincingly liquid. */
class OrbContourGeometry(val count: Int=96) {
 init { require(count>=24) }
 val x=FloatArray(count)
 val y=FloatArray(count)
 /** r0, then cos/sin pairs for harmonics 1..8 of the normalized contour; the AGSL film reads these. */
 val harmonics=FloatArray(1+2*HARMONICS)
 private val cosTable=FloatArray(count*HARMONICS) { val k=it%HARMONICS+1;val i=it/HARMONICS;cos(k*i*2*PI/count).toFloat() }
 private val sinTable=FloatArray(count*HARMONICS) { val k=it%HARMONICS+1;val i=it/HARMONICS;sin(k*i*2*PI/count).toFloat() }
 var areaScale=1f;private set
 var maximumRadius=1f;private set
 fun update(dynamics: OrbDynamics) {
  var squares=0f
  for(i in 0 until count) {
   val angle=i*(2*PI/count).toFloat();val r=dynamics.radiusAt(angle)
   x[i]=cos(angle)*r;y[i]=sin(angle)*r;squares+=r*r
  }
  areaScale=1f/sqrt((squares/count).coerceAtLeast(.1f))
  maximumRadius=0f
  harmonics.fill(0f)
  for(i in 0 until count) {
   x[i]*=areaScale;y[i]*=areaScale
   val r=sqrt(x[i]*x[i]+y[i]*y[i])
   maximumRadius=max(maximumRadius,r)
   harmonics[0]+=r/count
   for(k in 0 until HARMONICS) {
    harmonics[1+2*k]+=2f*r*cosTable[i*HARMONICS+k]/count
    harmonics[2+2*k]+=2f*r*sinTable[i*HARMONICS+k]/count
   }
  }
 }
 /** Fourier reconstruction used to verify the shader boundary on the JVM. */
 fun harmonicRadius(angle: Float): Float {
  var r=harmonics[0]
  for(k in 0 until HARMONICS) r+=harmonics[1+2*k]*cos((k+1)*angle)+harmonics[2+2*k]*sin((k+1)*angle)
  return r
 }
 companion object { const val HARMONICS=8 }
}
