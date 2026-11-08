# UI V1.6 — материалы проверки

- [Исследование, ссылки и контракт](DESIGN.md)
- [Концепт](concept.png)
- [До изменений](before.png)
- [Актуальная главная, Light](screenshots/384x832-font1.0-LIGHT-idle.png)
- [Запись, Dark](screenshots/384x832-font1.0-DARK-recording.png)
- [Панель завершения, Dark](screenshots/384x832-font1.0-DARK-decision.png)
- [Font200%, запись](screenshots/360x640-font2.0-DARK-recording.png)
- [Font200%, панель](screenshots/360x640-font2.0-DARK-decision.png)
- [Правая волна: controlled amplitude 80%, не микрофон](screenshots/injected-envelope-LIGHT.png)
- [Нативная видеодемонстрация](demo/native-demo.mp4), [границы демонстрации](demo/video-scope.json)
- [Тесты](tests/summary.json), [полный отчёт](../history/root/TEST_REPORT_V1_6.md)
- [SHA моделей и native](workspace-inputs.json), [перемещения](relocation.json), [очистка](cleanup.json)

`injected-envelope-*` сняты на отдельном native renderer fixture с заданным уровнем. Остальные recording PNG — реальный MediaRecorder эмулятора, host microphone отключён, тишина допустима. Видео не является замером FPS/батареи или физической проверкой голоса.

Сравнение с концептом выполнено в нативных размерах 384×832dp и 360×640dp. Концепт — трёхэкранная доска, не побайтовый screenshot app; существующие тема и типографика сохранены намеренно.

| Проверяемая деталь | Свидетельство в рендере | Результат |
| --- | --- | --- |
| Один центр шара, статуса и таймера | tall/compact/large native bounds assertions | Убран end-padding32dp, отклонение ≤1.1dp |
| Объём/свет/тень | LIGHT idle и DARK recording | Внутренние складывающиеся потоки, блики, мягкий край/тень; плоская прежняя заливка заменена |
| Правая стена и протяжённость | injected-envelope + bounds в RecordingExperience | Overlay64dp/88% высоты, корень у правой кромки, центр не сдвигается |
| Два исхода завершения | DARK decision, реальная запись/Room assertions | Пауза на время выбора; save/discard работают; dismiss восстанавливает прошлое состояние |
| Крупный шрифт | font200% запись/панель | Действия видны, кнопки не обрезаны; экранные контролы при необходимости в столбик |
| Copy и общий стиль | DESIGN + native PNG | Штатные русские labels; сохранены Serif/Onest, палитра Light/Graphite и радиусы control10dp |

Материальных исправимых расхождений с этим адаптированным контрактом после финального просмотра не осталось. Физическая оценка нового UI на vivo и Windows/ноутбуке отдельно от этих результатов.
