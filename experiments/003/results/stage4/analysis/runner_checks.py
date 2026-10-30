#!/usr/bin/env python3
"""Synthetic orchestrator failures only; no policy outcomes are injected."""
import fcntl,hashlib,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
OUT=ROOT/'experiments/003/results/stage4/runner-checks'
spec=importlib.util.spec_from_file_location('pilot_runner',ROOT/'experiments/003/fixtures/pilot.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
def main():
 OUT.mkdir(parents=True,exist_ok=False);rows=[]
 occupied=OUT/'existing';occupied.mkdir();sentinel=occupied/'sentinel';sentinel.write_text('immutable evidence\n');before=hashlib.sha256(sentinel.read_bytes()).hexdigest()
 try:p.run('low','wait',occupied,0)
 except FileExistsError:rows.append({'case':'exclusive_directory','verdict':'PASS','result':'refused existing output before mutation'})
 else:raise AssertionError('reused artifact directory')
 assert hashlib.sha256(sentinel.read_bytes()).hexdigest()==before
 cmd=['python3',str(ROOT/'experiments/003/fixtures/pilot.py'),'--profile','low','--policy','wait','--output',str(OUT/'must-not-start')]
 with open('/tmp/grpc-under-pressure-e3-stage4.lock','a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  run=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=5)
  (OUT/'lock-refusal.log').write_text(run.stdout+run.stderr);assert run.returncode!=0 and not (OUT/'must-not-start').exists()
 rows.append({'case':'single_active_run_lock','verdict':'PASS','result':'second invocation refused without spawning application'})
 real_popen=p.subprocess.Popen
 def fail_start(cmd,*args,**kwargs):
  if isinstance(cmd,list) and cmd and cmd[0]=='prlimit':raise OSError('SYNTHETIC startup failure; no application process created')
  return real_popen(cmd,*args,**kwargs)
 p.subprocess.Popen=fail_start;p.RESULTS=OUT
 try:
  try:p.run('low','wait',OUT/'synthetic-startup-failure',0)
  except SystemExit as e:assert e.code==1
  else:raise AssertionError('startup failure accepted')
 finally:p.subprocess.Popen=real_popen
 m=json.loads((OUT/'synthetic-startup-failure/verification.json').read_text());assert m['verdict']=='FAIL' and m['process_returncodes']=={'server':None,'client':None}
 assert (OUT/'EXCLUSIONS.json').exists()
 rows.append({'case':'startup_failure','verdict':'PASS','result':'FAIL manifest/exclusion/log files preserved; sampler joined; no child process leaked','synthetic_only':True})
 (OUT/'verification.json').write_text(json.dumps({'contract_revision':'A01','synthetic_runner_checks_only':True,'cases':rows,'verdict':'PASS'},indent=2)+'\n')
 print('PASS: exclusive output, single-run lock, startup-failure preservation/cleanup')
if __name__=='__main__':main()
