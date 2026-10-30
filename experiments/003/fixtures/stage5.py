#!/usr/bin/env python3
"""Preregistration freeze and serial matched-block execution. No app source edits."""
import argparse,fcntl,hashlib,importlib.util,json,os,platform,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'experiments/003/results/stage5';FROZEN=OUT/'FROZEN-MANIFEST.json'
ENV=['GOMAXPROCS','GOGC','GOMEMLIMIT','GODEBUG','GOFLAGS','RUSTFLAGS','CARGO_PROFILE_DEV_OPT_LEVEL','TOKIO_WORKER_THREADS','RUST_LOG']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):
 with p.open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
def atomic(p,obj):
 tmp=p.with_suffix('.pending');tmp.write_text(json.dumps(obj,indent=2)+'\n');tmp.replace(p)
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def source_paths():
 return sorted([p for p in (ROOT/'experiments/003').rglob('*') if p.is_file() and not any(x in p.parts for x in ['target','results','__pycache__'])]+[ROOT/'scripts/dev-env.sh',OUT/'RUN-PLAN.json',OUT/'WORKLOAD.json'])
def freeze():
 if FROZEN.exists():raise RuntimeError('freeze exists; immutable, do not overwrite')
 if git('status','--porcelain'):raise RuntimeError('commit preregistration before freezing/building')
 commit=git('rev-parse','HEAD');commands=[]
 cmds=['source scripts/dev-env.sh\ncargo build --locked --manifest-path experiments/003/server/Cargo.toml','source scripts/dev-env.sh\ncd experiments/003/client\ngo mod verify\ngo build -mod=readonly -o /workspace/toolchains/bin/e3-primary-client ./cmd/pilot']
 for i,cmd in enumerate(cmds):
  log=Path(f'/tmp/e3-stage5-freeze-build-{i}.log');start=time.time_ns()
  with log.open('w') as f:r=subprocess.run(['bash','-e','-c',cmd],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=120)
  commands.append({'argv':['bash','-e','-c',cmd],'exit':r.returncode,'started_unix_ns':start,'log':str(log)})
  if r.returncode:raise RuntimeError('normal build failed')
 # Repeat normal builds before recording hashes: prove reproducibility, not test-feature target identity.
 server=ROOT/'experiments/003/server/target/debug/pressure-e3-stage1';client=Path('/workspace/toolchains/bin/e3-primary-client');before={str(p):sha(p) for p in [server,client]}
 for cmd in cmds:
  subprocess.run(['bash','-e','-c',cmd],cwd=ROOT,check=True,stdout=subprocess.DEVNULL,timeout=120)
 assert before=={str(p):sha(p) for p in [server,client]}
 if git('status','--porcelain'):raise RuntimeError('build unexpectedly dirtied committed source')
 binary_dir=Path('/tmp')/('grpc-e3-stage5-'+commit[:12]+'-'+str(time.time_ns()));binary_dir.mkdir()
 binary={}
 for src,name in [(server,'server'),(client,'client')]:
  dst=binary_dir/name;shutil.copy2(src,dst);dst.chmod(0o555);binary[str(dst)]=sha(dst)
 toolchains=subprocess.check_output(['bash','-c','source scripts/dev-env.sh; rustc -Vv; cargo -V; go version'],cwd=ROOT,text=True).strip()
 pypack=subprocess.check_output([sys.executable,'-c','import matplotlib,numpy;print(matplotlib.__version__,numpy.__version__)'],env=dict(os.environ,MPLCONFIGDIR='/tmp/e3-stage5-mpl'),text=True).strip()
 frozen={'source_commit':commit,'application_baseline_commit':'e1370b0e625eec48fb39b94c6a5b4487f1abd962','preregistration_commit':commit,'created_unix_ns':time.time_ns(),'before_primary_execution':True,'clean_build_tree':True,'contract_revision':'A01','build_profile':'normal debug, no tests after final build','source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in source_paths()},'binary_sha256':binary,'normal_build_binary_sha256':before,'server_binary':str(binary_dir/'server'),'client_binary':str(binary_dir/'client'),'build_commands':commands,'toolchains':toolchains,'python':sys.version,'matplotlib_numpy':pypack,'environment':platform.uname()._asdict(),'runtime_environment':{k:os.environ.get(k) for k in ENV},'cgroup':{k:Path('/sys/fs/cgroup/'+k).read_text().strip() for k in ['cpu.max','memory.max']},'plan_sha256':sha(OUT/'RUN-PLAN.json'),'workload_sha256':sha(OUT/'WORKLOAD.json')}
 # The committed application trees must be unchanged from the accepted Stage4 baseline.
 app=[p for p in source_paths() if p.suffix in ['.rs','.go','.proto'] or p.name in ['Cargo.toml','Cargo.lock','go.mod','go.sum']]
 for p in app:
  old=subprocess.check_output(['git','show',f"e1370b0:{p.relative_to(ROOT)}"],cwd=ROOT);assert hashlib.sha256(old).hexdigest()==sha(p),str(p)
 frozen['application_identical_to_accepted_stage4']=True
 save(FROZEN,frozen)
 for i in range(len(cmds)):shutil.copy2(f'/tmp/e3-stage5-freeze-build-{i}.log',OUT/f'freeze-build-{i}.log')
 print('FROZEN',commit,binary,flush=True)

def guard():
 f=json.loads(FROZEN.read_text())
 assert git('rev-parse','HEAD')==f['source_commit'],'commit drift'
 assert {k:os.environ.get(k) for k in ENV}==f['runtime_environment'],'runtime environment drift'
 assert {k:Path('/sys/fs/cgroup/'+k).read_text().strip() for k in f['cgroup']}==f['cgroup'],'cgroup drift'
 assert sha(OUT/'RUN-PLAN.json')==f['plan_sha256'] and sha(OUT/'WORKLOAD.json')==f['workload_sha256'],'plan/workload drift'
 for name,h in f['source_sha256'].items():assert sha(ROOT/name)==h,'source drift '+name
 for name,h in f['binary_sha256'].items():assert sha(name)==h,'binary drift '+name
 return f

def category(run,error):
 if (run/'verification.json').exists():
  m=json.loads((run/'verification.json').read_text())
  if m.get('safety_abort'):return 'SAFETY_STOP'
  if (run/'primary-verification.json').exists():
   reason=json.loads((run/'primary-verification.json').read_text()).get('error','')
   if 'clock' in reason:return 'TRANSIENT_CLOCK'
   if 'sampling' in reason or 'metric' in reason:return 'TRANSIENT_SAMPLING'
   return 'INTEGRITY_STOP: '+reason
 if any(k in str(error).lower() for k in ['source','binary','drift','frozen','workload']):return 'SOURCE_STOP'
 return 'TRANSIENT_OPERATIONAL'

def execute():
 guard()
 if (OUT/'MATRIX.json').exists():raise RuntimeError('matrix already exists; no silent resume/reselection')
 plan=json.loads((OUT/'RUN-PLAN.json').read_text());matrix={'frozen_sha256':sha(FROZEN),'status':'RUNNING','started_unix_ns':time.time_ns(),'blocks':[]};atomic(OUT/'MATRIX.json',matrix)
 spec=importlib.util.spec_from_file_location('primary_engine',ROOT/'experiments/003/fixtures/primary-run.py');engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
 transients={}
 with open('/tmp/grpc-under-pressure-e3-stage4.lock','a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  for block in plan['blocks']:
   accepted=False
   for attempt in range(1,plan['max_full_block_attempts']+1):
    guard();parent=OUT/f"block-{block['block']:02d}-attempt-{attempt:02d}";parent.mkdir(exist_ok=False)
    save(parent/'block-manifest.json',{'block':block,'attempt':attempt,'frozen_sha256':sha(FROZEN),'created_before_block':True})
    entry={'block':block['block'],'attempt':attempt,'seed':block['jitter_seed'],'order':block['order'],'status':'RUNNING','runs':{},'verdicts':{}}
    matrix['blocks'].append(entry);atomic(OUT/'MATRIX.json',matrix);bad=None
    for policy in block['order']:
     guard();run=parent/policy;entry['runs'][policy]=str(run.relative_to(ROOT));atomic(OUT/'MATRIX.json',matrix)
     print(f"START block{block['block']} attempt{attempt} {policy} seed{block['jitter_seed']}",flush=True)
     try:engine.run('overload',policy,run,0,block['jitter_seed'])
     except (SystemExit,Exception) as e:
      bad=category(run,e);entry['verdicts'][policy]='INVALID';entry['reason']=bad;entry['error']=repr(e);break
     entry['verdicts'][policy]='PASS';atomic(OUT/'MATRIX.json',matrix)
    if bad is None:entry['status']='VALID';accepted=True;atomic(OUT/'MATRIX.json',matrix);print('VALID BLOCK',block['block'],flush=True);break
    entry['status']='EXCLUDED_ENTIRE_BLOCK';atomic(OUT/'MATRIX.json',matrix)
    transients[bad]=transients.get(bad,0)+1
    if 'STOP' in bad or transients[bad]>=2 or attempt==plan['max_full_block_attempts']:
     matrix['status']='STOPPED_FOR_REVIEW';matrix['stop_reason']=bad;atomic(OUT/'MATRIX.json',matrix);print('STOP FOR REVIEW',bad,flush=True);return
    print('REPLACE ENTIRE BLOCK under preregistered rule:',bad,flush=True)
   if not accepted:break
  matrix['status']='COMPLETE' if sum(b['status']=='VALID' for b in matrix['blocks'])==plan['required_valid_blocks'] else 'INCOMPLETE'
  matrix['completed_unix_ns']=time.time_ns();atomic(OUT/'MATRIX.json',matrix)
 print('MATRIX',matrix['status'],flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','execute']);a=p.parse_args();freeze() if a.phase=='freeze' else execute()
