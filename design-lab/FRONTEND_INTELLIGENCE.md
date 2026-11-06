# Фактический контракт Frontend Intelligence

Проверены локальные `AGENTS.md`, README, orchestrator, Creative Director, visual-quality, rule-model/system-architecture, `production/docs/operator-guide.md`, CLI и `freedom.py`. Runtime: `/home/egor/frontend-intelligence-runtime/20261102-recovery`. Дополнительно проверены README и реальные project/review adapters Desktop V2 из `/home/egor/frontend-intelligence-projects/desktop-v2` (package version 0.3.1).

Это инструкции/skills и Python control plane, а не Android build engine. Подтверждён supported mode **interactive Codex + registration/validation API**. `drive` не запускает creative workers. Объявленная доступность роли не подтверждает модельный вызов. Model identity встроенного imagegen не выводится из документации FI.

Реальный запуск CLI из runtime: `PYTHONPATH=production python3 -m hackathon_os.cli --run production/runs/NEW_ID preflight --config production/examples/os4-interactive-config.json`; затем `init --brief /absolute/brief.json --config ...`, `next`. Run root обязан находиться внутри production namespace; перенос SQLite между абсолютными путями не поддерживается. Проектная лаборатория поэтому остаётся здесь, controller metadata — в runtime.

OS4 жёстко проверяет 6–10 product theses (`FreedomController.explode`) и ≥6 image directions (`present_concept_review`). Пользователь требует три направления. Выбран ручной existing-product concept workflow по instructions с тремя направлениями, независимым review и реальным человеческим выбором. Автоматический OS4 gate **не объявляется пройденным**. Не изменяются движок, SQLite или human feedback ради обхода контракта. Сырые результаты preflight сохранены, включая первоначальный missing browser module.

Human Concept Review и HRE coded-product comparison — разные механизмы. HRE требует registered source revision, capture recipe и source-bound browser evidence. На данном этапе нет зарегистрированной нативной V1.4 и нет основания выдавать её за HRE completed change. Desktop показывает концепты из зарегистрированных image_concepts; незарегистрированные файлы доступны в «Все материалы». Автоматический human approval не выполняется.

Desktop Live Preview открывает локальный HTTP-сервер проекта; это подтверждено README и Electron adapter. Нативный Android preview/build/device automation в этом контракте не подтверждены. Android проверяется Gradle/ADB/instrumentation отдельно. Наличие browser mockup никогда не считается Android acceptance.

Browser plugin в доступных tools отсутствует. Для render/interaction QA лаборатории используется установленный Playwright из Desktop V2 node_modules и существующий Chromium. Никакие пакеты для этого не скачиваются.

Референсы исследованы 2026-11-05:

- [Linear UI redesign](https://linear.app/now/how-we-redesigned-the-linear-ui): ясное разделение chrome/content и ровная иерархия → B получает сетку и плотность, но не desktop sidebar или issue tracker.
- [Bear](https://bear.app/): приоритет редакторской типографики → C получает спокойную текстовую полосу, без заимствования cloud sync или продуктовых обещаний.
- [Rev Transcription Editor](https://support.rev.com/hc/en-us/articles/29824992702989-Transcription-Editor): timestamp рядом с speaker и переход в аудио → все направления сохраняют source-time navigation; не заимствуются word-level timestamps, которых REPLIKA не имеет.
- Реальные скриншоты REPLIKA V1.3/V1.2: сохраняются copy, export и audio navigation; исходные недостатки описаны в AUDIT.md.

Эти источники — ограниченные исследовательские наблюдения, не количественная UX-валидация. Выбор дизайна остаётся за пользователем.
