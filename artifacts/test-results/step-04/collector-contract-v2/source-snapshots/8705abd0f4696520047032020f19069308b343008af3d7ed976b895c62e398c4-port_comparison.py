"""Paired corpus WER gate clarified by the user; preserve every per-file diagnostic."""


def summarize(cases, threshold_pp=.5):
    if not cases:
        raise ValueError("A paired comparison requires cases")
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Duplicate paired case IDs")
    for case in cases:
        for key in ("reference_words", "host_errors", "native_errors"):
            if type(case[key]) is not int or case[key] < 0:
                raise ValueError("Counts must be nonnegative integers")
    words = sum(case["reference_words"] for case in cases)
    host_errors = sum(case["host_errors"] for case in cases)
    native_errors = sum(case["native_errors"] for case in cases)
    delta = 100 * (native_errors-host_errors) / words if words else None
    diagnostics = []
    for case in cases:
        difference = 100*(case["native_errors"]-case["host_errors"])/case["reference_words"] if case["reference_words"] else None
        diagnostics.append({**case, "wer_delta_percentage_points": difference,
                            "per_file_within_threshold": abs(difference)<=threshold_pp if difference is not None else None})
    return {"scope": "Fixed paired corpus, total errors / total reference words; per-file differences retained",
            "reference_words": words, "host_errors": host_errors, "native_errors": native_errors,
            "host_wer_raw": host_errors/words if words else None,
            "native_wer_raw": native_errors/words if words else None,
            "wer_delta_percentage_points": delta, "threshold_percentage_points": threshold_pp,
            "gate_pass": abs(delta)<=threshold_pp if delta is not None else False,
            "per_file_diagnostics": diagnostics}
