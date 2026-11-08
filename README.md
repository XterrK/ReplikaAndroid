# REPLIKA — локальная расшифровка разговоров на Android

**[Скачать APK · релиз 1.7](https://github.com/XterrK/ReplikaAndroid/releases/tag/v1.7-hack-20261108)** ·
[Сайт проекта](https://xterrk.github.io/ReplikaAndroid/) ·
[Демо-видео · 1 мин](https://github.com/XterrK/ReplikaAndroid/releases/download/v1.7-hack-20261108/demo.mp4)

REPLIKA превращает запись разговора в текст: кто говорил, что сказал и когда.
Нативное приложение на **Kotlin / Jetpack Compose**; все модели внутри APK.
Всё считается на телефоне. Аудио никуда не отправляется, интернет не нужен.

Проект для кейса Nuclear IT Hack: Android-приложение для локальной транскрибации
и диаризации с экспортом в JSON для автоматической проверки.

Качество на нашем тестовом наборе (подробно — в [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md)):

| Метрика | V1.6 (до хакатона) | Сейчас |
| --- | ---: | ---: |
| Raw WER, dev (8 файлов), меньше — лучше | 23,26% | **13,32%** |
| DER0 диаризатора, dev, меньше — лучше | 43,16% | **18,30%** |
| Верное число говорящих, dev | 2 из 8 | **7 из 8** |
| RTF на телефоне vivo X300 (1 / 10 мин записи) | — | **0,36 / 0,74** |

WER учитывает пунктуацию и регистр. DER0 диаризатора оценивает интервалы голосов;
DER0 **итогового JSON** на dev — **21,21%** ([сводный CSV](artifacts/test-results/results.csv)).
Замеры RTF в таблице — отдельные прогоны на повторённом фрагменте; условия и более
поздние замеры итоговой сборки приведены в [отчёте](docs/TEST_RESULTS.md#скорость-на-телефоне).
Корпус маленький и смонтированный из актёрских реплик. Ограничения — в
[docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Ключевые возможности

- **Импорт** аудио (WAV, MP3, M4A/AAC, OGG/Opus, FLAC) и видео — из видео берётся звук.
- **Запись** с микрофона прямо в приложении.
- **Распознавание русской и английской речи** с пунктуацией и регистром: язык определяется автоматически, русский — GigaAM v3, английский — Parakeet TDT v2.
- **Длинные записи** (часы): говорящие определяются окнами, память не растёт с длиной; файлы до нескольких ГБ импортируются без копии.
- **Определение говорящих** автоматически (до 8) или с заданным числом (2–20).
- **Временные метки** каждой реплики; нажатие на реплику включает звук с этого места.
- **Правка** текста и говорящих, переименование участников.
- **Экспорт** в JSON по формату жюри, а также в TXT, SRT и подробный диагностический JSON.
- **Офлайн.** Все модели внутри APK, работает в режиме полёта.

## Установка

1. Откройте [GitHub Releases](https://github.com/XterrK/ReplikaAndroid/releases) репозитория.
2. Скачайте APK для телефона (arm64, ≈ 840 МБ, все модели внутри).
   Финальный релиз для сдачи — [REPLIKA 1.7 (code 9) — Nuclear IT Hack](https://github.com/XterrK/ReplikaAndroid/releases/tag/v1.7-hack-20261108)
   (тег `v1.7-hack-20261108`), файл `REPLIKA-1.7-code9-AllInOne-arm64.apk`.
3. Проверьте SHA-256 по файлу `.sha256` рядом с APK (необязательно).
4. Установите:
   - на телефоне — откройте APK и разрешите установку из этого источника;
   - через компьютер — `adb install -r <файл>.apk`.

Требования: Android 8.0 или новее, лучше arm64-телефон. При первом запуске
приложение распаковывает ≈ 1 ГБ моделей и проверяет их (на телефоне около 20 секунд) — это занимает время
один раз.

Если раньше стояла наша сборка, новая устанавливается поверх, записи сохраняются.

## Как пользоваться

1. **Импорт.** На главном экране нажмите «Импорт аудио или видео» и выберите файл
   в системном диалоге (например, в «Загрузках»). Исходный файл не меняется.
2. **Обработка запускается сама** с автоматическими настройками: число говорящих и
   язык (русский / английский) определяются автоматически. Виден прогресс и оставшееся
   время; экран можно закрыть — обработка продолжится. Параметры можно поменять потом
   кнопкой «Обработать заново».
3. **Просмотр.** Готовая стенограмма показывает реплики, говорящих и время.
   Нажатие на реплику включает звук с этого места. Текст и говорящего можно исправить.
4. **Экспорт.** Нажмите «Экспорт» → **«Сохранить JSON для жюри в файл»** и выберите
   папку (по умолчанию «Загрузки»). Это работает на любом Android, в том числе на чистом
   эмуляторе. Ниже в том же окне — «Поделиться» в форматах TXT, SRT, JSON и
   диагностический JSON.

Формат JSON для жюри:

```json
{"transcript":[{"speaker_id":"speaker_1","start_ms":1250,"end_ms":4380,"text":"Добрый день!"}]}
```

Говорящие нумеруются `speaker_1`, `speaker_2`… по порядку первого появления.
Правки, сделанные в приложении, попадают в экспорт.

## Как это устроено

```text
Аудио → PCM 16 кГц → Silero VAD (где речь)
                    → Pyannote + ERes2Net + наша кластеризация окон (кто говорит)
      → GigaAM v3 по фрагментам речи с 600 мс контекста (текст и время слов)
      → каждому слову — говорящий → реплики → JSON
```

Нативный Kotlin и Jetpack Compose, sherpa-onnx 2.0.1, все вычисления на CPU.
Подробно — в [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) и [docs/MODELS.md](docs/MODELS.md).

## Соответствие шаблону сдачи

Структура повторяет [шаблон организаторов](https://github.com/grigorevmp/hacathon_template).
Код оставлен в стандартной для Android структуре в корне: перенос в `src/` сломал бы
проверенную сборку Gradle.

| Требование | Где в репозитории |
| --- | --- |
| APK | [GitHub Releases](https://github.com/XterrK/ReplikaAndroid/releases); суммы SHA-256 — [release/SHA256SUMS](release/SHA256SUMS) |
| Исходный код | [app/](app) — Android-приложение; [tools/](tools) — сборка и стенд оценки |
| Инструкция по запуску и сборке | [src/README.md](src/README.md) |
| Пример конфигурации | [config/example.env](config/example.env) |
| Архитектура | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Модели | [docs/MODELS.md](docs/MODELS.md) |
| Ограничения | [docs/LIMITATIONS.md](docs/LIMITATIONS.md) |
| Результаты тестов | [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) |
| Сырые результаты тестов | [artifacts/test-results/](artifacts/test-results/README.md); сводка — [results.csv](artifacts/test-results/results.csv) (колонки адаптированы под наш кейс: WER, DER, RTF) |
| Видеодемонстрация | [artifacts/demo/](artifacts/demo/README.md) |
| `docs/PROTOCOL.md` из шаблона | Не нужен: относится к другому кейсу |

## Карта репозитория

| Путь | Что там |
| --- | --- |
| [app/src/main/java/ru/replika/](app/src/main/java/ru/replika) | Код приложения: `ui`, `ml`, `domain`, `data` |
| [app/src/test/](app/src/test), [app/src/androidTest/](app/src/androidTest) | JVM- и Android-тесты |
| [tools/eval/](tools/eval/README.md) | Стенд оценки WER / DER / RTF на ПК |
| [benchmark/](benchmark) | Описание тестовых корпусов и эталоны |
| [configs/eval/](configs/eval) | Зафиксированные конфигурации экспериментов |
| [docs/](docs) | Документация; отчёты по этапам `STEP_0*.md` |
| [release/](release) | Описание и суммы APK; сами APK — в Releases |
| `docs/history/`, `review/`, `archive/` | История разработки и прежние отчёты |

## Документы

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — компоненты, решения, зависимости, приватность.
- [docs/MODELS.md](docs/MODELS.md) — модели, размеры, лицензии, почему выбраны.
- [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) — методика и результаты.
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md) — условия, ограничения, риски, планы.
- [src/README.md](src/README.md) — сборка из исходников.
- Отчёты по этапам: [JSON для жюри](docs/STEP_01_JURY_JSON.md),
  [распознавание](docs/STEP_03_VAD_WORD_ASR.md), [диаризация](docs/STEP_04_DIARIZATION.md),
  [потоки, нагрев, импорт](docs/STEP_05_RUNTIME_IMPORT.md).
- Полный технический обзор: [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md).
- Прежний README версии 1.6: [docs/history/README_v1.6_codex.md](docs/history/README_v1.6_codex.md).
- Исторические отчёты и рабочие заметки разработки: [docs/history/root/](docs/history/root/README.md).

## Лицензии

Модели и библиотеки распространяются под своими лицензиями (MIT, Apache-2.0, BSD; шрифт Onest — OFL).
Список и тексты — в [app/src/main/assets/licenses/](app/src/main/assets/licenses/NOTICE.md)
и [docs/MODELS.md](docs/MODELS.md).
