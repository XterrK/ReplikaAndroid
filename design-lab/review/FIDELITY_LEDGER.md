# C+B fidelity ledger — V1.5

Дата: 2026-11-06. Основание — прямое решение пользователя в [HUMAN_CONCEPT_REVIEW.md](../../docs/history/root/HUMAN_CONCEPT_REVIEW.md), окончательная палитра и последующие требования V1.5. Визуальная основа C / Editorial Voice, UX B / Linear Intelligence; A отклонён. Повторный выбор A/B/C не требуется.

Подробная текущая native сверка: [FIDELITY_REVIEW.md](../../docs/human-review/v1.5/FIDELITY_REVIEW.md). Она сопоставляет исходный [C board](../concepts/c-overview.png), актуальный design-lab и свежие native source11 captures. **Визуальная сверка source11 завершена**: 48 PNG основной матрицы, дополнительные recorder font130/200% и API28 Canvas. Финальное source11 видео и отдельные performance evidence добавлены в Human Review; визуальная сверка завершена.

## Утверждённое направление → реализация

| Точка | Решение / свидетельство | Текущая реализация |
| --- | --- | --- |
| Палитра | Окончательное указание пользователя `#F5F5F6` / `#111214` | Холодная Light, нейтральная графитовая Dark; сине-лавандовый свет локализован в Orb и акцентах |
| Типографика | Выразительные заголовки C, читаемый body | Системный serif в editorial headings; Onest в транскрипции, controls и metadata; fontScale не ограничивается |
| Home / навигация | Позднее прямое указание: старт — Orb, библиотека отдельно, экспорт на главной | Три вкладки «Запись», «Записи», «Модели»; contextual Dialogue/Reading/Review/Editor; Home import audio/video и export picker; при записи отдельные controls |
| Library | Компактность B, работа с текстом C | Строки, метаданные, поиск, быстрые действия, мягкие разделители |
| Recording | Orb — главный визуальный фокус | Перламутровый Light, сиренево-голубой Dark на графите; справа независимые VU-шкалы recorder; font130% — целые подписи без иконок, font200% — вертикальные полноширинные controls и меньший Orb ради текста |
| Processing | Структура без ложной точности | Реальная фаза, indeterminate indicator, отмена; без вымышленных процентов/ETA |
| Dialogue | Самостоятельные реплики и увеличенный player | Имя/номер/цвет, таймкод, отдельный текст; waveform112dp/82dp, Play64dp, симметричные ±10s48dp, seek semantics; mono голубой→розовый только для одного известного участника |
| Reading | Спокойное чтение | Исходные абзацы sans-serif, копирование/экспорт; transport56dp без waveform |
| Review | Полезные объяснения | Duration-only warnings скрыты; неоднозначность объясняется без ложного утверждения о короткой объединённой реплике; минимальный transport |
| Editor | Плотность и удобный IME | Исходный timecode/playback, текст/участник, Save/Undo; controls над клавиатурой, scrollable content |
| Models | Позднее прямое указание убрать Whisper | GigaAM v3 / разделение говорящих / VAD; подробности отдельно; архивная атрибуция сохраняется |
| Контейнеры | Пользователь запретил огромные декоративные карточки | Строки и мягкие панели; большая область оправдана Orb, текстом или главным waveform |
| Доступность | Ясное управление и системные настройки | Targets ≥48dp, явные Pause/Resume/Stop, phase semantics, gesture alternative, reduced motion, Light/Dark/System в DataStore |

## Прототип и native

Design-lab явно помечен как **концептуальный прототип, не Android**. Амплитуда симулируется тестовым уровнем; браузер не открывает микрофон. [V1.5 browser QA](../../docs/human-review/v1.5/evidence/orb-prototype/QA.md) отдельно фиксирует Light/Dark, quiet/loud/silence, drag с независимым VU, font130% и compact player.

Native получает peak envelope из `MediaRecorder.maxAmplitude` существующей сессии. Второго recorder и browser slider нет. Жесты деформируют только пружинное тело, не изменяя реальный правый VU. Idle/Permission/Starting/Recording/Paused/Stopping/Saved/Error — состояния приложения, сохранение идёт в Room.

Нативный contour — Bézier path с ограниченными модами, демпфированием и tap/drag. API33+ AGSL добавляет объёмный свет/край внутри этого path. API26–32 Canvas сохраняет физику, но имеет менее подробное преломление и более простую световую полосу; пиксельное равенство AGSL/Canvas2D/Canvas не заявляется. Просмотренные API28 Home Light/Dark сохраняют холодный светлый/нейтральный графитовый фон вокруг Orb.

Текущие browser V1.5 и native прекращают idle после settling. Source11 изменяет только draw cadence: scheduler около 30 draw/s при тихой записи, cap около 60 при речи/переходах/touch; это заданные пределы, не измеренные 60 FPS устройства. Native также учитывает Activity lifecycle, power save и thermal status. Reduced motion уменьшает движение, сохраняя состояние/уровень и явные controls. Физическая производительность vivo X300 не подтверждена.

## Намеренные отличия от исходного C

- Бумага/терракота заменены прямым final palette указанием. Light action color и secondary text затемнены для контраста.
- Восемь нижних вкладок C не перенесены. Первоначальная V1.4 схема из двух вкладок заменена тремя по позднему прямому запросу пользователя.
- Transcript/Reading использует читаемый sans-serif. Reading содержит исходные слова, не вымышленный пересказ из иллюстрации C.
- Увеличенный waveform предназначен для Dialogue; Reading и Review получают минимальный transport ради текста.
- AGSL богаче по объёмному свету, fallback проще; разрешения/запись/сохранение в native настоящие.
- Keyboard — отдельное приложение. Его Light тема при Dark REPLIKA не означает смену app surface; editor/insets проверяются отдельно.

## Финальные свидетельства source11

[Галерея](../../docs/human-review/v1.5/index.html) загружает оригинальные [source11 Android PNG](../../docs/human-review/v1.5/evidence/android/): 48 изображений = 12 экранов/состояний ×2 темы ×2 профиля (384×832/font100% и360×640/font130%). Дополнительно сохранены native virtual-mic Recording/Paused/Saved при 100/130/200%. Галерея не заменяет runtime. Сохранённые [browser gallery captures/report](../../docs/human-review/v1.5/evidence/review-gallery/) относятся к более ранней проверке страницы; live HTML использует свежие файлы, старые browser hashes не объявляются source11 re-run.

Повторно просмотрены свежие восемь основных экранов, Dark Home/Models/Reading/Review на нейтральном графите, Light Library/Dialogue/Processing/Editor с IME, [Recording font130](../../docs/human-review/v1.5/evidence/android/360x640-font1.3-virtual-mic-recording.png), [Recording font200](../../docs/human-review/v1.5/evidence/android/360x640-font2.0-virtual-mic-recording.png) и [Paused font200](../../docs/human-review/v1.5/evidence/android/360x640-font2.0-virtual-mic-paused.png). Старая многострочная подпись Stop устранена: 130% — обе action labels в одной строке, 200% — вертикальные Pause/Continue/Stop, без уменьшения system fontScale. Status/timer/подсказка и controls не перекрываются. Большой Dialogue player симметричен; Reading/Review сохраняют минимум controls и площадь текста.

[Source11 API28](../../docs/human-review/v1.5/evidence/api28/build11/README.md): 33/33 PASS, исходный профиль 384×760dp без runtime overrides,31 SHA-верифицированный PNG (27 полных app captures и 4 standalone renderer). Просмотренный [Dark Home Canvas](../../docs/human-review/v1.5/evidence/api28/build11/ui/384x760-font1.0-DARK-recording-idle.png) сохраняет графит и жидкую оболочку. API28 выполняет Canvas в automatic/forced cases; AGSL не заявляется. Disposable emulator выключен, оригинальные 7 AVD-файлов совпадают по SHA.

[Историческое native видео source10](../../docs/human-review/v1.5/evidence/native-demo-build10/native-orb-emulator-touch.mp4) показывает Start/tap/drag/Pause/Resume/Stop/Save с виртуальным входом и выключенным host mic. Материал/геометрия сохраняются, но видео предшествует cadence 30/60 source11 и не подтверждает его FPS. Финальные source11 видео/отдельный perf scope добавляет координатор. Старые [source10 PNG](../../docs/human-review/v1.5/evidence/android-build10/), сырые ошибки PixelCopy/queued-cancel и успешные изолированные повторы на неизменённом APK сохранены в evidence; история не очищается.

Набор controlled UI text доказывает layout, не automatic diarization. GigaAM v2 label у QA fixture/архивной записи относится к её метаданным; активная модель на Models — GigaAM v3. Настоящий Worker со студийными whisper fixtures проверяется отдельно. Emulator recorder evidence не подтверждает физический микрофон, телефонный русский шёпот, vivo X300 frame times, батарею/нагрев или устойчивость к реальным шумам.

Соответствие C+B подтверждено для source11: холодная Light/нейтральная graphite Dark, editorial headings, компактный sans-serif transcript, три вкладки и Home export, крупный Dialogue player, минимальный Review/Reading. Принятое решение пользователя не требует дополнительного concept approval.

Финальное source11 видео и отдельный performance capture завершены: `evidence/native-demo/` в Human Review. Область видео — настоящее приложение/виртуальный микрофон с hostmicOff. Source11 idle0кадров/4s; quiet p9538ms, reportedjank59,32%, поэтому60fps и физическая производительность не объявляются подтверждёнными. Source10 видео и метрики оставлены историческими.
