#!/usr/bin/env python3
"""Download the currently pinned manifest, verify bytes, and create a separate current offline pack.
Never changes the lock or replaces the historical V1.3/V1.4 pack. No automatic model upgrades.
"""
import argparse
import concurrent.futures
import hashlib
import pathlib
import shutil
import tarfile
import urllib.request
from prepare_embedded_pack import ROOT, read_lock, sha256_file
from prepare_current_pack import prepare


def install_url(url,specs,models,cache):
    name=hashlib.sha256(url.encode()).hexdigest()[:16]+'-'+url.rsplit('/',1)[-1]
    archive=cache/name
    if not archive.is_file():
        partial=archive.with_suffix(archive.suffix+'.part')
        print('Downloading',url,flush=True)
        try:
            with urllib.request.urlopen(url,timeout=90) as incoming,partial.open('wb') as outgoing:
                shutil.copyfileobj(incoming,outgoing,1024*1024)
            partial.replace(archive)
        finally:partial.unlink(missing_ok=True)
    def publish(spec,incoming):
        destination=models/spec['path'];destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.is_file() and destination.stat().st_size==spec['size'] and sha256_file(destination)==spec['sha256']:return
        temporary=destination.with_name(destination.name+'.installing')
        try:
            with temporary.open('wb') as outgoing:shutil.copyfileobj(incoming,outgoing,1024*1024)
            if temporary.stat().st_size!=spec['size'] or sha256_file(temporary)!=spec['sha256']:
                raise ValueError('Manifest-pinned model changed: '+spec['path'])
            temporary.replace(destination)
        finally:temporary.unlink(missing_ok=True)
    if all(spec.get('archiveMember') is None for spec in specs):
        if len(specs)!=1:raise ValueError('Ambiguous direct-file model URL')
        with archive.open('rb') as incoming:publish(specs[0],incoming)
    else:
        with tarfile.open(archive) as packed:
            for spec in specs:
                member=next(member for member in packed.getmembers() if pathlib.PurePosixPath(member.name).name==spec['archiveMember'])
                if not member.isfile():raise ValueError('Expected regular model archive member')
                with packed.extractfile(member) as incoming:publish(spec,incoming)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=pathlib.Path,default=ROOT/'app/src/main/assets/models-lock.json')
    parser.add_argument('--models',type=pathlib.Path,default=ROOT/'model-pack')
    parser.add_argument('--output',type=pathlib.Path,default=ROOT/'model-pack/replika-offline-pack-v1.5.zip')
    parser.add_argument('--cache',type=pathlib.Path,default=pathlib.Path('/mnt/f/ReplikaToolchain/model-downloads'))
    args=parser.parse_args();args.models.mkdir(parents=True,exist_ok=True);args.cache.mkdir(parents=True,exist_ok=True)
    _,_,specs=read_lock(args.manifest)
    grouped={}
    for spec in specs.values():grouped.setdefault(spec['url'],[]).append(spec)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        jobs=[executor.submit(install_url,url,rows,args.models,args.cache) for url,rows in grouped.items()]
        for job in jobs:job.result()
    result=prepare(args.models,args.manifest,args.output,ROOT/'app/src/main/assets/licenses')
    print('Pack ready',result['sourceBytes'],result['sourceSha256'],flush=True)
