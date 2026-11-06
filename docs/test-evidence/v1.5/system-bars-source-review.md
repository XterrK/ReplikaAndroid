# Manual appearance / system bars — source investigation

2026-11-05. Trigger: Android screenshots with the app manually set to DARK showed dark grey three-button navigation icons against the graphite background. This is a visual observation; no screenshot pixel-contrast metric was asserted.

Read-only device inspection found API 35, Android system night mode off, and the launcher in focus after the preceding test. No REPLIKA window remained to inspect. The investigation did not launch activities, switch themes, change emulator settings or run instrumentation.

The application pinned Core 1.16.0 and Activity 1.10.1. Inspection of the actual cached Core AAR confirmed that `Impl35` overrides appearance getters but inherits setters that write legacy `systemUiVisibility` as well as native appearance. The original activity also called `enableEdgeToEdge` on each theme-side effect, before a guaranteed attached/focused window. Theme XML declares light bars in the system-light configuration, which can differ from a manual app DARK override.

Upstream's later [appearance change](https://github.com/androidx/androidx/commit/dfd2896a8f2b) separates legacy access on older Android from native setters on API 35. Its explanation documents interactions between theme attributes and separate appearance calls before first layout. That supports avoiding mixed control paths; it does not prove the exact root cause of the observed screenshot. The Android [WindowInsetsController contract](https://developer.android.com/reference/android/view/WindowInsetsController#setSystemBarsAppearance(int,%20int)) allows both appearance bits to be set together with a mask.

The local change configures edge-to-edge once. On API 35 it sets status/navigation light-appearance bits atomically through the platform API and repeats application after attach/focus return. API 26–34 retain compat control; bar backgrounds match the explicit theme. No dependency upgrade or continuous polling is added. The app does not recolor the external keyboard's own keys/theme.

`ThemeBarsV15Test` inspects actual Activity flags before the export sheet, the actual focused sheet decor obtained through public `WindowInspector`, Activity flags after sheet dismissal and after recreation, for both manual LIGHT and DARK. It saves eight screenshots and native-mask snapshots in `files/theme-bars-v15/<run>/`; `latest.json` points to the run. Public global-window inspection requires API 29+, so this test explicitly skips older APIs rather than using hidden reflection. Both flags and rendered navigation-button contrast must be checked on the resulting images.

At source handoff the test and final visual verification were pending the integration owner's build/instrumentation. The source change alone is not a claim that the navigation-button appearance is fixed on an emulator or a physical phone.

## Runtime follow-up and exact-version correction

The integration owner's runtime-6 test passed all eight requested appearance-mask checks, but screenshots exposed a separate rendering failure: manual DARK retained milk-white status/navigation backgrounds. White status glyphs therefore became unreadable. Native mask checks alone did not validate the rendered result.

The exact Google Maven `activity-1.10.1-sources.jar` was inspected, rather than transferring current androidx-main behavior to this version. It contains Api30/Api29 color-setter implementations and no `EdgeToEdgeApi35` / `ProtectionLayout` implementation. Calling this version's setup on a theme change does not stack protection layouts. The correction updates explicit `SystemBarStyle.light/dark` colors and the underlying window background on each app-theme change, then applies the atomic native flags and attach/focus reapplication.

The test now waits for a frame committed by the actual focused decor and the compositor, saves screenshots before assertions, verifies empty status/navigation background pixels against the app tokens (allowing modal dim/sheet surfaces), and checks rendered clock/Home glyph contrast. Partial evidence survives a failing assertion. Final acceptance still depends on the integration owner's rebuilt runtime and screenshot results.
