# V1.7b — скриншоты после правок

Свой эмулятор `emulator-5600` (API 35, SwiftShader) в режиме экрана телефона: `wm size 1216x2640`, `wm density 480`. Сборка allInOneQa, ветка `hack/task-11b-ui-fixes`. Реальный импорт `dialog-two-speakers.wav` (1:09, два диктора).

| Файл | Что |
|---|---|
| `01-import-starts-processing-dark` | Сразу после выбора файла: обработка уже идёт, экрана выбора нет |
| `02-transcript-ready-dark`, `10-…font1.0`, `11-…font1.3` | Готовая стенограмма; ⚙ рядом с экспортом — «Обработать заново» |
| `03-reprocess-sheet-dark` | Шторка параметров: целиком помещается при шрифте 1.0 |
| `04-reprocessing-font1.3-dark` | Повторная обработка при шрифте 1.3 |
| `05-cancelled-compact-font1.3-dark`, `05b-…font1.0` | После отмены: заголовок, одна кнопка, строка параметров |
| `06-bubble-during-rapid-taps-dark`, `07-bubble-after-25-taps-settles-round-dark` | 25 быстрых тапов по пузырю во время записи: круг во время и после |
| `08-home-font1.3-dark`, `09-library-font1.3-dark` | Главная и библиотека при 1.3 |
