#!/usr/bin/env python3
"""Exclusive, guarded Stage6 real gRPC run; a separate secondary-only executable."""
import csv,hashlib,importlib.util,json,os,platform,signal,subprocess,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'experiments/003/results/stage6';FREEZE=OUT/'FROZEN-MANIFEST.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,o):
 with Path(p).open('x') as f:json.dump(o,f,indent=2);f.write('\n')
def source_guard():
 f=json.loads(FREEZE.read_text());assert all(sha(ROOT/p)==h for p,h in f['source_sha256'].items()),'source drift'
 assert all(sha(p)==h for p,h in f['binary_sha256'].items()),'binary drift'
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==f['source_commit'],'revision drift'
 assert {p:Path('/sys/fs/cgroup/'+p).read_text().strip() for p in ['cpu.max','memory.max']}==f['cgroup'],'cgroup drift'
 if 'runtime_environment' in f:assert {p:os.environ.get(p) for p in f['runtime_environment']}==f['runtime_environment'],'runtime environment drift'
 return f
def run(case,out,smoke=False):
 out.mkdir(parents=True,exist_ok=False);frozen=source_guard();clients=case['clients'];cutoff=8_000_000_000 if smoke else (42_000_000_000 if case['deadline_ns']==5_000_000_000 else 39_000_000_000)
 workload=json.loads((OUT/f'workloads/{case["study"]}.json').read_text())
 if smoke:workload['originals']=workload['originals'][:80]
 save(out/'workload.json',workload)
 epoch=time.time_ns()+3_000_000_000;limits=['prlimit','--cpu=30','--fsize=67108864','--core=0','--']
 command=limits+[frozen['server_binary'],'--manifest',str(out/'workload.json'),'--output',str(out/'server'),'--epoch-unix-ns',str(epoch),'--addr','127.0.0.1:0','--policy',case['policy'],'--clients',str(clients),'--observation-cutoff-ns',str(cutoff)]
 m={**case,'secondary_only':True,'primary_run':False,'contract_revision':'A01','profile':'secondary-smoke' if smoke else 'secondary','mode':'drain','client_outstanding_limit':33,'client_pending_limit':32,'server_admission_limit':32,'cutoff_ns':cutoff,'epoch_unix_ns':epoch,'source_sha256':frozen['source_sha256'],'binary_sha256':frozen['binary_sha256'],'source_commit':frozen['source_commit'],'dirty_state':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),'toolchains':frozen['toolchains'],'environment':platform.uname()._asdict(),'cgroup':frozen['cgroup'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'frozen_manifest_sha256':sha(FREEZE),'workload_sha256':sha(out/'workload.json'),'server_command':command,'client_command':[],'safety':{'cpu_seconds_per_process':30,'rss_bytes_per_process':268435456,'aggregate_rss_max_bytes':(clients+1)*268435456,'file_bytes':67108864,'wall_seconds':cutoff/1e9+12,'sample_interval_ns':200_000_000,'sample_max_gap_ns':500_000_000},'configuration':{'http2_stream_window':65535,'http2_connection_window':65535,'server_tokio_threads':2,'client_event_buffer_bytes':0,'server_event_buffer_bytes':65536,'response_progress_timeout_ns':1_000_000_000,'max_attempts_per_original':3,'worker_count':1,'service_ms':[10,40,10],'boundaries_s':[12,24],'compression':False,'grpc_configured_retry':False,'retry_replay_bytes':0,'server_global_staging':1,'server_global_terminal_slots':32,'server_global_immediate_slots':32,'server_bridge_capacity_per_stream':1,'client_response_events_per_process':64,'event_capacity_per_process':1024}}
 save(out/'manifest.json',m);procs={};files={};writers={};logs=[];errors=[];lock=threading.Lock();stop=threading.Event();deadline=time.monotonic()+cutoff/1e9+12
 for role in ['server']+[f'client-{i}' for i in range(clients)]:
  files[role]=(out/f'{role}-metrics.csv').open('x');writers[role]=csv.writer(files[role]);writers[role].writerow(['contract_revision','host_monotonic_ns','pid','rss_bytes','cpu_user_ns','cpu_system_ns','cpu_tick_ns'])
 def sample():
  with lock:
   for role,proc in list(procs.items()):
    try:
     text=Path(f'/proc/{proc.pid}/stat').read_text();v=text[text.rfind(')')+2:].split();tick=1_000_000_000//os.sysconf('SC_CLK_TCK');rss=int(v[21])*os.sysconf('SC_PAGE_SIZE');writers[role].writerow(['A01',time.monotonic_ns(),proc.pid,rss,int(v[11])*tick,int(v[12])*tick,tick]);files[role].flush()
     if rss>268435456:errors.append(role+' RSS safety abort')
    except (FileNotFoundError,ProcessLookupError):pass
 def sampler():
  while not stop.is_set():
   try:sample()
   except Exception as e:errors.append('sampler fault '+repr(e));return
   stop.wait(.2)
 def guard():
  if errors:raise RuntimeError(errors[0])
  if time.monotonic()>deadline:raise RuntimeError('wall safety abort')
 def waitfile(path,role,seconds):
  end=min(deadline,time.monotonic()+seconds)
  while not path.exists():
   guard()
   if procs[role].poll() is not None:raise RuntimeError(role+' exited before '+str(path)+': '+str(procs[role].returncode))
   if time.monotonic()>end:raise RuntimeError('timeout waiting '+str(path))
   time.sleep(.01)
 thread=threading.Thread(target=sampler);thread.start();m['verdict']='RUNNING';m['safety_abort']=False
 try:
  sl=(out/'server.log').open('x');logs.append(sl);procs['server']=subprocess.Popen(command,cwd=ROOT,stdout=sl,stderr=sl,start_new_session=True)
  waitfile(out/'server/ready.json','server',5);ready=json.loads((out/'server/ready.json').read_text());assert ready['default_hooks_only'] and ready['secondary_only'] and ready['client_count']==clients
  for cid in range(clients):
   directory=out/f'client-{cid}';directory.mkdir();cl=(directory/'process.log').open('x');logs.append(cl)
   cmd=limits+[frozen['client_binary'],'--manifest',str(out/'workload.json'),'--addr',ready['addr'],'--epoch-unix-ns',str(epoch),'--events',str(directory/'events.jsonl'),'--report',str(directory/'report.json'),'--server-ledger',str(out/'server/server-ledger.json'),'--policy',case['policy'],'--retry-seed',str(case['client_seeds'][cid]),'--profile',m['profile'],'--cutoff-ns',str(cutoff),'--event-buffer-bytes','0','--deadline-ns',str(case['deadline_ns']),'--clients',str(clients),'--client-id',str(cid),'--retry-mode',case['retry_mode']]
   m['client_command'].append(cmd);procs[f'client-{cid}']=subprocess.Popen(cmd,cwd=ROOT,stdout=cl,stderr=cl,start_new_session=True)
  for cid in range(clients):
   p=out/f'client-{cid}/report.json.transport';waitfile(p,f'client-{cid}',cutoff/1e9+3);progress=json.loads(p.read_text())
   if progress['exchange_error']:raise RuntimeError(f'client-{cid} RPC failure: '+progress['exchange_error'])
  waitfile(out/'server/finished.json','server',3);waitfile(out/'server/observation-complete.json','server',cutoff/1e9+3)
  while time.time_ns()<epoch+cutoff:guard();time.sleep(.005)
  sample();guard();os.killpg(procs['server'].pid,signal.SIGINT);procs['server'].wait(timeout=5)
  for cid in range(clients):procs[f'client-{cid}'].wait(timeout=5)
  if any(p.returncode for p in procs.values()):raise RuntimeError('nonzero process exit')
  source_guard();m['source_unchanged']=True;m['verdict']='PASS_EXECUTION'
 except BaseException as e:m['verdict']='FAIL';m['error']=repr(e);m['safety_abort']=bool(errors) or 'safety abort' in str(e)
 finally:
  for role,proc in reversed(list(procs.items())):
   if proc.poll() is None:
    os.killpg(proc.pid,signal.SIGINT if role=='server' else signal.SIGTERM)
    try:proc.wait(timeout=2)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
  stop.set();thread.join()
  for file in files.values():file.close()
  for file in logs:file.close()
  m['process_returncodes']={role:p.returncode for role,p in procs.items()};m['safety_abort']=m['safety_abort'] or any(v in [-signal.SIGXCPU,-signal.SIGXFSZ,-signal.SIGKILL] for v in m['process_returncodes'].values());m['sampler_errors']=errors;save(out/'verification.json',m)
 if m['verdict']=='PASS_EXECUTION':
  result=subprocess.run(['python3',str(Path(__file__).with_name('verify.py')),'--run',str(out)],cwd=ROOT,capture_output=True,text=True);save(out/'verifier-execution.json',{'command':result.args,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr});passed=result.returncode==0
 else:passed=False
 verdict={'verdict':'PASS' if passed else 'FAIL','reason':m.get('error') if m['verdict']!='PASS_EXECUTION' else None,'safety_abort':m['safety_abort']}
 if not passed and (out/'independent-verification.json').exists():verdict['reason']=json.loads((out/'independent-verification.json').read_text()).get('error','verifier failure')
 save(out/'outcome.json',verdict);print(out.name,verdict['verdict'],verdict['reason'],flush=True);return verdict
