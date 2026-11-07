package ru.replika.ui

/** Draw scheduling only. The recorder envelope, spring equations and contour are unchanged. */
internal class OrbFrameCadence {
 private var lastDrawNanos=Long.MIN_VALUE
 private var fastUntilNanos=Long.MIN_VALUE
 private var previousLevel=0f
 var fastFrames=false;private set

 /** Called on every available vsync, including skipped draws, so voice onset wakes promptly. */
 fun shouldDraw(nowNanos: Long,microphoneLevel: Float,interactionMoving: Boolean,settling: Boolean): Boolean {
  val level=if(microphoneLevel.isFinite()) microphoneLevel.coerceIn(0f,1f) else 0f
  if(level>=.015f || level-previousLevel>.006f || interactionMoving) {
   fastUntilNanos=maxOf(fastUntilNanos,nowNanos+800_000_000L)
  }
  previousLevel=level
  fastFrames=settling || interactionMoving || nowNanos<fastUntilNanos
  // 32ms admits two 60Hz/four 120Hz ticks even with timestamp rounding; no catch-up bursts.
  val minimum=if(fastFrames) 15_000_000L else 32_000_000L
  if(lastDrawNanos!=Long.MIN_VALUE && nowNanos-lastDrawNanos<minimum) return false
  lastDrawNanos=nowNanos
  return true
 }

 fun restMillis(active: Boolean,reducedMotion: Boolean,powerLimitMillis: Long): Long =
  maxOf(powerLimitMillis,if(reducedMotion) 120L else if(!active && !fastFrames) 70L else 0L)
}
