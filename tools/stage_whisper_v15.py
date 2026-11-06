#!/usr/bin/env python3
"""Stage the seven licensed public author-labelled RU-whisper test files on an explicit emulator.
Research fixtures stay in app-private QA files, outside APK assets/model packs. No phone microphone.
"""
import argparse,hashlib,json,pathlib,subprocess
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=pathlib.Path,default=pathlib.Path('/mnt/f/ReplikaToolchain/asr-v15-ru-whisper'))
p.add_argument('--adb',default='/tmp/replika-v14-adb');a=p.parse_args()
def call(*args):return subprocess.check_output([a.adb,*args],stderr=subprocess.STDOUT)
assert call('shell','getprop','ro.kernel.qemu').strip()==b'1','Explicit emulator only'
def native(path):
 path=str(path.resolve())
 return path[5].upper()+':\\'+path[7:].replace('/','\\') if path.startswith('/mnt/') and len(path)>7 else path
manifest=json.loads((a.source/'fixtures.json').read_text());rows=manifest['fixtures'];assert len(rows)==7
license_sha='e136a6af001dd43a9002f20f39dd56d200afa9a6d408e28a625d90c9a0c22143'
assert hashlib.file_digest((a.source/'LICENSE.md').open('rb'),'sha256').hexdigest()==license_sha
remote='/data/local/tmp/replika-v15-public-whisper';target='files/ru-whisper-v15'
call('shell','mkdir','-p',remote);call('shell','run-as','ru.replika.offline','mkdir','-p',target)
for row in rows:
 name=row['path'];assert pathlib.Path(name).name==name and name.endswith('.wav')
 path=a.source/name;assert hashlib.file_digest(path.open('rb'),'sha256').hexdigest()==row['sha256']
for name in [r['path'] for r in rows]+['fixtures.json','LICENSE.md']:
 call('push',native(a.source/name),remote+'/'+name)
 call('shell','run-as','ru.replika.offline','cp',remote+'/'+name,target+'/'+name)
 call('shell','rm',remote+'/'+name)
print('Staged all seven author-labelled studio whisper WAVs, independent references and LICENSE; no model or application source changed.')
