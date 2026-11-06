#!/usr/bin/env python3
"""Verify portable model/native inputs; print a relative-path SHA-256 manifest.

Read-only unless --output is explicitly supplied. No downloads or native imports.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile
import zlib

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
ABIS = ("arm64-v8a", "x86_64")
# Extracted from the SHA-256-verified sherpa-onnx v2.0.1 Android archive in
# tools/native-lock.json. These are library bytes, not hashes of an APK's stripped copies.
NATIVE_PINS = {
    "arm64-v8a/libonnxruntime.so": (
        22249560, "33847ad43bffe204699fd4a27f7f3603452a8cdaf2f9a44983a0bc31ffcf2da1"),
    "arm64-v8a/libsherpa-onnx-jni.so": (
        4609320, "5db8f89f12b2c900a98c9e01e00c475c59db35e9437a62e36e27839ec48b5575"),
    "x86_64/libonnxruntime.so": (
        25581120, "087e84297cad64acb823c3d901d6e0cc934e91add7cdb20da802cd1c0bea5c3e"),
    "x86_64/libsherpa-onnx-jni.so": (
        5053592, "878d61116f244131263eec24297ef05bf508d02bccdede2a4e3ad3202bbdaa48"),
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def relative_file(root, name):
    """Reject unsafe or escaping paths in a supplied workspace manifest."""
    relative = PurePosixPath(name)
    if (not name or relative.is_absolute() or ".." in relative.parts
            or "\\" in name or ":" in name or str(relative) != name):
        raise ValueError("Invalid workspace-relative path: " + repr(name))
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Input resolves outside the workspace: " + name)
    return path


def check_file(root, name, size, digest, group, report):
    row = {"path": name, "group": group, "expectedBytes": size,
           "expectedSha256": digest, "status": "FAIL"}
    report["files"].append(row)
    try:
        path = relative_file(root, name)
        row["bytes"] = path.stat().st_size
        row["sha256"] = sha256_file(path)
        if row["bytes"] != size or row["sha256"] != digest:
            raise ValueError("SHA-256 or size mismatch")
        row["status"] = "PASS"
    except (OSError, ValueError) as exc:
        report["errors"].append(f"{name}: {exc}")


def verify_workspace(root=ROOT, *, models=True, abis=ABIS, pack=None):
    # Reuse the existing pack format/path/CRC checks, without running its writer.
    from prepare_embedded_pack import read_lock, verify_pack

    root = Path(root)
    report = {"schemaVersion": 1, "status": "FAIL", "files": [], "errors": [],
              "scope": {"models": models, "abis": list(abis), "pack": pack is not None}}
    lock = root / "app/src/main/assets/models-lock.json"
    try:
        raw, _, expected = read_lock(lock)
        report["modelManifestSha256"] = hashlib.sha256(raw).hexdigest()
        if models:
            for name, spec in expected.items():
                check_file(root, "model-pack/" + name, spec["size"], spec["sha256"],
                           "model", report)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["errors"].append(f"Model lock: {exc}")
    for name, (size, digest) in NATIVE_PINS.items():
        if name.split("/", 1)[0] in abis:
            check_file(root, "app/src/main/jniLibs/" + name, size, digest, "native", report)
    # A stale custom Whisper .so would still get packaged by Gradle. Fail instead
    # of silently shipping it; leave all cleanup decisions to the caller.
    native_root = root / "app/src/main/jniLibs"
    for abi in abis:
        for path in sorted((native_root / abi).glob("*.so")):
            if f"{abi}/{path.name}" not in NATIVE_PINS:
                report["errors"].append("Unpinned native library: " + path.relative_to(root).as_posix())
    if pack is not None:
        try:
            pack_path = Path(pack)
            if not pack_path.is_absolute():
                pack_path = root / pack_path
            name = pack_path.resolve().relative_to(root.resolve()).as_posix()
            relative_file(root, name)
            inventory = verify_pack(pack_path, lock)
            report["files"].append({"path": name, "group": "pack", "status": "PASS",
                                    "bytes": pack_path.stat().st_size, "sha256": sha256_file(pack_path)})
            report["packModelBytes"] = inventory["modelBytes"]
        except (OSError, ValueError, KeyError, TypeError, EOFError,
                zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error) as exc:
            report["errors"].append(f"Model pack: {exc}")
    report["status"] = "FAIL" if report["errors"] else "PASS"
    return report


def compare_manifest(report, manifest):
    """Compare a saved successful inventory to the current independently pinned inputs."""
    previous = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if (not isinstance(previous, dict) or previous.get("schemaVersion") != 1 or previous.get("status") != "PASS"
            or previous.get("scope") != report["scope"]):
        raise ValueError("Saved manifest must be successful and use the same models/ABI/pack options")
    if previous.get("modelManifestSha256") != report.get("modelManifestSha256"):
        raise ValueError("Saved manifest has a different model lock")
    def inventory(value):
        rows = value["files"]
        items = {r["path"]: (r["bytes"], r["sha256"], r["group"]) for r in rows}
        if len(items) != len(rows):
            raise ValueError("Duplicate paths in workspace manifest")
        return items
    if inventory(previous) != inventory(report):
        raise ValueError("Saved manifest differs from verified workspace files")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-only", action="store_true", help="Standard APK: do not require loose models")
    parser.add_argument("--abi", action="append", choices=ABIS, help="Default: verify both ABIs")
    parser.add_argument("--pack", type=Path, help="Also stream-verify a ZIP inside the workspace against the model lock")
    parser.add_argument("--manifest", type=Path, help="Also compare a previously exported workspace manifest")
    parser.add_argument("--output", type=Path, help="Create a JSON manifest after success; never overwrite")
    parser.add_argument("--json", action="store_true", help="Print the complete JSON report to stdout")
    args = parser.parse_args(argv)
    report = verify_workspace(models=not args.native_only, abis=tuple(dict.fromkeys(args.abi or ABIS)), pack=args.pack)
    if args.manifest and not report["errors"]:
        try:
            compare_manifest(report, args.manifest)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report["errors"].append(f"Workspace manifest: {exc}")
    report["status"] = "FAIL" if report["errors"] else "PASS"
    if args.output and not report["errors"]:
        try:
            # The caller chooses/creates its destination directory. No implicit writes.
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(report, indent=2) + "\n")
        except OSError as exc:
            report["errors"].append(f"Manifest output: {exc}")
            report["status"] = "FAIL"
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for row in report["files"]:
            print(f"{row['status']} {row['path']}")
        for error in report["errors"]:
            print("ERROR " + error, file=sys.stderr)
        print(f"Workspace integrity: {report['status']} ({len(report['files'])} files)")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
