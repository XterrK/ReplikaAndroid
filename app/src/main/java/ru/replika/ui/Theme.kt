package ru.replika.ui
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
val Ink=Color(0xFF0B1120)
val Blue=Color(0xFF6687FF)
val Muted=Color(0xFF9BA8C1)
val Mint=Color(0xFF6CE5C0)
val Violet=Color(0xFFB398FF)
val SpeakerColors=listOf(Blue,Mint,Violet,Color(0xFFFFBC86),Color(0xFFEA98C0))
fun speakerColor(id: Int)=if(id<0) Muted else SpeakerColors[id%SpeakerColors.size]
@Composable fun ReplikaTheme(content: @Composable ()->Unit) { MaterialTheme(colorScheme=darkColorScheme(primary=Blue,secondary=Mint,tertiary=Violet,background=Ink,surface=Ink,surfaceVariant=Color(0xFF182238),onBackground=Color(0xFFEEF2FF),onSurface=Color(0xFFEEF2FF),outline=Color(0xFF34415B)),content=content) }
