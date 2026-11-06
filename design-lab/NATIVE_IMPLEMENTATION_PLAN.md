# Следующий этап после человеческого выбора

Это план, не выполненная реализация. Его точный визуальный spec зависит от фактического ответа пользователя.

1. Зафиксировать выбор/сочетание в synthesis brief с дословной обратной связью. Не менять выбранные цвет/иерархию/типографику без конкретного blocker.
2. Compose design tokens, typography, iconography, 4/8dp spacing, нажатия/selection/errors, source-time components и IME-safe sheets. Проверять APIs по текущему Compose BOM и resolved dependencies; не обновлять стек ради animation.
3. Dialogue сделать плоской LazyColumn по стабильному source ID. Группировку Reading оставить отдельной чистой проекцией. Не создавать времена на уровне предложений без alignment. Согласовать active/overlap, filter, follow scroll и timeline. Тяжёлые projection операции выносить из playback tick.
4. Заменить строковый UI substring mapping типизированной presentation-политикой review: unknown/overlap — основной слой; короткие/разрезанные/восстановленные границы — диагностика. Legacy не содержит точных вложенных локаторов: не придумывать их. Не мигрировать schema/corrections без необходимости.
5. Полный набор экранов из выбранного направления: Library, Recording, Processing, Dialogue, Reading, Segment Editor, Review, Models. Длинные имена/участники, пустые/error/cancel/recovery states. Copy/export из одного актуального Room snapshot.
6. Native motion: spring selection rail, аккуратный режим switch, play/pause state, draw-only playhead, нормальные Compose sheet transitions и keyboard insets, однократное сохранение/undo. Уважать animator duration scale. Без бесконечного декоративного motion при ML.
7. После тестов собрать отдельную V1.4 All-in-One arm64, сверить подпись со старым APK и embedded model hashes. V1.3 не перезаписывать. На эмуляторе сделать частный snapshot, install -r и сравнить DB/files; не удалять приложение. Fresh offline provisioning проверять в изолированном QA package без очистки пользовательского пакета.

| Приёмка | Проверка после реализации |
|---|---|
| Защищённая инфраструктура | Diff отсутствует для моделей/engines/PCM/Room schema/WorkManager/provisioning/thermal, кроме отдельно воспроизведённой и обоснованной необходимости |
| Dialogue/Reading | Одни source IDs/times, no inference on switch, native Compose tests для seek/filter/active/edit/reopen |
| Review | Регрессия 200ms edge→6000ms merged row; short-only не в очереди, unknown и persisted overlap корректно отражены; без выдуманного confidence |
| Исправления | Room save/undo/recreate/process restart; speaker changes, unknown, export TXT/SRT/JSON и clean copy |
| Экраны | API35 emulator, 360×640, modern phone, системный font130, реальная IME, screenshot baseline/new из Android |
| ML | Настоящий GigaAM/Whisper и прежние weights, целостность pack, single bypass, VAD/PCM invariants, thermal wait/cancel |
| Длинная запись | LazyColumn source keys, длительный scroll/seek с измерениями frame timing, без FPS claims до замеров |
| Upgrade | Same applicationId/signature, versionCode increment, install -r и сохранение DB/files без uninstall/clear |
| Physical vivo | Только при реально доступном телефоне; пользовательские ~30s не объявлять новым benchmark |
| Поставка | APK+SHA256, review ZIP без private audio, native screenshots/screenrecord при доступности, UX_BEFORE_AFTER, DESIGN_SYSTEM, MOTION_SPEC, FUNCTIONAL_FIXES, TEST_REPORT_V1_4, KNOWN_ISSUES |

Macrobenchmark добавлять лишь при доступном рабочем target/профилируемом варианте и осмысленной измеряемой цели. Инструментирование и эмуляторный UI не доказывают smoothness/thermal/RTF физического vivo. Automatic diarization остаётся явной отдельной ML-задачей.
