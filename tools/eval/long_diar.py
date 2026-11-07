#!/usr/bin/env python3
"""Step 6: long-recording diarization stand (legacy single-pass vs chunked).

``legacy``  = the current C2 path: the WHOLE recording is one Float32 array,
              one sherpa SD call, then C2 clean-window refinement (skipped
              above 2048 clean windows, exactly like Kotlin).
``chunked`` = ERES2NET_WINDOW_CHUNKED_V1: equal windows <= W with overlap O,
              PCM of each window read from disk blockwise, per-window SD + C2,
              per-window speaker centroids from refined clean-window embeddings,
              global average-linkage clustering of centroids with cannot-link
              inside one window, stitching at the overlap point nearest to the
              midpoint between window centres (silence preferred).

Pure planning/clustering/stitching mirrors app/src/main/java/ru/replika/domain/
ChunkedDiarization.kt; ``tools/eval/tests/test_long_diar.py`` checks both.
Each ``run`` invocation should be a fresh process so that peak memory
(Windows PeakWorkingSetSize / Linux ru_maxrss) belongs to that path only.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import gc
import json
import math
import os
from pathlib import Path
import sys
import time
import wave

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.eval.pipeline import Turn, stable_turns, _kotlin_round_ms  # noqa: E402
from tools.eval.speaker_refiner import EmbeddingWindow, clean_windows  # noqa: E402
from tools.eval.window_overcluster import WindowClusterConfig, overcluster  # noqa: E402

SR = 16000
REPO = Path(__file__).resolve().parents[2]
MODEL_ROOT = REPO / "model-pack"
C2_CONFIG = WindowClusterConfig(tau=.36, method="average", grid_ms=125, max_speakers=8, reassign_small=True)
MAX_CLEAN_WINDOWS = 2048


# --------------------------------------------------------------------------- pure policy

@dataclass(frozen=True)
class ChunkConfig:
    """Kotlin twin: ChunkedDiarization.Config."""
    min_duration_ms: int = 15 * 60_000   # chunk only strictly longer recordings
    window_ms: int = 10 * 60_000
    overlap_ms: int = 30_000
    global_tau: float = .50              # merge centroids when cosine >= tau
    max_speakers: int = 8
    stitch_search_ms: int = 10_000       # silence search radius around the stitch midpoint


@dataclass(frozen=True)
class Centroid:
    window: int
    label: int
    vector: tuple[float, ...]
    speech_ms: int


def plan_windows(duration_ms: int, config: ChunkConfig) -> list[tuple[int, int]]:
    """Equal windows no longer than W covering [0, D) with exact overlap O."""
    if duration_ms <= config.min_duration_ms:
        return [(0, duration_ms)]
    w, o = config.window_ms, config.overlap_ms
    if not 0 <= o < w:
        raise ValueError("overlap must be shorter than the window")
    count = -(-(duration_ms - o) // (w - o))       # ceil
    length = -(-(duration_ms + (count - 1) * o) // count)
    step = length - o
    windows = []
    for k in range(count):
        start = k * step
        end = duration_ms if k == count - 1 else min(duration_ms, start + length)
        windows.append((start, end))
    return windows


def _unit(vector) -> tuple[float, ...] | None:
    norm = math.sqrt(math.fsum(x * x for x in vector))
    if not math.isfinite(norm) or norm <= 1e-12:
        return None
    return tuple(x / norm for x in vector)


def _cosine(a, b) -> float:
    return max(-1., min(1., math.fsum(x * y for x, y in zip(a, b))))


def window_centroids(window_index: int, turns: list[Turn], measured: list[EmbeddingWindow]) -> list[Centroid]:
    """Weighted mean of unit clean-window vectors per final local label.

    A clean window belongs to the final label covering most of its span
    (ties: smaller label). Labels without any measured window get no centroid.
    """
    sums: dict[int, list[float]] = {}
    for window in measured:
        cover: dict[int, int] = {}
        for turn in turns:
            overlap = min(turn.end_ms, window.end_ms) - max(turn.start_ms, window.start_ms)
            if overlap > 0:
                cover[turn.speaker] = cover.get(turn.speaker, 0) + overlap
        if not cover:
            continue
        label = min(cover, key=lambda key: (-cover[key], key))
        unit = _unit(window.embedding)
        if unit is None:
            continue
        weight = float(window.end_ms - window.start_ms)
        acc = sums.setdefault(label, [0.] * len(unit))
        for i, value in enumerate(unit):
            acc[i] += value * weight
    speech = {}
    for turn in turns:
        speech[turn.speaker] = speech.get(turn.speaker, 0) + turn.end_ms - turn.start_ms
    result = []
    for label in sorted(sums):
        unit = _unit(sums[label])
        if unit is not None:
            result.append(Centroid(window_index, label, unit, speech.get(label, 0)))
    return result


def global_clusters(centroids: list[Centroid], config: ChunkConfig) -> list[int]:
    """Average linkage over cosine distance with cannot-link inside a window.

    Merge the closest allowed pair while its distance <= 1 - tau; then, while
    more than max_speakers clusters remain, keep merging the closest allowed
    pair regardless of the cut. Ties: smallest (i, j) cluster ids. Returns a
    stable 0..K-1 label per centroid in first-appearance order.
    """
    n = len(centroids)
    if n == 0:
        return []
    dist = [[0.] * n for _ in range(n)]
    for i in range(n):
        for j in range(i):
            d = min(2., max(0., 1. - _cosine(centroids[i].vector, centroids[j].vector)))
            dist[i][j] = dist[j][i] = d
    members = {i: [i] for i in range(n)}
    windows = {i: {centroids[i].window} for i in range(n)}
    cut = 1. - config.global_tau
    while len(members) > 1:
        best = None
        keys = sorted(members)
        for a_index, a in enumerate(keys):
            for b in keys[a_index + 1:]:
                if windows[a] & windows[b]:
                    continue
                d = dist[a][b]
                if best is None or d < best[0]:
                    best = (d, a, b)
        if best is None:
            break
        d, a, b = best
        if d > cut and len(members) <= config.max_speakers:
            break
        na, nb = len(members[a]), len(members[b])
        for c in members:
            if c not in (a, b):
                value = (na * dist[a][c] + nb * dist[b][c]) / (na + nb)
                dist[a][c] = dist[c][a] = value
        members[a] = members[a] + members.pop(b)
        windows[a] = windows[a] | windows.pop(b)
    owner = {}
    for key, items in members.items():
        for item in items:
            owner[item] = key
    order = sorted(range(n), key=lambda i: (centroids[i].window, centroids[i].label))
    stable: dict[int, int] = {}
    for i in order:
        stable.setdefault(owner[i], len(stable))
    return [stable[owner[i]] for i in range(n)]


def stitch_points(windows: list[tuple[int, int]], local_turns: list[list[Turn]], config: ChunkConfig) -> list[int]:
    """One cut per adjacent pair: the midpoint between window centres, moved to
    the nearest instant inside the overlap where neither window has speech
    (within stitch_search_ms); otherwise the midpoint itself."""
    cuts = []
    for k in range(len(windows) - 1):
        (s0, e0), (s1, e1) = windows[k], windows[k + 1]
        mid = (s0 + e0 + s1 + e1) // 4
        lo, hi = max(s1, mid - config.stitch_search_ms), min(e0, mid + config.stitch_search_ms)
        busy = sorted([(t.start_ms + s0, t.end_ms + s0) for t in local_turns[k]] +
                      [(t.start_ms + s1, t.end_ms + s1) for t in local_turns[k + 1]])
        merged: list[list[int]] = []
        for a, b in busy:
            if b <= lo or a >= hi:
                continue
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        free, cursor = [], lo
        for a, b in merged:
            if a > cursor:
                free.append((cursor, a))
            cursor = max(cursor, b)
        if cursor < hi:
            free.append((cursor, hi))
        best = None
        for a, b in free:
            point = min(max(mid, a), b)
            if b - a >= 1 and (best is None or abs(point - mid) < abs(best - mid)
                               or (abs(point - mid) == abs(best - mid) and point < best)):
                best = point
        cuts.append(mid if best is None else best)
    return cuts


def stitch(windows, local_turns, labels_by_window: list[dict[int, int]], cuts: list[int]) -> list[Turn]:
    """Clip each window's globally relabelled turns to its core and coalesce."""
    out: list[Turn] = []
    for k, (start, end) in enumerate(windows):
        core_lo = start if k == 0 else cuts[k - 1]
        core_hi = end if k == len(windows) - 1 else cuts[k]
        for turn in local_turns[k]:
            a, b = max(turn.start_ms + start, core_lo), min(turn.end_ms + start, core_hi)
            if b > a:
                out.append(Turn(a, b, labels_by_window[k][turn.speaker]))
    out.sort(key=lambda t: (t.start_ms, t.end_ms, t.speaker))
    merged: list[Turn] = []
    for turn in out:
        same = next((i for i in range(len(merged) - 1, max(-1, len(merged) - 9), -1)
                     if merged[i].speaker == turn.speaker and merged[i].end_ms >= turn.start_ms), None)
        if same is not None:
            prev = merged[same]
            merged[same] = Turn(prev.start_ms, max(prev.end_ms, turn.end_ms), prev.speaker)
        else:
            merged.append(turn)
    return sorted(merged, key=lambda t: (t.start_ms, t.end_ms, t.speaker))


def resolve_labels(local_turns, centroids, labels, window_count) -> list[dict[int, int]]:
    """Map every local label to a global one; a local label without centroid
    takes the label of the temporally nearest turn with a centroid in the same
    window, else the global cluster with the most speech."""
    mapping = [dict() for _ in range(window_count)]
    speech: dict[int, int] = {}
    for c, g in zip(centroids, labels):
        mapping[c.window][c.label] = g
        speech[g] = speech.get(g, 0) + c.speech_ms
    dominant = min(speech, key=lambda g: (-speech[g], g)) if speech else 0
    for k in range(window_count):
        known = [t for t in local_turns[k] if t.speaker in mapping[k]]
        for turn in local_turns[k]:
            if turn.speaker in mapping[k]:
                continue
            if known:
                near = min(known, key=lambda t: (abs((t.start_ms + t.end_ms) - (turn.start_ms + turn.end_ms)), t.start_ms))
                mapping[k][turn.speaker] = mapping[k][near.speaker]
            else:
                mapping[k][turn.speaker] = dominant
    return mapping


# --------------------------------------------------------------------------- native runtime

def peak_memory() -> dict:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                        ("PrivateUsage", ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        psapi = ctypes.WinDLL("psapi")
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        return {"peak_working_set_mb": counters.PeakWorkingSetSize / 2**20,
                "peak_private_mb": counters.PeakPagefileUsage / 2**20}
    import resource
    return {"peak_working_set_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}


class WavReader:
    """Blockwise PCM16 reader; never holds more than the requested range."""

    def __init__(self, path: Path):
        self.handle = wave.open(str(path), "rb")
        if (self.handle.getnchannels(), self.handle.getsampwidth(), self.handle.getframerate()) != (1, 2, SR):
            raise ValueError("16 kHz mono PCM16 WAV required")
        self.samples = self.handle.getnframes()

    @property
    def duration_ms(self) -> int:
        return self.samples * 1000 // SR

    def read(self, first: int, count: int):
        import numpy as np
        self.handle.setpos(first)
        raw = self.handle.readframes(count)
        return np.frombuffer(raw, dtype="<i2").astype(np.float32) / np.float32(32768)

    def close(self):
        self.handle.close()


@dataclass
class Native:
    threads: int = 4
    threshold: float = .3
    shift: float = .1
    tau: float = .36
    timings: dict = field(default_factory=dict)

    def add(self, key, value):
        self.timings[key] = self.timings.get(key, 0.) + value

    def sd(self, samples) -> list[Turn]:
        import sherpa_onnx as sherpa
        config = sherpa.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=str(MODEL_ROOT / "diar/segmentation.onnx"), window_shift_ratio=self.shift),
                num_threads=self.threads, provider="cpu", debug=False),
            embedding=sherpa.SpeakerEmbeddingExtractorConfig(
                model=str(MODEL_ROOT / "diar/embedding.onnx"), num_threads=self.threads, provider="cpu", debug=False),
            clustering=sherpa.FastClusteringConfig(num_clusters=-1, threshold=self.threshold),
            min_duration_on=.2, min_duration_off=.5)
        began = time.perf_counter()
        diarizer = sherpa.OfflineSpeakerDiarization(config)
        self.add("sd_load_s", time.perf_counter() - began)
        marks = []

        def progress(done, total):
            marks.append((time.perf_counter(), done, total))
            return 0

        began = time.perf_counter()
        segments = diarizer.process(samples, callback=progress).sort_by_start_time()
        ended = time.perf_counter()
        del diarizer
        gc.collect()
        self.add("sd_total_s", ended - began)
        if marks:
            # The callback fires after each embedding chunk; before the first one
            # sherpa ran segmentation, after the last one only clustering/post.
            first, last = marks[0][0], marks[-1][0]
            per_chunk = (last - first) / max(1, len(marks) - 1)
            self.add("sd_segmentation_s", max(0., first - began - per_chunk))
            self.add("sd_embedding_s", (last - first) + min(per_chunk, first - began))
            self.add("sd_clustering_s", ended - last)
            self.timings["sd_embedding_chunks"] = self.timings.get("sd_embedding_chunks", 0) + marks[-1][2]
        duration_ms = len(samples) * 1000 // SR
        turns = [Turn(max(0, min(duration_ms, _kotlin_round_ms(s.start))),
                      max(0, min(duration_ms, _kotlin_round_ms(s.end))), s.speaker) for s in segments]
        return stable_turns([t for t in turns if t.end_ms > t.start_ms])

    def refine(self, samples, turns: list[Turn]):
        """C2 exactly as DiarizationRefiner: returns (turns, measured, accepted, reason)."""
        import sherpa_onnx as sherpa
        duration_ms = len(samples) * 1000 // SR
        planned = clean_windows(turns, duration_ms)
        if len(planned) > MAX_CLEAN_WINDOWS:
            return turns, [], False, "too_many_windows_for_quadratic_hc"
        if not planned:
            result = overcluster(turns, [], duration_ms, C2_CONFIG if self.tau == .36 else
                                 WindowClusterConfig(tau=self.tau, method="average", grid_ms=125,
                                                     max_speakers=8, reassign_small=True))
            return list(result.turns), [], result.accepted, result.diagnostics.get("reason")
        began = time.perf_counter()
        extractor = sherpa.SpeakerEmbeddingExtractor(sherpa.SpeakerEmbeddingExtractorConfig(
            model=str(MODEL_ROOT / "diar/embedding.onnx"), num_threads=self.threads, provider="cpu", debug=False))
        self.add("refiner_load_s", time.perf_counter() - began)
        began = time.perf_counter()
        measured = []
        for window in planned:
            stream = extractor.create_stream()
            stream.accept_waveform(SR, samples[window.start_ms * 16:window.end_ms * 16])
            stream.input_finished()
            vector = tuple(float(x) for x in extractor.compute(stream))
            measured.append(EmbeddingWindow(window.start_ms, window.end_ms, window.speaker, vector))
            del stream
        del extractor
        gc.collect()
        self.add("refiner_embedding_s", time.perf_counter() - began)
        self.timings["refiner_windows"] = self.timings.get("refiner_windows", 0) + len(measured)
        began = time.perf_counter()
        config = C2_CONFIG if self.tau == .36 else WindowClusterConfig(
            tau=self.tau, method="average", grid_ms=125, max_speakers=8, reassign_small=True)
        result = overcluster(turns, measured, duration_ms, config)
        self.add("refiner_cluster_s", time.perf_counter() - began)
        return list(result.turns), measured, result.accepted, result.diagnostics.get("reason")


def run_legacy(path: Path, native: Native) -> dict:
    began = time.perf_counter()
    reader = WavReader(path)
    samples = reader.read(0, reader.samples)      # the whole recording, as ProcessingWorker
    reader.close()
    native.add("read_s", time.perf_counter() - began)
    turns = native.sd(samples)
    refined, _, accepted, reason = native.refine(samples, turns)
    return {"turns": refined, "native_turns": len(turns), "refined_accepted": accepted, "refined_reason": reason,
            "windows": [(0, len(samples) * 1000 // SR)]}


def dump_window(dump_dir: Path | None, stem: str, k: int, start: int, end: int, turns, measured):
    """Save SD turns and real clean-window vectors so C2/global variants can be replayed offline."""
    if dump_dir is None:
        return
    import numpy as np
    dump_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dump_dir / f"{stem}-w{k:03d}.npz", start_end=np.array([start, end], dtype=np.int64),
                        turns=np.array([[t.start_ms, t.end_ms, t.speaker] for t in turns], dtype=np.int64).reshape(-1, 3),
                        windows=np.array([[w.start_ms, w.end_ms, w.speaker] for w in measured], dtype=np.int64).reshape(-1, 3),
                        vectors=np.array([w.embedding for w in measured], dtype=np.float32).reshape(len(measured), -1))


def run_chunked(path: Path, native: Native, config: ChunkConfig, dump_dir: Path | None = None) -> dict:
    reader = WavReader(path)
    duration_ms = reader.duration_ms
    windows = plan_windows(duration_ms, config)
    local_turns, centroids, per_window = [], [], []
    for k, (start, end) in enumerate(windows):
        began = time.perf_counter()
        samples = reader.read(start * 16, (end - start) * 16)
        native.add("read_s", time.perf_counter() - began)
        turns = native.sd(samples)
        refined, measured, accepted, reason = native.refine(samples, turns)
        del samples
        dump_window(dump_dir, path.stem, k, start, end, turns, measured)
        local_turns.append(refined)
        found = window_centroids(k, refined, [w for w in measured])
        centroids += found
        per_window.append({"start_ms": start, "end_ms": end, "native_clusters": len({t.speaker for t in turns}),
                           "refined_clusters": len({t.speaker for t in refined}), "accepted": accepted,
                           "reason": reason, "centroids": len(found)})
        gc.collect()
    reader.close()
    began = time.perf_counter()
    labels = global_clusters(centroids, config)
    mapping = resolve_labels(local_turns, centroids, labels, len(windows))
    cuts = stitch_points(windows, local_turns, config)
    turns = stitch(windows, local_turns, mapping, cuts)
    native.add("global_s", time.perf_counter() - began)
    return {"turns": turns, "windows": windows, "per_window": per_window, "cuts": cuts,
            "centroids": [{"window": c.window, "label": c.label, "speech_ms": c.speech_ms,
                           "vector": [round(x, 7) for x in c.vector]} for c in centroids],
            "local_turns": [[[t.start_ms, t.end_ms, t.speaker] for t in lt] for lt in local_turns],
            "global_labels": labels}


# --------------------------------------------------------------------------- scoring

def fast_der(reference_rows, turns: list[Turn], duration_ms: int, frame_ms: int = 10) -> dict:
    """Frame DER (no collar, overlap counted) with optimal one-to-one mapping."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    frames = -(-duration_ms // frame_ms)
    ref_ids = sorted({r["speaker_id"] for r in reference_rows})
    hyp_ids = sorted({t.speaker for t in turns})
    ref = np.zeros((len(ref_ids), frames), dtype=bool)
    hyp = np.zeros((len(hyp_ids), frames), dtype=bool)
    for r in reference_rows:
        ref[ref_ids.index(r["speaker_id"]), r["start_ms"] // frame_ms:-(-r["end_ms"] // frame_ms)] = True
    for t in turns:
        hyp[hyp_ids.index(t.speaker), t.start_ms // frame_ms:-(-t.end_ms // frame_ms)] = True
    overlap = ref.astype(np.int32) @ hyp.astype(np.int32).T if hyp_ids else np.zeros((len(ref_ids), 0))
    rows, cols = linear_sum_assignment(-overlap) if hyp_ids else ([], [])
    nref, nhyp = ref.sum(0), hyp.sum(0)
    correct = np.zeros(frames, dtype=np.int64)
    for r, c in zip(rows, cols):
        correct += ref[r] & hyp[c]
    total = int(nref.sum())
    miss = int(np.maximum(nref - nhyp, 0).sum())
    fa = int(np.maximum(nhyp - nref, 0).sum())
    conf = int((np.minimum(nref, nhyp) - correct).sum())
    return {"der": (miss + fa + conf) / max(1, total), "miss": miss / max(1, total), "fa": fa / max(1, total),
            "confusion": conf / max(1, total), "frame_ms": frame_ms}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", choices=["legacy", "chunked"])
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--threshold", type=float, default=.3)
    parser.add_argument("--shift", type=float, default=.1)
    parser.add_argument("--tau", type=float, default=.36)
    parser.add_argument("--window-min", type=float, default=10)
    parser.add_argument("--overlap-s", type=float, default=30)
    parser.add_argument("--min-chunk-min", type=float, default=15)
    parser.add_argument("--global-tau", type=float, default=ChunkConfig.global_tau)
    parser.add_argument("--note", default="")
    parser.add_argument("--dump", type=Path, help="save per-window SD turns and clean-window vectors (npz)")
    args = parser.parse_args(argv)
    native = Native(threads=args.threads, threshold=args.threshold, shift=args.shift, tau=args.tau)
    config = ChunkConfig(min_duration_ms=int(args.min_chunk_min * 60000), window_ms=int(args.window_min * 60000),
                         overlap_ms=int(args.overlap_s * 1000), global_tau=args.global_tau)
    began = time.perf_counter()
    cpu_began = time.process_time()
    result = run_legacy(args.audio, native) if args.path == "legacy" else run_chunked(args.audio, native, config, args.dump)
    wall = time.perf_counter() - began
    turns = result.pop("turns")
    with wave.open(str(args.audio), "rb") as handle:
        duration_ms = handle.getnframes() * 1000 // SR
    report = {"path": args.path, "audio": str(args.audio), "duration_ms": duration_ms, "wall_s": wall,
              "process_cpu_s": time.process_time() - cpu_began, "rtf": wall / (duration_ms / 1000),
              "timings": native.timings, "memory": peak_memory(), "threads": args.threads,
              "threshold": args.threshold, "shift": args.shift, "tau": args.tau, "chunk_config": vars(config) if args.path == "chunked" else None,
              "speakers": len({t.speaker for t in turns}), "note": args.note,
              "turns": [[t.start_ms, t.end_ms, t.speaker] for t in turns], **result}
    if args.reference:
        reference = json.loads(args.reference.read_text(encoding="utf-8"))
        report["reference_speakers"] = len({r["speaker_id"] for r in reference["transcript"]})
        report["der"] = fast_der(reference["transcript"], turns, duration_ms, 1 if duration_ms <= 3 * 3600_000 else 10)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    der = report.get("der", {}).get("der")
    print(f"{args.path} {args.audio.name} wall={wall:.1f}s rtf={report['rtf']:.3f} "
          f"peakWS={report['memory']['peak_working_set_mb']:.0f}MB K={report['speakers']}/"
          f"{report.get('reference_speakers')} DER={der if der is None else round(der * 100, 2)}")


if __name__ == "__main__":
    main()
