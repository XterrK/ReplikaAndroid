#!/usr/bin/env python3
"""Task 07 runner: production C2 diarization + context600 ASR with a language mode.

Uses pipeline_refined.process with the frozen C2 parameters (configs/eval/c2-window-selected-full.json)
and language=ru|en|auto. Audio/reference hashes are checked against the manifest before and after
inference; references are only read by the scorer. Metrics come from tools/eval/score.py unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools/eval"))  # run.py imports its sibling hostmem as a top-level module
from tools.eval import pipeline_refined as refined  # noqa: E402
from tools.eval import score as scoring  # noqa: E402
from tools.eval.run import aggregate, confined, digest, validated_hypothesis, write_json  # noqa: E402


def summarize(output):
    """Re-aggregate an existing output folder from its per-case files (no inference)."""
    records = []
    for case_file in sorted(Path(output).glob("*/case.json")):
        record = json.loads(case_file.read_text(encoding="utf-8"))
        metric = record["metrics"]
        metric.setdefault("native_speaker_count_error", abs(metric["native_speaker_count"] - metric["speakers"]["reference"]))
        records.append(record)
    summary = {"status": "COMPLETE", "all": aggregate(records),
               "decidedLanguages": {r["id"]: r["decidedLanguage"] for r in records}}
    write_json(Path(output) / "summary.json", summary)
    meta = json.loads((Path(output) / "run.json").read_text(encoding="utf-8"))
    meta.update(status="COMPLETE", summarized_at=datetime.now(timezone.utc).isoformat())
    write_json(Path(output) / "run.json", meta)
    return summary


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--summarize":
        summarize(sys.argv[2])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, default=REPO / "model-pack")
    parser.add_argument("--c2-config", type=Path, default=REPO / "configs/eval/c2-window-selected-full.json")
    parser.add_argument("--language", choices=["ru", "en", "auto"], required=True)
    parser.add_argument("--per-segment-language", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="+")
    args = parser.parse_args()
    c2 = json.loads(args.c2_config.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Output exists; choose a fresh path")
    output.mkdir(parents=True)
    meta = {"schema_version": 1, "status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
            "language": args.language, "perSegmentLanguage": args.per_segment_language,
            "c2_config": {"path": str(args.c2_config.relative_to(REPO)), "sha256": digest(args.c2_config), "id": c2["id"]},
            "manifest": {"path": str(args.manifest.resolve().relative_to(REPO)), "sha256": digest(args.manifest)},
            "lock_sha256": digest(REPO / "app/src/main/assets/models-lock.json"),
            "code_sha256": {name: digest(REPO / "tools/eval" / name) for name in
                            ("pipeline_refined.py", "pipeline_words.py", "language_id.py", "score.py", "run_lang.py")},
            "host": {"platform": platform.platform(), "python": sys.version, "logical_cpus": os.cpu_count()},
            "scope": "Host CPU; not Android/ARM/phone. Shared PC: timings may include concurrent load from other sessions."}
    write_json(output / "run.json", meta)
    records = []
    for case in manifest["files"]:
        if args.cases and case["id"] not in args.cases:
            continue
        audio = confined(args.audio_root, case["audio"])
        reference_path = confined(args.manifest.parent, case["reference"])
        audio_hash, reference_hash = digest(audio), digest(reference_path)
        if audio_hash != case["audio_sha256"] or reference_hash != case.get("reference_sha256", reference_hash):
            raise ValueError("Pinned input hash mismatch: " + case["id"])
        started = time.perf_counter()
        actual = refined.process(audio, args.model_root, expected_speakers=-1, threads=c2["threads"],
                                 model_id=c2["model_id"], window_shift=c2["window_shift"],
                                 native_threshold=c2["native_threshold"], strategy="window_v1",
                                 window_config=c2["window_config"], cpu_plan="v16",
                                 language=args.language, per_segment_language=args.per_segment_language)
        if digest(audio) != audio_hash or digest(reference_path) != reference_hash:
            raise ValueError("Input changed during inference: " + case["id"])
        hypothesis = validated_hypothesis(actual["transcript"])
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        metric = scoring.score(reference, hypothesis, duration_ms=actual["duration_ms"], processing_ms=actual["processing_ms"])
        native_turns = [{"speaker_id": "native_" + str(t["speakerId"]), "start_ms": t["startMs"],
                         "end_ms": t["endMs"], "text": ""} for t in actual["diagnostics"]["diarizationTurns"]]
        for collar in (0, 250):
            metric[f"native_der_collar_{collar}ms"] = scoring.der(reference["transcript"], native_turns,
                                                                  actual["duration_ms"], collar_ms=collar)
        metric["native_speaker_count"] = len({t["speaker_id"] for t in native_turns})
        metric["native_speaker_count_error"] = abs(metric["native_speaker_count"] - metric["speakers"]["reference"])
        case_dir = output / case["id"]
        write_json(case_dir / "hypothesis.json", hypothesis)
        write_json(case_dir / "diagnostics.json", actual["diagnostics"])
        write_json(case_dir / "metrics.json", metric)
        language = actual["diagnostics"].get("language", {})
        record = {"id": case["id"], "split": case.get("split", "all"), "kind": case.get("kind", "unspecified"),
                  "audio_sha256": audio_hash, "reference_sha256": reference_hash,
                  "duration_ms": actual["duration_ms"], "processing_ms": actual["processing_ms"],
                  "runner_wall_ms": round((time.perf_counter() - started) * 1000), "metrics": metric,
                  "decidedLanguage": language.get("decided", args.language),
                  "languageIdMs": actual["diagnostics"]["stagesMs"].get("languageIdMs"),
                  "backend": actual["diagnostics"]["backend"],
                  "wordAssignmentSupported": actual["diagnostics"]["wordAssignmentSupported"]}
        write_json(case_dir / "case.json", record)
        records.append(record)
        print(json.dumps({"case": case["id"], "language": record["decidedLanguage"],
                          "wer_raw": metric["wer_raw"]["rate"], "wer_normalized": metric["wer_normalized"]["rate"],
                          "speakers": metric["speakers"], "rtf": metric["rtf"]}, ensure_ascii=False), flush=True)
    meta.update(completed_at=datetime.now(timezone.utc).isoformat())
    write_json(output / "run.json", meta)
    summarize(output)


if __name__ == "__main__":
    main()
