#!/usr/bin/env python3
"""Post-matrix audit: independent endpoint/paired arithmetic and unchanged gate replay.
No new endpoint or exclusion rule; does not modify original run artifacts.
"""
import hashlib,importlib.util,itertools,json,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[5]
OUT=ROOT/'experiments/003/results/stage5'
def read(p):return json.loads(p.read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 frozen=read(OUT/'FROZEN-MANIFEST.json');plan=read(OUT/'RUN-PLAN.json');matrix=read(OUT/'MATRIX.json');analysis=read(OUT/'analysis/RESULTS.json')
 assert matrix['status']=='COMPLETE' and len(matrix['blocks'])==5
 assert digest(OUT/'FROZEN-MANIFEST.json')==matrix['frozen_sha256']
 assert all(digest(ROOT/p)==h for p,h in frozen['source_sha256'].items())
 spec=importlib.util.spec_from_file_location('verify',ROOT/'experiments/003/fixtures/verify-stage5.py');verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
 rows=[];byblock={}
 for block in matrix['blocks']:
  pblock=next(b for b in plan['blocks'] if b['block']==block['block'])
  assert block['status']=='VALID' and block['attempt']==1
  assert block['order']==pblock['order'] and block['seed']==pblock['jitter_seed']
  byblock[block['block']]={}
  for policy,path in block['runs'].items():
   run=ROOT/path;assert digest(run/'workload.json')==frozen['workload_sha256']
   report=read(run/'client-report.json');server=read(run/'server/server-ledger.json');work=read(run/'workload.json')
   original={x['message_id']:x for x in server['originals']};assert len(original)==len(server['originals'])
   useful={i for i,o in original.items() if o['terminal']['outcome']==1 and o['terminal']['offset_ns']<=work['originals'][i]['deadline_offset_ns']}
   assert len(work['originals'])==2880 and report['server_reconciliation']['U']==len(useful)
   expected=next(r for r in analysis['runs'] if r['block']==block['block'] and r['policy']==policy)
   assert expected['U']==len(useful) and expected['U_over_N']==len(useful)/2880
   attempts={}
   for a in server['attempts']:attempts.setdefault(a['message_id'],[]).append(a)
   conversions=[]
   for i in useful:
    aa=sorted(attempts[i],key=lambda a:a['attempt_number'])
    if len(aa)>1:
     assert aa[-1]['terminal']['outcome']==1 and all(a['terminal']['outcome']==2 for a in aa[:-1])
     conversions.append(i)
   assert len(conversions)==expected['retry_converted_on_time_originals']
   replay=verifier.verify(run);assert replay['verdict']=='PASS'
   assert sum(report['server_reconciliation']['Counts'].values())==2880
   byblock[block['block']][policy]=len(useful)
   rows.append({'block':block['block'],'policy':policy,'U':len(useful),'N':2880,'validity_replay':'PASS','retry_conversion_original_ids':conversions,'original_verification_sha256':digest(run/'primary-verification.json'),'workload_sha256':digest(run/'workload.json')})
 pairs={}
 for left,right in plan['primary_analysis']['pairs']:
  # Independent integer count differences, then divide once. numpy percentile differs
  # from the frozen implementation's handwritten quantile code.
  diffs=np.array([byblock[b][left]-byblock[b][right] for b in sorted(byblock)],dtype=float)/2880
  boot=np.array(list(itertools.product(diffs,repeat=5))).mean(axis=1)
  interval=np.percentile(boot,[2.5,97.5],method='linear');key=left+'-minus-'+right
  frozen_pair=analysis['paired'][key]['U_over_N']
  assert np.allclose(diffs,frozen_pair['values'],rtol=0,atol=1e-15)
  assert np.allclose(interval,frozen_pair['interval95'],rtol=0,atol=1e-15)
  assert abs(float(diffs.mean())-frozen_pair['mean'])<1e-15
  pairs[key]={'count_differences':[byblock[b][left]-byblock[b][right] for b in sorted(byblock)],'fraction_mean':float(diffs.mean()),'interval95':interval.tolist(),'PASS':True}
 protected=subprocess.run(['git','diff','--diff-filter=MD','--name-only',frozen['application_baseline_commit'],'--','experiments/001','experiments/002','experiments/003'],cwd=ROOT,text=True,capture_output=True,check=True).stdout.splitlines()
 allowed={'experiments/003/STAGE5-PLAN.md',*[str((ROOT/'experiments/003/fixtures'/p).relative_to(ROOT)) for p in ['stage5.py','primary-run.py','verify-stage5.py','analyze-stage5.py']],*[str((OUT/p).relative_to(ROOT)) for p in ['RUN-PLAN.json','WORKLOAD.json','preflight.log']]}
 assert not(set(protected)-allowed),protected
 result={'verdict':'PASS','timing':'post-matrix; no additional primary runs','run_count':len(rows),'rows':rows,'paired_primary_reanalysis':pairs,'frozen_source_hashes_unchanged':True,'historical_tracked_changes_other_than_preregistration':[],'baseline':frozen['application_baseline_commit'],'current_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'audit_script_sha256':digest(Path(__file__))}
 (OUT/'analysis/OFFLINE-AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
 print('PASS: 20 validity replays, independent unique U and six paired bootstrap comparisons; historical artifacts unchanged')
if __name__=='__main__':main()
