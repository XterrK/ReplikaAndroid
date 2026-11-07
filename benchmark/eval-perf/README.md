# PLAN19 controlled performance proxy

Related controlled repeats of a previously evaluated acted dev montage; not independent recordings, natural dialogue, blind quality validation or word-time gold. Author text/actor IDs are retained; intervals remain whole author-clip timing proxies. No recognizer output, VAD or forced alignment enters corpus construction.

The frozen source is `dev-01-two-clean` at source SHA `80bdb11e4d9e313d2440c01b80babc0dbe319c9dbea371988ef62716ffb9d77b`.
Keep its first 6 complete author utterances through exact PCM
frame 842543 (52658.9375 ms), retain the
submillisecond clip tail omitted by the floored gold end_ms, and append
117457 zero samples to 60 seconds. Repeat this block
1/3/10 times. Author spelling, punctuation and actor IDs remain literal, with
integer 60000 ms shifts. No utterance/word is cut or invented.

The three recordings share the same six utterances and speakers. Their total
audio duration is 14 minutes, with 52.659 seconds of unique source-prefix
material. They measure length/repetition behavior; they are not a fresh quality
cohort, actor-disjoint data, natural dialogue or word timestamps. Do not pool
them with dev/holdout/reserve or describe repeated rows as independent examples.

Source is Langswap Dialogs, revision `a74ff44d8d27ca3d21098ea3ed4d31a32923fbdd`, under
the authors' custom OpenRAIL license, retained in `sources/LICENSE.md` and the
external audio root. Derived audio is not CC0 and must remain outside Git/APK.
Source metadata/reference/provenance snapshots and SHA pins are retained.

Reproduce in fresh directories (never overwrite):

```bash
python tools/create_plan19_perf_corpus.py \
  --source-audio-root /path/outside/repository/eval-audio \
  --audio-root /path/outside/repository/plan19-perf-v1 \
  --metadata-dir /path/to/new/perf-metadata-v1
```

Only canonical WAV/ID/SHA and global policies may enter Android. Reference
text and speaker counts stay on the host for independent post-inference scoring.

## Explicit Android performance driver

`protocol.json` fixes four batches in thread order **2, 4, 4, 2**, each with
the same 1/3/10-minute files in that order: twelve Workers, 56 minutes of audio.
Each triplet uses one instrumentation invocation and records its process ID;
separate instrumentation invocations may restart the process between batches.
CPU plan is `auto_v1`, with explicit requested threads 2/4 rather than a request
for automatic core mapping. Four threads can oversubscribe a two-core emulator.

The driver requires already installed app/test APKs with matching local SHA and
seven matching model files. It does not install, force-stop, clear app data or
send reference text/counts to the device. First perform local preflight:

```bash
python tools/run_plan19_perf.py --check --serial emulator-5556 \
  --audio-root /path/outside/repository/plan19-perf-v1 \
  --app-apk /path/to/app-debug.apk --test-apk /path/to/app-debug-androidTest.apk \
  --output /path/to/fresh/performance-output
```

`--check` creates no output and invokes no subprocess/ADB. Actual inference
requires replacing it with explicit `--execute`; the complete driver/device
path still needs the owner's review and actual run. A newly prepared alternate
metadata directory can reuse this frozen protocol via `--protocol`.

The QA bridge receives `evalCollectEvidence=false`. Production VAD, diarization,
real clean-window inference, refiner and ASR still execute; full token/vector
QA capture is disabled. Compact counts, balanced resource flags, exact policies,
WorkManager SUCCEEDED/UUIDs, actual ASR text and Jury JSON are checked. **This run
does not perform full token/vector replay.** Prior C2 replay evidence remains
separate and does not substitute for measurements on these longer inputs.

Per-case references/hypotheses/diagnostics/metrics and cumulative `results.csv`
are retained. Worker validation-through-ASR time, stage PSS/logcat and periodic
RSS/PSS/thermal snapshots have explicit scopes. Maxima of observations are not
continuous peak RAM. Sampling/instrumentation and uncontrolled host/device
conditions prevent causal speed claims. Forward/reverse pair ratios and raw,
normalized, cpWER and montage-DER values are descriptive; this adds no new
acceptance gate and does not establish natural-dialogue or ARM performance.
