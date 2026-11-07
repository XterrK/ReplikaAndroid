# Evaluation stand

Baseline reproduces V1.6/V1.5 ML on canonical16k monoPCM16 WAV. References stay outside inference. Models run locally without training or weight tuning; the actual recognition text remains in diagnostics. Experimental seam profiles explicitly test punctuation/case changes and are scored separately. Full metric definitions: [SCORING.md](SCORING.md). Results: [docs/TEST_RESULTS.md](../../docs/TEST_RESULTS.md).

## Setup and corpus

Tested on Linux/WSL Python3.12. Use the pinned requirements; keep environments/audio outside tracked source:

```bash
python3 -m venv local-dev/eval-venv
local-dev/eval-venv/bin/pip install -r tools/eval/requirements.lock.txt
export REPLIKA_EVAL_AUDIO=local-dev/eval-audio
local-dev/eval-venv/bin/python tools/eval/prepare_corpus.py --audio-root "$REPLIKA_EVAL_AUDIO"
# Verify/regenerate from existing source cache without network:
local-dev/eval-venv/bin/python tools/eval/prepare_corpus.py --audio-root "$REPLIKA_EVAL_AUDIO" --offline
local-dev/eval-venv/bin/python -m unittest discover -s tools/eval/tests -v
```

Corpus metadata/references/license are committed under benchmark/eval. Raw sources and generated audio stay under --audio-root and are not app assets. Selection uses pinned author val/test CSVs and publisher LFS hashes; initial unavailable-file attempts are retained. Montage boundaries are author clip placement intervals, not manually annotated natural dialogue speech activity. Do not use ASR hypotheses as gold.

## Host run

```bash
local-dev/eval-venv/bin/python tools/eval/run.py   --manifest benchmark/eval/manifest.json --audio-root "$REPLIKA_EVAL_AUDIO"   --model-root model-pack --config configs/eval/baseline-v16.json   --output artifacts/test-results/my-fresh-baseline
```

The default baseline is automatic−1 on every file. Manifest expected_speakers is never passed to inference. Current models must match models-lock; every invocation hashes required files. --split dev/holdout/all and --cases select explicit cases. Do not tune on holdout. New model/parameter behavior belongs to a later task and requires separate configuration/evidence before Android integration.

Each case saves reference.json, hypothesis.json, diagnostics.json, metrics.json and case.json; raw blank ASR slices/tokens/timestamps remain in diagnostics. Corpus summary and results.csv retain counts/denominators and native versus export speaker metrics. Timing includes host validation/decoding/VAD/diarization/ASR, not scoring/persistence. Linux high-water RSS is whole-process memory, not a phone/Android peak.

Existing output is rejected by default. --resume is permitted only for identical config/code/helper/dependencies/model/audio/reference fingerprints. Saved artifact hashes are rechecked. Incomplete attempts are moved under attempts/, not deleted; failures get a CSV row. Choose a fresh output after code/config changes.

Task D's experimental `vad_words_v1` pipeline is separate from the frozen `v16`
helper. `configs/eval/vad-words-context600.json` preserves the VAD/model/gain
settings and adds 600 ms of actual preceding ASR context. Real token-emission
times drive word speaker assignment; they are timing estimates, not forced
alignment. The failed earlier VAD profile and all original outputs remain saved.
[Task D report](../../docs/STEP_03_VAD_WORD_ASR.md) separates dev selection,
original holdout and the independent `benchmark/eval-reserve` checks.

**WER/CER/cpWER/DER are error rates (lower is better).** A 3% WER is about three
edits per hundred reference words, not a 3% success rate. Speaker-count exact
rate, punctuation F1 and case accuracy have the opposite direction.

## Android bridge and paired scoring

Install a matching debug/testAPK and use an explicit serial, preferably a dedicated fresh AVD. The bridge invokes the production Worker with an explicit profile and exports actual Jury JSON/diagnostics. It does not put eval UI or a filesystem intent into the production application. Only audio/id/SHA are staged; text and speaker-count gold remain on the host.

```bash
local-dev/eval-venv/bin/python tools/eval/pull_and_score.py   --serial emulator-5556 --audio-root "$REPLIKA_EVAL_AUDIO"   --host-run artifacts/test-results/my-fresh-baseline   --cases dev-01-two-clean dev-03-short holdout-02-three-clean holdout-04-overlap-expressive dev-mono-s   --output artifacts/test-results/my-fresh-native --install --stage-models --offline
```

--stage-models and automatic offline switching are emulator-only. Model staging stops the QA app before copying, never wipes data; use a dedicated AVD. A physical device needs explicit --allow-physical and existing normal model provisioning. Successful QA rows use UUIDs and only their own rows are cleaned; inputs and failed records remain for diagnosis. Cancellation requests target only the own QA job, with the existing non-immediate JNI limitation.

The bridge defaults to `--asr-plan v16`. A word-profile run needs, for example,
`--asr-plan vad_words_context600` and a completed host run using that same config.
Threads, expected-speaker mode and all seven profile fields are checked before
any ADB operation, then checked against the actual native report and diagnostics.
Word QA also requires complete token/timestamp/word payloads without truncation
or fallback. Rescoring cannot bypass that requirement.

Ordinary application builds retain `v16`. To build the explicit candidate:

```bash
python3 tools/build_portable.py :app:testDebugUnitTest :app:assembleAllInOne :app:assembleDebug :app:assembleDebugAndroidTest -PreplikaAsrPlan=vad_words_context600
```

The property chooses the default for newly enqueued requests. Historical
WorkData without a profile always stays legacy. Full token/word diagnostics are
QA-only and bounded; ordinary processing stores compact summaries. Candidate
quality/port gates do not establish the separate <200 ms word-timing target or
ARM/physical-phone performance.

The user clarified the0.5percentage-point gate applies to total errors/total reference words on the fixed paired corpus. Each per-file delta/outlier remains visible. To compare preserved native inference after a host-port correction without rerunning or rewriting it:

```bash
local-dev/eval-venv/bin/python tools/eval/compare_ports.py   --native-run artifacts/test-results/my-fresh-native   --host-run artifacts/test-results/my-corrected-host   --output artifacts/test-results/my-fresh-port-comparison
```

That operation is marked new_model_inference=false and validates matched inputs/policies. It does not make old native outputs represent a new model/planner. Exact equality across Linux/Android builds is not claimed: retained baseline has one Skeleton/скелетон difference, while corpus delta0.226pp passes. Current numerical decoder emulator is verified bit-exact against actual captured AndroidPCM; it reproduces existing behavior rather than improving AndroidASR.


## Task C: frozen C2 experiment

[Task C results and limitations](../../docs/STEP_04_DIARIZATION.md) distinguish
RU montage gates from the separate natural AMI diagnostic. C2 uses the original
seven-file pack; six alternative embedders were researched on the host. The
ordinary app default remains legacy; historical WorkData/manual K stay legacy.

A full C2 host run performs fresh VAD, native SD, clean-window embedding,
window clustering and GigaAM inference. Always pass the explicit C2 config;
the runner's default provisional policy is C1:

```bash
local-dev/eval-venv/bin/python tools/eval/run_refined.py \
  --audio-root "$REPLIKA_EVAL_AUDIO" --embedding-root local-dev/diar-models \
  --config configs/eval/c2-window-selected-full.json \
  --output artifacts/test-results/my-fresh-c2-host
```

Build matching candidate APKs with both flags:

```bash
python3 tools/build_portable.py :app:testDebugUnitTest :app:assembleAllInOne \
  :app:assembleDebug :app:assembleDebugAndroidTest \
  -PreplikaAsrPlan=vad_words_context600 -PreplikaDiarPlan=eres2net_window_v1
```

C2 has a separate strict collector; the frozen baseline/D collector is unchanged.
It requires the complete ten-file union of dev8 and historical fixed5. References
remain local. Native model/APK hashes, real512dim windows, private QA sidecar,
Python replay and token/word/Jury reconstruction are checked. WER0.5pp applies
only to weighted fixed5; dev7/8 and fixed-V1.6 DER+2pp are separate gates.

```bash
local-dev/eval-venv/bin/python tools/eval/pull_refined_android.py \
  --serial emulator-5556 --audio-root "$REPLIKA_EVAL_AUDIO" \
  --host-run artifacts/test-results/my-fresh-c2-host \
  --output artifacts/test-results/my-fresh-c2-native --check
# After preflight, repeat with --check removed; --install and --offline are explicit.
```

Read-only --check performs no ADB, output creation or inference. Every actual run
uses a fresh output. Source/code/input/model fingerprints are rechecked; failed
attempts remain evidence. Temporary emulator stay-on settings are restored.
Native windows are explicit bounded QA files outside Room; normal diagnostics
stay compact. Current C2 runtime acceptance is pending; see STATUS. Neither a
unit-test PASS nor low normalized WER establishes natural-dialogue, word-time,
ARM or phone-performance acceptance.
