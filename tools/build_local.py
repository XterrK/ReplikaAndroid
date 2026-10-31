#!/usr/bin/env python3
"""WSL/F: build with a RAM mirror, checkpointed as a buffered tar on F: after every build."""
import pathlib,os,shutil,concurrent.futures,subprocess,tarfile
ROOT=pathlib.Path('/mnt/f/Hackathons/ReplikaAndroid');TOOLS=pathlib.Path('/mnt/f/ReplikaToolchain');RAM=pathlib.Path('/dev/shm/replika-build');RAM.mkdir(exist_ok=True)
def copy_tree(src,dst):
 pairs=[]
 for base,dirs,files in os.walk(src):
  for name in files:
   if name.endswith('.lock'):continue
   f=pathlib.Path(base)/name;pairs.append((f,dst/f.relative_to(src)))
 def copy(pair):
  a,b=pair;b.parent.mkdir(parents=True,exist_ok=True)
  if not b.exists() or b.stat().st_size!=a.stat().st_size:shutil.copy2(a,b)
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as e:list(e.map(copy,pairs))
cache=RAM/'cache';archive=TOOLS/'gradle-cache-checkpoint.tar'
if not cache.exists():
 cache.mkdir()
 if archive.exists():
  with archive.open('rb',buffering=4*1024*1024) as f,tarfile.open(fileobj=f,mode='r|') as t:t.extractall(cache,filter='data')
 else:copy_tree(TOOLS/'gradle-cache',cache)
print('RAM cache ready',flush=True)
copy_tree(TOOLS/'gradle-8.13',RAM/'gradle')
jdk=RAM/'jdk';jdk.mkdir(exist_ok=True)
for name in ['bin','lib','conf']:copy_tree(TOOLS/'jdk-17.0.17+10'/name,jdk/name)
shutil.copy2(TOOLS/'jdk-17.0.17+10/release',jdk/'release')
env=os.environ.copy();env.update(JAVA_HOME=str(jdk),GRADLE_USER_HOME=str(cache),ANDROID_HOME=str(TOOLS/'sdk'),ANDROID_USER_HOME=str(TOOLS/'android-user'),TMPDIR=str(TOOLS/'tmp'))
args=['bash',str(RAM/'gradle/bin/gradle'),'-p',str(ROOT),':app:assembleDebug',':app:testDebugUnitTest',':app:assembleDebugAndroidTest','--max-workers=2','-Dorg.gradle.jvmargs=-Xmx1500m','-Pkotlin.compiler.execution.strategy=in-process']
try:result=subprocess.run(args,cwd=ROOT,env=env).returncode
finally:
 subprocess.run(['bash',str(RAM/'gradle/bin/gradle'),'--stop'],cwd=ROOT,env=env)
 temp=archive.with_suffix('.tar.part')
 with temp.open('wb',buffering=4*1024*1024) as f,tarfile.open(fileobj=f,mode='w|') as t:t.add(cache,arcname='.',filter=lambda i: None if i.name.endswith('.lock') else i)
 temp.replace(archive);print('Cache checkpoint saved on F:',flush=True)
raise SystemExit(result)
