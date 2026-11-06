# REPLIKA V1.5 — C+B / native fidelity review

Дата: 2026-11-06. Статус: **соответствие утверждённому C+B проверено на source11 и свежих Android PNG; визуальная сверка завершена**. Финальное видео и отдельный отчёт производительности source11 дополняет координатор после завершения ML-проверок. Это проверка исполнения уже принятого решения пользователя, а не новое концептуальное голосование.

## Основание и свидетельства

Приоритет имеют прямые указания пользователя в [HUMAN_CONCEPT_REVIEW.md](../../../HUMAN_CONCEPT_REVIEW.md): визуальная основа C / Editorial Voice, компактный UX B / Linear Intelligence, холодная Light и нейтральная графитовая Dark. A отклонён. Позднее прямое указание делает запись стартовым экраном, переносит библиотеку в отдельную вкладку и сохраняет экспорт на главной. [DESIGN_SYSTEM.md](../../../DESIGN_SYSTEM.md) переводит эти решения в нативные токены и правила.

Визуально просмотрены [оригинал C](../../../design-lab/concepts/c-overview.png), актуальные browser captures Orb-прототипа и отдельные Android screenshots всех восьми основных экранов. C — иллюстративный обзор из восьми экранов, а не Android layout, который следует буквально сжать в один viewport.

| Свидетельство | Что проверяется | Граница |
| --- | --- | --- |
| [Prototype QA / captures](evidence/orb-prototype/QA.md) | Две темы, quiet/loud/silence, деформация жестами, независимый VU, компактный player | Canvas2D и явно симулируемая амплитуда. Браузер не открывает микрофон; это не Android runtime |
| [Source11 Android PNG](evidence/android/) | Свежая матрица 48 PNG: Light/Dark ×384×832/font100% и360×640/font130% ×12 экранов/состояний; дополнительно virtual-mic Recording/Paused/Saved при 100/130/200% | Actual API35/x86_64 APK. Controlled UI text проверяет layout, emulator input не является физическим микрофоном телефона |
| [Source11 API28 UI](evidence/api28/build11/ui/) / [33/33 PASS и среда](evidence/api28/build11/README.md) | Оригинальный профиль384×760dp, обе темы, настоящий Canvas fallback, editor/IME, recording/save/reopen.31 PNG:27 полных Android captures и4 standalone renderer fixtures | На API28 выполняется Canvas, включая forced/automatic requests; AGSL не заявляется. Disposable VM выключена, оригинальные 7 AVD-файлов проверены по SHA |
| [Галерея оригинальных Android PNG](index.html) | Выбор Light/Dark и normal/compact профиля, подписи восьми экранов и четырёх дополнительных состояний, переходы к исходным PNG | HTML показывает файлы из актуального evidence/android. Сохранённые [browser gallery captures/report](evidence/review-gallery/) — более ранняя проверка галереи; они не переименовываются в новый source11 browser pass |
| Native source11 / [тестовые логи](evidence/android-tests-build11/) | Три вкладки/Home export, player/seek, состояния Orb, adaptive controls, system/dialog bars, все 4 Editorial UI tests normal/compact и отдельная запись при font200% | Конкретные native UI regressions; не физический vivo FPS/thermal benchmark |

UI-fixtures проверяют вёрстку, а не качество многоголосого ASR. Label GigaAM v2 в контролируемой Library fixture/архивной записи относится к её метаданным; активная модель source11 на экране Models — GigaAM v3. Старые наборы [through build6](evidence/android-through-build6/) и [source10 archive](evidence/android-build10/) сохранены отдельно, а финальная сверка использует свежую source11 матрицу. Геометрия/материал приложения в source11 сохранены; изменена каденция draw loop.

## Восемь экранов

| Экран | Связь с C+B и результат |
| --- | --- |
| **Recording / Home** | Editorial REPLIKA, один выразительный Orb, свободное поле вокруг него. Главная — запись; три вкладки «Запись», «Записи», «Модели», contextual режимы стенограммы. Импорт аудио/видео и экспорт доступны на Home. При записи навигация уступает таймеру и отдельным «Пауза» / «Продолжить» / «Остановить». Приfont130% подписи в строке без иконок, при font200% кнопки расположены вертикально; подписи целые, таймер/подсказка не перекрывают controls. Orb уменьшается ради доступного текста. Справа пять независимых VU-шкал без горизонтального трека. |
| **Library** | Serif-заголовок, компактные строки с длительностью, датой, состоянием и быстрым меню. Заметный поиск, ограничение строк названия, мягкие разделители. При 360dp/font130% видно меньше строк, список прокручивается. |
| **Processing** | Выразительный заголовок, одна спокойная область реальной фазы, indeterminate indicator и отдельная отмена. Проценты и ETA не выдумываются. Настройка участников отделена от прогресса; automatic mode не объявляет дефект диаризации исправленным. |
| **Dialogue** | Самостоятельные реплики, имя/номер/цвет участника, таймкод, меню исправления. Sans-serif body. Крупный waveform 112dp, компактный вариант 82dp; Play64dp и симметричные ±10s48dp. Скорость не сдвигает центральную тройку. При font130% таймкод под именем. |
| **Reading** | Чистые абзацы исходной стенограммы, копирование и экспорт, читаемый sans-serif. Полный waveform заменён transport56dp, чтобы текст занимал экран. Вымышленный пересказ из иллюстрации C не подставляется. |
| **Review** | Очередь конкретных проверок. Краткость реплики сама по себе не создаёт предупреждение: `reviewIssues` исключает старые duration-only причины. Объясняется сохранённая неоднозначность, а не утверждается, что объединённая реплика короткая. Transport минимален, действия прослушивания/исправления явные. |
| **Editor** | Компактная native sheet: время исходного фрагмента, playback, текст/участник, Save/Undo. В captures с IME текст и Save находятся над клавиатурой, содержимое прокручивается. Keyboard — отдельное приложение со своей темой. |
| **Models** | Активный GigaAM v3 и три локальные группы: распознавание, разделение говорящих, VAD. Подробности отдельно. Удаление Whisper следует позднему прямому указанию пользователя; строка Whisper из исходного C не переносится. |

## Палитра, типографика и player

`Theme.kt`: Light background `#F5F5F6`, белая surface, secondary `#EBECF0`; Dark background `#111214`, поверхности `#1C1D20` / `#282A2E`, divider `#36383E`. В просмотренных Home/Models/Reading нет navy фонового слоя. Сине-сиреневый свет локализован в Orb, интерактивных акцентах и speaker/waveform цветах. Success/warning/error имеют отдельные семантические цвета.

Light action text/button используют более тёмный `#465BB2`, secondary text — `#626977`: документированное усиление контраста относительно ориентировочных пользовательских токенов. Serif ограничен выразительными заголовками; Onest используется в transcript, controls и metadata. System fontScale не ограничивается. Светлая/Тёмная/Как в системе сохраняются в Preferences DataStore.

`AudioDock.kt`: голубой→розовый градиент применяется только когда все реплики принадлежат одному известному участнику. Несколько участников сохраняют семантические цвета по исходному времени; неизвестный не считается подтверждённым моноспикером. Peaks происходят из исходного аудио; max-pooling/нормализация относятся к рисунку. Есть tap/drag seek и accessibility `SetProgress`. Многоголосый Dialogue capture сам по себе не доказывает mono-gradient: условие проверяется исходниками и отдельной HomeExperience UI regression.

## Liquid Voice Orb: прототип → native

| Аспект | Реализация / различие |
| --- | --- |
| Форма | 96-точечный Bézier path, пять упругих мод, bounded expansion, демпфирование, нормализация площади; tap/drag с взаимно обратными осями. Деформируется граница. Browser использует Canvas2D, native — Kotlin `OrbDynamics` и Compose Canvas. |
| Материал | API33+ AGSL создаёт объёмный свет внутри того же path. API26–32 Canvas сохраняет контур/сигнал, но имеет проще градиентную глубину, широкую световую полосу и менее подробное преломление края. В API28 Light/Dark captures перламутровая оболочка узнаваема, окружающий фон нейтрален. Пиксельная идентичность материалов не заявляется. |
| Настоящий сигнал | `AppViewModel` читает `MediaRecorder.maxAmplitude` существующей MIC/AAC-сессии каждые50ms; `VoiceEnvelope` сглаживает атаку/затухание и ограниченно оценивает фон. Peak envelope не называется RMS, высотой тона или dB SPL. Второй сессии и simulation slider в native нет. |
| Игра и контроль | Touch меняет только `OrbDynamics`. Правый `LiveMicrophoneMeter` получает только реальный `voiceLevel`; в Paused он нулевой, даже если шар растягивается. Pause/Resume/Stop независимы от жестов. Permission-required не имитирует голос. |
| Состояния | Idle, Permission required, Starting, Recording, Paused, Stopping, Saved, Error представлены явно. Back предлагает сохранение/продолжение/удаление; сохранение открывает записанный материал. |
| Энергия / доступность | Frame state читается при draw, без покадровой recomposition всего экрана. Source11 scheduler: около 30 draw/s при тихой записи, cap около 60 при речи/переходе/touch с коротким удержанием быстрого режима; это лимиты планировщика, не измеренные 60 FPS устройства. RESUMED lifecycle, power-save/thermal cap, idle/paused settling. Актуальный browser V1.5 также замораживает idle после settling. Reduced motion подавляет wobble/touch stretch, оставляет статусы/VU/управление. Есть semantic click и accessibility-действие растяжения. |

Статичный screenshot показывает цвет/композицию. [Историческое native видео source10](evidence/native-demo-build10/native-orb-emulator-touch.mp4) демонстрирует Start→tap/drag→Pause/Resume→Stop/Save в настоящем приложении с виртуальным входом и выключенным host mic; [scope](evidence/native-demo-build10/video-scope.json). Геометрия и материал соответствуют текущему направлению, но видео предшествует source11 cadence 30/60 и не является доказательством его FPS/ритма. Final source11 video/performance evidence добавит координатор отдельно. Прототипные уровни явно симулируются; native virtual-mic captures подтверждают recorder/session state без утверждения о физическом голосовом входе vivo X300.

## Финальная сверка source11

Просмотрены свежие Home Dark, Library/Dialogue/Processing/Editor Light, Reading/Review/Models Dark, native Recording при font130%, Recording/Paused при font200% и API28 Canvas Home Dark. Утверждённая нейтральная палитра, editorial headings, sans-serif transcript, три вкладки, Home export, большой симметричный Dialogue player и минимальный Reading/Review transport сохранены. Настройки/ошибки/IME присутствуют в той же финальной 48 PNG матрице и проверены native UI suite.

Старая проблема переноса «Остановить» закрыта: [font130 Recording](evidence/android/360x640-font1.3-virtual-mic-recording.png) показывает обе подписи в одну строку; [font200 Recording](evidence/android/360x640-font2.0-virtual-mic-recording.png) и [Paused](evidence/android/360x640-font2.0-virtual-mic-paused.png) — вертикальные полноширинные кнопки без перекрытия. User fontScale сохранён. Status остаётся ниже REPLIKA, timer/подсказка — над первой action button. При 200% декоративный размер Orb уступает тексту и ясному управлению.

System/dialog bars source11 проверены отдельно, включая явную Light/Dark тему. Собственная тема сторонней IME не перекрашивается приложением; editor text/Save остаются выше неё. На source11 API28 пройдены 33/33 выбранных native tests без повторных запусков; Canvas Dark имеет графитовый фон. В основном API35 наборе первоначальные тайм-ауты тестов PixelCopy/queued-cancel и успешные изолированные повторы на неизменённом APK сохранены в [сырых логах](evidence/android-tests-build11/); они не удалены ради итогового отчёта.

Открыты **финальное source11 видео/отдельные performance measurements**, которые добавляет координатор; общая визуальная сверка PNG и controls завершена.30/60 — draw cadence targets, не подтверждённые phone FPS. Физический vivo X300, реакция его микрофона, батарея/нагрев и реальные шумы остаются вне этой визуальной приёмки. Семь студийных RU whisper файлов проверены отдельным Worker test, что не заменяет микрофон телефона; automatic diarization остаётся известным ограничением.

Source11 соответствует уже утверждённому пользователем C+B с документированными цветовыми и платформенными отличиями. Повторный выбор A/B/C не требуется.

Финальное source11 видео и отдельный performance capture завершены: `evidence/native-demo/` в Human Review. Область видео — настоящее приложение/виртуальный микрофон с hostmicOff. Source11 idle0кадров/4s; quiet p9538ms, reportedjank59,32%, поэтому60fps и физическая производительность не объявляются подтверждёнными. Source10 видео и метрики оставлены историческими.
