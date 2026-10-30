#!/usr/bin/env python3
"""Semantic corruption tests: mutate in-memory copies, never real raw evidence."""
import argparse,copy,importlib.util,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('verifier',Path(__file__).with_name('verify-stage3.py'));v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def duplicate_start(d):
 e=next(x for x in d['server_events'] if x['kind']=='worker_start');index=d['server_events'].index(e);d['server_events'].insert(index+1,copy.deepcopy(e))
 for i,x in enumerate(d['server_events']):x['seq']=i+1
 d['server']['event_seq']+=1

def main():
 p=argparse.ArgumentParser();p.add_argument('--run',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();baseline=v.load(a.run);v.verify(baseline)
 def change_count(d):d['client']['client']['SendSuccess']+=1
 def partition(d):d['client']['server_reconciliation']['Outcomes'][0]['disposition']='DROPPED'
 def clock(d):d['clock']['end']['epoch_min_ns']+=6_000_000;d['clock']['end']['epoch_max_ns']+=6_000_000
 def metric_gap(d):d['metrics']['client'][1]['host_monotonic_ns']=str(int(d['metrics']['client'][0]['host_monotonic_ns'])+1_000_000_000)
 cases=[('unexpected-stream-failure',lambda d:d['server'].update(failed='STREAM_FAILED')),('missing-middle',lambda d:d['server_events'].pop(2)),('missing-tail',lambda d:d['client_events'].pop()),('duplicate-worker-start-with-renumbered-log',duplicate_start),('send-counter',change_count),('wrong-partition',partition),('resource-overflow',lambda d:d['client_events'][0].update(pending=34)),('server-overflow',lambda d:d['server_events'][0]['resources'].update(terminal=33)),('clock-misalignment',clock),('missing-process-samples',lambda d:d['metrics'].update(client=[])),('sampling-gap',metric_gap),('A01-drift',lambda d:d['manifest'].update(client_outstanding_limit=32)),('high-water-mismatch',lambda d:d['server']['high_water'].update(immediate=31)),('transport-count',lambda d:d['client']['transport'].update(grpc_out_messages=999)),('missing-provenance',lambda d:d['manifest'].update(source_sha256={}))]
 rows=[]
 for name,inject in cases:
  d=copy.deepcopy(baseline);inject(d)
  try:v.verify(d)
  except (v.Invalid,ValueError,KeyError) as e:rows.append({'fault':name,'verdict':'REJECTED','reason':str(e)})
  else:raise RuntimeError('Verifier accepted invalid fixture: '+name)
 a.output.mkdir(parents=True,exist_ok=False);(a.output/'verification.json').write_text(json.dumps({'contract_revision':'A01','synthetic_faults_only':True,'baseline':str(a.run),'positive_control':'PASS','faults':rows,'verdict':'PASS'},indent=2)+'\n')
 print('PASS: rejected',len(rows),'deliberate semantic corruptions; raw evidence unchanged')
if __name__=='__main__':main()
