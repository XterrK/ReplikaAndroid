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

/** A draw-only frame subscription; touch never starts/stops an already running recorder. */
@Composable fun LiquidVoiceOrb(phase: RecordingPhase,level: StateFlow<Float>,onStart: ()->Unit,modifier: Modifier=Modifier,forceCanvas: Boolean=false) {
 val context=LocalContext.current
 val lifecycle=LocalLifecycleOwner.current.lifecycle
 val power=context.getSystemService(android.os.PowerManager::class.java)
 val haptics=LocalHapticFeedback.current
 val dark=LocalReplikaDark.current
 var reduced by remember { mutableStateOf(Settings.Global.getFloat(context.contentResolver,Settings.Global.ANIMATOR_DURATION_SCALE,1f)==0f) }
 DisposableEffect(context) {
  val observer=object: ContentObserver(Handler(Looper.getMainLooper())) { override fun onChange(selfChange: Boolean) { reduced=Settings.Global.getFloat(context.contentResolver,Settings.Global.ANIMATOR_DURATION_SCALE,1f)==0f } }
  context.contentResolver.registerContentObserver(Settings.Global.getUriFor(Settings.Global.ANIMATOR_DURATION_SCALE),false,observer)
  onDispose { context.contentResolver.unregisterContentObserver(observer) }
 }
 val dynamics=remember { OrbDynamics() }
 val geometry=remember { OrbContourGeometry() }
 val frame=remember { mutableLongStateOf(0L) }
 val gestureEpoch=remember { mutableIntStateOf(0) }
 val interaction=remember { MutableInteractionSource() }
 val active=phase==RecordingPhase.RECORDING || phase==RecordingPhase.STARTING
 val playable=phase==RecordingPhase.RECORDING || phase==RecordingPhase.PAUSED
 val canStart=phase in setOf(RecordingPhase.IDLE,RecordingPhase.SAVED,RecordingPhase.ERROR,RecordingPhase.PERMISSION_REQUIRED)
 val label=when(phase) {
  RecordingPhase.IDLE,RecordingPhase.SAVED->"Начать запись"
  RecordingPhase.PERMISSION_REQUIRED->"Разрешить доступ к микрофону"
  RecordingPhase.STARTING->"Включаем микрофон"
  RecordingPhase.RECORDING->"Запись идёт. Нажмите или потяните шар"
  RecordingPhase.PAUSED->"Запись на паузе. Можно размять шар"
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
     // Quiet recording uses 30fps; speech, phase changes and elastic touch retain the 60fps cap.
     // Keep listening to vsync rather than sleeping so a new voice peak wakes the next frame.
     val draw=cadence.shouldDraw(now,input,moving,transition)
     if(!draw && !reduced) return@withInfiniteAnimationFrameNanos
     val actual=if(last==0L) 1f/60 else (now-last)/1_000_000_000f
     last=now;elapsed+=actual
     dynamics.step(actual,input,active,reduced)
     frame.longValue=now
    }
    val now=android.os.SystemClock.elapsedRealtime()
    if(now-powerCheck>1000) {
     val thermal=if(Build.VERSION.SDK_INT>=29) power.currentThermalStatus else 0
     frameLimit=if(thermal>=3) 80 else if(power.isPowerSaveMode || thermal>=2) 24 else 0
     powerCheck=now
    }
    val rest=if(!active && !dynamics.hasInteractionMotion && elapsed>2.6f) maxOf(if(reduced) 500L else 65L,frameLimit) else cadence.restMillis(active,reduced,frameLimit)
    if(rest>0) delay(rest)
   } while(true)
  }
 }
 val shader=remember(forceCanvas) { if(Build.VERSION.SDK_INT>=33 && !forceCanvas) runCatching { AgslOrbSurface() }.getOrNull() else null }
 val contour=remember { Path() }
 val shadow=if(dark) Color(0x30685D8B) else Color(0x266A719A)
 val touch=if(playable) Modifier.pointerInput(phase,reduced) {
  awaitEachGesture {
   val down=awaitFirstDown(requireUnconsumed=false)
   fun normalized(position: Offset): Offset {
    val radius=size.width.coerceAtMost(size.height)*.39f
    return Offset(((position.x-size.width*.5f)/radius).coerceIn(-1f,1f),((position.y-size.height*.5f)/radius).coerceIn(-1f,1f))
   }
   val first=normalized(down.position)
   dynamics.press(first.x,first.y);gestureEpoch.intValue++
   haptics.performHapticFeedback(HapticFeedbackType.TextHandleMove)
   down.consume()
   try {
    while(true) {
     val event=awaitPointerEvent()
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
  .semantics {
   contentDescription=label;stateDescription=phase.name
   if(playable) {
    role=Role.Button
    onClick("Размять шар") { dynamics.poke();gestureEpoch.intValue++;true }
    customActions=listOf(CustomAccessibilityAction("Растянуть шар вправо") { dynamics.poke(.9f,0f);gestureEpoch.intValue++;true })
   }
  }
  .then(if(canStart) Modifier.clickable(interactionSource=interaction,indication=null,role=Role.Button,onClickLabel=label,onClick=onStart)
   else if(playable) Modifier.clickable(interactionSource=interaction,indication=null,role=Role.Button,onClickLabel="Размять шар") {
    dynamics.poke();gestureEpoch.intValue++
   }.then(touch) else Modifier)) {
  frame.longValue // Read exclusively during drawing, not in the screen's composition.
  geometry.update(dynamics)
  val base=Offset(size.width/2,size.height/2)
  val desired=size.minDimension*.39f*(1f+dynamics.expansion)
  val radius=min(desired,size.minDimension*.43f/geometry.maximumRadius.coerceAtLeast(.8f))
  val center=base+Offset(dynamics.centerX*radius,dynamics.centerY*radius)
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
  val floor=Offset(base.x+dynamics.centerX*radius*.4f,base.y+desired*.96f)
  scale(1f,.16f,floor) {
   drawCircle(Brush.radialGradient(listOf(shadow,Color.Transparent),floor,desired*.92f),desired*.92f,floor)
  }
  if(shader!=null && Build.VERSION.SDK_INT>=33) drawPath(contour,shader.brush(center,radius,dynamics,dark,geometry.areaScale))
  else drawFallbackSurface(contour,center,radius,dark,dynamics)
  drawPath(contour,Brush.linearGradient(listOf(Color.White.copy(alpha=.92f),Color(0xFFACC4FF).copy(alpha=.28f),Color(0xFFF2CBED).copy(alpha=.72f),Color.White.copy(alpha=.42f)),center-Offset(radius,radius),center+Offset(radius,radius)),style=Stroke(.55.dp.toPx()))
 }
}

private fun DrawScope.drawFallbackSurface(path: Path,c: Offset,r: Float,dark: Boolean,d: OrbDynamics) {
 clipPath(path) {
  rotate(d.touchAngle*180f/PI.toFloat(),c) {
   scale(exp(d.stretch),exp(-d.stretch),c) {
    drawRect(Brush.radialGradient(listOf(if(dark) Color(0xFF83AFE9) else Color(0xFFD5E8FA),if(dark) Color(0xFF7774BE) else Color(0xFFBAB6E7),if(dark) Color(0xFF4C639B) else Color(0xFFA4BBDD)),c-Offset(r*.25f,r*.3f),r*1.65f))
    val phase=d.time*.18f
    val blue=if(dark) Color(0xFF407FC3) else Color(0xFF80B9EB)
    val lilac=if(dark) Color(0xFF9373C4) else Color(0xFFC7AFE8)
    val flow=c+Offset(sin(phase)*r*.25f,r*.24f)
    drawOval(Brush.radialGradient(listOf(blue.copy(alpha=.70f),blue.copy(alpha=.18f),Color.Transparent),flow,r*1.1f),Offset(flow.x-r*1.3f,flow.y-r*.48f),Size(r*2.6f,r*1.05f))
    val cloud=c+Offset(r*.32f,cos(phase)*r*.22f-r*.23f)
    drawCircle(Brush.radialGradient(listOf(lilac.copy(alpha=.65f),Color.Transparent),cloud,r*.90f),r*.90f,cloud)
    rotate(-25f+sin(phase)*8f,c) {
     drawOval(Brush.verticalGradient(listOf(Color.Transparent,Color(0xFFD4F2FF).copy(alpha=.36f),Color.Transparent),c.y-r*.18f,c.y+r*.25f),Offset(c.x-r*1.3f,c.y-r*.18f),Size(r*2.6f,r*.43f))
    }
    drawCircle(Brush.radialGradient(0f to Color.Transparent,.78f to Color.Transparent,.93f to Color(0xFF657EBC).copy(alpha=.18f),.976f to Color(0xFFF1F6FF).copy(alpha=.80f),1f to Color(0xFF97C3EE).copy(alpha=.40f),center=c,radius=r),r,c)
    val key=c+Offset(-r*.40f,-r*.59f)
    rotate(-34f,key) {
     drawOval(Brush.radialGradient(listOf(Color.White.copy(alpha=.95f),Color.White.copy(alpha=.1f),Color.Transparent),key,r*.25f),key-Offset(r*.28f,r*.085f),Size(r*.56f,r*.17f))
    }
    val caustic=c+Offset(r*.38f,r*.73f)
    drawOval(Brush.radialGradient(listOf(Color.White.copy(alpha=.8f),Color.Transparent),caustic,r*.22f),caustic-Offset(r*.24f,r*.07f),Size(r*.48f,r*.14f))
   }
  }
 }
}

@RequiresApi(33)
internal class AgslOrbSurface {
 private val shader=android.graphics.RuntimeShader(SOURCE)
 private val shaderBrush=ShaderBrush(shader)
 fun brush(center: Offset,radius: Float,d: OrbDynamics,dark: Boolean,shapeScale: Float=1f): Brush {
  shader.setFloatUniform("center",center.x,center.y);shader.setFloatUniform("radius",radius)
  shader.setFloatUniform("time",d.time);shader.setFloatUniform("dark",if(dark) 1f else 0f)
  shader.setFloatUniform("energy",d.voiceEnergy);shader.setFloatUniform("contact",d.contactEnergy)
  shader.setFloatUniform("shape",d.stretch,d.touchAngle,shapeScale)
  shader.setFloatUniform("modesA",d.modes[0],d.modes[1],d.modes[2],d.modes[3]);shader.setFloatUniform("modeB",d.modes[4])
  return shaderBrush
 }
 companion object {
 private const val SOURCE="""
 uniform float2 center;
 uniform float radius;
 uniform float time;
 uniform float dark;
 uniform float energy;
 uniform float contact;
 uniform float3 shape;
 uniform float4 modesA;
 uniform float modeB;
 half4 main(float2 xy) {
  float2 p=(xy-center)/radius;
  float a=atan(p.y,p.x);
  float relative=a-shape.y;
  float sx=exp(shape.x);
  float sy=1./sx;
  float2 axis=float2(cos(relative),sin(relative));
  float ellipse=inversesqrt(axis.x*axis.x/(sx*sx)+axis.y*axis.y/(sy*sy));
  float wave=modesA.x*sin(a*2.+time*.24)+modesA.y*sin(a*3.+time*.24+1.7)+modesA.z*sin(a*4.+time*.24+3.4)+modesA.w*sin(a*5.+time*.24+5.1)+modeB*sin(a*6.+time*.24+6.8);
  float ripple=contact*.085*cos(relative*3.-time*1.1);
  float boundary=ellipse*(1.+clamp(wave*1.4+ripple,-.20,.20)+.003*sin(a*3.+time*.48))*shape.z;
  float2 q=p/max(boundary,.4);
  float rho=clamp(length(q),0.,1.);
  float z=sqrt(max(0.,1.-rho*rho));
  // Domain-warped internal flow sampled on a sphere, not a diagonal surface gradient.
  float3 normal=normalize(float3(q,z));
  float t=time*.18;
  float2 v=q*(1.15+.22*z);
  float bend=sin(v.y*2.6-t)*.24+sin(v.x*2.2+t*.8)*.17;
  float2 uv=float2(v.x+sin(v.y*2.3+t)*.30,v.y+sin(v.x*2.1-t*.7)*.28);
  float field=sin(uv.x*2.4+uv.y*1.6+t)+.48*sin(uv.y*4.2-uv.x*1.3-t*.8)+.20*sin(uv.x*7.+uv.y*4.+t*.5);
  float cloud=smoothstep(-1.15,1.25,field);
  float3 ice=mix(float3(.76,.88,.98),float3(.23,.51,.86),dark*.72);
  float3 lilac=mix(float3(.76,.71,.94),float3(.45,.31,.72),dark*.75);
  float3 col=mix(ice,lilac,cloud);
  float diffuse=max(0.,dot(normal,normalize(float3(-.5,-.65,1.))));
  col*=.76+.19*z+.16*diffuse;
  // Soft ribbons fold through the material. A wide shaded shoulder provides depth.
  float ribbon=uv.y*.85+uv.x*.40+bend+.12*sin(uv.x*3.-t);
  float band=exp(-pow((ribbon-.09*sin(t))/.18,2.));
  float shoulder=exp(-pow((ribbon+.19)/.30,2.));
  col=mix(col,mix(float3(.35,.65,.94),float3(.20,.39,.76),dark),shoulder*.36);
  col=mix(col,float3(.83,.96,1.),band*(.25+energy*.09));
  float ribbon2=uv.y-uv.x*.48-.45+.16*sin(uv.x*3.4+t*.6);
  float silk=exp(-pow(ribbon2/.10,2.));
  col=mix(col,float3(.92,.79,.98),silk*.24);
  float fine=exp(-pow((ribbon+.05+.05*sin(uv.x*5.+t))/.028,2.));
  col=mix(col,float3(.85,.94,1.),fine*.14);
  float depth=exp(-pow((ribbon-.28)/.23,2.))*z;
  col*=1.-depth*.09;
  float2 curl=uv+float2(sin(uv.y*3.+t*.7),cos(uv.x*2.7-t*.6))*.25;
  float fold=curl.y+curl.x*.32+.20*sin(curl.x*3.4-t*.3);
  float veil=exp(-pow((fold+.26)/.075,2.));
  float veil2=exp(-pow((fold-.40)/.10,2.));
  col=mix(col,float3(.79,.91,1.),veil*.22);
  col=mix(col,float3(.88,.77,.98),veil2*.20);
  // Spherical edge thickness, cool refraction, iridescence and soft core light.
  float fresnel=pow(1.-z,3.);
  float3 rim=mix(float3(.58,.78,1.),float3(.89,.73,.96),.5+.5*sin(a*2.3+t*.2));
  col=mix(col,rim,fresnel*.68);
  float inner=exp(-pow((rho-.915)/.034,2.));
  col*=1.-inner*.14;
  float shell=exp(-pow((rho-.977)/.010,2.));
  col=mix(col,float3(.92,.97,1.),shell*.82);
  float core=exp(-dot(q-float2(-.12,.34),q-float2(-.12,.34))*3.4);
  col+=core*float3(.035,.07,.10);
  // Reflections are ellipses with feathered edges: no painted white arcs or planet rings.
  float2 highlight=q-float2(-.40,-.59);
  float2 h=float2(highlight.x*.84+highlight.y*.55,-highlight.x*.55+highlight.y*.84);
  float spec=smoothstep(.12,.68,exp(-(h.x*h.x*36.+h.y*h.y*330.)));
  col=mix(col,float3(1.),spec*.96);
  float soft=exp(-dot(highlight,highlight)*12.);
  col=mix(col,float3(.97,.99,1.),soft*.22);
  float side=exp(-pow((q.x+.89)/.035,2.)-pow((q.y-.10)/.22,2.));
  col=mix(col,float3(.96,.99,1.),side*.80);
  float2 low=q-float2(.39,.73);
  float gleam=exp(-(low.x*low.x*70.+low.y*low.y*270.));
  col=mix(col,float3(.96,.98,1.),gleam*.74);
  float alpha=mix(.89,.94,dark)+fresnel*.045;

  return half4(half3(clamp(col,0.,1.)*alpha),half(alpha));
 }
 """
 }
}
