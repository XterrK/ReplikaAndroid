# C+B fidelity ledger — V1.4

Источники: прямое решение пользователя и Final Visual Direction Update; сохранённый оригинал design-lab/concepts/c-overview.png; обновлённый интерактивный design-lab. Старые A/B/C не являются вариантами для повторного голосования.

Сравнение выполняется через реальные Android screenshots отдельно от browser captures. `view_image` использован для оригинала C, прототипа Light/Dark и нативных Recording/Dialogue/Editor/Models. Нативный размер обзорного C — 1536×1024, это иллюстративный multi-screen board; Android нельзя честно представить восьмью runtime экранами в одном viewport. Проверяем каждый экран на отдельном телефоне.

| Точка | Свидетельство / решение | Реализация |
|---|---|---|
| Палитра | окончательное указание #111214 / #F5F5F6 | нейтральный графит/холодный светлый; navy фон удалён |
| Typography | C: выразительные editorial headings | serif в Library/Recording/Models/Editor; Onest в транскрипции и controls |
| Dialogue density | B: компактность, самостоятельные реплики | один исходный segment на строку, цвет+имя, таймкод, edit; при fontScale ≥1.2 таймкод под именем, Reading отдельно группирует абзацы |
| Orb material | прототип: перламутр/лаванда, блик, реальная волнистая граница | AGSL volume shading внутри Bézier path; Canvas fallback, без фоновой синевы |
| Navigation | B: ясные действия; пользователь отклонил 8 нижних вкладок | две вкладки + контекстные режимы/настройки |
| Controls / icons | существующий Material Outlined | 48 dp targets, текстовые pause/resume/stop; ripple/selected native |
| Containers | пользователь запретил огромные декоративные карточки | компактные строки и разделители, небольшой audio dock, waveform скрыт в Reading; согласованные 10 dp кнопки; большие области только текст/запись |
| Keyboard | native IME / insets | editor footer над IME, scrollable fields; AOSP keyboard имеет свою системную тему |

## Намеренные отличия

- Цвета бумага/терракота C заменены прямым указанием пользователя. Светлый accent text темнее исходного ориентировочного accent ради читаемости.
- C не переносит восемь нижних вкладок, декоративные шрифты в body или вымышленный пересказ Reading.
- Прототип имеет симуляцию амплитуды и fixture content. Native не имеет simulation slider, использует реальный существующий recorder.
- В Android idle заканчивает движение после settling; это защита энергии, документированная в MOTION_DESIGN.md.
- AGSL даёт более объёмный корпус и мягче внутреннюю световую полосу, чем Canvas2D prototype. Fallback не имеет всех Fresnel деталей.
- В тестовых Android screenshots видны контролируемые UI fixtures/ML-regression records. Это проверка верстки, не свидетельство нового многоголосого ASR.
- IME — отдельное приложение: AOSP keyboard при ручной Dark теме REPLIKA может оставаться светлым, следуя своей настройке. Insets/контраст editor проверяются независимо; приложение не меняет глобальную тему устройства.

## Copy diff

Производственные надписи берутся из DESIGN_SYSTEM.md и существующих действий V1.3. Изменения: «Сохранить» записи → явное «Остановить» с автоматическим сохранением; добавлены Настройки/Оформление и Liquid Voice states; «Нужна проверка» больше не появляется исключительно из-за короткой длительности. Browser-only «симуляция»/slider и fixture labels не перенесены в продукт. Технические сведения моделей остаются в расширенном управлении.

## Финальная сверка

Повторно просмотрены оригинальный C board и последние Android Library Light, Recording Dark, Dialogue при font 130%, Editor Light/Dark с IME. Проверены палитра/нейтральный фон, editorial heading vs sans body, плотность и самостоятельные реплики, геометрия/материал orb, 10 dp buttons и 48 dp touch targets, сохранение/IME footer. Reading убирает waveform. Исправлены compositor race, перекрытие текста редактора предупреждением и обрезанный floating label при IME. Назначение поля сохранено в accessibility semantics. Итог соответствует направлению C+B с документированными цветовыми и платформенными отличиями; физическая микрофонная/тепловая приёмка открыта.
