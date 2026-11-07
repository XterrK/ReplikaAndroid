The current shell PATH does not contain adb. Actual root-owned execution therefore uses an explicit CLI path; the script itself has no hardcoded toolchain path. Run only after the current actual Android inference session is terminal and the read-only review is accepted.

```bash
/home/egor/replika-toolchain/host-venv/bin/python /home/egor/replika-toolchain/evidence/step05-compact-smoke.py --repo /mnt/d/ReplikaAndroid/ReplikaAndroid --audio-root /home/egor/replika-toolchain/eval-audio --adb /home/egor/replika-toolchain/android-sdk/platform-tools/adb --execute

/home/egor/replika-toolchain/host-venv/bin/python /home/egor/replika-toolchain/evidence/step05-compact-smoke.py --repo /mnt/d/ReplikaAndroid/ReplikaAndroid --audio-root /home/egor/replika-toolchain/eval-audio --adb /home/egor/replika-toolchain/android-sdk/platform-tools/adb --execute --profile legacy-c2-moderate-one
```
