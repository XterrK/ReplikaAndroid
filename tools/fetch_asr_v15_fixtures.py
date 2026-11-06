#!/usr/bin/env python3
"""Fetch a fixed public evaluation subset; audio remains outside the repository/APK.

FLEURS: first N archive entries in ru_ru/test, selected before inference (CC BY 4.0).
EARS: publisher's real English whisper example, VAD-only (CC BY-NC 4.0).
Neither source is a Russian phone-whisper acceptance corpus.
"""
import argparse, hashlib, json, pathlib, tarfile, urllib.request

def get(url):
    return urllib.request.urlopen(url, timeout=120)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--count',type=int,default=32);p.add_argument('--offset',type=int,default=0);p.add_argument('--revision');a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    rev=a.revision or json.load(get('https://huggingface.co/api/datasets/google/fleurs'))['sha']
    base=f'https://huggingface.co/datasets/google/fleurs/resolve/{rev}/data/ru_ru/'
    tsv=get(base+'test.tsv').read();(a.out/'fleurs-test.tsv').write_bytes(tsv)
    refs={r[1]:r for line in tsv.decode().splitlines() if len(r:=line.split('\t'))>=7}
    fixtures=[];seen=0
    with get(base+'audio/test.tar.gz') as response, tarfile.open(fileobj=response,mode='r|gz') as archive:
        for member in archive:
            name=pathlib.PurePosixPath(member.name).name
            if not member.isfile() or name not in refs:continue
            seen+=1
            if seen<=a.offset:continue
            data=archive.extractfile(member).read();dest=a.out/name;dest.write_bytes(data);r=refs[name]
            fixtures.append({'id':name[:-4],'path':name,'language':'ru','speech':'ordinary recorded read speech','source':'google/fleurs ru_ru/test','revision':rev,'archiveMember':member.name,'license':'CC-BY-4.0','sha256':hashlib.sha256(data).hexdigest(),'reference':r[3],'referenceRaw':r[2],'gender':r[6]})
            print('FLEURS',len(fixtures),name,flush=True)
            if len(fixtures)>=a.count:break
    ears_url='https://www2.informatik.uni-hamburg.de/sp/audio/publications/interspeech2024-ears/files/ears/p012_rainbow_05_whisper.wav'
    data=get(ears_url).read();name='ears-p012-rainbow-05-whisper.wav';(a.out/name).write_bytes(data)
    transcript=json.load(get('https://raw.githubusercontent.com/facebookresearch/ears_dataset/main/transcripts.json'))['rainbow_05_whisper']
    fixtures.append({'id':'ears-p012-rainbow-05-whisper','path':name,'language':'en','speech':'real whispered speech, publisher sample','source':ears_url,'license':'CC-BY-NC-4.0; research evaluation only; not packaged in product','sha256':hashlib.sha256(data).hexdigest(),'reference':transcript,'evaluation':'VAD only; GigaAM Russian ASR is not evaluated on English'})
    (a.out/'fixtures.json').write_text(json.dumps({'selection':f'{a.count} FLEURS test archive entries after offset {a.offset}, fixed before model inference; publisher EARS whisper sample','offset':a.offset,'count':a.count,'fixtures':fixtures},ensure_ascii=False,indent=2))
    print('Saved',a.out/'fixtures.json',flush=True)

if __name__=='__main__':main()
