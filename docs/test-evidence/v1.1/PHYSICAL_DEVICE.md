# Физический Android: BLOCKED

Проверка окружения 31.10.2026: Linux `/mnt/f/ReplikaToolchain/sdk/platform-tools/adb devices -l` и Windows `F:\ReplikaToolchain\windows-tools\platform-tools\adb.exe devices -l` вернули пустые списки. Физический arm64 Android не подключён и не проверен. Прогон эмулятора не закрывает этот блокер.

В этой WSL/Windows сессии для эмулятора использован отдельный Windows ADB server на порту **5038**: порт 5037 пересекался с Linux ADB и не видел Windows AVD. Команды PowerShell ниже явно выбирают 5038. Это транспорт тестовой среды, не настройка телефона. Для другой машины можно использовать стандартный порт 5037.

## Подключение

1. На собственном тестовом телефоне включить Developer options → USB debugging, подключить USB-кабелем с передачей данных, разблокировать экран и подтвердить RSA-ключ этого компьютера. Не устанавливать посторонние APK и не менять другие системные настройки.
2. В PowerShell выполнить:

```powershell
$adb = 'F:\ReplikaToolchain\windows-tools\platform-tools\adb.exe'
& $adb -P 5038 devices -l
```

3. Если виден `unauthorized`, подтвердить запрос на телефоне; если пусто — проверить кабель, USB-порт и официальный USB-драйвер производителя. Для WSL не требуется пробрасывать USB: использовать Windows adb.exe. Если устройств несколько, во всех дальнейших командах указывать `-s SERIAL`. Не просматривать содержимое чужих каталогов, медиатеки, звонков и сообщений.
4. Проверить только системные свойства:

```powershell
$serial = 'SERIAL_FROM_ADB'
& $adb -P 5038 -s $serial shell getprop ro.product.manufacturer
& $adb -P 5038 -s $serial shell getprop ro.product.model
& $adb -P 5038 -s $serial shell getprop ro.build.version.release
& $adb -P 5038 -s $serial shell getprop ro.build.version.sdk
& $adb -P 5038 -s $serial shell getprop ro.product.cpu.abilist
& $adb -P 5038 -s $serial shell getprop ro.soc.model
& $adb -P 5038 -s $serial shell getconf PAGESIZE
& $adb -P 5038 -s $serial shell cat /proc/meminfo
```

Нужны API ≥26 и arm64-v8a; предпочтительно API35/36. Наличие 4096-байтных страниц не проверяет 16 KiB runtime. Сохранить вывод, точный APK SHA-256, режим питания и температуру. Пустой `ro.soc.model` записать как неизвестный, не подставлять предполагаемый процессор.

## Установка и независимая проверка

```powershell
$project = 'F:\Hackathons\ReplikaAndroid'
Get-FileHash "$project\app\build\outputs\apk\debug\app-debug.apk" -Algorithm SHA256
& $adb -P 5038 -s $serial install -r "$project\app\build\outputs\apk\debug\app-debug.apk"
& $adb -P 5038 -s $serial push "$project\model-pack\replika-offline-pack.zip" /sdcard/Download/replika-offline-pack.zip
```

Установить только собранный в этой итерации debug APK. Открыть REPLIKA → Модели → Импорт offline pack и выбрать этот ZIP. Дождаться проверки всех наборов. Зафиксировать ошибки и доступное место. Существующие аудиозаписи приложения не удалять. Pack не добавлять в Git или review ZIP.

Микрофон проверять только после отдельного согласия владельца телефона и участников. Этот документ не является разрешением записывать разговор или автоматически выдавать RECORD_AUDIO. Без согласия отметить microphone как BLOCKED; остальные сценарии продолжить.

Для offline-проверки владелец вручную включает авиарежим, отключает Wi-Fi и подтверждает отсутствие связи. Не переключать настройки телефона автоматически. Импортировать публичные разрешённые fixtures WAV/MP3/M4A через системный picker. Проверить длительность и звук каждого формата, затем запустить настоящие модели. Для русского многоголосного теста использовать согласованный диалог и ручную разметку из ML-протокола; последовательная склейка одноголосных файлов не доказывает качество естественного диалога.

Проверить:

- VAD → диаризация → выбранный ASR → Room → UI → JSON/TXT/SRT export; сохранить фактические JSON и diagnostics в отдельный каталог прогона.
- Auto speaker count и известное число участников на одном аудио; не выбирать глобальный threshold по одному результату.
- Нажатие сегмента, начало/конец фрагмента, seek, подсветку; текст, speaker ID, имена и состояние Smart Review после force-stop/relaunch; экспорт должен отражать исправления.
- Уход в фон и возврат во время inference и воспроизведения, поворот экрана, повторное нажатие processing, отмену между этапами и во время JNI; не считать нажатие Cancel доказательством немедленной остановки native.
- Повреждённый импорт без падения и без потери прежних стенограмм; нехватку места проверять на отдельном тестовом устройстве без заполнения личного телефона.
- Share через выбранное пользователем локальное приложение; сетевую отправку выполнять только по его явной инструкции.
- Микрофон при полученном согласии: запись, отказ permission, пауза/продолжение, фон, сохранение, воспроизведение. Запись в фоне должна ставиться на паузу.

Не запускать параллельные ML-прогоны. Cold run — после force-stop, warm run — повтор с теми же входом/параметрами; обозначать ограничения OS file cache. Снимать память отдельно во время каждой стадии, например `adb -s SERIAL shell dumpsys meminfo ru.replika.offline`. Диагностический `finalPssKb` не равен peak RSS/PSS. Замеры эмулятора не переносить на телефон. Для WER/CER/DER нужен независимый ручной reference.

## 16 KiB и современные Android

`python3 tools/verify_artifact.py` проверяет ZIP и ELF LOAD отдельно и сохраняет новый JSON. PASS означает статическую пригодность упаковки/загрузки, а не полный runtime PASS. Для закрытия 16 KiB требуется устройство или официальный 16 KiB image с `getconf PAGESIZE = 16384`, установка APK и полный inference с обеими ASR. Не включать 16 KiB режим владельцу телефона без отдельной договорённости и понимания перезагрузки.

API35: проверить foreground notification/отмену, возврат из фона, edge-to-edge и IME в редакторе. API36: дополнительно проверить длительную WorkManager-обработку с системными job quotas. Установлены SDK/image API35 и image API28; API36 image в текущем окружении отсутствует.

Официальные ограничения: [Android 16 KiB page sizes](https://developer.android.com/guide/practices/page-sizes), [foreground service timeouts](https://developer.android.com/develop/background-work/services/fgs/timeout), [foreground service changes, включая Android 16](https://developer.android.com/develop/background-work/services/fgs/changes). Android15 ограничивает суммарный dataSync/mediaProcessing foreground runtime; Android16 распространяет job quotas на работу, сопровождаемую foreground service. Проверка короткого WAV не подтверждает многочасовую стабильность.
