package ru.replika.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Translate
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import ru.replika.data.Recording
import ru.replika.domain.LanguageMode
import ru.replika.domain.TranscriptLanguage

/** Pre-processing choice next to the speaker mode: Auto (default) / Русский / English. */
@Composable fun LanguageChoice(language: LanguageMode,perSegment: Boolean,onLanguage: (LanguageMode)->Unit,onPerSegment: (Boolean)->Unit) {
 Text("Язык записи",style=MaterialTheme.typography.titleMedium)
 Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
  LanguageMode.entries.forEach { mode ->
   FilterChip(selected=language==mode,onClick={onLanguage(mode)},label={Text(mode.label)},modifier=Modifier.testTag("language-"+mode.wireId))
  }
 }
 Text(when(language) {
  LanguageMode.AUTO -> "Система сама определит, русская запись или английская. При сомнении выбирается русский."
  LanguageMode.RU -> "Русская речь · GigaAM v3."
  LanguageMode.EN -> "Английская речь · Parakeet TDT v2."
 },style=MaterialTheme.typography.bodySmall,color=Muted)
 if(language==LanguageMode.AUTO) Row(Modifier.fillMaxWidth().heightIn(min=48.dp)
  .toggleable(value=perSegment,role=Role.Switch,onValueChange=onPerSegment).testTag("language-per-segment"),
  verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
  Column(Modifier.weight(1f)) {
   Text("Определять язык для каждого фрагмента",style=MaterialTheme.typography.bodyMedium)
   Text("Экспериментально · для записей, где звучат оба языка. Обработка дольше.",style=MaterialTheme.typography.bodySmall,color=Muted)
  }
  Switch(checked=perSegment,onCheckedChange=null)
 }
}

/** Transcript header badge with the detected language and "Распознать заново как …". */
@Composable fun TranscriptLanguageAction(vm: AppViewModel,rec: Recording) {
 val summary=remember(rec.diagnostics) { TranscriptLanguage.fromDiagnostics(rec.diagnostics) }
 var menu by remember(rec.id) { mutableStateOf(false) }
 var confirm by remember(rec.id) { mutableStateOf<LanguageMode?>(null) }
 Box {
  AssistChip(onClick={menu=true},label={Text(TranscriptLanguage.badge(summary),style=MaterialTheme.typography.labelSmall)},
   leadingIcon={Icon(Icons.Outlined.Translate,null,Modifier.size(14.dp))},
   modifier=Modifier.heightIn(min=32.dp).testTag("transcript-language"))
  DropdownMenu(expanded=menu,onDismissRequest={menu=false}) {
   TranscriptLanguage.rerunTargets(summary).forEach { target ->
    DropdownMenuItem(text={Text(when(target) {
     LanguageMode.AUTO -> "Распознать заново · язык автоматически"
     LanguageMode.RU -> "Распознать заново как русский"
     LanguageMode.EN -> "Распознать заново как English"
    })},onClick={menu=false;confirm=target},modifier=Modifier.testTag("rerun-language-"+target.wireId))
   }
  }
 }
 confirm?.let { target ->
  AlertDialog(onDismissRequest={confirm=null},containerColor=SurfaceRaised,
   title={Text("Распознать заново?")},
   text={Text("Стенограмма будет создана заново (${target.label}). Ручные правки текущей версии будут заменены.",style=MaterialTheme.typography.bodyMedium)},
   confirmButton={TextButton(onClick={confirm=null;vm.process(rec.id,rec.expectedSpeakers,language=target)},modifier=Modifier.testTag("rerun-language-confirm")) { Text("Распознать") }},
   dismissButton={TextButton(onClick={confirm=null}) { Text("Отмена") }})
 }
}
