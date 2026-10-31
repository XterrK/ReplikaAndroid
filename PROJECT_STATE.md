# REPLIKA V1.1 — состояние на 31.10.2026

Продукт **PARTIAL**: настоящий локальный ML и Android end-to-end подтверждены на эмуляторе, однако русский многоголосный сценарий и физический arm64 остаются BLOCKED. Исходный проект продолжен; модели и прежние незакоммиченные исправления сохранены. Push не выполнялся.

Исходный commit: `c046ed6ac75ae90f169595b3b4a2f3833702b06a`. Рабочие изменения до V1.1 сохранены коммитом `06cfba7b20d1c4067d0c9e85da38a53e050872a1`, веткой `preservation/pre-v1.1` и внешним snapshot/Git bundle с SHA-256. Текущая ветка: `validation/v1.1`. Проверенный коммит реализации: `d0ba1eb06db3d07e808237d33859b5e4e6bd35d7`; финальный commit материалов фиксируется в манифесте Review ZIP. Полные сведения — `docs/test-evidence/v1.1/preservation.json`.

## Матрица готовности

WORKING относится только к указанной среде. PARTIAL означает проверенную часть с открытыми ограничениями; наличие кода не является доказательством телефона.

| Возможность | Статус | Фактическая проверка / ограничение |
|---|---|---|
| Clean debug APK arm64 + x86_64 | WORKING | Контрольная clean-сборка: 81 задача, BUILD SUCCESSFUL; APK совпал с протестированным по SHA-256 |
| JVM/domain | WORKING | 18 tests, 0 failures/errors/skipped |
| Android API35 x86_64 | WORKING | 19 instrumentation + 2 UI + 1 отдельный process-relaunch; без пропусков |
| GigaAM, Silero, diarization, Whisper native | WORKING на API35 x86_64 | Настоящие модели и WAV; файлы результатов сохранены |
| Русский mono full Worker → Room → UI → export | WORKING на API35 x86_64 | Оба ASR backend, raw JSON до ручных исправлений, отдельный исправленный экспорт |
| Полный русский многоголосный pipeline | BLOCKED | Нет допустимого многоголосного русского исходника/reference; подготовлен протокол добровольной записи |
| Automatic/fixed speaker count | WORKING как настройка | UI 1–20, запись и диагностика; zh automatic .5/.65: 7 кластеров, fixed4: 4 |
| Качество диаризации русских голосов | PARTIAL | Независимая оценка DER отсутствует; automatic overclustering остаётся |
| VAD pre-roll и alignment | WORKING на fixture/JVM | 100 ms pre, 0 post, clamp+merge; GigaAM «ничьих» восстановлено в полном Worker, глобальное начало 31 ms |
| Качество ASR/короткие ответы/overlaps | PARTIAL | Результаты настоящие, но нет WER/CER и русского многоголосного эталона; границы говорящих и 20s чанков остаются риском |
| TXT/SRT/JSON, ручные правки | WORKING на JVM/API35 | Текст, speaker ID, имя, reviewed, Activity recreation, force-stop, свежий UI JSON export |
| Smart Review | WORKING как эвристики | Вычисляемые причины без confidence; пустая очередь не означает правильный ASR; нет полноценного русского multi UX test |
| Плеер, segment tap, seek, active row | WORKING по состоянию API35 | isPlaying/active semantics, ручные adb taps: stop около 8.485s, seek clamp 11s и возврат 1s; физический звук не проверен |
| WAV/MP3/M4A decoder | WORKING на API35 | Реальные конверсии одного WAV, длительности и PCM; Дополнительно все три формата прошли реальный AOSP Downloads picker → Worker → Room → UI → JSON; другие SAF providers и телефон не проверены |
| Повреждённый файл/ошибка Worker | WORKING на API35 | Ошибка без падения, PCM удалён, прежняя ручная стенограмма сохранена |
| Offline model pack | WORKING на API35 через ModelManager | Реальный ZIP, SHA-256 всех групп; повреждённый ZIP не заменяет проверенную модель; системный SAF picker вручную на телефоне не проверен |
| Processing, duplicate requests, queued cancel, recovery | WORKING на API35 | Уникальное задание, общий gate, CANCELLING, сохранение данных, восстановление orphaned work |
| Мгновенная отмена текущего JNI | NOT IMPLEMENTED | Отмена ждёт текущий native call; отдельная проверка длительной native отмены на телефоне не выполнена |
| Запись / pause / resume / фон | PARTIAL | Виртуальный вход AVD -no-audio; UI сценарий прошёл. Настоящий микрофон только с согласия, не проверен |
| Share, мало места, прерванная загрузка | PARTIAL | JSON chooser открыт без отправки; внешние receivers, ENOSPC и download/resume не подтверждены этой сессией |
| 16 KiB ZIP + ELF LOAD alignment | WORKING статически | Все 8 .so, обе ABI, PT_LOAD/congruence и DT_NEEDED; не доказательство исполнения |
| 16 KiB Android runtime / API36 | BLOCKED | Доступный AVD имеет страницы 4096; API36 image/SDK не установлен |
| Физический arm64 | BLOCKED | Телефон не подключён; ADB-инструкция подготовлена |
| Peak RAM sampler | NOT IMPLEMENTED | Есть PSS snapshots, не peak |
| Часовые записи и нагрев телефона | BLOCKED | Физический телефон отсутствует; native diarization требует целый PCM |
| Word timestamps / разделение одновременно произнесённых слов / voice identity | NOT IMPLEMENTED | Segment timestamps и условные ID; пересечение неоднозначно |
| Human Review | WORKING как пакет доказательств | Реальные Android screenshots, самокритика, raw ML JSON, проблемы и ручной протокол; отдельные состояния отмечены непроверенными |

## Артефакты

APK: `app/build/outputs/apk/debug/app-debug.apk`, 83157436 bytes, versionName 1.1.0 / versionCode 2.

SHA-256: `9728e09fe8f6b0d66b4c038f5a71752c21602db5c72e7013e3b80d0ea6668b6a`.

Review ZIP: `review/REPLIKA_V1_1_HUMAN_REVIEW.zip`. Его манифест фиксирует финальный Git commit и хеш каждого вложенного файла. Модели, APK, SDK и аудио в архив не входят. Модели остаются в `model-pack/`, не в Git.

Главные приоритеты перед хакатоном: русский диалог с эталоном → физический arm64 в offline → длинные записи/память/перегрев/отмена. Детали открытых UX-дефектов и ограничений находятся в `docs/human-review/v1.1/ISSUES_V1_1.md` и `UX_REVIEW_V1_1.md`.
