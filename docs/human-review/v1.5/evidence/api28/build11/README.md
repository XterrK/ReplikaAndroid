# Source11 · Android 9 / API28 acceptance

**33/33 tests passed on the exact source 11 QA APK**, in one fresh invocation of each suite. See [installed-build11.json](installed-build11.json) for exact main/test APK SHA and [FINAL_API28_BUILD11_RESULTS.json](FINAL_API28_BUILD11_RESULTS.json) for counts and scope. This folder preserves new source 11 proof separately from the earlier source 10 evidence.

The isolated `Replika28` AVD used `-read-only -no-snapshot`, device `emulator-5558`, original **432×936 pixels at 180 dpi**, original default font1.0 and animator1.0, two cores and the original configured 2 GB memory. No `wm` size/density/font override was applied. Legacy app data was cleared only inside its disposable overlay before installation; no private records or DB were read or copied. Primary 5556 was not changed.

| Suite | Passing tests |
| --- | ---: |
| Media import: extractor/decoder, MP4 edit lists and AAC priming |15|
| Canvas renderer, both themes |1|
| Bounded import-journal recovery |8|
| Navigation |1|
| Orb voice/touch interaction and independent audio state |1|
| Home import/export and full-width waveform/transport |2|
| Editorial themes/screens/keyboard, virtual recording pause/Back/save/decode/reopen |4|
| Actual seven-clip studio-whisper Android Worker regression |1|
| **Total** |**33**|

The immutable [ui32-summary.json](ui32-summary.json) and [whisper1-summary.json](whisper1-summary.json) retain the two sequential batches. The Whisper Worker batch started only after root confirmed no competing long recognition work; its 55.59s elapsed is an emulator test duration, not a physical-phone benchmark.

The seven **public, licensed, author-scripted studio-whisper** recordings ran through bundled GigaAM, actual ProcessingWorker, Room queries and JSON export. Independent reference scripts were used only for scoring. Result: **9/84 word errors (WER10.714%),39/500 character errors (CER 7.8%)**. The difficult23-word clip had zero primary VAD spans and recovered 21 words via detector rescue gain 9.273613. The other six clips did not retry; recognition input gain stayed 1.0 and author WAV SHA remained unchanged. [Acceptance and seven exported transcripts](real-whisper-worker/acceptance.json) contain the evidence. “Whisper” here names a voice style, not the removed ASR model.

[ui/scope.json](ui/scope.json) indexes **31 SHA-verified PNGs**: 27 full 432×936 Android captures and 4 standalone 338×338 renderer fixtures. All headers, control rows and navigation remain inside the original display surface. Automatic and forced renderer requests both use **Canvas on SDK 28**; these files never claim AGSL. Recording/paused/saved frames use emulator microphone input and prove recorder state/save/decode/reopen behavior. They do not prove acoustic responsiveness on vivo X300.

The seven clips are a bounded regression set, not a guarantee for every speaker, phone microphone or whispered word. No physical vivo microphone, phone FPS, power, heat or automatic-diarization quality was validated here. Compact 360×640 and increased-font evidence belong to the separate API35 matrix; this API28 acceptance uses only the original native profile. Earlier source 10 runtime-override compositor failures remain preserved as invalid toolchain diagnostics outside this folder.

The owned 5558 emulator was gracefully stopped before the final seven-file original AVD SHA comparison. [shutdown.json](shutdown.json) records the explicit-device shutdown and preserved primary 5556. [ORIGINAL_AVD_PRESERVATION.json](ORIGINAL_AVD_PRESERVATION.json) records the final integrity outcome; no guest filesystem was mounted.
