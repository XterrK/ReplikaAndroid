#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source tools/env.sh
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell pm grant ru.replika.offline android.permission.POST_NOTIFICATIONS || true
adb shell pm grant ru.replika.offline android.permission.RECORD_AUDIO
python3 tools/stage_android.py --pack
adb shell am instrument -w -e class ru.replika.ModelPackTest,ru.replika.StorageAudioTest,ru.replika.DiarizationTest,ru.replika.PipelineTest,ru.replika.NavigationTest ru.replika.offline.test/androidx.test.runner.AndroidJUnitRunner
