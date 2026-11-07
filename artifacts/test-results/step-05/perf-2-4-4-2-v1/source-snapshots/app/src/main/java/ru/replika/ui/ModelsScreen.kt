@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package ru.replika.ui

import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import ru.replika.BuildConfig
import ru.replika.ReplikaApp
import ru.replika.data.Recording
import java.io.File

@Composable fun ModelsScreen(vm: AppViewModel,records: List<Recording>) {
 val context=LocalContext.current
 val restoreBundled: ()->Unit = { (context.applicationContext as ReplikaApp).bundledModels.start(forceCheck=true) }
 val backend by vm.backend.collectAsStateWithLifecycle();val models by vm.models.collectAsStateWithLifecycle();val progress by vm.modelProgress.collectAsStateWithLifecycle();val technicalError by vm.technicalError.collectAsStateWithLifecycle()
 val pack=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { it?.let(vm::importPack) }
 var download by remember { mutableStateOf<String?>(null) };var delete by remember { mutableStateOf<String?>(null) };var details by remember { mutableStateOf(false) };var pickDiagnostic by remember { mutableStateOf(false) };var diagnosticId by remember { mutableStateOf<String?>(null) };var benchmark by remember { mutableStateOf(false) }
 var advancedModels by rememberSaveable { mutableStateOf(false) }
 val showModelControls=!BuildConfig.BUNDLED_MODELS || advancedModels
 val bundledReady=models.isNotEmpty() && models.all { it.installed }
 val candidates=records.filter { it.diagnostics.isNotBlank() || it.error!=null };val rec=candidates.firstOrNull { it.id==diagnosticId }?:candidates.firstOrNull();val summary=remember(rec?.diagnostics) { DiagnosticView.parse(rec?.diagnostics?:"") }
 LazyColumn(Modifier.fillMaxSize().testTag("models-list"),contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
  item { Text("Модели",style=MaterialTheme.typography.headlineLarge);Spacer(Modifier.height(6.dp));Text("Распознавание на устройстве",color=Muted,style=MaterialTheme.typography.bodyMedium) }
  if(BuildConfig.BUNDLED_MODELS) item {
   Surface(color=SurfaceRaised,shape=MaterialTheme.shapes.medium,modifier=Modifier.testTag("models-bundled-status")) {
    Row(Modifier.fillMaxWidth().padding(16.dp),horizontalArrangement=Arrangement.spacedBy(12.dp),verticalAlignment=Alignment.Top) {
     Icon(if(bundledReady) Icons.Outlined.CheckCircle else Icons.Outlined.OfflineBolt,null,tint=if(bundledReady) Mint else Muted,modifier=Modifier.size(24.dp))
     Column(verticalArrangement=Arrangement.spacedBy(6.dp)) {
      Text("Встроенный офлайн-комплект",style=MaterialTheme.typography.titleMedium)
      Text(when {
       bundledReady->"Модели проверены. Распознавание работает без интернета."
       models.isEmpty()->"Проверяем подготовленные файлы. Все необходимые модели входят в APK."
       else->"Все необходимые модели входят в APK. Текущее состояние каждого набора показано ниже."
      },style=MaterialTheme.typography.bodyMedium,color=Muted)
     }
    }
   }
  }
  item { Column(verticalArrangement=Arrangement.spacedBy(8.dp)) {
   Text("Движок распознавания",style=MaterialTheme.typography.titleMedium)
   ListItem(headlineContent={Text(backendName(backend),style=MaterialTheme.typography.titleMedium)},supportingContent={Text("Русская речь · на устройстве")},leadingContent={Icon(Icons.Outlined.OfflineBolt,null,tint=Mint)},trailingContent={Text("Активна",color=Mint,style=MaterialTheme.typography.labelMedium)},colors=ListItemDefaults.colors(containerColor=SurfaceRaised),modifier=Modifier.testTag("asr-current"))
  } }
  if(BuildConfig.BUNDLED_MODELS) item {
   TextButton(onClick={advancedModels=!advancedModels},modifier=Modifier.fillMaxWidth().heightIn(min=48.dp).testTag("models-advanced-toggle")) {
    Text(if(advancedModels) "Скрыть расширенное управление" else "Расширенное управление",modifier=Modifier.weight(1f))
    Icon(if(advancedModels) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore,null)
   }
   if(advancedModels) Column(verticalArrangement=Arrangement.spacedBy(8.dp)) {
    Text("Дополнительно: ручной импорт ZIP, восстановление из APK и удаление моделей. Для готового встроенного комплекта эти действия не требуются.",style=MaterialTheme.typography.bodySmall,color=Muted)
    OutlinedButton(shape=ProductShape.control,onClick=restoreBundled,enabled=progress==null,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp).testTag("models-restore-bundled")) {
     Icon(Icons.Outlined.Restore,null);Spacer(Modifier.width(8.dp));Text("Восстановить из APK")
    }
    Text("Проверим весь встроенный комплект и восстановим недостающие или повреждённые файлы. Интернет не нужен.",style=MaterialTheme.typography.bodySmall,color=Muted)
   }
  }
  if(showModelControls) item { FilledTonalButton(shape=ProductShape.control,onClick={pack.launch(arrayOf("application/zip","application/octet-stream"))},enabled=progress==null,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)) { Icon(Icons.Outlined.FolderOpen,null);Spacer(Modifier.width(8.dp));Text("Импорт offline pack") };Spacer(Modifier.height(8.dp));Text("Для одного участника нужны GigaAM и Silero VAD. Для нескольких — также модели разделения говорящих. Файлы проверяются по SHA-256.",style=MaterialTheme.typography.bodySmall,color=Muted) }
  if(progress!=null) item { Column(Modifier.fillMaxWidth()) { LinearProgressIndicator(Modifier.fillMaxWidth());Spacer(Modifier.height(8.dp));Text(progress!!,style=MaterialTheme.typography.bodyMedium);TextButton(onClick=vm::cancelModelDownload) { Text("Отменить загрузку") } } }
  item { Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) { Text("На устройстве",style=MaterialTheme.typography.titleMedium);Text(if(models.isEmpty()) "Проверка…" else "${models.count { it.installed }} / ${models.size}",color=Muted,style=MaterialTheme.typography.labelLarge) } }
  if(models.isEmpty()) item { LinearProgressIndicator(Modifier.fillMaxWidth());Text("Проверяем файлы…",color=Muted) }
  items(models,key={it.id}) { m ->
   var menu by remember { mutableStateOf(false) }
   Surface(color=SurfaceBase,shape=MaterialTheme.shapes.medium) { Column(Modifier.fillMaxWidth().padding(start=16.dp,end=8.dp,top=12.dp,bottom=12.dp)) {
    Row(verticalAlignment=Alignment.Top) {
     Icon(if(m.installed) Icons.Outlined.CheckCircle else Icons.Outlined.Download,null,tint=if(m.installed) Mint else Muted,modifier=Modifier.padding(top=3.dp).size(20.dp));Spacer(Modifier.width(10.dp))
     Column(Modifier.weight(1f)) { Text(when(m.id) { "giga-v2"->"GigaAM v2";"giga-v3"->"GigaAM v3";"diar"->"Разделение говорящих";"vad"->"Silero VAD";else->m.title },style=MaterialTheme.typography.titleMedium)
      if(showModelControls) { Spacer(Modifier.height(4.dp));Text("${formatBytes(m.bytes)} / ${formatBytes(m.expected)}",style=MaterialTheme.typography.bodySmall,color=Muted) }
      Spacer(Modifier.height(4.dp));Text(if(m.installed) if(showModelControls) "SHA-256 проверен" else "Готова" else if(m.bytes>0) "Нужна проверка файлов" else "Не установлен",style=MaterialTheme.typography.labelMedium,color=if(m.installed) Mint else Muted)
     }
     if(showModelControls) Box { IconButton(onClick={menu=true},enabled=progress==null,modifier=Modifier.size(48.dp)) { Icon(Icons.Outlined.MoreVert,"Управление моделью ${m.id}",tint=Muted) }
      DropdownMenu(expanded=menu,onDismissRequest={menu=false}) {
       DropdownMenuItem(text={Text(if(BuildConfig.BUNDLED_MODELS) "Проверить / восстановить из APK" else if(m.installed) "Проверить / восстановить" else "Загрузить")},onClick={menu=false;if(BuildConfig.BUNDLED_MODELS) restoreBundled() else download=m.id})
       if(m.bytes>0) DropdownMenuItem(text={Text("Удалить модель")},onClick={menu=false;delete=m.id})
      }
     }
    }
   } }
  }
  item { HorizontalDivider(color=SurfaceLine);Spacer(Modifier.height(20.dp));Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.SpaceBetween) { Text("Диагностика",style=MaterialTheme.typography.titleLarge);if(candidates.size>1) TextButton(onClick={pickDiagnostic=true}) { Text("Выбрать запись") } }
   if(rec==null) { Spacer(Modifier.height(8.dp));Text("После обработки здесь появятся время, скорость и память. Без эталона качество не измеряется.",color=Muted) }
   else { Spacer(Modifier.height(8.dp));Text(rec.title,style=MaterialTheme.typography.titleMedium);Text(backendName(rec.backend),color=Muted,style=MaterialTheme.typography.bodySmall);Spacer(Modifier.height(12.dp))
    if(rec.error!=null) { Text(vm.errorMessage("Обработка",rec.error),color=MaterialTheme.colorScheme.error);Spacer(Modifier.height(8.dp)) }
    if(summary.data!=null) {
     Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(12.dp)) { MetricCell("Аудио",summary.audioMs?.let { audioClock(it) }?:"—",Modifier.weight(1f));MetricCell("Обработка",formatElapsed(summary.totalMs),Modifier.weight(1f)) }
     Spacer(Modifier.height(12.dp));Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(12.dp)) { MetricCell("Скорость · RTF",summary.rtf,Modifier.weight(1f));MetricCell("Память · PSS",summary.memory,Modifier.weight(1f)) }
     Spacer(Modifier.height(12.dp));Text("Время ML-этапов без экспорта. Память — снимок процесса, не пик. Качество ASR без эталона не измерено.",style=MaterialTheme.typography.bodySmall,color=Muted)
    }
    TextButton(onClick={details=true},modifier=Modifier.testTag("diagnostics-details")) { Text("Технические данные");Spacer(Modifier.width(6.dp));Icon(Icons.Outlined.ChevronRight,null) }
   }
   if(technicalError!=null && rec==null) TextButton(onClick={details=true}) { Text("Технические данные ошибки") }
  }
  item { TextButton(onClick={benchmark=!benchmark}) { Icon(Icons.Outlined.Science,null,Modifier.size(20.dp));Spacer(Modifier.width(8.dp));Text("Оценка по эталону") };if(benchmark) BenchmarkPanel(vm,records) }
 }
 if(download!=null) AlertDialog(onDismissRequest={download=null},title={Text("Проверить и загрузить файлы?")},text={Text("Проверенные файлы останутся на месте. Недостающие модели загрузятся из указанных источников. Потребуются трафик и свободное место. Аудио не передаётся.")},confirmButton={TextButton(onClick={vm.download(download!!);download=null}) { Text("Продолжить") }},dismissButton={TextButton(onClick={download=null}) { Text("Отмена") }})
 if(delete!=null) AlertDialog(onDismissRequest={delete=null},title={Text("Удалить модель?")},text={Text(if(BuildConfig.BUNDLED_MODELS) "Записи и стенограммы сохранятся. Для нового распознавания удалённый набор понадобится снова. Вернуть встроенный комплект можно кнопкой «Восстановить из APK», без интернета." else "Записи и стенограммы сохранятся. Для нового распознавания этот набор придётся установить снова.")},confirmButton={TextButton(onClick={vm.deleteModel(delete!!);delete=null}) { Text("Удалить",color=MaterialTheme.colorScheme.error) }},dismissButton={TextButton(onClick={delete=null}) { Text("Отмена") }})
 if(pickDiagnostic) ModalBottomSheet(onDismissRequest={pickDiagnostic=false},sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),containerColor=SurfaceRaised) {
  DarkSheetSystemBars()
  Text("Диагностика записи",style=MaterialTheme.typography.titleLarge,modifier=Modifier.padding(20.dp))
  LazyColumn(Modifier.fillMaxWidth().heightIn(max=440.dp),contentPadding=PaddingValues(bottom=24.dp)) { items(candidates,key={it.id}) { r -> ListItem(headlineContent={Text(r.title)},supportingContent={Text(backendName(r.backend))},trailingContent={if(rec?.id==r.id) Icon(Icons.Outlined.Check,null,tint=Mint)},colors=ListItemDefaults.colors(containerColor=SurfaceRaised),modifier=Modifier.clickable { diagnosticId=r.id;pickDiagnostic=false }) } }
 }
 if(details) TechnicalDetails(vm,rec,technicalError) { details=false }
}
@Composable private fun MetricCell(label: String,value: String,modifier: Modifier) { Column(modifier) { Text(label,color=Muted,style=MaterialTheme.typography.labelMedium);Spacer(Modifier.height(4.dp));Text(value,style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Medium) } }
@Composable private fun TechnicalDetails(vm: AppViewModel,rec: Recording?,technicalError: String?,onDismiss: ()->Unit) {
 val context=LocalContext.current;val scope=rememberCoroutineScope()
 val json=remember(rec?.id,rec?.title,rec?.diagnostics,rec?.error,technicalError) { JSONObject().put("recordingId",rec?.id?:JSONObject.NULL).put("title",rec?.title?:JSONObject.NULL).put("diagnostics",runCatching { JSONObject(rec?.diagnostics?:"") }.getOrDefault(JSONObject())).put("originalError",rec?.error?:JSONObject.NULL).put("latestUiError",technicalError?:JSONObject.NULL).toString(2) }
 ModalBottomSheet(onDismissRequest=onDismiss,sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),containerColor=SurfaceRaised) {
  DarkSheetSystemBars()
  Column(Modifier.fillMaxWidth().fillMaxHeight(.9f).padding(horizontal=20.dp)) {
   Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) { Text("Технические данные",style=MaterialTheme.typography.titleLarge,modifier=Modifier.weight(1f));IconButton(onClick=onDismiss) { Icon(Icons.Outlined.Close,"Закрыть диагностику") } }
   Text("Подробный JSON для проверки и отчёта",color=Muted,style=MaterialTheme.typography.bodySmall)
   SelectionContainer(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(vertical=16.dp).testTag("diagnostics-json")) { Text(json,fontFamily=FontFamily.Monospace,style=MaterialTheme.typography.bodySmall) }
   Button(shape=ProductShape.control,onClick={scope.launch { try {
    val file=withContext(Dispatchers.IO) { File(context.cacheDir,"exports").apply { mkdirs() }.let { File(it,"diagnostics-${rec?.id?:"error"}.json").apply { writeText(json) } } }
    val uri=FileProvider.getUriForFile(context,"${context.packageName}.files",file)
    context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("application/json").putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),"Передать диагностику"))
   } catch(e: Exception) { vm.reportError("Экспорт диагностики",e) } }},modifier=Modifier.fillMaxWidth().padding(bottom=16.dp).heightIn(min=50.dp)) { Text("Поделиться JSON") }
  }
 }
}
