# REPLIKA V1.4 — Editorial Intelligence

C+B утверждён непосредственно пользователем. Повторный выбор A/B/C не требуется. См. [решение](review/HUMAN_CONCEPT_REVIEW.md) и [дизайн-систему](DESIGN_SYSTEM.md).

Запуск: `python3 -m http.server 4174 --bind 0.0.0.0 --directory design-lab`, затем http://localhost:4174. Две темы сравниваются рядом. Восемь экранов, размеры 392×852 и 360×640. Liquid Voice Orb: Записать → Тихо/Громко/Тишина → Пауза/Продолжить → Остановить. Slider — явно отмеченная симуляция; браузер не использует микрофон и не изменяет Room.

Прототип — концептуальная проверка движения и палитры, не Android runtime. Native Compose использует существующий MediaRecorder. Снимки браузера: ../docs/human-review/v1.4/evidence/prototype/. Android evidence хранится отдельно.

Предыдущая лаборатория архивирована в review/v1.4-baseline/design-lab-before-v14.zip; прежние концепты и baseline screenshots оставлены как история. Они не переопределяют принятое решение. V1.3 APK сохранён по прежнему пути, Git до изменений сохранён bundle.

Browser plugin not available; проверка выполнена Playwright на имеющемся локальном Chromium. Старый tools/verify.cjs проверяет исторические A/B/C; V1.4 QA — tools/verify-v14.cjs.
