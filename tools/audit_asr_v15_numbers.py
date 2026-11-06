#!/usr/bin/env python3
"""Score saved hypotheses only; no inference and no bespoke numeral normalizer.

The no-digits-reference filter is fixed and symmetric across models. Predicted
digits are retained and scored literally, so ITN differences can still hurt v3.
"""
import argparse,collections,json,pathlib,re

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=pathlib.Path,nargs='+',required=True);p.add_argument('--level',type=float,default=1);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
    rows=[]
    for path in a.input:
        for r in json.loads(path.read_text())['asr']:
            if r['level']==a.level and r['method']=='greedy_search':rows.append(r)
    assert len({(r['id'],r['model']) for r in rows})==len(rows),'Duplicate scored file/model'
    out={'method':'Saved hypotheses only; symmetric filter excludes any reference containing a Unicode digit. No normalization of spoken numbers. Predicted digits still count as different tokens from spoken-number words. Compare equal file counts and input gain policies only.','level':a.level,'inputs':[str(p) for p in a.input],'summaries':[],'digitReferenceCases':[]}
    for label,predicate in [('all',lambda r:True),('no_digits_reference',lambda r:not re.search(r'\d',r['reference']))]:
        groups=collections.defaultdict(list)
        for r in rows:
            if predicate(r):groups[r['model']].append(r)
        for model,records in groups.items():
            errors=sum(r['wordErrors'] for r in records);words=sum(r['referenceWords'] for r in records)
            out['summaries'].append({'subset':label,'model':model,'files':len(records),'referenceWords':words,'wordErrors':errors,'wer':errors/words,'cer':sum(r['charErrors'] for r in records)/sum(r['referenceChars'] for r in records),'hypothesesWithDigits':sum(bool(re.search(r'\d',r['hypothesis'])) for r in records)})
    out['digitReferenceCases']=[{'id':r['id'],'model':r['model'],'reference':r['reference'],'hypothesis':r['hypothesis'],'wordErrors':r['wordErrors']} for r in rows if re.search(r'\d',r['reference'])]
    a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out['summaries'],indent=2))

if __name__=='__main__':main()
