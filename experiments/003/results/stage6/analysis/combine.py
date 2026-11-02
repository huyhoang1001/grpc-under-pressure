#!/usr/bin/env python3
"""Derived view only: preserve both original raw matrices and their exclusions."""
import hashlib,json
from pathlib import Path
OUT=Path(__file__).resolve().parent.parent
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 a=read(OUT/'MATRIX.json');b=read(OUT/'MATRIX-B2.json');aa=[x for x in a['blocks'] if x['study']=='A'];bb=b['blocks']
 complete=sum(x['status']=='VALID' for x in aa)==sum(x['status']=='VALID' for x in bb)==5 and b['status']=='COMPLETE'
 result={'status':'COMPLETE' if complete else 'INCOMPLETE','derived_view_only':True,'seed_amendment':'B2','input_matrices':{'MATRIX.json':sha(OUT/'MATRIX.json'),'MATRIX-B2.json':sha(OUT/'MATRIX-B2.json')},'frozen_sha256':a['frozen_sha256'],'frozen_B2_sha256':b['frozen_sha256'],'blocks':aa+bb,'attempts':a['attempts']+b['attempts'],'original_B_plan_excluded':True,'original_B_blocks':[x for x in a['blocks'] if x['study']=='B']}
 (OUT/'MATRIX-COMBINED.json').write_text(json.dumps(result,indent=2)+'\n')
 exclusions={'input_ledgers':['EXCLUSIONS.json','EXCLUSIONS-B2.json'],'attempts':result['attempts'],'excluded_blocks':[x for x in a['blocks']+b['blocks'] if x['status']!='VALID'],'original_B_plan_superseded_before_traffic':True,'reason':'Source-inspection seed stream overlap; preserved boundary startup is not a valid unfavorable measurement. Only original A and independently preregistered B2 pairs enter analysis.','primary_stage5_runs_used':0}
 (OUT/'EXCLUSIONS-COMBINED.json').write_text(json.dumps(exclusions,indent=2)+'\n');print('Combined matrix',result['status'],'valid A',sum(x['status']=='VALID' for x in aa),'valid B2',sum(x['status']=='VALID' for x in bb))
if __name__=='__main__':main()
