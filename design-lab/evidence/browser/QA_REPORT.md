# Browser QA concept lab

Статус: **PASS для лаборатории, не Android acceptance**. Фактические source hashes, 69 records и errors=[] — `report.json`. Рабочий сервер: http://localhost:4174, standalone mobile routes `screen.html?direction=a|b|c&screen=library|recording|processing|dialogue|reading|editor|review|models`.

Browser plugin отсутствует. Первые full/headless Chromium1248 launch завершились SIGSEGV до навигации; установленный cache содержит обрезанные binaries. Без скачивания зависимостей использован сохранённый FI Chromium1193, с per-process LD_LIBRARY_PATH recovery/local-libs. Первый успешный render-run нашёл favicon404; inline favicon устранил ошибку. Исходные failure logs сохранены отдельно.

Проверено:

- 48 основных viewport captures: 3 направления × 8 экранов × 392×852/360×640. Проверены отсутствие horizontal document overflow, fit app height, ненулевая content area, Save выше imitation keyboard.
- 15 дополнительных captures: три направления × Dialogue font130, Editor font130, 500+ rows long dialogue, empty Library, thermal pause. Проверена прокрутка к последнему исходному source ID длинного набора.
- Для каждого направления: выбрать turn→seek=19000, unknown filter, изменить слова и speaker, проверить снятие unknown issue, отметить overlap reviewed, перейти в Reading без подмены слов, скопировать чистый текст без times/labels, экспортировать JSON с сохранённой правкой, cancel/retry Processing. Это state лаборатории, не настоящие Media3/Room/WorkManager.
- Reduced motion для всех направлений: computed transitionDuration=0s.
- Desktop1440×1180 и mobile390×844 comparison shell; три iframes/переходы и mobile horizontal comparison доступны. Всего 65 PNG.
- Page identity, meaningful content, отсутствие error overlay, консоль errors=[].

Сценарий воспроизводится `design-lab/tools/verify.cjs`. Последняя исходная сессия: `run-final-review.log`. Source изменялся только по конкретным findings: local font fallback, очевидные Save/edit actions, компактный Reading dock, timeline positions, editor fill-height, review counts после исправлений. После изменений captures пересняты; финальный report относится к текущим hash.

Автор и независимый AI-reviewer просмотрели концепты и актуальные renders через view_image. Визуальная проверка охватывает композицию, палитру, typography, spacing/containers, icon/actions, compact/keyboard и Reading. Принятые отличия от imagegen — `review/FIDELITY_LEDGER.md`. Human approval отсутствует, никакая 10/10 fidelity к ещё не принятому дизайну не заявляется.

Остаются риски вариантов: B time gutter, C compact density, platform serif fallback, native IME/TalkBack/performance. Данные synthetic; playback без звука; CSS font130 не системный Android font scale. Full native testing/real model performance не заменяются browser suite.
