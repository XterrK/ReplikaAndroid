#!/usr/bin/env python3
"""Build a deterministic embedded ZIP from the existing verified local pack; never download models."""
import argparse
import hashlib
import json
import os
import pathlib
import stat
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHUNK = 1024 * 1024
SUPPORT_GROUPS = {"diar", "vad"}


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        while chunk := stream.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(name):
    path = pathlib.PurePosixPath(name)
    if (not name or "\\" in name or "\0" in name or ":" in name or path.is_absolute()
            or ".." in path.parts or str(path) != name):
        raise ValueError(f"Unsafe ZIP path: {name!r}")
    return name


def read_lock(path):
    raw = pathlib.Path(path).read_bytes()
    manifest = json.loads(raw)
    files = manifest.get("files", [])
    expected = {}
    for item in files:
        name = safe_path(item["path"])
        if name in expected or item["size"] <= 0:
            raise ValueError(f"Invalid or duplicate model in lock: {name}")
        digest = item["sha256"]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"Invalid SHA-256 in lock: {name}")
        expected[name] = item
    groups = {item["group"] for item in files}
    asr = groups - SUPPORT_GROUPS
    if len(expected) != 7 or len(asr) != 1 or not next(iter(asr)).startswith("giga-") or not SUPPORT_GROUPS <= groups:
        raise ValueError("Expected one seven-file GigaAM/VAD/diarization lock")
    return raw, manifest, expected


def archive_entries(archive, manifest, expected):
    entries = {}
    for entry in archive.infolist():
        name = safe_path(entry.filename)
        mode = entry.external_attr >> 16
        if entry.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
            raise ValueError(f"Only regular files are accepted: {name}")
        if name in entries:
            raise ValueError(f"Duplicate ZIP entry: {name}")
        if name not in expected and name != "manifest.json" and not name.startswith("licenses/"):
            raise ValueError(f"Unexpected entry in model pack: {name}")
        if entry.flag_bits & 1:
            raise ValueError(f"Encrypted ZIP entry is unsupported: {name}")
        entries[name] = entry
    missing = {"manifest.json", *expected} - entries.keys()
    if missing:
        raise ValueError(f"Missing pack entries: {sorted(missing)}")
    if entries["manifest.json"].file_size > 1024 * 1024:
        raise ValueError("Pack manifest is unexpectedly large")
    if json.loads(archive.read("manifest.json")) != manifest:
        raise ValueError("Pack manifest differs from app/src/main/assets/models-lock.json")
    if not any(name.startswith("licenses/") for name in entries):
        raise ValueError("Model redistribution notices are missing")
    for name, item in expected.items():
        if entries[name].file_size != item["size"]:
            raise ValueError(f"Model size mismatch: {name}")
    return entries


def stream_copy(source, destination=None):
    digest = hashlib.sha256()
    count = 0
    while chunk := source.read(CHUNK):
        count += len(chunk)
        digest.update(chunk)
        if destination is not None:
            destination.write(chunk)
    return count, digest.hexdigest()


def verify_pack(path, lock_path):
    """Verify all expected model bytes using bounded-memory streaming; return a small inventory."""
    lock_raw, manifest, expected = read_lock(lock_path)
    with zipfile.ZipFile(path) as archive:
        entries = archive_entries(archive, manifest, expected)
        models = []
        for name, item in expected.items():
            with archive.open(name) as stream:
                count, digest = stream_copy(stream)
            if count != item["size"] or digest != item["sha256"]:
                raise ValueError(f"Model SHA-256/size mismatch: {name}")
            models.append({"path": name, "bytes": count, "sha256": digest})
        licenses = sorted(name for name in entries if name.startswith("licenses/"))
        # Consume non-model entries too, so their CRC errors cannot escape verification.
        for name in ["manifest.json", *licenses]:
            with archive.open(name) as stream:
                stream_copy(stream)
    return {"manifestSha256": hashlib.sha256(lock_raw).hexdigest(), "models": models,
            "modelBytes": sum(item["size"] for item in expected.values()), "licenses": licenses}


def prepare(source, lock, output, metadata):
    source, lock, output, metadata = map(pathlib.Path, (source, lock, output, metadata))
    if source.resolve() == output.resolve():
        raise ValueError("Generated output must not replace the original model pack")
    _, manifest, expected = read_lock(lock)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".part", dir=output.parent, delete=False) as temp:
        temporary = pathlib.Path(temp.name)
    try:
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as generated:
            entries = archive_entries(original, manifest, expected)
            ordered = ["manifest.json", *expected,
                       *sorted(name for name in entries if name.startswith("licenses/"))]
            for name in ordered:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                info._compresslevel = 6
                with original.open(name) as incoming, generated.open(info, "w", force_zip64=True) as outgoing:
                    count, digest = stream_copy(incoming, outgoing)
                if name in expected and (count != expected[name]["size"] or digest != expected[name]["sha256"]):
                    raise ValueError(f"Source model SHA-256/size mismatch: {name}")
        inventory = verify_pack(temporary, lock)
        inventory.update(source=str(source.resolve()), sourceBytes=source.stat().st_size,
                         sourceSha256=sha256_file(source), embeddedAsset="offline/replika-models.zip",
                         generatedBytes=temporary.stat().st_size, generatedSha256=sha256_file(temporary),
                         compression="ZIP DEFLATE level 6; APK stores this ZIP without a second compression layer")
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        temporary.replace(output)
        metadata.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=metadata.name + ".",
                                         suffix=".part", dir=metadata.parent, delete=False) as stream:
            metadata_temp = pathlib.Path(stream.name)
            json.dump(inventory, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        metadata_temp.replace(metadata)
        return inventory
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, default=ROOT / "model-pack/replika-offline-pack-v1.5.zip")
    parser.add_argument("--manifest", type=pathlib.Path, default=ROOT / "app/src/main/assets/models-lock.json")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "app/build/generated/embedded-models/assets/offline/replika-models.zip")
    parser.add_argument("--metadata", type=pathlib.Path, default=ROOT / "app/build/generated/embedded-models/pack-verification.json")
    args = parser.parse_args()
    try:
        result = prepare(args.source, args.manifest, args.output, args.metadata)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        parser.exit(1, f"Embedded pack preparation failed: {exc}\n")
    print(json.dumps({"output": str(args.output), "metadata": str(args.metadata),
                      "bytes": result["generatedBytes"], "sha256": result["generatedSha256"],
                      "modelBytes": result["modelBytes"], "models": len(result["models"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
