#!/usr/bin/env python3
"""Stage4-specific negative gates; in-memory mutations, no live policy injection."""
import copy,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
spec=importlib.util.spec_from_file_location('verify4',ROOT/'experiments/003/fixtures/verify-stage4.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def main():
 baseline=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False);d=v.V.load(baseline);phases=(baseline/'server/phases.jsonl').read_text();v.verify(baseline);real_load=v.V.load;cases=[]
 def short_sampling(x):
  b=x['clock']['start'];epoch=(b['epoch_min_ns']+b['epoch_max_ns'])//2
  x['metrics']['server']=[r for r in x['metrics']['server'] if int(r['host_monotonic_ns'])<epoch+38_000_000_000]
 tests=[('client-exits-before-cutoff',lambda x:x['client'].update(observation_end_offset_ns=38_000_000_000),None),('sampler-stops-before-cutoff',short_sampling,None),('worker-barrier-enabled',lambda x:x['manifest'].update(worker_barrier=True),None),('RPC-not-drained-by-cutoff',lambda x:x['client'].update(rpc_end_offset_ns=40_000_000_000),None),('missing-phase-cutoff',lambda x:None,'\n'.join(phases.splitlines()[:-1])+'\n')]
 try:
  for name,inject,phase in tests:
   data=copy.deepcopy(d);inject(data);run=out/name;(run/'server').mkdir(parents=True);(run/'server/phases.jsonl').write_text(phase if phase is not None else phases);v.V.load=lambda _:data
   try:v.verify(run)
   except (v.V.Invalid,KeyError,ValueError) as e:cases.append({'fault':name,'result':'REJECTED','reason':str(e),'synthetic_only':True})
   else:raise AssertionError('invalid pilot accepted: '+name)
 finally:v.V.load=real_load
 (out/'verification.json').write_text(json.dumps({'contract_revision':'A01','synthetic_only':True,'positive_control':'PASS','cases':cases,'verdict':'PASS'},indent=2)+'\n')
 print('PASS: five Stage4-specific corrupted coverage/control fixtures rejected')
if __name__=='__main__':main()
