#!/usr/bin/env python3
"""Derived measurement validity summaries; no policy performance inference."""
import csv,json,statistics,sys
from pathlib import Path
ROOT=Path(sys.argv[1])
final=['accepted-wait-drain','accepted-reject-drain','accepted-retry-drain','accepted-drop-drain','accepted-wait-cancel']
summary={}
for name in final:
 d=ROOT/name;v=json.loads((d/'independent-verification-v2.json').read_text());s=json.loads((d/'server/server-ledger.json').read_text());c=json.loads((d/'client-report.json').read_text());m=json.loads((d/'verification.json').read_text())
 summary[name]={'verdict':v['verdict'],'clock_uncertainty_ns':v['clock_uncertainty_ns'],'populations':v['counter_populations'],'partition':v['partition'],'client_high_water':v['client_high_water'],'server_high_water':v['server_high_water'],'process_metrics':v['process_metrics'],'transport':c['transport'],'ledger_record_estimates':{'server':s['allocated_ledger_bytes'],'client':c['client']['LedgerAllocatedBytes']},'log_bytes':{role:(d/('server/server-events.jsonl' if role=='server' else 'client-events.jsonl')).stat().st_size for role in ['server','client']}}
 for role in ['client','server']:
  process=list(csv.DictReader((d/(role+'-metrics.csv')).open()));state=list(csv.DictReader((d/(role+'-state.csv')).open()))
  with (d/(role+'-series.csv')).open('w') as f:
   writer=csv.writer(f);writer.writerow(['contract_revision','host_monotonic_ns','offset_ns','rss_bytes','cpu_percent_one_core_quantized','cpu_tick_ns','queue_or_pending','running_or_outstanding','cumulative_worker_exits_or_sends','final_ledger_record_estimate_reference_not_sampled_allocation'])
   for i,(p,t) in enumerate(zip(process,state)):
    percent=''
    if i:
     prev=process[i-1];dt=int(p['host_monotonic_ns'])-int(prev['host_monotonic_ns']);dc=int(p['cpu_user_ns'])+int(p['cpu_system_ns'])-int(prev['cpu_user_ns'])-int(prev['cpu_system_ns']);percent=100*dc/dt
    writer.writerow(['A01',p['host_monotonic_ns'],t['offset_ns'],p['rss_bytes'],percent,p['cpu_tick_ns'],t['queue_or_pending'],t['running_or_outstanding'],t['cumulative_worker_exits_or_sends'],t['ledger_record_bytes_estimate']])
pairs=[]
for i in range(1,4):
 pair={}
 for mode in ['optimized','legacy']:
  d=ROOT/f'sweep-v4-{i}-{mode}';v=json.loads((d/'independent-verification-v2.json').read_text());c=json.loads((d/'client-report.json').read_text());pair[mode]={'client_events':c['client']['EventSeq'],'client_log_bytes':(d/'client-events.jsonl').stat().st_size,'last_observed_client_cpu_ns':v['process_metrics']['client']['last_observed_cpu_ns'],'counts':v['counter_populations'],'partition':v['partition']}
 assert pair['optimized']['counts']==pair['legacy']['counts'] and pair['optimized']['partition']==pair['legacy']['partition']
 pair['client_cpu_delta_legacy_minus_optimized_ns']=pair['legacy']['last_observed_client_cpu_ns']-pair['optimized']['last_observed_client_cpu_ns'];pairs.append(pair)
(ROOT/'measurement-summary.json').write_text(json.dumps(summary,indent=2)+'\n');(ROOT/'sweep-overhead-summary.json').write_text(json.dumps({'calibration_only':True,'pairs':pairs,'cpu_delta_range_ns':[min(p['client_cpu_delta_legacy_minus_optimized_ns'] for p in pairs),max(p['client_cpu_delta_legacy_minus_optimized_ns'] for p in pairs)],'cpu_quantization_ns':10_000_000,'limitations':'Last observed CPU precedes process exit; three pairs on shared host, not a CI or total instrumentation cost.'},indent=2)+'\n')
