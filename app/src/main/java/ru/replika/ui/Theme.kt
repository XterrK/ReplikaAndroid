package ru.replika.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
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
val Mint: Color @Composable get()=if(LocalReplikaDark.current) Color(0xFF88D5B1) else Color(0xFF25735C)
val Violet: Color @Composable get()=MaterialTheme.colorScheme.tertiary
val Amber: Color @Composable get()=if(LocalReplikaDark.current) Color(0xFFE5BB7D) else Color(0xFF8D570C)
val LocalReplikaDark=staticCompositionLocalOf { false }
@Composable fun speakerColor(id: Int): Color {
 val dark=LocalReplikaDark.current
 val colors=if(dark) listOf(0xFF8C9CFF,0xFFB9A2F0,0xFF88D5B1,0xFFE5BB7D,0xFFE5A7CA,0xFF8DCBD4) else listOf(0xFF465BB2,0xFF7855A6,0xFF25735C,0xFF8D570C,0xFF9B426F,0xFF266D7B)
 return if(id<0) Muted else Color(colors[id%colors.size])
}
object ProductSpace { val xs=4.dp;val sm=8.dp;val md=12.dp;val lg=16.dp;val xl=24.dp }
object ProductShape { val control=RoundedCornerShape(10.dp);val panel=RoundedCornerShape(12.dp);val sheet=RoundedCornerShape(20.dp) }
val EditorialFont=FontFamily.Serif
private val Onest=FontFamily(Font(R.font.onest))
private val ReplikaTypography=Typography(
 headlineLarge=TextStyle(fontFamily=EditorialFont,fontWeight=FontWeight.Normal,fontSize=30.sp,lineHeight=36.sp),
 headlineMedium=TextStyle(fontFamily=EditorialFont,fontWeight=FontWeight.Normal,fontSize=26.sp,lineHeight=32.sp),
 headlineSmall=TextStyle(fontFamily=EditorialFont,fontWeight=FontWeight.Normal,fontSize=24.sp,lineHeight=30.sp),
 titleLarge=TextStyle(fontFamily=EditorialFont,fontWeight=FontWeight.Medium,fontSize=22.sp,lineHeight=28.sp),
 titleMedium=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Medium,fontSize=16.sp,lineHeight=22.sp),
 titleSmall=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Medium,fontSize=14.sp,lineHeight=20.sp),
 bodyLarge=TextStyle(fontFamily=Onest,fontSize=16.sp,lineHeight=24.sp),
 bodyMedium=TextStyle(fontFamily=Onest,fontSize=14.sp,lineHeight=21.sp),
 bodySmall=TextStyle(fontFamily=Onest,fontSize=12.sp,lineHeight=18.sp),
 labelLarge=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Medium,fontSize=14.sp,lineHeight=20.sp),
 labelMedium=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Medium,fontSize=13.sp,lineHeight=18.sp),
 labelSmall=TextStyle(fontFamily=Onest,fontWeight=FontWeight.Medium,fontSize=12.sp,lineHeight=16.sp)
)
private val Light=lightColorScheme(
 primary=Color(0xFF465BB2),onPrimary=Color.White,primaryContainer=Color(0xFF798CE8),onPrimaryContainer=Color(0xFF151B31),
 secondary=Color(0xFF705594),onSecondary=Color.White,secondaryContainer=Color(0xFFEBECF0),onSecondaryContainer=Color(0xFF202226),
 tertiary=Color(0xFF7855A6),tertiaryContainer=Color(0xFFAE9DE9),onTertiaryContainer=Color(0xFF202226),
 background=Color(0xFFF5F5F6),onBackground=Color(0xFF202226),surface=Color.White,onSurface=Color(0xFF202226),
 surfaceVariant=Color(0xFFEBECF0),onSurfaceVariant=Color(0xFF626977),outline=Color(0xFF747A86),outlineVariant=Color(0xFFD9DCE3),
 surfaceContainer=Color.White,surfaceContainerLow=Color(0xFFF5F5F6),surfaceContainerHigh=Color(0xFFEBECF0),surfaceContainerHighest=Color(0xFFE2E4EA),surfaceContainerLowest=Color.White,
 error=Color(0xFFBA3048),errorContainer=Color(0xFFFFE5E9),onErrorContainer=Color(0xFF72152A),surfaceTint=Color.Transparent
)
private val Dark=darkColorScheme(
 primary=Color(0xFF8C9CFF),onPrimary=Color(0xFF171B2F),primaryContainer=Color(0xFF8C9CFF),onPrimaryContainer=Color(0xFF171B2F),
 secondary=Color(0xFFB9A2F0),onSecondary=Color(0xFF211B30),secondaryContainer=Color(0xFF282A2E),onSecondaryContainer=Color(0xFFF2F2F4),
 tertiary=Color(0xFFB9A2F0),tertiaryContainer=Color(0xFF282A2E),onTertiaryContainer=Color(0xFFB9A2F0),
 background=Color(0xFF111214),onBackground=Color(0xFFF2F2F4),surface=Color(0xFF1C1D20),onSurface=Color(0xFFF2F2F4),
 surfaceVariant=Color(0xFF282A2E),onSurfaceVariant=Color(0xFFA6A6AF),outline=Color(0xFF777A84),outlineVariant=Color(0xFF36383E),
 surfaceContainer=Color(0xFF1C1D20),surfaceContainerLow=Color(0xFF1C1D20),surfaceContainerHigh=Color(0xFF282A2E),surfaceContainerHighest=Color(0xFF303236),surfaceContainerLowest=Color(0xFF111214),
 error=Color(0xFFFFB4AB),errorContainer=Color(0xFF46212A),onErrorContainer=Color(0xFFFFDADD),surfaceTint=Color.Transparent
)
@Composable fun ReplikaTheme(mode: ThemeMode=ThemeMode.SYSTEM,content: @Composable ()->Unit) {
 val dark=mode==ThemeMode.DARK || mode==ThemeMode.SYSTEM && isSystemInDarkTheme()
 CompositionLocalProvider(LocalReplikaDark provides dark) {
  MaterialTheme(colorScheme=if(dark) Dark else Light,typography=ReplikaTypography,shapes=Shapes(extraSmall=RoundedCornerShape(6.dp),small=ProductShape.control,medium=ProductShape.panel,large=ProductShape.sheet,extraLarge=RoundedCornerShape(24.dp)),content=content)
 }
}
