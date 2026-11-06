#!/usr/bin/env python3
"""Capture an emulator UI demonstration, with host microphone disabled. No performance claim."""
import argparse,json,pathlib,re,subprocess,time,xml.etree.ElementTree as ET
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--adb',required=True);p.add_argument('--serial',required=True);p.add_argument('--output',type=pathlib.Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
def call(*args):return subprocess.check_output([a.adb,'-s',a.serial,*args],stderr=subprocess.STDOUT)
assert call('shell','getprop','ro.kernel.qemu').strip()==b'1','Emulator only'
# pidof returns a nonzero status when absent, so inspect without check_output.
running=subprocess.run([a.adb,'-s',a.serial,'shell','pidof','screenrecord'],capture_output=True).stdout.strip()
assert not running,'Do not interrupt another screenrecord'
call('emu','avd','hostmicoff')
call('shell','pm','grant','ru.replika.offline','android.permission.RECORD_AUDIO')
call('shell','am','force-stop','ru.replika.offline')
call('shell','am','start','-W','-n','ru.replika.offline/ru.replika.MainActivity')
def bounds(label):
 for attempt in range(12):
  call('shell','uiautomator','dump','/data/local/tmp/replika-v16.xml')
  root=ET.fromstring(call('exec-out','cat','/data/local/tmp/replika-v16.xml'))
  for node in root.iter('node'):
   if node.get('text')==label or (node.get('content-desc') or '').split(',')[0]==label:
    box=list(map(int,re.findall(r'\d+',node.get('bounds',''))))
    if len(box)==4 and node.get('enabled')!='false':return box
  time.sleep(.2)
 raise RuntimeError('Missing control: '+label)
def tap(label):
 x1,y1,x2,y2=bounds(label);call('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2));time.sleep(.4)
bounds('Начать запись')
remote='/sdcard/replika-v16-ui.mp4'
proc=subprocess.Popen([a.adb,'-s',a.serial,'shell','screenrecord','--time-limit','60',remote],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
time.sleep(.5);pids=call('shell','pidof','screenrecord').decode().split();assert len(pids)==1
try:
 tap('Начать запись');time.sleep(1.5)
 x1,y1,x2,y2=bounds('Запись идёт. Нажмите или потяните шар')
 cx=(x1+x2)//2;cy=(y1+y2)//2
 call('shell','input','swipe',str(cx),str(cy),str(cx+(x2-x1)//4),str(cy-30),'700');time.sleep(1)
 tap('Пауза');tap('Выйти из записи');time.sleep(.5);tap('Удалить запись');time.sleep(1)
finally:
 call('shell','kill','-2',pids[0]);proc.communicate(timeout=10)
(a.output/'native-demo.mp4').write_bytes(call('exec-out','cat',remote));call('shell','rm',remote)
(a.output/'video-scope.json').write_text(json.dumps({'actualNativeApp':True,'emulatorOnly':True,'hostMicrophoneEnabled':False,'syntheticSpeechInjected':False,'performanceMeasured':False,'actions':['start','drag/release','pause','exit','discard','clean home']},indent=2)+'\n')
print('Native emulator demo saved')
