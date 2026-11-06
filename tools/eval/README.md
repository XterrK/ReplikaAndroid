# Evaluation stand

Baseline reproduces current V1.6/V1.5 ML on canonical16k monoPCM16 WAV. References stay outside inference. The code does not train models, tune weights, alter recognition text or call cloud services. Full metric definitions: [SCORING.md](SCORING.md). Results: [docs/TEST_RESULTS.md](../../docs/TEST_RESULTS.md).

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

## Android bridge and paired scoring

Install a matching debug/testAPK and use an explicit serial, preferably a dedicated fresh AVD. The bridge invokes the unchanged productionWorker and exports actual Jury JSON/diagnostics. It does not put eval UI or a filesystem intent into the production application. Only audio/id/SHA are staged; text and speaker-count gold remain on the host.

```bash
local-dev/eval-venv/bin/python tools/eval/pull_and_score.py   --serial emulator-5556 --audio-root "$REPLIKA_EVAL_AUDIO"   --host-run artifacts/test-results/my-fresh-baseline   --cases dev-01-two-clean dev-03-short holdout-02-three-clean holdout-04-overlap-expressive dev-mono-s   --output artifacts/test-results/my-fresh-native --install --stage-models --offline
```

--stage-models and automatic offline switching are emulator-only. Model staging stops the QA app before copying, never wipes data; use a dedicated AVD. A physical device needs explicit --allow-physical and existing normal model provisioning. Successful QA rows use UUIDs and only their own rows are cleaned; inputs and failed records remain for diagnosis. Cancellation requests target only the own QA job, with the existing non-immediate JNI limitation.

The user clarified the0.5percentage-point gate applies to total errors/total reference words on the fixed paired corpus. Each per-file delta/outlier remains visible. To compare preserved native inference after a host-port correction without rerunning or rewriting it:

```bash
local-dev/eval-venv/bin/python tools/eval/compare_ports.py   --native-run artifacts/test-results/my-fresh-native   --host-run artifacts/test-results/my-corrected-host   --output artifacts/test-results/my-fresh-port-comparison
```

That operation is marked new_model_inference=false and validates matched inputs/policies. It does not make old native outputs represent a new model/planner. Exact equality across Linux/Android builds is not claimed: retained baseline has one Skeleton/скелетон difference, while corpus delta0.226pp passes. Current numerical decoder emulator is verified bit-exact against actual captured AndroidPCM; it reproduces existing behavior rather than improving AndroidASR.
