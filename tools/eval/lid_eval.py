#!/usr/bin/env python3
"""Measure the per-file language decision on corpus manifests (host CPU).

VAD/chunking reproduces the production context600 path (Silero .5/.25/.25, 600 ms
pre-roll, 20 s energy split); the decision itself is tools/eval/language_id.py.
References are never read. Optionally every single source clip of a folder is also
classified as its own file (stress test on short utterances).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import language_id  # noqa: E402
import pipeline as base  # noqa: E402
import pipeline_words as words  # noqa: E402
from vad_words import plan_vad_chunks  # noqa: E402


def read_audio(path, np):
    try:
        return base._read_canonical_wav(Path(path), np)
    except ValueError:
        # Short source clips are 22/24/48 kHz; LID-only resampling (not the Android decoder).
        import soundfile as sf
        from math import gcd
        from scipy.signal import resample_poly
        audio, rate = sf.read(str(path), dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)
        g = gcd(16000, rate)
        return resample_poly(audio, 16000 // g, rate // g).astype(np.float32)


def chunks_for(path, model_root, np, sherpa):
    samples = read_audio(path, np)
    stages = {}
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.
    gain = base.quiet_gain(peak)
    spans = words._detect_with_durations(samples, gain, model_root, stages, np, sherpa, .25, .25, .5)
    bounded = base.context_spans(spans, len(samples) * 1000 // 16000, 600, 0)
    chunks = plan_vad_chunks(bounded, samples, max_ms=20000, energy_split=True)
    if gain != 1:
        samples = samples * np.float32(gain)
    return samples, [(c.start_ms, c.end_ms) for c in chunks], stages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", action="append", nargs=3, metavar=("NAME", "MANIFEST", "AUDIO_ROOT"), default=[])
    parser.add_argument("--clips", action="append", nargs=3, metavar=("NAME", "FOLDER", "LANG"), default=[])
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--per-segment", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import numpy as np
    import sherpa_onnx as sherpa
    load_started = time.perf_counter()
    identifier = language_id.make_identifier(args.model_root, args.threads)
    load_ms = (time.perf_counter() - load_started) * 1000
    cases = []
    for name, manifest_path, audio_root in args.set:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        for item in manifest["files"]:
            cases.append((name, item["id"], Path(audio_root) / item["audio"], item.get("language", "ru")))
    for name, folder, lang in args.clips:
        for path in sorted(Path(folder).glob("*.wav")):
            cases.append((name, path.stem, path, lang))
    rows = []
    for set_name, case_id, path, expected in cases:
        samples, chunks, _ = chunks_for(path, args.model_root, np, sherpa)
        result = language_id.identify(samples, chunks, args.model_root, args.threads,
                                      per_segment=args.per_segment, identifier=identifier)
        rows.append({"set": set_name, "id": case_id, "expected": expected, "decided": result["language"],
                     "correct": result["language"] == expected, "probeLabels": result["probeLabels"],
                     "probeMs": [sum(e - s for s, e in probe) for probe in result["probes"]],
                     "segmentLanguages": result["segmentLanguages"],
                     "audioMs": len(samples) * 1000 // 16000, "lidMs": round(result["fileDecisionMs"], 1),
                     "lidWithPerSegmentMs": round(result["totalMs"], 1) if args.per_segment else None})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    summary = {}
    for set_name in dict.fromkeys(r["set"] for r in rows):
        group = [r for r in rows if r["set"] == set_name]
        times = sorted(r["lidMs"] for r in group)
        summary[set_name] = {"files": len(group), "correct": sum(r["correct"] for r in group),
                             "accuracy": sum(r["correct"] for r in group) / len(group),
                             "lidMsMedian": times[len(times) // 2], "lidMsMax": times[-1]}
    report = {"schema_version": 1, "scope": "Host CPU, sherpa-onnx " + sherpa.__version__ + ", whisper tiny int8 LID; "
              "lidMs = per-file decision (probes + vote), excludes the one-time model load and VAD; lidWithPerSegmentMs adds the experimental per-chunk mode; references never read",
              "host": {"platform": platform.platform(), "logical_cpus": os.cpu_count()},
              "threads": args.threads, "modelLoadMs": round(load_ms, 1),
              "policy": {"speechBudgetMs": language_id.SPEECH_BUDGET_MS, "probeMaxMs": language_id.PROBE_MAX_MS,
                         "probeMinMs": language_id.PROBE_MIN_MS, "maxProbes": language_id.MAX_PROBES,
                         "vote": "strict majority of 'en' -> en, otherwise ru"},
              "summary": summary, "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
