package ru.replika.ui

import android.graphics.Bitmap
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.Shader
import androidx.compose.animation.core.withInfiniteAnimationFrameNanos
import androidx.compose.foundation.Canvas
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.StateFlow
import kotlin.math.*

/**
 * Noise gate over the display envelope: hysteresis (opens at [OPEN], closes below [CLOSE]) and
 * attack/release smoothing, so room noise and short clicks launch nothing and the stream follows a
 * voice smoothly. [intensity] is 0 while closed and grows with loudness above the gate.
 */
class VoiceGate {
 var smoothed=0f;private set
 var open=false;private set
 var intensity=0f;private set
 private var above=0f
 fun reset() { smoothed=0f;open=false;intensity=0f;above=0f }
 fun step(level: Float,dt: Float,active: Boolean): Float {
  val h=if(dt.isFinite()) dt.coerceIn(0f,.2f) else 0f
  val target=if(active && level.isFinite()) level.coerceIn(0f,1f) else 0f
  val tau=if(target>smoothed) ATTACK else RELEASE
  smoothed+=(target-smoothed)*(1f-exp(-h/tau))
  // Opening also needs the level to stay above the gate for HOLD seconds: a click is not a voice.
  above=if(active && !open && smoothed>=OPEN) above+h else 0f
  if(!active) { open=false;smoothed=0f }
  else if(!open && above>=HOLD) open=true
  else if(open && smoothed<CLOSE) open=false
  intensity=if(open) ((smoothed-CLOSE)/(1f-CLOSE)).coerceIn(0f,1f) else 0f
  return intensity
 }
 companion object { const val OPEN=.22f;const val CLOSE=.15f;const val ATTACK=.12f;const val RELEASE=.35f;const val HOLD=.1f }
}

/**
 * Display-only glowing comets rising from the microphone edge into the bubble, only while recording
 * and only when the gate is open. Paths bend and swirl towards the bubble and speed up near the film;
 * on contact a particle is absorbed with a flash and a few sparks. Preallocated arrays, no per-frame
 * allocation. Units are pixels; [unit] is one dp in pixels.
 */
class VoiceParticleSystem(val capacity: Int=MAX_ALIVE,seed: Int=0x2F6B) {
 val gate=VoiceGate()
 val x=FloatArray(capacity);val y=FloatArray(capacity)
 val vx=FloatArray(capacity);val vy=FloatArray(capacity)
 val radius=FloatArray(capacity);val bright=FloatArray(capacity);val age=FloatArray(capacity)
 val swirl=FloatArray(capacity);val twinkle=FloatArray(capacity);val startDistance=FloatArray(capacity)
 /** 0 at birth (blue) → 1 at the film (pink): how far along its path the particle is. */
 val hue=FloatArray(capacity)
 val alive=BooleanArray(capacity)
 /** Comet tail: the last [TRAIL] positions of each particle in a ring buffer. */
 val trailX=FloatArray(capacity*TRAIL);val trailY=FloatArray(capacity*TRAIL)
 val trailHead=IntArray(capacity);val trailCount=IntArray(capacity)
 val sparkX=FloatArray(SPARKS);val sparkY=FloatArray(SPARKS);val sparkVx=FloatArray(SPARKS);val sparkVy=FloatArray(SPARKS)
 val sparkAge=FloatArray(SPARKS) { SPARK_LIFE };val sparkHue=FloatArray(SPARKS)
 val flashX=FloatArray(FLASHES);val flashY=FloatArray(FLASHES);val flashAge=FloatArray(FLASHES) { FLASH_LIFE };val flashHue=FloatArray(FLASHES)
 private var nextSpark=0
 private var nextFlash=0
 private var spawnDebt=0f
 private var random=seed
 var count=0;private set
 var spawned=0;private set
 var hits=0;private set

 fun reset() { alive.fill(false);count=0;spawnDebt=0f;flashAge.fill(FLASH_LIFE);sparkAge.fill(SPARK_LIFE);gate.reset() }
 val idle get()=count==0 && flashAge.all { it>=FLASH_LIFE } && sparkAge.all { it>=SPARK_LIFE }

 private fun rand(): Float { random=random xor (random shl 13);random=random xor (random ushr 17);random=random xor (random shl 5);return (random ushr 8)/16777216f }

 /** Particles per second for a gate intensity: smooth growth from a trickle to [MAX_RATE]. */
 fun rate(intensity: Float): Float=if(!intensity.isFinite() || intensity<=0f) 0f else MAX_RATE*intensity.coerceAtMost(1f).pow(1.2f)
 /** Cruise speed in dp/s for a gate intensity. */
 fun speed(intensity: Float): Float=210f+380f*(if(intensity.isFinite()) intensity.coerceIn(0f,1f) else 0f)

 /**
  * Advances the gate, every particle, spark and flash. A particle that reaches the bubble boundary is
  * absorbed and reported through [onHit] with the screen angle (y down) and a strength in 0..1.
  */
 fun step(dt: Float,level: Float,active: Boolean,width: Float,height: Float,unit: Float,targetX: Float,targetY: Float,boundary: (Float)->Float,onHit: (Float,Float)->Unit) {
  val intensity=gate.step(level,dt,active)
  val h=if(dt.isFinite()) dt.coerceIn(0f,.05f) else 0f
  for(f in 0 until FLASHES) if(flashAge[f]<FLASH_LIFE) flashAge[f]+=h
  for(s in 0 until SPARKS) if(sparkAge[s]<SPARK_LIFE) {
   sparkAge[s]+=h;val drag=exp(-h*5f)
   sparkVx[s]*=drag;sparkVy[s]*=drag;sparkX[s]+=sparkVx[s]*h;sparkY[s]+=sparkVy[s]*h
  }
  if(active && width>0f && height>0f && intensity>0f) {
   spawnDebt=(spawnDebt+rate(intensity)*h).coerceAtMost(3f)
   while(spawnDebt>=1f) { spawnDebt-=1f;spawn(intensity,width,height,unit,targetX,targetY,boundary) }
  } else spawnDebt=0f
  val steer=1f-exp(-h*3.4f)
  val cruise=speed(intensity.coerceAtLeast(.25f))*unit
  for(i in 0 until capacity) {
   if(!alive[i]) continue
   age[i]+=h
   val dx=targetX-x[i];val dy=targetY-y[i];val distance=sqrt(dx*dx+dy*dy).coerceAtLeast(1f)
   val angle=atan2(y[i]-targetY,x[i]-targetX)
   val edge=boundary(angle)
   if(distance<=edge+radius[i]*.5f) { absorb(i,angle,unit,intensity,onHit);continue }
   val gap=(distance-edge).coerceAtLeast(0f)
   hue[i]=(1f-gap/(startDistance[i]-edge).coerceAtLeast(1f)).coerceIn(0f,1f)
   // Attraction plus a vortex that fades near the film; the pull speeds the comet up at the surface.
   val nx=dx/distance;val ny=dy/distance
   val near=(1f-gap/(240f*unit)).coerceIn(0f,1f)
   val pace=cruise*(1f+1.5f*near*near)
   val spin=swirl[i]*(gap/(320f*unit)).coerceIn(0f,1f)*.85f
   vx[i]+=((nx-ny*spin)*pace-vx[i])*steer
   vy[i]+=((ny+nx*spin)*pace-vy[i])*steer
   x[i]+=vx[i]*h;y[i]+=vy[i]*h
   pushTrail(i)
   if(age[i]>LIFE || y[i]< -40f*unit || x[i]< -60f*unit || x[i]>width+60f*unit) { alive[i]=false;count-- }
  }
 }

 private fun pushTrail(i: Int) {
  val head=(trailHead[i]+1)%TRAIL;trailHead[i]=head
  trailX[i*TRAIL+head]=x[i];trailY[i*TRAIL+head]=y[i]
  if(trailCount[i]<TRAIL) trailCount[i]++
 }

 private fun absorb(i: Int,angle: Float,unit: Float,intensity: Float,onHit: (Float,Float)->Unit) {
  alive[i]=false;count--;hits++
  onHit(angle,(.25f+.5f*(radius[i]/(4f*unit))*(.5f+intensity)).coerceIn(0f,1f))
  flashX[nextFlash]=x[i];flashY[nextFlash]=y[i];flashAge[nextFlash]=0f;flashHue[nextFlash]=1f;nextFlash=(nextFlash+1)%FLASHES
  // A few sparks skate along the film in both directions and fade.
  val tx=-sin(angle);val ty=cos(angle)
  repeat(SPARKS_PER_HIT) { k ->
   val s=nextSpark;nextSpark=(nextSpark+1)%SPARKS
   val side=if(k%2==0) 1f else -1f
   val v=(70f+rand()*150f)*unit
   val out=(rand()*.6f+.15f)*v
   sparkX[s]=x[i];sparkY[s]=y[i]
   sparkVx[s]=tx*side*v+cos(angle)*out;sparkVy[s]=ty*side*v+sin(angle)*out
   sparkAge[s]=0f;sparkHue[s]=.7f+rand()*.3f
  }
 }

 private fun spawn(intensity: Float,width: Float,height: Float,unit: Float,targetX: Float,targetY: Float,boundary: (Float)->Float) {
  val slot=alive.indexOfFirst { !it };if(slot<0) return
  // A wide, centre-weighted band at the bottom edge: the microphone zone.
  val spread=(rand()+rand()+rand()-1.5f)/1.5f*.48f
  x[slot]=width*(.5f+spread);y[slot]=height+10f*unit
  val v=speed(intensity)*unit*(.75f+rand()*.4f)
  vx[slot]=(rand()-.5f)*80f*unit;vy[slot]=-v
  radius[slot]=(1.7f+rand()*2.6f+intensity*1.2f)*unit
  bright[slot]=.55f+rand()*.45f
  swirl[slot]=(if(rand()<.5f) -1f else 1f)*(.55f+rand()*.45f)
  twinkle[slot]=rand()*6.28f
  val dx=targetX-x[slot];val dy=targetY-y[slot]
  startDistance[slot]=sqrt(dx*dx+dy*dy)
  hue[slot]=0f;age[slot]=0f;alive[slot]=true;count++;spawned++
  trailHead[slot]=0;trailCount[slot]=0;pushTrail(slot)
 }

 companion object {
  /** Upper bound on simultaneous comets: the stream never floods the screen. */
  const val MAX_ALIVE=36
  const val MAX_RATE=30f
  const val TRAIL=10
  const val SPARKS=72
  const val SPARKS_PER_HIT=5
  const val SPARK_LIFE=.38f
  const val FLASHES=12
  const val FLASH_LIFE=.32f
  const val LIFE=4.5f
  /** Raw level under which the accessibility meter reports silence. */
  const val SILENCE=.03f
 }
}

/** Soft round glow sprites pre-tinted along the brand ramp; drawn additively they read as light. */
private class GlowSprites {
 val sprites: Array<ImageBitmap> = Array(HUES) { index ->
  val color=Brand.at(index/(HUES-1f)).toArgb()
  val bitmap=Bitmap.createBitmap(SIZE,SIZE,Bitmap.Config.ARGB_8888)
  val paint=Paint(Paint.ANTI_ALIAS_FLAG)
  val c=SIZE/2f
  paint.shader=RadialGradient(c,c,c,intArrayOf(withAlpha(color,255),withAlpha(color,110),withAlpha(color,28),withAlpha(color,0)),floatArrayOf(0f,.22f,.55f,1f),Shader.TileMode.CLAMP)
  android.graphics.Canvas(bitmap).drawCircle(c,c,c,paint)
  bitmap.asImageBitmap()
 }
 fun at(t: Float)=sprites[(t.coerceIn(0f,1f)*(HUES-1)).roundToInt()]
 companion object {
  const val HUES=12
  const val SIZE=64
  private fun withAlpha(color: Int,alpha: Int)=(color and 0x00FFFFFF) or (alpha shl 24)
 }
}

private fun DrawScope.glow(sprite: ImageBitmap,center: Offset,diameter: Float,alpha: Float,mode: BlendMode) {
 val d=diameter.roundToInt().coerceAtLeast(2)
 drawImage(sprite,IntOffset.Zero,IntSize(GlowSprites.SIZE,GlowSprites.SIZE),IntOffset((center.x-d/2f).roundToInt(),(center.y-d/2f).roundToInt()),IntSize(d,d),
  alpha=alpha.coerceIn(0f,1f),blendMode=mode,filterQuality=FilterQuality.Low)
}

/**
 * Full-height overlay over the recording screen. It never takes layout space and never moves the
 * bubble centre. Comets exist only while the recorder is recording and the voice gate is open.
 */
@Composable fun VoiceParticleField(orb: OrbState,level: StateFlow<Float>,phase: RecordingPhase,modifier: Modifier=Modifier,system: VoiceParticleSystem=remember { VoiceParticleSystem() }) {
 val amplitude by level.collectAsStateWithLifecycle()
 val recording=phase==RecordingPhase.RECORDING
 val reduced=rememberReducedMotion()
 val value=if(recording) amplitude.coerceIn(0f,1f) else 0f
 val tick=remember { mutableLongStateOf(0L) }
 val origin=remember { floatArrayOf(0f,0f,0f,0f) } // x, y, width, height of this field in root
 val unit=LocalDensity.current.density
 val dark=LocalReplikaDark.current
 val sprites=remember { GlowSprites() }
 val lifecycle=LocalLifecycleOwner.current.lifecycle
 val power=LocalContext.current.getSystemService(android.os.PowerManager::class.java)
 val boundary=remember(orb) { { angle: Float -> orb.boundaryPx(angle) } }
 val hit=remember(orb) { { angle: Float,strength: Float -> if(!orb.reducedMotion) orb.dynamics.impact(angle,strength*PARTICLE_WEIGHT) } }
 LaunchedEffect(recording,reduced,lifecycle) {
  if(reduced) { system.reset();tick.longValue++;return@LaunchedEffect }
  if(!recording) system.gate.reset()
  if(!recording && system.idle) return@LaunchedEffect
  lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
   var last=0L;var limit=0L;var check=0L
   // Pause stops new comets at once; those in flight finish their path, then the loop ends.
   while(recording || !system.idle) {
    withInfiniteAnimationFrameNanos { now ->
     val dt=if(last==0L) 1f/60 else (now-last)/1_000_000_000f;last=now
     system.step(dt,level.value,recording && limit<80,origin[2],origin[3],unit,orb.centerX-origin[0],orb.centerY-origin[1],boundary,hit)
     tick.longValue=now
    }
    val clock=android.os.SystemClock.elapsedRealtime()
    if(clock-check>1000) { limit=powerFrameLimit(power);check=clock }
    // Gate closed with nothing in flight: poll the envelope cheaply instead of drawing every vsync.
    val rest=if(system.idle && !system.gate.open) 90L else limit
    if(rest>0) delay(rest)
   }
  }
 }
 Canvas(modifier.testTag("voice-particles")
  .onGloballyPositioned { val p=it.positionInRoot();origin[0]=p.x;origin[1]=p.y;origin[2]=it.size.width.toFloat();origin[3]=it.size.height.toFloat() }
  .semantics {
   contentDescription="Уровень микрофона"
   stateDescription=if(!recording) "Микрофон не записывает" else if(value<VoiceParticleSystem.SILENCE) "Тишина" else "Звуковой сигнал"
   progressBarRangeInfo=ProgressBarRangeInfo(value,0f..1f)
  }) {
  tick.longValue
  // Additive light on the dark theme; on the light theme additive would wash out to white.
  val mode=if(dark) BlendMode.Plus else BlendMode.SrcOver
  val boost=if(dark) 1f else .8f
  val trail=VoiceParticleSystem.TRAIL
  for(i in 0 until system.capacity) {
   if(!system.alive[i]) continue
   val fade=(system.age[i]/.3f).coerceAtMost(1f)*((VoiceParticleSystem.LIFE-system.age[i])/.6f).coerceIn(0f,1f)
   val shimmer=.82f+.18f*sin(system.age[i]*14f+system.twinkle[i])
   val light=system.bright[i]*fade*shimmer*boost
   val color=Brand.at(system.hue[i])
   // Comet tail: a tapered, fading polyline along the real path (butt joints: no additive beads).
   val n=system.trailCount[i];val head=system.trailHead[i]
   for(k in 0 until n-1) {
    val a=(head-k+trail)%trail;val b=(head-k-1+trail)%trail
    val w=1f-k/(trail-1f)
    drawLine(color,Offset(system.trailX[i*trail+a],system.trailY[i*trail+a]),Offset(system.trailX[i*trail+b],system.trailY[i*trail+b]),
     strokeWidth=system.radius[i]*1.5f*w,cap=StrokeCap.Butt,alpha=(.55f*w*light).coerceIn(0f,1f),blendMode=mode)
   }
   val center=Offset(system.x[i],system.y[i])
   glow(sprites.at(system.hue[i]),center,system.radius[i]*12f,.85f*light,mode)
   drawCircle(Color.White,system.radius[i]*.5f,center,alpha=(.9f*light).coerceIn(0f,1f),blendMode=mode)
  }
  for(s in 0 until VoiceParticleSystem.SPARKS) {
   val a=system.sparkAge[s];if(a>=VoiceParticleSystem.SPARK_LIFE) continue
   val k=1f-a/VoiceParticleSystem.SPARK_LIFE
   val p=Offset(system.sparkX[s],system.sparkY[s])
   val back=Offset(p.x-system.sparkVx[s]*.035f,p.y-system.sparkVy[s]*.035f)
   drawLine(Brand.at(system.sparkHue[s]),back,p,strokeWidth=1.4f*unit,cap=StrokeCap.Round,alpha=(k*boost).coerceIn(0f,1f),blendMode=mode)
   glow(sprites.at(system.sparkHue[s]),p,7f*unit,.5f*k*boost,mode)
  }
  for(f in 0 until VoiceParticleSystem.FLASHES) {
   val a=system.flashAge[f];if(a>=VoiceParticleSystem.FLASH_LIFE) continue
   val k=a/VoiceParticleSystem.FLASH_LIFE
   glow(sprites.at(system.flashHue[f]),Offset(system.flashX[f],system.flashY[f]),(18f+30f*k)*unit,(1f-k)*(1f-k)*.9f*boost,mode)
  }
 }
}

/** Particles hit lightly: at most ~40 % of a finger tap, so speech ripples the film without denting it hard. */
internal const val PARTICLE_WEIGHT=.4f
