#!/usr/bin/env python3
"""Frozen paired primary analysis. No policy tuning or exploratory endpoint selection."""
import argparse,bisect,collections,csv,hashlib,itertools,json,math,os,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'experiments/003/results/stage5';POL=['wait','reject','retry','drop'];N=2880;CUT=39_000_000_000

def quantile(xs,p):
 if not xs:return None
 a=sorted(xs);x=(len(a)-1)*p;i=int(x);f=x-i;return a[i]*(1-f)+a[min(i+1,len(a)-1)]*f

def dist(xs):return {'n':len(xs),'p50':quantile(xs,.5),'p95':quantile(xs,.95),'p99':quantile(xs,.99)}
def paired(values):
 n=len(values)
 if not n:return {'n':0,'mean':None,'interval95':None,'values':[]}
 boot=[sum(x)/n for x in itertools.product(values,repeat=n)]
 return {'n':n,'values':values,'mean':statistics.mean(values),'median':statistics.median(values),'interval95':[quantile(boot,.025),quantile(boot,.975)],'positive_blocks':sum(x>0 for x in values),'negative_blocks':sum(x<0 for x in values),'method':'exact paired-block bootstrap; descriptive, not significance'}
def integrate(events,value):
 total=0;last=0;state=0
 for e in events:
  t=max(0,min(CUT,e['offset_ns']));total+=max(0,t-last)*state;last=t;state=value(e)
 total+=max(0,CUT-last)*state;return total

def process_metrics(run,role,epoch):
 rows=list(csv.DictReader((run/(role+'-metrics.csv')).open()));selected=[]
 for r in rows:
  t=int(r['host_monotonic_ns'])-epoch
  if t>=0 and (not selected or selected[-1][0]<CUT):selected.append((t,int(r['cpu_user_ns'])+int(r['cpu_system_ns'])))
 return {'sampled_rss_peak_bytes':max(int(r['rss_bytes']) for r in rows),'cpu_window_ns':selected[-1][1]-selected[0][1],'cpu_window_offsets_ns':[selected[0][0],selected[-1][0]],'cpu_resolution_ns':int(rows[0]['cpu_tick_ns'])}

def summarize(run):
 load=lambda f:json.loads((run/f).read_text())
 w=load('workload.json');s=load('server/server-ledger.json');c=load('client-report.json');v=load('primary-verification.json');m=load('verification.json');clock=load('server/clock.json')
 se=[json.loads(x) for x in (run/'server/server-events.jsonl').read_text().splitlines()];ce=[json.loads(x) for x in (run/'client-events.jsonl').read_text().splitlines()]
 completed=[o for o in s['originals'] if o['terminal']['outcome']==1];on=[o for o in completed if o['terminal']['offset_ns']<=w['originals'][o['message_id']]['deadline_offset_ns']]
 latency=lambda group:[o['terminal']['offset_ns']-w['originals'][o['message_id']]['scheduled_offset_ns'] for o in group]
 last_observed={}
 for e in ce:
  if e['kind']=='terminal_observed':last_observed[e['message_id']]=e['offset_ns']
 original_attempts=collections.Counter(a['message_id'] for a in s['attempts'])
 retry_converted=sum(original_attempts[o['message_id']]>1 for o in on)
 cohort={}
 for lo,hi,label in [(0,12e9,'initial'),(12e9,24e9,'slowdown'),(24e9,36e9,'recovery')]:
  group=[o for o in completed if lo<=w['originals'][o['message_id']]['scheduled_offset_ns']<hi];cohort[label]=dist(latency(group))
 old=[o for o in s['originals'] if o['admitted_ns'] is not None and o['admitted_ns']<24e9 and (o['exit_ns'] is None or o['exit_ns']>=24e9)]
 censored=any(o['exit_ns'] is None or o['exit_ns']>CUT for o in old)
 clearance=None if censored else max([24_000_000_000]+[o['exit_ns'] for o in old])-24_000_000_000
 st=[e['offset_ns'] for e in se];ct=[e['commit_offset_ns'] for e in ce]
 recovery=[]
 for second in range(24,40):
  t=second*1_000_000_000;si=bisect.bisect_right(st,t)-1;ci=bisect.bisect_right(ct,t)-1
  server=se[si] if si>=0 else None;client=ce[ci] if ci>=0 else None
  recovery.append({'second':second,'on_time_completions':sum(t<=o['terminal']['offset_ns']<t+1e9 for o in on) if second<39 else 0,'client_pending':client['pending'] if client else 0,'client_outstanding':client['outstanding'] if client else 0,'server_occupied':server['occupied'] if server else 0,'retry_scheduled':sum(e['kind']=='retry_scheduled' and t<=e['offset_ns']<t+1e9 for e in ce)})
 queue_time=integrate(se,lambda e:e['queued']);retained=integrate(se,lambda e:e['occupied'])*16384;staged=integrate(se,lambda e:e['resources']['staging'])*16384
 idle=integrate(se,lambda e:int(e['queued']>0 and e['running']==0))
 proc={}
 for role in ['server','client']:
  b=clock['start'] if role=='server' else c['client']['ClockStart'];epoch=(b['epoch_min_ns']+b['epoch_max_ns'])//2 if role=='server' else (b['EpochMinNS']+b['EpochMaxNS'])//2;proc[role]=process_metrics(run,role,epoch)
 slow_service=[o['terminal']['worker_service_ns'] for o in completed if 12e9<=o['start_ns']<24e9]
 return {'policy':m['policy'],'seed':m['retry_seed'],'directory':str(run.relative_to(ROOT)),'verdict':v['verdict'],'N':N,'U':len(on),'U_over_N':len(on)/N,'deadline_goodput_per_s':len(on)/36,'counts':c['server_reconciliation']['Counts'],'A':c['client']['Attempts'],'F':c['client']['FirstAttempts'],'S':c['client']['SendSuccess'],'R':s['attempt_entries'],'attempts_per_original':c['client']['Attempts']/N,'retries':c['client']['Retries'],'retries_per_original':c['client']['Retries']/N,'admitted_fraction_original':s['permits_acquired']/N,'admitted_fraction_attempt':s['permits_acquired']/max(1,c['client']['Attempts']),'completed_fraction_admitted':len(completed)/max(1,s['permits_acquired']),'completion_latency_ns':dist(latency(completed)),'on_time_completion_latency_ns':dist(latency(on)),'phase_scheduled_completion_latency_ns':cohort,'client_observed_terminal_latency_ns':dist([t-w['originals'][i]['scheduled_offset_ns'] for i,t in last_observed.items()]),'admission_wait_ns':dist(v['logical_admission_wait_ns']),'queue_residence_ns':dist(v['queue_residence_ns']),'send_duration_ns':dist(v['send_duration_ns']),'queue_occupancy_item_ns':queue_time,'occupied_max':max(e['occupied'] for e in se),'server_payload_byte_ns':retained,'staged_payload_byte_ns':staged,'worker_occupied_ns':v['worker_occupied_ns'],'worker_occupied_by_disposition_ns':v['worker_elapsed_by_disposition'],'worker_utilization_observation':v['worker_occupied_ns']/CUT,'idle_with_backlog_ns':idle,'process_metrics':proc,'transport':c['transport'],'tcp_write_bytes_per_original':c['transport']['tcp_stream_write_bytes']/N,'clock_uncertainty_ns':v['clock_uncertainty_ns'],'client_high_water':v['client_high_water'],'server_high_water':v['server_high_water'],'writer_local_progress_ns':v['writer_local_progress_ns'],'retry_converted_on_time_originals':retry_converted,'slowdown_completed_service_median_ns':statistics.median(slow_service) if slow_service else None,'recovery_clearance_ns':clearance,'recovery_censored':censored,'pre24_backlog_at24':len(old),'recovery_series':recovery,'deadline_attainment':{str(x):sum(t<=x*1e9 for t in latency(completed))/N for x in [.5,1,2,5]}}

def analyze():
 plan=json.loads((OUT/'RUN-PLAN.json').read_text());matrix=json.loads((OUT/'MATRIX.json').read_text());out=OUT/'analysis';out.mkdir(exist_ok=True)
 runs=[];blocks=[]
 for entry in matrix['blocks']:
  if entry['status']!='VALID':continue
  rows={p:summarize(ROOT/entry['runs'][p]) for p in POL}
  for r in rows.values():r['block']=entry['block'];runs.append(r)
  blocks.append(rows)
 paired_rows={}
 endpoints=['U_over_N','attempts_per_original','retries_per_original','server_payload_byte_ns','worker_utilization_observation','idle_with_backlog_ns','tcp_write_bytes_per_original','recovery_clearance_ns']
 for a,b in plan['primary_analysis']['pairs']:
  name=a+'-minus-'+b;paired_rows[name]={}
  for endpoint in endpoints:
   vals=[row[a][endpoint]-row[b][endpoint] for row in blocks if row[a][endpoint] is not None and row[b][endpoint] is not None]
   # Never silently drop censored blocks from an apparently complete comparison.
   paired_rows[name][endpoint]=paired(vals) if len(vals)==len(blocks) else {'n':len(vals),'required_n':len(blocks),'status':'CENSORED_OR_MISSING','interval95':None,'values':vals}
 stats={p:{'runs':len(blocks),'U_over_N':paired([b[p]['U_over_N'] for b in blocks]),'A_over_N':paired([b[p]['attempts_per_original'] for b in blocks]),'retries_over_N':paired([b[p]['retries_per_original'] for b in blocks]),'counts_mean':{key:statistics.mean(b[p]['counts'].get(key,0) for b in blocks) for key in sorted({k for b in blocks for k in b[p]['counts']})}} for p in POL} if blocks else {}
 def verdicts():
  if len(blocks)<5:return {'status':'INCOMPLETE','note':'No full primary hypothesis assessment from partial evidence.'}
  h1=all(b['wait']['slowdown_completed_service_median_ns']>=40e6 and b['wait']['occupied_max']==32 and b['wait']['client_high_water']['Pending']>0 and sum(b['wait']['counts'].get(x,0) for x in ['CLIENT_BACKLOG_EXHAUSTED','EXPIRED_BEFORE_SEND','EXPIRED_WAITING_OR_QUEUED','EXPIRED_PROCESSING'])>0 for b in blocks)
  h2=paired_rows['reject-minus-wait']['server_payload_byte_ns'];h2yes=h2['mean']<0 and h2['negative_blocks']>=4 and all(b['reject']['counts'].get('REJECTED_FINAL',0)>0 for b in blocks)
  h3=paired_rows['retry-minus-reject']['U_over_N'];conversions=[b['retry']['retry_converted_on_time_originals'] for b in blocks];h3yes=h3['mean']>0 and h3['interval95'][0]>0 and h3['positive_blocks']>=4 and sum(x>0 for x in conversions)>=4
  d=paired_rows['drop-minus-reject'];h4dist=any(x['interval95'] and (x['interval95'][0]>0 or x['interval95'][1]<0) and max(x.get('positive_blocks',0),x.get('negative_blocks',0))>=4 for x in [d['U_over_N'],d['server_payload_byte_ns']])
  h5any=any(x['recovery_clearance_ns'].get('interval95') and (x['recovery_clearance_ns']['interval95'][0]>0 or x['recovery_clearance_ns']['interval95'][1]<0) and max(x['recovery_clearance_ns'].get('positive_blocks',0),x['recovery_clearance_ns'].get('negative_blocks',0))>=4 for x in paired_rows.values())
  return {'H1':{'assessment':'DESCRIPTIVELY_SUPPORTED' if h1 else 'MIXED_OR_NOT_ESTABLISHED'},'H2':{'assessment':'DESCRIPTIVELY_SUPPORTED' if h2yes else 'MIXED_OR_NOT_ESTABLISHED'},'H3':{'assessment':'DESCRIPTIVELY_SUPPORTED' if h3yes else 'NO_CONVERSION_BENEFIT_OBSERVED' if not any(conversions) else 'MIXED_OR_NOT_ESTABLISHED','retry_converted_on_time_per_block':conversions},'H4':{'assessment':'DISTINCT_OPERATIONAL_EFFECT_OBSERVED' if h4dist else 'NO_DISTINCT_TRADEOFF_ESTABLISHED_NOT_EQUIVALENCE_PROOF'},'H5':{'assessment':'DESCRIPTIVE_RECOVERY_DIFFERENCES' if h5any else 'INCONCLUSIVE_OR_CENSORED'},'caveat':'Operational preregistered descriptive assessments, not universal causal/statistical claims.'}
 result={'valid_blocks':len(blocks),'runs':runs,'policies':stats,'paired':paired_rows,'hypotheses':verdicts(),'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'limitations':['n=5 independent fresh-process blocks on one shared host; exact bootstrap intervals are descriptive.','Conditional latency cohorts differ; failures/unsent originals remain in all-original denominator.','Sampled RSS, quantized CPU and inherited clock assumptions retained.','Direct debug-profile instrumentation overhead is part of this model and not fully isolated.']}
 (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
 with (out/'runs.csv').open('w') as f:
  keys=['block','policy','N','U','U_over_N','A','F','S','R','retries','attempts_per_original','retries_per_original','server_payload_byte_ns','worker_occupied_ns','idle_with_backlog_ns','recovery_clearance_ns','recovery_censored'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in runs)
 if blocks:figures(result,out)
 print('Analyzed',len(blocks),'complete valid blocks;',len(runs),'runs')

def figures(result,out):
 os.environ.setdefault('MPLCONFIGDIR','/tmp/e3-stage5-mpl')
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 import numpy as np
 figdir=out/'figures';figdir.mkdir(exist_ok=True);colors=['#315b96','#c27820','#26836c','#9d4a61']
 def save(fig,name):
  fig.tight_layout();fig.savefig(figdir/(name+'.png'),dpi=160);fig.savefig(figdir/(name+'.svg'));plt.close(fig)
 fig,ax=plt.subplots(figsize=(7,4))
 for p,col in zip(POL,colors):
  rows=[r for r in result['runs'] if r['policy']==p];ax.plot([r['block'] for r in rows],[100*r['U_over_N'] for r in rows],'-o',label=p,color=col)
 ax.set(xlabel='Matched block',ylabel='Unique on-time / all2880 originals (%)',title='Primary all-original endpoint (five paired blocks)');ax.legend();save(fig,'deadline-goodput')
 fig,ax=plt.subplots(figsize=(8,4));names=list(result['paired']);x=[];lo=[];hi=[]
 for n in names:
  d=result['paired'][n]['U_over_N'];x.append(d['mean']*100);lo.append((d['mean']-d['interval95'][0])*100);hi.append((d['interval95'][1]-d['mean'])*100)
 ax.errorbar(x,range(len(names)),xerr=[lo,hi],fmt='o');ax.axvline(0,color='gray');ax.set_yticks(range(len(names)),names);ax.set(xlabel='Mean paired difference (percentage points)',title='Descriptive paired-block bootstrap95% intervals; n=5');save(fig,'paired-differences')
 fig,ax=plt.subplots(figsize=(8,4));labels=sorted({k for p in result['policies'].values() for k in p['counts_mean']});bottom=np.zeros(4)
 for label in labels:
  vals=np.array([result['policies'][p]['counts_mean'].get(label,0)/N*100 for p in POL]);ax.bar(POL,vals,bottom=bottom,label=label);bottom+=vals
 ax.set(ylabel='Mean fraction of all originals (%)',title='All-original terminal partitions; never completed-only denominator');ax.legend(fontsize=7,bbox_to_anchor=(1,1));save(fig,'outcomes')
 fig,axes=plt.subplots(2,1,figsize=(8,6),sharex=True)
 for p,col in zip(POL,colors):
  rows=[r for r in result['runs'] if r['policy']==p];series=np.array([[x['on_time_completions'] for x in r['recovery_series']] for r in rows]);back=np.array([[x['client_pending']+x['client_outstanding'] for x in r['recovery_series']] for r in rows]);t=list(range(24,40));axes[0].plot(t,series.mean(axis=0),label=p,color=col);axes[1].plot(t,back.mean(axis=0),label=p,color=col)
 axes[0].set(ylabel='Unique on-time completions /1s',title='Recovery means across five blocks; not steady-state proof');axes[1].set(xlabel='Seconds from workload epoch',ylabel='Client pending + outstanding');axes[0].legend();save(fig,'recovery')
 fig,ax=plt.subplots(figsize=(8,4))
 for j,(p,col) in enumerate(zip(POL,colors)):
  rows=[r for r in result['runs'] if r['policy']==p];ax.scatter([j]*len(rows),[r['completion_latency_ns']['p95']/1e6 for r in rows],label=p,color=col)
 ax.set_xticks(range(4),POL);ax.set(ylabel='Scheduled→completion p95 (ms)',title='Conditional on completed originals; cohort counts in RESULTS.json');save(fig,'conditional-latency')
 fig,axes=plt.subplots(1,2,figsize=(9,4))
 for j,(p,col) in enumerate(zip(POL,colors)):
  rows=[r for r in result['runs'] if r['policy']==p];axes[0].scatter([j]*len(rows),[r['process_metrics']['server']['cpu_window_ns']/1e9 for r in rows],color=col);axes[1].scatter([j]*len(rows),[r['process_metrics']['server']['sampled_rss_peak_bytes']/2**20 for r in rows],color=col)
 for ax in axes:ax.set_xticks(range(4),POL)
 axes[0].set(ylabel='Server sampled-window CPU (s)',title='Jiffy-quantized, sampled endpoints');axes[1].set(ylabel='Server sampled RSS peak (MiB)',title='Lower bound on true peak');save(fig,'resources')

def selftest():
 assert paired([0]*5)['interval95']==[0,0]
 assert quantile([0,10],.95)==9.5
 assert integrate([{'offset_ns':0,'v':2},{'offset_ns':1_000_000_000,'v':0}],lambda e:e['v'])==2_000_000_000
 assert paired([1]*5)['mean']==1
 print('PASS: bootstrap/quantile/integral self-tests')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--selftest',action='store_true');a=p.parse_args();selftest() if a.selftest else analyze()
