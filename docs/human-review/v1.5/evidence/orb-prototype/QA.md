# Prototype interaction QA — 2026-11-05

PASS: 15 scenario groups; no JavaScript errors or console warnings. This is a conceptual browser prototype with explicitly simulated amplitude. It never opens a microphone.

Environment: http://localhost:4174, existing Playwright 1.64.1 and headless Chromium. Browser plugin not available; the frontend-testing-debugging skill's Playwright fallback was used. No browser dependencies were installed.

The flow under test is: Recording Home → start → quiet/loud/silence → drag or keyboard toy with independent right VU → pause/resume/stop → export from Home → import a video fixture.

| Check | Result |
| --- | --- |
| Page identity and meaningful content | PASS |
| No framework overlay / console health | PASS / 0 errors |
| Light / neutral graphite Dark | PASS |
| 392×852 / 360×640 | PASS |
| 130% font at 360×640 | Primary action, import, export visible; no horizontal overflow |
| Quiet → loud → silence | Expansion ~0.114 → ~0.198 → ~0.091; VU decays below 0.008 |
| Drag in silence | Shape ratio ~2.29, VU ≤0.001, phase stays Recording |
| Release | Stretch settles to ~0.0002 after 1.9 s |
| Keyboard action | Shape ratio ~1.49, recording unchanged |
| Pause / resume / stop | PASS; paused VU is zero; Saved reached |
| Reduced Motion | No toy stretch or oscillation |
| Idle rendering | Draw count freezes after settling |
| Home export / video import | Recording picker → format chooser; video fixture → Processing |
| Playback waveform | 112 px normal / 82 px compact, blue→pink for one speaker |
| Playback transport | Play centered within 1 px; clocks and speed cannot shift controls |
| Reading | Compact transport only |

Evidence: `report.json` and the accompanying screenshots. Run `design-lab/tools/verify-v15-orb.cjs` with the existing server on port 4174 to repeat.

Visual fixes during QA: the initial one-speaker SVG gradient had zero-width object bounding boxes on vertical paths, so it was invisible. Switching to a gradient in user space restores the waveform. Stretching initially revealed flat-colored tips; applying the reciprocal body transform to the material keeps the highlight and depth attached to the deformed body. The same transform is present in native Canvas fallback.

Accepted C+B fidelity: expressive headings, sans-serif transcript/metadata, compact navigation and actions; cold light surfaces and neutral graphite background. A/B/C voting was not repeated. The recording orb is the Home focus, library is a separate tab, export remains on Home. Native AGSL is more detailed than the Canvas prototype and is separately verified by the parent Android task.

These checks do not establish real microphone response, offline ASR accuracy, physical vivo X300 frame times, thermal behavior, or battery use. Those require separate Android/device evidence.
