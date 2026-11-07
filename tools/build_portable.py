#!/usr/bin/env python3
"""Build through the checked-in Gradle wrapper, with portable, offline asset preflight.

Requires Python 3.12+ and JDK 17. --check and --print-env never invoke Gradle.
Remaining arguments are passed through to Gradle, including --offline.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS = [":app:assembleDebug", ":app:testDebugUnitTest", ":app:assembleDebugAndroidTest"]
DEBUG_CERT_SHA256 = "f40399356577bcd0a5c220818ba13e9686768a02830a7f6e3af81d5a487947ab"


def unescape_property(value):
    def replace(match):
        token = match.group(1)
        if token.startswith("u") and len(token) == 5:
            return chr(int(token[1:], 16))
        return {"t": "\t", "r": "\r", "n": "\n", "f": "\f"}.get(token, token)
    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", replace, value)


def sdk_property(root):
    path = root / "local.properties"
    if not path.is_file():
        return None
    logical = ""
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        logical += line.lstrip() if logical else line
        trailing = len(logical) - len(logical.rstrip("\\"))
        if trailing % 2:
            logical = logical[:-1]
            continue
        match = re.match(r"^\s*sdk\.dir(?:\s*[:=]\s*|\s+)(.*)$", logical)
        logical = ""
        if match:
            return unescape_property(match.group(1))
    return None


def resolve_path(value, root):
    path = Path(os.path.expandvars(value)).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def discover_environment(root=ROOT, original=None):
    env = dict(os.environ if original is None else original)
    java = env.get("JAVA_HOME")
    if not java:
        javac = shutil.which("javac", path=env.get("PATH", ""))
        if not javac:
            raise ValueError("Set JAVA_HOME to a JDK 17 directory (or put its javac on PATH)")
        java = str(Path(javac).resolve().parent.parent)
    java_home = resolve_path(java, root)
    java_binary = java_home / "bin" / ("java.exe" if os.name == "nt" else "java")
    javac_binary = java_home / "bin" / ("javac.exe" if os.name == "nt" else "javac")
    if not java_binary.is_file() or not javac_binary.is_file():
        raise ValueError(f"JAVA_HOME is not a JDK directory: {java_home}")
    configured = sdk_property(root)
    home, sdk_root = env.get("ANDROID_HOME"), env.get("ANDROID_SDK_ROOT")
    if home and sdk_root and resolve_path(home, root) != resolve_path(sdk_root, root):
        raise ValueError("ANDROID_HOME and ANDROID_SDK_ROOT disagree; use the same SDK")
    sdk = home or sdk_root or configured
    if not sdk:
        raise ValueError("Set ANDROID_HOME or sdk.dir in the machine-local local.properties")
    sdk_home = resolve_path(sdk, root)
    if configured and (home or sdk_root) and resolve_path(configured, root) != sdk_home:
        raise ValueError("SDK environment and local.properties sdk.dir disagree; update/remove the stale sdk.dir")
    if not sdk_home.is_dir():
        raise ValueError(f"Android SDK directory is missing: {sdk_home}")
    env.update(JAVA_HOME=str(java_home), ANDROID_HOME=str(sdk_home), ANDROID_SDK_ROOT=str(sdk_home))
    for key, default in [("ANDROID_USER_HOME", root / "local-dev"),
                         ("GRADLE_USER_HOME", root / "local-dev/gradle")]:
        env[key] = str(resolve_path(env.get(key) or str(default), root))
    additions = [java_home / "bin", sdk_home / "platform-tools", sdk_home / "emulator",
                 sdk_home / "cmdline-tools/latest/bin"]
    env["PATH"] = os.pathsep.join([str(p) for p in additions if p.is_dir()] + [env.get("PATH", "")])
    return env


def build_preflight(root, env, tasks, allow_new_key=False):
    from verify_workspace import ABIS, verify_workspace

    errors = []
    for name in ["gradle/wrapper/gradle-wrapper.jar", "gradle/wrapper/gradle-wrapper.properties",
                 "gradlew.bat" if os.name == "nt" else "gradlew"]:
        if not (root / name).is_file():
            errors.append("Missing Gradle wrapper file: " + name)
    java = Path(env["JAVA_HOME"]) / "bin" / ("java.exe" if os.name == "nt" else "java")
    try:
        result = subprocess.run([str(java), "-version"], capture_output=True, text=True, timeout=15)
        output = result.stdout + result.stderr
        if result.returncode or not re.search(r'version\s+"17(?:[.\-"]|$)', output):
            errors.append("JDK 17 is required; JAVA_HOME java -version returned: " + output.strip())
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"Cannot execute the JDK on this host: {exc}")
    sdk = Path(env["ANDROID_HOME"])
    build_file = (root / "app/build.gradle.kts").read_text(encoding="utf-8")
    platform = re.search(r"compileSdk\s*=\s*(\d+)", build_file)
    ndk = re.search(r'ndkVersion\s*=\s*"([^"]+)"', build_file)
    if not platform or not ndk:
        errors.append("Cannot read compileSdk/ndkVersion from app/build.gradle.kts")
    else:
        requirements = [sdk / f"platforms/android-{platform.group(1)}/android.jar",
                        sdk / "build-tools/35.0.0" / ("aapt2.exe" if os.name == "nt" else "aapt2"),
                        sdk / f"ndk/{ndk.group(1)}/source.properties"]
        host = "windows-x86_64" if os.name == "nt" else "darwin-x86_64" if sys.platform == "darwin" else "linux-x86_64"
        requirements.append(sdk / f"ndk/{ndk.group(1)}/toolchains/llvm/prebuilt/{host}/bin" /
                            ("llvm-strip.exe" if os.name == "nt" else "llvm-strip"))
        for path in requirements:
            if not path.is_file():
                errors.append("Missing SDK component: " + str(path))
    # Conservatively verify all native ABIs even for aggregate Gradle tasks.
    # Embedded builds consume the ZIP; they do not also require extracted weights.
    lowered = [task.lower() for task in tasks]
    all_in_one = any("allinone" in task for task in lowered)
    aggregate = any(task.rsplit(":", 1)[-1] in ("assemble", "build", "buildneeded", "builddependents")
                    for task in lowered)
    needs_pack = all_in_one or aggregate
    if any(token in task for task in lowered for token in ("allin", "assemblea", "bundlea", "mergea")):
        needs_pack = True  # Cover common Gradle task abbreviations as well.
    pack = Path("model-pack/replika-offline-pack-v1.6.zip") if needs_pack else None
    integrity = verify_workspace(root, models=False, abis=ABIS, pack=pack)
    errors.extend(integrity["errors"])
    # Mirror app/build.gradle.kts: its explicit local key takes precedence over
    # AGP's default key under ANDROID_USER_HOME.
    portable_key = root / "local-dev/debug.keystore"
    keystore = portable_key if portable_key.is_file() else Path(env["ANDROID_USER_HOME"]) / "debug.keystore"
    if not keystore.is_file() and not allow_new_key:
        errors.append(f"Debug signing key missing: {keystore}. Copy the existing private key, or explicitly "
                      "use --allow-new-debug-key for a separate install that cannot update existing builds")
    elif keystore.is_file() and not allow_new_key:
        keytool = java.parent / ("keytool.exe" if os.name == "nt" else "keytool")
        try:
            certificate = subprocess.run([str(keytool), "-exportcert", "-keystore", str(keystore),
                                          "-alias", "androiddebugkey", "-storepass", "android"],
                                         capture_output=True, timeout=15)
            if certificate.returncode:
                errors.append("Cannot read the existing Android debug signing certificate: " +
                              certificate.stderr.decode(errors="replace").strip())
            elif hashlib.sha256(certificate.stdout).hexdigest() != DEBUG_CERT_SHA256:
                errors.append("Debug signing certificate differs from the preserved releases; "
                              "copy the original key or explicitly use --allow-new-debug-key")
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"Cannot verify the debug signing certificate: {exc}")
    return errors, integrity, keystore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true", help="Validate and print the command without invoking Gradle")
    parser.add_argument("--print-env", action="store_true", help="Print discovered NAME=value lines for tools/env.sh; no preflight")
    parser.add_argument("--allow-new-debug-key", action="store_true", help="Allow a new/different debug key, incompatible with preserved releases")
    args, tasks = parser.parse_known_args(argv)
    if tasks[:1] == ["--"]:
        tasks = tasks[1:]
    tasks = tasks or DEFAULT_TASKS.copy()
    if all(argument.startswith("-") for argument in tasks):
        tasks = DEFAULT_TASKS + tasks
    if not any(argument.startswith("-PreplikaPython=") for argument in tasks):
        tasks = [*tasks, "-PreplikaPython=" + sys.executable]
    try:
        if sys.version_info < (3, 12):
            raise ValueError("Python 3.12+ is required")
        env = discover_environment()
        if args.print_env:
            for key in ["JAVA_HOME", "ANDROID_HOME", "ANDROID_SDK_ROOT", "ANDROID_USER_HOME", "GRADLE_USER_HOME", "PATH"]:
                if any(character in env[key] for character in "\r\n\0"):
                    raise ValueError(f"Cannot export {key} containing a newline or NUL")
                print(key + "=" + env[key])
            return 0
        errors, integrity, keystore = build_preflight(ROOT, env, tasks, args.allow_new_debug_key)
        for error in errors:
            print("ERROR " + error, file=sys.stderr)
        if errors:
            return 1
        wrapper = ROOT / ("gradlew.bat" if os.name == "nt" else "gradlew")
        # POSIX Git currently records gradlew as 100644; sh avoids requiring chmod.
        command = [str(wrapper), *tasks] if os.name == "nt" else ["sh", str(wrapper), *tasks]
        print("Project: " + str(ROOT), flush=True)
        print("JDK: " + env["JAVA_HOME"], flush=True)
        print("SDK: " + env["ANDROID_HOME"], flush=True)
        print("Signing key: " + str(keystore), flush=True)
        print(f"Input integrity: PASS ({len(integrity['files'])} files)", flush=True)
        print("Gradle arguments: " + repr(tasks), flush=True)
        if not args.check:
            return subprocess.run(command, cwd=ROOT, env=env).returncode
        print("Check only: Gradle was not started.")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("ERROR " + str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
