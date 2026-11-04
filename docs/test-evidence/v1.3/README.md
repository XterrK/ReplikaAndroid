# V1.3 evidence

- `test-summary.json` — 38 JVM + 60 distinct final Android methods, zero failures/skips. Product acceptance remains PARTIAL; automatic known-four quality not accepted.
- `baseline-v121/`, `android-baseline-v121.log` — freshly executed installed V1.2.1 GigaAM Worker, not new-version inference.
- `initial-debug/`, `android-new-debug.log` — first five new Android executions and only their v13 outputs/screens/logs. Old ML JSON was deliberately excluded from this folder.
- `final-qa/` — raw named instrumentation statuses for 59 final QA cases and one additional long automatic test. Summary groups cover the first 59; aggregate test-summary includes the extra method.
- `final-results/` — newly produced public/controlled ML hypotheses, timings, UI-mode screenshots, private provisioning metadata copied only from tests, and allowlisted technical log records. No original user recording was supplied or collected. The JSON text here is actual inference on pinned public fixtures; controlled UI prose is explicitly marked.
- `host-diarization-probe.json` — Linux WSL native sensitivity, NOT Android. The long waveform repeats one public short clip; not an independent recording.
- `observations.json` — numeric observations plus known automatic quality acceptance failure; no hidden WER/CER/DER.
- `upgrade.json` — byte-for-byte DB/files comparison around emulator install-r code4→5, before new-version launch. Raw backup paths/data remain outside repository.
- `arm64-static.json`, `qa-static.json`, signature/badging — package/model/native/ABI/static alignment, not physical/runtime compatibility.
- `build-logs/` — successful build logs plus initial compiler/test failures and their subsequent correction. A Gradle skipped preBuild task is not a skipped JUnit test.

The final long mono Worker total was 55.341 s; the earlier Debug run was 79.346 s. Cache/host load was uncontrolled. Never present these as a vivo speed guarantee or evidence that the user's original 11-speaker case was fixed. The source safety/test/report details are in the five root V1.3 reports.

Windows ADB captures retain CRLF. Whitespace check uses Git `core.whitespace=cr-at-eol,-blank-at-eof` for these raw logs (including terminal blank lines); no event values or status codes were rewritten.
