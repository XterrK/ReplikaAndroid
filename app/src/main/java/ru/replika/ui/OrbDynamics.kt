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
 var stretch=0f;private set
 private var stretchSpeed=0f
 var touchAngle=0f;private set
 private var targetAngle=0f
 var centerX=0f;private set
 var centerY=0f;private set
 private var centerSpeedX=0f
 private var centerSpeedY=0f
 private var touchX=0f
 private var touchY=0f
 private var stretchTarget=0f
 var contactEnergy=0f;private set
 private var contactSpeed=0f
 var isTouching=false;private set
 private var lastLevel=0f
 /** Jelly membrane: radial displacement of [RING] mass points joined by springs to rest and to neighbours. */
 val ring=FloatArray(RING)
 private val ringSpeed=FloatArray(RING)
 private val ringForce=FloatArray(RING)
 /** Count of particle/tap impacts since creation; display-only telemetry for tests. */
 var impacts=0;private set
 val ringMotion: Boolean get() { for(i in 0 until RING) if(abs(ring[i])>.002f || abs(ringSpeed[i])>.02f) return true;return false }
 val hasInteractionMotion get()=isTouching || abs(stretch)>.003f || abs(stretchSpeed)>.015f || abs(centerX)+abs(centerY)>.004f || abs(centerSpeedX)+abs(centerSpeedY)>.02f || abs(contactSpeed)>.02f || ringMotion

 /**
  * A blow on the film at [angle]: an inward velocity impulse with a Gaussian footprint. Area
  * normalization in [OrbContourGeometry] turns the dent into a sideways bulge, then the
  * neighbour springs carry it around the contour as a damped wave.
  */
 fun impact(angle: Float,strength: Float) {
  if(!angle.isFinite() || !strength.isFinite()) return
  val s=strength.coerceIn(0f,1.6f)
  impacts++
  for(i in 0 until RING) {
   val node=i*(2f*PI.toFloat()/RING)
   val d=atan2(sin(node-angle),cos(node-angle))
   val w=exp(-(d*d)/(2f*.30f*.30f))
   ringSpeed[i]=(ringSpeed[i]-s*1.15f*w).coerceIn(-4f,4f)
  }
 }

 fun press(x: Float=0f,y: Float=0f) {
  isTouching=true
  moveTouch(x,y)
  val distance=sqrt(touchX*touchX+touchY*touchY)
  // A finger near the film dents it locally; a central tap squashes the whole bubble from above.
  if(distance>.12f) impact(atan2(touchY,touchX),.55f+distance*.35f) else { impact(-PI.toFloat()/2,.6f);impact(PI.toFloat()/2,.35f) }
  // An impulse makes even a short tap elastic; holding then dragging continuously stretches it.
  stretchSpeed=(stretchSpeed+1.9f).coerceAtMost(3.5f)
  contactSpeed=(contactSpeed+3.2f).coerceAtMost(5f)
  speeds[0]=(speeds[0]+.32f).coerceIn(-.8f,.8f)
  speeds[1]=(speeds[1]-.19f).coerceIn(-.8f,.8f)
 }
 fun moveTouch(x: Float,y: Float) {
  touchX=if(x.isFinite()) x.coerceIn(-1f,1f) else 0f
  touchY=if(y.isFinite()) y.coerceIn(-1f,1f) else 0f
  val distance=sqrt(touchX*touchX+touchY*touchY).coerceAtMost(1f)
  targetAngle=if(distance>.12f) atan2(touchY,touchX) else 0f
  stretchTarget=.19f+distance*.17f
 }
 fun release() { isTouching=false;stretchTarget=0f;touchX=0f;touchY=0f }
 fun poke(x: Float=0f,y: Float=0f) { press(x,y);release() }

 fun step(delta: Float,level: Float,active: Boolean,reduced: Boolean=false) {
  val dt=if(delta.isFinite()) delta.coerceIn(0f,.05f) else 0f
  val amplitude=if(active && level.isFinite()) level.coerceIn(0f,1f) else 0f
  val target=(if(active) .09f else 0f)+amplitude*.125f
  voiceEnergy=amplitude
  if(reduced) {
   expansion=target;velocity=0f;modes.fill(0f);speeds.fill(0f)
   stretch=0f;stretchSpeed=0f;centerX=0f;centerY=0f;centerSpeedX=0f;centerSpeedY=0f;contactEnergy=0f;contactSpeed=0f
   ring.fill(0f);ringSpeed.fill(0f)
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
    val goal=(.0015f+amplitude*.016f)/sqrt((j+1).toFloat())*sin(time*(1.65f+j*.43f)+j*1.3f)
    speeds[j]+=((36+j*10)*(goal-modes[j])-5.7f*speeds[j])*h
    modes[j]=(modes[j]+speeds[j]*h).coerceIn(-.026f,.026f)
   }
   // Angular interpolation follows the short arc when a finger crosses -pi/pi.
   val angleDelta=atan2(sin(targetAngle-touchAngle),cos(targetAngle-touchAngle))
   touchAngle+=angleDelta*(1f-exp(-h*13f))
   stretchSpeed+=(62f*(stretchTarget-stretch)-7.8f*stretchSpeed)*h
   stretch=(stretch+stretchSpeed*h).coerceIn(-.16f,.43f)
   val goalX=if(isTouching) touchX*.16f else 0f
   val goalY=if(isTouching) touchY*.16f else 0f
   centerSpeedX+=(72f*(goalX-centerX)-10f*centerSpeedX)*h
   centerSpeedY+=(72f*(goalY-centerY)-10f*centerSpeedY)*h
   centerX=(centerX+centerSpeedX*h).coerceIn(-.19f,.19f)
   centerY=(centerY+centerSpeedY*h).coerceIn(-.19f,.19f)
   contactSpeed+=(-55f*contactEnergy-8.5f*contactSpeed)*h
   contactEnergy=(contactEnergy+contactSpeed*h).coerceIn(-.18f,.55f)
   // Semi-implicit Euler on the membrane; omega*h < 0.4 at 120 Hz keeps every mode stable.
   for(i in 0 until RING) {
    val laplacian=ring[(i+RING-1)%RING]+ring[(i+1)%RING]-2f*ring[i]
    ringForce[i]=RING_STIFFNESS*-ring[i]+RING_TENSION*laplacian-RING_DAMPING*ringSpeed[i]
   }
   for(i in 0 until RING) {
    ringSpeed[i]=(ringSpeed[i]+ringForce[i]*h).coerceIn(-4f,4f)
    ring[i]=(ring[i]+ringSpeed[i]*h).coerceIn(-RING_LIMIT,RING_LIMIT)
   }
  }
 }

 /** Polar radius before per-frame area normalization; always positive and bounded. */
 fun radiusAt(angle: Float): Float {
  val relative=angle-touchAngle
  val sx=exp(stretch)
  val sy=1f/sx
  val cosine=cos(relative);val sine=sin(relative)
  val ellipse=1f/sqrt(cosine*cosine/(sx*sx)+sine*sine/(sy*sy))
  var wave=0f
  for(j in modes.indices) wave+=modes[j]*sin(angle*(j+2)+time*.24f+j*1.7f)
  val ripple=contactEnergy*.085f*cos(relative*3f-time*1.1f)
  return ellipse*(1f+((wave*1.4f+ripple).coerceIn(-.20f,.20f)+ringAt(angle)).coerceIn(-.30f,.34f)+.003f*sin(angle*3f+time*.48f))
 }

 /** Catmull-Rom interpolation keeps a smooth film between the [RING] mass points. */
 fun ringAt(angle: Float): Float {
  val turn=2f*PI.toFloat()
  val u=((angle%turn+turn)%turn)/turn*RING
  val i=floor(u).toInt();val t=u-i
  val p0=ring[(i+RING-1)%RING];val p1=ring[i%RING];val p2=ring[(i+1)%RING];val p3=ring[(i+2)%RING]
  return .5f*(2f*p1+(-p0+p2)*t+(2f*p0-5f*p1+4f*p2-p3)*t*t+(-p0+3f*p1-3f*p2+p3)*t*t*t)
 }

 companion object {
  const val RING=32
  const val RING_STIFFNESS=58f
  const val RING_TENSION=820f
  const val RING_DAMPING=3.4f
  const val RING_LIMIT=.26f
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
