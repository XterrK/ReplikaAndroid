# Step C: pinned speaker-embedding models

All six requested exact ONNX models are available in the official
[sherpa-onnx speaker model release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models)
(release ID `133152315`). No substitute model was selected. The five new files
total **227,082,991 bytes**; weights remain outside Git. The existing ERes2Net
baseline file remains unchanged.

| Catalog ID | Size, bytes | Embedding dimension | Model-weight license evidence |
| --- | ---: | ---: | --- |
| `eres2net_zh` | 39,593,761 | 512 | Apache-2.0: exact author ModelScope metadata and maintainer checkpoint clarification |
| `wespeaker_resnet34_lm` | 26,530,550 | 256 | CC-BY-4.0: exact author HF card and official pretrained-model documentation |
| `campplus_en` | 29,596,978 | 512 | Apache-2.0: exact English VoxCeleb author ModelScope metadata |
| `wespeaker_camplus_lm` | 29,292,687 | 512 | Conflicting author sources: exact HF card Apache-2.0; official VoxCeleb pretrained policy CC-BY-4.0 |
| `titanet_small` | 40,257,283 | 192 | Exact NGC card explicitly applies the NeMo toolkit license; referenced license is Apache-2.0 |
| `titanet_large` | 101,405,493 | 192 | CC-BY-4.0: exact NVIDIA HF card |

The CAM++ LM conflict remains unresolved. Its external research-cache inclusion
does not authorize redistribution. No app pack, Android model lock or baseline
file was changed. Other dataset terms are separate from the model-card statements.

`configs/eval/diar-models.json` pins each immutable GitHub asset ID, exact URL,
byte size and independently measured SHA-256. Available author HF card revisions
are also pinned. The older GitHub assets have no publisher digest; these are
measured hashes, not publisher-signed integrity claims. The catalog SHA-256 is
`743624f2f25be1635fe60b11c3e11324c6dd8480f793cdbe196542733d29f7a3`.

`repoRelative=true` resolves the baseline `path` from the project root.
Other `path` values are filenames relative to the caller's external embedding
root. Reproduce using an external directory of your choice:

```sh
python tools/eval/prepare_diar_models.py --output-root "$DIAR_MODEL_ROOT" \
  --probe --report /path/to/fresh-model-provenance.json
```

Use `--check` for offline verification. Existing files with mismatched size or
SHA are rejected and not replaced. Missing non-baseline files are fetched only
after checking official asset metadata against the pinned immutable ID/name/size.
The repository baseline is never written by this tool.

Evidence:

- `model-provenance-sources.json`: primary sources, source response hashes,
  immutable revisions/IDs, exact author license statements and limitations.
- `model-provenance-load.json`: all six files passed byte verification and
  extractor load/dimension checks on sherpa-onnx **2.0.1**, CPU, one thread.
- `model-provenance-reproduction.json`: the preparer's actual clean-cache
  download of ResNet34 LM passed the same size/SHA pins.
- `model-provenance-validation.json`: missing-file, unknown-ID, wrong-size,
  wrong-SHA, traversal and existing-evidence guards.

The load probe supplies no audio and performs no embedding inference. It does
not measure quality, automatic speaker count, DER, audio RTF or Android behavior.
Exact original training-checkpoint/export byte-equivalence has not been recreated;
the downloaded ONNX release bytes are pinned and verified directly.
