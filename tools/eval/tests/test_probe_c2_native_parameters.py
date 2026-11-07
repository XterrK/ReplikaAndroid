"""Final C2 probe contracts with fake NN objects; no model inference or ADB."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import gc
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest import mock
import weakref

import numpy as np
from tools.eval import probe_c2_native_parameters as p


def protocol():
    return p.load(p.REPO / "configs/eval/c2-final-native-parameters-v1.json")


def fake_sdk(*, fail_compute=False):
    library=NS(__version__="2.0.1", configs=[], weak_resources=[], calls=[])
    for name in ("OfflineSpeakerDiarizationConfig","OfflineSpeakerSegmentationModelConfig",
        "OfflineSpeakerSegmentationPyannoteModelConfig","SpeakerEmbeddingExtractorConfig","FastClusteringConfig"):
        setattr(library,name,lambda **kwargs:NS(**kwargs))
    class Stream:
        def accept_waveform(self,rate,samples):
            library.calls.append(("waveform",rate,len(samples)))
        def input_finished(self):pass
    class Diarizer:
        def __init__(self,config):
            library.configs.append(config);library.weak_resources.append(weakref.ref(self))
        def process(self,samples):
            library.calls.append(("sd",len(samples)))
            return NS(sort_by_start_time=lambda:[NS(start=0.,end=3.,speaker=9)])
    class Extractor:
        dim=512
        def __init__(self,config):
            self.config=config;library.weak_resources.append(weakref.ref(self))
        def create_stream(self):
            stream=Stream();library.weak_resources.append(weakref.ref(stream));return stream
        def is_ready(self,stream):return True
        def compute(self,stream):
            library.calls.append(("compute",))
            if fail_compute:raise RuntimeError("fake NN compute failure")
            return [1.]+[0.]*511
    library.OfflineSpeakerDiarization=Diarizer
    library.SpeakerEmbeddingExtractor=Extractor
    return library


class ProbeContractTest(unittest.TestCase):
    def test_exact_four_global_alternatives_and_no_fixed_k_or_crossgrid(self):
        for profile in p.FRESH_PROFILES:
            selected=p.validate_protocol(protocol(),profile)
            self.assertTrue(selected["inference"])
        for bad in ("baseline-existing","off-0p75","holdout","per-case"):
            with self.assertRaises(ValueError):p.validate_protocol(protocol(),bad)
        for mutate in (lambda x:x.update(expected_speakers=2),lambda x:x.update(threads=1),
                       lambda x:x.update(split="holdout"),lambda x:x["window_config"].update(tau=.35),
                       lambda x:x["profiles"][1].update(min_duration_off=.4),
                       lambda x:x["selection"].update(maximum_native_der0=.28885),
                       lambda x:x.update(new_asr_inference=True)):
            value=protocol();mutate(value)
            with self.assertRaises(ValueError):p.validate_protocol(value,"off-0p25")

    def test_sdk_config_metadata_has_off_before_session_constructor_and_float32_bits(self):
        sdk=fake_sdk()
        with mock.patch.object(sdk,"OfflineSpeakerDiarization") as neural:
            for profile in p.PROFILES[1:]:
                metadata=p.sdk_metadata(profile,sdk)
                self.assertEqual(profile["min_duration_off"],metadata["observed"]["min_duration_off"])
                self.assertEqual(-1,metadata["num_clusters"])
                self.assertEqual(8,len(metadata["float32_bits"]["native_threshold"]))
            neural.assert_not_called()
        result=p.infer(np.zeros(48000,np.float32),"embedding","segmentation",p.PROFILES[2],sdk)
        self.assertEqual(1.,sdk.configs[0].min_duration_off)
        self.assertEqual(.1,sdk.configs[0].segmentation.pyannote.window_shift_ratio)
        self.assertEqual(-1,sdk.configs[0].clustering.num_clusters)
        self.assertTrue(result["refinerAccepted"])

    def test_real_shape_replay_resources_and_no_gold_boundary(self):
        sdk=fake_sdk()
        with mock.patch.object(p,"overcluster",wraps=p.overcluster) as refiner:
            diagnostic=p.infer(np.zeros(48000,np.float32),"embedding","segmentation",p.PROFILES[1],sdk)
        args,kwargs=refiner.call_args
        self.assertEqual({},kwargs);self.assertEqual(4,len(args));self.assertEqual(3000,args[2])
        self.assertEqual(3,len(diagnostic["cleanEmbeddingWindows"]))
        self.assertTrue(all(len(w["embedding"])==512 for w in diagnostic["cleanEmbeddingWindows"]))
        self.assertEqual(3,diagnostic["counts"]["createdStreams"])
        self.assertEqual(3,diagnostic["counts"]["releasedStreams"])
        self.assertTrue(diagnostic["counts"]["sdReleased"])
        self.assertTrue(diagnostic["counts"]["extractorReleased"])
        self.assertFalse(diagnostic["newAsrInference"])
        gc.collect();self.assertTrue(all(w() is None for w in sdk.weak_resources))
        with self.assertRaises(TypeError):
            p.infer(np.zeros(1),"e","s",p.PROFILES[1],sdk,expected_speakers=2)

    def test_failed_compute_preserves_partial_real_counters_and_releases_references(self):
        sdk=fake_sdk(fail_compute=True)
        with self.assertRaisesRegex(RuntimeError,"fake NN") as caught:
            p.infer(np.zeros(48000,np.float32),"embedding","segmentation",p.PROFILES[1],sdk)
        diag=caught.exception.c2_diagnostics
        self.assertEqual([],diag["cleanEmbeddingWindows"])
        self.assertEqual(1,diag["counts"]["computeAttempts"])
        self.assertEqual(0,diag["counts"]["embeddingForwardCalls"])
        self.assertEqual(1,diag["counts"]["releasedStreams"])
        self.assertTrue(diag["counts"]["sdReleased"]);self.assertTrue(diag["counts"]["extractorReleased"])

    def records(self):
        rows=[]
        for i in range(8):
            edits={"errors":71 if i==0 else 0,"reference_tokens":533 if i==0 else 0,"rate":0.}
            der={"miss_ms":.18298480576441103*1000 if i==0 else 0.,"false_alarm_ms":0.,
                 "confusion_ms":0.,"reference_speaker_ms":1000. if i==0 else 0.,"rate":0.}
            metrics={key:deepcopy(edits) for key in ("wer_raw","wer_normalized","cpwer_raw","cpwer_normalized")}
            metrics.update({key:deepcopy(der) for key in ("native_der_collar_0ms","native_der_collar_250ms","der_collar_0ms","der_collar_250ms")})
            rows.append({"id":"dev"+str(i),"status":"COMPLETE","metrics":metrics,"duration_ms":1000,
                "native_speaker_count_error":0 if i<7 else 1,"raw_asr_invariant":True,"diarization_inference_ms":2.})
        return rows

    def test_weighted_der_exact_boundary_count_and_tie_keep_baseline(self):
        rows=self.records();gate=p.quality_gate(rows,protocol())
        self.assertTrue(gate["gate_pass"]);self.assertFalse(gate["strictly_better_der"])
        self.assertEqual("retain existing C2",gate["tie_policy"])
        rows[0]["metrics"]["native_der_collar_0ms"]["miss_ms"]+=1e-8
        self.assertFalse(p.quality_gate(rows,protocol())["conditions"]["native_der_no_regrowth"])
        rows=self.records();rows[6]["native_speaker_count_error"]=1
        self.assertFalse(p.quality_gate(rows,protocol())["conditions"]["native_count_at_least7"])

    def test_failure_missing_duplicate_and_raw_change_cannot_pass(self):
        for mutate in (lambda rows:rows.pop(),lambda rows:rows[0].update(status="FAILED"),
                       lambda rows:rows[0].update(raw_asr_invariant=False),
                       lambda rows:rows[-1].update(id=rows[0]["id"])):
            rows=self.records();mutate(rows)
            self.assertFalse(p.quality_gate(rows,protocol())["gate_pass"])
        self.assertEqual(["Один,","два!"],p.raw_tokens({"transcript":[{"text":"Один, два!"}]}))
        self.assertNotEqual(p.raw_tokens({"transcript":[{"text":"Один, два!"}]}),p.raw_tokens({"transcript":[{"text":"два! Один,"}]}))

    def test_existing_output_refused_before_neural_or_config_construction(self):
        with tempfile.TemporaryDirectory() as temp:
            args=p.parser().parse_args(["--profile","off-0p25","--audio-root",temp,"--output",temp])
            sdk=fake_sdk()
            with mock.patch.object(sdk,"OfflineSpeakerDiarization") as neural,self.assertRaisesRegex(ValueError,"fresh output"):
                p.run(args,sherpa=sdk,native=NS())
            neural.assert_not_called()

    def test_case_failure_is_saved_and_repeated_run_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output=root/"fresh";source=root/"source";source.mkdir()
            for name in ("reference","hypothesis","metrics","diagnostics"):(source/(name+".json")).write_text('{}')
            audio=root/"audio.wav";audio.write_bytes(b"fixture");reference=source/"reference.json"
            protocol_path=root/"protocol.json";protocol_path.write_text(json.dumps(protocol()))
            args=p.parser().parse_args(["--profile","off-0p25","--audio-root",str(root),"--output",str(output),"--protocol",str(protocol_path)])
            case={"id":"source","audio_sha256":p.digest(audio),"duration_ms":3000}
            checked={"protocol":protocol(),"profile":p.PROFILES[1],"sdk_config":{},"asr_run":root,
                "inputs":[{"case":case,"audio":audio,"reference":reference,"reference_sha256":p.digest(reference)}],
                "fingerprint":{"code":p._dependencies(),"protocol_sha256":p.digest(protocol_path),"models":[],
                    "source_cases":{"source":{"evidence_sha256":p.evidence_hashes(source)}}}}
            with mock.patch.object(p,"preflight",return_value=checked),mock.patch.object(p.base,"_verify_models",return_value=([],0)),mock.patch.object(p.base,"_read_canonical_wav",return_value=np.zeros(48000,np.float32)),mock.patch.object(p,"infer",side_effect=RuntimeError("fixture failed")) as infer,redirect_stdout(io.StringIO()):
                self.assertEqual(1,p.run(args,sherpa=fake_sdk(),native=NS()))
            self.assertEqual(5,len(infer.call_args.args));self.assertEqual({},infer.call_args.kwargs)
            self.assertEqual("FAILED",p.load(output/"run.json")["status"])
            self.assertEqual("FAILED",p.load(output/"source/case.json")["status"])
            self.assertTrue((output/"source/failure.json").exists());self.assertTrue((output/"results.csv").exists())
            self.assertFalse(p.load(output/"summary.json")["gate_pass"])
            with self.assertRaisesRegex(ValueError,"fresh output"):p.run(args,sherpa=fake_sdk(),native=NS())


if __name__=="__main__":unittest.main()
