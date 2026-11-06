> Latest acceptance: **[source11 —33/33 PASS](build11/README.md)** on the exact final source11 APK, including seven actual public studio-whisper Worker clips, fresh31 Android/Canvas PNGs and unchanged original AVD SHA. The earlier source10 evidence below remains preserved and must not be attributed to source11.

# Final Android 28 Canvas/runtime QA

**PASS: 32/32 selected instrumented cases on unchanged production build10.** Original native AVD profile432×936 at180dpi, app configuration384×760dp, system font1.0. Exact main/test APK hashes and per-suite results are in `FINAL_API28_RESULTS.json` and `installed-native-final-tests.json`. Only the test APK changed for the final glyph/focus assertion corrections; production APK was unchanged.

| Suite | Result |
| --- | --- |
| Media import, including AAC edit-list offset and priming |15/15 PASS|
| True API28 Canvas renderer, both themes/automatic+forced branches |1/1 PASS|
| Persisted import journal / actual Java NIO / Room references |8/8 PASS|
| Navigation |1/1 PASS|
| Orb gestures/accessibility independent of recording signal |1/1 PASS|
| Home export JSON/chooser/return, mono player/seek |2/2 PASS|
| Both themes/screens/IME, save+Undo, persisted appearance, virtual recording |4/4 PASS|

`build10-ui/` contains31 fresh native-profile PNGs:24 screen/state captures for both themes,3 virtual-recorder states,4 isolated renderer fixtures. Full headers, controls and bottom navigation were visually checked. All transcript/library content is controlled UI fixture data using the parent-designated public WAV; no old records/private databases were collected. Virtual microphone input is emulator-only. Recording was paused, resumed, saved, decoded and reopened; it is not evidence about the physical vivo X300 microphone.

API28 cannot run RuntimeShader. Old renderer test files named `agsl` exercise automatic Canvas fallback here; saved filenames honestly say `canvas-automatic-api28`. AGSL execution is not claimed. Isolated renderer fixtures retain the test-window background; actual Dark Home captures use neutral graphite. Keyboard is the AOSP input method with its own theme.

## Investigations retained honestly

Build7 exposed a real old-platform MP4 issue: Android9 MediaExtractor normalized delayed AAC timestamps to0 while a leading empty MP4 edit remained. Exact framework output and original ISO-BMFF boxes are retained in `mediaextractor-format-probe-api28.txt` / `aac-offset-boxes.json`. The defect and related cancellation path were fixed; all15 final real codec tests pass.

Initial Home tests used an unavailable `com.android.intentresolver` package and then a stale API28 accessibility root for return detection. Focus traces proved that Back had returned to MainActivity. The final test checks the real Activity window focus/lifecycle and passes; JSON/current Room text and actual chooser checks remain. An overly broad TextLayoutResult.hasVisualOverflow assertion also flagged a one-line glyph run because paragraph allocation was wider than the visible text. Final tests check actual glyph/line bounds and still reject the genuine former multi-line Stop regression.

A runtime attempt to shrink this old emulator via wm size/density produced cropped compositor images and an AOSP SystemUI ANR. `build10-invalid-wm-override/` is diagnostic-only and explicitly excluded from compact pixel acceptance. The source AVD profile was restored; SystemUI was recovered using its exact confirmed Close App button, no blind Back. Final32 cases and31 valid PNGs were rerun on the original native profile. Compact360×640 and enlarged fonts are accepted separately on the primary API35 device, not claimed from invalid API28 crops. This was SystemUI, not an application ANR.

## Isolation and preservation

Owned emulator5558 ran with `-read-only -no-snapshot -no-window`; primary5556 never received package/settings mutations from this task. Read-only instances discard guest disk changes on exit; see the [Android Emulator release notes](https://developer.android.com/studio/releases/emulator). Prior0.1.0 app data was cleared only inside the disposable overlay for fresh-runtime scope. Public codec fixtures and the verified361324-byte public WAV were the only staged inputs. No legacy Room migration claim is made.

Only5558 was stopped using its explicit serial. Its Windows process is absent and primary5556 remains listed. Source config SHA and source image metadata match the before-boot baseline. Full original userdata/cache/encryption image SHA snapshots were additionally taken before the final stage and after shutdown; comparison PASS for all7 files (`ORIGINAL_AVD_PRESERVATION.json`). The before-final-stage and after-shutdown SHA256, sizes and mtimes are identical; initial before-boot config SHA/disk metadata also match. Checksum I/O is finished; primary graphics measurements can start. No guest filesystem was mounted or records inspected for these integrity checks. Physical phone mic, thermal, GPU/battery behavior and automatic diarization remain outside this acceptance.
