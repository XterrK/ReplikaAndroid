# REPLIKA V1.2.1 · реальные экраны

Все PNG получены на Android API35/x86_64 AVD. Исходные V1.1/V1.2 изображения сохранены. Снимки в acceptance/files/human-review-v1.2 имеют историческое имя producer-каталога, но сняты заново в чистом AIOQA-приложении этой итерации.

- [Настоящий прогресс подготовки](../../test-evidence/v1.2.1/first-launch-after-cold/01-clean-offline-progress-ui.png).
- [Library после автоматической проверки](../../test-evidence/v1.2.1/first-launch-after-cold/01-clean-offline-library.png).
- [Processing настоящего GigaAM Worker](../../test-evidence/v1.2.1/acceptance/files/human-review-v1.2/03-processing.png).
- [Transcript Workspace из настоящего inference](../../test-evidence/v1.2.1/acceptance/files/human-review-v1.2/04-transcript-workspace.png).
- [Установленный встроенный комплект](../../test-evidence/v1.2.1/acceptance/files/human-review-v1.2.1/06-models-bundled-ready.png).
- [Дополнительный ручной импорт/restore](../../test-evidence/v1.2.1/acceptance/files/human-review-v1.2.1/07-models-advanced-optional.png).
- [Ошибка/retry/font1.3: явно помеченный UI fixture](../../test-evidence/v1.2.1/acceptance/files/human-review-v1.2.1/08-ui-fixture-error-font130.png). Это rendering-тест, не настоящий сбой файла большого APK.
- [Recording/review/editing/screens](../../test-evidence/v1.2.1/regression/files/human-review-v1.2/),[raw JSON до ручных правок](../../test-evidence/v1.2.1/acceptance/files/android-transcript.json),[экспорты после UI-правок](../../test-evidence/v1.2.1/regression/cache/exports/).

Тексты ASR — официальный публичный русский mono smoke fixture, не демонстрационный диалог. Присвоенный редактором speaker1 не означает второго обнаруженного моделью человека. Данные редактора с длинным roster — тест взаимодействия, не ML evidence. Recording использует виртуальный -no-audio источник эмулятора. Первый неуспешный ANR-прогон хранится отдельно и не представлен как рабочий onboarding. Внешнее UX-одобрение не заявляется.

[Полный отчёт](../../ALL_IN_ONE_TEST_REPORT.md),[инструкция](../../ALL_IN_ONE_INSTALL.md),[ограничения](../../ALL_IN_ONE_KNOWN_ISSUES.md).
