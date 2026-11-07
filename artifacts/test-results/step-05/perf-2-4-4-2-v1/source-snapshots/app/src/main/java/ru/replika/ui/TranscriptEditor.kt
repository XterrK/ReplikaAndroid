@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class,androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package ru.replika.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import ru.replika.data.SegmentRow
import ru.replika.domain.Exporter

data class SpeakerChoice(val id: Int,val name: String)

@Composable fun SpeakerPickerDialog(
 choices: List<SpeakerChoice>,selected: Int?,allowAll: Boolean=false,
 onChoose: (Int?)->Unit,onDismiss: ()->Unit,onCreate: (() -> Unit)?=null
) {
 var query by rememberSaveable { mutableStateOf("") }
 val focus=LocalFocusManager.current
 val keyboard=LocalSoftwareKeyboardController.current
 val imeVisible=WindowInsets.isImeVisible
 val shown=remember(choices,query) { choices.filter { query.isBlank() || it.name.contains(query.trim(),ignoreCase=true) || (it.id+1).toString()==query.trim() } }
 fun choose(id: Int?) { focus.clearFocus();keyboard?.hide();onChoose(id) }
 ModalBottomSheet(
  onDismissRequest=onDismiss,containerColor=SurfaceRaised,
  sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),modifier=Modifier.fillMaxHeight().testTag("speaker-picker")
 ) {
  DarkSheetSystemBars()
  Column(Modifier.fillMaxSize().imePadding()) {
   Row(Modifier.fillMaxWidth().padding(start=20.dp,end=8.dp,bottom=8.dp),verticalAlignment=Alignment.CenterVertically) {
    Text("Выбрать говорящего",style=MaterialTheme.typography.titleLarge,modifier=Modifier.weight(1f))
    IconButton(onClick=onDismiss) { Icon(Icons.Outlined.Close,"Закрыть выбор говорящего") }
   }
   OutlinedTextField(query,{query=it},Modifier.fillMaxWidth().padding(horizontal=20.dp).testTag("speaker-search"),label={Text("Поиск участника")},singleLine=true,leadingIcon={Icon(Icons.Outlined.Search,null)})
   Spacer(Modifier.height(8.dp))
   LazyColumn(Modifier.fillMaxWidth().weight(1f).padding(horizontal=20.dp).testTag("speaker-options"),verticalArrangement=Arrangement.spacedBy(2.dp),contentPadding=PaddingValues(vertical=4.dp)) {
    if(allowAll && query.isBlank()) item { SpeakerOption(null,"Все участники",selected==null) { choose(null) } }
    items(shown,key={it.id}) { choice -> SpeakerOption(choice.id,choice.name,selected==choice.id) { choose(choice.id) } }
    if(shown.isEmpty()) item { Text("Нет совпадений. Измените запрос.",color=Muted,modifier=Modifier.padding(vertical=16.dp)) }
   }
   if(onCreate!=null && (!imeVisible || shown.isEmpty())) TextButton(onClick={focus.clearFocus();keyboard?.hide();onCreate()},modifier=Modifier.fillMaxWidth().heightIn(min=48.dp).testTag("speaker-add")) {
    Icon(Icons.Outlined.Add,null,Modifier.size(20.dp));Spacer(Modifier.width(8.dp));Text("Добавить участника")
   }
   if(!imeVisible) Text("Подпись задаётся вручную. Это не определение личности по голосу.",style=MaterialTheme.typography.bodySmall,color=Muted,modifier=Modifier.padding(horizontal=20.dp,vertical=12.dp))
  }
 }
}

@Composable private fun SpeakerOption(id: Int?,name: String,selected: Boolean,onClick: ()->Unit) {
 Row(
  Modifier.fillMaxWidth().heightIn(min=56.dp).selectable(selected,role=Role.RadioButton,onClick=onClick).padding(vertical=8.dp).testTag("speaker-option-"+(id?.toString()?:"all")),
  verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(10.dp)
 ) {
  if(id==null) Icon(Icons.Outlined.Groups,null,Modifier.size(26.dp),tint=Muted) else SpeakerAvatar(id)
  Column(Modifier.weight(1f)) {
   Text(name,style=MaterialTheme.typography.bodyMedium,fontWeight=if(selected) FontWeight.SemiBold else FontWeight.Normal)
   if(id!=null && id>=0 && name!="Участник "+(id+1)) Text("Участник "+(id+1),style=MaterialTheme.typography.labelSmall,color=Muted)
  }
  RadioButton(selected,onClick=null)
 }
}

@Composable fun TranscriptEditor(
 vm: AppViewModel,row: SegmentRow,choices: List<SpeakerChoice>,
 onListen: ()->Unit,onPause: ()->Unit,playing: Boolean,onDismiss: ()->Unit
) {
 var text by rememberSaveable(row.id) { mutableStateOf(row.text) }
 var speaker by rememberSaveable(row.id) { mutableIntStateOf(row.speakerId) }
 var reviewed by rememberSaveable(row.id) { mutableStateOf(row.reviewed) }
 var saving by remember(row.id) { mutableStateOf(false) }
 var picking by rememberSaveable(row.id) { mutableStateOf(false) }
 var discard by rememberSaveable(row.id) { mutableStateOf(false) }
 var addedIds by rememberSaveable(row.id) { mutableStateOf(emptyList<Int>()) }
 val focus=LocalFocusManager.current
 val keyboard=LocalSoftwareKeyboardController.current
 val dirty=text!=row.text || speaker!=row.speakerId || reviewed!=row.reviewed
 val dirtyNow by rememberUpdatedState(dirty)
 val sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true,confirmValueChange={ target ->
  if(target==SheetValue.Hidden && (dirtyNow || saving)) { if(!saving) discard=true;false } else true
 })
 val allChoices=(choices+addedIds.map { SpeakerChoice(it,"Участник "+(it+1)) }).distinctBy { it.id }
 val selectedName=allChoices.firstOrNull { it.id==speaker }?.name?:if(speaker<0) "Неизвестный" else "Участник "+(speaker+1)
 fun close() { if(!saving) { focus.clearFocus();keyboard?.hide();if(dirty) discard=true else onDismiss() } }
 ModalBottomSheet(
  onDismissRequest={close()},sheetState=sheetState,
  containerColor=SurfaceBase,modifier=Modifier.fillMaxHeight().testTag("transcript-editor")
 ) {
  DarkSheetSystemBars()
  val keyboardVisible=WindowInsets.isImeVisible
  Column(Modifier.fillMaxWidth().imePadding()) {
   Row(Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=if(keyboardVisible) 4.dp else 8.dp),verticalAlignment=Alignment.CenterVertically) {
    Column(Modifier.weight(1f)) {
     Text(if(keyboardVisible) "Редактор" else "Проверить фрагмент",style=if(keyboardVisible) MaterialTheme.typography.titleMedium else MaterialTheme.typography.titleLarge)
     Text(Exporter.stamp(row.startMs)+" — "+Exporter.stamp(row.endMs),style=MaterialTheme.typography.bodySmall,color=Muted)
    }
    if(keyboardVisible) IconButton(onClick=if(playing) onPause else onListen,modifier=Modifier.testTag("editor-listen")) { Icon(if(playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,if(playing) "Пауза оригинала" else "Прослушать участок") }
    IconButton(onClick={close()},enabled=!saving) { Icon(Icons.Outlined.Close,"Закрыть редактор") }
   }
   Column(
    Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal=20.dp),
    verticalArrangement=Arrangement.spacedBy(12.dp)
   ) {
    val issues=remember(row.reasons,row.speakerId,row.startMs,row.endMs) { reviewIssues(row) }
    if(!keyboardVisible && issues.isNotEmpty()) Column(Modifier.fillMaxWidth().background(SurfaceRaised,ProductShape.control).padding(12.dp),verticalArrangement=Arrangement.spacedBy(6.dp)) {
     issues.forEach { issue -> Text(issue.title,style=MaterialTheme.typography.labelMedium,color=Amber);Text(issue.explanation,style=MaterialTheme.typography.bodySmall,color=Muted) }
    }
    if(!keyboardVisible) OutlinedButton(shape=ProductShape.control,onClick=if(playing) onPause else onListen,modifier=Modifier.heightIn(min=48.dp).testTag("editor-listen")) {
     Icon(if(playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,null,Modifier.size(20.dp));Spacer(Modifier.width(6.dp));Text(if(playing) "Пауза" else "Прослушать участок")
    }
    OutlinedTextField(
     text,{text=it},modifier=Modifier.fillMaxWidth().testTag("editor-text").semantics { contentDescription="Текст реплики" },enabled=!saving,
     label={if(!keyboardVisible) Text("Текст реплики")},minLines=if(keyboardVisible) 2 else 3,maxLines=if(keyboardVisible) 5 else 9,
     supportingText={if(!keyboardVisible) Text(if(dirty) "Изменения ещё не сохранены" else "Сохранённый текст",style=MaterialTheme.typography.bodySmall)}
    )
    if(!keyboardVisible) Column(verticalArrangement=Arrangement.spacedBy(6.dp)) {
     Text("Говорящий",style=MaterialTheme.typography.labelMedium,color=Muted)
     Row(
      Modifier.fillMaxWidth().background(SurfaceRaised,ProductShape.control).clickable(enabled=!saving) { focus.clearFocus();keyboard?.hide();picking=true }.padding(12.dp).testTag("editor-speaker"),
      verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(10.dp)
     ) {
      SpeakerAvatar(speaker)
      Text(selectedName,style=MaterialTheme.typography.bodyLarge,modifier=Modifier.weight(1f))
      Icon(Icons.Outlined.ExpandMore,"Выбрать говорящего",Modifier.size(20.dp),tint=Muted)
     }
    }
    if(!keyboardVisible) Row(Modifier.fillMaxWidth().heightIn(min=48.dp),verticalAlignment=Alignment.CenterVertically) {
     Checkbox(reviewed,if(saving) null else { value -> reviewed=value },modifier=Modifier.testTag("editor-reviewed"))
     Text("Фрагмент проверен",style=MaterialTheme.typography.bodyMedium)
    }
    if(!keyboardVisible) Text("Метки относятся ко всей реплике, а не к отдельным словам.",style=MaterialTheme.typography.bodySmall,color=Muted)
    Spacer(Modifier.height(8.dp))
   }
   HorizontalDivider(color=SurfaceLine)
   Column(
    Modifier.fillMaxWidth().background(SurfaceRaised).navigationBarsPadding().padding(horizontal=20.dp,vertical=if(keyboardVisible) 6.dp else 12.dp),
    verticalArrangement=Arrangement.spacedBy(8.dp)
   ) {
    Text(if(saving) "Записываем в историю…" else if(dirty) "Есть несохранённые изменения" else "Изменений нет",style=MaterialTheme.typography.labelSmall,color=if(dirty) Amber else Muted,modifier=Modifier.testTag("editor-save-state"))
    Button(shape=ProductShape.control,
     onClick={saving=true;focus.clearFocus();keyboard?.hide();vm.edit(row,text,speaker,reviewed) { ok -> saving=false;if(ok) onDismiss() }},
     enabled=!saving && dirty,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp).testTag("editor-save")
    ) { Text(if(saving) "Сохраняем…" else "Сохранить исправления") }
   }
  }
 }
 if(picking) SpeakerPickerDialog(
  allChoices,speaker,onChoose={id->if(id!=null) speaker=id;picking=false},onDismiss={picking=false},
  onCreate={
   val id=(allChoices.maxOfOrNull { it.id }?:-1)+1
   addedIds=addedIds+id;speaker=id;picking=false
  }
 )
 if(discard) AlertDialog(
  onDismissRequest={discard=false},containerColor=SurfaceRaised,title={Text("Не сохранять изменения?")},
  text={Text("Сохранённая версия останется в истории. Текущие правки будут закрыты.")},
  confirmButton={TextButton(onClick={discard=false;onDismiss()}) { Text("Не сохранять") }},
  dismissButton={TextButton(onClick={discard=false}) { Text("Продолжить редактирование") }}
 )
}
