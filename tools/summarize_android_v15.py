#!/usr/bin/env python3
"""Summarize actual AndroidJUnit status blocks, retaining failures and the latest result per case."""
import argparse,json,pathlib,re
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
records=[];uncompleted=[]
for path in sorted(a.directory.glob('*.log'),key=lambda x:(re.search(r'(\d{8}T\d{6})',x.name).group(1) if re.search(r'(\d{8}T\d{6})',x.name) else '',x.name)):
 fields={};ended=False
 for line in path.read_text(errors='replace').splitlines():
  match=re.match(r'INSTRUMENTATION_STATUS: (class|test)=(.*)',line)
  if match:fields[match[1]]=match[2]
  match=re.match(r'INSTRUMENTATION_STATUS_CODE: (-?\d+)',line)
  if match:
   code=int(match[1])
   if code!=1 and fields.get('class') and fields.get('test'):
    records.append({'case':fields['class']+'#'+fields['test'],'code':code,'result':'PASS' if code==0 else 'SKIP' if code in (-3,-4) else 'FAIL','log':path.name})
   fields={}
  if re.match(r'INSTRUMENTATION_CODE:',line):ended=True
 if not ended:uncompleted.append(path.name)
latest={r['case']:r for r in records}
result={'scope':str(a.directory),'testInvocations':len(records),'uniqueCases':len(latest),'latestPassed':sum(r['result']=='PASS' for r in latest.values()),'latestFailed':sum(r['result']=='FAIL' for r in latest.values()),'latestSkipped':sum(r['result']=='SKIP' for r in latest.values()),'historicalFailedInvocations':[r for r in records if r['result']=='FAIL'],'uncompletedLogs':uncompleted,'cases':list(latest.values())}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False));print(json.dumps({k:v for k,v in result.items() if k not in ['cases','historicalFailedInvocations']},ensure_ascii=False))
