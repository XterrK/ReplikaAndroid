package ru.replika.ui

import android.database.ContentObserver
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.annotation.RequiresApi
import androidx.compose.animation.core.withInfiniteAnimationFrameNanos
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.*
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.StateFlow
import kotlin.math.*

/**
 * Shared between the bubble and the particle field: the jelly body plus where the bubble was last
 * drawn (root coordinates), so particles can hit the real contour. Plain fields, read during draw.
 */
@Stable class OrbState {
 val dynamics=OrbDynamics()
 internal val geometry=OrbContourGeometry()
 var centerX=0f;internal set
 var centerY=0f;internal set
 var radiusPx=0f;internal set
 var reducedMotion=false;internal set
 /** Boundary radius in px along a screen angle (y down), including dents and area normalization. */
 fun boundaryPx(angle: Float): Float=radiusPx*dynamics.radiusAt(angle)*geometry.areaScale
}
@Composable fun rememberOrbState()=remember { OrbState() }

@Composable internal fun rememberReducedMotion(): Boolean {
 val context=LocalContext.current
 var reduced by remember { mutableStateOf(Settings.Global.getFloat(context.contentResolver,Settings.Global.ANIMATOR_DURATION_SCALE,1f)==0f) }
 DisposableEffect(context) {
  val observer=object: ContentObserver(Handler(Looper.getMainLooper())) { override fun onChange(selfChange: Boolean) { reduced=Settings.Global.getFloat(context.contentResolver,Settings.Global.ANIMATOR_DURATION_SCALE,1f)==0f } }
  context.contentResolver.registerContentObserver(Settings.Global.getUriFor(Settings.Global.ANIMATOR_DURATION_SCALE),false,observer)
  onDispose { context.contentResolver.unregisterContentObserver(observer) }
 }
 return reduced
}

/** Thermal/power frame floor in ms: 0 normally, 24 in power save or moderate heat, 80 when hot. */
internal fun powerFrameLimit(power: android.os.PowerManager?): Long {
 if(power==null) return 0
 val thermal=if(Build.VERSION.SDK_INT>=29) power.currentThermalStatus else 0
 return if(thermal>=3) 80 else if(power.isPowerSaveMode || thermal>=2) 24 else 0
}

/** A soap bubble with a jelly membrane. Touch never starts/stops an already running recorder. */
@Composable fun LiquidVoiceOrb(phase: RecordingPhase,level: StateFlow<Float>,onStart: ()->Unit,modifier: Modifier=Modifier,forceCanvas: Boolean=false,state: OrbState=rememberOrbState()) {
 val context=LocalContext.current
 val lifecycle=LocalLifecycleOwner.current.lifecycle
 val power=context.getSystemService(android.os.PowerManager::class.java)
 val haptics=LocalHapticFeedback.current
 val dark=LocalReplikaDark.current
 val reduced=rememberReducedMotion()
 val dynamics=state.dynamics
 val geometry=state.geometry
 SideEffect { state.reducedMotion=reduced }
 val frame=remember { mutableLongStateOf(0L) }
 val gestureEpoch=remember { mutableIntStateOf(0) }
 val interaction=remember { MutableInteractionSource() }
 val origin=remember { floatArrayOf(0f,0f) }
 val active=phase==RecordingPhase.RECORDING || phase==RecordingPhase.STARTING
 val playable=phase==RecordingPhase.RECORDING || phase==RecordingPhase.PAUSED
 val canStart=phase in setOf(RecordingPhase.IDLE,RecordingPhase.SAVED,RecordingPhase.ERROR,RecordingPhase.PERMISSION_REQUIRED)
 val label=when(phase) {
  RecordingPhase.IDLE,RecordingPhase.SAVED->"Начать запись"
  RecordingPhase.PERMISSION_REQUIRED->"Разрешить доступ к микрофону"
  RecordingPhase.STARTING->"Включаем микрофон"
  RecordingPhase.RECORDING->"Запись идёт. Нажмите или потяните пузырь"
  RecordingPhase.PAUSED->"Запись на паузе. Можно потрогать пузырь"
  RecordingPhase.STOPPING->"Сохраняем запись"
  RecordingPhase.ERROR->"Повторить запись"
 }
 LaunchedEffect(phase,reduced,lifecycle,gestureEpoch.intValue) {
  lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
   var last=0L;var elapsed=0f;var frameLimit=0L;var powerCheck=0L
   val cadence=OrbFrameCadence()
   do {
    withInfiniteAnimationFrameNanos { now ->
     val input=if(active) level.value else 0f
     val moving=dynamics.hasInteractionMotion || abs(dynamics.contactEnergy)>.003f
     val transition=if(active) elapsed<2.6f else phase!=RecordingPhase.IDLE && phase!=RecordingPhase.PERMISSION_REQUIRED && elapsed<1.2f
     // Quiet recording uses 30fps; speech, particle hits, phase changes and touch retain the 60fps cap.
     // Keep listening to vsync rather than sleeping so a new voice peak wakes the next frame.
     val draw=cadence.shouldDraw(now,input,moving,transition)
     if(!draw && !reduced) return@withInfiniteAnimationFrameNanos
     val actual=if(last==0L) 1f/60 else (now-last)/1_000_000_000f
     last=now;elapsed+=actual
     dynamics.step(actual,input,active,reduced)
     frame.longValue=now
    }
    val now=android.os.SystemClock.elapsedRealtime()
    if(now-powerCheck>1000) { frameLimit=powerFrameLimit(power);powerCheck=now }
    val rest=if(!active && !dynamics.hasInteractionMotion && elapsed>2.6f) maxOf(if(reduced) 500L else 65L,frameLimit) else cadence.restMillis(active,reduced,frameLimit)
    if(rest>0) delay(rest)
   } while(true)
  }
 }
 val shader=remember(forceCanvas) { if(Build.VERSION.SDK_INT>=33 && !forceCanvas) runCatching { AgslBubbleSurface() }.getOrNull() else null }
 val fallback=remember { CanvasBubbleSurface() }
 val contour=remember { Path() }
 val touch=if(playable) Modifier.pointerInput(phase,reduced) {
  awaitEachGesture {
   val down=awaitFirstDown(requireUnconsumed=false)
   fun normalized(position: Offset): Offset {
    val radius=size.width.coerceAtMost(size.height)*.37f
    return Offset(((position.x-size.width*.5f)/radius).coerceIn(-1f,1f),((position.y-size.height*.5f)/radius).coerceIn(-1f,1f))
   }
   val first=normalized(down.position)
   dynamics.press(first.x,first.y);gestureEpoch.intValue++
   haptics.performHapticFeedback(HapticFeedbackType.TextHandleMove)
   down.consume()
   try {
    while(true) {
     val event=awaitPointerEvent()
     // Every extra finger that lands dents the film at its own side; waves superpose.
     for(other in event.changes) if(other.id!=down.id && other.pressed && !other.previousPressed) {
      val p=normalized(other.position)
      if(p.x*p.x+p.y*p.y>.0144f) dynamics.impact(kotlin.math.atan2(p.y,p.x),1f)
      other.consume();gestureEpoch.intValue++
     }
     val change=event.changes.firstOrNull { it.id==down.id }?:break
     if(!change.pressed) { change.consume();break }
     val point=normalized(change.position)
     dynamics.moveTouch(point.x,point.y)
     change.consume()
    }
   } finally { dynamics.release();gestureEpoch.intValue++ }
  }
 } else Modifier
 Canvas(modifier.aspectRatio(1f).testTag("liquid-voice-orb")
  .onGloballyPositioned { val p=it.positionInRoot();origin[0]=p.x;origin[1]=p.y }
  .semantics {
   contentDescription=label;stateDescription=phase.name
   if(playable) {
    role=Role.Button
    onClick("Потрогать пузырь") { dynamics.poke();gestureEpoch.intValue++;true }
    customActions=listOf(CustomAccessibilityAction("Нажать на пузырь") { dynamics.poke(.9f,0f);gestureEpoch.intValue++;true })
   }
  }
  .then(if(canStart) Modifier.clickable(interactionSource=interaction,indication=null,role=Role.Button,onClickLabel=label) {
    dynamics.poke();gestureEpoch.intValue++;onStart()
   }
   else if(playable) Modifier.clickable(interactionSource=interaction,indication=null,role=Role.Button,onClickLabel="Потрогать пузырь") {
    dynamics.poke();gestureEpoch.intValue++
   }.then(touch) else Modifier)) {
  frame.longValue // Read exclusively during drawing, not in the screen's composition.
  geometry.update(dynamics)
  val base=Offset(size.width/2,size.height/2)
  // The isotropic tap spread scales the whole circle after area normalization: never an oval.
  val desired=size.minDimension*.37f*(1f+dynamics.expansion+dynamics.spread)
  val radius=min(desired,size.minDimension*.485f/geometry.maximumRadius.coerceAtLeast(.8f))
  val center=base+Offset(dynamics.centerX*radius,dynamics.centerY*radius)
  state.centerX=origin[0]+center.x;state.centerY=origin[1]+center.y;state.radiusPx=radius
  val points=geometry.count
  contour.reset();contour.moveTo(center.x+geometry.x[0]*radius,center.y+geometry.y[0]*radius)
  for(i in 0 until points) {
   val p=(i+points-1)%points;val n=(i+1)%points;val m=(i+2)%points
   contour.cubicTo(
    center.x+(geometry.x[i]+(geometry.x[n]-geometry.x[p])/6)*radius,
    center.y+(geometry.y[i]+(geometry.y[n]-geometry.y[p])/6)*radius,
    center.x+(geometry.x[n]-(geometry.x[m]-geometry.x[i])/6)*radius,
    center.y+(geometry.y[n]-(geometry.y[m]-geometry.y[i])/6)*radius,
    center.x+geometry.x[n]*radius,center.y+geometry.y[n]*radius)
  }
  contour.close()
  // Soft coloured glow and a floor shadow: depth without an opaque body.
  drawCircle(Brush.radialGradient(listOf(Brand.violet.copy(alpha=if(dark) .20f else .13f),Brand.blue.copy(alpha=if(dark) .08f else .05f),Color.Transparent),center,radius*1.45f),radius*1.45f,center)
  val floor=Offset(base.x+dynamics.centerX*radius*.4f,base.y+desired*1.02f)
  scale(1f,.14f,floor) {
   drawCircle(Brush.radialGradient(listOf(if(dark) Color(0x40000000) else Color(0x2A2A2F5A),Color.Transparent),floor,desired*.85f),desired*.85f,floor)
  }
  if(shader!=null && Build.VERSION.SDK_INT>=33) drawPath(contour,shader.brush(center,radius,dynamics,dark,geometry))
  else with(fallback) { draw(contour,center,radius,dark,dynamics) }
 }
}

/** API 26–32: gradients and strokes only, still transparent with an iridescent, slowly turning rim. */
internal class CanvasBubbleSurface {
 private val matrix=android.graphics.Matrix()
 private var sweep: android.graphics.SweepGradient?=null
 private var sweepCenter=Offset.Unspecified
 private val sweepColors=intArrayOf(Brand.blue.toArgb(),Brand.cyan.toArgb(),Brand.violet.toArgb(),Brand.pink.toArgb(),0xFFFFC3E1.toInt(),Brand.blue.toArgb())
 private fun rim(c: Offset,degrees: Float): Brush {
  if(sweep==null || sweepCenter!=c) { sweep=android.graphics.SweepGradient(c.x,c.y,sweepColors,null);sweepCenter=c }
  matrix.setRotate(degrees,c.x,c.y);sweep!!.setLocalMatrix(matrix)
  return ShaderBrush(sweep!!)
 }
 fun DrawScope.draw(path: Path,c: Offset,r: Float,dark: Boolean,d: OrbDynamics) {
  val t=d.time
  clipPath(path) {
   // Transparent body: the background shows through; colour gathers towards the film edge.
   drawCircle(Brush.radialGradient(0f to Brand.blue.copy(alpha=if(dark) .05f else .07f),.62f to Brand.violet.copy(alpha=if(dark) .08f else .10f),.86f to Brand.pink.copy(alpha=if(dark) .22f else .26f),1f to Brand.cyan.copy(alpha=.55f),center=c,radius=r*1.06f),r*1.4f,c)
   // Two drifting film swirls stand in for thin-film interference.
   val a=c+Offset(sin(t*.31f)*r*.28f,cos(t*.23f)*r*.22f-r*.18f)
   drawCircle(Brush.radialGradient(listOf(Brand.cyan.copy(alpha=.26f+d.voiceEnergy*.12f),Color.Transparent),a,r*.75f),r*.75f,a)
   val b=c+Offset(cos(t*.27f)*r*.30f,sin(t*.19f)*r*.24f+r*.24f)
   drawCircle(Brush.radialGradient(listOf(Brand.pink.copy(alpha=.24f+d.voiceEnergy*.12f),Color.Transparent),b,r*.8f),r*.8f,b)
   // Window highlight and a small counter-reflection.
   val key=c+Offset(-r*.36f,-r*.44f)
   rotate(-36f,key) {
    drawOval(Brush.radialGradient(listOf(Color.White.copy(alpha=.92f),Color.White.copy(alpha=.18f),Color.Transparent),key,r*.30f),key-Offset(r*.30f,r*.11f),Size(r*.60f,r*.22f))
   }
   val low=c+Offset(r*.42f,r*.50f)
   drawCircle(Brush.radialGradient(listOf(Color.White.copy(alpha=.55f),Color.Transparent),low,r*.10f),r*.10f,low)
  }
  drawPath(path,rim(c,t*18f),style=Stroke(2.4.dp.toPx()),alpha=if(dark) .85f else .95f)
  drawPath(path,Color.White.copy(alpha=if(dark) .35f else .6f),style=Stroke(.7.dp.toPx()))
 }
}

@RequiresApi(33)
internal class AgslBubbleSurface {
 private val shader=android.graphics.RuntimeShader(SOURCE)
 private val shaderBrush=ShaderBrush(shader)
 fun brush(center: Offset,radius: Float,d: OrbDynamics,dark: Boolean,g: OrbContourGeometry?=null): Brush {
  shader.setFloatUniform("center",center.x,center.y);shader.setFloatUniform("radius",radius)
  shader.setFloatUniform("time",d.time);shader.setFloatUniform("dark",if(dark) 1f else 0f)
  shader.setFloatUniform("energy",d.voiceEnergy);shader.setFloatUniform("contact",d.contactEnergy)
  val h=g?.harmonics
  if(h==null) {
   shader.setFloatUniform("r0",1f)
   for(name in UNIFORMS) shader.setFloatUniform(name,0f,0f,0f,0f)
  } else {
   shader.setFloatUniform("r0",h[0])
   shader.setFloatUniform("ca",h[1],h[3],h[5],h[7]);shader.setFloatUniform("sa",h[2],h[4],h[6],h[8])
   shader.setFloatUniform("cb",h[9],h[11],h[13],h[15]);shader.setFloatUniform("sb",h[10],h[12],h[14],h[16])
  }
  return shaderBrush
 }
 companion object {
 private val UNIFORMS=arrayOf("ca","sa","cb","sb")
 internal const val SOURCE="""
 uniform float2 center;
 uniform float radius;
 uniform float time;
 uniform float dark;
 uniform float energy;
 uniform float contact;
 uniform float r0;
 uniform float4 ca;
 uniform float4 sa;
 uniform float4 cb;
 uniform float4 sb;
 // Boundary of the jelly contour as 8 Fourier harmonics computed on the CPU each frame.
 float boundary(float a) {
  float c1=cos(a);float s1=sin(a);
  float c2=c1*c1-s1*s1;float s2=2.*s1*c1;
  float c3=c2*c1-s2*s1;float s3=s2*c1+c2*s1;
  float c4=c3*c1-s3*s1;float s4=s3*c1+c3*s1;
  float c5=c4*c1-s4*s1;float s5=s4*c1+c4*s1;
  float c6=c5*c1-s5*s1;float s6=s5*c1+c5*s1;
  float c7=c6*c1-s6*s1;float s7=s6*c1+c6*s1;
  float c8=c7*c1-s7*s1;float s8=s7*c1+c7*s1;
  float r=r0+dot(ca,float4(c1,c2,c3,c4))+dot(sa,float4(s1,s2,s3,s4))+dot(cb,float4(c5,c6,c7,c8))+dot(sb,float4(s5,s6,s7,s8));
  return max(r,.3);
 }
 // Thin-film interference: reflected intensity for red, green and blue at film thickness d (nm).
 float3 film(float d,float cosT) {
  float3 ph=6.2831853*(2.*1.33*d*cosT)/float3(650.,532.,450.)+3.1415927;
  return .5+.5*cos(ph);
 }
 float3 ramp(float g) {
  float3 blue=float3(.239,.482,1.);
  float3 violet=float3(.541,.361,1.);
  float3 pink=float3(1.,.310,.639);
  return g<.5 ? mix(blue,violet,g*2.) : mix(violet,pink,g*2.-1.);
 }
 half4 main(float2 xy) {
  float2 p=(xy-center)/radius;
  float a=atan(p.y,p.x);
  float b=boundary(a);
  float2 q=p/b;
  float rho=clamp(length(q),0.,1.);
  float z=sqrt(max(0.,1.-rho*rho));
  float t=time;
  // Film thickness: gravity drains it towards the bottom, slow swirls stir the colours,
  // voice and touch add travelling bands.
  float swirl=sin(q.x*3.1+t*.35+sin(q.y*2.3-t*.27)*1.6)*.5+sin(q.y*4.2-t*.22+q.x*1.7)*.35+sin((q.x+q.y)*6.+t*.5)*.15;
  float thick=300.+260.*(q.y*.5+.5)+130.*swirl+80.*energy*sin(t*2.6+rho*7.)+70.*contact*sin(rho*16.-t*7.);
  float cosT=sqrt(max(0.,1.-rho*rho/1.769));
  float3 iris=film(thick,cosT);
  float g=.5+.5*sin(a+t*.12+swirl*.8);
  float3 col=mix(iris,ramp(g),.52);
  col=mix(col,col*col,(1.-dark)*.35);
  float fres=pow(1.-z,2.4);
  float alpha=mix(.10,.08,dark)+fres*mix(.82,.70,dark);
  // The far wall of the bubble shows as a faint inner ring.
  float ir=(rho-.90)/.045;alpha+=exp(-ir*ir)*.10;
  float rr=(rho-.985)/.018;float rim=exp(-rr*rr);
  col=mix(col,min(ramp(g)*1.15,float3(1.)),rim*.5);
  alpha=max(alpha,rim*.92);
  // Window reflection top-left, a counter-reflection bottom-right and a tiny glint.
  float2 h=q-float2(-.36,-.44);
  float2 hr=float2(h.x*.80+h.y*.60,-h.x*.60+h.y*.80);
  float spec=exp(-(hr.x*hr.x*22.+hr.y*hr.y*70.));
  float2 h2=q-float2(.42,.50);
  float spec2=exp(-dot(h2,h2)*160.)*.75;
  float2 h3=q-float2(-.55,-.16);
  float glint=exp(-dot(h3,h3)*260.)*.8;
  float s=clamp(spec*.92+spec2+glint,0.,1.);
  col=mix(col,float3(1.),s);
  alpha=clamp(alpha+s*.85,0.,.97);
  return half4(half3(clamp(col,0.,1.)*alpha),half(alpha));
 }
 """
 }
}
