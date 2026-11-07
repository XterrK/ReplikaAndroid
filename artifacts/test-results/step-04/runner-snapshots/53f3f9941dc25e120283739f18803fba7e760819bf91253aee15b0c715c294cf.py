import copy,hashlib,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from tools.eval import score as scorer
repo=Path.cwd(); step=repo/'artifacts/test-results/step-04'; source_hashes={}; checks=0; resolutions={}; rows=[]
def digest(p):
 p=Path(p).resolve();h=hashlib.sha256(p.read_bytes()).hexdigest()
 if str(p) in source_hashes: assert source_hashes[str(p)]==h,('changed',str(p))
 source_hashes[str(p)]=h;return h
def read(p):
 digest(p);return json.loads(Path(p).read_text())
def check(condition,label):
 global checks
 checks+=1
 if not condition:raise AssertionError(label)
def pinned_code(rel,h):
 current=repo/rel
 if digest(current)==h:p=current
 else:p=step/'runner-snapshots'/(h+'.py');check(p.is_file(),'Missing historic source snapshot '+rel)
 check(digest(p)==h,('code pin',rel));resolutions[rel+'@'+h]=str(p.relative_to(repo))
def record(folder,case,rh):
 c=read(folder/'case.json');e={k:read(folder/k) for k in ['reference.json','hypothesis.json','diagnostics.json','metrics.json']};hs={k:digest(folder/k) for k in e}
 for k in ['id','split','duration_ms','audio_sha256']:check(c[k]==case[k],(case['id'],'record',k))
 check(c['reference_sha256']==rh==hs['reference.json'],'record reference pin')
 check(c['evidence_sha256']==hs,'evidence hash map');check(c['metrics']==e['metrics.json'],'record metrics')
 if 'turns_sha256' in c:
  check(digest(folder/'turns.json')==c['turns_sha256'],'saved turns SHA');check(read(folder/'turns.json')==e['diagnostics.json']['diarizationTurns'],'saved turns value')
 return c,e,{'case.json':digest(folder/'case.json'),**hs}
def literal(doc):return [token for row in sorted(doc['transcript'],key=lambda r:(r['start_ms'],r['end_ms'])) for token in row['text'].split()]
code_map={'runner':'refine_sweep.py','refiner':'speaker_refiner.py','diar_helpers':'diar_sweep.py','word_helpers':'vad_words.py','scorer':'score.py','baseline_helpers':'pipeline.py'}
cohorts=[('original',repo/'benchmark/eval/manifest.json',Path('/home/egor/replika-toolchain/eval-audio'),repo/'artifacts/test-results/step-03/context600-selected-host',13),('reserve',repo/'benchmark/eval-reserve/manifest.json',Path('/home/egor/replika-toolchain/eval-reserve-audio'),repo/'artifacts/test-results/step-03/reserve-context600-host',10)]
freeze=read(step/'candidate-c1-validation-freeze.json');fullcfg=read(repo/'configs/eval/c1-refined-selected.json'); model_pins_checked={}; runs={}; total_slices=total_tokens=total_windows=total_words=0; counter=Counter()
for cohort,manifest,audio_root,asrroot,expected in cohorts:
 full=step/('candidate-c1-full-'+cohort);fm=read(full/'run.json');fp=fm['fingerprint'];corpus=read(manifest);cases=corpus['files'];am=read(asrroot/'run.json')
 check(fm['status']=='COMPLETE' and fm['new_model_inference'] is True,'full run completion/inference')
 check(len(cases)==expected and set(fp['selected_ids'])=={c['id'] for c in cases},'complete exact cohort')
 check(digest(manifest)==fp['manifest_sha256'],'manifest pin');check(read(full/'manifest.json')==corpus,'export manifest')
 check(fullcfg==fm['config']==read(full/'config.json') and digest(repo/'configs/eval/c1-refined-selected.json')==fp['config_sha256'],'full config pin')
 check(fp['config_sha256']==digest(repo/'configs/eval/c1-refined-selected.json') and fm['config']['candidate_freeze_sha256']==digest(step/'candidate-c1-validation-freeze.json'),'frozen policy link')
 check(fp['model_lock_sha256']==digest(repo/'app/src/main/assets/models-lock.json'),'model lock pin')
 check(am['status']=='COMPLETE' and am['config']['pipeline']=='vad_words_v1' and am['config']['pre_roll_ms']==600 and am['config']['expected_speakers']==-1,'D auto context600 source')
 for rel,h in fp['code'].items():pinned_code(rel,h)
 for rel,h in fp['packaged_models'].items():
  p=repo/'model-pack'/rel
  if str(p) not in model_pins_checked:model_pins_checked[str(p)]=digest(p)
  check(model_pins_checked[str(p)]==h,'actual packaged model SHA')
 check(fp['external_embedding']['sha256']==freeze['model']['sha256'],'external model freeze pin')
 for case in cases:
  cid=case['id'];dev=case['split']=='dev'; cached=step/('candidate-c1-reserve-refined' if cohort=='reserve' else 'refine-resnet34-050-temporal-guard0p7' if dev else 'candidate-c1-holdout-refined')
  sdroot=step/('candidate-c1-reserve-diar' if cohort=='reserve' else 'auto-wespeaker-resnet34-lm' if dev else 'candidate-c1-holdout-diar')
  cm=read(cached/'run.json');cfp=read(cached/'source-fingerprint.json');nm=read(sdroot/'run.json')
  check(cm['status']==nm['status']=='COMPLETE' and not cm['failures'] and not cm['pending_cases'],'complete research source')
  check(hashlib.sha256(json.dumps(cfp,sort_keys=True,allow_nan=False).encode()).hexdigest()==cm['source_fingerprint_sha256'],'canonical research fingerprint')
  check(cfp['config']==cm['config'] and cfp['asr_run']==digest(asrroot/'run.json') and cfp['diar_run']==digest(sdroot/'run.json') and cfp['manifest']==digest(manifest),'research run links')
  for key,name in code_map.items():pinned_code('tools/eval/'+name,cfp[key])
  reference=manifest.parent/case['reference'];rh=digest(reference);audio=audio_root/case['audio'];ah=digest(audio)
  check(rh==fp['references'][cid] and ah==case['audio_sha256']==fp['audio'][cid],'actual source input SHA')
  f,fe,fh=record(full/cid,case,rh);c,ce,ch=record(cached/'tau-0p7'/cid,case,rh);n,ne,nh=record(sdroot/'auto-0p50'/cid,case,rh);a,ae,ash=record(asrroot/cid,case,rh)
  links={'diar':nh,'asr':ash,'reference':rh,'original_audio':ah};check(cfp['cases'][cid]==c['source_evidence_sha256']==ce['diagnostics.json']['sourceEvidence']==links,'per-case source links')
  d=fe['diagnostics.json'];cd=ce['diagnostics.json'];nd=ne['diagnostics.json'];ad=ae['diagnostics.json'];metric=fe['metrics.json'];cached_metric=ce['metrics.json']
  check(n['mode']=='auto' and n['model_id']=='wespeaker_resnet34_lm' and nd['numClustersPassed']==-1 and nd['threshold']==.5 and nd['windowShiftRatio']==.1 and nd['threads']==2,'research automatic native policy')
  check(d['pipelineVariant']=='refined_words_v1' and d['expectedSpeakers']==-1 and d['config']['nativeNumClusters']==-1 and d['config']['nativeThreshold']==.5 and d['config']['segmentationWindowShiftRatio']==.1,'actual full policy')
  check(d['config']['refiner']==cd['refiner']['config'] and d['config']['refiner']['merge_threshold']==.7 and d['config']['refiner']['minimum_reassignment_similarity']==.7,'global refiner config')
  check(f['new_model_inference'] is True and f['new_asr_inference'] is True and f['new_diarization_inference'] is True and d['asrReplay'] is False and d['newDiarizationInference'] is True and d['newAsrInference'] is True,'actual new neural flags')
  check(d['wordAssignmentSupported'] is True and d['fallbackChunks']==0 and d['refinerAccepted'] is True and d['nativeModelCacheRetained'] is False,'actual supported complete output')
  check({x['path']:x['sha256'] for x in d['modelFiles']}==fp['packaged_models'],'actual package diag pins')
  check(d['externalEmbedding']['sha256']==fp['external_embedding']['sha256'] and d['externalEmbedding']['catalogSha256']==fp['external_embedding']['catalog_sha256'],'actual catalog embedding pin')
  check(digest(repo/'configs/eval/diar-models.json')==fp['external_embedding']['catalog_sha256'],'actual catalog SHA')
  ep=Path(d['externalEmbedding']['path']);check(digest(ep)==fp['external_embedding']['sha256'],'actual external weight SHA')
  for rel,h in d['sourceFiles'].items():check(fp['code'][rel]==h,'per-case/full code pins')
  check(d['audioSha256']==ah and d['audioMs']==case['duration_ms'],'decoded audio pins')
  results={'jury_json':fe['hypothesis.json']==ce['hypothesis.json'],'jury_bytes_sha':fh['hypothesis.json']==ch['hypothesis.json'],'literal_tokens':literal(fe['hypothesis.json'])==literal(ce['hypothesis.json'])==literal(ae['hypothesis.json']),'raw_native_turns':d['rawDiarizationTurns']==nd['rawDiarizationTurns'],'stable_native_turns':d['nativeDiarizationTurns']==nd['diarizationTurns'],'refined_turns':d['diarizationTurns']==d['refinedDiarizationTurns']==cd['diarizationTurns'],'actual_clean_vectors':d['cleanEmbeddingWindows']==nd['cleanEmbeddingWindows'],'refiner_diagnostics':d['refiner']==cd['refiner'],'asr_slices':len(d['asrSlices'])==len(ad['asrSlices']) and all(all(x[k]==y[k] for k in ['startMs','endMs','text','tokens','timestamps']) for x,y in zip(d['asrSlices'],ad['asrSlices']))}
  for field in ['originalPcmPeak','recognitionInputGain','vadDetectorGain','vadPrimarySpanCount','vadRescueAttempted','vadRescueApplied','vadRescueRms','vadRescueRmsSamples','vadRescueSpanCount','vadSpans','asrChunks']:
   results['vad_gain.'+field]=d[field]==ad[field]
  check(d['asrForwardCalls']==len(d['asrSlices']) and d['embeddingForwardCalls']==len(d['cleanEmbeddingWindows']) and len(d['asrSlices'])==len(d['asrChunks']),'per stage forward counts')
  for k,v in cached_metric.items():
   if k=='rtf':continue
   if k=='inputs':
    left={x:y for x,y in metric[k].items() if x!='processing_ms'};right={x:y for x,y in v.items() if x!='processing_ms'}
    results['metric.inputs_except_processing_ms']=left==right
   else:results['metric.'+k]=metric[k]==v
  fresh=scorer.score(fe['reference.json'],fe['hypothesis.json'],case['duration_ms'])
  for k,v in fresh.items():
   if k in ['rtf','inputs']:continue
   check(metric[k]==v,(cid,'rescored metric',k))
  for collar in [0,250]:
   def native_rows(t):return [{'speaker_id':'native_'+str(x['speakerId']),'start_ms':x['startMs'],'end_ms':x['endMs'],'text':''} for x in t]
   check(scorer.der(fe['reference.json']['transcript'],native_rows(d['diarizationTurns']),case['duration_ms'],collar)==metric[f'native_der_collar_{collar}ms'],'fresh final DER')
   check(metric[f'unrefined_native_der_collar_{collar}ms']==ne['metrics.json'][f'native_der_collar_{collar}ms'],'unrefined native DER')
  for key,ok in results.items():check(ok,(cid,key));counter[key]+=int(ok)
  total_slices+=len(d['asrSlices']);total_tokens+=sum(len(x['tokens']) for x in d['asrSlices']);total_windows+=len(d['cleanEmbeddingWindows']);total_words+=len(d['words'])
  rows.append({'id':cid,'split':case['split'],'full_run':str(full.relative_to(repo)),'cached_refined_run':str(cached.relative_to(repo)),'native_run':str(sdroot.relative_to(repo)),'actual_asr_slices':len(d['asrSlices']),'actual_tokens':sum(len(x['tokens']) for x in d['asrSlices']),'real_clean_vectors':len(d['cleanEmbeddingWindows']),'all_equivalent':True,'equivalence':results,'raw_errors':metric['wer_raw']['errors'],'reference_words':metric['wer_raw']['reference_tokens'],'full_evidence_sha256':fh,'cached_evidence_sha256':ch})
 runs[cohort]={'full_run_sha256':digest(full/'run.json'),'full_config_sha256':fp['config_sha256'],'cases':expected,'new_model_inference':fm['new_model_inference'],'raw_errors':sum(x['raw_errors'] for x in rows if (x['id'].startswith('reserve-'))==(cohort=='reserve'))}
check(len(rows)==23,'complete 23 case audit')
for p,h in source_hashes.copy().items():check(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,('source changed during audit',p))
result={'schema_version':1,'status':'PASS','at':datetime.now(timezone.utc).isoformat(),'scope':'Read-only per-case equivalence of completed actual full C1 inference against frozen research SD/refiner and actual saved D ASR evidence. Not a C2/native/phone/speed acceptance.','cases':23,'checks':checks,'failures':[],'all_cases_exact':True,'neural_inference_by_auditor':False,'full_runs':runs,'equality_counts':dict(counter),'actual_full_evidence_totals':{'asr_slices':total_slices,'tokens':total_tokens,'word_proxies':total_words,'clean_vectors':total_windows},'metric_scope':'Every common core metric including lexical/punctuation/cpWER/native/projected DER and segment timing proxy matches per case. Performance RTF/processing/stage/wall timing ignored; no aggregate cancellation can mask lexical/turn differences. All standard metrics and final DER independently rescored for all23.','history_scope':'Completed C1 run source pins resolve to preserved snapshots for pipeline_refined/run_refined; current modules may add explicit C2. Historical proof is not rewritten.','source_version_resolutions':resolutions,'source_sha256':source_hashes,'rows':rows}
p=step/'full-c1-equivalence-audit.json';p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'PASS','cases':23,'checks':checks,'counts':dict(counter),'totals':result['actual_full_evidence_totals'],'audit_sha256':hashlib.sha256(p.read_bytes()).hexdigest()},ensure_ascii=False))
