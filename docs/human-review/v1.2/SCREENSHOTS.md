# Реальные кадры REPLIKA V1.2

Кадры получены на Android15/API35/x86_64 AVD, не на физическом телефоне. Финальный APK: `5d06dc98cb4f896f2640e1d76c5821462dad8e26ec8a275991c8828d3cd5141c`. Обычный профиль 432×936px/384dp/font1.0; `compact130` —360×640px/font1.3. Это настоящие UiAutomation/screencap PNG без макетов и генерации. Размеры, SHA и точный APK каждого кадра — [manifest](../../test-evidence/v1.2/screenshots.json).

| Сценарий | Основной кадр | Compact/дополнение |
|---|---|---|
| Library |[01](01-library.png)|[font1.3](compact130-01-library.png)|
| Recording/первые отсчёты |[02](02-recording.png),[32](32-recording-early-levels.png)|[compact](compact130-32-recording-early-levels.png)|
| Реальный Processing |[03](03-processing.png)|Отдельный кадр текущего native CANCELLING не получен|
| Raw GigaAM Workspace |[04](04-transcript-workspace.png)|[реальный текст с ручными QA-именами](22-product-workspace-compact130-360x640.png)|
| Editor |[05](05-segment-editing.png)|[IME/save](23-product-editor-keyboard-compact130-360x640.png)|
| Переименование |[05 speaker](05-speaker-editing.png)|Изменение подписи вручную, не voice identity|
| Выбор 12 длинных имён |[20](20-product-editor-longnames-base-384x832.png)|[поиск с IME](29-product-speaker-picker-keyboard-compact130-360x640.png)|
| Discard/Undo |[21](21-product-discard-base-384x832.png),[24](24-product-saved-undo-base-384x832.png)|[compact discard](21-product-discard-compact130-360x640.png)|
| Сохранённая коррекция |[11](11-transcript-after-correction.png)|[после трёх cold launches](37-cold-restart-correction.png)|
| Плеер/seek/speed |[28](28-product-player-seek-base-384x832.png)|[compact](28-product-player-seek-compact130-360x640.png)|
| Smart Review empty |[06](06-smart-review.png)|Пустая очередь не доказывает правильность ASR|
| Реальный short flag |[14](14-smart-review-real-warning.png),[15 editor](15-smart-review-warning-editor.png),[16 reviewed](16-smart-review-reviewed.png)|[compact queue](compact130-14-smart-review-real-warning.png),[650ms clamp](compact130-16-smart-review-reviewed.png)|
| Models/малый VAD |[07](07-models-diagnostics.png),[31](31-models-installed-small-file.png)|[compact](compact130-31-models-installed-small-file.png)|
| Читаемая диагностика |[35](35-models-metrics.png)|[compact metrics](compact130-35-models-metrics.png)|
| Raw JSON opt-in |[30](30-models-technical-details.png)|[compact](compact130-30-models-technical-details.png)|
| Безопасное удаление |[25](25-product-delete-confirmation-base-384x832.png)|[compact](25-product-delete-confirmation-compact130-360x640.png)|
| Corrupt Worker recovery |[34](34-product-corrupt-worker-recovery-base-384x832.png)|[compact](34-product-corrupt-worker-recovery-compact130-360x640.png)|
| Сохранённая virtual M4A → setup |[33](33-recording-saved-setup.png)|Не проверка настоящего микрофона|
| Экспорт без скрытых форматов |[36](36-product-export-options-base-384x832.png)|[compact](36-product-export-options-compact130-360x640.png)|
| Сохранённый M4A после APK update |[40](40-saf-m4a-transcript.png)|Inference выполнен ранее на 5cc, результат реально открыт финальным APK|

Дополнительные ручные кадры [36 fixed1](36-fixed-speaker-count.png),[38 system picker](38-system-import-picker.png),[41 bad SAF](41-saf-corrupt-recovery.png) относятся к промежуточному 5ccперед изменением только меню экспорта. Их scope указан явно; они не подменяют финальный suite. Двенадцать участников на UI-only copies созданы вручную для проверки имён; исходный model input mono. Raw ML JSON и ручной export хранятся отдельно.

Ранние кадры fade/белого окна и повторные снимки сохранены в `docs/test-evidence/v1.2/attempts/` и `capture-history/`. В light ZIP используются эта финальная галерея и 19 оригинальных кадров V1.1; промежуточные PNG из attempts исключены из ZIP, но сохранены в Git. TalkBack, естественный русский диалог, физический arm64 и реальный microphone path кадрами не подтверждены.
