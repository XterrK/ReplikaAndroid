# Step 8 emulator checks (big import, progress, FGS timeout)

Only for your own emulator: the scripts refuse serials that are not `emulator-*`.
Environment: `ANDROID_HOME`, optional `REPLIKA_EMULATOR` (default `emulator-5580`).
Run Python with `-I`; the scripts add their own folder to `sys.path`.

Test files are generated on the PC from real speech (any 16 kHz mono WAV of 2 h or more):

```
ffmpeg -i long-120m.wav -c copy replika-2h-16k-mono.wav                             # 232 MB, copied on import
ffmpeg -i long-240m.wav -t 11700 -ar 48000 -ac 2 -c:a pcm_s16le replika-3h15m-48k-stereo.wav   # 2.25 GB, imported without a copy
ffmpeg -i replika-2h-16k-mono.wav -af "atrim=0:180,apad=whole_dur=3000" -ar 48000 -ac 2 -c:a pcm_s16le replika-50m-speech3m-48k.wav  # 576 MB
ffmpeg -f lavfi -i "nullsrc=s=320x240:r=25,geq=random(1)*255:128:128" -t 60 -c:v libx264 -preset ultrafast -b:v 2M -g 50 -pix_fmt yuv420p clip.mp4
ffmpeg -stream_loop 130 -i clip.mp4 -i replika-2h-16k-mono.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 64k -t 7200 replika-2h-video.mp4   # 1.88 GB
adb -s emulator-5580 push <files> /sdcard/Download/
adb -s emulator-5580 shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Download/<file>
```

- `ui.py show|tap <regex>|wait <regex>|shot <png>`: uiautomator helper.
- `pick.py <file>`: Import → system picker → Downloads → file.
- `scenario_ready.py <file> [mode-regex]`: import, process, log the stage/percent/ETA every 10 s, save screenshots.
- Out-of-space checks: `adb shell fallocate -l <N>M /data/local/tmp/filler.bin` (delete afterwards).
- FGS time limit: `adb shell device_config put activity_manager media_processing_fgs_timeout_duration 60000`,
  start processing, press Home, wait about 70 s; `device_config delete …` restores the default.
