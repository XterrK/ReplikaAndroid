from pathlib import Path
from dataclasses import asdict,replace
from datetime import datetime,timezone
import math,json,random,subprocess,hashlib,sys,os
project=Path.cwd();sys.path.insert(0,str(project));root=Path(__file__).resolve().parent
from tools.eval import speaker_refiner as ref
from tools.eval.pipeline import Turn
from tools.eval.run import digest,evidence_hashes
assert digest(ref.__file__)=='4f52854185c9ad4b2e54b9679a9670b5415d5a9fcc1c16d0c5f392eb6aa69eb1'
rng=random.Random(190407);cases=[];sourceproof=[]
selected=ref.RefineConfig(merge_threshold=.7,minimum_reassignment_similarity=.7,small_missing_centroid_policy='temporal')
def add(identifier,turns,windows,duration,config=selected,**meta):
 cases.append({'id':identifier,'kind':'refine','turns':[asdict(t)for t in turns],'windows':[asdict(w)for w in windows],'duration_ms':duration,'config':asdict(config),**meta})
def measured(turns,duration,vectors):return [replace(w,embedding=tuple(vectors[w.speaker]))for w in ref.clean_windows(turns,duration)if w.speaker in vectors]
base=project/'artifacts/test-results/step-04'
cohorts=[('dev','auto-wespeaker-resnet34-lm','refine-resnet34-050-temporal-guard0p7'),('holdout','candidate-c1-holdout-diar','candidate-c1-holdout-refined'),('reserve','candidate-c1-reserve-diar','candidate-c1-reserve-refined')]
for cohort,source,derived in cohorts:
 paths=sorted((base/source/'auto-0p50').glob('*/case.json'))
 assert len(paths)=={'dev':8,'holdout':5,'reserve':10}[cohort]
 for p in paths:
  c=json.loads(p.read_text());assert c['evidence_sha256']==evidence_hashes(p.parent)
  d=json.loads((p.parent/'diagnostics.json').read_text());turns=[Turn(t['startMs'],t['endMs'],t['speakerId'])for t in d['diarizationTurns']]
  windows=[ref.EmbeddingWindow(w['start_ms'],w['end_ms'],w['speaker'],tuple(w['embedding']),w['clean'])for w in d['cleanEmbeddingWindows']]
  result=ref.refine(turns,windows,c['duration_ms'],selected)
  q=base/derived/'tau-0p7'/c['id'];dc=json.loads((q/'case.json').read_text());assert dc['evidence_sha256']==evidence_hashes(q)
  expected=json.loads((q/'diagnostics.json').read_text())
  assert expected['refiner']['config']==asdict(selected)
  assert expected['diarizationTurns']==[{'startMs':t.start_ms,'endMs':t.end_ms,'speakerId':t.speaker}for t in result.turns]
  add(cohort+':'+c['id'],turns,windows,c['duration_ms'],cohort=cohort)
  sourceproof.append({'id':cases[-1]['id'],'source':str(p.parent.relative_to(project)),'source_evidence_sha256':{'case.json':digest(p),**evidence_hashes(p.parent)},'saved_refined':str(q.relative_to(project)),'saved_refined_evidence_sha256':{'case.json':digest(q/'case.json'),**evidence_hashes(q)},'windows':len(windows),'embedding_dimensions':sorted({len(w.embedding)for w in windows})})
iso=ref.RefineConfig(merge_similar=False,use_eigengap=False,reassign_small=False,smooth=False)
t=[Turn(0,4000,40),Turn(5000,9000,70),Turn(10000,14000,90)];v={40:(1,0),70:(.99,.01),90:(0,1)}
add('controlled:actual_eigengap_merge',t,measured(t,14000,v),14000,replace(iso,use_eigengap=True))
add('controlled:cosine_only',t,measured(t,14000,v),14000,replace(iso,merge_similar=True))
for angles in [(0,35,70),(0,20,40)]:
 vv={key:(math.cos(math.radians(a)),math.sin(math.radians(a)))for key,a in zip((40,70,90),angles)}
 for guard in [False,True]:add('controlled:chain'+str(angles)+'guard'+str(guard),t,measured(t,14000,vv),14000,replace(iso,merge_similar=True,merge_threshold=.5 if angles[1]==35 else .85,complete_link_guard=guard))
for length in [499,500]:
 tt=[Turn(0,2000,0),Turn(2000,2000+length,1),Turn(2000+length,5000,0),Turn(6000,8000,1)]
 add('controlled:smooth'+str(length),tt,measured(tt,9000,{0:(1,0),1:(0,1)}),9000,replace(iso,smooth=True))
for policy in ['retain','temporal']:
 tt=[Turn(0,5000,0),Turn(6000,10000,1),Turn(10000,10220,2)]
 add('controlled:missing'+policy,tt,measured(tt,11000,{0:(1,0),1:(0,1)}),11000,replace(iso,reassign_small=True,small_missing_centroid_policy=policy))
add('controlled:empty',[],[],0)
add('controlled:unknown',[Turn(0,1000,-1)],[],1000)
add('controlled:invalidturn',[Turn(-1,2000,0),Turn(0,3000,1)],[],3000)
add('controlled:hardcapmissing',[Turn(i*1000,i*1000+220,i)for i in range(9)],[],9000,iso)
tt=[Turn(i*4000,i*4000+3000,i)for i in range(9)]
add('controlled:forcedcap',tt,measured(tt,35000,{i:tuple(float(i==j)for j in range(9))for i in range(9)}),35000,iso)
for vector in [(1e308,1e308),(1e-300,1e-300),(0,0),('NaN',0),('Inf',0)]:
 add('controlled:vector'+str(vector),[Turn(0,3000,0)],[ref.EmbeddingWindow(0,1500,0,vector)],3000,iso)
for emb in [(1,0),(0,1),(1,-0.0)]:
 add('controlled:duplicate'+str(emb),[Turn(0,3000,0)],[ref.EmbeddingWindow(0,1500,0,(1,0)),ref.EmbeddingWindow(0,1500,0,emb)],3000,iso)
# Long-clock midpoints use Python arbitrary precision / Kotlin BigInteger, never overflow.
e=(1<<63)-1;tt=[Turn(e-10000,e-5000,7),Turn(e-4000,e-2800,2),Turn(e-200,e,9)]
add('controlled:longclock',tt,measured(tt,e,{7:(1,0),2:(0,1)}),e,replace(iso,reassign_small=True,min_cluster_fraction=0,small_missing_centroid_policy='temporal'))
for index in range(160):
 duration=20000;tt=[]
 for k in range(rng.randint(1,12)):
  start=rng.randrange(0,duration-200);end=min(duration,start+rng.randrange(100,5000));tt.append(Turn(start,end,rng.choice([-1,0,1,2,3,4])))
 dimension=rng.randint(2,8);vectors={s:tuple(rng.gauss(0,1)for _ in range(dimension))for s in range(5)}
 windows=measured(tt,duration,vectors)
 if windows and rng.random()<.3:windows=windows[:-1]
 if windows and rng.random()<.2:windows.append(windows[0])
 config=ref.RefineConfig(merge_threshold=rng.choice([0.,.3,.5,.7,.85]),max_speakers=rng.choice([2,4,8]),merge_similar=bool(index%2),use_eigengap=bool(index%3),reassign_small=bool(index%4),smooth=bool(index%5),complete_link_guard=bool(index%7==0),minimum_reassignment_similarity=rng.choice([None,.3,.7]),small_missing_centroid_policy=rng.choice(['retain','temporal']))
 add('random:'+str(index),tt,windows,duration,config)
for index in range(65):
 n=rng.randrange(0,25);dim=rng.randrange(2,16);vectors=[tuple(rng.gauss(0,1)for _ in range(dim))for _ in range(n)]
 cases.append({'id':'eigen:'+str(index),'kind':'estimate','centroids':vectors,'config':{'merge_threshold':rng.choice([-.2,0.,.3,.7,.85]),'max_speakers':rng.choice([1,2,4,8])}})
for n in [256,257]:
 vectors=[tuple(rng.gauss(0,1)for _ in range(8))for _ in range(n)]
 cases.append({'id':'eigen:bound'+str(n),'kind':'estimate','centroids':vectors,'config':{'merge_threshold':.3,'max_speakers':8}})
(root/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,allow_nan=False)+'\n')
expected=[]
for c in cases:
 try:
  cfg=ref.RefineConfig(**c['config'])
  if c['kind']=='estimate':row={'id':c['id'],'diagnostics':ref.estimate_speakers(c['centroids'],cfg.merge_threshold,cfg.max_speakers)}
  else:
   result=ref.refine([Turn(**t)for t in c['turns']],[ref.EmbeddingWindow(**w)for w in c['windows']],c['duration_ms'],cfg)
   row={'id':c['id'],'accepted':result.accepted,'turns':[asdict(t)for t in result.turns],'diagnostics':result.diagnostics}
 except Exception as ex:row={'id':c['id'],'error':True,'error_type':type(ex).__name__,'reason':str(ex)}
 expected.append(row)
(root/'python-output.json').write_text(json.dumps(expected,ensure_ascii=False,allow_nan=False)+'\n')
state=json.loads((root/'build-state.json').read_text());cmd=[state['jdk']+'/bin/java','-Xmx128m','-XX:+UseSerialGC','-XX:ActiveProcessorCount=2','-cp',state['runtime_classpath'],'SpeakerRefinerProbeKt',str(root/'cases.json'),str(root/'kotlin-output.json')]
with(root/'differential-java.log').open('w')as stream:rc=subprocess.run(['/usr/bin/time','-v',*cmd],stdout=stream,stderr=subprocess.STDOUT,timeout=120).returncode
if rc:print((root/'differential-java.log').read_text());raise SystemExit(rc)
actual=json.loads((root/'kotlin-output.json').read_text());assert len(actual)==len(expected)
errors=[];maxdiff=0.
def compare(a,b,path):
 global maxdiff
 if isinstance(a,bool)or isinstance(b,bool):return []if a is b else[(path,a,b)]
 if type(a)is int and type(b)is int:
  delta=abs(a-b);maxdiff=max(maxdiff,delta)
  return []if a==b else[(path,a,b)]
 if isinstance(a,(float,int))and isinstance(b,(float,int)):
  delta=abs(a-b);maxdiff=max(maxdiff,delta)
  return []if delta<=1e-9+abs(a)*1e-9 else[(path,a,b)]
 if type(a)!=type(b):return[(path,a,b)]
 if isinstance(a,dict):
  if set(a)!=set(b):return[(path+'.keys',sorted(a),sorted(b))]
  return [v for k in a for v in compare(a[k],b[k],path+'.'+k)]
 if isinstance(a,list):
  if len(a)!=len(b):return[(path+'.length',len(a),len(b))]
  return[v for i,(x,y)in enumerate(zip(a,b))for v in compare(x,y,path+'['+str(i)+']')]
 return []if a==b else[(path,a,b)]
for old,new in zip(expected,actual):
 if old.get('error')or new.get('error'):
  diff=[]if old.get('error')is True and new.get('error')is True else[('error-status',old,new)]
 else:diff=compare(old,new,old['id'])
 if diff:errors.append({'id':old['id'],'differences':diff[:12]})
report={'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),'cases':len(cases),'real_cases':23,'controlled_refine_cases':sum(c['kind']=='refine'and c['id'].startswith('controlled:')for c in cases),'random_refine_cases':160,'spectral_cases':67,'numeric_tolerance':'1e-9 absolute +1e-9 relative; integer/boolean/string/list structure and returned native turn clocks/labels separately exact','max_numeric_absolute_difference':maxdiff,'cases_with_differences':len(errors),'differences':errors,'source_proof':sourceproof,'python_sha256':digest(ref.__file__),'kotlin_sha256':digest(root/'SpeakerRefiner.kt'),'case_fixture_sha256':digest(root/'cases.json'),'python_output_sha256':digest(root/'python-output.json'),'kotlin_output_sha256':digest(root/'kotlin-output.json'),'scope':'Standalone pure Kotlin/Python differential of23actual real-vector dev/oldholdout/reserve cases plus controlled/random/eigensystem cases. No audio/NN/reference/model inputs; no app/Gradle changes.'}
# Exact output semantics matter independently from harmless floating diagnostics.
report['exact_turn_differences']=[{'id':a['id'],'expected':a.get('turns'),'actual':b.get('turns')}for a,b in zip(expected,actual)if a.get('turns')!=b.get('turns')or a.get('accepted')!=b.get('accepted')]
(root/'differential-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:report[k]for k in ['cases','real_cases','controlled_refine_cases','random_refine_cases','spectral_cases','max_numeric_absolute_difference','cases_with_differences','exact_turn_differences']},ensure_ascii=False))
if errors:print(json.dumps(errors[:5],ensure_ascii=False,indent=2))
raise SystemExit(bool(errors or report['exact_turn_differences']))
