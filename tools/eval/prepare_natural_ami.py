#!/usr/bin/env python3
"""Prepare only the three frozen AMI diagnostic crops, without neural inference.

Audio stays outside Git. HTTP200 is rejected before its body is read: there is
no automatic whole-file/archive fallback. Every audio request must prove an
exact206 range, frozen total length/ETag, and bounded body length. RIFF chunks
are parsed on their actual offsets, including odd-byte padding. Whole-source
audio SHA remains null because only headers and selected PCM frames are read.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FREEZE = ROOT / "artifacts/test-results/step-04/natural-probe-freeze.json"
DEFAULT_METADATA = ROOT / "benchmark/eval-natural-ami"
MAX_HEADER_OFFSET = 1024 * 1024
MAX_FMT_BYTES = 65536
MAX_CHUNKS = 64
MAX_RANGE_BYTES = 2 * 1024 * 1024
LICENSE_SPEC = {
    "url": "https://raw.githubusercontent.com/pyannote/AMI-diarization-setup/67c2d539286e89f68952d5dcf83912bd9f01dfae/LICENSE",
    "bytes": 11357,
    "sha256": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
}


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _name(value):
    if not isinstance(value, str) or value in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError("Unsafe metadata ID")
    return value


class RangeSource:
    def __init__(self, frozen, *, opener=urllib.request.urlopen):
        self.case, self.opener, self.responses, self.attempts = frozen, opener, [], []

    def read(self, start, end):
        if (type(start) is not int or type(end) is not int or not 0 <= start <= end < self.case["content_length"]
                or end - start + 1 > MAX_RANGE_BYTES):
            raise ValueError("Requested audio range exceeds frozen bounds/read cap")
        wanted = end - start + 1
        request = urllib.request.Request(self.case["audio_url"], headers={
            "Range": f"bytes={start}-{end}", "If-Match": self.case["etag"],
            "Accept-Encoding": "identity", "User-Agent": "REPLIKA-AMI-diagnostic-preparation/1"})
        attempt = {"start_byte": start, "end_byte_inclusive": end, "body_read": False}
        self.attempts.append(attempt)
        with self.opener(request, timeout=30) as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
            kept_headers = {key: headers.get(key) for key in ("content-range", "content-length", "content-type", "etag", "last-modified", "accept-ranges", "content-encoding")}
            attempt.update(status=response.status, url=response.geturl(), headers=kept_headers)
            # Do not read even one body byte if a server ignores Range.
            if response.status != 206:
                raise ValueError(f"Audio Range requires 206, received {response.status}; full-file fallback prohibited")
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", headers.get("content-range", ""))
            if not match or tuple(map(int, match.groups())) != (start, end, self.case["content_length"]):
                raise ValueError("Content-Range differs from requested/frozen source bounds")
            if headers.get("etag") != self.case["etag"]:
                raise ValueError("Frozen audio ETag changed or absent")
            if self.case.get("last_modified") and headers.get("last-modified") != self.case["last_modified"]:
                raise ValueError("Frozen audio Last-Modified changed or absent")
            if headers.get("content-length") is not None and int(headers["content-length"]) != wanted:
                raise ValueError("Range Content-Length differs")
            if headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("Encoded audio range is unsupported")
            mime = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if mime not in ("audio/x-wav", "audio/wav", "audio/wave", "audio/vnd.wave", "application/octet-stream"):
                raise ValueError("Unexpected audio MIME type")
            if response.geturl() != self.case["audio_url"]:
                raise ValueError("Audio URL redirected outside frozen identity")
            raw = response.read(wanted + 1)
            attempt.update(body_read=True, body_bytes=len(raw), sha256=sha256(raw))
            if len(raw) != wanted:
                raise ValueError("Truncated or oversized range body")
            self.responses.append({"start_byte": start, "end_byte_inclusive": end, "body_bytes": len(raw),
                "sha256": sha256(raw), "status": 206, "url": response.geturl(),
                "headers": kept_headers})
            return raw


@dataclass(frozen=True)
class WavInfo:
    source_bytes: int
    riff_bytes: int
    format_code: int
    channels: int
    sample_rate: int
    bits_per_sample: int
    block_align: int
    data_offset: int
    data_bytes: int
    source_frames: int


def parse_wav_ranges(read, source_bytes):
    """Parse bounded RIFF headers through read(start,end-inclusive), not audio."""
    first = read(0, 11)
    if first[:4] != b"RIFF" or first[8:12] != b"WAVE":
        raise ValueError("Only little-endian RIFF/WAVE is supported")
    riff_end = struct.unpack_from("<I", first, 4)[0] + 8
    if riff_end != source_bytes or riff_end < 20:
        raise ValueError("RIFF length differs from frozen full-source length")
    position, fmt, chunks = 12, None, []
    for _ in range(MAX_CHUNKS):
        if position > MAX_HEADER_OFFSET or position + 8 > riff_end:
            raise ValueError("Missing/oversized WAV header before data")
        header = read(position, position + 7)
        identifier, size = header[:4], struct.unpack_from("<I", header, 4)[0]
        payload = position + 8
        if payload + size > riff_end:
            raise ValueError("WAV chunk exceeds declared source length")
        chunks.append({"id_hex": identifier.hex(), "header_offset": position, "payload_bytes": size})
        if identifier == b"fmt ":
            if fmt is not None or not 16 <= size <= MAX_FMT_BYTES:
                raise ValueError("Duplicate/invalid fmt chunk")
            fmt = read(payload, payload + size - 1)
        elif identifier == b"data":
            if fmt is None:
                raise ValueError("WAV data precedes a valid fmt chunk")
            code, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", fmt)
            pcm = code == 1
            if code == 0xfffe:
                pcm_guid = bytes.fromhex("0100000000001000800000aa00389b71")
                pcm = (len(fmt) >= 40 and struct.unpack_from("<H", fmt, 16)[0] >= 22
                       and struct.unpack_from("<H", fmt, 18)[0] == 16 and fmt[24:40] == pcm_guid)
            if not pcm or channels != 1 or rate != 16000 or bits != 16 or align != 2 or byte_rate != 32000:
                raise ValueError("Frozen crop requires PCM16 mono16kHz without resampling/downmixing")
            if size % align:
                raise ValueError("PCM data has an incomplete frame")
            return WavInfo(source_bytes, riff_end, code, channels, rate, bits, align, payload, size, size // align), chunks
        position = payload + size + (size % 2)
    raise ValueError("WAV chunk-count limit exceeded")


def fetch_pinned(url, size, expected_sha, *, opener=urllib.request.urlopen):
    if type(size) is not int or not 0 < size <= 1024 * 1024:
        raise ValueError("Pinned text exceeds metadata cap")
    request = urllib.request.Request(url, headers={"User-Agent": "REPLIKA-AMI-diagnostic-preparation/1", "Accept-Encoding": "identity"})
    with opener(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError("Pinned metadata GET failed")
        raw = response.read(size + 1)
    if len(raw) != size or sha256(raw) != expected_sha:
        raise ValueError("Pinned metadata size/SHA256 mismatch")
    return raw


def rttm_reference(raw, meeting, start_ms, end_ms):
    """Decimal clipping on source clock, shift, then half-up integer milliseconds."""
    if (type(start_ms) is not int or type(end_ms) is not int or not 0 <= start_ms < end_ms):
        raise ValueError("Invalid frozen crop clock")
    left, right = Decimal(start_ms) / 1000, Decimal(end_ms) / 1000
    rows, seconds, dropped = [], {}, 0
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 10 or fields[0] != "SPEAKER" or fields[1] != meeting or fields[2] != "1" or fields[7] == "<NA>":
            raise ValueError(f"Invalid RTTM identity/shape at line{number}")
        try:
            start, duration = Decimal(fields[3]), Decimal(fields[4])
        except InvalidOperation as exc:
            raise ValueError("Invalid RTTM decimal") from exc
        if not start.is_finite() or not duration.is_finite() or start < 0 or duration <= 0:
            raise ValueError("Invalid RTTM start/duration")
        clipped_start, clipped_end = max(start, left), min(start + duration, right)
        if clipped_end <= clipped_start:
            continue
        speaker = fields[7]
        seconds[speaker] = seconds.get(speaker, Decimal(0)) + clipped_end - clipped_start
        a = int(((clipped_start - left) * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        b = int(((clipped_end - left) * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if b <= a:
            dropped += 1
            continue
        rows.append({"speaker_id": speaker, "start_ms": a, "end_ms": b, "text": ""})
    rows.sort(key=lambda row: (row["start_ms"], row["end_ms"], row["speaker_id"]))
    if not rows:
        raise ValueError("Frozen crop contains no reference speech")
    return {"transcript": rows}, {"decimal_speaker_seconds": {k: str(v) for k, v in sorted(seconds.items())},
        "submillisecond_rows_dropped_after_rounding": dropped,
        "timing_policy": "Decimal source seconds; clip to crop first, subtract crop start, ROUND_HALF_UP milliseconds; preserve IDs/overlap/whole-crop silence"}


def canonical_wav(pcm):
    if len(pcm) != 960000 * 2:
        raise ValueError("Exactly960000 PCM16 frames required")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(pcm)
    return output.getvalue()


NOTICE = """# AMI natural-meeting diagnostic attribution

AMI Meeting Corpus signals and manual annotation release1.6.2: CC BY4.0,
according to https://groups.inf.ed.ac.uk/ami/download/ (2017 license update).
Attribute the AMI consortium and J. Carletta et al., The AMI Meeting Corpus: A
Pre-announcement (2006). The selected EN2002a/c meetings are naturally occurring
project discussions; speech references derive from manual word annotation.

RTTM benchmark setup: BUT Speech@FIT / F. Landini, J. Profant, M. Diez and
L. Burget, AMI-diarization-setup; pin/source URLs and SHA256 are in provenance.
Retain the accompanying Apache2.0 setup LICENSE and cite the benchmark setup.

Changes: first60-second PCM crop only; RTTM intervals clipped to that crop and
converted to integer milliseconds. No ASR, VAD, voice replacement or annotation
correction. Gold has blank text; this is speaker-diarization research only,
not English ASR task E. Audio stays outside Git/APK.

EN2002a headset/array are the same conversation/ground truth. EN2002a/c share
participants; this is not a speaker-disjoint sample. Candidate model training
overlap is unknown. This small diagnostic does not replace the original dev or
regression gates or establish general natural-dialogue performance.
"""


def prepare(freeze_path, metadata_root, audio_root, *, opener=urllib.request.urlopen):
    freeze_path, metadata_root, audio_root = map(Path, (freeze_path, metadata_root, audio_root))
    if audio_root.resolve() == ROOT or ROOT in audio_root.resolve().parents:
        raise ValueError("Research audio must stay outside repository")
    if metadata_root.exists() or audio_root.exists():
        raise FileExistsError("Use fresh metadata/audio roots; prior evidence is never overwritten")
    frozen_raw = freeze_path.read_bytes()
    frozen = json.loads(frozen_raw)
    cases = frozen["cases"]
    if (frozen.get("status") != "METADATA_ONLY_FROZEN_BEFORE_AUDIO_AND_INFERENCE" or len(cases) != 3
            or len({_name(c["id"]) for c in cases}) != 3
            or any(c["crop_start_ms"] != 0 or c["crop_end_ms"] != 60000 for c in cases)):
        raise ValueError("Exactly the three metadata-frozen first60s cases are required")
    metadata_root.mkdir(parents=True); audio_root.mkdir(parents=True)
    provenance = {"schema_version": 1, "status": "PREPARING", "started_at": datetime.now(timezone.utc).isoformat(),
                  "freeze_sha256": sha256(frozen_raw), "freeze_status": frozen["status"], "audio_fetched": False,
                  "audio_fetch_attempted": False,
                  "new_model_inference": False, "whole_source_audio_sha256": None, "cases": []}
    try:
        write_new(metadata_root / "selection-freeze.json", frozen_raw)
        write_new(metadata_root / "ATTRIBUTION.md", NOTICE.encode("utf-8"))
        license_raw = fetch_pinned(LICENSE_SPEC["url"], LICENSE_SPEC["bytes"], LICENSE_SPEC["sha256"], opener=opener)
        write_new(metadata_root / "sources/AMI-diarization-setup-LICENSE", license_raw)
        provenance["setup_license"] = LICENSE_SPEC
        text_cache, files = {}, []
        for case in cases:
            identifier, meeting = _name(case["id"]), _name(case["meeting"])
            source = RangeSource(case, opener=opener)
            item = {"id": identifier, "meeting": meeting, "channel": case["channel"], "source_http_url": case["audio_url"],
                    "whole_source_audio_sha256": None, "status": "PREPARING", "http_partial_responses": source.responses,
                    "http_range_attempts": source.attempts}
            provenance["cases"].append(item)
            provenance["audio_fetch_attempted"] = True
            info, chunks = parse_wav_ranges(source.read, case["content_length"])
            provenance["audio_fetched"] = True
            if info.source_frames < 960000:
                raise ValueError("Source PCM is shorter than the frozen60s crop")
            pcm = source.read(info.data_offset, info.data_offset + 960000 * info.block_align - 1)
            wav = canonical_wav(pcm)
            key = (case["rttm_url"], case["rttm_sha256"])
            if key not in text_cache:
                raw = fetch_pinned(case["rttm_url"], case["rttm_bytes"], case["rttm_sha256"], opener=opener)
                text_cache[key] = raw
                write_new(metadata_root / "sources" / (meeting + ".rttm"), raw)
            reference, reference_meta = rttm_reference(text_cache[key], meeting, 0, 60000)
            expected = case["reference_speaker_seconds"]
            observed = reference_meta["decimal_speaker_seconds"]
            if set(expected) != set(observed) or any(abs(Decimal(observed[k]) - Decimal(str(expected[k]))) > Decimal(".001") for k in expected):
                raise ValueError("RTTM crop differs from metadata-frozen speaker/time selection")
            audio = "diagnostic/" + identifier + ".wav"
            ref = "references/" + identifier + ".json"
            reference_raw = json_bytes(reference)
            write_new(audio_root / audio, wav)
            write_new(metadata_root / ref, reference_raw)
            item.update({"source_bytes": info.source_bytes, "status": "PREPARED",
                    "source_header": asdict(info), "riff_chunks_before_data": chunks, "http_partial_responses": source.responses,
                    "pcm_crop_frames": 960000, "pcm_crop_sha256": sha256(pcm), "canonical_crop_sha256": sha256(wav),
                    "reference_sha256": sha256(reference_raw), "rttm_url": case["rttm_url"], "rttm_sha256": case["rttm_sha256"],
                    "reference_metadata": reference_meta, "source_crop_start_ms": 0, "source_crop_end_ms": 60000})
            files.append({"id": identifier, "split": "diagnostic", "language": "en", "audio": audio, "reference": ref,
                "duration_ms": 60000, "sample_rate": 16000, "channels": 1, "format": "PCM_16",
                "audio_sha256": sha256(wav), "reference_sha256": sha256(reference_raw), "reference_speaker_count": len(observed),
                "reference_speaker_count_role": "scoring only; never input to automatic inference",
                "reference_group": case["reference_group"], "paired_session": meeting, "related_participants_group": "AMI-EN2002",
                "kind": "natural_meeting_first60s", "channel": case["channel"],
                "timing_scope": "Manual-word-derived RTTM speech intervals, clipped on original sample clock; not word-alignment/ASR acceptance",
                "allowed_task": "speaker_diarization_only", "whole_source_audio_sha256": None})
        manifest = {"schema_version": 1, "status": "PREPARED", "audio_fetch_completed": True, "new_model_inference": False,
                    "freeze_sha256": sha256(frozen_raw), "files": files, "license": frozen["license"],
                    "training_overlap": frozen["training_overlap"], "related_samples": frozen["related_samples"],
                    "total_audio_ms": 180000, "unique_meeting_crop_ms": 120000,
                    "scope": "Separate natural-meeting diarization diagnostic only; paired channels/related participants, not a new dev/holdout gate or English ASR task E",
                    "inference_policy": {"expected_speakers": -1, "reference_inputs": []}}
        provenance.update(status="PREPARED", completed_at=datetime.now(timezone.utc).isoformat(),
                          manifest_sha256=sha256(json_bytes(manifest)), freeze_unchanged=freeze_path.read_bytes() == frozen_raw)
        if not provenance["freeze_unchanged"]:
            raise ValueError("Source selection freeze changed during preparation")
        write_new(metadata_root / "manifest.json", json_bytes(manifest))
        write_new(metadata_root / "provenance.json", json_bytes(provenance))
        return manifest, provenance
    except Exception as exc:
        provenance["audio_fetched"] = any(attempt.get("body_read", False)
            for case in provenance["cases"] for attempt in case["http_range_attempts"])
        provenance.update(status="FAILED", error=f"{type(exc).__name__}: {exc}",
                          completed_at=datetime.now(timezone.utc).isoformat(), automatic_full_file_fallback=False)
        write_new(metadata_root / "preparation-failure.json", json_bytes(provenance))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--metadata-root", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--audio-root", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest, provenance = prepare(args.freeze, args.metadata_root, args.audio_root)
    print(json.dumps({"status": provenance["status"], "cases": len(manifest["files"]),
                      "audio_root": str(args.audio_root), "metadata_root": str(args.metadata_root),
                      "manifest_sha256": provenance["manifest_sha256"], "new_model_inference": False}))


if __name__ == "__main__":
    main()
