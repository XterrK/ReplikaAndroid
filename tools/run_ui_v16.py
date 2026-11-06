#!/usr/bin/env python3
"""Emulator-only recording UI regression. Preserves app data and restores display settings."""
import argparse,io,json,os,pathlib,re,shutil,subprocess,tarfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--adb',default=os.environ.get('ADB') or shutil.which('adb') or shutil.which('adb.exe'))
p.add_argument('--serial',required=True)
p.add_argument('--profile',choices=['tall','compact','large'],default='tall')
p.add_argument('--classes',default='ru.replika.RecordingExperienceV16Test')
p.add_argument('--output',type=pathlib.Path,required=True)
a=p.parse_args()
if not a.adb:p.error('Set --adb or put adb on PATH')
a.output.mkdir(parents=True,exist_ok=True)
def call(*words):return subprocess.check_output([a.adb,'-s',a.serial,*words],stderr=subprocess.STDOUT)
assert call('shell','getprop','ro.kernel.qemu').strip()==b'1','Emulator only; do not run against a phone'
def override(kind):
 found=re.search(rb'Override (?:size|density):\s*(\S+)',call('shell','wm',kind))
 return found.group(1).decode() if found else 'reset'
old_size=override('size');old_density=override('density')
old_font=call('shell','settings','get','system','font_scale').decode().strip()
profiles={'tall':('432x936','180','1.0'),'compact':('360x640','160','1.3'),'large':('360x640','160','2.0')}
start=time.monotonic();raw=b''
try:
 size,density,font=profiles[a.profile]
 call('shell','wm','size',size);call('shell','wm','density',density)
 call('shell','settings','put','system','font_scale',font)
 call('emu','avd','hostmicoff')
 raw=call('shell','am','instrument','-w','-r','-e','class',a.classes,'ru.replika.offline.test/androidx.test.runner.AndroidJUnitRunner')
 (a.output/'instrumentation.log').write_bytes(raw)
 data=call('exec-out','run-as','ru.replika.offline','tar','-cf','-','files/ui-v1.6')
 with tarfile.open(fileobj=io.BytesIO(data)) as archive:
  for member in archive.getmembers():
   if member.isfile():
    dest=a.output/'screenshots'/pathlib.PurePosixPath(member.name).name
    dest.parent.mkdir(exist_ok=True);dest.write_bytes(archive.extractfile(member).read())
finally:
 call('shell','am','force-stop','ru.replika.offline')
 call('shell','wm','size',old_size);call('shell','wm','density',old_density)
 if old_font=='null':call('shell','settings','delete','system','font_scale')
 else:call('shell','settings','put','system','font_scale',old_font)
failed=bool(re.search(rb'FAILURES!!!|INSTRUMENTATION_FAILED|Process crashed|INSTRUMENTATION_STATUS_CODE: -(?:1|2)\b',raw)) or not re.search(rb'OK \(\d+ tests?\)',raw)
report={'profile':a.profile,'classes':a.classes,'elapsedSeconds':round(time.monotonic()-start,2),'status':'FAIL' if failed else 'PASS','emulatorOnly':True,'physicalMicrophoneUsed':False,'displaySettingsRestored':True}
(a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
raise SystemExit(1 if failed else 0)
