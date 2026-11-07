package ru.replika.ui

import androidx.compose.animation.core.withInfiniteAnimationFrameNanos
import androidx.compose.foundation.Canvas
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.StateFlow
import kotlin.math.*

/**
 * Display-only particles rising from the microphone edge. Spawn rate and speed follow the real
 * recorder envelope; silence and pause spawn nothing. Preallocated arrays, no per-frame allocation.
 * Units are pixels; [unit] is one dp in pixels.
 */
class VoiceParticleSystem(val capacity: Int=56,seed: Int=0x2F6B) {
 val x=FloatArray(capacity);val y=FloatArray(capacity)
 val vx=FloatArray(capacity);val vy=FloatArray(capacity)
 val radius=FloatArray(capacity);val hue=FloatArray(capacity);val age=FloatArray(capacity)
 val alive=BooleanArray(capacity)
 /** Horizontal aim offset as a fraction of the bubble radius, −0.9…0.9, triangular around 0. */
 val aim=FloatArray(capacity)
 val flashX=FloatArray(FLASHES);val flashY=FloatArray(FLASHES);val flashAge=FloatArray(FLASHES) { FLASH_LIFE };val flashHue=FloatArray(FLASHES)
 private var nextFlash=0
 private var spawnDebt=0f
 private var random=seed
 var count=0;private set
 var spawned=0;private set
 var hits=0;private set

 fun reset() { alive.fill(false);count=0;spawnDebt=0f;flashAge.fill(FLASH_LIFE) }
 val idle get()=count==0 && flashAge.all { it>=FLASH_LIFE }

 private fun rand(): Float { random=random xor (random shl 13);random=random xor (random ushr 17);random=random xor (random shl 5);return (random ushr 8)/16777216f }

 /** Particles per second for a normalized envelope; zero below the silence threshold. */
 fun rate(level: Float): Float=if(!level.isFinite() || level<SILENCE) 0f else 3f+52f*level.coerceAtMost(1f).pow(1.25f)
 /** Launch speed in dp/s. */
 fun speed(level: Float): Float=230f+640f*(if(level.isFinite()) level.coerceIn(0f,1f) else 0f)

 /**
  * Advances every particle; a particle that crosses the bubble boundary is removed and reported
  * through [onHit] with the screen angle (y down) and a strength in 0..1.
  */
 fun step(dt: Float,level: Float,active: Boolean,width: Float,height: Float,unit: Float,targetX: Float,targetY: Float,boundary: (Float)->Float,onHit: (Float,Float)->Unit) {
  val h=if(dt.isFinite()) dt.coerceIn(0f,.05f) else 0f
  val signal=if(active && level.isFinite()) level.coerceIn(0f,1f) else 0f
  for(f in 0 until FLASHES) if(flashAge[f]<FLASH_LIFE) flashAge[f]+=h
  if(active && width>0f && height>0f) {
   spawnDebt=(spawnDebt+rate(signal)*h).coerceAtMost(6f)
   while(spawnDebt>=1f) { spawnDebt-=1f;spawn(signal,width,height,unit,targetX,targetY) }
  } else spawnDebt=0f
  val homing=1f-exp(-h*2.6f)
  val reach=boundary((PI/2).toFloat())*.85f
  for(i in 0 until capacity) {
   if(!alive[i]) continue
   age[i]+=h
   val cx=targetX-x[i];val cy=targetY-y[i];val centre=sqrt(cx*cx+cy*cy)
   val angle=atan2(y[i]-targetY,x[i]-targetX)
   if(centre<=boundary(angle)+radius[i]) {
    alive[i]=false;count--;hits++
    onHit(angle,(.16f+.34f*(radius[i]/(4.5f*unit))*(.45f+signal)).coerceIn(0f,1f))
    flashX[nextFlash]=x[i];flashY[nextFlash]=y[i];flashAge[nextFlash]=0f;flashHue[nextFlash]=hue[i];nextFlash=(nextFlash+1)%FLASHES
    continue
   }
   // Each particle aims at its own point across the bubble, so blows spread over the lower film.
   val dx=targetX+aim[i]*reach-x[i];val dy=targetY-y[i];val distance=sqrt(dx*dx+dy*dy).coerceAtLeast(1f)
   val pace=sqrt(vx[i]*vx[i]+vy[i]*vy[i]).coerceAtLeast(40f*unit)
   val wobble=sin(age[i]*7f+hue[i]*11f)*28f*unit
   vx[i]+=((dx/distance)*pace-vx[i])*homing+wobble*h
   vy[i]+=((dy/distance)*pace-vy[i])*homing
   x[i]+=vx[i]*h;y[i]+=vy[i]*h
   if(age[i]>4f || y[i]< -40f*unit || x[i]< -40f*unit || x[i]>width+40f*unit) { alive[i]=false;count-- }
  }
 }

 private fun spawn(level: Float,width: Float,height: Float,unit: Float,targetX: Float,targetY: Float) {
  val slot=alive.indexOfFirst { !it };if(slot<0) return
  // Centre-weighted across the bottom edge: the sum of two uniforms is triangular.
  val spread=(rand()+rand()-1f)*.48f
  x[slot]=width*(.5f+spread);y[slot]=height+6f*unit
  val dx=targetX-x[slot];val dy=targetY-y[slot];val d=sqrt(dx*dx+dy*dy).coerceAtLeast(1f)
  val v=speed(level)*unit*(.8f+rand()*.4f)
  vx[slot]=dx/d*v+(rand()-.5f)*60f*unit;vy[slot]=dy/d*v
  radius[slot]=(1.6f+rand()*2.4f+level*1.6f)*unit
  aim[slot]=(rand()+rand()-1f)*.9f
  hue[slot]=rand();age[slot]=0f;alive[slot]=true;count++;spawned++
 }
 companion object { const val SILENCE=.03f;const val FLASHES=12;const val FLASH_LIFE=.28f }
}

/**
 * Full-height overlay that replaces the old right-edge meter. It never takes layout space and never
 * moves the bubble centre. Particles are drawn only while the recorder is actually recording.
 */
@Composable fun VoiceParticleField(orb: OrbState,level: StateFlow<Float>,phase: RecordingPhase,modifier: Modifier=Modifier,system: VoiceParticleSystem=remember { VoiceParticleSystem() }) {
 val amplitude by level.collectAsStateWithLifecycle()
 val recording=phase==RecordingPhase.RECORDING
 val reduced=rememberReducedMotion()
 val value=if(recording) amplitude.coerceIn(0f,1f) else 0f
 val tick=remember { mutableLongStateOf(0L) }
 val origin=remember { floatArrayOf(0f,0f,0f,0f) } // x, y, width, height of this field in root
 val unit=LocalDensity.current.density
 val lifecycle=LocalLifecycleOwner.current.lifecycle
 val power=LocalContext.current.getSystemService(android.os.PowerManager::class.java)
 val boundary=remember(orb) { { angle: Float -> orb.boundaryPx(angle) } }
 val hit=remember(orb) { { angle: Float,strength: Float -> if(!orb.reducedMotion) orb.dynamics.impact(angle,strength*PARTICLE_WEIGHT) } }
 LaunchedEffect(recording,reduced,lifecycle) {
  if(reduced) { system.reset();tick.longValue++;return@LaunchedEffect }
  if(!recording && system.idle) return@LaunchedEffect
  lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
   var last=0L;var limit=0L;var check=0L
   // Pause stops new particles; the ones in flight finish their path, then the loop ends.
   while(recording || !system.idle) {
    withInfiniteAnimationFrameNanos { now ->
     val dt=if(last==0L) 1f/60 else (now-last)/1_000_000_000f;last=now
     system.step(dt,level.value,recording && limit<80,origin[2],origin[3],unit,orb.centerX-origin[0],orb.centerY-origin[1],boundary,hit)
     tick.longValue=now
    }
    val clock=android.os.SystemClock.elapsedRealtime()
    if(clock-check>1000) { limit=powerFrameLimit(power);check=clock }
    // Silence with nothing in flight: poll the envelope cheaply instead of drawing every vsync.
    val rest=if(system.idle && level.value<VoiceParticleSystem.SILENCE) 90L else limit
    if(rest>0) { if(rest>=90L) last=0L;delay(rest) }
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
  for(i in 0 until system.capacity) {
   if(!system.alive[i]) continue
   val color=Brand.at(system.hue[i])
   val head=Offset(system.x[i],system.y[i])
   val tail=Offset(system.x[i]-system.vx[i]*.045f,system.y[i]-system.vy[i]*.045f)
   drawLine(color.copy(alpha=.32f),tail,head,strokeWidth=system.radius[i]*1.3f,cap=StrokeCap.Round)
   drawCircle(color.copy(alpha=.95f),system.radius[i],head)
  }
  for(f in 0 until VoiceParticleSystem.FLASHES) {
   val a=system.flashAge[f];if(a>=VoiceParticleSystem.FLASH_LIFE) continue
   val k=a/VoiceParticleSystem.FLASH_LIFE
   drawCircle(Brand.at(system.flashHue[f]).copy(alpha=(1f-k)*.8f),(3f+12f*k)*unit,Offset(system.flashX[f],system.flashY[f]),style=Stroke(1.5f*unit))
  }
 }
}

/** Particles hit lightly: at most ~40 % of a finger tap, so speech ripples the film without denting it hard. */
internal const val PARTICLE_WEIGHT=.4f
