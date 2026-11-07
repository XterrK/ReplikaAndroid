package ru.replika.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import ru.replika.data.ThemeMode

@Composable fun AppearanceSettings(vm: AppViewModel,onBack: ()->Unit) {
 val mode by vm.themeMode.collectAsStateWithLifecycle()
 Column(Modifier.fillMaxSize().padding(horizontal=20.dp)) {
  Row(verticalAlignment=Alignment.CenterVertically) {
   IconButton(onClick=onBack) { Icon(Icons.Outlined.ArrowBack,"Назад") }
   Text("Настройки",style=MaterialTheme.typography.headlineMedium)
  }
  Spacer(Modifier.height(24.dp))
  Text("Оформление",style=MaterialTheme.typography.titleMedium)
  Spacer(Modifier.height(12.dp))
  listOf(ThemeMode.LIGHT,ThemeMode.DARK,ThemeMode.SYSTEM).forEach { choice ->
   Row(Modifier.fillMaxWidth().heightIn(min=56.dp).testTag("theme-"+choice.name).selectable(selected=mode==choice,role=Role.RadioButton,onClick={vm.selectTheme(choice)}),verticalAlignment=Alignment.CenterVertically) {
    RadioButton(mode==choice,null);Spacer(Modifier.width(8.dp));Text(choice.label,style=MaterialTheme.typography.bodyLarge)
   }
   HorizontalDivider(color=SurfaceLine)
  }
 }
}
