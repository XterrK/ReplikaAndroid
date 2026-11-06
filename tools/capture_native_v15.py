#!/usr/bin/env python3
"""Capture the real V1.5 emulator UI. Does not generate speech, contact a phone or send exports.
Run after installing/verifying the candidate. Use ADB pointing at an explicit emulator wrapper.
A native screenrecord demo is separate from performance measurement.
"""
import argparse,json,os,pathlib,re,subprocess,time,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--adb',default=os.environ.get('ADB','/tmp/replika-v14-adb'))
parser.add_argument('--video',action='store_true')
parser.add_argument('--performance',action='store_true')
args=parser.parse_args()
out=ROOT/'docs/human-review/v1.5/evidence/native-demo';out.mkdir(parents=True,exist_ok=True)
adb=args.adb

def call(*words):return subprocess.check_output([adb,*words],stderr=subprocess.STDOUT)
assert call('shell','getprop','ro.kernel.qemu').strip()==b'1','This controlled capture supports emulators only'

def node(label):
 for attempt in range(25):
  call('shell','uiautomator','dump','/data/local/tmp/replika-v15-capture.xml')
  raw=call('exec-out','cat','/data/local/tmp/replika-v15-capture.xml')
  try:root=ET.fromstring(raw)
  except ET.ParseError:time.sleep(.5);continue
  found=[n for n in root.iter('node') if n.get('text')==label or n.get('content-desc')==label or (n.get('content-desc') or '').startswith(label+',')]
  for n in found:
   bounds=list(map(int,re.findall(r'\d+',n.get('bounds',''))))
   if n.get('enabled')!='false' and len(bounds)==4 and bounds[2]>bounds[0] and bounds[3]>bounds[1]:return bounds
  time.sleep(.5)
 raise RuntimeError('Visible control missing: '+label)

def tap(label):
 x1,y1,x2,y2=node(label);call('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2));time.sleep(.5)
def capture(name):
 raw=call('exec-out','screencap','-p');assert raw.startswith(b'\x89PNG');(out/(name+'.png')).write_bytes(raw)
def launch():
 call('shell','am','force-stop','ru.replika.offline')
 call('shell','am','start','-W','-f','0x10008000','-n','ru.replika.offline/ru.replika.MainActivity')
 node('Настройки')
def theme(label):
 tap('Настройки');tap(label);tap('Назад');time.sleep(1)

launch();theme('Тёмная');launch();capture('home-dark-after-process-launch')
if args.video:
 running=subprocess.run([adb,'shell','pidof','screenrecord'],capture_output=True).stdout.strip()
 assert not running,'Another screenrecord must not be interrupted'
 call('emu','avd','hostmicoff') # No physical host microphone is used by this recording.
 remote='/sdcard/replika-v15-orb-touch-emulator.mp4'
 proc=subprocess.Popen([adb,'shell','screenrecord','--time-limit','120','--bit-rate','4000000',remote],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 time.sleep(.7);pids=call('shell','pidof','screenrecord').decode().split();assert len(pids)==1
 try:
  tap('Начать запись');time.sleep(2);capture('recording-virtual-input')
  x1,y1,x2,y2=node('Запись идёт. Нажмите или потяните шар');cx=(x1+x2)//2;cy=(y1+y2)//2
  call('shell','input','tap',str(cx),str(cy));time.sleep(.35)
  call('shell','input','swipe',str(cx-20),str(cy+12),str(cx+int((x2-x1)*.30)),str(cy-35),'900')
  capture('touch-release');time.sleep(1.5)
  tap('Пауза');capture('paused');time.sleep(1)
  tap('Продолжить');time.sleep(2);tap('Остановить');time.sleep(1.5);capture('saved-processing-setup')
 finally:
  subprocess.run([adb,'shell','kill','-2',pids[0]],capture_output=True);proc.communicate(timeout=20)
 data=call('exec-out','cat',remote);assert len(data)>10000
 (out/'native-orb-emulator-touch.mp4').write_bytes(data)
 call('shell','rm',remote)
 (out/'video-scope.json').write_text(json.dumps({'actualNativeApplication':True,'physicalPhoneMicrophoneTested':False,'hostMicrophoneEnabled':False,'input':'emulator virtual microphone with host audio input disabled; no synthetic speech injected','actions':['orb start','tap','drag/release','pause','resume','stop/save'],'performanceMeasuredDuringVideo':False},indent=2))
if args.performance:
 launch();tap('Начать запись');time.sleep(5)
 call('shell','dumpsys','gfxinfo','ru.replika.offline','reset');time.sleep(10)
 (out/'gfxinfo-recording-warm.txt').write_bytes(call('shell','dumpsys','gfxinfo','ru.replika.offline','framestats'))
 (out/'thermal-during-recording.txt').write_bytes(call('shell','dumpsys','thermalservice'))
 tap('Остановить');time.sleep(2)
 launch();time.sleep(4)
 call('shell','dumpsys','gfxinfo','ru.replika.offline','reset');time.sleep(4)
 (out/'gfxinfo-idle-settled.txt').write_bytes(call('shell','dumpsys','gfxinfo','ru.replika.offline','framestats'))
 (out/'performance-scope.json').write_text(json.dumps({'scope':'Emulator only; run without another AVD, Gradle, host ASR or screenrecord competing','recordingWarmupSeconds':5,'recordingSampleSeconds':10,'idleSettledBeforeResetSeconds':4,'idleSampleSeconds':4,'physicalVivoFpsBatteryThermalConfirmed':False},indent=2))
# Actual system configuration and persisted app theme, separate from a theme-only rendering fixture.
launch();theme('Как в системе')
for mode in ['yes','no']:
 call('shell','cmd','uimode','night',mode);time.sleep(2);capture('system-night-'+mode)
launch();capture('system-theme-after-force-stop')
print('Controlled native emulator capture complete',flush=True)
