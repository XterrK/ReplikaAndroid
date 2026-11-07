# Step 8 emulator protocol (07.11.2026, own AVD only)

AVD `ReplikaImport35`: `system-images;android-35;default;x86_64`, 4 vCPU, 4 GB RAM, data 8 GB,
Java heap growth limit 192 MB, WHPX. APK `allInOneQa` (x86_64, models embedded) from this branch.
All commands used `adb -s emulator-5580`. The physical phone was never touched.
Files were generated on the PC from real speech and pushed to `/sdcard/Download`, then picked
in the system picker (Downloads root).

## 2 h WAV (232 MB, 16 kHz mono): copied, single-speaker processing, cancel
    import: "Копирование аудио · 218 из 232 МБ" -> recording 120:56, files/audio/<id>.audio 232208046 B
    15:51:13 Поиск речи · 48 % | Осталось ≈ 12 мин | Обработано 59:01 из 120:56
    15:52:12 Поиск речи · 79 % | Осталось ≈ 13 мин | Обработано 95:39 из 120:56
    15:52:51 Загрузка модели распознавания | Поиск речи · 100 %
    15:53:15 Распознавание · 9/1025 | 0 % | Осталось ≈ 13 мин | Обработано 00:40 из 120:56
    15:53:55 Распознавание · 25/1025 | 2 % | Осталось ≈ 43 мин
    15:54:54 Распознавание · 56/1025 | 5 % | Осталось ≈ 34 мин | Обработано 06:25 из 120:56
    cancel -> "Обработка остановлена", cache/ has no PCM

## 2.25 GB WAV (3 h 15 min, 48 kHz stereo): imported without a copy
    import ~1 s, files/audio unchanged, /data free unchanged (2622112 KB -> 2622096 KB)
    dumpsys activity permissions: persistable=0x3 persisted=0x1 for ru.replika.offline.aioqa
    duration 195:00; processing decodes from content URI: "Декодирование · 3 %, Обработано 06:29 из 195:00"

## Android 15 FGS limit (media_processing_fgs_timeout_duration=60000, app in background)
    dumpsys: isForeground=true types=0x00002000 (mediaProcessing)
    E ActivityManager: FGS (mediaProcessing) timed out: ... SystemForegroundService
    I WM-SystemFgDispatcher: Foreground service timed out, FGS type: 8192
    run 1 (first build): ERROR, "Android остановил долгую фоновую обработку…"
    rerun before race fix: WorkManager's rescheduled attempt overwrote it with a generic error
      ("Calls to setForegroundAsync() must complete…") -> fixed (settleStop for stopped workers,
      timeout error kept); runs 3–5 on the final APK: 3/3 timeout message, 0 crashes

## Cancel mid big import (MP4 1.88 GB, 2 h, AAC): PCM path
    "Подготовка звука · 4 МБ" + .wav 5382188 B + .pending marker -> "Отменить"
    -> files/audio has only the earlier recording, .pending-imports empty, no Room row

## Out of space (filler via fallocate in /data/local/tmp)
    free 630 MB, 2.25 GB WAV: "Недостаточно места: нужно около 816 МБ (временные данные распознавания
      749 МБ, запас 67 МБ), свободно 630 МБ. Освободите ещё 186 МБ и повторите импорт."
    free 630 MB, 232 MB WAV: copy+PCM does not fit, PCM fits -> imported without a copy
    free 400 MB, processing the 2 h no-copy recording: "Недостаточно места: для обработки нужно около
      532 МБ (временные данные распознавания 464 МБ и запас)…", cache/ empty

## No-copy 576 MB WAV (50 min, 3 min speech) -> transcript -> playback
    automatic speakers: "Для этой записи не хватает памяти…" (diarization heap check, 192 MB heap; not step 8)
    single speaker: READY in 144 s, player plays from content URI (00:00 -> 00:06 in 5 s, "Пауза")
    see scenario-50m-*.log
