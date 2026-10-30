#!/usr/bin/env python3
"""Independent pilot gates, extending Stage3 replay rather than trusting summaries."""
import argparse,csv,hashlib,importlib.util,json,statistics
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('e3_verify',Path(__file__).with_name('verify-stage3.py'))
V=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(V)
def verify(run):
 d=V.load(run);result=V.verify(d);m=d['manifest'];c=d['client'];s=d['server'];w=d['workload']
 need=V.need;low=m['profile']=='low';rate=10 if low else 80;duration=4 if low else 36;cutoff=(7 if low else 39)*1_000_000_000
 need(m['pilot_only'] and not m['worker_barrier'] and m['client_event_buffer_bytes'] in [0,65536],'pilot controls')
 need(m['source_hashes_unchanged'] and m['server_exit']==m['client_exit']==0,'source/process status')
 need(len(w['originals'])==rate*duration and m['observation_cutoff_ns']==cutoff,'frozen pilot shape')
 for i,o in enumerate(w['originals']):need(o['scheduled_offset_ns']==i*(1_000_000_000//rate) and o['deadline_offset_ns']==o['scheduled_offset_ns']+2_000_000_000 and o['expendable'],'workload/deadline drift')
 need(c['profile']==m['profile'] and c['observation_end_offset_ns']>=cutoff,'client observation cutoff')
 need(m['server_observation']['cutoff_ns']==cutoff and m['server_observation']['actual_offset_ns']>=cutoff,'server observation cutoff')
 need(s['occupied']==s['decoded_staging']==s['receive_stage_reservation']==s['terminal_responses_reserved']==s['immediate_responses']==s['event_writer_queue']==0,'final server resource cleanup')
 need(s['queued_payload_bytes']==s['worker_payload_bytes']==s['staging_payload_bytes']==0,'final payload ownership')
 need(c['client']['Pending']==c['client']['Outstanding']==c['client']['EventQueue']==0,'final client queues')
 arrivals=[e for e in d['client_events'] if e['kind']=='original_arrival'];need(len(arrivals)==len(w['originals']),'missing scheduled original')
 half=[e for e in d['client_events'] if e['kind']=='client_half_close'];need(len(half)==1,'client EOF evidence')
 need(c['rpc_end_offset_ns']<=cutoff and half[0]['offset_ns']<=c['rpc_end_offset_ns'],'EOF/drain beyond cutoff')
 phases=[json.loads(x) for x in (run/'server/phases.jsonl').read_text().splitlines()]
 expected=[x for x in [0,12_000_000_000,24_000_000_000,36_000_000_000,cutoff] if x<=cutoff]
 need([x['expected_offset_ns'] for x in phases]==sorted(set(expected)),'phase marker coverage')
 phase_lateness=[x['actual_offset_ns']-x['expected_offset_ns'] for x in phases];need(all(x>=0 for x in phase_lateness),'premature phase marker')
 services={'initial':[],'slowdown':[],'recovery':[],'drain':[]}
 for o in s['originals']:
  if not o['starts']:continue
  need(o['exit_ns'] is not None and o['exit_ns']<=cutoff,'live/unresolved worker at cutoff')
  start=o['start_ns'];phase='initial' if start<12_000_000_000 else 'slowdown' if start<24_000_000_000 else 'recovery' if start<36_000_000_000 else 'drain'
  elapsed=o['exit_ns']-start;services[phase].append(elapsed)
  if o['terminal']['outcome']==1:need(elapsed>=(40_000_000 if phase=='slowdown' else 10_000_000),'service timer violates selected start phase')
  elif o['terminal']['outcome'] in [4,6]:need(o['cancellation_requested_ns'] is not None and o['cancellation_observed_ns'] is not None,'cancellation accounting')
 if not low:need(all(services[p] for p in ['initial','slowdown','recovery']),'missing workload phase')
 sampled={}
 for role,rows in d['metrics'].items():
  b=d['clock']['start'] if role=='server' else c['client']['ClockStart']
  epoch=(b['epoch_min_ns']+b['epoch_max_ns'])//2 if role=='server' else (b['EpochMinNS']+b['EpochMaxNS'])//2
  t=[int(x['host_monotonic_ns']) for x in rows]
  need(t[0]<=epoch and t[-1]>=epoch+cutoff,'process sampling fails cutoff coverage: '+role)
  sampled[role]={'first_offset_ns':t[0]-epoch,'last_offset_ns':t[-1]-epoch,'max_gap_ns':max(v-u for u,v in zip(t,t[1:])),'rows':len(rows)}
 activation={'full_rejections':sum(a['terminal']['outcome']==2 for a in s['attempts']),'full_drops':sum(a['terminal']['outcome']==3 for a in s['attempts']),'actual_retries':c['client']['Retries']}
 if low:need(result['partition']=={'COMPLETED_ON_TIME':40},'low-rate normal delivery failed')
 result.update({'pilot_only':True,'profile':m['profile'],'policy':m['policy'],'genuine_activation':activation,'phase_marker_lateness_ns':phase_lateness,'service_by_start_phase':{k:{'count':len(v),'min_ns':min(v) if v else None,'median_ns':statistics.median(v) if v else None,'max_ns':max(v) if v else None} for k,v in services.items()},'sampling_coverage':sampled,'rpc_end_offset_ns':c['rpc_end_offset_ns'],'client_half_close_offset_ns':half[0]['offset_ns'],'drain_after_arrivals_ns':max(0,c['rpc_end_offset_ns']-duration*1_000_000_000),'observation_end_offset_ns':c['observation_end_offset_ns'],'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);a=p.parse_args()
 try:r=verify(a.run)
 except (V.Invalid,ValueError,KeyError) as e:r={'verdict':'FAIL','error':str(e)}
 (a.run/'pilot-verification.json').write_text(json.dumps(r,indent=2)+'\n');print(r['verdict'],r.get('error',''),flush=True)
 if r['verdict']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
