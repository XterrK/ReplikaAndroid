#!/usr/bin/env python3
"""Ordered emulator-only regressions. Does not uninstall, clear data or record microphone audio.
Requires final All-in-One QA same-ID app/test APKs and existing staged public fixtures.
"""
import argparse,json,os,pathlib,re,subprocess,time
p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=True)
adb=os.environ.get('ADB','/mnt/f/ReplikaToolchain/v13-adb.exe')
def call(*args):return subprocess.check_output([adb,*args]).decode(errors='replace')
assert call('shell','getprop','ro.kernel.qemu').strip()=='1','Run only on emulator'
groups=[
 ('bundle','ru.replika.AllInOneAcceptanceTest'),
 ('core',','.join('ru.replika.'+x for x in ['ModelPackTest','StorageAudioTest','ProductStorageTest','ProcessingRecoveryTest','BundledModelInstallerTest','DiarizationTest','PipelineTest#realWhisperBackend'])),
 ('ml','ru.replika.MLComparisonTest'),
 ('warning','ru.replika.WarningPipelineTest'),
 ('recovery','ru.replika.RecoveryV13InstrumentedTest,ru.replika.TranscriptModesV13Test'),
 ('ui','ru.replika.NavigationTest,ru.replika.AllInOneUiTest,ru.replika.ProductExperienceTest,ru.replika.ReviewScreenshotsTest'),
 ('persist','ru.replika.PersistedEditsTest')]
summary=[]
for label,classes in groups:
 status=call('shell','dumpsys','thermalservice')
 m=re.search(r'Thermal Status:\s*(\d+)',status)
 assert m and int(m[1])<3,'No heavy suite while SEVERE; cool then resume'
 if label=='persist':call('shell','am','force-stop','ru.replika.offline')
 start=time.monotonic();print('START',label,flush=True)
 output=call('shell','am','instrument','-w','-r','-e','class',classes,'ru.replika.offline.test/androidx.test.runner.AndroidJUnitRunner')
 path=a.output/(label+'.log');path.write_text(output)
 failed=bool(re.search(r'INSTRUMENTATION_STATUS_CODE: -(?:1|2)\b|FAILURES!!!|INSTRUMENTATION_FAILED|Process crashed',output))
 tests=[];case={}
 for line in output.splitlines():
  if line.startswith('INSTRUMENTATION_STATUS: class='):case['class']=line.split('=',1)[1]
  if line.startswith('INSTRUMENTATION_STATUS: test='):case['test']=line.split('=',1)[1]
  if line.startswith('INSTRUMENTATION_STATUS_CODE:'):
   code=int(line.split(':',1)[1])
   if code!=1 and 'test' in case:
    tests.append(dict(case,code=code));case={}
 entry={'group':label,'elapsedSeconds':round(time.monotonic()-start,3),'failed':failed,'tests':tests}
 summary.append(entry);(a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('END',label,'FAILED' if failed else 'PASS',len(tests),flush=True)
 if failed:print(output[-10000:],flush=True)
print('FINISHED',flush=True)
raise SystemExit(any(x['failed'] for x in summary))
