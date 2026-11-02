#!/usr/bin/env python3
"""Stage6 preregistered freeze and serial matched studies, append-only attempts."""
import fcntl,hashlib,importlib.util,json,os,platform,shutil,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'experiments/003/results/stage6'
spec=importlib.util.spec_from_file_location('run',Path(__file__).with_name('run.py'));R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
def atomic(p,o):
 q=p.with_suffix('.pending');q.write_text(json.dumps(o,indent=2)+'\n');q.replace(p)
def freeze():
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(),'commit preregistration/source/fixtures first'
 assert not R.FREEZE.exists(),'exclusive freeze already exists'
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 commands=['source scripts/dev-env.sh\ncargo build --locked --manifest-path experiments/003/secondary/server/Cargo.toml','source scripts/dev-env.sh\ncd experiments/003/secondary/client\ngo mod verify\ngo build -mod=readonly -o /tmp/e3-secondary-client ./cmd/secondary']
 server=ROOT/'experiments/003/secondary/server/target/debug/pressure-e3-stage1';client=Path('/tmp/e3-secondary-client');logs=[];hashes=[]
 for repeat in range(2):
  for cmd in commands:
   result=subprocess.run(['bash','-e','-c',cmd],cwd=ROOT,capture_output=True,text=True);logs.append({'argv':result.args,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr});assert result.returncode==0,result.stderr
  hashes.append([R.sha(server),R.sha(client)])
 assert hashes[0]==hashes[1],'normal build not reproducible'
 target=Path(tempfile.mkdtemp(prefix='grpc-e3-stage6-'+revision[:12]+'-'))
 for p,name in [(server,'server'),(client,'client')]:shutil.copyfile(p,target/name);os.chmod(target/name,0o555)
 # Source inputs only, plus frozen configuration. Historical raw evidence is not
 # read inside each workload; git/content preservation is checked before/after.
 paths=[]
 for name in ['experiments/003/secondary','experiments/003/server','experiments/003/client','experiments/003/proto']:
  paths += [p for p in (ROOT/name).rglob('*') if p.is_file() and not any(x in p.parts for x in ['target','__pycache__','.git'])]
 paths += [ROOT/'experiments/003'/name for name in ['EXPERIMENT-003.md','PROTOCOL-003.md','VALIDITY-003.md','STAGE5-PLAN.md','STAGE5-REPORT.md','STAGE6-PLAN.md']]
 paths += [OUT/'RUN-PLAN.json',*(OUT/'workloads').glob('*.json'),ROOT/'scripts/dev-env.sh',ROOT/'experiments/003/fixtures/verify-stage3.py']
 frozen={'source_commit':revision,'primary_baseline_commit':'4638543acede9756c51b752a0f694a39ef553d39','secondary_only':True,'contract_revision':'A01','created_unix_ns':time.time_ns(),'before_study_execution':True,'clean_build_tree':True,'normal_debug_builds':logs,'repeated_normal_binary_hashes':hashes,'source_sha256':{str(p.relative_to(ROOT)):R.sha(p) for p in paths},'binary_sha256':{str(target/name):R.sha(target/name) for name in ['server','client']},'server_binary':str(target/'server'),'client_binary':str(target/'client'),'toolchains':subprocess.check_output(['bash','-c','source scripts/dev-env.sh; rustc -Vv; cargo -V; go version'],cwd=ROOT,text=True),'python':sys.version,'environment':platform.uname()._asdict(),'cgroup':{p:Path('/sys/fs/cgroup/'+p).read_text().strip() for p in ['cpu.max','memory.max']},'runtime_environment':{p:os.environ.get(p) for p in ['GOMAXPROCS','GOGC','GOMEMLIMIT','GODEBUG','GOFLAGS','RUSTFLAGS','TOKIO_WORKER_THREADS','RUST_LOG']}}
 R.save(R.FREEZE,frozen);print('FROZEN',revision,hashes[0],flush=True)
def execute():
 R.source_guard()
 for name in ['a500-wait','a5000-wait','b-deterministic','b-jitter']:
  assert json.loads((OUT/f'preflight/pinned/{name}-registry.json').read_text())['outcome']['verdict']=='PASS','pinned preflight gate'
 assert json.loads((OUT/'checks/fault-verification-pinned.json').read_text())['verdict']=='PASS','verifier fault gate'
 plan=json.loads((OUT/'RUN-PLAN.json').read_text());matrix={'status':'RUNNING','started_unix_ns':time.time_ns(),'frozen_sha256':R.sha(R.FREEZE),'blocks':[],'attempts':[]}
 R.save(OUT/'MATRIX.json',matrix);categories=set()
 with open('/tmp/grpc-under-pressure-e3-stage4.lock','a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  for block in plan['blocks']:
   for attempt in [1,2]:
    directory=OUT/f'{block["study"]}-block-{block["block"]:02}-attempt-{attempt:02}';directory.mkdir(exist_ok=False);R.save(directory/'block-manifest.json',{**block,'attempt':attempt,'frozen_sha256':matrix['frozen_sha256']})
    entry={**block,'attempt':attempt,'status':'RUNNING','runs':{}};matrix['blocks'].append(entry);atomic(OUT/'MATRIX.json',matrix);failed=None
    for case in block['cases']:
     R.source_guard();path=directory/case['name'];print('START',block['study'],block['block'],attempt,case['name'],flush=True)
     try:verdict=R.run(case,path)
     except BaseException as error:
      verdict={'verdict':'FAIL','reason':repr(error),'safety_abort':False}
      if path.exists() and not (path/'outcome.json').exists():R.save(path/'outcome.json',verdict)
     entry['runs'][case['name']]={'directory':str(path.relative_to(ROOT)),**verdict};matrix['attempts'].append({'study':block['study'],'block':block['block'],'attempt':attempt,'case':case['name'],'directory':str(path.relative_to(ROOT)),**verdict});atomic(OUT/'MATRIX.json',matrix)
     if verdict['verdict']!='PASS':failed=verdict;break
    if failed is None:entry['status']='VALID';atomic(OUT/'MATRIX.json',matrix);print('VALID BLOCK',block['study'],block['block'],flush=True);break
    entry['status']='EXCLUDED_WHOLE_BLOCK';reason=failed['reason'] or 'unknown failure';category=next((c for c in ['clock','sampling','startup'] if c in reason.lower()),None)
    if category is None and any(word in reason.lower() for word in ['timeout waiting','exited before']):category='startup'
    stop=failed['safety_abort'] or category is None or category in categories or attempt==2
    if category:categories.add(category)
    entry['exclusion_reason']=reason;atomic(OUT/'MATRIX.json',matrix)
    if stop:matrix['status']='STOPPED_FOR_REVIEW';atomic(OUT/'MATRIX.json',matrix);exclusions(matrix);print('STOP FOR REVIEW',reason,flush=True);raise SystemExit(1)
  matrix['status']='COMPLETE';matrix['completed_unix_ns']=time.time_ns();atomic(OUT/'MATRIX.json',matrix);exclusions(matrix);print('SECONDARY MATRIX COMPLETE',flush=True)
def exclusions(matrix):
 atomic(OUT/'EXCLUSIONS.json',{'attempts':matrix['attempts'],'excluded_blocks':[b for b in matrix['blocks'] if b['status']!='VALID'],'replacement_attempts':[b for b in matrix['blocks'] if b['attempt']>1],'primary_stage5_runs_used':0})
if __name__=='__main__':
 if sys.argv[1]=='freeze':freeze()
 elif sys.argv[1]=='execute':execute()
 else:raise SystemExit('freeze or execute')
