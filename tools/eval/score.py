#!/usr/bin/env python3
"""Score independent reference and hypothesis transcripts without model inference.

Primary WER preserves case, punctuation, ё and numeric spelling. All rates are
fractions; undefined denominators are JSON null. See SCORING.md for protocols.
The scorer itself uses the Python standard library. num2words is optional.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import importlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
import unicodedata
from typing import Callable, Mapping, Sequence

ROW_KEYS = {"speaker_id", "start_ms", "end_ms", "text"}
PUNCTUATION = (".", ",", "?", "!", "—", ":")
LEXICAL_PATTERN = re.compile(r"[^\W_]+|[.,?!—:]", re.UNICODE)


@dataclass(frozen=True)
class Row:
    speaker_id: str
    start_ms: int
    end_ms: int
    text: str


def _duration(value: int) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("duration_ms must be a positive integer")
    return value


def _rows(rows: Sequence[Mapping], duration_ms: int) -> list[Row]:
    if not isinstance(rows, (list, tuple)):
        raise ValueError("transcript must be an array")
    result = []
    for index, item in enumerate(rows):
        if not isinstance(item, Mapping) or set(item) != ROW_KEYS:
            raise ValueError(f"transcript[{index}] must have exactly {sorted(ROW_KEYS)}")
        speaker, start, end, text = (item[k] for k in ("speaker_id", "start_ms", "end_ms", "text"))
        if not isinstance(speaker, str) or not speaker.strip():
            raise ValueError(f"transcript[{index}].speaker_id must be a nonempty string")
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= duration_ms:
            raise ValueError(f"transcript[{index}] times must be integers within [0, duration_ms]")
        if not isinstance(text, str):
            raise ValueError(f"transcript[{index}].text must be a string")
        result.append(Row(speaker, start, end, text))
    return sorted(result, key=lambda row: (row.start_ms, row.end_ms))


def _document(document: Mapping, duration_ms: int) -> list[Row]:
    if not isinstance(document, Mapping) or set(document) != {"transcript"}:
        raise ValueError("document must contain exactly one root field: transcript")
    return _rows(document["transcript"], duration_ms)


def normalized_tokens(text: str) -> list[str]:
    """Match domain/Benchmark.kt: lowercase, NFC, ё→е, letters/numbers only."""
    text = unicodedata.normalize("NFC", text.lower().replace("ё", "е"))
    return "".join(char if unicodedata.category(char)[0] in {"L", "N"} else " " for char in text).split()


def punctuation_tokens(text: str) -> list[str]:
    """Keep exact word spelling; separate each punctuation/symbol codepoint."""
    result, word = [], []
    for char in text:
        if char.isalnum() or char == "_" or unicodedata.category(char).startswith("M"):
            word.append(char)
        else:
            if word:
                result.append("".join(word))
                word.clear()
            if not char.isspace():
                result.append(char)
    if word:
        result.append("".join(word))
    return result


def _text(rows: Sequence[Row]) -> str:
    return "\n".join(row.text for row in rows)


def _edit(reference: Sequence, hypothesis: Sequence) -> tuple[dict, list[tuple[int | None, int | None, str]]]:
    """Unit-cost Levenshtein, deterministic diagonal/deletion/insertion ties.

    Costs use two rolling rows; one byte per DP cell stores backtrace decisions.
    This avoids a quadratic matrix of Python integer/tuple objects.
    """
    n, m = len(reference), len(hypothesis)
    width = m + 1
    trace = bytearray((n + 1) * width)
    trace[1:width] = bytes([3]) * m
    previous = list(range(width))
    for i, ref in enumerate(reference, 1):
        current = [i] + [0] * m
        trace[i * width] = 2
        for j, hyp in enumerate(hypothesis, 1):
            same = ref == hyp
            diagonal = previous[j - 1] + (not same)
            deletion, insertion = previous[j] + 1, current[j - 1] + 1
            cost = min(diagonal, deletion, insertion)
            current[j] = cost
            trace[i * width + j] = (0 if same else 1) if cost == diagonal else (2 if cost == deletion else 3)
        previous = current
    operations = []
    correct = substitutions = deletions = insertions = 0
    i, j = n, m
    while i or j:
        operation = trace[i * width + j]
        if operation in (0, 1):
            i -= 1
            j -= 1
            name = "equal" if operation == 0 else "substitution"
            correct += operation == 0
            substitutions += operation == 1
            operations.append((i, j, name))
        elif operation == 2:
            i -= 1
            deletions += 1
            operations.append((i, None, "deletion"))
        else:
            j -= 1
            insertions += 1
            operations.append((None, j, "insertion"))
    operations.reverse()
    errors = substitutions + deletions + insertions
    return {
        "rate": errors / n if n else None,
        "errors": errors,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "correct": correct,
        "reference_tokens": n,
        "hypothesis_tokens": m,
        "status": "ok" if n else "no_reference_tokens",
    }, operations


def _distance(reference: Sequence, hypothesis: Sequence) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, 1):
        current = [i]
        for j, hyp in enumerate(hypothesis, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ref != hyp)))
        previous = current
    return previous[-1]


def _assignment(costs: Sequence[Sequence[float]]) -> list[int]:
    """Exact square Hungarian minimum assignment, deterministic index ties."""
    n = len(costs)
    if not n:
        return []
    if any(len(row) != n for row in costs):
        raise ValueError("assignment costs must be square")
    u, v = [0.0] * (n + 1), [0.0] * (n + 1)
    p, way = [0] * (n + 1), [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minimum, used = [math.inf] * (n + 1), [False] * (n + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], math.inf, 0
            for j in range(1, n + 1):
                if not used[j]:
                    current = costs[i0 - 1][j - 1] - u[i0] - v[j]
                    if current < minimum[j]:
                        minimum[j], way[j] = current, j0
                    if minimum[j] < delta:
                        delta, j1 = minimum[j], j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    result = [0] * n
    for j in range(1, n + 1):
        result[p[j] - 1] = j - 1
    return result


def der(reference_rows: Sequence[Mapping], hypothesis_rows: Sequence[Mapping], duration_ms: int, collar_ms: float = 0) -> dict:
    """DER with optimal label permutation, overlap, full-file UEM and collars.

    Timed blank-text rows count. speaker_id is an opaque, nonempty string.
    pyannote convention: collar_ms is TOTAL width; 250 means ±125 ms around
    every positive-duration reference segment boundary, excluded on both sides.
    """
    duration_ms = _duration(duration_ms)
    if isinstance(collar_ms, bool) or not isinstance(collar_ms, (int, float)) or not math.isfinite(collar_ms) or collar_ms < 0:
        raise ValueError("collar_ms must be finite and nonnegative")
    reference = [row for row in _rows(reference_rows, duration_ms) if row.end_ms > row.start_ms]
    hypothesis = [row for row in _rows(hypothesis_rows, duration_ms) if row.end_ms > row.start_ms]
    ref_ids = list(dict.fromkeys(row.speaker_id for row in reference))
    hyp_ids = list(dict.fromkeys(row.speaker_id for row in hypothesis))
    ref_index, hyp_index = {s: i for i, s in enumerate(ref_ids)}, {s: i for i, s in enumerate(hyp_ids)}
    events = defaultdict(list)
    events[0]
    events[duration_ms]
    for side, rows in enumerate((reference, hypothesis)):
        for row in rows:
            events[row.start_ms].append((side, row.speaker_id, 1))
            events[row.end_ms].append((side, row.speaker_id, -1))
    if collar_ms:
        half = collar_ms / 2
        for row in reference:
            for boundary in (row.start_ms, row.end_ms):
                a, b = max(0, boundary - half), min(duration_ms, boundary + half)
                if b > a:
                    events[a].append((2, "collar", 1))
                    events[b].append((2, "collar", -1))
    points = sorted(events)
    active = [Counter(), Counter(), Counter()]
    frames = []
    n = max(len(ref_ids), len(hyp_ids))
    weights = [[0.0] * n for _ in range(n)]
    evaluated = overlap_ms = 0.0
    for position, next_position in zip(points, points[1:]):
        for side, speaker, delta in events[position]:
            active[side][speaker] += delta
            if not active[side][speaker]:
                del active[side][speaker]
        if active[2]:
            continue
        milliseconds = next_position - position
        ref, hyp = set(active[0]), set(active[1])
        frames.append((milliseconds, ref, hyp))
        evaluated += milliseconds
        if len(ref) > 1:
            overlap_ms += milliseconds
        for r in ref:
            for h in hyp:
                weights[ref_index[r]][hyp_index[h]] += milliseconds
    assignment = _assignment([[-weight for weight in row] for row in weights])
    mapping = {
        hyp_ids[j]: ref_ids[i]
        for i, j in enumerate(assignment)
        if i < len(ref_ids) and j < len(hyp_ids) and weights[i][j] > 0
    }
    miss = false_alarm = confusion = reference_speaker_ms = 0.0
    for milliseconds, ref, hyp in frames:
        correct = sum(mapping.get(h) in ref for h in hyp)
        miss += max(0, len(ref) - len(hyp)) * milliseconds
        false_alarm += max(0, len(hyp) - len(ref)) * milliseconds
        confusion += (min(len(ref), len(hyp)) - correct) * milliseconds
        reference_speaker_ms += len(ref) * milliseconds
    errors = miss + false_alarm + confusion
    return {
        "rate": errors / reference_speaker_ms if reference_speaker_ms else None,
        "miss_ms": miss,
        "false_alarm_ms": false_alarm,
        "confusion_ms": confusion,
        "error_speaker_ms": errors,
        "reference_speaker_ms": reference_speaker_ms,
        "evaluated_duration_ms": evaluated,
        "excluded_duration_ms": duration_ms - evaluated,
        "reference_overlap_ms": overlap_ms,
        "collar_ms": collar_ms,
        "collar_half_width_ms": collar_ms / 2,
        "mapping_hypothesis_to_reference": mapping,
        "status": "ok" if reference_speaker_ms else "no_reference_speaker_time",
    }


def _lexical_units(rows: Sequence[Row]) -> tuple[list[str], list[str], Counter, list[int]]:
    words, originals, punctuation, initials = [], [], Counter(), []
    for row in rows:
        initial = None
        for match in LEXICAL_PATTERN.finditer(unicodedata.normalize("NFC", row.text)):
            token = match.group()
            if token in PUNCTUATION:
                punctuation[len(words) - 1, token] += 1
            else:
                words.append(token.lower().replace("ё", "е"))
                originals.append(token)
                if initial is None and _initial_case(token) is not None:
                    initial = len(words) - 1
        if initial is not None:
            initials.append(initial)
    return words, originals, punctuation, initials


def _initial_case(word: str) -> bool | None:
    for char in word:
        if char.isupper() or char.istitle():
            return True
        if char.islower():
            return False
    return None


def _punctuation_and_case(reference: Sequence[Row], hypothesis: Sequence[Row]) -> tuple[dict, dict]:
    ref, ref_original, ref_punct, ref_initials = _lexical_units(reference)
    hyp, hyp_original, hyp_punct, _ = _lexical_units(hypothesis)
    _, operations = _edit(ref, hyp)
    matched = {r: h for r, h, operation in operations if operation == "equal"}
    def statistics_for_mark(mark: str | None = None) -> dict:
        ref_count = sum(count for (_, p), count in ref_punct.items() if mark is None or p == mark)
        hyp_count = sum(count for (_, p), count in hyp_punct.items() if mark is None or p == mark)
        tp = 0
        for (anchor, p), count in ref_punct.items():
            if mark is not None and p != mark:
                continue
            hyp_anchor = -1 if anchor == -1 else matched.get(anchor)
            if hyp_anchor is not None:
                tp += min(count, hyp_punct[hyp_anchor, p])
        return {
            "true_positive": tp, "false_positive": hyp_count - tp, "false_negative": ref_count - tp,
            "reference_marks": ref_count, "hypothesis_marks": hyp_count,
            "precision": tp / hyp_count if hyp_count else None,
            "recall": tp / ref_count if ref_count else None,
            "f1": 2 * tp / (ref_count + hyp_count) if ref_count + hyp_count else None,
        }
    punctuation = statistics_for_mark()
    punctuation.update({"marks": list(PUNCTUATION), "by_mark": {mark: statistics_for_mark(mark) for mark in PUNCTUATION},
                        "aligned_lexical_words": len(matched), "reference_lexical_words": len(ref),
                        "hypothesis_lexical_words": len(hyp)})
    eligible = correct = 0
    for position in ref_initials:
        other = matched.get(position)
        if other is not None:
            eligible += 1
            correct += _initial_case(ref_original[position]) == _initial_case(hyp_original[other])
    initial_case = {
        "accuracy": correct / len(ref_initials) if ref_initials else None,
        "conditional_accuracy": correct / eligible if eligible else None,
        "correct": correct, "reference_initials": len(ref_initials), "aligned_reference_initials": eligible,
        "unmatched_reference_initials": len(ref_initials) - eligible,
    }
    return punctuation, initial_case


def _cpwer(reference: Sequence[Row], hypothesis: Sequence[Row], tokenizer: Callable[[str], list[str]]) -> dict:
    def concatenate(rows: Sequence[Row]) -> dict[str, list[str]]:
        groups = {}
        for row in rows:
            tokens = tokenizer(row.text)
            if tokens:
                groups.setdefault(row.speaker_id, []).extend(tokens)
        return groups
    ref, hyp = concatenate(reference), concatenate(hypothesis)
    ref_ids, hyp_ids = list(ref), list(hyp)
    n = max(len(ref_ids), len(hyp_ids))
    refs = [ref[label] for label in ref_ids] + [[] for _ in range(n - len(ref_ids))]
    hyps = [hyp[label] for label in hyp_ids] + [[] for _ in range(n - len(hyp_ids))]
    costs = [[_distance(a, b) for b in hyps] for a in refs]
    assignment = _assignment(costs)
    totals = Counter()
    pairs = []
    for i, j in enumerate(assignment):
        pair, _ = _edit(refs[i], hyps[j])
        for name in ("errors", "substitutions", "deletions", "insertions", "correct", "reference_tokens", "hypothesis_tokens"):
            totals[name] += pair[name]
        pairs.append({"reference_speaker": ref_ids[i] if i < len(ref_ids) else None,
                      "hypothesis_speaker": hyp_ids[j] if j < len(hyp_ids) else None,
                      "errors": pair["errors"], "reference_tokens": len(refs[i]), "hypothesis_tokens": len(hyps[j])})
    result = {name: totals[name] for name in ("errors", "substitutions", "deletions", "insertions", "correct", "reference_tokens", "hypothesis_tokens")}
    result.update({"rate": totals["errors"] / totals["reference_tokens"] if totals["reference_tokens"] else None,
                   "status": "ok" if totals["reference_tokens"] else "no_reference_tokens", "speaker_pairs": pairs})
    return result


def _timing(reference: Sequence[Row], hypothesis: Sequence[Row]) -> dict:
    ref = [(index, row) for index, row in enumerate(reference) if row.end_ms > row.start_ms]
    hyp = [(index, row) for index, row in enumerate(hypothesis) if row.end_ms > row.start_ms]
    n = max(len(ref), len(hyp))
    ious = [[0.0] * n for _ in range(n)]
    for i, (_, a) in enumerate(ref):
        for j, (_, b) in enumerate(hyp):
            intersection = max(0, min(a.end_ms, b.end_ms) - max(a.start_ms, b.start_ms))
            union = max(a.end_ms, b.end_ms) - min(a.start_ms, b.start_ms)
            ious[i][j] = intersection / union if intersection else 0
    assignment = _assignment([[-iou for iou in row] for row in ious])
    pairs = []
    for i, j in enumerate(assignment):
        if i >= len(ref) or j >= len(hyp) or not ious[i][j]:
            continue
        ref_index, a = ref[i]
        hyp_index, b = hyp[j]
        pairs.append({"reference_index": ref_index, "hypothesis_index": hyp_index, "iou": ious[i][j],
                      "start_abs_error_ms": abs(a.start_ms - b.start_ms), "end_abs_error_ms": abs(a.end_ms - b.end_ms)})
    start_errors = [pair["start_abs_error_ms"] for pair in pairs]
    end_errors = [pair["end_abs_error_ms"] for pair in pairs]
    over = sum(max(pair["start_abs_error_ms"], pair["end_abs_error_ms"]) > 250 for pair in pairs)
    matched = len(pairs)
    return {
        "matched_pairs": matched, "reference_intervals": len(ref), "hypothesis_intervals": len(hyp),
        "reference_coverage": matched / len(ref) if ref else None,
        "hypothesis_coverage": matched / len(hyp) if hyp else None,
        "unmatched_reference": len(ref) - matched, "unmatched_hypothesis": len(hyp) - matched,
        "mean_start_abs_error_ms": statistics.mean(start_errors) if pairs else None,
        "mean_end_abs_error_ms": statistics.mean(end_errors) if pairs else None,
        "median_start_abs_error_ms": statistics.median(start_errors) if pairs else None,
        "median_end_abs_error_ms": statistics.median(end_errors) if pairs else None,
        "pairs_over_250ms": over, "fraction_over_250ms": over / matched if matched else None,
        "reference_fraction_over_250ms_or_unmatched": (over + len(ref) - matched) / len(ref) if ref else None,
        "pairs": pairs,
    }


def _number_metric(reference: str, hypothesis: str) -> dict:
    try:
        num2words = importlib.import_module("num2words").num2words
    except ImportError:
        return {"available": False, "rate": None, "reason": "optional num2words dependency is not installed; numeric forms are not guessed"}
    language = "ru" if re.search("[А-Яа-яЁё]", reference + hypothesis) else "en"
    counts = []
    def tokens(text: str) -> list[str]:
        output, count = [], 0
        for token in normalized_tokens(text):
            if re.fullmatch("[0-9]+", token):
                try:
                    output.extend(normalized_tokens(num2words(int(token), lang=language)))
                    count += 1
                except (NotImplementedError, OverflowError, ValueError):
                    # A partially normalized sequence must not be presented as complete.
                    raise ValueError("num2words could not verbalize all numeric tokens")
            else:
                output.append(token)
        counts.append(count)
        return output
    try:
        result, _ = _edit(tokens(reference), tokens(hypothesis))
    except ValueError as error:
        return {"available": False, "rate": None, "reason": str(error)}
    result.update({"available": True, "language": language, "reference_integer_tokens_converted": counts[0],
                   "hypothesis_integer_tokens_converted": counts[1],
                   "scope": "cardinal integers after lexical normalization; dates/times/percent/ordinals are not semantically interpreted"})
    return result


def score(reference: Mapping, hypothesis: Mapping, duration_ms: int, processing_ms: float | None = None) -> dict:
    """Score strict Jury JSON documents; no reference text is used for inference."""
    duration_ms = _duration(duration_ms)
    if processing_ms is not None and (isinstance(processing_ms, bool) or not isinstance(processing_ms, (int, float)) or not math.isfinite(processing_ms) or processing_ms < 0):
        raise ValueError("processing_ms must be finite and nonnegative, or None")
    ref, hyp = _document(reference, duration_ms), _document(hypothesis, duration_ms)
    ref_text, hyp_text = _text(ref), _text(hyp)
    raw, _ = _edit(ref_text.split(), hyp_text.split())
    separated, _ = _edit(punctuation_tokens(ref_text), punctuation_tokens(hyp_text))
    normalized, _ = _edit(normalized_tokens(ref_text), normalized_tokens(hyp_text))
    characters, _ = _edit(list("".join(normalized_tokens(ref_text))), list("".join(normalized_tokens(hyp_text))))
    punctuation, initial_case = _punctuation_and_case(ref, hyp)
    ref_speakers = set(row.speaker_id for row in ref if row.end_ms > row.start_ms)
    hyp_speakers = set(row.speaker_id for row in hyp if row.end_ms > row.start_ms)
    # Public der() also supports raw native turns with blank text and arbitrary string labels.
    ref_rows = [row.__dict__ for row in ref]
    hyp_rows = [row.__dict__ for row in hyp]
    return {
        "schema_version": 1,
        "protocol": {
            "primary_metric": "wer_raw",
            "rate_units": "fraction; null for an undefined denominator",
            "raw_wer": "whitespace tokens; exact case, attached punctuation, ё and numeric spelling; rows ordered by start_ms/end_ms",
            "edit_ties": "diagonal (match/substitution), then deletion, then insertion",
            "normalized": "NFC lowercase, ё→е, non-letter/non-number characters become spaces; CER removes spaces",
            "punctuation": "micro F1 for . , ? ! — : anchored to preceding equal lexical token after normalized alignment; BEGIN anchor before first token; substitutions/insertions do not match anchors",
            "initial_case": "first cased letter of each reference segment, aligned by normalized lexical word; unmatched initials count incorrect; conditional_accuracy excludes unmatched",
            "der": "full recording [0,duration_ms], overlap included, optimal global speaker permutation reoptimized after collar exclusion; collar total width ±half around each reference boundary",
            "cpwer": "minimum sum of Levenshtein costs over speaker-concatenated streams, padded empty streams for unequal counts; raw and normalized",
            "timing": "global one-to-one maximum-total temporal IoU matching of positive-duration segments; only positive-IoU pairs; text/speaker independent; granularity-dependent",
        },
        "inputs": {"reference_segments": len(ref), "hypothesis_segments": len(hyp), "duration_ms": duration_ms,
                   "processing_ms": processing_ms, "reference_blank_text_segments": sum(not row.text.strip() for row in ref),
                   "hypothesis_blank_text_segments": sum(not row.text.strip() for row in hyp),
                   "reference_zero_duration_segments": sum(row.start_ms == row.end_ms for row in ref),
                   "hypothesis_zero_duration_segments": sum(row.start_ms == row.end_ms for row in hyp)},
        "wer_raw": raw, "wer_punctuation_tokens": separated, "wer_normalized": normalized,
        "cer_normalized": characters, "wer_number_normalized": _number_metric(ref_text, hyp_text),
        "punctuation": punctuation, "initial_case": initial_case,
        "der_collar_0ms": der(ref_rows, hyp_rows, duration_ms),
        "der_collar_250ms": der(ref_rows, hyp_rows, duration_ms, collar_ms=250),
        "speakers": {"reference": len(ref_speakers), "hypothesis": len(hyp_speakers),
                     "signed_error": len(hyp_speakers) - len(ref_speakers), "absolute_error": abs(len(hyp_speakers) - len(ref_speakers))},
        "cpwer_raw": _cpwer(ref, hyp, str.split), "cpwer_normalized": _cpwer(ref, hyp, normalized_tokens),
        "timing": _timing(ref, hyp), "rtf": processing_ms / duration_ms if processing_ms is not None else None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--hypothesis", required=True, type=Path)
    parser.add_argument("--duration-ms", required=True, type=int)
    parser.add_argument("--processing-ms", type=float)
    parser.add_argument("--output", type=Path, help="New output path; existing evidence is never overwritten")
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.exists():
            raise ValueError(f"output already exists: {args.output}")
        result = score(json.loads(args.reference.read_text(encoding="utf-8")),
                       json.loads(args.hypothesis.read_text(encoding="utf-8")), args.duration_ms, args.processing_ms)
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8", newline="\n") as output:
                output.write(encoded)
        else:
            print(encoded, end="")
    except (ValueError, OSError, TypeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
