"""Denoise every file of an eval manifest with sherpa-onnx GTCRN and write a matching manifest.

Experiment helper: answers "does speech enhancement before the whole pipeline help or hurt?".
  python tools/eval/denoise_corpus.py --manifest M --audio-root A --model C:/R/denoise/gtcrn_simple.onnx \
      --out-audio OUT --out-manifest OUT_MANIFEST_DIR [--splits dev holdout]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--audio-root", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--out-audio", type=Path, required=True)
    ap.add_argument("--out-manifest", type=Path, required=True)
    ap.add_argument("--splits", nargs="+", default=None)
    args = ap.parse_args()
    config = sherpa_onnx.OfflineSpeechDenoiserConfig(model=sherpa_onnx.OfflineSpeechDenoiserModelConfig(
        gtcrn=sherpa_onnx.OfflineSpeechDenoiserGtcrnModelConfig(model=str(args.model)), num_threads=2))
    denoiser = sherpa_onnx.OfflineSpeechDenoiser(config)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    files = []
    for case in manifest["files"]:
        if args.splits and case["split"] not in args.splits:
            continue
        x, sr = sf.read(args.audio_root / case["audio"], dtype="float32")
        out = denoiser(x, sr)
        y = np.asarray(out.samples, dtype="float32")
        if out.sample_rate != sr:
            raise SystemExit(f"Unexpected denoiser rate {out.sample_rate}")
        y = np.resize(y, len(x)) if len(y) != len(x) else y
        dst = args.out_audio / case["audio"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        sf.write(dst, np.clip(y, -1, 1), sr, subtype="PCM_16")
        entry = dict(case)
        entry["audio_sha256"] = hashlib.sha256(dst.read_bytes()).hexdigest()
        # The runners refuse references outside the manifest folder: copy them alongside.
        ref = args.manifest.parent / case["reference"]
        (args.out_manifest / "references").mkdir(parents=True, exist_ok=True)
        shutil.copy2(ref, args.out_manifest / "references" / ref.name)
        entry["reference"] = "references/" + ref.name
        entry.setdefault("conditions", {})["denoised"] = "gtcrn_simple"
        files.append(entry)
    args.out_manifest.mkdir(parents=True, exist_ok=True)
    (args.out_manifest / "manifest.json").write_text(json.dumps(dict(manifest, files=files), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(len(files), "files")


if __name__ == "__main__":
    main()
