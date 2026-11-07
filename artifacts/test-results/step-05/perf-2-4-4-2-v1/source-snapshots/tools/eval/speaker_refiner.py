"""Measured-embedding speaker refinement; no audio inference or reference input.

``clean_windows`` plans 1500 ms windows every 750 ms inside exclusive native
speaker activity. A whole 1000..1499 ms island is usable without padding.
``refine`` accepts embeddings measured on those exact windows. Each vector is
L2-normalized, then the duration-weighted mean is normalized again. Zero,
nonfinite, inconsistent-dimensional and non-clean observations are rejected.
Missing cluster centroids stay explicitly marked and outside acoustic math.

The first merge stage repeatedly chooses the largest centroid cosine > tau.
An optional complete-link guard requires every original-centroid pair to pass
tau too. Eigengap uses Aij=max(0,(cos(i,j)-tau)/(1-tau)), Aii=0, and the symmetric
normalized Laplacian L=I-D^-1/2 A D^-1/2 (isolated rows/diagonal are zero).
Among ascending eigenvalues the largest gap lambda[k]-lambda[k-1] estimates
K<=8; ties prefer larger K, and flat spectra retain min(N,8). This is an explicit
thresholded-centroid heuristic, not a claim to implement NME-SC. Weak ubiquitous
cosines alone cannot establish K=1. Spectral reduction never splits a cluster;
it requires a positive nearest-centroid cosine. A hard >8 cap may force lower
similarity merges, which are separately reported. Eigensystems are only N by N
for native cluster centroids, never for all embedding windows; N>256 is rejected.

Small means union duration < max(2000 ms, .03 * recording duration). Such groups
are assigned to their nearest non-small measured centroid; all-small input uses
the longest group as an explicit deterministic anchor. Optional minimum cosine
is a separate experimental guard; its default None follows the plan literally.
Missing small centroids default to retain; an explicit temporal profile may use
nearest established interval midpoint (tie: earlier interval, then label order).
This fallback is never described as acoustic speaker identification. The hard
cap runs after small reassignments and counts missing-centroid labels too; an
unachievable cap returns unsupported, unchanged valid native turns.
Finally, an insertion <500 ms touching identical neighbors may be relabeled;
overlapping insertions and gaps are never smoothed. All endpoints/activity come
from native turns. Cosine ties use original first appearance, then source label.

RefineResult.accepted means the computation had sufficient valid evidence. It
does NOT mean dev/holdout quality, speaker identity or release acceptance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from numbers import Real
from typing import Iterable

from tools.eval.pipeline import Turn


@dataclass(frozen=True)
class EmbeddingWindow:
    start_ms: int
    end_ms: int
    speaker: int
    embedding: tuple[float, ...] = ()
    clean: bool = True


@dataclass(frozen=True)
class RefineConfig:
    merge_threshold: float = .85
    max_speakers: int = 8
    min_cluster_ms: int = 2000
    min_cluster_fraction: float = .03
    smooth_ms: int = 500
    merge_similar: bool = True
    use_eigengap: bool = True
    reassign_small: bool = True
    smooth: bool = True
    complete_link_guard: bool = False
    minimum_reassignment_similarity: float | None = None
    small_missing_centroid_policy: str = "retain"


@dataclass(frozen=True)
class RefineResult:
    turns: tuple[Turn, ...]
    accepted: bool
    diagnostics: dict


def _integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_duration(duration_ms: int) -> None:
    if not _integer(duration_ms) or not 0 <= duration_ms <= (1 << 63) - 1:
        raise ValueError("duration_ms must be a nonnegative signed-64-bit integer")


def _finite_real(value) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _validate_config(config: RefineConfig) -> None:
    if not _finite_real(config.merge_threshold) or not -1 < config.merge_threshold < 1:
        raise ValueError("merge_threshold must be finite and strictly between -1 and 1")
    if not _integer(config.max_speakers) or not 1 <= config.max_speakers <= 8:
        raise ValueError("max_speakers must be an integer in 1..8")
    if not _integer(config.min_cluster_ms) or config.min_cluster_ms < 0:
        raise ValueError("min_cluster_ms must be nonnegative")
    if not _finite_real(config.min_cluster_fraction) or not 0 <= config.min_cluster_fraction <= 1:
        raise ValueError("min_cluster_fraction must be in 0..1")
    if not _integer(config.smooth_ms) or config.smooth_ms < 0:
        raise ValueError("smooth_ms must be nonnegative")
    value = config.minimum_reassignment_similarity
    if value is not None and (not _finite_real(value) or not -1 <= value <= 1):
        raise ValueError("minimum_reassignment_similarity must be in -1..1 or None")
    for name in ("merge_similar", "use_eigengap", "reassign_small", "smooth", "complete_link_guard"):
        if not isinstance(getattr(config, name), bool):
            raise ValueError(name + " must be boolean")
    if config.small_missing_centroid_policy not in ("retain", "temporal"):
        raise ValueError("small_missing_centroid_policy must be retain or temporal")


def _valid_turns(turns: Iterable[Turn], duration_ms: int) -> tuple[list[Turn], int]:
    result, invalid = [], 0
    for turn in turns:
        if (not isinstance(turn, Turn) or not all(_integer(v) for v in
                (turn.start_ms, turn.end_ms, turn.speaker)) or
                not 0 <= turn.start_ms < turn.end_ms <= duration_ms or turn.speaker < -1):
            invalid += 1
        else:
            result.append(turn)
    return sorted(result, key=lambda t: (t.start_ms, t.end_ms, t.speaker)), invalid


def _union(intervals) -> list[tuple[int, int]]:
    result = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def _exclusive(turns: list[Turn], speaker: int) -> list[tuple[int, int]]:
    own = _union((t.start_ms, t.end_ms) for t in turns if t.speaker == speaker)
    other = _union((t.start_ms, t.end_ms) for t in turns if t.speaker != speaker)
    result = []
    for start, end in own:
        cursor = start
        for left, right in other:
            if right <= cursor:
                continue
            if left >= end:
                break
            if left > cursor:
                result.append((cursor, min(left, end)))
            cursor = max(cursor, right)
            if cursor >= end:
                break
        if cursor < end:
            result.append((cursor, end))
    return result


def clean_windows(turns: Iterable[Turn], duration_ms: int, window_ms: int = 1500,
                  step_ms: int = 750, min_clean_ms: int = 1000) -> tuple[EmbeddingWindow, ...]:
    """Metadata only; never pad, fill pauses, or include simultaneous labels.

    Invalid native turns raise instead of providing apparently clean windows.
    Unknown (-1) activity blocks windows of known speakers too.
    """
    _validate_duration(duration_ms)
    if (not all(_integer(v) and v > 0 for v in (window_ms, step_ms, min_clean_ms))
            or min_clean_ms > window_ms):
        raise ValueError("positive window/step/minimum and minimum<=window required")
    native, invalid = _valid_turns(turns, duration_ms)
    if invalid:
        raise ValueError("invalid native turns")
    result = []
    for speaker in sorted({t.speaker for t in native if t.speaker >= 0}):
        for start, end in _exclusive(native, speaker):
            if end - start < min_clean_ms:
                continue
            if end - start < window_ms:
                result.append(EmbeddingWindow(start, end, speaker))
            else:
                while start + window_ms <= end:
                    result.append(EmbeddingWindow(start, start + window_ms, speaker))
                    start += step_ms
    return tuple(sorted(result, key=lambda w: (w.start_ms, w.end_ms, w.speaker)))


def _unit(values) -> tuple[float, ...] | None:
    try:
        vector = tuple(float(x) for x in values if isinstance(x, Real) and not isinstance(x, bool))
        if len(vector) != len(values) or not vector or not all(math.isfinite(x) for x in vector):
            return None
        scale = max(abs(x) for x in vector)
        if scale == 0:
            return None
        norm = math.hypot(*vector)
        if math.isfinite(norm) and norm > 0:
            return tuple(x / norm for x in vector)
        scaled = tuple(x / scale for x in vector)
        norm = math.hypot(*scaled)
        return tuple(x / norm for x in scaled)
    except (TypeError, ValueError, OverflowError):
        return None


def _cos(a, b) -> float:
    return max(-1.0, min(1.0, math.fsum(x * y for x, y in zip(a, b))))


def _mean(observations) -> tuple[float, ...] | None:
    if not observations:
        return None
    total = math.fsum(weight for _, weight in observations)
    mean = tuple(math.fsum(vector[i] * (weight / total) for vector, weight in observations)
                 for i in range(len(observations[0][0])))
    return None if math.hypot(*mean) <= 1e-12 else _unit(mean)


def estimate_speakers(centroids: Iterable[tuple[float, ...]], threshold: float = .85,
                      max_speakers: int = 8) -> dict:
    """Bounded thresholded-centroid eigengap, with reproducible diagnostics."""
    import numpy as np
    _validate_config(RefineConfig(merge_threshold=threshold, max_speakers=max_speakers))
    vectors = [_unit(c) for c in centroids]
    if any(c is None for c in vectors) or len({len(c) for c in vectors}) > 1:
        raise ValueError("valid same-dimensional nonzero centroids required")
    count = len(vectors)
    if count > 256:
        raise ValueError("centroid count exceeds 256")
    if count < 2:
        return {"estimated_k": count, "eigenvalues": [0.0] * count, "gaps": [],
                "reason": "empty" if not count else "single_centroid", "affinity_threshold": threshold}
    affinity = np.zeros((count, count), dtype=np.float64)
    for i in range(count):
        for j in range(i):
            affinity[i, j] = affinity[j, i] = max(0.0, (_cos(vectors[i], vectors[j]) - threshold) / (1 - threshold))
    degree = affinity.sum(axis=1)
    inv = np.zeros(count)
    positive = degree > 0
    inv[positive] = 1 / np.sqrt(degree[positive])
    laplacian = -affinity * inv[:, None] * inv[None, :]
    laplacian[np.diag_indices(count)] = positive.astype(float)
    eigenvalues = np.linalg.eigvalsh(laplacian)
    eigenvalues = [0.0 if abs(float(v)) < 1e-12 else float(v) for v in eigenvalues]
    candidates = [(k, max(0.0, eigenvalues[k] - eigenvalues[k - 1]))
                  for k in range(1, min(max_speakers, count - 1) + 1)]
    largest = max(gap for _, gap in candidates)
    if largest <= 1e-9:
        chosen, reason = min(count, max_speakers), "flat_spectrum_retain"
    else:
        chosen = max(k for k, gap in candidates if largest - gap <= 1e-9)
        reason = "largest_gap_larger_k_tie"
    return {"estimated_k": chosen, "eigenvalues": eigenvalues,
            "gaps": [{"k": k, "gap": gap} for k, gap in candidates], "reason": reason,
            "affinity_threshold": threshold, "isolated_centroids": int((~positive).sum())}


def _coalesce(turns: Iterable[Turn]) -> list[Turn]:
    source = list(turns)
    result = []
    for speaker in sorted({t.speaker for t in source}):
        result.extend(Turn(a, b, speaker) for a, b in
                      _union((t.start_ms, t.end_ms) for t in source if t.speaker == speaker))
    return sorted(result, key=lambda t: (t.start_ms, t.end_ms, t.speaker))


def _duration(native: list[Turn], members: set[int]) -> int:
    return sum(b - a for a, b in _union((t.start_ms, t.end_ms) for t in native if t.speaker in members))


def _overlap_ms(native: list[Turn], left: set[int], right: set[int]) -> int:
    a = _union((t.start_ms, t.end_ms) for t in native if t.speaker in left)
    b = _union((t.start_ms, t.end_ms) for t in native if t.speaker in right)
    return sum(max(0, min(y, v) - max(x, u)) for x, y in a for u, v in b)


def refine(turns: Iterable[Turn], windows: Iterable[EmbeddingWindow], duration_ms: int,
           config: RefineConfig = RefineConfig()) -> RefineResult:
    """Pure deterministic refinement of real native intervals and observations."""
    _validate_duration(duration_ms)
    _validate_config(config)
    native, invalid_turns = _valid_turns(turns, duration_ms)
    diagnostics = {"algorithm": "centroid-eigengap-v1", "config": asdict(config),
                   "duration_ms": duration_ms, "invalid_turns": invalid_turns,
                   "invalid_windows": [], "merges": [], "small_reassignments": [],
                   "smoothing": [], "forced_cap_merges": 0, "low_similarity_merges": 0,
                   "overlap_collapses_ms": 0}

    def unsupported(reason):
        diagnostics.update(status="UNSUPPORTED", reason=reason, output_clusters=len({t.speaker for t in native if t.speaker >= 0}))
        return RefineResult(tuple(native), False, diagnostics)

    if invalid_turns:
        return unsupported("invalid_native_turns")
    order = sorted({t.speaker for t in native if t.speaker >= 0},
                   key=lambda speaker: (min(t.start_ms for t in native if t.speaker == speaker), speaker))
    rank = {speaker: i for i, speaker in enumerate(order)}
    diagnostics["input_clusters"] = len(order)
    if not order:
        diagnostics.update(status="EMPTY" if not native else "UNKNOWN_ONLY", output_clusters=0)
        return RefineResult(tuple(native), True, diagnostics)
    if len(order) > 256:
        return unsupported("too_many_native_clusters")
    allowed = {(w.start_ms, w.end_ms, w.speaker) for w in clean_windows(native, duration_ms)}
    observed = {speaker: [] for speaker in order}
    prepared = {}
    for index, window in enumerate(windows):
        valid_metadata = (isinstance(window, EmbeddingWindow) and
                          all(_integer(v) for v in (window.start_ms, window.end_ms, window.speaker)))
        key = (window.start_ms, window.end_ms, window.speaker) if valid_metadata else None
        vector = _unit(window.embedding) if isinstance(window, EmbeddingWindow) else None
        if key not in allowed or window.clean is not True or vector is None:
            diagnostics["invalid_windows"].append({"index": index, "reason": "invalid_or_nonclean_window"})
        else:
            prepared.setdefault(key, []).append((vector, index))
    dimensions = {len(vector) for entries in prepared.values() for vector, _ in entries}
    if len(dimensions) > 1:
        return unsupported("embedding_dimension_mismatch")
    # Repeated windows are not independent measurements. Conflicting duplicates
    # are rejected, identical duplicates contribute once, independent of order.
    for key, entries in sorted(prepared.items()):
        variants = set(vector for vector, _ in entries)
        if len(variants) != 1:
            diagnostics["invalid_windows"].extend({"index": index, "reason": "conflicting_duplicate_window"} for _, index in entries)
            continue
        observed[key[2]].append((entries[0][0], key[1] - key[0]))
    original = {speaker: _mean(observed[speaker]) for speaker in order}
    missing = [speaker for speaker in order if original[speaker] is None]
    diagnostics["window_counts"] = [{"speaker": speaker, "count": len(observed[speaker])} for speaker in order]
    diagnostics["missing_centroid_labels"] = missing
    diagnostics["fully_acoustic_supported"] = not missing
    diagnostics["centroids"] = [{"speaker": speaker, "embedding": list(original[speaker])}
                                for speaker in order if original[speaker] is not None]
    if not diagnostics["centroids"] and len(order) <= config.max_speakers:
        return unsupported("no_measured_centroids")
    eigengap = estimate_speakers([original[speaker] for speaker in order if original[speaker] is not None],
                                config.merge_threshold, config.max_speakers)
    diagnostics["eigengap"] = eigengap
    groups = {speaker: {speaker} for speaker in order}

    def centroid(key):
        return _mean([observation for speaker in sorted(groups[key], key=rank.get) for observation in observed[speaker]])

    def pair():
        choices = []
        keys = sorted(groups, key=rank.get)
        centroids = {key: centroid(key) for key in keys}
        for i, left in enumerate(keys):
            for right in keys[i + 1:]:
                a, b = centroids[left], centroids[right]
                if a is None or b is None:
                    continue
                if config.complete_link_guard and any(_cos(original[x], original[y]) <= config.merge_threshold
                        for x in groups[left] for y in groups[right]):
                    continue
                choices.append((_cos(a, b), left, right))
        return min(choices, key=lambda p: (-p[0], rank[p[1]], rank[p[2]])) if choices else None

    def merge(best, stage):
        similarity, left, right = best
        overlap = _overlap_ms(native, groups[left], groups[right])
        diagnostics["merges"].append({"stage": stage, "left": sorted(groups[left]), "right": sorted(groups[right]),
                                      "cosine": similarity, "simultaneous_ms": overlap})
        diagnostics["overlap_collapses_ms"] += overlap
        diagnostics["low_similarity_merges"] += int(similarity <= config.merge_threshold)
        diagnostics["forced_cap_merges"] += int(stage == "forced_cap")
        groups[left] |= groups.pop(right)

    if config.merge_similar:
        while (best := pair()) is not None and best[0] > config.merge_threshold:
            merge(best, "cosine")
    if config.use_eigengap:
        target = eigengap["estimated_k"]
        def acoustic_count():
            return sum(centroid(key) is not None for key in groups)
        while acoustic_count() > target:
            best = pair()
            if best is None or best[0] <= 0:
                break
            merge(best, "eigengap")
        diagnostics["eigengap_target_reached"] = acoustic_count() <= target

    cutoff = max(config.min_cluster_ms, config.min_cluster_fraction * duration_ms)
    diagnostics["small_cluster_cutoff_ms"] = cutoff
    if config.reassign_small and len(groups) > 1:
        durations = {key: _duration(native, members) for key, members in groups.items()}
        anchors = [key for key in groups if durations[key] >= cutoff and centroid(key) is not None]
        if not anchors:
            available = [key for key in groups if centroid(key) is not None]
            if available:
                anchors = [min(available, key=lambda key: (-durations[key], rank[key]))]
                diagnostics["all_small_anchor" if all(v < cutoff for v in durations.values())
                            else "no_large_measured_anchor"] = anchors[0]
        # Freeze anchor centroids for this pass so source iteration is immaterial.
        anchor_centroids = {key: centroid(key) for key in anchors}
        planned = []
        for key in sorted(groups, key=rank.get):
            if key in anchors or durations[key] >= cutoff:
                continue
            vector = centroid(key)
            if vector is None:
                if config.small_missing_centroid_policy == "retain" or not anchors:
                    diagnostics["small_reassignments"].append({"source": sorted(groups[key]), "target": None,
                        "cosine": None, "method": "retain", "applied": False,
                        "reason": "missing_centroid" if anchors else "no_measured_anchor"})
                    continue
                source_turns = [t for t in native if t.speaker in groups[key]]
                distances = [(abs((source.start_ms + source.end_ms) - (candidate.start_ms + candidate.end_ms)),
                              candidate.start_ms, rank[anchor], source.start_ms, anchor)
                             for anchor in anchors for candidate in native if candidate.speaker in groups[anchor]
                             for source in source_turns]
                best_distance, _, _, _, target = min(distances)
                planned.append((key, target, None, best_distance / 2))
                continue
            if not anchors:
                continue
            similarity, target = min(((_cos(vector, anchor_centroids[a]), a) for a in anchors if anchor_centroids[a] is not None),
                                     key=lambda p: (-p[0], rank[p[1]]))
            guard = config.minimum_reassignment_similarity
            if guard is not None and similarity < guard:
                diagnostics["small_reassignments"].append({"source": sorted(groups[key]), "target": target,
                    "cosine": similarity, "method": "centroid", "applied": False, "reason": "minimum_similarity_guard"})
            else:
                planned.append((key, target, similarity, None))
        for key, target, similarity, distance in planned:
            overlap = _overlap_ms(native, groups[key], groups[target])
            diagnostics["small_reassignments"].append({"source": sorted(groups[key]), "target": target,
                "cosine": similarity, "method": "temporal" if similarity is None else "centroid",
                "midpoint_distance_ms": distance, "applied": True, "simultaneous_ms": overlap})
            diagnostics["overlap_collapses_ms"] += overlap
            groups[target] |= groups.pop(key)
    # The hard cap includes missing-centroid labels and takes precedence over
    # the optional complete-link guard. Never invent a missing centroid.
    while len(groups) > config.max_speakers:
        keys = sorted(groups, key=rank.get)
        centroids = {key: centroid(key) for key in keys}
        candidates = [(_cos(a, b), left, right) for i, left in enumerate(keys)
                      for right in keys[i + 1:]
                      if (a := centroids[left]) is not None and (b := centroids[right]) is not None]
        if not candidates:
            return unsupported("hard_cap_without_valid_centroids")
        merge(min(candidates, key=lambda p: (-p[0], rank[p[1]], rank[p[2]])), "forced_cap")
    mapping = {speaker: key for key, members in groups.items() for speaker in members}
    diagnostics["source_mapping_before_smoothing"] = [{"source": speaker, "target": mapping[speaker]} for speaker in order]
    output = _coalesce(Turn(t.start_ms, t.end_ms, mapping.get(t.speaker, -1)) for t in native)
    if config.smooth and config.smooth_ms > 0:
        changed = True
        while changed:
            changed = False
            for i in range(1, len(output) - 1):
                left, middle, right = output[i - 1:i + 2]
                if (left.speaker < 0 or middle.speaker < 0 or left.speaker != right.speaker or middle.speaker == left.speaker
                        or middle.end_ms - middle.start_ms >= config.smooth_ms
                        or left.end_ms != middle.start_ms or middle.end_ms != right.start_ms):
                    continue
                if any(t.speaker != middle.speaker and t.start_ms < middle.end_ms and t.end_ms > middle.start_ms
                       for j, t in enumerate(output) if j != i):
                    continue
                diagnostics["smoothing"].append({"start_ms": middle.start_ms, "end_ms": middle.end_ms,
                                                "source": middle.speaker, "target": left.speaker})
                output[i] = Turn(middle.start_ms, middle.end_ms, left.speaker)
                output = _coalesce(output)
                changed = True
                break
    stable = {}
    for turn in output:
        if turn.speaker >= 0 and turn.speaker not in stable:
            stable[turn.speaker] = len(stable)
    output = [Turn(t.start_ms, t.end_ms, stable.get(t.speaker, -1)) for t in output]
    diagnostics.update(status="SUPPORTED" if not missing else "PARTIAL_ACOUSTIC", output_clusters=len(stable),
                       output_label_mapping=[{"source": k, "target": v} for k, v in stable.items()])
    return RefineResult(tuple(output), True, diagnostics)
