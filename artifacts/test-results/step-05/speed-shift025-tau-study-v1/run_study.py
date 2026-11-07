#!/usr/bin/env python3
"""Frozen dev-only saved-vector tau study; never loads neural models/audio."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
# An accidental future neural import must fail rather than start a new model.
sys.modules["sherpa_onnx"] = None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def source_guard(repo, protocol):
    for group in ("source_sha256", "source_code_sha256"):
        for relative, expected in protocol[group].items():
            if sha(repo/relative) != expected:
                raise ValueError("Frozen study input changed: " + relative)


def gate(summary, protocol):
    selection = protocol["selection"]
    conditions = {
        "complete_dev8": summary["cases"] == 8 and summary["complete_case_coverage"],
        "all_refiners_supported": summary["refiner_accepted_cases"] == 8,
        "native_count_at_least7": summary["speaker_count_exact_cases"] >= 7,
        "native_der_no_regrowth": (summary["native_der_collar_0ms"]["rate"] is not None
            and summary["native_der_collar_0ms"]["rate"] <= selection["maximum_native_der0"] + selection["der_numeric_allowance"]),
        "cpwer_no_regrowth": summary["cpwer_raw"]["errors"] <= 146 and summary["cpwer_raw"]["reference_tokens"] == 533,
        "raw_invariant": summary["raw_wer_invariant"] and summary["wer_raw"]["errors"] == 71 and summary["wer_raw"]["reference_tokens"] == 533,
        "normalized_invariant": summary["wer_normalized"]["errors"] == 16 and summary["wer_normalized"]["reference_tokens"] == 532,
    }
    return {"pass": all(conditions.values()), "conditions": conditions}


def load_inputs(repo, protocol):
    sys.path.insert(0, str(repo))
    from tools.eval import pipeline as base, refine_sweep as saved
    from tools.eval.diar_sweep import load_asr
    from tools.eval.refiner_ablation import _tokens
    from tools.eval.run import evidence_hashes
    from tools.eval.speaker_refiner import clean_windows
    source = repo/protocol["source_diar_run"]
    asr = repo/protocol["source_asr_run"]
    meta, dmeta = read(source/"run.json"), read(asr/"run.json")
    if meta["status"] != "COMPLETE" or dmeta["status"] != "COMPLETE":
        raise ValueError("Completed actual SD and actual D sources required")
    if (meta["profile"] != {"id": "shift-0p25", "window_shift": .25, "min_duration_off": .5, "inference": True}
            or meta.get("new_diarization_inference") is not True or meta.get("new_embedding_inference") is not True
            or meta.get("asr_replay") is not True or meta.get("new_asr_inference") is not False
            or meta["fingerprint"]["asr_run_sha256"] != sha(asr/"run.json")):
        raise ValueError("Actual source mode or D provenance differs")
    manifest = repo/protocol["manifest"]
    cases = [case for case in read(manifest)["files"] if case["split"] == "dev"]
    if [c["id"] for c in cases] != protocol["selected_ids"] or len(cases) != 8:
        raise ValueError("Only the exact eight frozen dev cases may be read")
    lock = read(repo/"app/src/main/assets/models-lock.json")["files"]
    model_pins = [(r["path"], r["size"], r["sha256"]) for r in lock]
    if model_pins != [(r["path"], r["bytes"], r["sha256"]) for r in meta["fingerprint"]["models"]]:
        raise ValueError("Actual SD source old7 model pins differ")
    result = []
    for case in cases:
        identifier = case["id"]
        reference = manifest.parent/case["reference"]
        rh = sha(reference)
        record, hashes = saved._checked_record(source/identifier, case, rh, profile="shift-0p25")
        chunks, drecord, backend = load_asr(asr/identifier, case, rh)
        diag = read(source/identifier/"diagnostics.json")
        if (record.get("status") != "COMPLETE" or record.get("asr_replay") is not True
                or record.get("new_asr_inference") is not False
                or any(record.get(k) is not True for k in ("new_diarization_inference", "new_embedding_inference"))
                or diag.get("asrEvidenceSha256") != evidence_hashes(asr/identifier)
                or diag.get("sourceDRunSha256") != sha(asr/"run.json")
                or diag.get("originalPcm") is not True or diag.get("sampleRate") != 16000):
            raise ValueError("Actual per-case NN/source-D evidence differs: " + identifier)
        if diag["modelFiles"] != meta["fingerprint"]["models"] or diag["sdkConfig"] != meta["sdk_config"]:
            raise ValueError("Actual case model/SDK policy differs")
        sdk = diag["sdkConfig"]
        if sdk["float32_bits"] != {"native_threshold":"3e99999a","window_shift":"3e800000","min_duration_on":"3e4ccccd","min_duration_off":"3f000000"} or sdk["threads"] != 2 or sdk["num_clusters"] != -1:
            raise ValueError("Expected recorded actual shift.25 native policy")
        turns = saved._turns(diag["nativeDiarizationTurns"], case["duration_ms"])
        raw = saved._turns(diag["rawDiarizationTurns"], case["duration_ms"])
        if base.stable_turns(raw) != turns:
            raise ValueError("Actual native stable turn mapping differs")
        windows = saved._windows(diag["cleanEmbeddingWindows"])
        expected = [(w.start_ms,w.end_ms,w.speaker) for w in clean_windows(turns,case["duration_ms"])]
        actual = [(w.start_ms,w.end_ms,w.speaker) for w in windows]
        if actual != expected or len(set(actual)) != len(actual) or not windows:
            raise ValueError("Real clean window planner coverage differs")
        if any(len(w.embedding)!=512 or not all(math.isfinite(x) for x in w.embedding) or math.hypot(*w.embedding)<=1e-12 for w in windows):
            raise ValueError("Actual finite 512-dimensional measured vectors required")
        counts = diag["counts"]
        for key, value in {"sdLoads":1,"sdProcessCalls":1,"sdReleased":True,"extractorLoads":1,
            "extractorReleased":True,"nativeResourcesReleased":True,"embeddingDimension":512,
            **{key:len(windows) for key in ("plannedWindows","measuredWindows","createdStreams","releasedStreams","computeAttempts","embeddingForwardCalls")}}.items():
            if type(counts.get(key)) is not type(value) or counts[key] != value:
                raise ValueError("Actual source inference lifecycle differs: "+key)
        result.append(SimpleNamespace(case_id=identifier,split="dev",duration_ms=case["duration_ms"],
            audio_sha256=case["audio_sha256"],reference_path=reference,reference_sha256=rh,
            turns=tuple(turns),windows=tuple(windows),chunks=tuple(chunks),backend=backend,
            expected_raw=drecord["metrics"]["wer_raw"],source_tokens=_tokens(read(asr/identifier/"hypothesis.json")),
            source_hashes={"actual_sd":hashes,"actual_d":{"case.json":sha(asr/identifier/"case.json"),**evidence_hashes(asr/identifier)}}))
    return result


def run(repo, directory):
    protocol_path = directory/"protocol.json"
    protocol = read(protocol_path)
    if protocol["thresholds"] != [x/100 for x in range(25,46)] or protocol["split"] != "dev":
        raise ValueError("Frozen 21-tau dev-only protocol required")
    source_guard(repo, protocol)
    inputs = load_inputs(repo, protocol)
    from tools.eval import pipeline as base
    from tools.eval.refiner_ablation import score_projection
    from tools.eval.run import evidence_hashes
    from tools.eval.window_overcluster import WindowClusterConfig, overcluster
    from tools.eval.refine_sweep import _summarize
    import scipy
    output = directory/"outputs"
    if output.exists():
        raise FileExistsError("Preserve all existing outputs; no overwrite")
    freeze = {"frozen_utc":datetime.now(timezone.utc).isoformat(),"procedure_sha256":sha(__file__),
        "protocol_sha256":sha(protocol_path),"source_guard_pass":True,"complete_dev8":True,
        "real_vector_count":sum(len(c.windows) for c in inputs),"embedding_dimensions":[512],
        "new_neural_inference":False,"scipy":scipy.__version__}
    write(directory/"execution-freeze.json",freeze)
    output.mkdir()
    records, summaries, cache, failures = [], [], {}, []
    try:
        for tau in protocol["thresholds"]:
            config = WindowClusterConfig(**{**protocol["base_window_config"],"tau":tau})
            local = []
            for case in inputs:
                began = time.perf_counter()
                # This is the entire clustering boundary. No text, gold, K or ID.
                result = overcluster(case.turns,case.windows,case.duration_ms,config)
                elapsed = (time.perf_counter()-began)*1000
                hypothesis, metrics = score_projection(case,result.turns,cache)
                count, truth = metrics["native_speaker_count"],metrics["speakers"]["reference"]
                folder = output/("tau-"+format(tau,".2f").replace(".","p"))/case.case_id
                diagnostics = {"algorithm":"window-overcluster-v1","refiner":result.diagnostics,
                    "refinerAccepted":result.accepted,"diarizationTurns":base._turn_json(result.turns),
                    "sourceEvidence":case.source_hashes,"newDiarizationInference":False,
                    "newEmbeddingInference":False,"newAsrInference":False,"asrReplay":True,
                    "refinerOnlyMs":elapsed,"timingScope":"Pure cached-vector clustering; no NN/speed or whole RTF"}
                folder.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(case.reference_path,folder/"reference.json")
                for name,value in (("hypothesis",hypothesis),("metrics",metrics),("diagnostics",diagnostics)):
                    write(folder/(name+".json"),value)
                record = {"id":case.case_id,"split":"dev","tau":tau,"config":asdict(config),
                    "audio_sha256":case.audio_sha256,"reference_sha256":case.reference_sha256,
                    "duration_ms":case.duration_ms,"metrics":metrics,"native_speaker_count":count,
                    "reference_speaker_count":truth,"native_speaker_count_error":abs(count-truth),
                    "raw_wer_invariant":True,"refiner_accepted":result.accepted,"refiner_only_ms":elapsed,
                    "diarization_inference_ms":0,"new_diarization_inference":False,
                    "new_embedding_inference":False,"new_asr_inference":False,"asr_replay":True,
                    "source_evidence_sha256":case.source_hashes,"evidence_sha256":evidence_hashes(folder)}
                write(folder/"case.json",record)
                records.append(record);local.append(record)
            summary = _summarize(local,8)
            summary.update(new_embedding_inference=False,rtf=None)
            summary.update(tau=tau,gate=gate(summary,protocol))
            summaries.append(summary)
            print(json.dumps({"tau":tau,"exact":summary["speaker_count_exact_cases"],"der":summary["native_der_collar_0ms"]["rate"],"cp_errors":summary["cpwer_raw"]["errors"],"pass":summary["gate"]["pass"]}),flush=True)
        source_guard(repo,protocol)
        if sha(__file__) != freeze["procedure_sha256"] or sha(protocol_path) != freeze["protocol_sha256"]:
            raise ValueError("Procedure/protocol changed during pure study")
    except BaseException as error:
        failures.append({"tau":locals().get("tau"),"id":getattr(locals().get("case"),"case_id",None),"error":repr(error)})
        raise
    finally:
        write(directory/"failures.json",failures)
        write(directory/"summaries.json",{"status":"FAILED" if failures else "COMPLETE","profiles":summaries})
        with (directory/"results.csv").open("x",newline="") as stream:
            fields=["tau","id","native_speakers","reference_speakers","native_der0","native_der250","cpwer_errors","raw_errors","normalized_errors","raw_invariant","refiner_accepted","refiner_only_ms","new_neural_inference"]
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            for row in records:
                m=row["metrics"]
                writer.writerow({"tau":row["tau"],"id":row["id"],"native_speakers":row["native_speaker_count"],"reference_speakers":row["reference_speaker_count"],"native_der0":m["native_der_collar_0ms"]["rate"],"native_der250":m["native_der_collar_250ms"]["rate"],"cpwer_errors":m["cpwer_raw"]["errors"],"raw_errors":m["wer_raw"]["errors"],"normalized_errors":m["wer_normalized"]["errors"],"raw_invariant":True,"refiner_accepted":row["refiner_accepted"],"refiner_only_ms":row["refiner_only_ms"],"new_neural_inference":False})
    passing=[s for s in summaries if s["gate"]["pass"]]
    best=min(passing,key=lambda s:(s["native_der_collar_0ms"]["rate"],s["cpwer_raw"]["errors"],s["tau"])) if passing else None
    write(directory/"selection.json",{"status":"COMPLETE","passing_profiles":len(passing),"selected_tau":best["tau"] if best else None,
        "decision":"Research candidate only; requires future fresh holdout/speed validation" if best else "Reject all; retain frozen C2",
        "promoted":False,"new_neural_inference":False,"holdout_reserve_natural_used":False,"performance_claim":False,
        "selected_summary":best,"complete_case_outputs":len(records),"protocol_sha256":freeze["protocol_sha256"],"procedure_sha256":freeze["procedure_sha256"]})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",type=Path,default=Path(__file__).resolve().parents[4])
    args=parser.parse_args()
    run(args.repo.resolve(),Path(__file__).resolve().parent)
