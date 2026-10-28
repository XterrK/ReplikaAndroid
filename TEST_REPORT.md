# Отчёт о проверках REPLIKA

Дата: 28.10.2026. Результаты компиляции, Linux ML, эмулятора и физического Android учитываются отдельно. Этот файл обновляется по фактическим прогонам, а не по наличию реализации.

## Подтверждено

| Проверка | Результат | Доказательство |
|---|---|---|
| Android debug APK, arm64-v8a + x86_64 | Сборка успешна | app/build/outputs/apk/debug/app-debug.apk; лог full-build.log / final-build.log в F:\ReplikaToolchain |
| whisper.cpp JNI для обеих ABI | Компиляция и линковка успешны, native -O2 | app/build/intermediates/cxx/Debug/*/obj; CMake log |
| JVM unit tests | 13 tests, 0 failures, 0 errors, 0 skipped | docs/test-evidence/jvm-domain-tests.xml |
| Kotlin/Compose/Room generated code | Компиляция успешна | Gradle build logs |
| Android test APK | Собран | app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk |
| GigaAM v2 INT8 на Linux x86_64 | Настоящий ASR успешно распознал русский официальный WAV | docs/host-smoke.json |
| Pyannote + 3D-Speaker на Linux | Настоящая диаризация 56.86 s WAV, четыре ID при numClusters=4 | docs/host-smoke.json |
| Точность WER/CER/DER | N/A — эталон не предоставлен | Не подменяется распознанным текстом |
| Физический Android через ADB | Устройство не найдено в Linux и Windows ADB | Проверка devices -l |

Последняя успешная полная сборка предшествовала нескольким небольшим исправлениям навигации/уведомлений и добавлению лицензий. Финальная сборка актуального дерева выполняется повторно после перезапуска окружения. Не следует считать незавершённую сборку подтверждением актуального APK.

## Состав JVM tests

Объединение пересекающихся и соседних интервалов; стабильность speaker ID; сохранение неизвестного ID; честное назначение неизвестного участника при overlap; отсутствие пересекающихся ASR-чанков; вычисляемые предупреждения коротких интервалов; round-trip ручной коррекции; TXT/SRT/JSON с точными миллисекундами и без фиктивного confidence; WER/CER без эталона; нормализация ё/пунктуации; DER с оптимальной перестановкой, пересечениями, miss, false alarm и confusion; anti-alias фильтр сохраняет 1 kHz и подавляет 12 kHz при переходе 48→16 kHz.

## Android tests: реализация и способ запуска

`StorageAudioTest` проверяет Room после закрытия/открытия, сохранность сегментов при переименовании записи, исправления текста/говорящего, повреждённый импорт, стерео WAV 48→16 kHz без дрейфа длительности и opt-in реальный ASR.

`PipelineTest` выполняет полный Worker с настоящими моделями и отдельно Whisper; нужны файлы из tools/stage_android.py. Без них тесты пропускаются через Assume, что не считается успешным ML-прогоном.

`NavigationTest` проверяет переход Library→Models→Library. `ReviewScreenshotsTest` снимает реальные Android screenshots и открывает запись, созданную настоящим pipeline. Он не создаёт демонстрационную стенограмму.

```bash
source tools/env.sh
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest
bash tools/android_smoke.sh
adb shell am instrument -w -e class ru.replika.ReviewScreenshotsTest \
  ru.replika.offline.test/androidx.test.runner.AndroidJUnitRunner
```

На момент этого промежуточного отчёта Android execution ещё не подтверждён. Эмулятор Android 15/API 35 x86_64 запущен без KVM. Он дошёл до ADB и System Server, но Package Manager ещё не был готов: установка ответила `Can't find service: package`. После перезапуска WSL эмулятор запускается с сохранённым диском. Это блокировка тестовой среды, не пройденный тест приложения.

## Ограничения проверок

Нет подтверждённой проверки на arm64-телефоне, Android 14/16, часовом диалоге, низкой памяти, перегреве, реальном микрофоне телефона и авиарежиме. UI tests и screenshots нельзя считать пройденными только потому, что test APK скомпилирован. Код отмены тяжёлого JNI имеет документированные задержки. Benchmark DER пока не сверен с md-eval/pyannote.metrics на внешнем размеченном корпусе.
