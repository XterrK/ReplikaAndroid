package ru.replika.ui

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

val Ink=Color(0xFF0B1120)
val SurfaceBase=Color(0xFF101A2C)
val SurfaceRaised=Color(0xFF162238)
val SurfaceLine=Color(0xFF28364D)
val Blue=Color(0xFF6687FF)
val Muted=Color(0xFF9BA8C1)
val Mint=Color(0xFF6CE5C0)
val Violet=Color(0xFFB398FF)
val Amber=Color(0xFFFFC58A)
val SpeakerColors=listOf(Violet,Mint,Color(0xFFFFBC86),Color(0xFFEA98C0),Color(0xFF87C9EF),Color(0xFFB9C990),Color(0xFFD6B2EE),Color(0xFFB9BFEF),Color(0xFFF1A9A7),Color(0xFF80C6BA))
fun speakerColor(id: Int)=if(id<0) Muted else SpeakerColors[id%SpeakerColors.size]
object ProductSpace { val xs=4.dp;val sm=8.dp;val md=12.dp;val lg=16.dp;val xl=24.dp }
object ProductShape { val control=RoundedCornerShape(12.dp);val panel=RoundedCornerShape(16.dp);val sheet=RoundedCornerShape(20.dp) }

private val ReplikaTypography=Typography(
 headlineLarge=TextStyle(fontFamily=FontFamily.SansSerif,fontWeight=FontWeight.SemiBold,fontSize=28.sp,lineHeight=34.sp),
 headlineMedium=TextStyle(fontFamily=FontFamily.SansSerif,fontWeight=FontWeight.SemiBold,fontSize=24.sp,lineHeight=30.sp),
 titleLarge=TextStyle(fontWeight=FontWeight.SemiBold,fontSize=20.sp,lineHeight=26.sp),
 titleMedium=TextStyle(fontWeight=FontWeight.SemiBold,fontSize=16.sp,lineHeight=22.sp),
 titleSmall=TextStyle(fontWeight=FontWeight.Medium,fontSize=14.sp,lineHeight=20.sp),
 bodyLarge=TextStyle(fontSize=16.sp,lineHeight=24.sp),
 bodyMedium=TextStyle(fontSize=14.sp,lineHeight=21.sp),
 bodySmall=TextStyle(fontSize=12.sp,lineHeight=18.sp),
 labelLarge=TextStyle(fontWeight=FontWeight.Medium,fontSize=14.sp,lineHeight=20.sp),
 labelMedium=TextStyle(fontWeight=FontWeight.Medium,fontSize=13.sp,lineHeight=18.sp),
 labelSmall=TextStyle(fontWeight=FontWeight.Medium,fontSize=12.sp,lineHeight=16.sp)
)
@Composable fun ReplikaTheme(content: @Composable ()->Unit) {
 MaterialTheme(
  colorScheme=darkColorScheme(primary=Blue,onPrimary=Color(0xFF071128),primaryContainer=Color(0xFF1D315B),onPrimaryContainer=Color(0xFFDDE5FF),secondary=Mint,onSecondary=Color(0xFF08251F),secondaryContainer=SurfaceRaised,onSecondaryContainer=Mint,tertiary=Violet,onTertiary=Color(0xFF241B3B),tertiaryContainer=Color(0xFF29223F),onTertiaryContainer=Violet,background=Ink,surface=SurfaceBase,surfaceVariant=SurfaceRaised,onBackground=Color(0xFFEEF2FF),onSurface=Color(0xFFEEF2FF),onSurfaceVariant=Muted,outline=SurfaceLine,error=Color(0xFFFFB4AB),errorContainer=Color(0xFF3B202B),onErrorContainer=Color(0xFFFFDADD),surfaceTint=Blue),
  typography=ReplikaTypography,
  shapes=Shapes(extraSmall=RoundedCornerShape(8.dp),small=ProductShape.control,medium=ProductShape.panel,large=ProductShape.sheet,extraLarge=RoundedCornerShape(24.dp)),
  content=content
 )
}
