# Portable build and private workspace handoff

The current application is V1.6, versionCode 8. It still uses the pinned V1.5
GigaAM v3 model pack. The application version and model-pack version are separate.
Keep the complete working tree: current source, tests, documentation, fixtures,
design work and release evidence include uncommitted and untracked files. A clone
of the current Git HEAD alone does not reproduce this workspace.

`tools/build_portable.py` discovers the project from its own location and uses the
checked-in Gradle wrapper. `tools/build_local.py` remains the existing machine's
fast RAM-cache build; it deliberately retains its original machine-specific setup.
Neither portable tool downloads models, installs SDK components, removes files,
or rewrites `local.properties`.

## Required contents

The source, current models and native libraries already reside in the project.
Copy the whole private workspace first, including hidden files and ignored assets;
do not copy only Git-tracked files. Preserve `.git` so branches and local history
travel with the source. Store an independent, verified snapshot before any later
reorganization. Do not run `git clean -xfd`, reset the tree or delete ignored inputs.

| Contents to preserve | Purpose |
| --- | --- |
| `app/`, `tools/`, Gradle files, wrapper JAR/scripts and all current source/test assets | Application and build inputs; the checked-in Sherpa Kotlin bindings must match the native runtime |
| `model-pack/giga-v3/`, `model-pack/diar/`, `model-pack/vad/` | Seven manifest-pinned current model/token files; 278,127,730 bytes total |
| `model-pack/replika-offline-pack-v1.5.zip` | All-in-One source ZIP; 278,569,170 bytes; required even if loose models are present |
| `app/src/main/jniLibs/arm64-v8a/{libonnxruntime.so,libsherpa-onnx-jni.so}` | Device native libraries |
| `app/src/main/jniLibs/x86_64/{libonnxruntime.so,libsherpa-onnx-jni.so}` | Emulator native libraries; keep both ABIs for the normal debug build |
| `app/src/main/assets/models-lock.json`, `app/src/main/assets/licenses/`, `docs/licenses/`, `tools/native-lock.json` | Checksums, model provenance and redistribution notices |
| `local-dev/debug.keystore` | Private existing signing key, already copied locally; required for compatible updates |
| `model-pack/giga-v2/`, `model-pack/whisper-tiny/`, `model-pack/manifest.json`, `model-pack/replika-offline-pack.zip`, `third_party/` | Historical models, pack and Whisper sources; preserve for previous versions/research |
| `release/`, `review/`, `docs/`, root reports, `design-lab/`, `archive/video-production-fi-20261105/`, `.tools/` | All historical APKs, test evidence, design/media work, local helpers and captured device state |

The four native SHA-256 pins in `verify_workspace.py` were measured from the
Sherpa v2.0.1 archive after checking the archive against `tools/native-lock.json`.
The verifier checks the raw copied `.so` files, not the stripped copies inside an
APK. Update those pins deliberately if the runtime is intentionally changed.

No SDK needs to be bundled with the workspace. Install a host-native SDK and JDK
on the destination. Do not reuse Linux executables on Windows or vice versa.
An existing toolchain may be retained separately as a recovery archive.

For Android integration staging, copy `russian-example.wav`, `russian-example.mp3`,
`russian-example.m4a` and `four-speakers-zh.wav` from the original toolchain into
`benchmark/fixtures/`. These local audio files are ignored by Git.
Additional copies are needed only to rerun historical host/media investigations:
retain the original toolchain's `asr-v15-candidates/`, `asr-v15-fixtures/`,
`asr-v15-holdout/`, `asr-v15-ru-whisper/`, `python/`, `python-wheels/`,
`linux-libs/`, `ffmpeg/`, `model-downloads/` and preservation directories. Keep
their manifests/provenance with them. These are separate from Android compilation.
The portable launcher does not rewrite older scripts that still reference the
original toolchain or temporary ADB wrappers.

## Signing key privacy

`local-dev/` is ignored by Git. Keep its signing key in the private workspace and
an access-controlled backup; exclude it from public source ZIPs, review ZIPs,
uploads and shared manifests. Check `git check-ignore local-dev/debug.keystore`
before sharing source, and never force-add the key. It is a development key with
the conventional Android debug alias/password, not a production release key.

Gradle uses `local-dev/debug.keystore` when present. The launcher checks its
certificate SHA-256 against the preserved releases:
`f40399356577bcd0a5c220818ba13e9686768a02830a7f6e3af81d5a487947ab`.
It falls back to `ANDROID_USER_HOME/debug.keystore` if no project-local key exists.
Without the original key, a newly signed APK cannot update an installed build
with the old certificate. `--allow-new-debug-key` explicitly permits a separate
development identity. Do not uninstall the user's app to work around a signing
mismatch: that can delete recordings and database edits.

## Destination setup

Use Python 3.12+, JDK 17, Android platform 35, Build Tools 35.0.0 and NDK
27.2.12479018. The NDK is currently retained for native strip tasks; compiling
Whisper/CMake is no longer part of the app build. The wrapper pins Gradle 8.13
and its distribution SHA-256; AGP is 8.9.2 and Kotlin is 2.1.20.

Set `JAVA_HOME` to the JDK root and `ANDROID_HOME` to the SDK root. If
`JAVA_HOME` is absent, the launcher looks for `javac` on PATH. The SDK may instead
come from `sdk.dir` in the ignored, machine-local `local.properties`;
`ANDROID_SDK_ROOT` is also accepted. An environment/local.properties mismatch
fails explicitly because Gradle could otherwise select a different SDK. Correct
or remove a stale `sdk.dir` on the destination. Use forward slashes in Windows
properties, for example `sdk.dir=C:/Android/Sdk`, or Java-properties escaping.

Install the matching SDK packages with the destination's command-line tools:

```text
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0" "ndk;27.2.12479018"
sdkmanager --licenses
```

For Bash, optionally source `tools/env.sh` after configuring the JDK and SDK. It
resolves paths from the script, exports paths safely without evaluating shell
code, respects explicit cache/user-home settings, and creates no directories.
The launcher can be used directly on Windows, Linux or macOS; sourcing Bash is
not required. Host execution on each additional OS still needs validation.

By default `ANDROID_USER_HOME` is `local-dev/` and `GRADLE_USER_HOME` is
`local-dev/gradle/`. Set either explicitly to reuse another location. The launcher
passes its running Python interpreter to Gradle's `replikaPython` property, so
All-in-One preparation also works when the interpreter is named `python`.

## Verify and build

Run from the project root; substitute `python` for `python3` when appropriate:

```bash
# Verify all seven loose model files and four native libraries; read-only.
python3 tools/verify_workspace.py

# Also verify the source ZIP, including manifest, model SHA-256 and ZIP CRCs.
python3 tools/verify_workspace.py --pack model-pack/replika-offline-pack-v1.5.zip

# Read-only SDK/JDK/wrapper/signing/native preflight, without starting Gradle.
python3 tools/build_portable.py --check
python3 tools/build_portable.py --check :app:assembleAllInOne

# Default: debug APK, JVM tests and debug instrumentation-test APK.
python3 tools/build_portable.py
python3 tools/build_portable.py :app:assembleAllInOne
python3 tools/build_portable.py :app:assembleAllInOneQa
```

Use full Gradle task names for All-in-One builds. Explicit All-in-One tasks and
the aggregate `assemble`/`build` tasks require the current ZIP during preflight.
A standard build verifies native libraries but does not require loose weights or
the pack. The full workspace verifier requires loose weights by default; use
`--native-only` for source-only standard builds or `--abi arm64-v8a` to inspect
one ABI. All-in-One APKs consume the ZIP directly and do not require loose weights.

Create an optional portable SHA-256 inventory only after successful verification:

```bash
python3 tools/verify_workspace.py --pack model-pack/replika-offline-pack-v1.5.zip --output local-dev/workspace-manifest.json
python3 tools/verify_workspace.py --pack model-pack/replika-offline-pack-v1.5.zip --manifest local-dev/workspace-manifest.json
```

The output parent directory must already exist. `--output` never overwrites an
existing file. Use the same `--native-only`, `--abi` and `--pack` options when
checking a saved manifest. `--json` prints the report without writing it. The
manifest contains relative asset paths, sizes and hashes; it excludes signing
material and does not snapshot all source/history or authenticate the publisher.

The first wrapper invocation may download Gradle; the first build may download
Maven artifacts. Models are never fetched by this launcher. The existing old
cache lacked the DataStore dependency; an online build was needed to populate
it. Use `--offline` only after the wrapper distribution and every needed variant's
dependencies are cached; Gradle's offline flag does not prevent the wrapper's
initial distribution download. Copying a cache checkpoint alone does not prove
that the wrapper distribution is installed. Keep `tools/build_local.py` for the
original fast build; its Gradle/RAM cache is independent of the portable defaults.

Output locations remain `app/build/outputs/apk/debug/app-debug.apk`,
`app/build/outputs/apk/allInOne/app-allInOne.apk` and
`app/build/outputs/apk/allInOneQa/app-allInOneQa.apk`. `allInOne` is arm64;
`allInOneQa` is x86_64 with a separate `.aioqa` application ID by default. Use
`-PreplikaTestBuildType=allInOneQa` when building its instrumentation APK.

## Emulator and integration-test limits

The inspected toolchain contains platform 35, Build Tools 35.0.0, NDK
27.2.12479018, CMake 3.22.1, Linux and Windows emulator 37.2.12, and API28/API35
x86_64 system images. Linux AVDs are `Replika28`/`Replika35`; Windows AVDs are
`Replika28`/`Replika35v11`. Their `.ini` and `config.ini` files contain original
absolute paths; recreate AVDs on another computer instead of blindly moving them.
The inspected WSL session has no `/dev/kvm`; use the Windows hypervisor-backed
emulator there or a host with working acceleration. SDK/AVD presence does not
establish current device connectivity or successful runtime acceptance.

For a fresh host, install `emulator` and an appropriate x86_64 system image,
create an AVD with `avdmanager`, then use `emulator -list-avds`, `adb devices -l`
and an explicit `adb -s SERIAL` for installation/tests. Avoid competing Linux and
Windows ADB servers. The old local wrappers used server port 5038 and an explicit
emulator TCP serial; these settings are machine-local, not portable defaults.

`tools/stage_android.py` accepts `ADB` or discovers `adb`/`adb.exe` on PATH and
reads the four common audio fixtures from `benchmark/fixtures/`. It uses
`wslpath` for Windows ADB pushes from WSL; native Windows needs no conversion.
It targets `ru.replika.offline`, not the default QA package,
uses `run-as` (requires a debuggable build), has no serial argument of its own,
and stages app-private files. `--pack` still checks all loose model hashes before
pushing the ZIP. Its hashes use Python assertions, so do not run it with `-O`.
Temporary cleanup can fail after an interrupted push. The model-push behavior
is unchanged; do not use it against valuable app data.
Bootstrap/preparation/packaging scripts can download or write files and are not
read-only inspection commands. Phone microphone/thermal and arm64 runtime checks
remain separate from static checks or x86_64 emulator results.

## Workspace cleanup in V1.6

Previous APKs, test APK, original checksum files, historical ARTIFACTS.json and
SHA256SUMS were moved byte-for-byte to `release/archive/`. `release/README.md`
identifies the current APK; old reports may retain original release paths as
historical evidence. Relocation hashes are recorded in `docs/ui-v1.6/relocation.json`.
Loose JVM crash/replay logs moved to `archive/diagnostics/`; the previous video
production folder moved intact to `archive/video-production-fi-20261105/`.

Versioned reports, `docs/`, `review/`, `design-lab/`, historical local model packs,
`.tools/` helpers and `.git` are retained. Current native/model inputs and the
private signing key stay at their build paths. Regenerable caches and temporary
build output are removed only after APK/test evidence has been copied into the
release/evidence folders. See HANDOFF.md and TEST_REPORT_V1_6.md for actual checks.
