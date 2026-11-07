# Independent non-NN Android step5 audit

PASS: 311/311 integrity checks.

13 fixture bytes match the pinned439e manifest, local assets and ce4851 test APK. Six actual import tests are COMPLETE. Their recorded clocks, finite PCM/spectra, stereo averages, UUID-copy independence, truncation/errors and cleanup satisfy the pinned conditions. Both large cancellation WAV sources were independently regenerated to the recorded SHA; cancellation followed positive actual copy/PCM byte observations. Temporary PCM was deleted, so this is saved-measurement revalidation.

The original7-test suite remains PARTIAL_FAILURE: thermal was not executed because of the non-void JUnit method. Removing only the later explicit Unit signatures reproduces the original source SHA. The repaired thermal run passes1 test on API35: NONE waits0ms; valid SEVERE blocks, MODERATE resumes, CRITICAL cancellation is preserved, and reset returns0. Core2/request0 maps to1 thread without NN.

Actual DocumentsUI/back plus three sequential Downloads imports pass with distinct UUIDs, correct source SHA, real decode and recorded prior-row/audio preservation; only the three owned rows are cleaned. PNG CRC/dimensions pass and representative captures were visually reviewed. Identical pre-selection Downloads screenshots are not treated as distinct file-selection proof.

This audit performs no NN, device/decoder invocation, ADB, Gradle or Git. It does not accept model quality, CPU speed, ARM/phone behavior, pre29 thermal behavior or the whole step5. Detailed input/source hashes and evidence limits are in the JSON.
