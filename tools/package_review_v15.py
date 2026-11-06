#!/usr/bin/env python3
"""Package the final V1.5 Human Review without modifying previous deliveries.

Run only after final APK verification, tests and reports. No build/install/push is done.
The ZIP contains one installable APK; model weights occur only inside that APK.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APK = PurePosixPath("release/REPLIKA-V1.5-AllInOne-arm64.apk")
DEST = PurePosixPath("review/HUMAN_REVIEW_V1_5.zip")
STATIC_REPORT = PurePosixPath("docs/human-review/v1.5/evidence/arm64-static.json")
BASELINE = PurePosixPath("review/v1.5-baseline/preservation.json")
MANIFEST_NAME = "v1.5-delivery.json"
BLOCK = 1024 * 1024

REQUIRED = (
    "README.md", "PROJECT_STATE.md", "HUMAN_CONCEPT_REVIEW.md", "DESIGN_SYSTEM.md",
    "LIQUID_ORB_TECHNICAL_SPEC.md", "LIQUID_ORB_V1_5.md", "MOTION_DESIGN.md",
    "UX_BEFORE_AFTER.md", "UX_V1_5_BRIEF.md", "TEST_REPORT_V1_5.md", "KNOWN_ISSUES.md",
    "MODEL_SELECTION_V1_5.md", "ASR_QUALITY_V1_5.md", "VIDEO_IMPORT_TECHNICAL_SPEC.md",
    "build.gradle.kts", "settings.gradle.kts", "gradle.properties", "gradlew", "gradlew.bat",
    "gradle/wrapper/gradle-wrapper.jar", "gradle/wrapper/gradle-wrapper.properties",
    "app/build.gradle.kts", "app/src/main/AndroidManifest.xml", "app/src/main/assets/models-lock.json",
    "tools/package_review_v15.py", "tools/build_local.py", "tools/prepare_current_pack.py",
    "tools/prepare_models.py", "tools/prepare_runtime.py", "tools/prepare_embedded_pack.py",
    "tools/verify_artifact.py", "tools/verify_all_in_one.py", "tools/native-lock.json",
    "tools/benchmark_asr_v15.py", "tools/create_media_import_fixtures.py",
    "design-lab/index.html", "design-lab/screen.html", "design-lab/screen.js",
    "design-lab/screen.css", "design-lab/orb.js", "design-lab/DESIGN_SYSTEM.md",
    "design-lab/concepts/b-overview.png", "design-lab/concepts/c-overview.png",
    "design-lab/assets/fonts/Onest-Variable.ttf", "design-lab/assets/fonts/Onest-OFL.txt",
    "design-lab/tools/verify-v15-orb.cjs", "docs/human-review/v1.5/REVIEW_GUIDE.md",
    str(APK), str(STATIC_REPORT), str(BASELINE),
)
SKIP_PARTS = {".git", ".gradle", ".kotlin", ".idea", ".cxx", "build", "__pycache__",
              "node_modules", ".venv", "venv", "cache", ".cache", "model-pack", "weights", "jniLibs"}
FORBIDDEN_SUFFIXES = {".apk", ".zip", ".aar", ".so", ".onnx", ".tflite", ".gguf", ".ggml",
                      ".bin", ".pt", ".pth", ".ckpt", ".safetensors", ".pb", ".npz", ".npy",
                      ".ort", ".h5", ".hdf5", ".pkl", ".pickle", ".rknn", ".engine",
                      ".pyc", ".jks", ".keystore", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db", ".wal", ".shm", ".journal"}
SOURCE_SUFFIXES = {".kt", ".java", ".xml", ".cpp", ".cc", ".c", ".h", ".hpp", ".txt",
                   ".md", ".json", ".ttf", ".otf", ".png", ".webp", ".svg", ".kts", ".pro"}
TOOL_SUFFIXES = {".py", ".sh", ".bat", ".cjs", ".mjs", ".js", ".json", ".toml", ".md", ".txt"}
LAB_SUFFIXES = {".html", ".css", ".js", ".json", ".md"}
ACCEPTED_REFS = {"b-overview.png", "c-overview.png", "c-dialogue-study.png", "artifacts.json", "generation-provenance.json"}
LAB_REVIEW = {"HUMAN_CONCEPT_REVIEW.md", "DESIGN_SYSTEM.md", "REFERENCE_NOTES.md", "FIDELITY_LEDGER.md"}


class PackageError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_destination(destination: Path) -> None:
    # lexists also rejects dangling symlinks; neither ZIP nor checksum is overwritten.
    for path in (destination, Path(str(destination) + ".sha256")):
        require(not os.path.lexists(path), f"Preserve existing output: {path}. Select a new name explicitly in source.")


def allowed_payload(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        return False
    if path == APK:
        return True
    if any(part in SKIP_PARTS or part.startswith("video-production") for part in path.parts):
        return False
    lower = path.name.lower()
    database_sidecar = any(lower.endswith(extension + suffix) for extension in (".db", ".sqlite", ".sqlite3") for suffix in ("-wal", "-shm", "-journal"))
    if (path.suffix.lower() in FORBIDDEN_SUFFIXES or database_sidecar
            or lower.startswith(".env") or lower == "local.properties"):
        return False
    if path.parent == PurePosixPath("."):
        return path.suffix == ".md" or path.name in {".gitignore", "build.gradle.kts", "settings.gradle.kts", "gradle.properties", "gradlew", "gradlew.bat"}
    if str(path).startswith("gradle/"):
        return path.suffix in {".jar", ".properties", ".toml", ".kts"}
    if path == PurePosixPath("app/build.gradle.kts") or path == BASELINE:
        return True
    if str(path).startswith("app/src/"):
        if str(path).startswith("app/src/main/assets/"):
            return path == PurePosixPath("app/src/main/assets/models-lock.json") or str(path).startswith("app/src/main/assets/licenses/") and path.suffix in SOURCE_SUFFIXES
        if str(path).startswith("app/src/androidTest/assets/media-import/"):
            return path.suffix in {".json", ".mp4", ".m4a", ".webm", ".wav", ".txt"}
        return path.suffix in SOURCE_SUFFIXES
    if str(path).startswith("tools/"):
        return path.suffix in TOOL_SUFFIXES
    if str(path).startswith(("docs/human-review/v1.5/", "docs/test-evidence/v1.5/", "docs/licenses/")):
        return True
    if path.parent == PurePosixPath("docs"):
        return path.suffix == ".md"
    if path == PurePosixPath("release/ARTIFACTS.json") or path == PurePosixPath(str(APK) + ".sha256"):
        return True
    if path.parent == PurePosixPath("design-lab"):
        return path.suffix in LAB_SUFFIXES
    if path.parent == PurePosixPath("design-lab/concepts"):
        return path.name in ACCEPTED_REFS
    if path.parent == PurePosixPath("design-lab/review"):
        return path.name in LAB_REVIEW
    if str(path).startswith("design-lab/assets/fonts/"):
        return path.suffix in {".ttf", ".otf", ".txt", ".md"}
    if str(path).startswith(("design-lab/tools/", "design-lab/probes/")):
        return path.suffix in TOOL_SUFFIXES | {".java"}
    return False


def collect_payload(root: Path) -> list[Path]:
    candidates = list(root.iterdir())
    for directory in ("gradle", "app/src", "tools", "docs/human-review/v1.5", "docs/test-evidence/v1.5", "docs/licenses", "design-lab"):
        folder = root / directory
        require(folder.is_dir(), f"Missing source/evidence directory: {directory}")
        candidates.extend(folder.rglob("*"))
    candidates.extend((root / "docs").glob("*.md"))
    candidates.extend(root / name for name in ("app/build.gradle.kts", str(APK), str(APK) + ".sha256", "release/ARTIFACTS.json", str(BASELINE)))
    files: dict[str, Path] = {}
    for path in candidates:
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        if not allowed_payload(name):
            continue
        require(not path.is_symlink(), f"Do not follow source/evidence symlink: {name}")
        require(path.resolve().is_relative_to(root.resolve()), f"File escaped workspace: {name}")
        files[name] = path
    missing = sorted(set(REQUIRED) - files.keys())
    require(not missing, "Final delivery is incomplete; missing: " + ", ".join(missing))
    require([name for name in files if name.lower().endswith(".apk")] == [str(APK)], "Expected exactly the final arm64 APK")
    return [files[name] for name in sorted(files)]


def validate_apk(root: Path) -> tuple[dict, str]:
    apk = root / APK
    report = json.loads((root / STATIC_REPORT).read_text())
    require(isinstance(report.get("errors"), list) and not report["errors"], "Final arm64 static report contains errors or has no errors list")
    require(report.get("staticVerification") == "PASS", "Final arm64 static verification is not PASS")
    require(report.get("actualAbis") == ["arm64-v8a"] and report.get("expectedAbis") == ["arm64-v8a"], "Static report must verify only arm64-v8a")
    require(report.get("embeddedPackCopies") == 1 and report.get("looseModelAssets") == [], "Static report must verify one embedded pack and no loose model weights")
    require(Path(report.get("apk", "")).name == APK.name, "Static report names another APK")
    digest = sha256(apk)
    require(report.get("sha256") == digest and report.get("bytes") == apk.stat().st_size, "Final APK differs from its static SHA/size report")
    sidecar = Path(str(apk) + ".sha256")
    if sidecar.exists():
        require(sidecar.read_text().split()[0] == digest, "APK checksum sidecar is stale")
    return report, digest


def validate_preservation(root: Path) -> tuple[dict, dict[str, str]]:
    baseline = json.loads((root / BASELINE).read_text())
    expected = {name: value for name, value in baseline.items()
                if "/" in name and isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{64}", value)}
    require({"release/REPLIKA-V1.4-AllInOne-arm64.apk", "review/HUMAN_REVIEW_V1_4.zip"} <= expected.keys(), "Preservation record is missing previous APK/ZIP SHA256")
    for name, digest in expected.items():
        rel = PurePosixPath(name)
        require(not rel.is_absolute() and ".." not in rel.parts and "\\" not in name, f"Unsafe baseline path: {name}")
        path = root / rel
        require(path.is_file() and not path.is_symlink(), f"Preserved artifact missing or redirected: {name}")
        require(path.resolve().is_relative_to(root.resolve()), f"Preserved artifact escaped workspace: {name}")
        require(sha256(path) == digest.lower(), f"Previous artifact changed: {name}")
    return baseline, expected


def write_payload(archive: zipfile.ZipFile, path: Path, root: Path) -> dict:
    name = path.relative_to(root).as_posix()
    before = path.stat()
    info = zipfile.ZipInfo.from_file(path, name, strict_timestamps=False)
    info.compress_type = zipfile.ZIP_STORED if name == str(APK) else zipfile.ZIP_DEFLATED
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
        while chunk := source.read(BLOCK):
            require(total != 0 or not chunk.startswith(b"SQLite format 3\x00"), f"Database content excluded from Human Review: {name}")
            target.write(chunk)
            digest.update(chunk)
            total += len(chunk)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and total == before.st_size,
            f"Input changed while packaging: {name}; finish work before packaging")
    return {"path": name, "bytes": total, "sha256": digest.hexdigest()}


def verify_archive(destination: Path, expected: dict) -> None:
    with zipfile.ZipFile(destination) as archive:
        bad = archive.testzip()
        require(bad is None, f"ZIP CRC failed: {bad}")
        names = archive.namelist()
        payload = expected["files"]
        require(len(names) == len(set(names)) == len(payload) + 1, "ZIP entries are duplicated or missing")
        require(set(names) == {row["path"] for row in payload} | {MANIFEST_NAME}, "ZIP payload differs from manifest")
        require([name for name in names if name.lower().endswith(".apk")] == [str(APK)], "ZIP must contain exactly one final APK")
        require(json.loads(archive.read(MANIFEST_NAME)) == expected, "ZIP manifest content changed")
        for row in payload:
            with archive.open(row["path"]) as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            require(digest == row["sha256"] and archive.getinfo(row["path"]).file_size == row["bytes"], f"ZIP SHA/size failed: {row['path']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Validate final inputs and preserved artifacts without writing a ZIP or checksum")
    args = parser.parse_args()
    destination = ROOT / DEST
    validate_destination(destination)
    files = collect_payload(ROOT)
    anchors = {str(name): sha256(ROOT / name) for name in (STATIC_REPORT, BASELINE)}
    static, apk_sha = validate_apk(ROOT)
    baseline, preserved = validate_preservation(ROOT)
    require(all(sha256(ROOT / name) == digest for name, digest in anchors.items()), "Verification/preservation record changed during validation")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = {
        "version": "1.5", "createdAtUtc": datetime.now(timezone.utc).isoformat(),
        "gitHead": head, "baselineGitHead": baseline.get("baselineGitHead"),
        "workingTree": "Current uncommitted implementation; no commit or push by packager",
        "apk": str(APK), "apkSha256": apk_sha, "apkBytes": static["bytes"],
        "staticReport": str(STATIC_REPORT), "staticVerification": static["staticVerification"],
        "verificationRecordSha256": anchors,
        "previousArtifactPreservation": {"record": str(BASELINE), "before": "PASS", "artifacts": preserved},
        "dataScope": "Public/synthetic test evidence and source; no private databases or standalone model weights. Models are included only inside the single APK.",
        "acceptanceScope": "Physical vivo X300 microphone, thermal and power acceptance remains open. Automatic diarization remains a known issue. See TEST_REPORT_V1_5.md for completed checks.",
        "files": [],
    }
    if args.check_only:
        print(json.dumps({"status": "INPUTS_VALIDATED_ONLY", "archiveCreated": False,
                          "destination": str(DEST), "payloadFiles": len(files), "apkSha256": apk_sha,
                          "previousArtifacts": "PASS", "crc": "NOT RUN", "zipSha256": "NOT RUN"}, indent=2))
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    created_sidecar = False
    try:
        # x is authoritative even if another process creates output after the preflight check.
        with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            created = True
            for path in files:
                manifest["files"].append(write_payload(archive, path, ROOT))
            apk_entry = next(row for row in manifest["files"] if row["path"] == str(APK))
            require(apk_entry["sha256"] == apk_sha, "APK changed after static verification")
            for name, digest in anchors.items():
                row = next(item for item in manifest["files"] if item["path"] == name)
                require(row["sha256"] == digest, f"Verification/preservation record changed before archiving: {name}")
            _, preserved_after = validate_preservation(ROOT)
            require(preserved_after == preserved, "Preservation record changed while packaging")
            manifest["previousArtifactPreservation"]["after"] = "PASS"
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        verify_archive(destination, manifest)
        # Verify preservation again after full archive I/O, before declaring success.
        _, preserved_after = validate_preservation(ROOT)
        require(preserved_after == preserved, "Preservation record changed after ZIP verification")
        require(all(sha256(ROOT / name) == digest for name, digest in anchors.items()), "Verification/preservation record changed after ZIP verification")
        archive_sha = sha256(destination)
        with Path(str(destination) + ".sha256").open("x") as sidecar:
            created_sidecar = True
            sidecar.write(archive_sha + "  " + destination.name + "\n")
    except BaseException:
        # Only remove a partial artifact created by this invocation, never prior deliveries.
        if created_sidecar:
            Path(str(destination) + ".sha256").unlink(missing_ok=True)
        if created and destination.exists():
            destination.unlink()
        raise
    print(json.dumps({"archive": str(DEST), "bytes": destination.stat().st_size,
                      "sha256": archive_sha, "entries": len(files) + 1, "apkEntries": 1,
                      "crc": "PASS", "payloadSha256": "PASS", "previousArtifacts": "PASS",
                      "manifest": MANIFEST_NAME}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PackageError, OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"V1.5 packaging refused: {error}", file=sys.stderr)
        raise SystemExit(1)
