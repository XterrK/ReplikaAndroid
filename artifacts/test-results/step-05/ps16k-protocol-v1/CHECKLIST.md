Prepared only: no ADB, SDK, Gradle, Git or neural inference was executed by this protocol author. Execute in the frozen order in `protocol.json`, using fresh evidence directories. Scope: API35/x86_64/16 KB runtime and offline-pack compatibility; ARM/phone and performance remain unestablished.

1. Bind the new build and device. Use `allInOneQa` and its matching instrumentation APK, isolated application `ru.replika.offline.aioqa`, test application `ru.replika.offline.aioqa.test`. Verify actual APK manifests/BuildConfig targets, SHA256, size, signer and installed APK equality. Do not reuse debug/test APK hashes from the previous normal package. Preserve the initial missing-testBuildType build failure. The required build command is:

   ```bash
   python3 tools/build_portable.py \
     -PreplikaTestBuildType=allInOneQa \
     -PreplikaAsrPlan=vad_words_context600 \
     -PreplikaDiarPlan=eres2net_window_v1 \
     -PreplikaCpuPlan=auto_v1 \
     :app:assembleAllInOneQa :app:assembleAllInOneQaAndroidTest
   ```

   Keep `replikaAioQaSameId` absent/false. `allInOne` is ARM64-only; `allInOneQa` is x86_64. Fresh device: `emulator-5558`, API35, x86_64, two cores. Capture build fingerprint, image revision5 and `adb -s emulator-5558 shell getconf PAGE_SIZE` == **16384**. Verify APK ZIP alignment with `zipalign -c -P 16 -v 4 APK` and every packaged ELF LOAD alignment >=2**14. These are the [official 16 KB checks](https://developer.android.com/guide/practices/page-sizes).

2. Save screen/network/backcompat state on the dedicated new VM. Wake with `KEYCODE_WAKEUP`, dismiss keyguard, enable stay-on temporarily, use the actual component `ru.replika.offline.aioqa/ru.replika.MainActivity`, and verify Awake/RESUMED before UI polling or Worker. Save/read back original values and restore in finally, including failures. On this fresh VM only, the official [backcompat-off values](https://developer.android.com/guide/practices/page-sizes#16-kb-backcompat-mode) are:

   ```bash
   adb -s emulator-5558 shell setprop bionic.linker.16kb.app_compat.enabled false
   adb -s emulator-5558 shell setprop pm.16kb.app_compat.disabled true
   ```

   Record original property values and readback; unsupported writes are a limitation, not proof that fallback was disabled. No adb-root, Manifest modification, existing AVD wipe or data clearing of `ru.replika.offline` is part of this protocol.

3. Run the existing non-NN cold provisioning harness, before any real Worker. **ANDROID_SERIAL is mandatory**: this harness does not supply `-s` itself.

   ```bash
   ANDROID_SERIAL=emulator-5558 \
   /home/egor/replika-toolchain/host-venv/bin/python \
     tools/test_bundled_first_launch.py \
     --adb /home/egor/replika-toolchain/android-sdk/platform-tools/adb \
     --output artifacts/test-results/step-05/ps16k-cold-provision-v1
   ```

   The existing harness force-stops/clears only isolated `.aioqa` for clean/interrupted starts. Stage no external models or ZIP. Require clean offline preparation of all seven files; a different provisioning run with unchanged model file stat rows and zero extraction; then an actual observed staged partial interruption, no premature live publication, and resumed reuse/publish. If the interruption race is not observed, preserve the failure and do not claim success. Capture `environment.json`, `01-clean-offline.json`, `02-cold-restart.json`, `02-preserved-model-times.json`, `03-interruption.json`, `04-resumed-offline.json`, `summary.json`, UI XML and PNGs, plus raw command log/stdout/stderr. Check actual network restoration afterward; the harness restores its observed prior airplane/wifi/data state.

4. Execute only the existing prepared-file hash method, not the entire acceptance class:

   ```bash
   adb -s emulator-5558 shell am instrument -w -r \
     -e class ru.replika.AllInOneAcceptanceTest#preparedBundleHashesAndNoExtractionOnRepeatedLaunch \
     ru.replika.offline.aioqa.test/androidx.test.runner.AndroidJUnitRunner
   ```

   Pull `run-as ru.replika.offline.aioqa cat files/all-in-one-prepared-models.json` into a fresh host proof file. Require that the proof was actually created after this invocation, all seven SHA/size/group records match `models-lock.json`, and repeated readiness preserves mtimes. `OK` with an assumption/skip and no new proof is insufficient. `differentProcessObserved=false` on this first hash check is not a failure; cold restart evidence comes from the harness. Do not call `currentGigaWorkerUsesAutomaticallyPreparedBundle`: it invokes the legacy pre-roll100 test and is incompatible with context600.

5. Stage exactly one fresh safe `evalRun`, containing only `audio/dev-mono-s.wav` and the exact `batch.json` shape from the protocol. Canonical audio source is `/home/egor/replika-toolchain/eval-audio/dev/dev-mono-s.wav`, duration6333ms, SHA256 `97943f4d90c2b56166031263a6820c41e0f80b94643a9d3737327debdc8fbe53`. No author reference, true speaker count, transcript or model files enter the batch. Verify the already provisioned seven remote model hashes before NN. Root supplies a fresh safe run name in:

   ```bash
   adb -s emulator-5558 shell am instrument -w -r \
     -e evalRun FRESH_SAFE_RUN_NAME \
     -e evalThreads 0 -e evalExpectedSpeakers -1 \
     -e evalCpuPlan auto_v1 \
     -e evalAsrPlan vad_words_context600 \
     -e evalDiarPlan eres2net_window_v1 \
     -e evalCollectEvidence true \
     -e class ru.replika.EvaluationBatchTest#stagedCanonicalInputsThroughProductionWorker \
     ru.replika.offline.aioqa.test/androidx.test.runner.AndroidJUnitRunner
   ```

   This is **CPU request0**, not explicit1: on two observed cores require actual ASR1/SD1/refinement1 and both stage pins false. Paired completed host is `artifacts/test-results/step-05/cpu-host-threads1`. Full-QA is deliberately true for the single short actual JNI run. The internal per-case wait remains20min; preserve timeout/partial evidence and do not equate a cancellation request with terminal JNI.

6. Pull available outputs even after failure, from `files/evaluation/FRESH_SAFE_RUN_NAME/output/`: `report.json`, `dev-mono-s.case.json`, `dev-mono-s.hypothesis.json`, `dev-mono-s.diagnostics.json`, `dev-mono-s.diarization-evidence.json`. Capture raw instrumentation output and final device/power/properties. Bind native report/case by exact object equality, equal positive PID, fresh work/recording UUIDs, input hash and clock. Full-QA instrumentation verifies READY and actual sidecar work ID; it does **not** emit compact-mode `workManagerState=SUCCEEDED`, so do not invent that evidence.

7. Validate on the host with existing pure APIs, using `cpu_plan="auto_v1", threads=1, requested_threads=0`: `validate_native_diar_policy` on report/diagnostic; `validate_diarization_evidence` on the actual bytes and case; `native_policy.validate_word_evidence`; exact `reconstruct_jury(diag,6333)` equality with the exported hypothesis; then `pull_refined_android.score_case` against the independent host-only reference. Require full nontruncated actual512-vectors, resource counts/release, exact pure C2 replay and frameStride40. Preserve references/hypotheses/metrics/source hashes locally. The frozen full10 collector CLI intentionally rejects a one-case subset: reuse its validators, not its full-cohort execution command.

No new quality threshold, ARM acceptance or speed claim follows from this duplicate six-second compatibility smoke. Restore and verify original screen/network/backcompat settings; preserve failures and APK/source receipts instead of overwriting them.
