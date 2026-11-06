# REPLIKA V1.6 · UI / передача проекта · 06.11.2026

Цель цикла: переработать главную запись и шар, вынести голосовую волну на правую кромку без смещения центра, упростить сохранение/удаление и убрать старый таймер. Исследование и визуальный контракт: [DESIGN](docs/ui-v1.6/DESIGN.md), [концепт](docs/ui-v1.6/concept.png). Рабочее дерево предыдущего цикла сохранено; reset/clean/push/удаление app data не выполнялись.

## Реализовано

- Шар .39 размера квадратного Canvas, строго в центре. AGSL: внутренние плавные silk folds/domain warp, сферическое освещение, рефракция края, мягкие блики и перистая тень вместо жёсткой подложки. Canvas fallback использует согласованную палитру и слои света. Геометрия речи спокойнее, упругое взаимодействие сохранено.
- Правая волна — overlay 64dp × 88% высоты главной, горизонтальные штрихи из физической правой кромки, огибающая реального рекордера и её история 20Hz. Нет зарезервированной колонки и end-padding шара. Touch не попадает в amplitude. Это не FFT.
- Стрелка выхода, Android Back и «Завершить» открывают одну панель с «Сохранить запись» / «Удалить запись». Запись на время выбора ставится на паузу. Закрытие восстанавливает только ранее работающую запись; ранее поставленная вручную пауза остаётся паузой. Панель прокручивается на коротких экранах.
- До завершения старта микрофона Save отключён. Ошибка MediaRecorder больше не открывает повторный старт до окончания cleanup. При ненулевом записанном времени длительность сохраняется в Room, UI elapsed/levels очищаются; при очень ранней программной остановке доступна длительность из готового AAC. Таймер показывается только в живой сессии.
- Подготовлены portable launcher, проверка SHA моделей/native/ZIP, локальные smoke fixtures, приватный прежний ключ подписи, HANDOFF и AGENTS. Исторические APK/суммы перенесены в `release/archive/`; crash logs и прежний видеоэксперимент — в `archive/`.

## Проверки

**JVM:** 80 тестов, 0 failures/errors/skips. [XML](docs/ui-v1.6/tests/jvm/), [итоговая сборка](docs/ui-v1.6/tests/final-build.log), [сборка тестового APK](docs/ui-v1.6/tests/test-build.log). Debug и arm64 All-in-One собраны из актуального source. Предупреждения устаревших Compose API остались; compile/test ошибок в финальных сборках нет.

**Android UI: 11 уникальных методов / 15 вызовов, 0 failures/skips в финальных прогонах.** [Сводка](docs/ui-v1.6/tests/summary.json).

| Прогон | Тестов | Результат |
| --- | ---: | --- |
| [384×832dp, font1.0](docs/ui-v1.6/tests/tall-final/instrumentation.log) | 9 | PASS |
| [360×640dp, font1.3](docs/ui-v1.6/tests/compact-final/instrumentation.log) | 3 | PASS |
| [360×640dp, font2.0, обе темы](docs/ui-v1.6/tests/large-final/instrumentation.log) | 1 | PASS |
| [Прежний recorder regression, новый flow](docs/ui-v1.6/tests/legacy-recorder-final/instrumentation.log) | 1 | PASS |
| [Отказ в разрешении микрофона](docs/ui-v1.6/tests/permission-final.log) | 1 | PASS |

 Профили: API35 x86_64, 384×832dp/font1.0; 360×640dp/font1.3; 360×640dp/font2.0. Проверяется реальный виртуальный MediaRecorder, AAC decode, Room, отсутствие черновых/дублирующих файлов, пауза и восстановление, все три входа в decision sheet, сохранённая длительность, возврат без таймера, экспорт и старый waveform, оба renderer и touch. Заданный вход 80% используется только отдельным `EdgeMicrophoneV16Test`; его скриншоты `injected-envelope-*` не являются микрофонным тестом.

**APK:** [статическая проверка](docs/ui-v1.6/tests/all-in-one-static.json) PASS: один вложенный ZIP, семь pinned model/token files, arm64-only, ZIP/ELF alignment и native dependencies. [Badging](docs/ui-v1.6/tests/apk-badging.txt): `ru.replika.offline`, code8/name1.6. [Подпись](docs/ui-v1.6/tests/apk-signature.txt): прежний сертификат SHA256 `f40399356577bcd0a5c220818ba13e9686768a02830a7f6e3af81d5a487947ab`.

APK: [REPLIKA-V1.6-AllInOne-arm64.apk](release/REPLIKA-V1.6-AllInOne-arm64.apk). SHA256: `dec7523de9403248358a5b590f12069be47e821460cb6095af4c1424edb7febd`. Размер и актуальный состав: [CURRENT](release/CURRENT.json), [SHA256SUMS](release/SHA256SUMS).

**Перенос:** 12 входов (семь моделей/токенов, четыре native .so, ZIP) проверены по SHA; [manifest](docs/ui-v1.6/workspace-inputs.json), [повтор](docs/ui-v1.6/tests/workspace-recheck.log). Portable preflight Debug и All-in-One прошёл, в том числе вызов из другого cwd. Все входы находятся в папке; ключ не включается в Git. Новая Windows/ноутбук ещё не запускались. Инструкция: [HANDOFF](HANDOFF.md), [PORTABILITY](PORTABILITY.md).

## Визуальная проверка

Это нативное Android-приложение; браузер/Playwright не использовался. Рендеры получены Android instrumentation `uiAutomation.takeScreenshot` и Compose captureToImage для отдельного controlled renderer fixture; изображения открыты через view_image вместе с концептом.

Проверены: 1) общий центр шара/статуса/таймера, 2) сферический материал, мягкость бликов и тени, 3) протяжённость/привязка правой волны, 4) читаемость обеих тем, 5) иерархия и доступность двух исходов панели, 6) кнопки при увеличенном шрифте. Исправлены старый сдвиг 32dp, иконка-VU вместо edge field, плоская диагональная заливка, жёсткая тень и остаточный таймер.

Сознательные адаптации концепта: существующие холодная Light/Graphite палитра и serif REPLIKA/заголовки, Onest controls, радиусы кнопок общего приложения. Статус «На паузе» сохраняет прежний словарь; нет новой навигации, декоративных карточек/метрик. Native copy сверена с DESIGN; техническая подпись controlled fixture не является текстом продукта. Внешний вид проверен по принятому контракту, с этими явными адаптациями.

[Нативные PNG](docs/ui-v1.6/screenshots/) включают обычный, компактный и font200% экраны. Финальный концепт и актуальные LIGHT idle / DARK decision font200% открыты рядом через view_image; кнопки и текст доступны, остаточных материальных расхождений с контрактом не обнаружено. Нативная [видеодемонстрация](docs/ui-v1.6/demo/native-demo.mp4) показывает start/drag/pause/exit/discard; [scope](docs/ui-v1.6/demo/video-scope.json) отделяет её от физического микрофона и performance-измерений.

## Ранние ошибки и исправления проверки

Старый Gradle offline cache не содержал datastore1.1.4; зависимость восстановлена обычной онлайн-сборкой, дальнейшие сборки прошли offline. В ранней сборке нового теста исправлен доступ к высоте DpRect. Ранний test APK не содержал только что добавленный EdgeMicrophoneV16Test. В save/recreate UI-тесте с замороженными Compose часами добавлено явное ожидание кадра/Room-навигации (поиск «Запись» и Workspace до отрисовки); прежние failed logs сохранены в `recording-tall-first.log`, `tall/`, а не объявлены успешными. Окончательная приёмка относится к повторным `*-final` прогонам.

## Очистка рабочего дерева

После копирования APK и evidence регенерируемые `app/build`, корневой `build`, `.gradle`, `.kotlin` и машинный `local.properties` вынесены из переносимой папки в desktop recovery cache. Python bytecode и временные изображения/дубли QA удалены. [Журнал](docs/ui-v1.6/cleanup.json). Обязательные модели/native/ключ, `.git`, source, тесты и архивы прежней работы оставлены. После очистки повторно прошли [portable preflight](docs/ui-v1.6/tests/portable-after-cleanup.log) и [SHA-входы](docs/ui-v1.6/tests/inputs-after-cleanup.log). Это не `git clean` и не удаление ignored build inputs.

## Границы результата

Новый APK/UI пока не принят на физическом vivo. Реальные FPS/GPU/батарея/нагрев не измерены; scheduling caps не являются измеренной частотой кадров. Активная речь/touch используют прежний cap60, тишина cap30, спокойное idle течение — более редкие кадры; lifecycle/reduced motion/power/thermal limits сохранены. Canvas проверен на API35 принудительно, это не новый физический API26–32 тест.

ASR/VAD/quiet gain/diarization/Room schema не изменялись. Пользователь подтвердил работу шёпота после предыдущих тестов; нового ASR benchmark в этом UI-цикле не было. Automatic diarization и немгновенная отмена native call остаются прежними ограничениями. Новая машина требует host-native SDK/JDK; обычные Gradle зависимости скачиваются при первом запуске, модели уже включены.
