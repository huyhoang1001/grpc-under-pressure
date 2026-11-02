#!/usr/bin/env python3
"""Preregistered Stage6 paired secondary analysis. No Stage5 outcomes are pooled."""
import argparse,collections,csv,hashlib,itertools,json,math,os,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5];OUT=ROOT/'experiments/003/results/stage6';POL=['wait','reject','retry','drop'];N=2880
def read(p):return json.loads(p.read_text())
def quantile(a,q):
 if not a:return None
 s=sorted(a);x=(len(s)-1)*q;i=int(x);return s[i]*(1-(x-i))+s[min(i+1,len(s)-1)]*(x-i)
def dist(a):return {'n':len(a),**{k:quantile(a,p) for k,p in [('p50',.5),('p95',.95),('p99',.99)]}}
def paired(values,required=5):
 if len(values)!=required or any(x is None for x in values):return {'status':'INCOMPLETE_OR_UNDEFINED','values':values,'n':len(values),'required':required,'mean':None,'interval95':None}
 boot=[statistics.mean(x) for x in itertools.product(values,repeat=len(values))]
 return {'values':values,'n':len(values),'mean':statistics.mean(values),'median':statistics.median(values),'positive':sum(x>0 for x in values),'negative':sum(x<0 for x in values),'interval95':[quantile(boot,.025),quantile(boot,.975)],'method':'exact paired-block bootstrap; descriptive only'}
def integrate(events,key,cutoff):
 last=0;value=0;total=0
 for e in events:
  t=max(0,min(cutoff,e['offset_ns']));total+=max(0,t-last)*value;last=t;value=key(e)
 return total+max(0,cutoff-last)*value
def bursts(events,width=20_000_000,shift=0,retries_only=True):
 times=[e['offset_ns'] for e in events if e['kind']=='attempt_initiated' and (not retries_only or e['attempt_number']>1) and 12e9<=e['offset_ns']<24e9]
 counts=collections.Counter((int(t)-12_000_000_000-shift)//width for t in times)
 first=(-shift)//width;last=(12_000_000_000-1-shift)//width;bins=[counts[i] for i in range(first,last+1)];r=len(times);mean=r/len(bins)
 return {'events':r,'bins':len(bins),'width_ns':width,'shift_ns':shift,'collision':sum(k*(k-1) for k in bins)/(r*(r-1)) if r>=2 else None,'max_count':max(bins),'p95_count':quantile(bins,.95),'fano':statistics.pvariance(bins)/mean if mean else None,'counts':bins}
def summarize(run,block):
 m=read(run/'verification.json');v=read(run/'independent-verification.json');w=read(run/'workload.json');s=read(run/'server/server-ledger.json');clock=read(run/'server/clock.json');cut=m['cutoff_ns'];clients=m['clients']
 assert v['verdict']=='PASS'
 ce=[];reports=[];roles={};client_series=[]
 for cid in range(clients):
  reports.append(read(run/f'client-{cid}/report.json'));ce.extend([{**json.loads(x),'owner_client':cid} for x in (run/f'client-{cid}/events.jsonl').read_text().splitlines()])
 se=[json.loads(x) for x in (run/'server/server-events.jsonl').read_text().splitlines()]
 ce.sort(key=lambda e:(e['commit_offset_ns'],e['owner_client'],e['seq']))
 state={cid:(0,0) for cid in range(clients)};max_pending=max_outstanding=0
 for e in ce:
  state[e['owner_client']]=(e['pending'],e['outstanding']);p=sum(x[0] for x in state.values());o=sum(x[1] for x in state.values());max_pending=max(max_pending,p);max_outstanding=max(max_outstanding,o)
  client_series.append({'offset_ns':max(0,e['commit_offset_ns']),'pending':p,'outstanding':o})
 for role in ['server']+[f'client-{i}' for i in range(clients)]:
  b=clock['start'] if role=='server' else reports[int(role.split('-')[1])]['client']['ClockStart'];epoch=(b['epoch_min_ns']+b['epoch_max_ns'])//2 if role=='server' else (b['EpochMinNS']+b['EpochMaxNS'])//2
  samples=list(csv.DictReader((run/f'{role}-metrics.csv').open()));window=[]
  for row in samples:
   t=int(row['host_monotonic_ns'])-epoch
   if t>=0 and (not window or window[-1][0]<cut):window.append((t,int(row['cpu_user_ns'])+int(row['cpu_system_ns'])))
  roles[role]={'rss_peak_sampled_bytes':max(int(x['rss_bytes']) for x in samples),'cpu_window_ns':window[-1][1]-window[0][1],'cpu_window_offsets_ns':[window[0][0],window[-1][0]],'tick_ns':int(samples[0]['cpu_tick_ns'])}
 completed=[o for o in s['originals'] if o['terminal']['outcome']==1];useful=[o for o in completed if o['terminal']['offset_ns']<=w['originals'][o['message_id']]['deadline_offset_ns']]
 latency=lambda cohort:[o['terminal']['offset_ns']-w['originals'][o['message_id']]['scheduled_offset_ns'] for o in cohort]
 phase={name:dist(latency([o for o in completed if lo<=w['originals'][o['message_id']]['scheduled_offset_ns']<hi])) for name,lo,hi in [('initial',0,12e9),('slowdown',12e9,24e9),('recovery',24e9,36e9)]}
 old=[o for o in s['originals'] if o['admitted_ns'] is not None and o['admitted_ns']<24e9 and (o['exit_ns'] is None or o['exit_ns']>=24e9)];censored=any(o['exit_ns'] is None or o['exit_ns']>cut for o in old);clearance=None if censored else max([24_000_000_000]+[o['exit_ns'] for o in old])-24_000_000_000
 # Event-state integration keeps payload ownership separate from RSS and ledger.
 payload=integrate(se,lambda e:e['occupied']*16384,cut);common=integrate(se,lambda e:e['occupied']*16384,min(cut,39_000_000_000))
 recovery=[]
 import bisect
 st=[e['offset_ns'] for e in se];ct=[e['offset_ns'] for e in client_series]
 for second in range(24,int(cut//1e9)+1):
  t=second*1_000_000_000;si=bisect.bisect_right(st,t)-1;ci=bisect.bisect_right(ct,t)-1
  recovery.append({'second':second,'occupied':se[si]['occupied'] if si>=0 else 0,'client_pending':client_series[ci]['pending'] if ci>=0 else 0,'client_outstanding':client_series[ci]['outstanding'] if ci>=0 else 0,'on_time_in_following_second':sum(t<=o['terminal']['offset_ns']<min(t+1e9,cut) for o in useful) if t<cut else None})
 transport={key:sum(c['transport'][key] for c in reports) for key in reports[0]['transport']}
 A=sum(c['client']['Attempts'] for c in reports);F=sum(c['client']['FirstAttempts'] for c in reports);S=sum(c['client']['SendSuccess'] for c in reports);retry=A-F
 observations={e['message_id']:e['offset_ns'] for e in ce if e['kind']=='terminal_observed'}
 return {'block':block,'study':m['study'],'name':m['name'],'policy':m['policy'],'retry_mode':m['retry_mode'],'directory':str(run.relative_to(ROOT)),'deadline_ns':m['deadline_ns'],'cutoff_ns':cut,'clients':clients,'N':N,'U':len(useful),'U_over_N':len(useful)/N,'U_per_36s':len(useful)/36,'completed_per_36s':len(completed)/36,'A':A,'F':F,'S':S,'R':v['R'],'retries':retry,'A_over_N':A/N,'retries_over_N':retry/N,'A_over_F':A/F if F else None,'unsent':N-F,'outcomes':v['partition'],'ack_missing':v['ack_missing'],'completion_ns':dist(latency(completed)),'on_time_completion_ns':dist(latency(useful)),'phase_completion_ns':phase,'ack_observed_ns':dist([t-w['originals'][i]['scheduled_offset_ns'] for i,t in observations.items()]),'queue_residence_ns':dist(v['queue_residence_ns']),'admission_wait_ns':dist(v['admission_wait_ns']),'admission_wait_sum_ns':sum(v['admission_wait_ns']),'send_ns':dist([e['send_duration_ns'] for e in ce if e['kind']=='grpc_send_return']),'worker_occupied_ns':v['worker_occupied_ns'],'worker_occupancy_fraction':v['worker_occupied_ns']/cut,'idle_with_backlog_ns':integrate(se,lambda e:int(e['queued']>0 and e['running']==0),cut),'payload_byte_ns':payload,'payload_byte_ns_common_39':common,'staging_byte_ns':integrate(se,lambda e:e['resources']['staging']*16384,cut),'client_pending_item_ns':integrate(client_series,lambda e:e['pending'],cut),'client_outstanding_item_ns':integrate(client_series,lambda e:e['outstanding'],cut),'aggregate_pending_high_water':max_pending,'aggregate_outstanding_high_water':max_outstanding,'client_high_water':v['client_high_water'],'server_high_water':v['server_high_water'],'server_ledger_record_bytes_estimate':s['allocated_ledger_bytes'],'sum_client_ledger_record_bytes_estimate':sum(c['client']['LedgerAllocatedBytes'] for c in reports),'process':roles,'sum_client_process_rss_peaks_bytes_not_simultaneous':sum(r['rss_peak_sampled_bytes'] for name,r in roles.items() if name!='server'),'transport':transport,'tcp_write_bytes_per_original':transport['tcp_stream_write_bytes']/N,'writer_local_elapsed_ns':s['writer_progress_ns'],'recovery_clearance_ns':clearance,'recovery_censored':censored,'recovery':recovery,'retry_burst20':bursts(ce),'retry_burst20_shift10':bursts(ce,20_000_000,10_000_000),'retry_burst10':bursts(ce,10_000_000),'retry_burst50':bursts(ce,50_000_000),'all_attempt_burst20':bursts(ce,retries_only=False),'clock_uncertainty_ns':v['clock_uncertainty_ns'],'genuine_refusals':v['genuine_refusals'],'genuine_drops':v['genuine_drops'],'source_manifest_sha256':m['frozen_manifest_sha256']}
def analyze():
 matrix=read(OUT/'MATRIX-COMBINED.json');plan=read(OUT/'RUN-PLAN.json');destination=OUT/'analysis';destination.mkdir(exist_ok=True);rows=[];blocks={}
 for block in matrix['blocks']:
  if block['status']!='VALID':continue
  key=(block['study'],block['block']);blocks[key]={}
  for name,run in block['runs'].items():
   r=summarize(ROOT/run['directory'],block['block']);rows.append(r);blocks[key][name]=r
 contrasts={};endpoints=['U_over_N','A_over_N','retries_over_N','payload_byte_ns_common_39','client_pending_item_ns','recovery_clearance_ns','tcp_write_bytes_per_original']
 def compare(label,pairs):
  contrasts[label]={endpoint:paired([a[endpoint]-b[endpoint] if a[endpoint] is not None and b[endpoint] is not None else None for a,b in pairs]) for endpoint in endpoints}
 akeys=sorted(k for k in blocks if k[0]=='A');bkeys=sorted(k for k in blocks if k[0]=='B')
 for study in ['a500','a5000']:
  for left,right in plan['pairs']:compare(study+':'+left+'-minus-'+right,[(blocks[k][study+'-'+left],blocks[k][study+'-'+right]) for k in akeys])
 for p in POL:compare('deadline5000-minus-500:'+p,[(blocks[k]['a5000-'+p],blocks[k]['a500-'+p]) for k in akeys])
 interactions={}
 for left,right in plan['pairs']:
  interactions[left+'-minus-'+right]=paired([(blocks[k]['a5000-'+left]['U_over_N']-blocks[k]['a5000-'+right]['U_over_N'])-(blocks[k]['a500-'+left]['U_over_N']-blocks[k]['a500-'+right]['U_over_N']) for k in akeys])
 compare('B:deterministic-minus-jitter',[(blocks[k]['b-deterministic'],blocks[k]['b-jitter']) for k in bkeys])
 bursts_stats={}
 for field in ['retry_burst20','retry_burst20_shift10','retry_burst10','retry_burst50','all_attempt_burst20']:
  values=[];relative=[]
  for k in bkeys:
   a=blocks[k]['b-deterministic'][field]['collision'];b=blocks[k]['b-jitter'][field]['collision'];values.append(a-b if a is not None and b is not None else None);relative.append(a/b-1 if a is not None and b is not None and b>0 else None)
  bursts_stats[field]={'difference':paired(values),'relative':paired(relative)}
 primary=bursts_stats['retry_burst20'];d=primary['difference'];rel=primary['relative'];h6='INCOMPLETE_OR_UNDEFINED'
 if d['mean'] is not None and rel['mean'] is not None:
  supported=d['mean']>0 and d['interval95'][0]>0 and d['positive']>=4 and rel['mean']>=.10
  h6='MATERIAL_SECONDARY_SUPPORT' if supported else 'NO_MATERIAL_SECONDARY_SUPPORT'
  shifted=bursts_stats['retry_burst20_shift10']['difference']['mean']
  if supported and shifted is not None and shifted<0:h6='FRAGILE_BIN_ALIGNMENT_SIGNAL'
 result={'secondary_only':True,'stage5_runs_pooled':0,'matrix_status':matrix['status'],'valid_blocks_A':len(akeys),'valid_blocks_B':len(bkeys),'run_count':len(rows),'rows':rows,'contrasts':contrasts,'deadline_policy_interactions_U_over_N':interactions,'burst_contrasts':bursts_stats,'H6':h6,'stage6_verdict':'PASS' if matrix['status']=='COMPLETE' and len(akeys)==len(bkeys)==5 and len(rows)==50 else 'FAIL','analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'limitations':['Secondary only; five paired blocks/study, one shared host, simulated timers and debug/direct instrumentation.','RSS sampled peaks and ledger estimates do not bound process memory; CPU endpoints are sampled/quantized.','Conditional latency cohorts differ; denominator for U/N is every scheduled original.','Eight-client metadata/transport/credits differ from primary but are identical within StudyB.','Deterministic common relative backoff does not guarantee synchronized retry bursts.']}
 (destination/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
 fields=['block','study','name','deadline_ns','clients','N','U','U_over_N','A','F','S','R','retries','unsent','A_over_N','A_over_F','payload_byte_ns','payload_byte_ns_common_39','worker_occupied_ns','aggregate_pending_high_water','aggregate_outstanding_high_water','recovery_clearance_ns']
 with (destination/'runs.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({key:r[key] for key in fields} for r in rows)
 if rows:figures(result,destination)
 print('Analyzed secondary runs',len(rows),'A blocks',len(akeys),'B blocks',len(bkeys),result['stage6_verdict'],h6)
def figures(result,destination):
 os.environ.setdefault('MPLCONFIGDIR','/tmp/e3-stage6-mpl');os.environ.setdefault('XDG_CACHE_HOME','/tmp/e3-stage6-cache')
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 plots=destination/'figures';plots.mkdir(exist_ok=True)
 def save(fig,name):
  fig.tight_layout()
  for ext in ['png','svg']:fig.savefig(plots/(name+'.'+ext),dpi=160)
  plt.close(fig)
 fig,ax=plt.subplots(1,2,figsize=(10,4),sharey=True)
 for a,study in zip(ax,['a500','a5000']):
  for p in POL:
   rows=[r for r in result['rows'] if r['study']==study and r['policy']==p];a.plot([r['block'] for r in rows],[r['U_over_N']*100 for r in rows],'-o',label=p)
  a.set(title=study,xlabel='Matched block',ylabel='U / all2880 originals (%)');a.legend()
 save(fig,'deadline-goodput')
 fig,ax=plt.subplots(1,2,figsize=(10,4))
 for mode in ['deterministic','jitter']:
  rows=[r for r in result['rows'] if r['study']=='b' and r['retry_mode']==mode]
  ax[0].plot([r['block'] for r in rows],[r['retry_burst20']['collision'] for r in rows],'-o',label=mode);ax[1].plot([r['block'] for r in rows],[r['U_over_N']*100 for r in rows],'-o',label=mode)
 ax[0].set(title='Slowdown retry concentration',xlabel='Matched pair',ylabel='20ms pair-collision probability');ax[1].set(title='Secondary useful delivery',xlabel='Matched pair',ylabel='U / all2880 (%)');ax[0].legend();save(fig,'retry-pairs')
 fig,ax=plt.subplots(figsize=(10,4))
 for mode in ['deterministic','jitter']:
  rows=[r for r in result['rows'] if r['study']=='b' and r['retry_mode']==mode]
  if rows:ax.plot([12+i*.02 for i in range(600)],[statistics.mean(r['retry_burst20']['counts'][i] for r in rows) for i in range(600)],label=mode,alpha=.8)
 ax.set(xlabel='Seconds from epoch',ylabel='Mean retries /20ms bin',title='Eight-client slowdown: actual initiated retries, not scheduled originals');ax.legend();save(fig,'retry-bursts')
 fig,ax=plt.subplots(2,1,figsize=(9,6),sharex=True)
 for mode in ['deterministic','jitter']:
  rows=[r for r in result['rows'] if r['study']=='b' and r['retry_mode']==mode]
  if not rows:continue
  times=[x['second'] for x in rows[0]['recovery']]
  ax[0].plot(times,[statistics.mean(r['recovery'][i]['client_pending']+r['recovery'][i]['client_outstanding'] for r in rows) for i in range(len(times))],label=mode)
  ax[1].plot(times[:-1],[statistics.mean(r['recovery'][i]['on_time_in_following_second'] for r in rows) for i in range(len(times)-1)],label=mode)
 ax[0].set(ylabel='Aggregate pending + outstanding',title='Eight-client recovery; cohort clearance is not steady state');ax[1].set(xlabel='Seconds from epoch',ylabel='On-time completions / observed1s');ax[0].legend();save(fig,'retry-recovery')
def selftest():
 assert paired([0]*5)['interval95']==[0,0]
 assert paired([None]*5)['mean'] is None
 events=[{'kind':'attempt_initiated','attempt_number':2,'offset_ns':12_000_000_001},{'kind':'attempt_initiated','attempt_number':2,'offset_ns':12_000_000_002}]
 assert bursts(events)['collision']==1 and bursts([])['collision'] is None
 assert integrate([{'offset_ns':0,'x':2},{'offset_ns':10,'x':0}],lambda e:e['x'],20)==20
 print('PASS: secondary quantile/bootstrap/collision/undefined/integral self-tests')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--selftest',action='store_true');args=p.parse_args();selftest() if args.selftest else analyze()
