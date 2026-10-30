#!/usr/bin/env python3
"""Pilot measurement/activation summary only; no policy ranking or hypothesis test."""
import bisect,csv,json,statistics,sys
from pathlib import Path
OUT=Path(sys.argv[1]);names=['final-low-wait','overload-wait','overload-reject','overload-retry','overload-drop','overhead-wait-buffered']
summary={}
def pct(xs,p):return sorted(xs)[min(len(xs)-1,int((len(xs)-1)*p))] if xs else None
for name in names:
 d=OUT/name;m=json.loads((d/'verification.json').read_text());v=json.loads((d/'pilot-verification.json').read_text());c=json.loads((d/'client-report.json').read_text());s=json.loads((d/'server/server-ledger.json').read_text());ce=[json.loads(x) for x in (d/'client-events.jsonl').read_text().splitlines()];se=[json.loads(x) for x in (d/'server/server-events.jsonl').read_text().splitlines()];work=json.loads((d/'workload.json').read_text())
 phase=[]
 for lo,hi,label in [(0,12e9,'initial'),(12e9,24e9,'slowdown'),(24e9,36e9,'recovery'),(36e9,39e9,'drain')]:
  group=[o for o in s['originals'] if o['start_ns'] is not None and lo<=o['start_ns']<hi];completed=[o['terminal']['worker_service_ns'] for o in group if o['terminal']['outcome']==1]
  phase.append({'phase':label,'starts':len(group),'completed':len(completed),'processing_expiries':sum(o['terminal']['outcome']==4 for o in group),'completed_only_service_median_ns':statistics.median(completed) if completed else None})
 arrival_late=[e['offset_ns']-work['originals'][e['message_id']]['scheduled_offset_ns'] for e in ce if e['kind']=='original_arrival'];blocked_arrivals=[e for e in ce if e['kind']=='original_arrival' and e.get('state')=='CLIENT_BACKLOG_EXHAUSTED']
 final={k:v[k] for k in ['verdict','counter_populations','partition','genuine_activation','clock_uncertainty_ns','client_high_water','server_high_water','sampling_coverage','rpc_end_offset_ns','client_half_close_offset_ns','drain_after_arrivals_ns','observation_end_offset_ns','phase_marker_lateness_ns']}
 final.update({'profile':m['profile'],'policy':m['policy'],'event_buffer_bytes':m['client_event_buffer_bytes'],'worker_start_phase_cohorts':phase,'arrival_lateness_ns':{'median':statistics.median(arrival_late),'p99':pct(arrival_late,.99),'max':max(arrival_late)},'backlog_full_arrivals':{'count':len(blocked_arrivals),'outstanding33':sum(e['outstanding']==33 for e in blocked_arrivals),'available_credit_at_arrival':sum(e['outstanding']<33 for e in blocked_arrivals)},'send_duration_ns':{'p50':pct(v['send_duration_ns'],.5),'p95':pct(v['send_duration_ns'],.95),'p99':pct(v['send_duration_ns'],.99),'max':max(v['send_duration_ns'])},'process_metrics':v['process_metrics'],'record_storage_estimates_bytes':{'client':c['client']['LedgerAllocatedBytes'],'server':s['allocated_ledger_bytes']},'event_log_bytes':{'client':(d/'client-events.jsonl').stat().st_size,'server':(d/'server/server-events.jsonl').stat().st_size},'transport':c['transport'],'writer_local_progress_ns':v['writer_local_progress_ns']})
 summary[name]=final
 for role,events in [('client',ce),('server',se)]:
  b=json.loads((d/'server/clock.json').read_text())['start'] if role=='server' else c['client']['ClockStart'];epoch=(b['epoch_min_ns']+b['epoch_max_ns'])//2 if role=='server' else (b['EpochMinNS']+b['EpochMaxNS'])//2
  ts=[e['offset_ns'] if role=='server' else e['commit_offset_ns'] for e in events];need_sorted=all(a<=b for a,b in zip(ts,ts[1:]));assert need_sorted
  rows=list(csv.DictReader((d/(role+'-metrics.csv')).open()));cpu_window=[]
  with (d/(role+'-series.csv')).open('w') as f:
   writer=csv.writer(f);writer.writerow(['contract_revision','offset_ns','rss_bytes','cpu_percent_one_core_quantized','queue_or_pending','running_or_outstanding','staging','queued_payload_bytes','worker_payload_bytes'])
   for i,row in enumerate(rows):
    t=int(row['host_monotonic_ns'])-epoch;idx=bisect.bisect_right(ts,t)-1;e=events[idx] if idx>=0 else None;cpu=int(row['cpu_user_ns'])+int(row['cpu_system_ns']);percent=''
    if i:
     p=rows[i-1];delta=int(row['host_monotonic_ns'])-int(p['host_monotonic_ns']);percent=100*(cpu-int(p['cpu_user_ns'])-int(p['cpu_system_ns']))/delta
    if t>=0 and (not cpu_window or cpu_window[-1][0]<m['observation_cutoff_ns']):cpu_window.append((t,cpu))
    q=(e['queued'] if role=='server' else e['pending']) if e else 0;running=(e['running'] if role=='server' else e['outstanding']) if e else 0;stage=e['resources']['staging'] if role=='server' and e else 0
    writer.writerow(['A01',t,row['rss_bytes'],percent,q,running,stage,q*16384 if role=='server' else '',running*16384 if role=='server' else ''])
  final['process_metrics'][role]['sample_window_cpu_ns']=cpu_window[-1][1]-cpu_window[0][1];final['process_metrics'][role]['sample_window_offsets_ns']=[cpu_window[0][0],cpu_window[-1][0]]
base,control=summary['overload-wait'],summary['overhead-wait-buffered']
overhead={'pilot_instrumentation_control_only':True,'replicated_pairs':1,'only_requested_change':'client event-output buffer0 vs65536, same final source/binaries/workload/policy/guards','same_workload_sha256':json.loads((OUT/'overload-wait/verification.json').read_text())['workload_sha256']==json.loads((OUT/'overhead-wait-buffered/verification.json').read_text())['workload_sha256'],'cpu_delta_buffered_minus_direct_ns':{role:control['process_metrics'][role]['sample_window_cpu_ns']-base['process_metrics'][role]['sample_window_cpu_ns'] for role in ['server','client']},'direct_partition':base['partition'],'buffered_partition':control['partition'],'direct_log_bytes':base['event_log_bytes'],'buffered_log_bytes':control['event_log_bytes'],'limitations':['One nonconsecutive pair on shared host; no confidence interval or attribution of outcome differences.','10ms CPU quantization and200ms sampling: window starts at first sample at/after epoch and ends at first sample at/after cutoff; endpoints approximate.','Event batching isolates a component of output cost, not total instrumentation overhead or state-lock accounting.','No policy configuration or default instrumentation changed based on results.']}
(OUT/'PILOT-SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n');(OUT/'INSTRUMENTATION-CONTROL.json').write_text(json.dumps(overhead,indent=2)+'\n')
print('PASS: six pilot summaries, resource/CPU series and instrumentation control')
