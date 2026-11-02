#!/usr/bin/env python3
"""Statically verify an All-in-One APK; this does not establish device/runtime compatibility."""
import argparse
import collections
import datetime
import hashlib
import json
import os
import pathlib
import struct
import subprocess
import zipfile

from prepare_embedded_pack import CHUNK, verify_pack
from verify_artifact import PAGE, REQUIRED_LIBRARIES, SYSTEM_LIBRARIES, elf_report

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSET = "assets/offline/replika-models.zip"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=pathlib.Path, required=True)
    parser.add_argument("--abi", action="append", choices=("arm64-v8a", "x86_64"))
    parser.add_argument("--manifest", type=pathlib.Path, default=ROOT / "app/src/main/assets/models-lock.json")
    parser.add_argument("--pack-metadata", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--sdk", type=pathlib.Path, default=pathlib.Path(os.environ.get("ANDROID_HOME", "/mnt/f/ReplikaToolchain/sdk")))
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc)
    output = args.output or ROOT / "docs/test-evidence/v1.2.1" / (
        "all-in-one-apk-verification-" + stamp.strftime("%Y%m%dT%H%M%S.%fZ") + ".json")
    if output.exists():
        parser.error(f"Evidence already exists; choose a new --output: {output}")
    expected_abis = set(args.abi or ["arm64-v8a"])
    result = {"checkedAtUtc": stamp.isoformat(), "apk": str(args.apk.resolve()), "expectedAbis": sorted(expected_abis),
              "errors": [], "runtime16KiBValidation": "BLOCKED: requires an actual 16 KiB Android runtime",
              "scope": "Pack/model hashes, one embedded ZIP, target ABIs, ZIP/ELF 16 KiB alignment and DT_NEEDED; no inference/runtime claim"}
    errors = result["errors"]
    try:
        result["bytes"] = args.apk.stat().st_size
        with args.apk.open("rb") as stream:
            digest = hashlib.sha256()
            while chunk := stream.read(CHUNK):
                digest.update(chunk)
            result["sha256"] = digest.hexdigest()
        with args.apk.open("rb") as apk_stream, zipfile.ZipFile(args.apk) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            duplicates = sorted(name for name, count in collections.Counter(names).items() if count > 1)
            if duplicates:
                errors.append(f"Duplicate APK ZIP entries: {duplicates}")
            packed = [entry for entry in entries if entry.filename == ASSET]
            result["embeddedPackCopies"] = len(packed)
            loose_models = [name for name in names if name.startswith("assets/") and name.endswith((".onnx", ".bin", ".ggml", ".gguf"))]
            result["looseModelAssets"] = loose_models
            if loose_models:
                errors.append("Unexpected duplicate/loose model weights outside the embedded pack")
            if len(packed) != 1:
                errors.append("Expected exactly one embedded model pack asset")
            else:
                pack = packed[0]
                pack_digest = hashlib.sha256()
                with archive.open(pack) as stream:
                    while chunk := stream.read(CHUNK):
                        pack_digest.update(chunk)
                result["embeddedPack"] = {"name": ASSET, "bytes": pack.file_size, "apkStoredBytes": pack.compress_size,
                                          "zipStored": pack.compress_type == zipfile.ZIP_STORED,
                                          "sha256": pack_digest.hexdigest()}
                if pack.compress_type != zipfile.ZIP_STORED:
                    errors.append("Embedded ZIP should be stored without a second APK compression layer")
                # ZipExtFile is seekable; nested ZIP verification streams model bytes without a full archive allocation.
                with archive.open(pack) as stream:
                    result["embeddedPack"].update(verify_pack(stream, args.manifest))
                if args.pack_metadata:
                    metadata = json.loads(args.pack_metadata.read_text(encoding="utf-8"))
                    if (metadata["generatedSha256"] != result["embeddedPack"]["sha256"]
                            or metadata["generatedBytes"] != pack.file_size):
                        errors.append("Embedded pack differs from generated pack metadata")
            natives = [entry for entry in entries if entry.filename.startswith("lib/") and entry.filename.endswith(".so")]
            native_names = {entry.filename for entry in natives}
            actual_abis = {entry.filename.split("/")[1] for entry in natives}
            result["actualAbis"] = sorted(actual_abis)
            if actual_abis != expected_abis:
                errors.append(f"Expected only {sorted(expected_abis)}; packaged {sorted(actual_abis)}")
            for abi in sorted(expected_abis):
                for library in sorted(REQUIRED_LIBRARIES):
                    if f"lib/{abi}/{library}" not in native_names:
                        errors.append(f"Missing required library: {abi}/{library}")
            result["nativeLibraries"] = []
            for entry in natives:
                name = entry.filename
                abi = name.split("/")[1]
                row = {"name": name, "bytes": entry.file_size}
                result["nativeLibraries"].append(row)
                apk_stream.seek(entry.header_offset)
                header = apk_stream.read(30)
                name_len, extra_len = struct.unpack_from("<HH", header, 26)
                offset = entry.header_offset + 30 + name_len + extra_len
                row.update(zipDataOffset=offset, zipStored=entry.compress_type == zipfile.ZIP_STORED,
                           zipAlignment16KiB="PASS" if entry.compress_type == zipfile.ZIP_STORED and offset % PAGE == 0 else "FAIL")
                row.update(elf_report(archive.read(entry)))
                if row["machine"] != {"arm64-v8a": 183, "x86_64": 62}.get(abi):
                    errors.append(f"ELF machine does not match ABI: {name}")
                dependencies = []
                for needed in row.pop("needed"):
                    source = ("APK same ABI" if f"lib/{abi}/{needed}" in native_names else
                              "Android public native library" if needed in SYSTEM_LIBRARIES else "MISSING")
                    dependencies.append({"name": needed, "providedBy": source})
                    if source == "MISSING":
                        errors.append(f"Unresolved dependency: {name} -> {needed}")
                row["dependencies"] = dependencies
                if row["zipAlignment16KiB"] != "PASS" or row["elfLoadAlignment16KiB"] != "PASS":
                    errors.append(f"16 KiB static alignment failed: {name}")
        zipalign = args.sdk / "build-tools/35.0.0/zipalign"
        check = subprocess.run([str(zipalign), "-c", "-P", "16", "4", str(args.apk)], capture_output=True, text=True)
        result["zipalign"] = {"exitCode": check.returncode, "stdout": check.stdout, "stderr": check.stderr}
        if check.returncode:
            errors.append("Android zipalign verification failed")
    except (OSError, ValueError, KeyError, IndexError, struct.error, zipfile.BadZipFile) as exc:
        errors.append(str(exc))
    result["staticVerification"] = "FAIL" if errors else "PASS"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({"output": str(output), "staticVerification": result["staticVerification"], "errors": errors}, ensure_ascii=False))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
