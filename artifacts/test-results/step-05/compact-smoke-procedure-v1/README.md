Prepared short compact-QA smoke; actual Android has not been executed.

Both local preflights and eight controlled tests pass. The tests use mock ADB and transformed saved full-QA data; they do not prove actual QA=false behavior. The frozen performance runner validates auto2 compact output and scores author text only on the host. A separate narrow legacy1 checker requires ASR1/SD2/ref2 and pinned stage flags without altering native metadata or the frozen strict2 C acceptance validator.

Execution is root-owned, after the current Android NN run is terminal. Each profile uses a fresh distinct output and fresh one-case remote batch. The script checks local/installed APKs and all seven model hashes before inference, wakes the emulator, restores initial stay-on 1 in finally, and preserves available outputs after instrumentation failure. It installs, clears, wipes and force-stops nothing. A restoration failure returns nonzero and preserves any preceding error.

Without `--execute` the script performs local preflight only and invokes no ADB/subprocess or output mkdir.

```bash
/home/egor/replika-toolchain/host-venv/bin/python /home/egor/replika-toolchain/evidence/step05-compact-smoke.py --repo /mnt/d/ReplikaAndroid/ReplikaAndroid --audio-root /home/egor/replika-toolchain/eval-audio --check
/home/egor/replika-toolchain/host-venv/bin/python /home/egor/replika-toolchain/evidence/step05-compact-smoke.py --repo /mnt/d/ReplikaAndroid/ReplikaAndroid --audio-root /home/egor/replika-toolchain/eval-audio --execute
/home/egor/replika-toolchain/host-venv/bin/python /home/egor/replika-toolchain/evidence/step05-compact-smoke.py --repo /mnt/d/ReplikaAndroid/ReplikaAndroid --audio-root /home/egor/replika-toolchain/eval-audio --execute --profile legacy-c2-moderate-one
```

The 6.333-second dev-mono-s audio is duplicate contract evidence. It is outside the controlled 1/3/10 performance protocol and does not establish model-quality acceptance, full token/vector replay, causal speed or phone/ARM performance.
