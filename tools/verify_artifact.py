#!/usr/bin/env python3
"""Inspect the final APK, preserving earlier evidence. Static checks are not a device test."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import struct
import subprocess
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = 16384
# Public Android native libraries used by the application's current dependencies.
# Other dependencies must be packaged for the same ABI; this is not a symbol/API audit.
SYSTEM_LIBRARIES = {
    "libandroid.so", "liblog.so", "libm.so", "libdl.so", "libc.so", "libz.so",
    "libEGL.so", "libGLESv2.so", "libGLESv3.so", "libOpenSLES.so", "libjnigraphics.so",
}
REQUIRED_LIBRARIES = {"libsherpa-onnx-jni.so", "libonnxruntime.so"}


def elf_report(data):
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected little-endian ELF64")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 54)
    if phentsize < 56 or phoff + phnum * phentsize > len(data):
        raise ValueError("Invalid ELF program header table")
    headers = [struct.unpack_from("<IIQQQQQQ", data, phoff + i * phentsize) for i in range(phnum)]
    loads = []
    for kind, flags, offset, vaddr, _, filesz, memsz, alignment in headers:
        if kind == 1:
            loads.append({"offset": offset, "virtualAddress": vaddr, "fileBytes": filesz,
                          "memoryBytes": memsz, "alignment": alignment,
                          "alignmentAtLeast16KiB": alignment >= PAGE and alignment & (alignment - 1) == 0,
                          "offsetAddressCongruent16KiB": offset % PAGE == vaddr % PAGE})
    dynamic = []
    for kind, _, offset, _, _, filesz, _, _ in headers:
        if kind == 2:
            for pos in range(offset, offset + filesz, 16):
                tag, value = struct.unpack_from("<qQ", data, pos)
                if tag == 0:
                    break
                dynamic.append((tag, value))
    needed_offsets = [value for tag, value in dynamic if tag == 1]
    string_address = next((value for tag, value in dynamic if tag == 5), None)
    string_offset = None
    for kind, _, offset, vaddr, _, filesz, _, _ in headers:
        if kind == 1 and string_address is not None and vaddr <= string_address < vaddr + filesz:
            string_offset = offset + string_address - vaddr
    if needed_offsets and string_offset is None:
        raise ValueError("Cannot locate DT_STRTAB for DT_NEEDED")
    needed = []
    for offset in needed_offsets:
        start = string_offset + offset
        needed.append(data[start:data.index(b"\0", start)].decode("utf-8"))
    return {"machine": struct.unpack_from("<H", data, 18)[0], "loadSegments": loads,
            "elfLoadAlignment16KiB": "PASS" if loads and all(
                s["alignmentAtLeast16KiB"] and s["offsetAddressCongruent16KiB"] for s in loads) else "FAIL",
            "needed": needed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=pathlib.Path, default=ROOT / "app/build/outputs/apk/debug/app-debug.apk")
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--sdk", type=pathlib.Path, default=pathlib.Path(os.environ.get("ANDROID_HOME", "/mnt/f/ReplikaToolchain/sdk")))
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc)
    output = args.output or ROOT / "docs/test-evidence/v1.1" / ("apk-verification-" + stamp.strftime("%Y%m%dT%H%M%S.%fZ") + ".json")
    if output.exists():
        parser.error(f"Evidence already exists; choose a new --output: {output}")
    result = {"checkedAtUtc": stamp.isoformat(), "apk": str(args.apk.resolve()), "errors": [],
              "runtime16KiBValidation": "BLOCKED: requires an actual 16 KiB Android runtime",
              "scope": "APK ZIP alignment, ELF LOAD alignment, ABI and DT_NEEDED presence; no runtime or symbol compatibility claim"}
    errors = result["errors"]
    try:
        with args.apk.open("rb") as stream:
            result.update(bytes=args.apk.stat().st_size, sha256=hashlib.file_digest(stream, "sha256").hexdigest())
        with args.apk.open("rb") as apk_stream, zipfile.ZipFile(args.apk) as archive:
            weights = [n for n in archive.namelist() if n.startswith("assets/") and n.endswith((".onnx", ".bin"))]
            result["weightsBundled"] = weights
            if weights:
                errors.append("Model weights bundled in APK")
            if any(name.endswith("/libreplika-whisper.so") for name in archive.namelist()):
                errors.append("Removed custom Whisper runtime is still packaged")
            natives = [i for i in archive.infolist() if i.filename.startswith("lib/") and i.filename.endswith(".so")]
            result["nativeLibraries"] = []
            names = {i.filename for i in natives}
            for abi in ("arm64-v8a", "x86_64"):
                for lib in sorted(REQUIRED_LIBRARIES):
                    if f"lib/{abi}/{lib}" not in names:
                        errors.append(f"Missing required library: {abi}/{lib}")
            for entry in natives:
                name = entry.filename
                abi = name.split("/")[1]
                row = {"name": name, "bytes": entry.file_size}
                result["nativeLibraries"].append(row)
                try:
                    apk_stream.seek(entry.header_offset)
                    header = apk_stream.read(30)
                    name_len, extra_len = struct.unpack_from("<HH", header, 26)
                    offset = entry.header_offset + 30 + name_len + extra_len
                    row.update(zipDataOffset=offset, zipStored=entry.compress_type == zipfile.ZIP_STORED,
                               zipAlignment16KiB="PASS" if entry.compress_type == zipfile.ZIP_STORED and offset % PAGE == 0 else "FAIL")
                    row.update(elf_report(archive.read(entry)))
                    expected_machine = {"arm64-v8a": 183, "x86_64": 62}.get(abi)
                    if row["machine"] != expected_machine:
                        errors.append(f"ELF machine does not match ABI: {name}")
                    dependencies = []
                    for needed in row.pop("needed"):
                        source = "APK same ABI" if f"lib/{abi}/{needed}" in names else "Android public native library" if needed in SYSTEM_LIBRARIES else "MISSING"
                        dependencies.append({"name": needed, "providedBy": source})
                        if source == "MISSING":
                            errors.append(f"Unresolved dependency: {name} -> {needed}")
                    row["dependencies"] = dependencies
                    if row["zipAlignment16KiB"] != "PASS" or row["elfLoadAlignment16KiB"] != "PASS":
                        errors.append(f"16 KiB static alignment failed: {name}")
                except (ValueError, IndexError, struct.error) as exc:
                    row["error"] = str(exc)
                    errors.append(f"Invalid native library {name}: {exc}")
        zipalign = args.sdk / "build-tools/35.0.0/zipalign"
        try:
            check = subprocess.run([str(zipalign), "-c", "-P", "16", "4", str(args.apk)], capture_output=True, text=True)
            result["zipalign"] = {"command": [str(zipalign), "-c", "-P", "16", "4", str(args.apk)], "exitCode": check.returncode,
                                  "stdout": check.stdout, "stderr": check.stderr}
            if check.returncode:
                errors.append("Android zipalign verification failed")
        except OSError as exc:
            errors.append(f"Cannot run zipalign: {exc}")
    except (OSError, zipfile.BadZipFile) as exc:
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
