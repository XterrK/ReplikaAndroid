"""C2: pure measured-window HC and native-activity voting; no audio/NN/gold.

Each real clean window starts as its own observation. Complete/average linkage
uses condensed cosine distances; SciPy fcluster(distance) includes equality at
the cut 1-tau. If needed the same HC tree continues to the explicit <=8 cap.
Canonical window ordering makes ties reproducible for the recorded SciPy version.

Source contracts:
https://docs.scipy.org/doc/scipy/reference/generated/scipy.cluster.hierarchy.linkage.html
https://docs.scipy.org/doc/scipy/reference/generated/scipy.cluster.hierarchy.fcluster.html

125 ms atoms split only original native activity. Same-source covering windows
vote by overlap times a center triangle; uncovered activity uses the nearest
same-source measured window, or an explicitly non-acoustic global time fallback.
New internal boundaries are voting-grid proxies, never forced alignment.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from numbers import Real

from tools.eval.pipeline import Turn
from tools.eval.speaker_refiner import (
    EmbeddingWindow, clean_windows, estimate_speakers,
    _unit, _mean, _cos, _union, _coalesce,
)


@dataclass(frozen=True)
class WindowClusterConfig:
    tau: float = .65
    method: str = "complete"
    grid_ms: int = 125
    max_speakers: int = 8
    reassign_small: bool = False
    min_cluster_ms: int = 2000
    min_cluster_fraction: float = .03
    minimum_reassignment_similarity: float | None = None
    smooth: bool = True
    smooth_ms: int = 500


@dataclass(frozen=True)
class WindowClusterResult:
    turns: tuple[Turn, ...]
    accepted: bool
    diagnostics: dict


def _integer(value):
    return type(value) is int


def _finite(value):
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _validate(config, duration):
    if not _integer(duration) or not 0 <= duration <= (1 << 63) - 1:
        raise ValueError("duration_ms must be a nonnegative signed-64-bit integer")
    if not _finite(config.tau) or not -1 < config.tau < 1:
        raise ValueError("tau must be finite and strictly between -1 and 1")
    if config.method not in ("complete", "average"):
        raise ValueError("method must be complete or average")
    if not _integer(config.grid_ms) or not 1 <= config.grid_ms <= 1000:
        raise ValueError("grid_ms must be an integer in 1..1000")
    if not _integer(config.max_speakers) or not 1 <= config.max_speakers <= 8:
        raise ValueError("max_speakers must be an integer in 1..8")
    if not _integer(config.min_cluster_ms) or config.min_cluster_ms < 0:
        raise ValueError("min_cluster_ms must be nonnegative")
    if not _finite(config.min_cluster_fraction) or not 0 <= config.min_cluster_fraction <= 1:
        raise ValueError("min_cluster_fraction must be in 0..1")
    if not _integer(config.smooth_ms) or config.smooth_ms < 0:
        raise ValueError("smooth_ms must be nonnegative")
    if type(config.reassign_small) is not bool or type(config.smooth) is not bool:
        raise ValueError("stage flags must be booleans")
    guard = config.minimum_reassignment_similarity
    if guard is not None and (not _finite(guard) or not -1 <= guard <= 1):
        raise ValueError("minimum_reassignment_similarity must be in -1..1 or None")


def _speaker_time(turns):
    return sum(b - a for speaker in {t.speaker for t in turns}
               for a, b in _union((t.start_ms, t.end_ms) for t in turns if t.speaker == speaker))


def _activity(turns):
    return _union((t.start_ms, t.end_ms) for t in turns)


def _cluster(windows, vectors, config, diagnostic):
    import numpy as np
    import scipy
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform

    count = len(windows)
    diagnostic.update(scipy_version=scipy.__version__, cut_distance=1 - config.tau,
                      cut_inclusive=True, linkage_method=config.method,
                      canonical_window_order="start_ms, end_ms, original speaker")
    if count == 1:
        tree, initial = np.empty((0, 4), dtype=np.float64), [1]
    else:
        values = np.asarray(vectors, dtype=np.float64)
        distances = np.clip(1 - values @ values.T, 0., 2.)
        np.fill_diagonal(distances, 0.)
        # Explicit symmetrization avoids strict squareform symmetry failures
        # from independently accumulated floating-point dot products.
        distances = (distances + distances.T) / 2
        tree = linkage(squareform(distances), method=config.method, optimal_ordering=False)
        initial = [int(v) for v in fcluster(tree, t=1 - config.tau, criterion="distance")]
    groups = {}
    for index, label in enumerate(initial):
        groups.setdefault(label, set()).add(index)
    diagnostic["window_clusters_at_cut"] = len(groups)
    diagnostic["linkage_tree"] = tree.tolist()
    diagnostic["forced_cap_merges"] = []
    leaves = {i: {i} for i in range(count)}
    for row_index, row in enumerate(tree):
        members = leaves[int(row[0])] | leaves[int(row[1])]
        leaves[count + row_index] = members
        keys = [key for key, group in groups.items() if group & members]
        if len(groups) > config.max_speakers and len(keys) > 1:
            # All descendants below this HC node are complete flat clusters.
            # Continue this same nearest-linkage tree, not a hidden new metric.
            if any(not groups[key] <= members for key in keys):
                continue
            keep = min(keys, key=lambda key: min(groups[key]))
            combined = set().union(*(groups[key] for key in keys))
            diagnostic["forced_cap_merges"].append({
                "linkage_row": row_index, "window_groups": [sorted(groups[key]) for key in keys],
                "distance": float(row[2]), "above_cut": float(row[2]) > 1 - config.tau,
                "result_window_indices": sorted(combined),
            })
            for key in keys:
                if key != keep:
                    groups.pop(key)
            groups[keep] = combined
    ordered = sorted(groups.values(), key=min)
    assignments = [next(label for label, members in enumerate(ordered) if index in members)
                   for index in range(count)]
    centroids = {label: _mean([(vectors[i], windows[i].end_ms - windows[i].start_ms) for i in members])
                 for label, members in enumerate(ordered)}
    diagnostic["window_clusters_after_cap"] = len(ordered)
    diagnostic["window_cluster_members"] = [sorted(group) for group in ordered]
    diagnostic["cluster_centroids"] = [{"cluster": label, "embedding": list(v) if v is not None else None}
                                        for label, v in centroids.items()]
    return assignments, centroids


def _assign(native, windows, cluster_labels, config, diagnostic):
    by_source = {speaker: [i for i, window in enumerate(windows) if window.speaker == speaker]
                 for speaker in {t.speaker for t in native}}
    atoms, result, fallbacks = [], [], []
    for speaker in sorted(by_source):
        for begin, end in _union((t.start_ms, t.end_ms) for t in native if t.speaker == speaker):
            start = begin
            while start < end:
                stop = min(end, (start // config.grid_ms + 1) * config.grid_ms)
                scores, votes = {}, []
                for index in by_source[speaker]:
                    window = windows[index]
                    left, right = max(start, window.start_ms), min(stop, window.end_ms)
                    if right <= left:
                        continue
                    triangle = 1 - abs((left + right) - (window.start_ms + window.end_ms)) / (window.end_ms - window.start_ms)
                    weight = (right - left) * max(0., triangle)
                    label = cluster_labels[index]
                    scores[label] = scores.get(label, 0.) + weight
                    votes.append({"window": index, "cluster": label, "overlap_ms": right - left, "weight": weight})
                if scores and max(scores.values()) > 0:
                    label = min(scores, key=lambda value: (-scores[value], value))
                    method, nearest = "covering_same_source_vote", None
                else:
                    same_source = bool(by_source[speaker])
                    candidates = by_source[speaker] if same_source else range(len(windows))
                    nearest = min(candidates, key=lambda i: (
                        abs((start + stop) - (windows[i].start_ms + windows[i].end_ms)),
                        windows[i].start_ms + windows[i].end_ms, i))
                    label = cluster_labels[nearest]
                    method = "nearest_same_source_time" if same_source else "nearest_global_time_missing_source_windows"
                    fallbacks.append({"start_ms": start, "end_ms": stop, "source_speaker": speaker,
                        "window": nearest, "cluster": label, "method": method,
                        "midpoint_distance_ms": abs((start + stop) - (windows[nearest].start_ms + windows[nearest].end_ms)) / 2})
                atoms.append({"start_ms": start, "end_ms": stop, "source_speaker": speaker,
                              "cluster": label, "method": method, "nearest_window": nearest, "votes": votes})
                result.append(Turn(start, stop, label))
                start = stop
    diagnostic["assignment_atoms"] = sorted(atoms, key=lambda item: (item["start_ms"], item["end_ms"], item["source_speaker"]))
    diagnostic["fallbacks"] = fallbacks
    diagnostic["assignment_method_speaker_ms"] = {
        method: sum(a["end_ms"] - a["start_ms"] for a in atoms if a["method"] == method)
        for method in sorted({a["method"] for a in atoms})}
    diagnostic["fully_acoustic_supported"] = not fallbacks
    diagnostic["every_native_label_has_measured_windows"] = all(by_source.values())
    return _coalesce(result)


def _small(turns, centroids, duration, config, diagnostic):
    cutoff = max(config.min_cluster_ms, config.min_cluster_fraction * duration)
    diagnostic["small_cluster_cutoff_ms"] = cutoff
    diagnostic["small_reassignments"] = []
    labels = sorted({t.speaker for t in turns})
    mapping = {label: label for label in centroids}
    if not config.reassign_small or len(labels) < 2:
        return turns, mapping
    durations = {label: sum(b - a for a, b in _union((t.start_ms, t.end_ms) for t in turns if t.speaker == label)) for label in labels}
    anchors = [label for label in labels if durations[label] >= cutoff]
    if not anchors:
        anchors = [min(labels, key=lambda label: (-durations[label], label))]
        diagnostic["all_small_anchor"] = anchors[0]
    for label in labels:
        if label in anchors or durations[label] >= cutoff:
            continue
        similarity, target = min(((_cos(centroids[label], centroids[a]), a) for a in anchors),
                                 key=lambda item: (-item[0], item[1]))
        applied = config.minimum_reassignment_similarity is None or similarity >= config.minimum_reassignment_similarity
        diagnostic["small_reassignments"].append({"source": label, "target": target, "cosine": similarity,
            "source_activity_ms": durations[label], "applied": applied,
            "reason": "nearest_measured_window_cluster_centroid" if applied else "minimum_similarity_guard"})
        if applied:
            mapping[label] = target
    return _coalesce(Turn(t.start_ms, t.end_ms, mapping[t.speaker]) for t in turns), mapping


def _smooth(turns, config, diagnostic):
    result = list(turns)
    diagnostic["smoothing"] = []
    changed = config.smooth and config.smooth_ms > 0
    while changed:
        changed = False
        for i in range(1, len(result) - 1):
            left, middle, right = result[i - 1:i + 2]
            if (left.speaker != right.speaker or middle.speaker == left.speaker
                    or middle.end_ms - middle.start_ms >= config.smooth_ms
                    or left.end_ms != middle.start_ms or middle.end_ms != right.start_ms):
                continue
            if any(t.start_ms < middle.end_ms and t.end_ms > middle.start_ms
                   for j, t in enumerate(result) if j != i):
                continue
            diagnostic["smoothing"].append({"start_ms": middle.start_ms, "end_ms": middle.end_ms,
                                             "source": middle.speaker, "target": left.speaker})
            result[i] = Turn(middle.start_ms, middle.end_ms, left.speaker)
            result = _coalesce(result)
            changed = True
            break
    return result


def overcluster(turns, windows, duration_ms, config=WindowClusterConfig()):
    """Split/merge saved native activity using measured windows and global knobs.

    accepted indicates computational support only, never speaker quality/gates.
    Missing-window temporal fallbacks are explicit; zero real windows with speech
    is unsupported and returns the unchanged native intervals.
    """
    _validate(config, duration_ms)
    source, supplied = list(turns), list(windows)
    native = sorted([t for t in source if isinstance(t, Turn)
                     and all(_integer(v) for v in (t.start_ms, t.end_ms, t.speaker))
                     and 0 <= t.start_ms < t.end_ms <= duration_ms and t.speaker >= 0],
                    key=lambda t: (t.start_ms, t.end_ms, t.speaker))
    diagnostic = {"algorithm": "window-overcluster-v1", "config": asdict(config), "duration_ms": duration_ms,
                  "new_neural_inference": False, "eigengap_applied": False,
                  "boundary_timing_scope": "Saved-window votes on an activity-confined grid; no forced alignment or true change-point accuracy claim",
                  "invalid_windows": [], "duplicate_windows": [], "native_input_clusters": len({t.speaker for t in native})}
    def unsupported(reason):
        diagnostic.update(status="UNSUPPORTED", reason=reason, output_clusters=len({t.speaker for t in native}))
        return WindowClusterResult(tuple(native), False, diagnostic)
    if len(native) != len(source):
        return unsupported("invalid_native_turns")
    allowed = {(w.start_ms, w.end_ms, w.speaker) for w in clean_windows(native, duration_ms)}
    prepared = {}
    for index, window in enumerate(supplied):
        metadata = isinstance(window, EmbeddingWindow) and all(_integer(v) for v in (window.start_ms, window.end_ms, window.speaker))
        key = (window.start_ms, window.end_ms, window.speaker) if metadata else None
        unit = _unit(window.embedding) if isinstance(window, EmbeddingWindow) else None
        if key not in allowed or window.clean is not True or unit is None:
            diagnostic["invalid_windows"].append(index)
        elif key in prepared:
            if prepared[key][1] != unit:
                diagnostic["invalid_windows"].append(index)
            else:
                diagnostic["duplicate_windows"].append(index)
        else:
            prepared[key] = (window, unit)
    if diagnostic["invalid_windows"]:
        return unsupported("invalid_or_conflicting_measured_windows")
    ordered = [prepared[key] for key in sorted(prepared)]
    if not native:
        diagnostic.update(status="EMPTY", output_clusters=0, activity_union_preserved=True, window_labels=[])
        return WindowClusterResult((), True, diagnostic)
    if not ordered:
        return unsupported("no_real_clean_windows")
    if len(ordered) > 2048:
        return unsupported("too_many_windows_for_quadratic_hc")
    measured, vectors = [item[0] for item in ordered], [item[1] for item in ordered]
    if len({len(v) for v in vectors}) != 1:
        return unsupported("embedding_dimension_mismatch")
    labels, centroids = _cluster(measured, vectors, config, diagnostic)
    if any(v is None for v in centroids.values()):
        return unsupported("cancelled_measured_cluster_centroid")
    diagnostic["eigengap_diagnostic"] = estimate_speakers(list(centroids.values()), config.tau, config.max_speakers)
    assigned = _assign(native, measured, labels, config, diagnostic)
    diagnostic["clusters_after_voting"] = len({t.speaker for t in assigned})
    result, small_mapping = _small(assigned, centroids, duration_ms, config, diagnostic)
    diagnostic["clusters_after_small"] = len({t.speaker for t in result})
    result = _smooth(result, config, diagnostic)
    stable = {}
    for turn in result:
        stable.setdefault(turn.speaker, len(stable))
    result = [Turn(t.start_ms, t.end_ms, stable[t.speaker]) for t in result]
    diagnostic["window_labels"] = [{"index": i, "start_ms": w.start_ms, "end_ms": w.end_ms,
        "source_speaker": w.speaker, "cluster": labels[i], "after_small_cluster": small_mapping[labels[i]],
        "stable_label_if_present": stable.get(small_mapping[labels[i]])} for i, w in enumerate(measured)]
    original_boundaries = {x for t in native for x in (t.start_ms, t.end_ms)}
    new_boundaries = sorted({x for t in result for x in (t.start_ms, t.end_ms)} - original_boundaries)
    diagnostic.update(status="SUPPORTED" if diagnostic["fully_acoustic_supported"] else "PARTIAL_TEMPORAL",
        measured_unique_windows=len(measured), embedding_dimension=len(vectors[0]), output_clusters=len(stable),
        stable_label_mapping=[{"cluster": key, "label": value} for key, value in stable.items()],
        original_activity_union_ms=sum(b - a for a, b in _activity(native)),
        output_activity_union_ms=sum(b - a for a, b in _activity(result)),
        activity_union_preserved=_activity(native) == _activity(result),
        original_speaker_time_ms=_speaker_time(native), output_speaker_time_ms=_speaker_time(result),
        speaker_time_collapsed_ms=_speaker_time(native) - _speaker_time(result),
        new_internal_grid_boundaries_ms=new_boundaries, grid_boundary_resolution_ms=config.grid_ms,
        max_assignment_atom_ms=max(a["end_ms"] - a["start_ms"] for a in diagnostic["assignment_atoms"]))
    if not diagnostic["activity_union_preserved"]:
        return unsupported("internal_activity_union_changed")
    return WindowClusterResult(tuple(result), True, diagnostic)
