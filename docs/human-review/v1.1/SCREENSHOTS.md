# Настоящие Android screenshots V1.1

Android15/API35 x86_64, AVD Replika35v11 / WHPX / 432×936 / 180dpi / 4096-byte pages. Снимки сняты UIAutomation.takeScreenshot либо adb screencap; макеты и генерация изображений не использовались. APK SHA-256: `9728e09fe8f6b0d66b4c038f5a71752c21602db5c72e7013e3b80d0ea6668b6a`.

| Файл | Реальное состояние |
|---|---|
| 01-library.png | Библиотека двух результатов настоящих mono Worker |
| 02-recording.png | Активный MediaRecorder на виртуальном AVD -no-audio; не реальный микрофон телефона |
| 03-processing.png | Настоящий Worker, стадия проверки моделей |
| 04-transcript-workspace.png | Холодное открытие после force-stop; исправления и подпись видны в UI, fresh hierarchy проверена |
| 05-speaker-editing.png | Настоящее окно переименования участника после ручной смены ID |
| 05-segment-editing.png | Открытый редактор реплики |
| 06-smart-review.png | Реальная пустая очередь вычисленных предупреждений; качество ASR этим не доказано |
| 07-models-diagnostics.png | Переключатель ASR и проверенные model groups |
| 09-segment-editing-keyboard.png | Экранный IME действительно открыт в редакторе |
| 10-segment-editing-save.png | IME закрыт, доступны говорящий/проверка/Save; последующее сохранение проверено отдельно |
| 11-transcript-after-correction.png | Текст, ID и подпись сохранены, Activity recreation пройдена |
| 12-models-diagnostics-details.png | Прокрутка Models: pack, Benchmark Suite и начало диагностического JSON |
| 13-offline-pack.png | Контролы реального offline pack, не картинка установщика |
| 14-transcript-loading-transient.png | Открытый дефект: временный ложный empty-state до прихода Room Flow. Это прежний кадр04, сохранён без подмены |
| 15-diagnostics-timings.png | Дополнительная ручная прокрутка настоящего диагностического JSON |
| 16-speaker-count-fixed.png | WAV реально импортирован через Downloads, выбран fixed mode и1 участник до запуска |
| 17-corrupt-import-error.png | Обработанный Media3 Source error после выбора повреждённого fixture |
| 18-saf-wav-transcript.png | Настоящий новый WAV pipeline с fixed1, без ручных правок |
| 19-corrupt-worker-error.png | Последующий Worker ERROR для повреждённого файла, приложение работает |

Raw transcript/diagnostics относятся к реальному русскому одноголосному WAV. Надпись «проверено», новый ID и имя «Проверенная подпись» добавлены **вручную QA-сценарием** для тестирования редактора и экспорта. Это не второй настоящий участник и не результат диаризации. Оригинальный результат модели хранится отдельно в android-transcript.json до правок.

Не воспроизведены визуально: физический микрофон, low storage, положительные предупреждения русского многоголосного диалога, длительное ожидание отмены активного JNI, large-font/TalkBack и пустая Library. Их нет среди подтверждённых screenshots. Первоначальный кандидат и его неудачный UI-прогон сохранены в соседнем integration-v1.1; итоговая проверка UI2 и process-relaunch1 прошла.
