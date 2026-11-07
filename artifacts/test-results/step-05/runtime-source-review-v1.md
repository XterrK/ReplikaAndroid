# Focused task 5 runtime source review

Reviewed at 2026-11-07T08:44:33.867493+00:00. Base: `87f669a`. Outcome: **no confirmed new Android production defect found in the reviewed changes; no source/APK change recommended by this review**.

Scope: targeted production and host CPU-policy changes within the task5 tracked diff, plus new CpuPlan. Covered CPU defaults/persistence, effective stage threads, thermal getter/listener/cancellation lifecycle, and UI dispatch. A separate agent independently inspected AppViewModel/WorkspaceScreen and import call boundaries and also reported no concrete new bug. This is a scoped source review, not proof that the entire application has no bugs.

No ADB, SDK installation, Gradle, neural inference, new tests, Git mutation or production edit was performed. Existing JVM/Python/device evidence was not rerun.

## Checked paths and behavior

- `ProcessingWorker.kt:44–46,68,460–470`: missing historical plan keys resolve through persisted legacy IDs, independent of new APK defaults. enqueue stores request0 only for explicit AUTO_V1; legacy default remains2. CPU is resolved again against actual available cores when Worker starts.
- `CpuPlan.kt:8–23` / `TranscriptPresentation.kt:71–76`: auto uses the declared floor bucket from1/2/4 under clamp(cores−1,1,4), normalizes unavailable core counts, preserves explicit1/2/4 and rejects legacy request0. Legacy refined C2 pins SD/refinement2 while respecting ASR1. Worker164/183 passes the corresponding stage counts to the real SD and embedding adapter. Manual/single modes bypass the automatic refiner as before.
- `PipelineTelemetry.kt:115–160`: listener registration failure does not disable getter polling; a valid SEVERE getter still blocks. Unknown/read-failed status becomes unavailable−1. Only known3..6 cool. CancellationException is propagated and the loop remains cancellable; listener cleanup is guarded and idempotent.
- `DiarizationRefiner.kt:99–105,172–218`: adaptive1/2/4 requires explicit AUTO_V1; default adapter remains strict2. Existing use/finally scopes still release extractor and streams on failure/cancellation.
- `AppViewModel.kt:149–164` and `WorkspaceScreen.kt:269–307`: auto0 is accepted only in an opt-in build, ordinary dispatch follows its default plan, explicit moderate1 is retained, and restored old ordinary2/4 UI state is normalized at dispatch. Busy/cancel flow was not changed.
- `AudioDecoder.kt`, `MediaImporter.kt`, `ImportJournal.kt`: targeted git diff against87f669a is empty; no new decoder/import/journal production implementation was introduced in this step.

## Residual risks and limits

1. **Existing JNI cancellation/thermal boundary, not a new regression.** `ProcessingWorker.kt:168` calls synchronous `sd.process(samples)`; cancellation is checked at169 and SD release is in finally172. Thermal checks occur at surrounding guards, not inside that native call. A long native operation can therefore outlive a UI cancellation request or instrumentation timeout. The existing UI text at `WorkspaceScreen.kt:282` correctly explains that limitation. A timeout is not proof of terminal JNI; retain the separate terminal-process evidence. No model/SDK rebuild or cancellation redesign is proposed here.

2. **Low-risk host producer validation edge; no demonstrated actual-result corruption.** `tools/eval/run_refined.py:177` compares `cpu.get("vadThreads") != 1` without an exact-int check, so synthetic boolean True would pass that one producer-side comparison. The actual producer writes literal integer1 (`pipeline_refined.py:332`), and the strict native collector checks the exact int type (`pull_refined_android.py:105`). Other execution-thread fields are type-checked. This does not invalidate the observed actual runs or require an Android/APK change; it is a narrow future host-validator hardening opportunity.

Physical ARM behavior, physical heat, and speed are not established by source review. The frozen candidate APK is not rebuilt or modified.

## Source SHA256 at review

| Path | SHA256 |
|---|---|
| `app/build.gradle.kts` | `5653e4499b00bd06f4f1ab5791011bce5ed4a43fab5c78f1b96701e732ba8548` |
| `app/src/main/java/ru/replika/domain/CpuPlan.kt` | `711ebbbd1f1d30dc72fb09faf1faf86bb1f670ecca30a0b0ef89f5292477b895` |
| `app/src/main/java/ru/replika/domain/TranscriptPresentation.kt` | `9c738a90adb14d0153592c1ed7e527255cf6fc27e0512f80d420a407fb0fb4aa` |
| `app/src/main/java/ru/replika/ml/ProcessingWorker.kt` | `0ee3b18ad616dd7bc32dbbd940f4077374ec48dd9142ace1e969025195506c8d` |
| `app/src/main/java/ru/replika/ml/PipelineTelemetry.kt` | `23e20f7fc10f567c41ac8e700d3ed87c8c1b119e5428e0d5c652f759170c56f8` |
| `app/src/main/java/ru/replika/ml/DiarizationRefiner.kt` | `155bcb2ed0a62d9aaa41595d76174b5e219d2a0a6b19ae111f7eee16ecd049a9` |
| `app/src/main/java/ru/replika/ui/AppViewModel.kt` | `bc58c951add266c6c398c5ca502459d4ccb0e87ebbc28eaf1a83eb5c61c68552` |
| `app/src/main/java/ru/replika/ui/WorkspaceScreen.kt` | `e7845640dddcad0a65a6d2866ad32f315151f5be9dc5294cedae0aa22c02e7f4` |
| `app/src/main/java/ru/replika/ml/AudioDecoder.kt` | `53cb484da019c62cca72f74c1930b50dabd934018aef47528eafbaf690b34b06` |
| `app/src/main/java/ru/replika/ml/MediaImporter.kt` | `2cf2d1347b20f877973781157cd714a78b08ee54d5751e35e3a8bf28eab1c257` |
| `app/src/main/java/ru/replika/data/ImportJournal.kt` | `8ce158cd5f1200f2fb1c1e1f6371dd1b06a24abfb99d2ec6cd9e264cc709230b` |
| `tools/eval/pipeline_refined.py` | `2de1516a85faeed8b12a93a017a23fc4bede38f6fb03e78e89837a26a1c17229` |
| `tools/eval/run_refined.py` | `fa8d297d64c00aad467a72ac08f6543727289f80acd99483f0368c1ad61d883c` |
| `tools/eval/native_diar_policy.py` | `3cbd379c545b3d6206a5afc52817c34ae601836fae38cc808c6972e651c407df` |
| `tools/eval/pull_refined_android.py` | `a1f0524e5c0a814514143ff3db93c393bd9161dff9a6a2ac0c3a7e9ccee8ec5a` |
