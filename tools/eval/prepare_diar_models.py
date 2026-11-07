#!/usr/bin/env python3
"""Fetch/verify the pinned step-C embedding catalog; optionally load, never infer.

Example (weights stay outside the checkout):
  python tools/eval/prepare_diar_models.py --output-root /path/to/embedding-cache \
      --probe --report /path/to/fresh-model-provenance.json

--check is fully offline and will not download missing files. Existing files with
incorrect pins are rejected, rather than silently replaced. The repository's
baseline is only verified and is never written by this tool.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "configs/eval/diar-models.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_catalog(path: Path) -> dict[str, Any]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("models"), list):
        raise ValueError("Expected schema_version=1 and a models list")
    ids: set[str] = set()
    for model in catalog["models"]:
        if not isinstance(model, dict):
            raise ValueError("Each model must be an object")
        model_id = model.get("id")
        if not isinstance(model_id, str) or not re.fullmatch(r"[a-z0-9_]+", model_id):
            raise ValueError("Invalid model id")
        if model_id in ids:
            raise ValueError(f"Duplicate model id: {model_id}")
        ids.add(model_id)
        relative = model.get("path")
        if not isinstance(relative, str) or not relative:
            raise ValueError(f"Missing path: {model_id}")
        relpath = Path(relative)
        if relpath.is_absolute() or ".." in relpath.parts or "\\" in relative:
            raise ValueError(f"Model path must be a contained relative path: {model_id}")
        if type(model.get("repoRelative")) is not bool:
            raise ValueError(f"repoRelative must be a boolean: {model_id}")
        if type(model.get("size")) is not int or model["size"] <= 0:
            raise ValueError(f"Invalid byte size: {model_id}")
        if not isinstance(model.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", model["sha256"]):
            raise ValueError(f"Invalid SHA-256: {model_id}")
        if urlparse(model.get("url", "")).scheme != "https":
            raise ValueError(f"HTTPS download URL required: {model_id}")
        source = model.get("source", {})
        if type(source.get("asset_id")) is not int or source["asset_id"] <= 0:
            raise ValueError(f"Missing pinned GitHub asset id: {model_id}")
        if not isinstance(source.get("asset_name"), str):
            raise ValueError(f"Missing pinned GitHub asset name: {model_id}")
    if catalog.get("baseline_id") not in ids:
        raise ValueError("baseline_id must identify a catalog entry")
    return catalog


def model_path(model: dict[str, Any], output_root: Path, project_root: Path) -> Path:
    root = (project_root if model["repoRelative"] else output_root).resolve()
    path = (root / model["path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Model path escapes its root: {model['id']}")
    return path


def check_file(path: Path, model: dict[str, Any]) -> None:
    if path.stat().st_size != model["size"]:
        raise ValueError(f"Byte-size mismatch for {model['id']}")
    if sha256_file(path) != model["sha256"]:
        raise ValueError(f"SHA-256 mismatch for {model['id']}")


def request(url: str) -> Request:
    return Request(url, headers={"User-Agent": "Replika-diar-model-preparer/1"})


def download_model(path: Path, model: dict[str, Any]) -> None:
    """Confirm immutable asset identity, then verify a temporary byte download."""
    source = model["source"]
    api_url = "https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/assets/" + str(source["asset_id"])
    with urlopen(request(api_url), timeout=60) as response:
        metadata = json.load(response)
    expected = {
        "id": source["asset_id"], "name": source["asset_name"],
        "size": model["size"], "browser_download_url": model["url"],
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"Pinned asset metadata mismatch ({key}): {model['id']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=path.name + ".", suffix=".part", dir=path.parent, delete=False) as destination:
            temporary = Path(destination.name)
            received = 0
            with urlopen(request(model["url"]), timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > model["size"]:
                        raise ValueError(f"Download exceeds pinned size: {model['id']}")
                    destination.write(chunk)
        check_file(temporary, model)
        if path.exists():
            raise FileExistsError(f"Destination appeared during download: {path}")
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def probe_model(path: Path, expected_dim: int, required_runtime: str) -> dict[str, Any]:
    import sherpa_onnx

    if sherpa_onnx.__version__ != required_runtime:
        raise ValueError(f"Expected sherpa-onnx {required_runtime}, found {sherpa_onnx.__version__}")
    started = time.perf_counter()
    extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(path), provider="cpu", num_threads=1, debug=False,
        )
    )
    dimension = extractor.dim
    del extractor
    gc.collect()
    if dimension != expected_dim:
        raise ValueError(f"Unexpected embedding dimension: {dimension}; expected {expected_dim}")
    return {
        "status": "load_ok", "dimension": dimension, "runtime": sherpa_onnx.__version__,
        "provider": "cpu", "num_threads": 1, "load_wall_sec": round(time.perf_counter() - started, 6),
        "audio_processed": False, "embedding_inference_performed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--model", action="append", dest="models", help="Select an id; repeat for more (default: all)")
    parser.add_argument("--check", action="store_true", help="Offline verification only; never download")
    parser.add_argument("--probe", action="store_true", help="Load extractor and check dimension; never supply audio")
    parser.add_argument("--report", type=Path, help="Write provenance JSON to a fresh output file")
    args = parser.parse_args(argv)
    if args.report and args.report.exists():
        parser.error("--report already exists; choose a fresh evidence path")
    try:
        catalog = load_catalog(args.catalog)
        ids = {entry["id"] for entry in catalog["models"]}
        selected = set(args.models or ids)
        if selected - ids:
            raise ValueError("Unknown model ids: " + ", ".join(sorted(selected - ids)))
        report: dict[str, Any] = {
            "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "catalog_sha256": sha256_file(args.catalog), "required_runtime": catalog["required_runtime"],
            "scope": "Byte verification and optional extractor load/dimension only; no audio/model inference or quality measurement",
            "offline_check": args.check, "models": [],
        }
        for model in catalog["models"]:
            if model["id"] not in selected:
                continue
            item = {"id": model["id"], "path": model["path"], "repoRelative": model["repoRelative"],
                    "size": model["size"], "sha256": model["sha256"], "source": model["source"],
                    "license": model["license"], "downloaded": False}
            try:
                path = model_path(model, args.output_root, args.project_root)
                if not path.is_file():
                    if args.check or model["repoRelative"]:
                        raise FileNotFoundError(f"Missing pinned model: {model['id']} ({path})")
                    download_model(path, model)
                    item["downloaded"] = True
                check_file(path, model)
                item["status"] = "verified"
                if args.probe:
                    item["probe"] = probe_model(path, model["embedding_dimension"], catalog["required_runtime"])
            except Exception as exc:
                item["status"] = "failed"
                item["error"] = f"{type(exc).__name__}: {exc}"
            report["models"].append(item)
        report["success"] = all(item["status"] == "verified" for item in report["models"])
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
        print(json.dumps({"success": report["success"], "models": [
            {key: item[key] for key in ("id", "status", "error", "probe") if key in item}
            for item in report["models"]]}, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if report["success"] else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    sys.exit(main())
