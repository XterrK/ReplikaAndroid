#!/usr/bin/env python3
"""Create original CC0 tones for Android import/codec checks, never ASR quality.

Use a fresh --output directory. FFmpeg is an explicit executable or is found on
PATH; the manifest records its version/hash but never a machine-specific path.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import wave


CASES = (
    ("wav-08k-mono", "wav", 8000, 1, "pcm_s16le", ()),
    ("wav-16k-mono", "wav", 16000, 1, "pcm_s16le", ()),
    ("wav-44k-stereo", "wav", 44100, 2, "pcm_s16le", ()),
    ("wav-48k-stereo", "wav", 48000, 2, "pcm_s16le", ()),
    ("mp3-16k-mono", "mp3", 16000, 1, "libmp3lame", ("-b:a", "64k")),
    ("mp3-44k-stereo", "mp3", 44100, 2, "libmp3lame", ("-b:a", "128k")),
    ("m4a-16k-mono", "m4a", 16000, 1, "aac", ("-b:a", "48k", "-movflags", "+faststart")),
    ("m4a-48k-stereo", "m4a", 48000, 2, "aac", ("-b:a", "128k", "-movflags", "+faststart")),
    ("aac-adts-16k-mono", "aac", 16000, 1, "aac", ("-b:a", "64k", "-f", "adts")),
    ("ogg-opus-48k-mono", "ogg", 48000, 1, "libopus", ("-b:a", "32k", "-f", "ogg")),
    ("ogg-opus-48k-stereo", "ogg", 48000, 2, "libopus", ("-b:a", "64k", "-f", "ogg")),
    ("flac-44k-mono", "flac", 44100, 1, "flac", ()),
    ("flac-48k-stereo", "flac", 48000, 2, "flac", ()),
)
DURATION_MS = 3000
AMPLITUDE = 0.32
FREQUENCIES_HZ = (440, 880)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(128 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tone_wav(path: Path, rate: int, channels: int) -> None:
    """200 ms silence at each edge; L=440 Hz, R=880 Hz; 5 ms fades."""
    samples = rate * DURATION_MS // 1000
    pcm = bytearray()
    for frame in range(samples):
        seconds = frame / rate
        envelope = max(0.0, min(1.0, (seconds - 0.2) / 0.005, (2.8 - seconds) / 0.005))
        for channel in range(channels):
            value = AMPLITUDE * envelope * math.sin(2 * math.pi * FREQUENCIES_HZ[channel] * seconds)
            pcm.extend(struct.pack("<h", round(value * 32767)))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm)


def amplitude(samples: tuple[int, ...], hz: int) -> float:
    # A whole interior second avoids packet priming and fractional FFT bins.
    interior = samples[16000:32000]
    real = sum(value / 32768 * math.cos(2 * math.pi * hz * i / 16000) for i, value in enumerate(interior))
    imag = sum(value / 32768 * math.sin(2 * math.pi * hz * i / 16000) for i, value in enumerate(interior))
    return 2 * math.hypot(real, imag) / len(interior)


def generate(ffmpeg: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError("Use a fresh output directory; prior fixtures/evidence must remain intact")
    version = subprocess.run([str(ffmpeg), "-version"], check=True, capture_output=True, text=True).stdout.splitlines()[0]
    output.mkdir(parents=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix="plan19-import-masters-") as temporary:
        masters = Path(temporary)
        for identity, extension, rate, channels, codec, options in CASES:
            master = masters / f"{identity}.wav"
            tone_wav(master, rate, channels)
            name = f"p19-{identity}.{extension}"
            destination = output / name
            if extension == "wav":
                shutil.copyfile(master, destination)
            else:
                command = [str(ffmpeg), "-n", "-hide_banner", "-loglevel", "error", "-i", str(master),
                           "-map_metadata", "-1", "-vn", "-c:a", codec, "-ar", str(rate), "-ac", str(channels),
                           "-fflags", "+bitexact", "-flags:a", "+bitexact", *options, str(destination)]
                subprocess.run(command, check=True, capture_output=True)
            decoded = subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(destination),
                                      "-vn", "-f", "s16le", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
                                     check=True, capture_output=True).stdout
            if len(decoded) % 2:
                raise ValueError(f"Odd host sanity PCM length: {name}")
            values = struct.unpack(f"<{len(decoded) // 2}h", decoded)
            duration = len(values) * 1000 / 16000
            tolerance = 3 if extension in ("wav", "flac") else 250
            spectrum = {str(hz): amplitude(values, hz) for hz in (440, 880, 1300)}
            if abs(duration - DURATION_MS) > tolerance or spectrum["440"] < 0.06:
                raise ValueError(f"Host generation sanity failed: {name}: {duration}, {spectrum}")
            if channels == 2 and (spectrum["880"] < 0.06 or not 0.55 < spectrum["440"] / spectrum["880"] < 1.8):
                raise ValueError(f"Host stereo generation sanity failed: {name}: {spectrum}")
            rows.append({
                "id": identity, "name": name, "bytes": destination.stat().st_size, "sha256": sha(destination),
                "format": extension, "encoder": codec, "sample_rate": rate, "channels": channels,
                "expected_duration_ms": DURATION_MS, "duration_tolerance_ms": tolerance,
                "tone_hz": list(FREQUENCIES_HZ[:channels]), "tone_amplitude_per_source_channel": AMPLITUDE,
                "edge_silence_ms": 200, "host_sanity": {
                    "scope": "FFmpeg generation sanity only; not Android/ASR/quality acceptance",
                    "decoded_16k_mono_samples": len(values), "decoded_pcm16_sha256": hashlib.sha256(decoded).hexdigest(),
                    "spectral_amplitudes": spectrum,
                },
            })
    manifest = {
        "schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "license": "CC0-1.0: original mathematical tones generated for this project; no speech or third-party recordings",
        "scope": "Import/codec/channel/resampling checks; no model inference and no speech-quality claim",
        "generator": "tools/create_plan19_import_fixtures.py", "generator_sha256": sha(Path(__file__)),
        "ffmpeg": {"version": version, "executable_sha256": sha(ffmpeg)},
        "files": rows,
        "suggested_picker_fixtures": ["p19-wav-08k-mono.wav", "p19-ogg-opus-48k-stereo.ogg", "p19-flac-44k-mono.flac"],
    }
    (output / "fixtures.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"), help="FFmpeg executable; otherwise use PATH")
    parser.add_argument("--output", required=True, type=Path, help="New directory; never overwrite existing fixtures")
    arguments = parser.parse_args()
    if not arguments.ffmpeg:
        parser.error("FFmpeg is not on PATH; pass --ffmpeg with an available executable")
    executable = shutil.which(arguments.ffmpeg) or arguments.ffmpeg
    manifest = generate(Path(executable).resolve(strict=True), arguments.output)
    print(json.dumps({"files": len(manifest["files"]), "bytes": sum(row["bytes"] for row in manifest["files"]),
                      "manifest_sha256": sha(arguments.output / "fixtures.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
