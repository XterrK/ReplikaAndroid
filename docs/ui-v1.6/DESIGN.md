# UI V1.6 — design contract · 06.11.2026

Source concept: [concept.png](concept.png). Native Android implementation, not a website.

## References and decisions

- [React Bits Orb](https://reactbits.dev/backgrounds/orb), [source](https://github.com/DavidHDev/react-bits/blob/main/src/content/Backgrounds/Orb/Orb.jsx): layered light and slow motion. Its hollow luminous ring is not the desired solid sphere; do not copy that silhouette.
- [ElevenLabs Orb](https://ui.elevenlabs.io/docs/components/orb), [official introduction](https://elevenlabs.io/blog/elevenlabs-ui): audio volume separate from agent state; use real recorder envelope, never touch as microphone evidence.
- [Paper Shaders](https://shaders.paper.design/), especially smoke-ring/warp: flowing domain-warped fields, not rotating a flat linear gradient. No dependency copied.
- [Android ShaderBrush](https://developer.android.com/develop/ui/compose/graphics/draw/brush), [AGSL](https://developer.android.com/develop/ui/views/graphics/agsl): native RuntimeShader on API33+, Canvas fallback on API26–32. No WebView/React runtime.

## Composition

Retain existing cold light and graphite theme tokens, serif REPLIKA wordmark and Onest controls (intentional adaptation from generated concept). One large central opaline sphere. Header 56dp; visible back during recording. Status above sphere, light tabular timer below only during a live session. Idle hint: «Нажмите на шар для записи». Recording hint: «Говорите, мы слушаем». Pause hint: «Продолжите, когда будете готовы».

Sphere: blue/lavender volumetric wisps, soft white key reflection, refracted rim, lower caustic and diffuse floor shadow. Geometry remains near-spherical except direct manipulation. Retain elastic touch, accessibility, power/thermal/reduced-motion and lifecycle bounds. Surface flows through the sphere, not around an opaque ball.

Right edge: many horizontal strokes rooted at physical right edge, nearly full content height, amplitude controls inward extent. Separate overlay, no layout weight/reserved gutter, no hit interception. No fake idle activity. Input is MediaRecorder envelope, not an FFT; do not imply spectral accuracy. No lateral displacement of orb, status or timer.

## Decisions and copy

Pause / Завершить controls (56dp targets, stack for large fonts). Header back, system back and Завершить all open same bottom sheet. Opening sheet pauses recording. Primary «Сохранить запись»; secondary destructive «Удалить запись». Dismiss resumes only if sheet paused a running session. No third competing action required. Disable navigation while stopping. Save publishes audio to library and opens its workspace; discard removes draft and returns to clean home. Timer hidden and elapsed reset after completion; saved recording metadata retains actual duration.

All controls and text remain native, accessible and adaptive. Rounded sheet 24dp, controls existing 10dp for consistency across app. No new decorative badges, helper metrics or UI panels. Generated concept is a direction, not an image shipped as the recording screen.
