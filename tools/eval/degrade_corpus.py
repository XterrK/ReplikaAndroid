"""Build degraded copies of an eval corpus (noise, babble, telephone) with a matching manifest.

Deterministic (fixed seeds). The references are reused unchanged, so WER/DER differences
come only from the degraded audio. Example:

  python tools/eval/degrade_corpus.py --manifest benchmark/eval/manifest.json \
      --audio-root C:/R/eval-audio --babble-root C:/R/eval-natural-ami-audio \
      --out-audio C:/R/eval-degraded --out-manifests benchmark/eval-degraded
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

SR = 16000


def speech_rms(x: np.ndarray) -> float:
    """RMS over the louder half of 20 ms frames, so silence does not dilute the SNR."""
    frame = SR // 50
    usable = len(x) // frame * frame
    energy = (x[:usable].reshape(-1, frame) ** 2).mean(axis=1)
    loud = np.sort(energy)[len(energy) // 2:]
    return float(np.sqrt(loud.mean() + 1e-12))


def mix(x: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    noise = np.resize(noise, len(x))
    gain = speech_rms(x) / (np.sqrt((noise ** 2).mean()) + 1e-12) / (10 ** (snr_db / 20))
    y = x + gain * noise
    peak = np.abs(y).max()
    return y / peak * 0.95 if peak > 0.99 else y


def babble_source(root: Path, seed: int, seconds: int) -> np.ndarray:
    files = sorted(p for p in root.rglob("*.wav"))
    if not files:
        raise SystemExit(f"No babble wavs under {root}")
    rng = np.random.default_rng(seed)
    out = np.zeros(SR * seconds)
    for layer in range(4):  # four overlapping talkers
        y, sr = sf.read(files[rng.integers(len(files))], dtype="float64")
        if y.ndim > 1:
            y = y.mean(axis=1)
        if sr != SR:
            y = signal.resample_poly(y, SR, sr)
        start = rng.integers(max(1, len(y) - len(out)))
        out += np.resize(y[start:], len(out)) / (speech_rms(y) + 1e-12)
    return out


def telephone(x: np.ndarray) -> np.ndarray:
    sos = signal.butter(6, [300, 3400], btype="bandpass", fs=SR, output="sos")
    y = signal.sosfilt(sos, x)
    y8 = signal.resample_poly(y, 1, 2)
    mu = 255.0
    y8 = np.clip(y8 / (np.abs(y8).max() + 1e-12) * 0.9, -1, 1)
    q = np.sign(y8) * np.log1p(mu * np.abs(y8)) / np.log1p(mu)
    q = np.round(q * 127) / 127  # 8-bit mu-law
    y8 = np.sign(q) * ((1 + mu) ** np.abs(q) - 1) / mu
    return signal.resample_poly(y8, 2, 1)[: len(x)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--audio-root", type=Path, required=True)
    ap.add_argument("--babble-root", type=Path, required=True)
    ap.add_argument("--out-audio", type=Path, required=True)
    ap.add_argument("--out-manifests", type=Path, required=True)
    ap.add_argument("--splits", nargs="+", default=["dev", "holdout"])
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    conditions = {
        "white10": lambda x, i: mix(x, np.random.default_rng(100 + i).standard_normal(len(x)), 10),
        "babble10": lambda x, i: mix(x, babble_source(args.babble_root, 200 + i, 120), 10),
        "babble5": lambda x, i: mix(x, babble_source(args.babble_root, 300 + i, 120), 5),
        "phone": lambda x, i: telephone(x),
    }
    for name, fn in conditions.items():
        files = []
        for i, case in enumerate(manifest["files"]):
            if case["split"] not in args.splits:
                continue
            x, sr = sf.read(args.audio_root / case["audio"], dtype="float64")
            assert sr == SR and x.ndim == 1, case["id"]
            y = fn(x, i)
            dst = args.out_audio / name / case["audio"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            sf.write(dst, np.clip(y, -1, 1), SR, subtype="PCM_16")
            entry = dict(case)
            entry["audio_sha256"] = hashlib.sha256(dst.read_bytes()).hexdigest()
            # The runners refuse references outside the manifest folder: copy them alongside.
            ref = args.manifest.parent / case["reference"]
            (args.out_manifests / name / "references").mkdir(parents=True, exist_ok=True)
            shutil.copy2(ref, args.out_manifests / name / "references" / ref.name)
            entry["reference"] = "references/" + ref.name
            entry.setdefault("conditions", {})["degradation"] = name
            files.append(entry)
        out = dict(manifest, name=f"{manifest['name']} — {name}", files=files)
        (args.out_manifests / name).mkdir(parents=True, exist_ok=True)
        (args.out_manifests / name / "manifest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(name, len(files), "files")


if __name__ == "__main__":
    main()
