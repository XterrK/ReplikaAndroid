package ru.replika.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.*
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.replika.R
import ru.replika.data.ThemeMode

// Semantic accessors keep every existing screen, dialog and Canvas on the same palette.
val Ink: Color @Composable get()=MaterialTheme.colorScheme.background
val SurfaceBase: Color @Composable get()=MaterialTheme.colorScheme.surface
val SurfaceRaised: Color @Composable get()=MaterialTheme.colorScheme.surfaceVariant
val SurfaceLine: Color @Composable get()=MaterialTheme.colorScheme.outlineVariant
val Blue: Color @Composable get()=MaterialTheme.colorScheme.primary
val Muted: Color @Composable get()=MaterialTheme.colorScheme.onSurfaceVariant
val Mint: Color @Composable get()=if(LocalReplikaDark.current) Color(0xFF7CD9B4) else Color(0xFF1F7A5A)
val Violet: Color @Composable get()=MaterialTheme.colorScheme.tertiary
val Pink: Color @Composable get()=MaterialTheme.colorScheme.secondary
val Amber: Color @Composable get()=if(LocalReplikaDark.current) Color(0xFFE8C07D) else Color(0xFF8A560B)
val LocalReplikaDark=staticCompositionLocalOf { false }

/** V1.7 brand: one contrasting blue → violet → pink ramp shared by orb, icon, particles and CTAs. */
object Brand {
 val blue=Color(0xFF3D7BFF)
 val violet=Color(0xFF8A5CFF)
 val pink=Color(0xFFFF4FA3)
 val cyan=Color(0xFF4FD8FF)
 val colors=listOf(blue,violet,pink)
 /** Deeper stops for surfaces that carry white text: every stop keeps ≥ 4.5:1 against white. */
 val strong=listOf(Color(0xFF2F66EB),Color(0xFF7646EE),Color(0xFFD3307D))
 val horizontal get()=Brush.horizontalGradient(colors)
 val strongHorizontal get()=Brush.horizontalGradient(strong)
 /** Position t ∈ 0..1 along the ramp, used by particles and the bubble rim. */
 fun at(t: Float): Color {
  val x=t.coerceIn(0f,1f)
  return if(x<.5f) lerp(blue,violet,x*2f) else lerp(violet,pink,(x-.5f)*2f)
 }
 private fun lerp(a: Color,b: Color,f: Float)=Color(a.red+(b.red-a.red)*f,a.green+(b.green-a.green)*f,a.blue+(b.blue-a.blue)*f,a.alpha+(b.alpha-a.alpha)*f)
}

@Composable fun speakerColor(id: Int): Color {
 val dark=LocalReplikaDark.current
 val colors=if(dark) listOf(0xFF8FB2FF,0xFFFF8CC4,0xFF7CD9B4,0xFFE8C07D,0xFFB79BFF,0xFF7FD3E0) else listOf(0xFF2C5BD8,0xFFC02A72,0xFF1F7A5A,0xFF8A560B,0xFF6B3FD9,0xFF16707E)
 return if(id<0) Muted else Color(colors[id%colors.size])
}
object ProductSpace { val xs=4.dp;val sm=8.dp;val md=12.dp;val lg=16.dp;val xl=24.dp }
/** One radius family: controls 14, cards 16, sheets 24. */
object ProductShape { val control=RoundedCornerShape(14.dp);val panel=RoundedCornerShape(16.dp);val sheet=RoundedCornerShape(24.dp) }

/** The single typeface. Onest ships as one variable file (wght 100–900); weights are axis instances. */
@OptIn(androidx.compose.ui.text.ExperimentalTextApi::class)
private fun onest(weight: FontWeight)=Font(R.font.onest,weight=weight,variationSettings=FontVariation.Settings(FontVariation.weight(weight.weight)))
val Onest=FontFamily(onest(FontWeight.Light),onest(FontWeight.Normal),onest(FontWeight.Medium),onest(FontWeight.SemiBold),onest(FontWeight.Bold))
/** Kept for source compatibility with older screens; it is Onest, never a serif. */
val EditorialFont=Onest
// Hierarchy by weight and size only. Line height stays within 1.35–1.45 of the font size.
private val ReplikaTypography=Typography(
 displaySmall=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Bold,fontSize=32.sp,lineHeight=44.sp),
 headlineLarge=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Bold,fontSize=32.sp,lineHeight=44.sp),
 headlineMedium=TextStyle(fontFamily=Onest,fontWeight=FontWeight.SemiBold,fontSize=26.sp,lineHeight=36.sp),
 headlineSmall=TextStyle(fontFamily=Onest,fontWeight=FontWeight.SemiBold,fontSize=24.sp,lineHeight=33.sp),
 titleLarge=TextStyle(fontFamily=Onest,fontWeight=FontWeight.SemiBold,fontSize=22.sp,lineHeight=30.sp),
 titleMedium=TextStyle(fontFamily=Onest,fontWeight=FontWeight.SemiBold,fontSize=16.sp,lineHeight=22.sp),
 titleSmall=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Medium,fontSize=14.sp,lineHeight=20.sp),
 bodyLarge=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Normal,fontSize=16.sp,lineHeight=23.sp),
 bodyMedium=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Normal,fontSize=14.sp,lineHeight=20.sp),
 bodySmall=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Normal,fontSize=13.sp,lineHeight=18.sp),
 labelLarge=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Medium,fontSize=14.sp,lineHeight=20.sp),
 labelMedium=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Medium,fontSize=13.sp,lineHeight=18.sp),
 labelSmall=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Medium,fontSize=12.sp,lineHeight=17.sp)
)
// Text contrast (WCAG): light onSurface 17:1, onSurfaceVariant #5B6070 5.4–6.3:1, primary #2C5BD8 5.5:1;
// dark onSurface 17:1, onSurfaceVariant #A3A6B4 6.3–7.9:1, primary #8FB2FF 9:1.
private val Light=lightColorScheme(
 primary=Color(0xFF2C5BD8),onPrimary=Color.White,primaryContainer=Color(0xFFDCE6FF),onPrimaryContainer=Color(0xFF10245E),
 secondary=Color(0xFFC02A72),onSecondary=Color.White,secondaryContainer=Color(0xFFECEEF5),onSecondaryContainer=Color(0xFF15171D),
 tertiary=Color(0xFF6B3FD9),onTertiary=Color.White,tertiaryContainer=Color(0xFFE9E1FF),onTertiaryContainer=Color(0xFF26135A),
 background=Color(0xFFF6F7FB),onBackground=Color(0xFF15171D),surface=Color.White,onSurface=Color(0xFF15171D),
 surfaceVariant=Color(0xFFECEEF5),onSurfaceVariant=Color(0xFF5B6070),outline=Color(0xFF767B8A),outlineVariant=Color(0xFFDADDE8),
 surfaceContainer=Color.White,surfaceContainerLow=Color(0xFFF6F7FB),surfaceContainerHigh=Color(0xFFECEEF5),surfaceContainerHighest=Color(0xFFE3E6EF),surfaceContainerLowest=Color.White,
 error=Color(0xFFB3261E),errorContainer=Color(0xFFFFE4E6),onErrorContainer=Color(0xFF6E1420),surfaceTint=Color.Transparent
)
private val Dark=darkColorScheme(
 primary=Color(0xFF8FB2FF),onPrimary=Color(0xFF0E0F13),primaryContainer=Color(0xFF233A7A),onPrimaryContainer=Color(0xFFDCE6FF),
 secondary=Color(0xFFFF8CC4),onSecondary=Color(0xFF2A0A1A),secondaryContainer=Color(0xFF22252E),onSecondaryContainer=Color(0xFFF2F3F7),
 tertiary=Color(0xFFB79BFF),onTertiary=Color(0xFF1C1238),tertiaryContainer=Color(0xFF22252E),onTertiaryContainer=Color(0xFFB79BFF),
 background=Color(0xFF0E0F13),onBackground=Color(0xFFF2F3F7),surface=Color(0xFF181A21),onSurface=Color(0xFFF2F3F7),
 surfaceVariant=Color(0xFF22252E),onSurfaceVariant=Color(0xFFA3A6B4),outline=Color(0xFF6E7282),outlineVariant=Color(0xFF2E3240),
 surfaceContainer=Color(0xFF181A21),surfaceContainerLow=Color(0xFF14161C),surfaceContainerHigh=Color(0xFF22252E),surfaceContainerHighest=Color(0xFF2A2D37),surfaceContainerLowest=Color(0xFF0E0F13),
 error=Color(0xFFFFB4AB),errorContainer=Color(0xFF4A1E26),onErrorContainer=Color(0xFFFFDADD),surfaceTint=Color.Transparent
)
@Composable fun ReplikaTheme(mode: ThemeMode=ThemeMode.SYSTEM,content: @Composable ()->Unit) {
 val dark=mode==ThemeMode.DARK || mode==ThemeMode.SYSTEM && isSystemInDarkTheme()
 CompositionLocalProvider(LocalReplikaDark provides dark) {
  MaterialTheme(colorScheme=if(dark) Dark else Light,typography=ReplikaTypography,shapes=Shapes(extraSmall=RoundedCornerShape(8.dp),small=ProductShape.control,medium=ProductShape.panel,large=ProductShape.sheet,extraLarge=RoundedCornerShape(28.dp)),content=content)
 }
}
