#!/usr/bin/env python3
"""Sequential validation on an explicitly selected adb target. Uses only REPLIKA app data."""
import os,subprocess,pathlib,sys,datetime
ROOT=pathlib.Path(__file__).resolve().parents[1]
ADB=os.environ.get('ADB','/mnt/f/ReplikaToolchain/sdk/platform-tools/adb')
OUT=ROOT/'docs/test-evidence/v1.2';OUT.mkdir(parents=True,exist_ok=True)
PKG='ru.replika.offline';RUNNER=PKG+'.test/androidx.test.runner.AndroidJUnitRunner'
def adb(*args,**kw):return subprocess.run([ADB,*args],check=True,**kw)
def capture(*args):return subprocess.check_output([ADB,*args],text=True).strip()
def run(label,classes):
 path=OUT/(label+'.txt')
 if path.exists():path=OUT/(label+'-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.txt')
 result=subprocess.run([ADB,'shell','am','instrument','-w','-r','-e','class',classes,RUNNER],capture_output=True,text=True)
 text=result.stdout+result.stderr;path.write_text(text);print(label,text[-900:],flush=True)
 if result.returncode or 'FAILURES!!!' in text or 'INSTRUMENTATION_FAILED' in text or 'INSTRUMENTATION_CODE: -1' not in text or any('INSTRUMENTATION_STATUS_CODE: '+code in text for code in ['-3','-4']):
  raise SystemExit('Validation failed or skipped; inspect '+str(path))
assert capture('shell','getprop','ro.kernel.qemu')=='1','This automated runner grants only virtual emulator microphone access; use manual physical guide for a phone.'
adb('shell','input','keyevent','KEYCODE_WAKEUP');adb('shell','wm','dismiss-keyguard')
adb('shell','settings','put','system','screen_off_timeout','2147483647')
adb('shell','settings','put','secure','show_ime_with_hard_keyboard','1')
adb('shell','wm','size','reset');adb('shell','wm','density','reset');adb('shell','settings','put','system','font_scale','1.0')
for relative in ['app/build/outputs/apk/debug/app-debug.apk','app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk']:
 local=ROOT/relative
 if ADB.endswith('.exe'):local=pathlib.Path(subprocess.check_output(['wslpath','-w',str(local)],text=True).strip())
 adb('install','-r',str(local))
adb('shell','pm','grant',PKG,'android.permission.POST_NOTIFICATIONS')
# AVD launched -no-audio: virtual input only, no host/phone microphone recording.
adb('shell','pm','grant',PKG,'android.permission.RECORD_AUDIO')
subprocess.run([sys.executable,str(ROOT/'tools/stage_android.py'),'--pack'],env=os.environ,check=True)
adb('shell','svc','wifi','disable');adb('shell','svc','data','disable')
run('android-pack-install','ru.replika.ModelPackTest#importRealOfflinePack')
classes=['ModelPackTest','StorageAudioTest','DiarizationTest','PipelineTest','NavigationTest','ProcessingRecoveryTest','ProductStorageTest','MLComparisonTest','WarningPipelineTest']
run('android-instrumentation',','.join('ru.replika.'+c for c in classes))
run('android-compose-ui','ru.replika.ReviewScreenshotsTest')
run('android-product-ui','ru.replika.ProductExperienceTest')
subprocess.run([sys.executable,str(ROOT/'tools/collect_android_v12.py')],env=os.environ,check=True)
try:
 adb('shell','wm','size','360x640');adb('shell','wm','density','160');adb('shell','settings','put','system','font_scale','1.3')
 run('android-compact130',','.join(['ru.replika.ProductExperienceTest','ru.replika.ReviewScreenshotsTest#libraryModelsAndRecording','ru.replika.ReviewScreenshotsTest#actualShortSpeechReviewQueue']))
 subprocess.run([sys.executable,str(ROOT/'tools/collect_android_v12.py')],env=os.environ,check=True)
finally:
 adb('shell','wm','size','reset');adb('shell','wm','density','reset');adb('shell','settings','put','system','font_scale','1.0')
adb('shell','am','force-stop',PKG)
run('android-process-relaunch','ru.replika.PersistedEditsTest')
subprocess.run([sys.executable,str(ROOT/'tools/collect_android_v12.py')],env=os.environ,check=True)
