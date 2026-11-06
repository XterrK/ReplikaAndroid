#!/usr/bin/env python3
"""Download exactly the separately evaluated public weights, verifying every SHA-256.

Never changes the application's current model pack. Source revisions/hashes live in
docs/test-evidence/v1.5/*-provenance.json. Weights remain outside version control.
"""
import argparse,hashlib,json,pathlib,urllib.request

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):h.update(block)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',choices=['giga-v3','giga-v3-rnnt','parakeet-v3'],required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
    root=pathlib.Path(__file__).resolve().parents[1];manifest=json.loads((root/'docs/test-evidence/v1.5'/f'{a.model}-provenance.json').read_text())
    a.out.mkdir(parents=True,exist_ok=True)
    for f in manifest['files']:
        rel=pathlib.PurePosixPath(f['path']);assert not rel.is_absolute() and '..' not in rel.parts
        dest=a.out/str(rel);dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists() or digest(dest)!=f['sha256']:
            temp=dest.with_name(dest.name+'.part')
            url=f"https://huggingface.co/{manifest['repository']}/resolve/{manifest['revision']}/{rel}"
            with urllib.request.urlopen(url,timeout=120) as response,temp.open('wb') as out:
                while block:=response.read(1024*1024):out.write(block)
            if temp.stat().st_size!=f['bytes'] or digest(temp)!=f['sha256']:
                temp.unlink(missing_ok=True);raise ValueError(f'Integrity mismatch: {rel}')
            temp.replace(dest)
        print('VERIFIED',f['path'],f['bytes'],flush=True)
    (a.out/'provenance.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
