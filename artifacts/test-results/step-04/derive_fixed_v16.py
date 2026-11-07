"""Reproduce the production fixed-mode SD comparison from actual saved fixed runs.

Only K=1 uses the original full-duration V1.6 bypass. Other turns are immutable
actual ERes fixed inference; D ASR is replayed for comparable word projection.
This is a computed stage-quality comparison, not another whole-model run.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.eval import pipeline as base
from tools.eval.diar_sweep import load_asr, summarize
from tools.eval.refine_sweep import _checked_record, _score_turns, _turns
from tools.eval.run import confined, digest, evidence_hashes, write_json


def main():
    here = Path(__file__).resolve().parent
    source = here / "fixed-eres2net-zh-v2"
    asr = here.parent / "step-03/context600-selected-host"
    manifest_file = ROOT / "benchmark/eval/manifest.json"
    manifest = json.loads(manifest_file.read_text())
    out = here / "fixed-v16-production-comparison"
    out.mkdir(exist_ok=False)
    records = []
    for case in manifest["files"]:
        if case["split"] != "dev":
            continue
        reference_file = confined(manifest_file.parent, case["reference"])
        reference_hash = digest(reference_file)
        folder = source / "fixed" / case["id"]
        old, source_hashes = _checked_record(folder, case, reference_hash, profile="fixed")
        diagnostic = json.loads((folder / "diagnostics.json").read_text())
        duration = case["duration_ms"]
        single = case["expected_speakers"] == 1
        turns = [base.Turn(0, duration, 0)] if single else _turns(diagnostic["diarizationTurns"], duration)
        chunks, asr_record, backend = load_asr(asr / case["id"], case, reference_hash)
        reference = json.loads(reference_file.read_text())
        hypothesis, metrics = _score_turns(turns, reference, chunks, backend, duration, asr_record["metrics"]["wer_raw"])
        n, gold = metrics["native_speaker_count"], metrics["speakers"]["reference"]
        target = out / case["id"]
        for name, value in (("reference", reference), ("hypothesis", hypothesis), ("metrics", metrics),
                ("diagnostics", {"diarizationTurns": base._turn_json(turns), "singleBypass": single,
                    "source_fixed_evidence_sha256": source_hashes, "source_asr_evidence_sha256": asr_record["evidence_sha256"],
                    "scope": "Computed fixed V1.6 SD stage quality; known K, saved actual nonmono SD, saved D ASR, no new inference"})):
            write_json(target / (name + ".json"), value)
        record = {"id": case["id"], "split": "dev", "duration_ms": duration,
            "native_speaker_count": n, "reference_speaker_count": gold, "native_speaker_count_error": abs(n-gold),
            "audio_sha256": case["audio_sha256"], "reference_sha256": reference_hash, "metrics": metrics,
            "diarization_inference_ms": 0, "new_diarization_inference": False, "new_asr_inference": False,
            "evidence_sha256": evidence_hashes(target)}
        write_json(target / "case.json", record)
        records.append(record)
    summary = summarize(records)
    summary.pop("rtf_diarization_stage")
    summary.pop("diarization_inference_ms")
    summary["timing_scope"] = "No new inference; quality only; not RTF"
    write_json(out / "summary.json", summary)
    write_json(out / "run.json", {"status": "COMPLETE", "manifest_sha256": digest(manifest_file),
        "derivation_code_sha256": digest(__file__), "source_run_sha256": digest(source / "run.json"),
        "asr_run_sha256": digest(asr / "run.json"), "new_model_inference": False})
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
