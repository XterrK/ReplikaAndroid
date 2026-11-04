#!/usr/bin/env python3
"""Validate the actual ReplikaPerf log schema; never consume general-device logs."""
import argparse,json,pathlib,re
p=argparse.ArgumentParser();p.add_argument('log',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
allowed={'run','stage','ms','pssKb','javaUsedBytes','thermalStatus','outcome','backend','threads','vadThreads','audioMs','mode'}
stages={'start','finish','thermal','config','cooling','provisioningWaitMs','validationMs','decodeMs','metadataPersistenceMs','vadLoadMs','vadMs','diarizationMs','diarizationLoadMs','diarizationReadMs','diarizationInferenceMs','alignmentMs','asrLoadMs','asrReadMs','asrInferenceMs','asrMs','persistenceMs'}
count=0;runs=set();errors=[]
for i,line in enumerate(a.log.read_text().splitlines(),1):
 if 'ReplikaPerf:' not in line:continue
 try:
  row=json.loads(line.split('ReplikaPerf:',1)[1].strip());count+=1
  assert set(row)<=allowed,'nonallowlisted field'
  assert re.fullmatch(r'[0-9a-f-]{36}',row['run']),'invalid run id'
  assert row['stage'] in stages,'nonallowlisted stage'
  runs.add(row['run'])
  for key,value in row.items():
   if key not in {'run','stage','outcome','backend','mode'}:assert type(value) is int,'unexpected nonnumeric telemetry'
  if 'backend' in row:assert row['backend'] in {'giga-v2','whisper-tiny'}
  if 'mode' in row:assert row['mode'] in {'single','fixed','automatic'}
 except (ValueError,AssertionError,KeyError) as e:errors.append({'line':i,'reason':str(e)})
report={'events':count,'runs':len(runs),'errors':errors,'allowlistedFieldsOnly':not errors and count>0,'scope':'Observed ReplikaPerf records only; arbitrary OEM/native system logs were not audited'}
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));assert report['allowlistedFieldsOnly']
