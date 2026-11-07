# Инструкция по запуску и сборке проекта

> Исходный код лежит не в этой папке, а в корне репозитория: Android-модуль — в
> [`app/`](../app), скрипты — в [`tools/`](../tools). Мы не переносили код в `src/`,
> чтобы не ломать проверенную сборку Gradle. Соответствие папок шаблону — в
> [корневом README](../README.md#соответствие-шаблону-сдачи).

Если нужно просто установить приложение, сборка не нужна — возьмите готовый APK
(см. [README](../README.md#установка)).

## Что нужно

| Компонент | Версия |
| --- | --- |
| JDK | 17 |
| Android SDK | platform 35, Build Tools 35.0.0, platform-tools |
| Android NDK | 27.2.12479018 (используется для strip нативных библиотек) |
| Python | 3.12 или новее, без сторонних пакетов |
| Gradle | 8.13 — скачивается wrapper'ом автоматически |
| Место на диске | ≈ 3 ГБ: модели, кэш Gradle, APK |

Установка SDK-компонентов:

```text
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0" "ndk;27.2.12479018"
sdkmanager --licenses
```

## Шаг 1. Переменные окружения

Задайте две переменные. Остальные необязательны — их список в
[config/example.env](../config/example.env).

```bash
# Linux / macOS
export JAVA_HOME=/path/to/jdk-17
export ANDROID_HOME=/path/to/Android/Sdk
```

```powershell
# Windows PowerShell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17"
$env:ANDROID_HOME = "C:\Android\Sdk"
```

Вместо `ANDROID_HOME` можно указать `sdk.dir` в `local.properties`
(на Windows — прямые слэши: `sdk.dir=C:/Android/Sdk`). Если заданы оба
и они различаются, сборка остановится с понятной ошибкой.

## Шаг 2. Нативные библиотеки и модели

Веса моделей, нативные `.so` и ключ подписи **не хранятся в Git**: они большие,
а ключ приватный. Их нужно положить в рабочую копию.

### Нативные библиотеки sherpa-onnx 2.0.1

Нужны четыре файла:

```text
app/src/main/jniLibs/arm64-v8a/libonnxruntime.so
app/src/main/jniLibs/arm64-v8a/libsherpa-onnx-jni.so
app/src/main/jniLibs/x86_64/libonnxruntime.so
app/src/main/jniLibs/x86_64/libsherpa-onnx-jni.so
```

Их источник — архив [sherpa-onnx-v2.0.1-android.tar.bz2](https://github.com/k2-fsa/sherpa-onnx/releases/download/v2.0.1/sherpa-onnx-v2.0.1-android.tar.bz2).
SHA-256 архива закреплён в [tools/native-lock.json](../tools/native-lock.json).
Скрипт `tools/prepare_runtime.py` скачивает и раскладывает их, но использует кэш
по пути исходной машины (`/mnt/f/ReplikaToolchain`). На другой машине проще
распаковать архив вручную и скопировать четыре файла из папок `arm64-v8a` и `x86_64`.

### Модели

Семь файлов, 278 127 730 байт. Ссылки и SHA-256 — в
[app/src/main/assets/models-lock.json](../app/src/main/assets/models-lock.json).
Скрипт скачивает их с GitHub и Hugging Face, проверяет хеши и собирает ZIP для
сборки All-in-One:

```bash
python3 tools/prepare_models.py --cache local-dev/model-downloads
```

Результат:

```text
model-pack/giga-v3/   model-pack/vad/   model-pack/diar/
model-pack/replika-offline-pack-v1.5.zip   (278 569 170 байт)
```

Аргумент `--cache` обязателен на новой машине: значение по умолчанию указывает
на путь исходной машины.

Проверка, что всё на месте (только чтение):

```bash
python3 tools/verify_workspace.py --pack model-pack/replika-offline-pack-v1.5.zip
```

### Ключ подписи

Ключ `local-dev/debug.keystore` приватный и в репозиторий не входит.
Он нужен только для того, чтобы новый APK устанавливался **поверх** наших
предыдущих сборок без потери записей.

Без ключа соберите APK с новым отладочным ключом:

```bash
python3 tools/build_portable.py --allow-new-debug-key :app:assembleAllInOne
```

Такой APK нельзя поставить поверх нашего опубликованного — сначала удалите
старую версию приложения.

## Шаг 3. Сборка

На Windows используйте `python` вместо `python3`.

```bash
# Проверка окружения без запуска Gradle
python3 tools/build_portable.py --check :app:assembleAllInOne

# APK для телефона со всеми моделями внутри (основной вариант)
python3 tools/build_portable.py :app:assembleAllInOne

# Обычный debug APK без моделей + JVM-тесты + тестовый APK
python3 tools/build_portable.py
```

Готовый APK: `app/build/outputs/apk/allInOne/app-allInOne.apk`.

`build_portable.py` сам находит JDK и SDK, проверяет версии, нативные библиотеки,
модели и ключ, затем запускает Gradle wrapper. Он ничего не скачивает и не удаляет.
Подробности переноса на другую машину — в [PORTABILITY.md](../PORTABILITY.md).

## Варианты конвейера

По умолчанию собирается текущий конвейер, который описан в документации
и измерен в [TEST_RESULTS.md](../docs/TEST_RESULTS.md). Его составляют три профиля:

| Свойство Gradle | По умолчанию | Что делает | Значение V1.6 |
| --- | --- | --- | --- |
| `replikaAsrPlan` | `vad_words_context600` | Распознавание по фрагментам речи с 600 мс контекста, слова с временем | `v16` |
| `replikaDiarPlan` | `eres2net_window_v1` | Уточнение говорящих кластеризацией окон 1,5 с | `v16` |
| `replikaCpuPlan` | `auto_v1` | Число потоков по числу ядер: 1, 2 или 4 | `v16` |

Собрать прежний конвейер V1.6:

```bash
python3 tools/build_portable.py :app:assembleAllInOne \
  -PreplikaAsrPlan=v16 -PreplikaDiarPlan=v16 -PreplikaCpuPlan=v16
```

`eres2net_window_v1` работает только вместе с `vad_words_context600`;
другие сочетания сборка отклонит.

Дополнительные свойства для тестирования:

| Свойство | Назначение |
| --- | --- |
| `replikaTestBuildType=allInOneQa` | Тестовый APK для варианта `allInOneQa` (эмулятор x86_64) |
| `replikaAioQaSameId=true` | Убирает суффикс `.aioqa` у тестового варианта — только для проверки обновления |
| `replikaPython` | Путь к Python для подготовки моделей; `build_portable.py` передаёт его сам |

## Тесты

```bash
# JVM-тесты (входят в сборку по умолчанию)
python3 tools/build_portable.py :app:testDebugUnitTest

# UI-тесты на явно выбранном эмуляторе
python3 tools/run_ui_v16.py --help
```

Стенд оценки качества (WER, DER, RTF) на ПК описан в
[tools/eval/README.md](../tools/eval/README.md). Он требует отдельного Python-окружения
и скачивает тестовый корпус с Hugging Face.

## Установка собранного APK

```bash
adb install -r app/build/outputs/apk/allInOne/app-allInOne.apk
```

Флаг `-r` обновляет приложение, сохраняя записи. Если подпись отличается,
`adb` откажет — тогда сначала `adb uninstall ru.replika.offline`
(это удалит записи на устройстве).
