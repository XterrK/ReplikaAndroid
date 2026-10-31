# Текущее состояние REPLIKA

Исследовательское Android-приложение с настоящим локальным ML-кодом. Это не макет UI и не имитация распознавания. Но наличие native-кода и APK не равно подтверждённому end-to-end результату на телефоне. Подробности — в TEST_REPORT.md.

Проект: `F:\Hackathons\ReplikaAndroid` (`/mnt/f/Hackathons/ReplikaAndroid`). Инструменты и веса находятся на F:, исходные пользовательские файлы не удалялись. Создан отдельный Git; push и публикация не выполнялись.

## Матрица готовности

Статус WORKING применяется только к той среде, которая названа в строке. PARTIAL означает реализацию с неполной Android-проверкой или известным функциональным ограничением.

| Функция | Статус | Подтверждение / ограничение |
|---|---|---|
| Android debug build | WORKING | APK собран для arm64/x86_64; актуальное дерево повторно собирается после перезапуска |
| Доменная логика на JVM | WORKING | 13 тестов прошли |
| Основной ASR на Linux | WORKING | Реальный GigaAM v2 INT8, официальный русский WAV |
| Диаризация на Linux | WORKING | Pyannote + 3D-Speaker, официальный многоголосный WAV; задано 4 участника |
| GigaAM ASR на Android | PARTIAL | JNI интегрирован, on-device прогон ещё не подтверждён |
| Диаризация на Android | PARTIAL | Официальная поддерживаемая конфигурация; тест не завершён |
| Полный Android pipeline | PARTIAL | Реализован Worker, требуется успешный Android execution |
| Silero VAD | PARTIAL | Настоящий sherpa VAD интегрирован; Android прогон ожидается |
| Whisper tiny / whisper.cpp | PARTIAL | JNI собран для обеих ABI; реальный Android inference не подтверждён |
| Явный выбор ASR | PARTIAL | Backend сохраняется в настройках/записи и экспорте; Android UI ещё не проверен |
| Импорт WAV/MP3/M4A | PARTIAL | SAF + MediaExtractor/MediaCodec; обработка ошибок и тесты реализованы |
| Запись / пауза / уровень / таймер | PARTIAL | MediaRecorder, разрешение, пауза при уходе в фон; физический микрофон не проверен |
| PCM normalization / stereo / resampling | PARTIAL | 63-tap FIR и PTS, unit test фильтра прошёл; MediaCodec test ждёт Android |
| Temporal alignment | WORKING на JVM | Непересекающиеся реальные интервалы, повторное ASR по границам; нет выдуманных word timestamps |
| Smart Review heuristics | WORKING на JVM | Unknown, overlap, короткие интервалы, разрез длинной реплики; без процентов confidence |
| Smart Review UI и исправления | PARTIAL | Реализованы, Android UI ещё не подтверждён |
| Room / история / редактирование | PARTIAL | DAO, транзакции, Flow, Upsert; Android storage tests ещё не выполнены |
| Library / поиск | PARTIAL | Названия + поиск по тексту; нет визуального smoke test |
| Processing / foreground / отмена | PARTIAL | WorkManager dataSync, отдельные jobs и общий mutex; отмена ждёт native вызов |
| Waveform / speaker timeline | PARTIAL | Настоящие PCM peaks и интервалы; визуальный Android test ожидается |
| Media3 / seek / скорость / синхронизация | PARTIAL | Реализовано; физическое воспроизведение не подтверждено |
| Переименование и фильтр говорящего | PARTIAL | Room + Compose; Android UI test ожидается |
| TXT / SRT / JSON generation | WORKING на JVM | Время/имена/исправления проверены тестами |
| Android Share | PARTIAL | FileProvider / ACTION_SEND; внешний receiver не проверен |
| Model download / resume / delete | PARTIAL | HTTPS, Range, .part, проверка SHA-256; прерванная загрузка на Android не проверена |
| Offline pack | PARTIAL | Настоящий ZIP подготовлен с лицензиями и весами; Android SAF import ещё не пройден |
| Benchmark WER/CER/DER | WORKING на JVM | Алгоритмы протестированы; точность моделей N/A |
| Benchmark import/comparison UI | PARTIAL | JSON import и локальное сохранение реализованы; Android execution ожидается |
| Реальные Android RTF / peak RAM | BLOCKED | Нет завершённого Android прогона; peak RAM не инструментирован |
| Human Review screenshots | BLOCKED | Эмулятор ещё не готов к запуску приложения; нарисованных screenshots нет |
| Полная проверка на arm64-телефоне | BLOCKED | Физическое устройство не подключено |
| Мгновенное прерывание JNI | NOT IMPLEMENTED | Требует upstream abort API или отдельного процесса |
| Word-level timestamps | NOT IMPLEMENTED | Приложение честно использует segment timestamps |
| Разделение одновременных слов | NOT IMPLEMENTED | Пересечение помечается как неоднозначное |

## Файлы для установки

`app/build/outputs/apk/debug/app-debug.apk` — debug APK. `model-pack/replika-offline-pack.zip` — локальный pack всех установленных весов, без включения их в APK. Runtime и модели намеренно не коммитятся как огромные бинарники; восстановление через tools/prepare_runtime.py и tools/prepare_models.py.

## Приоритет следующей проверки

Завершить актуальную сборку, установить на готовый API 35 emulator, выполнить storage/navigation/real ML tests, собрать screenshots и обновить эту матрицу. Затем проверить тот же offline pack и русский диалог с несколькими участниками на arm64-телефоне в авиарежиме. Измерить качество на размеченном согласованном корпусе и проверить немедленную отмену через изоляцию ML-процесса.
