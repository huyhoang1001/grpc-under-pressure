#!/usr/bin/env python3
"""Stage7 read-only evidence review. No server/client/build/performance invocation.
New arithmetic reads raw events/ledgers; archived gate functions are additionally
replayed in memory, separately labeled as reused checks. Outputs only Stage7.
"""
import argparse,collections,csv,datetime,hashlib,importlib.util,itertools,json,math,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
import numpy as np
ROOT=Path(__file__).resolve().parents[4];BASE=ROOT/'experiments/003/results';DEST=BASE/'stage7';REVIEWED='25771cda76abfbcee32f994841a67e900efe5833';N=2880

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p):return str(Path(p).relative_to(ROOT))
def events(p):return [json.loads(x) for x in p.read_text().splitlines()]
def dist(xs):
 return {'n':len(xs),**{name:float(np.quantile(xs,q,method='linear')) if xs else None for name,q in [('p50',.5),('p95',.95),('p99',.99)]}}
def paired(xs):
 if len(xs)!=5 or any(x is None for x in xs):return {'n':len(xs),'values':xs,'mean':None,'interval95':None}
 a=np.asarray(xs,dtype=float);idx=np.asarray(list(itertools.product(range(5),repeat=5)));means=a[idx].mean(axis=1)
 return {'n':5,'values':xs,'mean':float(a.mean()),'median':float(np.median(a)),'positive':int((a>0).sum()),'negative':int((a<0).sum()),'interval95':np.quantile(means,[.025,.975],method='linear').tolist()}
def close(a,b):
 assert a is not None and b is not None and math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12),(a,b)
def verify_pair(actual,archived):
 close(actual['mean'],archived['mean'])
 assert np.allclose(actual['values'],archived['values'],rtol=0,atol=1e-12)
 assert np.allclose(actual['interval95'],archived['interval95'],rtol=0,atol=1e-12)
def gates(path,name):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def integrity():
 manifests={};checked={}
 for stage in [5,6]:
  p=BASE/f'stage{stage}';m=read(p/'SHA256SUMS.json');package=read(p/'PACKAGE-VERIFICATION.json')
  expected=package.get('checksum_manifest_sha256',package.get('sha256_manifest_sha256'));assert sha(p/'SHA256SUMS.json')==expected
  for name,v in m.items():
   file=ROOT/name;assert file.is_file() and file.stat().st_size==v['bytes'] and sha(file)==v['sha256'],name;checked[name]=v['sha256']
  actual_files=[file for file in p.rglob('*') if file.is_file() and file.name not in ['SHA256SUMS.json','PACKAGE-VERIFICATION.json'] and '__pycache__' not in file.parts]
  assert all(rel(file) in m for file in actual_files),'archive file outside checksum inventory'
  manifests[str(stage)]={'archive_files_covered':len(actual_files),'self_referential_exclusions':['SHA256SUMS.json','PACKAGE-VERIFICATION.json'],'manifest':rel(p/'SHA256SUMS.json'),'sha256':sha(p/'SHA256SUMS.json'),'entries':len(m)}
 inputs={}
 for name in ['EXPERIMENT-003.md','PROTOCOL-003.md','VALIDITY-003.md','STAGE5-PLAN.md','STAGE5-REPORT.md','STAGE6-PLAN.md','STAGE6-REPORT.md','STAGE6-B-SEED-AMENDMENT.md']:
  p=ROOT/'experiments/003'/name;inputs[rel(p)]=sha(p)
 return {'verdict':'PASS','checked_unique_files':len(checked),'manifests':manifests,'documents':inputs},checked

def provenance():
 records=[];cache={}
 for name in ['stage5/FROZEN-MANIFEST.json','stage6/FROZEN-MANIFEST.json','stage6/FROZEN-MANIFEST-B2.json']:
  f=read(BASE/name);commit=f['source_commit'];subprocess.run(['git','cat-file','-e',commit+'^{commit}'],cwd=ROOT,check=True)
  for path,h in f['source_sha256'].items():
   assert sha(ROOT/path)==h,path
   key=(commit,path)
   if key not in cache:cache[key]=hashlib.sha256(subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT)).hexdigest()
   assert cache[key]==h,key
  binaries=[]
  for path,h in f['binary_sha256'].items():
   available=Path(path).exists()
   if available:assert sha(path)==h
   binaries.append({'path':path,'sha256':h,'currently_available_and_verified':available})
  commit_time=int(subprocess.check_output(['git','show','-s','--format=%ct',commit],cwd=ROOT,text=True));assert commit_time*1_000_000_000<=f['created_unix_ns']
  records.append({'freeze':name,'source_commit':commit,'git_commit_unix_s':commit_time,'created_unix_ns':f['created_unix_ns'],'source_files_bound_to_git':len(f['source_sha256']),'binaries':binaries,'binary_build_source_commit':f.get('binary_build_source_commit',commit),'build_profile_note':f.get('build_profile','normal Rust debug / default Go; see archived build argv')})
 a,b=read(BASE/'stage6/FROZEN-MANIFEST.json'),read(BASE/'stage6/FROZEN-MANIFEST-B2.json');assert a['binary_sha256']==b['binary_sha256'] and b['binary_build_source_commit']==a['source_commit']
 return {'verdict':'PASS','records':records,'note':'Git timestamps/manifests are internal provenance, not external attestation. Binaries are not committed; available copies were checked, absent copies would remain archive-only hash claims.'}

def extract(path,family,block,condition,validator):
 w=read(path/'workload.json');s=read(path/'server/server-ledger.json');m=read(path/'verification.json');originals=w['originals'];assert len(originals)==N
 clients=1 if family=='PRIMARY' else m['clients'];deadline=2_000_000_000 if family=='PRIMARY' else m['deadline_ns'];cutoff=39_000_000_000 if family=='PRIMARY' else m['cutoff_ns']
 assert all(o['message_id']==i and o['scheduled_offset_ns']==i*12_500_000 and o['deadline_offset_ns']==i*12_500_000+deadline and o['client_id']==i%clients for i,o in enumerate(originals))
 required=['manifest.json','verification.json','workload.json','outcome.json','server/server-ledger.json','server/server-events.jsonl','server/clock.json','server/phases.jsonl','server/finished.json','server/observation-complete.json','server-metrics.csv']
 if family=='PRIMARY':required+=['client-report.json','client-events.jsonl','client-metrics.csv','primary-verification.json']
 else:
  required+=['independent-verification.json']
  for cid in range(clients):required += [f'client-{cid}/report.json',f'client-{cid}/events.jsonl',f'client-{cid}-metrics.csv']
 assert all((path/name).is_file() for name in required),path
 freeze_path=BASE/('stage5/FROZEN-MANIFEST.json' if family=='PRIMARY' else 'stage6/FROZEN-MANIFEST-B2.json' if family=='B2' else 'stage6/FROZEN-MANIFEST.json')
 frozen=read(freeze_path);assert m['frozen_manifest_sha256']==sha(freeze_path)
 assert m['binary_sha256']==frozen['binary_sha256'] and m['source_sha256']==frozen['source_sha256']
 assert m['git_commit' if family=='PRIMARY' else 'source_commit']==frozen['source_commit']
 assert m['epoch_unix_ns']>frozen['created_unix_ns']
 if family=='PRIMARY':
  planned=next(b for b in read(BASE/'stage5/RUN-PLAN.json')['blocks'] if b['block']==block)
  assert m['retry_seed']==planned['jitter_seed'] and m['policy']==condition
  assert sha(path/'workload.json')==frozen['workload_sha256']
 else:
  planfile='RUN-PLAN-B2.json' if family=='B2' else 'RUN-PLAN.json'
  planned=next(b for b in read(BASE/'stage6'/planfile)['blocks'] if b['block']==block and b['study']==('B' if family=='B2' else 'A'))
  case=next(c for c in planned['cases'] if c['name']==condition);assert all(m[k]==value for k,value in case.items())
  assert sha(path/'workload.json')==sha(BASE/f'stage6/workloads/{m["study"]}.json')
  if family=='B2':assert m['binary_build_source_commit']==frozen['binary_build_source_commit']

 se=events(path/'server/server-events.jsonl');assert [e['seq'] for e in se]==list(range(1,s['event_seq']+1))
 initiations={};observed={};local={};arrived=set();sends={};all_ce=[];reports=[]
 for cid in range(clients):
  c=read(path/('client-report.json' if family=='PRIMARY' else f'client-{cid}/report.json'));ce=events(path/('client-events.jsonl' if family=='PRIMARY' else f'client-{cid}/events.jsonl'));reports.append(c)
  assert [e['seq'] for e in ce]==list(range(1,c['client']['EventSeq']+1))
  for e in ce:
   i=e['message_id'];a=e['attempt_id'];kind=e['kind'];all_ce.append(e)
   if i<N and originals[i]['client_id']==cid and e.get('state'):local[i]=e['state']
   if kind=='original_arrival':assert i not in arrived and originals[i]['client_id']==cid;arrived.add(i)
   if kind=='attempt_initiated':
    assert a not in initiations and originals[i]['client_id']==cid;assert originals[i]['scheduled_offset_ns']<=e['offset_ns']<originals[i]['deadline_offset_ns'];initiations[a]=(i,e['attempt_number'])
   if kind=='grpc_send_return':assert a not in sends;sends[a]=e['send_success']
   if kind=='terminal_observed':observed[a]=e['result']
 assert arrived==set(range(N));assert set(sends)==set(initiations)
 actual={a['attempt_id']:(a['message_id'],a['attempt_number']) for a in s['attempts']};assert len(actual)==len(s['attempts']) and actual==initiations
 by=collections.defaultdict(list)
 for a in s['attempts']:by[a['message_id']].append(a)
 for aa in by.values():assert sorted(a['attempt_number'] for a in aa)==list(range(1,len(aa)+1)) and len(aa)<=3
 indexed={o['message_id']:o for o in s['originals']};assert len(indexed)==len(s['originals']);assert all(o['starts']<=1 for o in indexed.values())
 completed={i:o for i,o in indexed.items() if o['terminal']['outcome']==1};useful={i for i,o in completed.items() if o['terminal']['offset_ns']<=originals[i]['deadline_offset_ns']}
 partition={};missing=0
 for i in range(N):
  o=indexed.get(i);t=o['terminal'] if o else None
  if t is None:
   assert i not in by
   status='CLIENT_BACKLOG_EXHAUSTED' if local.get(i)=='CLIENT_BACKLOG_EXHAUSTED' else 'EXPIRED_BEFORE_SEND'
  elif t['outcome']==1:status='COMPLETED_ON_TIME' if i in useful else 'COMPLETED_LATE'
  elif t['outcome']==2:status='EXPIRED_WAITING_OR_QUEUED' if local.get(i)=='EXPIRED_WAITING_OR_QUEUED' else 'REJECTED_FINAL'
  elif t['outcome']==3:status='DROPPED'
  elif t['outcome']==4:status='EXPIRED_PROCESSING' if t['detail_code']=='EXPIRED_PROCESSING' else 'EXPIRED_WAITING_OR_QUEUED'
  elif t['outcome']==5:status='PROCESSING_FAILED'
  elif t['outcome']==6:status='CANCELLED'
  else:raise AssertionError('unknown server terminal')
  partition[i]=status
  if t:
   aa=sorted(by[i],key=lambda a:a['attempt_number']);v=observed.get(aa[-1]['attempt_id']);missing+=int(v is None or (v['Outcome'],v['Seq'],v['Offset'],v['Service'])!=(t['outcome'],t['event_seq'],t['offset_ns'],t['worker_service_ns']))
 rec={o['message_id']:o for c in reports for o in c['server_reconciliation']['Outcomes']};assert len(rec)==N and {i:o['disposition'] for i,o in rec.items()}==partition
 assert missing==sum(o['ack_missing'] for o in rec.values())
 counts=dict(collections.Counter(partition.values()));F=len(by);A=len(initiations);S=sum(sends.values());R=len(actual);assert all(len(useful)==c['server_reconciliation']['U'] for c in reports) if clients==1 else sum(c['server_reconciliation']['U'] for c in reports)==len(useful)
 assert A==sum(c['client']['Attempts'] for c in reports) and F==sum(c['client']['FirstAttempts'] for c in reports) and S==sum(c['client']['SendSuccess'] for c in reports)
 converted=[]
 for i in useful:
  aa=sorted(by[i],key=lambda a:a['attempt_number'])
  if len(aa)>1:assert all(a['terminal']['outcome']==2 for a in aa[:-1]);converted.append(i)
 phase={};cohorts={}
 for label,lo,hi in [('initial',0,12_000_000_000),('slowdown',12_000_000_000,24_000_000_000),('recovery',24_000_000_000,36_000_000_000)]:
  ids=sorted(i for i in completed if lo<=originals[i]['scheduled_offset_ns']<hi);cohorts[label]=ids;phase[label]=dist([completed[i]['terminal']['offset_ns']-originals[i]['scheduled_offset_ns'] for i in ids])
 last=0;occupied=0;area=0;peak=0
 for e in se:
  t=max(0,min(cutoff,e['offset_ns']));assert t>=last;area+=(t-last)*occupied;occupied=e['occupied'];last=t;peak=max(peak,occupied);assert occupied==e['queued']+e['running']<=32
 area+=(cutoff-last)*occupied
 old_cohort=[o for o in indexed.values() if o['admitted_ns'] is not None and o['admitted_ns']<24_000_000_000 and (o['exit_ns'] is None or o['exit_ns']>=24_000_000_000)]
 clearance=None if any(o['exit_ns'] is None or o['exit_ns']>cutoff for o in old_cohort) else max([24_000_000_000]+[o['exit_ns'] for o in old_cohort])-24_000_000_000
 result={'recovery_cohort_clearance_ns':clearance,'family':family,'block':block,'condition':condition,'directory':rel(path),'deadline_ns':deadline,'cutoff_ns':cutoff,'clients':clients,'N':N,'U':len(useful),'U_over_N':len(useful)/N,'A':A,'F':F,'S':S,'R':R,'retries':A-F,'A_over_N':A/N,'retries_over_N':(A-F)/N,'A_over_F':A/F,'outcomes':counts,'ack_missing':missing,'conversion_original_ids':sorted(converted),'phase_completion_ns':phase,'phase_completed_ids':cohorts,'payload_byte_ns':area*16384,'occupied_peak':peak}
 if family=='B2':
  ts=[e['offset_ns'] for e in all_ce if e['kind']=='attempt_initiated' and e['attempt_number']>1 and 12_000_000_000<=e['offset_ns']<24_000_000_000]
  metrics={}
  for width,shift,label in [(20_000_000,0,'20ms'),(20_000_000,10_000_000,'20ms_shift10'),(10_000_000,0,'10ms'),(50_000_000,0,'50ms')]:
   start=12_000_000_000+(shift-width if shift else 0);edges=np.arange(start,24_000_000_000+width,width,dtype=np.int64);hist,_=np.histogram(ts,bins=edges);assert int(hist.sum())==len(ts)
   numerator=sum(math.comb(int(k),2) for k in hist);denominator=math.comb(len(ts),2) if len(ts)>=2 else 0;collision=numerator/denominator if denominator else None
   if label=='20ms':
    labels=np.searchsorted(edges,np.asarray(ts),side='right')-1
    exhaustive=sum(a==b for a,b in itertools.combinations(labels.tolist(),2));assert exhaustive==numerator
   metrics[label]={'retry_count_M':len(ts),'bins':len(hist),'same_bin_unordered_pairs':numerator,'all_unordered_retry_pairs':denominator,'collision':collision,'maximum_bin_count':int(hist.max()),'p95_bin_count':float(np.quantile(hist,.95)),'counts':hist.tolist()}
  result['retry_bursts']=metrics
 archived=read(path/('primary-verification.json' if family=='PRIMARY' else 'independent-verification.json'));assert archived['verdict']=='PASS'
 replay=validator.verify(path);assert replay['verdict']=='PASS'
 result['gate_replay']={'status':'PASS','implementation':'Reused archived gate function, in memory; not a separately implemented validator.','archived_file_sha256':sha(path/('primary-verification.json' if family=='PRIMARY' else 'independent-verification.json'))}
 return result

def chronology():
 p=BASE/'stage6';a=read(p/'RUN-PLAN.json');b=read(p/'RUN-PLAN-B2.json');f=read(p/'FROZEN-MANIFEST-B2.json');matrix=read(p/'MATRIX-B2.json');boundary=read(p/'BOUNDARY-VERIFICATION.json');stopped=read(p/'MATRIX-AT-BOUNDARY.json')
 assert boundary['no_original_B_traffic'] and not boundary['original_B_event_files'] and not any(boundary['original_B_traffic_counts'].values())
 assert sha(p/'MATRIX-AT-BOUNDARY.json')==boundary['interrupted_matrix_sha256'];assert all(not x['runs'] for x in stopped['blocks'] if x['study']=='B')
 assert not any(x['study']=='B' for x in stopped['attempts'])
 assert boundary['boundary_stop']['sent_unix_ns']<f['created_unix_ns']<matrix['started_unix_ns']
 commit_ns=int(subprocess.check_output(['git','show','-s','--format=%ct',f['source_commit']],cwd=ROOT,text=True))*1_000_000_000;assert boundary['boundary_stop']['sent_unix_ns']<commit_ns<=f['created_unix_ns']
 checks=[];gamma=0x9e3779b97f4a7c15;mask=(1<<64)-1
 for block in b['blocks']:
  old=next(x for x in a['blocks'] if x['study']=='B' and x['block']==block['block']);assert old['seed']==block['seed'];assert [x['name'] for x in old['cases']]==[x['name'] for x in block['cases']]
  seeds=[int.from_bytes(hashlib.sha256(f'e3-stage6-b2|{block["seed"]}|{cid}'.encode('ascii')).digest()[:8],'little') for cid in range(8)];assert all(c['client_seeds']==seeds for c in block['cases'])
  states=set()
  for seed in seeds:
   for draw in range(1,8641):v=(seed+draw*gamma)&mask;assert v not in states;states.add(v)
  assert ((old['cases'][0]['client_seeds'][0]+2*gamma)&mask)==((old['cases'][0]['client_seeds'][1]+gamma)&mask)
  checks.append({'block':block['block'],'hash_seed_derivation':'PASS','first_8640_states_per_client_nonoverlap':'PASS','master_seed_and_order_unchanged':True})
 missing=[]
 for file in ['analysis/RESULTS.json','analysis/analysis.log']:
  r=subprocess.run(['git','cat-file','-e',f['source_commit']+':'+rel(p/file)],cwd=ROOT,capture_output=True);missing.append({'path':file,'absent_at_B2_preregistration':r.returncode!=0});assert r.returncode!=0
 epochs=[]
 for block in matrix['blocks']:
  for run in block['runs'].values():epochs.append(read(ROOT/run['directory']/'verification.json')['epoch_unix_ns'])
 assert f['created_unix_ns']<min(epochs)
 return {'verdict':'PASS','boundary_stop_unix_ns':boundary['boundary_stop']['sent_unix_ns'],'B2_preregistration_commit':f['source_commit'],'B2_commit_unix_ns_1s_resolution':commit_ns,'B2_freeze_unix_ns':f['created_unix_ns'],'B2_matrix_start_unix_ns':matrix['started_unix_ns'],'first_B2_epoch_unix_ns':min(epochs),'original_B_attempts':0,'original_B_traffic_files':0,'checks':checks,'analysis_absence_checks':missing,'limits':'Archived chronology and code/math support a pre-traffic amendment. No B outcomes existed to select on. This cannot independently attest what a human viewed in A or provide externally trusted timestamps.'}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DEST/'audit');args=parser.parse_args();out=args.output.resolve();assert out.is_relative_to(DEST.resolve());out.mkdir(parents=True,exist_ok=True)
 start=time.time_ns();integrity_result,before=integrity();prov=provenance();chron=chronology()
 old_analysis=(ROOT/'experiments/003/secondary/fixtures/analyze.py').read_text()
 actual_analysis=(BASE/'stage6/analysis/analyze_b2.py').read_text()
 assert old_analysis.replace('parents[4]','parents[5]').replace("matrix=read(OUT/'MATRIX.json')","matrix=read(OUT/'MATRIX-COMBINED.json')")==actual_analysis,'B2 numerical analysis changed beyond input-path plumbing'
 for stage,script,key in [(5,'audit-stage5.py','audit_script_sha256'),(6,'audit.py','audit_sha256')]:
  archived_audit=read(BASE/f'stage{stage}/analysis/OFFLINE-AUDIT.json');assert archived_audit[key]==sha(BASE/f'stage{stage}/analysis'/script)
 v5=gates(ROOT/'experiments/003/fixtures/verify-stage5.py','s7_v5');v6=gates(ROOT/'experiments/003/secondary/fixtures/verify.py','s7_v6');vb=gates(ROOT/'experiments/003/secondary/fixtures/verify_b2.py','s7_vb')
 rows=[];p=read(BASE/'stage5/MATRIX.json');assert p['status']=='COMPLETE'
 for block in p['blocks']:
  assert block['status']=='VALID'
  planned=next(b for b in read(BASE/'stage5/RUN-PLAN.json')['blocks'] if b['block']==block['block'])
  assert block['order']==planned['order'] and list(block['runs'])==planned['order']
  for policy,path in block['runs'].items():rows.append(extract(ROOT/path,'PRIMARY',block['block'],policy,v5))
 m6=read(BASE/'stage6/MATRIX-COMBINED.json');assert m6['status']=='COMPLETE'
 for block in m6['blocks']:
  assert block['status']=='VALID'
  assert list(block['runs'])==[c['name'] for c in block['cases']]
  for name,run in block['runs'].items():rows.append(extract(ROOT/run['directory'],'B2' if block['study']=='B' else 'A',block['block'],name,vb if block['study']=='B' else v6))
 assert len(rows)==70
 old5=read(BASE/'stage5/analysis/RESULTS.json');old6=read(BASE/'stage6/analysis/RESULTS.json')
 for r in rows:
  old=next(x for x in (old5['runs'] if r['family']=='PRIMARY' else old6['rows']) if x['block']==r['block'] and x['directory']==r['directory'])
  for key in ['U','A','F','S','R','retries']:assert old[key]==r[key]
  assert r['recovery_cohort_clearance_ns']==old['recovery_clearance_ns']
  close(r['payload_byte_ns'],old['server_payload_byte_ns' if r['family']=='PRIMARY' else 'payload_byte_ns'])
  for phase,d in r['phase_completion_ns'].items():
   published=old['phase_scheduled_completion_latency_ns' if r['family']=='PRIMARY' else 'phase_completion_ns'][phase];assert d['n']==published['n']
   for q in ['p50','p95','p99']:
    if d[q] is None:assert published[q] is None
    else:close(d[q],published[q])
  if r['family']=='B2':
   for metric,field in [('20ms','retry_burst20'),('20ms_shift10','retry_burst20_shift10'),('10ms','retry_burst10'),('50ms','retry_burst50')]:close(r['retry_bursts'][metric]['collision'],old[field]['collision'])
 def subset(family):return [r for r in rows if r['family']==family]
 def row(family,block,condition):return next(r for r in rows if (r['family'],r['block'],r['condition'])==(family,block,condition))
 primary={};pairs=read(BASE/'stage5/RUN-PLAN.json')['primary_analysis']['pairs']
 for a,b in pairs:
  key=a+'-minus-'+b;primary[key]={field:paired([row('PRIMARY',i,a)[field]-row('PRIMARY',i,b)[field] for i in range(1,6)]) for field in ['U_over_N','A_over_N','retries_over_N','payload_byte_ns']};verify_pair(primary[key]['U_over_N'],old5['paired'][key]['U_over_N'])
 recovery=[]
 for i in range(1,6):
  a,b=row('PRIMARY',i,'retry'),row('PRIMARY',i,'reject');ia=set(a['phase_completed_ids']['recovery']);ib=set(b['phase_completed_ids']['recovery'])
  recovery.append({'block':i,'retry':a['phase_completion_ns']['recovery'],'reject':b['phase_completion_ns']['recovery'],'common_completed_originals':len(ia&ib),'retry_only_completed':len(ia-ib),'reject_only_completed':len(ib-ia),'p95_difference_ns':a['phase_completion_ns']['recovery']['p95']-b['phase_completion_ns']['recovery']['p95']})
 deadline={}
 for policy in ['wait','reject','retry','drop']:
  value=paired([row('A',i,'a5000-'+policy)['U_over_N']-row('A',i,'a500-'+policy)['U_over_N'] for i in range(1,6)]);verify_pair(value,old6['contrasts']['deadline5000-minus-500:'+policy]['U_over_N']);deadline[policy]=value
 bursts={}
 for metric,field in [('20ms','retry_burst20'),('20ms_shift10','retry_burst20_shift10'),('10ms','retry_burst10'),('50ms','retry_burst50')]:
  delta=[];relative=[]
  for i in range(1,6):
   d=row('B2',i,'b-deterministic')['retry_bursts'][metric]['collision'];j=row('B2',i,'b-jitter')['retry_bursts'][metric]['collision'];delta.append(d-j);relative.append(d/j-1)
  bursts[metric]={'absolute':paired(delta),'relative':paired(relative)};verify_pair(bursts[metric]['absolute'],old6['burst_contrasts'][field]['difference']);verify_pair(bursts[metric]['relative'],old6['burst_contrasts'][field]['relative'])
 anomalous=[row('A',i,'a500-wait') for i in range(1,6)]
 influence={'all_five_U':[r['U'] for r in anomalous],'all_five_late':[r['outcomes'].get('COMPLETED_LATE',0) for r in anomalous],'all_five_processing_expired':[r['outcomes'].get('EXPIRED_PROCESSING',0) for r in anomalous],'mean_U_over_N':float(np.mean([r['U_over_N'] for r in anomalous])),'median_U_over_N':float(np.median([r['U_over_N'] for r in anomalous])),'all_five_deadline_differences':deadline['wait'],'exclusion_performed':False,'cause':'Not established by these data; no causal diagnosis attempted.'}
 for name,h in before.items():assert sha(ROOT/name)==h,name
 output={'verdict':'PASS','reviewed_revision':REVIEWED,'audit_started_unix_ns':start,'completed_unix_ns':time.time_ns(),'performance_runs_executed':0,'previous_evidence_modified':False,'integrity':integrity_result,'provenance':prov,'B2_chronology':chron,'runs':rows,'primary_paired':primary,'primary_recovery_conditional':recovery,'secondary_deadline_paired':deadline,'secondary_burst_paired':bursts,'anomalous_WAIT500_influence':influence,'audit_script_sha256':sha(Path(__file__)),'independence_scope':'New raw arithmetic/partition/bin/bootstrap implementation; archived gate functions replayed in memory as additional shared-logic checks, not claimed as a new independent validator or external laboratory replication.'}
 (out/'REVIEW-AUDIT.json').write_text(json.dumps(output,indent=2)+'\n')
 fields=['family','block','condition','directory','deadline_ns','clients','N','U','U_over_N','A','F','S','R','retries','A_over_N','A_over_F','ack_missing']
 with (out/'RUNS.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:r[k] for k in fields} for r in rows)
 print('PASS:70 read-only gate replays; new raw U/partitions/attempts/conditional quantiles/bursts/paired calculations; provenance and historical hashes unchanged')
if __name__=='__main__':main()
