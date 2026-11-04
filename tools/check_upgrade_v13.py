#!/usr/bin/env python3
"""Capture/compare only REPLIKA app-private DB/file bytes around an emulator update.
Raw paths remain in private output outside the repository; public evidence contains counts only.
Never uninstalls or clears data. The caller performs adb install -r between capture and compare.
"""
import argparse,hashlib,json,os,pathlib,subprocess,tarfile,io,sqlite3,tempfile
p=argparse.ArgumentParser();p.add_argument('mode',choices=['capture','compare']);p.add_argument('--private',type=pathlib.Path,required=True);p.add_argument('--evidence',type=pathlib.Path,required=True);a=p.parse_args()
adb=os.environ.get('ADB','/mnt/f/ReplikaToolchain/v13-adb.exe')
def run(*args):return subprocess.check_output([adb,*args])
assert b'Android SDK' in run('shell','getprop','ro.product.model'), 'This preservation helper is emulator-only'
run('shell','am','force-stop','ru.replika.offline')
raw=run('exec-out','run-as','ru.replika.offline','tar','-cf','-','databases','files')
hashes={}
with tarfile.open(fileobj=io.BytesIO(raw)) as t:
 for m in t:
  if m.isfile(): hashes[m.name]=hashlib.sha256(t.extractfile(m).read()).hexdigest()
version=run('shell','dumpsys','package','ru.replika.offline').decode(errors='replace')
versions=[s.strip() for s in version.splitlines() if 'versionCode=' in s or 'versionName=' in s]
if a.mode=='capture':
 a.private.mkdir(parents=True,exist_ok=True)
 (a.private/'upgrade-before-private.tar').write_bytes(raw)
 (a.private/'upgrade-before-private.json').write_text(json.dumps({'hashes':hashes,'version':versions}))
 print(json.dumps({'capturedFiles':len(hashes),'version':versions,'privateBackupOutsideRepo':True}))
else:
 old=json.loads((a.private/'upgrade-before-private.json').read_text())
 changed=[k for k,v in old['hashes'].items() if hashes.get(k)!=v]
 (a.private/'upgrade-changed-private.json').write_text(json.dumps(changed))
 report={'beforeVersion':old['version'],'afterVersion':versions,'beforeFiles':len(old['hashes']),'afterFiles':len(hashes),'changedOrMissingFiles':len(changed),'identicalBeforeFiles':not changed,'scope':'Exact DB and files byte hashes immediately around install -r before new-version launch; emulator only; private paths excluded'}
 a.evidence.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));assert not changed
