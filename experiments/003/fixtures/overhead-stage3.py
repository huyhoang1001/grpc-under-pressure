#!/usr/bin/env python3
"""Predeclared matched calibration of incremental JSON/file cost, not policies."""
import argparse,json,subprocess,hashlib,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 binary=ROOT/'experiments/003/server/target/debug/examples/measurement-cost'
 order=['file','no-encoding','no-encoding','file','file','no-encoding']
 manifest={'contract_revision':'A01','calibration_only':True,'order':order,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'experiments/003').rglob('*') if p.is_file() and not any(x in p.parts for x in ['target','results','__pycache__'])},'dirty_state':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),'toolchains':subprocess.check_output(['bash','-c','source scripts/dev-env.sh; rustc -V; cargo -V; go version'],cwd=ROOT,text=True).strip(),'configuration':{'client_outstanding':33,'client_pending':32,'server_admission':32,'rounds':5,'originals_per_round':64,'event_buffer':1024},'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'commands':[]};(out/'predeclared.json').write_text(json.dumps(manifest,indent=2)+'\n')
 rows=[]
 for index,mode in enumerate(order):
  run=out/f'{index+1}-{mode}';cmd=['prlimit','--cpu=5','--fsize=16777216','--core=0','--',str(binary),'--mode',mode,'--output',str(run)]
  result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=10);(out/f'{index+1}.log').write_text(result.stdout+result.stderr);manifest['commands'].append({'argv':cmd,'exit':result.returncode})
  if result.returncode:raise RuntimeError('calibration failed; preserve partial evidence')
  rows.append(json.loads((run/'summary.json').read_text()))
 pairs=[]
 for i in range(0,len(rows),2):
  by={r['mode']:r for r in rows[i:i+2]};yes,no=by['file'],by['no-encoding'];assert yes['events']==no['events'] and yes['unique_fixture_completions']==no['unique_fixture_completions']
  pairs.append({'cpu_delta_ns':yes['cpu_ns']-no['cpu_ns'],'wall_delta_ns':yes['wall_ns']-no['wall_ns'],'events_per_mode':yes['events']})
 manifest.update({'rows':rows,'pairs':pairs,'median_cpu_delta_ns':statistics.median(p['cpu_delta_ns'] for p in pairs),'cpu_delta_range_ns':[min(p['cpu_delta_ns'] for p in pairs),max(p['cpu_delta_ns'] for p in pairs)],'verdict':'PASS_CALIBRATION_NOT_PERFORMANCE','limitations':['Three pairs, noisy shared host; range is descriptive, not a confidence interval.','Measures incremental JSON+buffered file writes only, not total instrumentation overhead.','Both modes construct identical events and execute identical ledger transitions; no network/service timers.','No-encoding controls intentionally produce empty event files and are not valid experimental runs.']})
 (out/'summary.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
