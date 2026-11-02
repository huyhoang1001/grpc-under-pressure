#!/usr/bin/env python3
"""Post-run audit and common-window extraction of preregistered quantities.
Does not modify any raw measurement, original verifier output, or frozen analysis.
"""
import collections,csv,hashlib,importlib.util,itertools,json,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[5];OUT=ROOT/'experiments/003/results/stage6'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def area(times,values,end):
 # Independent interval representation, including initial zero and cutoff.
 if not times:return 0
 points=[0]+[min(end,max(0,t)) for t in times]+[end]
 states=[0]+values
 return sum((b-a)*state for a,b,state in zip(points,points[1:],states))
def main():
 frozen=read(OUT/'FROZEN-MANIFEST.json');matrix=read(OUT/'MATRIX-COMBINED.json');analysis=read(OUT/'analysis/RESULTS.json');plan=read(OUT/'RUN-PLAN.json')
 frozenB=read(OUT/'FROZEN-MANIFEST-B2.json');planB=read(OUT/'RUN-PLAN-B2.json')
 assert sha(OUT/'FROZEN-MANIFEST-B2.json')==matrix['frozen_B2_sha256']
 assert all(sha(ROOT/path)==h for path,h in frozenB['source_sha256'].items())
 assert all(sha(OUT/path)==h for path,h in matrix['input_matrices'].items())
 assert sha(OUT/'FROZEN-MANIFEST.json')==matrix['frozen_sha256']
 assert all(sha(ROOT/path)==h for path,h in frozen['source_sha256'].items())
 spec=importlib.util.spec_from_file_location('verifier',ROOT/'experiments/003/secondary/fixtures/verify.py');V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)
 specB=importlib.util.spec_from_file_location('verifier_b2',ROOT/'experiments/003/secondary/fixtures/verify_b2.py');VB=importlib.util.module_from_spec(specB);specB.loader.exec_module(VB)
 rows=[];byblock={}
 for block in matrix['blocks']:
  if block['status']!='VALID':continue
  declared=next(x for x in (planB if block['study']=='B' else plan)['blocks'] if x['study']==block['study'] and x['block']==block['block'])
  assert block['cases']==declared['cases'] and block['seed']==declared['seed']
  for name,item in block['runs'].items():
   run=ROOT/item['directory'];replay=(VB if block['study']=='B' else V).verify(run);case_frozen=frozenB if block['study']=='B' else frozen;assert replay['verdict']=='PASS'
   m=read(run/'verification.json');s=read(run/'server/server-ledger.json');w=read(run/'workload.json');clock=read(run/'server/clock.json')
   assert m['frozen_manifest_sha256']==sha(OUT/('FROZEN-MANIFEST-B2.json' if block['study']=='B' else 'FROZEN-MANIFEST.json'))
   assert sha(run/'workload.json')==sha(OUT/f'workloads/{m["study"]}.json')
   assert m['binary_sha256']==frozen['binary_sha256']==case_frozen['binary_sha256'] and m['source_commit']==case_frozen['source_commit'] and m['source_sha256']==case_frozen['source_sha256']
   completed={o['message_id']:o for o in s['originals'] if o['terminal']['outcome']==1};useful={i for i,o in completed.items() if o['terminal']['offset_ns']<=w['originals'][i]['deadline_offset_ns']}
   expected=next(r for r in analysis['rows'] if r['name']==name and r['block']==block['block'])
   assert len(useful)==expected['U']==replay['U']
   se=[json.loads(x) for x in (run/'server/server-events.jsonl').read_text().splitlines()];ce=[];reports=[]
   for cid in range(m['clients']):
    c=read(run/f'client-{cid}/report.json');reports.append(c);ce.extend([{**json.loads(x),'owner':cid} for x in (run/f'client-{cid}/events.jsonl').read_text().splitlines()])
   retry_times=[e['offset_ns'] for e in ce if e['kind']=='attempt_initiated' and e['attempt_number']>1 and 12_000_000_000<=e['offset_ns']<24_000_000_000]
   # Count unordered retry pairs sharing a bin, independently of factorial sum.
   grouped=collections.defaultdict(list)
   for t in retry_times:grouped[(t-12_000_000_000)//20_000_000].append(t)
   collision=sum(len(a)*(len(a)-1)//2 for a in grouped.values())/(len(retry_times)*(len(retry_times)-1)//2) if len(retry_times)>=2 else None
   assert collision==expected['retry_burst20']['collision']
   end=39_000_000_000;server_payload=area([e['offset_ns'] for e in se],[e['occupied']*16384 for e in se],end)
   assert server_payload==expected['payload_byte_ns_common_39']
   ce.sort(key=lambda e:(e['commit_offset_ns'],e['owner'],e['seq']));state={cid:(0,0) for cid in range(m['clients'])};pending=[];outstanding=[]
   for e in ce:
    state[e['owner']]=(e['pending'],e['outstanding']);pending.append(sum(x[0] for x in state.values()));outstanding.append(sum(x[1] for x in state.values()))
   cpu={}
   for role in ['server']+[f'client-{cid}' for cid in range(m['clients'])]:
    b=clock['start'] if role=='server' else reports[int(role.split('-')[1])]['client']['ClockStart'];epoch=(b['epoch_min_ns']+b['epoch_max_ns'])//2 if role=='server' else (b['EpochMinNS']+b['EpochMaxNS'])//2
    samples=list(csv.DictReader((run/f'{role}-metrics.csv').open()));start=next(x for x in samples if int(x['host_monotonic_ns'])>=epoch);finish=next(x for x in samples if int(x['host_monotonic_ns'])>=epoch+end)
    cpu[role]=int(finish['cpu_user_ns'])+int(finish['cpu_system_ns'])-int(start['cpu_user_ns'])-int(start['cpu_system_ns'])
   supplementary={'common_window_ns':[0,end],'server_payload_byte_ns':server_payload,'staging_payload_byte_ns':area([e['offset_ns'] for e in se],[e['resources']['staging']*16384 for e in se],end),'client_pending_item_ns':area([max(0,e['commit_offset_ns']) for e in ce],pending,end),'client_outstanding_item_ns':area([max(0,e['commit_offset_ns']) for e in ce],outstanding,end),'cpu_sampled_common_window_ns':cpu}
   supplementary['worker_occupied_by_disposition_ns']={str(code):sum(o['terminal']['worker_service_ns'] for o in s['originals'] if o['terminal']['outcome']==code) for code in range(1,7)}
   supplementary['completed_service_by_start_phase']={phase:{'n':len(values),'median_ns':float(np.median(values)) if values else None} for phase,lo,hi in [('initial',0,12e9),('slowdown',12e9,24e9),('recovery',24e9,36e9),('drain',36e9,m['cutoff_ns'])] for values in [[o['terminal']['worker_service_ns'] for o in completed.values() if lo<=o['start_ns']<hi]]}
   rows.append({'study':block['study'],'block':block['block'],'name':name,'directory':item['directory'],'validity_replay':'PASS','independent_U':len(useful),'retry_collision':collision,'raw_verification_sha256':sha(run/'independent-verification.json'),'supplementary_common_39':supplementary})
   byblock.setdefault((block['study'],block['block']),{})[name]=len(useful)
 bootstrap={}
 for label,value in analysis['contrasts'].items():
  if label.startswith('a'):
   study,pair=label.split(':');a,b=pair.split('-minus-');keys=sorted(k for k in byblock if k[0]=='A');pairs=[(study+'-'+a,study+'-'+b) for _ in keys]
  elif label.startswith('deadline'):
   p=label.split(':')[1];keys=sorted(k for k in byblock if k[0]=='A');pairs=[('a5000-'+p,'a500-'+p) for _ in keys]
  else:keys=sorted(k for k in byblock if k[0]=='B');pairs=[('b-deterministic','b-jitter') for _ in keys]
  if len(keys)!=5:continue
  values=np.array([byblock[k][a]-byblock[k][b] for k,(a,b) in zip(keys,pairs)],dtype=float)/2880
  boot=np.array(list(itertools.product(values,repeat=5))).mean(axis=1);interval=np.percentile(boot,[2.5,97.5],method='linear');expected=value['U_over_N']
  assert np.allclose(values,expected['values'],rtol=0,atol=1e-15) and np.allclose(interval,expected['interval95'],rtol=0,atol=1e-15)
  bootstrap[label]={'PASS':True,'values':values.tolist(),'interval95':interval.tolist()}
 historical=json.loads((ROOT/'experiments/003/results/stage5/SHA256SUMS.json').read_text());assert all(sha(ROOT/path)==v['sha256'] for path,v in historical.items())
 modified=subprocess.check_output(['git','diff','--diff-filter=MD','--name-only',frozen['primary_baseline_commit'],'--','experiments'],cwd=ROOT,text=True).splitlines();assert not modified,modified
 output={'verdict':'PASS','matrix_status':matrix['status'],'runs_replayed':len(rows),'rows':rows,'paired_U_reanalysis':bootstrap,'stage5_checksums_unchanged':len(historical),'modified_or_deleted_historical_files':modified,'source_commit':frozen['source_commit'],'audit_sha256':sha(Path(__file__)),'note':'Common39 quantities implement the human preregistration; no endpoint/exclusion/hypothesis is redefined. CPU windows remain sampled/quantized.'}
 (OUT/'analysis/OFFLINE-AUDIT.json').write_text(json.dumps(output,indent=2)+'\n');print('PASS: offline validity/identity/U/burst/paired audit;',len(rows),'runs; primary unchanged')
if __name__=='__main__':main()
