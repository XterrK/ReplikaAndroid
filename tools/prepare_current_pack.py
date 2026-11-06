#!/usr/bin/env python3
"""Create a new manifest-pinned pack from local weights. Never overwrite the historical pack."""
import argparse
import json
import os
import pathlib
import stat
import tempfile
import zipfile
from prepare_embedded_pack import ROOT, read_lock, safe_path, stream_copy, verify_pack, sha256_file


def prepare(models, manifest, output, licenses):
    models,manifest,output,licenses=map(pathlib.Path,(models,manifest,output,licenses))
    if output.resolve()==(ROOT/'model-pack/replika-offline-pack.zip').resolve():
        raise ValueError('The historical offline pack must be preserved')
    raw,_,expected=read_lock(manifest)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=output.name+'.',suffix='.part',dir=output.parent,delete=False) as stream:
        temporary=pathlib.Path(stream.name)
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
            def entry(name):
                info=zipfile.ZipInfo(safe_path(name),date_time=(1980,1,1,0,0,0))
                info.create_system=3;info.external_attr=(stat.S_IFREG|0o644)<<16
                return info
            archive.writestr(entry('manifest.json'),raw)
            for name,spec in expected.items():
                source=models/name
                if not source.is_file() or source.stat().st_size!=spec['size']:
                    raise ValueError('Missing or incorrect local model: '+str(source))
                with source.open('rb') as incoming, archive.open(entry(name),'w',force_zip64=True) as outgoing:
                    count,digest=stream_copy(incoming,outgoing)
                if count!=spec['size'] or digest!=spec['sha256']:
                    raise ValueError('Pinned model SHA-256 mismatch: '+name)
            for source in sorted(licenses.iterdir()):
                if source.is_file():archive.writestr(entry('licenses/'+source.name),source.read_bytes())
        inventory=verify_pack(temporary,manifest)
        with temporary.open('rb') as stream:os.fsync(stream.fileno())
        temporary.replace(output)
        inventory.update(source=str(output.resolve()),sourceBytes=output.stat().st_size,sourceSha256=sha256_file(output))
        return inventory
    finally:
        temporary.unlink(missing_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models',type=pathlib.Path,default=ROOT/'model-pack')
    parser.add_argument('--manifest',type=pathlib.Path,default=ROOT/'app/src/main/assets/models-lock.json')
    parser.add_argument('--output',type=pathlib.Path,default=ROOT/'model-pack/replika-offline-pack-v1.5.zip')
    parser.add_argument('--licenses',type=pathlib.Path,default=ROOT/'app/src/main/assets/licenses')
    args=parser.parse_args()
    print(json.dumps(prepare(args.models,args.manifest,args.output,args.licenses),ensure_ascii=False,indent=2))
