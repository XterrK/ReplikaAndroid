import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

from tools.eval import prepare_natural_ami as ami


class Response:
    def __init__(self, body, status, headers, url):
        self.body, self.status, self.headers, self.url = body, status, headers, url
        self.read_calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self.url

    def read(self, cap):
        self.read_calls.append(cap)
        return self.body[:cap]


def chunk(name, body):
    return name + struct.pack("<I", len(body)) + body + (b"\0" if len(body) % 2 else b"")


def wav_bytes(*, frames=960000, rate=16000, channels=1, code=1, junk=True, extensible=False):
    fmt = struct.pack("<HHIIHH", 0xfffe if extensible else code, channels, rate, rate * channels * 2, channels * 2, 16)
    if extensible:
        fmt += struct.pack("<HHI", 22, 16, 0) + bytes.fromhex("0100000000001000800000aa00389b71")
    body = b"WAVE" + (chunk(b"JUNK", b"odd") if junk else b"") + chunk(b"fmt ", fmt)
    body += chunk(b"data", b"\x12\x34" * frames * channels)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def rttm(meeting="EN2002a"):
    return (f"SPEAKER {meeting} 1 0.100 1.000 <NA> <NA> A <NA> <NA>\n"
            f"SPEAKER {meeting} 1 0.500 0.250 <NA> <NA> B <NA> <NA>\n"
            f"SPEAKER {meeting} 1 59.900 0.200 <NA> <NA> A <NA> <NA>\n").encode()


def frozen_case(data, identifier="case-a", meeting="EN2002a", channel="Mix-Headset"):
    ref = rttm(meeting)
    return {"id": identifier, "meeting": meeting, "channel": channel,
            "crop_start_ms": 0, "crop_end_ms": 60000,
            "audio_url": "https://example.invalid/" + identifier + ".wav",
            "content_length": len(data), "etag": '"frozen"', "last_modified": "Fri, 27 Jan 2006 14:29:07 GMT",
            "rttm_url": "https://example.invalid/" + meeting + ".rttm",
            "rttm_bytes": len(ref), "rttm_sha256": ami.sha256(ref),
            "reference_group": meeting + "-first60", "reference_speaker_seconds": {"A": 1.1, "B": .25}}


class RangeTests(unittest.TestCase):
    def setUp(self):
        self.data = b"0123456789abcdef"
        self.case = frozen_case(self.data)

    def response(self, *, status=206, body=None, headers=None, url=None):
        valid = {"Content-Range": f"bytes 2-5/{len(self.data)}", "Content-Length": "4",
                 "ETag": self.case["etag"], "Last-Modified": self.case["last_modified"],
                 "Content-Type": "audio/x-wav", "Accept-Ranges": "bytes"}
        valid.update(headers or {})
        return Response(self.data[2:6] if body is None else body, status, valid, url or self.case["audio_url"])

    def test_exact_partial_and_request_condition(self):
        response = self.response()
        requests = []
        def open_request(request, **_):
            requests.append(request)
            return response
        source = ami.RangeSource(self.case, opener=open_request)
        self.assertEqual(source.read(2, 5), b"2345")
        self.assertEqual(response.read_calls, [5])
        self.assertEqual(requests[0].get_header("Range"), "bytes=2-5")
        self.assertEqual(requests[0].get_header("If-match"), '"frozen"')
        self.assertEqual(source.responses[0]["sha256"], ami.sha256(b"2345"))
        self.assertTrue(source.attempts[0]["body_read"])

    def test_200_rejected_before_read_and_recorded(self):
        response = self.response(status=200, body=b"full-file")
        source = ami.RangeSource(self.case, opener=lambda *_a, **_k: response)
        with self.assertRaisesRegex(ValueError, "requires 206"):
            source.read(2, 5)
        self.assertEqual(response.read_calls, [])
        self.assertEqual(source.responses, [])
        self.assertEqual(source.attempts[0]["status"], 200)
        self.assertFalse(source.attempts[0]["body_read"])

    def test_header_identity_failures_never_read(self):
        for changed in ({"Content-Range": "bytes 2-5/999"}, {"Content-Range": "bytes 1-4/16"},
                        {"ETag": '"changed"'}, {"Last-Modified": "changed"}, {"Content-Length": "8"},
                        {"Content-Encoding": "gzip"}, {"Content-Type": "text/html"}):
            with self.subTest(changed=changed):
                response = self.response(headers=changed)
                source = ami.RangeSource(self.case, opener=lambda *_a, **_k: response)
                with self.assertRaises(ValueError):
                    source.read(2, 5)
                self.assertEqual(response.read_calls, [])
        response = self.response(url="https://elsewhere.invalid/audio")
        with self.assertRaisesRegex(ValueError, "redirected"):
            ami.RangeSource(self.case, opener=lambda *_a, **_k: response).read(2, 5)
        self.assertEqual(response.read_calls, [])

    def test_truncated_and_oversized_bodies_recorded(self):
        for body in (b"23", b"23456"):
            with self.subTest(body=body):
                response = self.response(body=body)
                source = ami.RangeSource(self.case, opener=lambda *_a, **_k: response)
                with self.assertRaisesRegex(ValueError, "Truncated or oversized"):
                    source.read(2, 5)
                self.assertEqual(source.attempts[0]["sha256"], ami.sha256(body))
                self.assertEqual(source.responses, [])

    def test_bounds_rejected_before_network(self):
        def forbidden(*_a, **_k):
            self.fail("network must not run")
        source = ami.RangeSource(self.case, opener=forbidden)
        for bounds in ((-1, 3), (3, 2), (0, 16), (False, 1), (0, 3.0)):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                source.read(*bounds)
        case = dict(self.case, content_length=ami.MAX_RANGE_BYTES + 2)
        with self.assertRaises(ValueError):
            ami.RangeSource(case, opener=forbidden).read(0, ami.MAX_RANGE_BYTES)


class WavAndRttmTests(unittest.TestCase):
    def test_actual_chunk_offsets_and_odd_padding(self):
        data, reads = wav_bytes(frames=4), []
        def read(a, b):
            reads.append((a, b))
            return data[a:b+1]
        info, chunks = ami.parse_wav_ranges(read, len(data))
        self.assertEqual(info.data_offset, 56)
        self.assertEqual(info.source_frames, 4)
        self.assertEqual(data[info.data_offset:], b"\x12\x34" * 4)
        self.assertEqual([bytes.fromhex(c["id_hex"]) for c in chunks], [b"JUNK", b"fmt ", b"data"])
        self.assertNotIn((20, 22), reads)  # skipped JUNK is not downloaded

    def test_extensible_pcm_and_invalid_formats(self):
        data = wav_bytes(frames=2, extensible=True)
        info, _ = ami.parse_wav_ranges(lambda a, b: data[a:b+1], len(data))
        self.assertEqual(info.format_code, 0xfffe)
        for kwargs in ({"code": 3}, {"rate": 8000}, {"channels": 2}):
            with self.subTest(kwargs=kwargs):
                data = wav_bytes(frames=2, **kwargs)
                with self.assertRaisesRegex(ValueError, "PCM16 mono16kHz"):
                    ami.parse_wav_ranges(lambda a, b: data[a:b+1], len(data))

    def test_riff_bounds_and_header_budget(self):
        data = wav_bytes(frames=2)
        with self.assertRaisesRegex(ValueError, "RIFF length"):
            ami.parse_wav_ranges(lambda a, b: data[a:b+1], len(data) + 1)
        malformed = b"RIFF" + struct.pack("<I", 20) + b"WAVE" + b"JUNK" + struct.pack("<I", 100) + b"00000000"
        with self.assertRaisesRegex(ValueError, "chunk exceeds"):
            ami.parse_wav_ranges(lambda a, b: malformed[a:b+1], len(malformed))
        body = b"WAVE" + chunk(b"JUNK", bytes(ami.MAX_HEADER_OFFSET)) + chunk(b"fmt ", bytes(16))
        data = b"RIFF" + struct.pack("<I", len(body)) + body
        with self.assertRaisesRegex(ValueError, "oversized WAV header"):
            ami.parse_wav_ranges(lambda a, b: data[a:b+1], len(data))

    def test_decimal_clip_shift_half_up_and_overlap(self):
        raw = ("SPEAKER X 1 0.5 1.0 <NA> <NA> A <NA> <NA>\n"
               "SPEAKER X 1 1.0005 0.001 <NA> <NA> B <NA> <NA>\n"
               "SPEAKER X 1 1.9995 2 <NA> <NA> A <NA> <NA>\n"
               "SPEAKER X 1 4 1 <NA> <NA> outside <NA> <NA>\n").encode()
        ref, meta = ami.rttm_reference(raw, "X", 1000, 2000)
        self.assertEqual(ref["transcript"], [
            {"speaker_id": "A", "start_ms": 0, "end_ms": 500, "text": ""},
            {"speaker_id": "B", "start_ms": 1, "end_ms": 2, "text": ""}])
        self.assertEqual(meta["submillisecond_rows_dropped_after_rounding"], 1)
        self.assertEqual(meta["decimal_speaker_seconds"], {"A": "0.5005", "B": "0.0010"})

    def test_reference_rejects_wrong_identity_and_nonfinite(self):
        for raw in (b"SPEAKER wrong 1 0 1 <NA> <NA> A <NA> <NA>",
                    b"SPEAKER X 2 0 1 <NA> <NA> A <NA> <NA>",
                    b"SPEAKER X 1 NaN 1 <NA> <NA> A <NA> <NA>",
                    b"SPEAKER X 1 0 Infinity <NA> <NA> A <NA> <NA>",
                    b"SPEAKER X 1 -1 1 <NA> <NA> A <NA> <NA>",
                    b"SPEAKER X 1 0 0 <NA> <NA> A <NA> <NA>", b""):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                ami.rttm_reference(raw, "X", 0, 60000)

    def test_canonical_exact_frame_count(self):
        pcm = b"\0\x01" * 960000
        raw = ami.canonical_wav(pcm)
        with wave.open(io.BytesIO(raw)) as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()), (1, 2, 16000, 960000))
            self.assertEqual(wav.readframes(960001), pcm)
        with self.assertRaises(ValueError):
            ami.canonical_wav(pcm[:-2])


class PreparationTests(unittest.TestCase):
    def fixture(self, root, *, ignore_range=False):
        data = wav_bytes()
        cases = [frozen_case(data), frozen_case(data, "case-array", channel="Array1-01"),
                 frozen_case(data, "case-c", meeting="EN2002c")]
        freeze = {"status": "METADATA_ONLY_FROZEN_BEFORE_AUDIO_AND_INFERENCE", "cases": cases,
                  "license": {"ami": "CC BY 4.0"}, "training_overlap": "unknown", "related_samples": "same participants"}
        path = root / "freeze.json"
        path.write_bytes(ami.json_bytes(freeze))
        license_raw = b"test-license"
        license_spec = {"url": "https://example.invalid/LICENSE", "bytes": len(license_raw), "sha256": ami.sha256(license_raw)}
        text = {c["rttm_url"]: rttm(c["meeting"]) for c in cases}
        text[license_spec["url"]] = license_raw
        audio = {c["audio_url"]: c for c in cases}
        responses, requests = [], []
        def opener(request, **_):
            url = request.full_url
            requests.append(request)
            if url in text:
                response = Response(text[url], 200, {}, url)
            else:
                case = audio[url]
                a, b = map(int, request.get_header("Range")[6:].split("-"))
                headers = {"Content-Range": f"bytes {a}-{b}/{len(data)}", "Content-Length": str(b-a+1),
                           "ETag": case["etag"], "Last-Modified": case["last_modified"], "Content-Type": "audio/x-wav"}
                response = Response(data if ignore_range else data[a:b+1], 200 if ignore_range else 206, headers, url)
            responses.append(response)
            return response
        return path, license_spec, opener, requests, responses

    def test_full_mock_preparation_preserves_pins_groups_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, spec, opener, requests, _ = self.fixture(root)
            frozen_before = path.read_bytes()
            meta, audio = root / "meta", root / "audio"
            with patch.object(ami, "LICENSE_SPEC", spec):
                manifest, provenance = ami.prepare(path, meta, audio, opener=opener)
            self.assertEqual(path.read_bytes(), frozen_before)
            self.assertEqual((manifest["status"], len(manifest["files"])), ("PREPARED", 3))
            self.assertFalse(manifest["new_model_inference"])
            self.assertEqual(manifest["inference_policy"], {"expected_speakers": -1, "reference_inputs": []})
            self.assertEqual(manifest["files"][0]["reference_group"], manifest["files"][1]["reference_group"])
            self.assertNotEqual(manifest["files"][0]["reference_group"], manifest["files"][2]["reference_group"])
            for case in provenance["cases"]:
                self.assertIsNone(case["whole_source_audio_sha256"])
                self.assertEqual(case["source_header"]["data_offset"], 56)
                self.assertEqual(case["pcm_crop_frames"], 960000)
                self.assertEqual(len(case["http_partial_responses"]), 6)
                self.assertEqual(case["status"], "PREPARED")
            for case in manifest["files"]:
                self.assertEqual(ami.sha256((audio / case["audio"]).read_bytes()), case["audio_sha256"])
                ref = json.loads((meta / case["reference"]).read_bytes())
                self.assertTrue(all(row["text"] == "" for row in ref["transcript"]))
            self.assertEqual(sum(request.full_url.endswith("EN2002a.rttm") for request in requests), 1)
            self.assertEqual(provenance["manifest_sha256"], ami.sha256((meta / "manifest.json").read_bytes()))
            with self.assertRaises(FileExistsError):
                ami.prepare(path, meta, audio, opener=opener)

    def test_ignored_range_preserves_failure_without_body_or_full_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, spec, opener, requests, responses = self.fixture(root, ignore_range=True)
            meta, audio = root / "meta", root / "audio"
            with patch.object(ami, "LICENSE_SPEC", spec), self.assertRaisesRegex(ValueError, "requires 206"):
                ami.prepare(path, meta, audio, opener=opener)
            failure = json.loads((meta / "preparation-failure.json").read_bytes())
            self.assertFalse(failure["automatic_full_file_fallback"])
            self.assertFalse(failure["new_model_inference"])
            self.assertFalse(failure["audio_fetched"])
            self.assertTrue(failure["audio_fetch_attempted"])
            self.assertEqual(failure["cases"][0]["http_range_attempts"][0]["status"], 200)
            self.assertEqual(responses[-1].read_calls, [])
            self.assertEqual(len(requests), 2)  # license, first12-byte audio request
            self.assertFalse((meta / "manifest.json").exists())
            self.assertEqual(list(audio.rglob("*.wav")), [])

    def test_pinned_text_integrity_and_repo_audio_guard(self):
        response = Response(b"bad", 200, {}, "https://example.invalid/x")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            ami.fetch_pinned(response.url, 3, ami.sha256(b"yes"), opener=lambda *_a, **_k: response)
        self.assertEqual(response.read_calls, [4])
        with self.assertRaisesRegex(ValueError, "outside repository"):
            ami.prepare(Path("absent-freeze"), Path("absent-meta"), ami.ROOT / "forbidden-audio")


if __name__ == "__main__":
    unittest.main()
