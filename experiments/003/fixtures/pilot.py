#!/usr/bin/env python3
"""Stage4 real-process pilots only; one run, no barriers, no outcome injection."""
import argparse,fcntl,csv,hashlib,json,os,platform,signal,struct,subprocess,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
RESULTS=ROOT/'experiments/003/results/stage4'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):
 with p.open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
def sources():return {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'experiments/003').rglob('*') if p.is_file() and not any(x in p.parts for x in ['target','results','__pycache__'])}
def run(profile,policy,out,buffer_bytes):
 out.mkdir(parents=True,exist_ok=False)
 count,rate,cutoff=(40,10,7_000_000_000) if profile=='low' else (2880,80,39_000_000_000)
 payload=b''.join(hashlib.sha256(struct.pack('<QQ',1,i)).digest() for i in range(512));digest=list(hashlib.sha256(payload).digest())
 work={'run_id':'e3-stage4-'+profile+'-v1','payload_seed':1,'originals':[{'message_id':i,'client_id':0,'scheduled_offset_ns':i*(1_000_000_000//rate),'deadline_offset_ns':i*(1_000_000_000//rate)+2_000_000_000,'payload_sha256':digest,'expendable':True} for i in range(count)]}
 save(out/'workload.json',work)
 server=ROOT/'experiments/003/server/target/debug/pressure-e3-stage1';client=Path('/workspace/toolchains/bin/e3-pilot')
 limits=['prlimit','--cpu=30','--fsize=67108864','--core=0','--'];epoch=time.time_ns()+2_000_000_000
 command=limits+[str(server),'--manifest',str(out/'workload.json'),'--output',str(out/'server'),'--epoch-unix-ns',str(epoch),'--addr','127.0.0.1:0','--policy',policy,'--observation-cutoff-ns',str(cutoff)]
 m={'verdict':'RUNNING','contract_revision':'A01','pilot_only':True,'primary_run':False,'worker_barrier':False,'mode':'drain','profile':profile,'policy':policy,'client_outstanding_limit':33,'client_pending_limit':32,'server_admission_limit':32,'retry_seed':1,'payload_bytes':16384,'rate':rate,'duration_s':count/rate,'observation_cutoff_ns':cutoff,'client_event_buffer_bytes':buffer_bytes,'epoch_unix_ns':epoch,'source_sha256':sources(),'binary_sha256':{str(p):sha(p) for p in [server,client]},'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'dirty_state':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),'toolchains':subprocess.check_output(['bash','-c','source scripts/dev-env.sh; rustc -Vv; cargo -V; go version'],cwd=ROOT,text=True).strip(),'environment':platform.uname()._asdict(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'cgroup':{p:Path('/sys/fs/cgroup/'+p).read_text().strip() for p in ['cpu.max','memory.max']},'safety':{'cpu_seconds_per_process':30,'rss_abort_bytes_per_process':268435456,'file_bytes':67108864,'wall_seconds':cutoff/1e9+12,'sample_interval_ns':200000000},'server_command':command,'workload_sha256':sha(out/'workload.json'),'configuration':{'server_worker_threads':2,'grpc_windows':[65535,65535],'compression':False,'automatic_configured_retry':False,'retry_replay_buffer_bytes':0,'max_message_bytes':1048576,'service_delay_ms':[10,40,10],'phase_boundaries_s':[12,24],'default_hooks_only':True}}
 save(out/'manifest.json',m)
 sp=cp=None;stop=threading.Event();sample_lock=threading.Lock();failure=[];sample_files={};writers={};deadline=time.monotonic()+cutoff/1e9+12
 def sample():
  with sample_lock:
   for role,proc in [('server',sp),('client',cp)]:
    if proc is None:continue
    try:
     text=Path('/proc/'+str(proc.pid)+'/stat').read_text();f=text[text.rfind(')')+2:].split();rss=int(f[21])*os.sysconf('SC_PAGE_SIZE');tick=1_000_000_000//os.sysconf('SC_CLK_TCK')
     writers[role].writerow(['A01',time.monotonic_ns(),proc.pid,rss,int(f[11])*tick,int(f[12])*tick,tick]);sample_files[role].flush()
     if rss>268435456:failure.append(role+' RSS safety abort')
    except (FileNotFoundError,ProcessLookupError):pass
 def sampler():
  while not stop.is_set():
   try:sample()
   except Exception as e:failure.append('sampler fault: '+repr(e));return
   stop.wait(.2)
 def guard():
  if failure:raise RuntimeError(failure[0])
  if time.monotonic()>deadline:raise RuntimeError('wall safety abort')
 def wait_file(path,proc,timeout):
  end=min(deadline,time.monotonic()+timeout)
  while not path.exists():
   guard()
   if proc.poll() is not None:raise RuntimeError('process exited before '+str(path)+': '+str(proc.returncode))
   if time.monotonic()>end:raise RuntimeError('timeout waiting '+str(path))
   time.sleep(.01)
 for role in ['server','client']:
  sample_files[role]=(out/(role+'-metrics.csv')).open('x');writers[role]=csv.writer(sample_files[role]);writers[role].writerow(['contract_revision','host_monotonic_ns','pid','rss_bytes','cpu_user_ns','cpu_system_ns','cpu_tick_ns'])
 thread=threading.Thread(target=sampler);thread.start()
 try:
  with (out/'server.log').open('x') as sl,(out/'client.log').open('x') as cl:
   sp=subprocess.Popen(command,cwd=ROOT,stdout=sl,stderr=sl,start_new_session=True);m['server_pid']=sp.pid
   wait_file(out/'server/ready.json',sp,5);ready=json.loads((out/'server/ready.json').read_text());assert ready['default_hooks_only']
   ccmd=limits+[str(client),'--manifest',str(out/'workload.json'),'--addr',ready['addr'],'--epoch-unix-ns',str(epoch),'--events',str(out/'client-events.jsonl'),'--report',str(out/'client-report.json'),'--server-ledger',str(out/'server/server-ledger.json'),'--policy',policy,'--retry-seed','1','--profile',profile,'--cutoff-ns',str(cutoff),'--event-buffer-bytes',str(buffer_bytes)]
   m['client_command']=ccmd;cp=subprocess.Popen(ccmd,cwd=ROOT,stdout=cl,stderr=cl,start_new_session=True);m['client_pid']=cp.pid
   wait_file(out/'client-report.json.transport',cp,cutoff/1e9+4)
   progress=json.loads((out/'client-report.json.transport').read_text());print('RPC ended:',out.name,progress['rpc_end_offset_ns']/1e9,progress['exchange_error'],flush=True)
   if progress['exchange_error']:raise RuntimeError('client RPC failure: '+progress['exchange_error'])
   wait_file(out/'server/finished.json',sp,3)
   wait_file(out/'server/observation-complete.json',sp,cutoff/1e9+3)
   # Wait for both clocks to reach cutoff; client does not write its final report
   # until server truth is available. Both processes remain alive for sampling.
   while time.time_ns()<epoch+cutoff:guard();time.sleep(.005)
   sample();guard();m['server_observation']=json.loads((out/'server/observation-complete.json').read_text())
   os.killpg(sp.pid,signal.SIGINT);m['server_exit']=sp.wait(timeout=5);m['client_exit']=cp.wait(timeout=5)
   if sp.returncode or cp.returncode:raise RuntimeError('nonzero pilot exit')
  m['source_hashes_unchanged']=sources()==m['source_sha256']
  if not m['source_hashes_unchanged']:raise RuntimeError('source changed during pilot')
  m['verdict']='PASS_EXECUTION'
 except BaseException as e:
  m['verdict']='FAIL';m['error']=repr(e);m['safety_abort']=bool(failure) or 'safety abort' in str(e)
 finally:
  for proc in [cp,sp]:
   if proc is not None and proc.poll() is None:
    os.killpg(proc.pid,signal.SIGINT if proc==sp else signal.SIGTERM)
    try:proc.wait(timeout=2)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
  stop.set();thread.join()
  for f in sample_files.values():f.close()
  m['process_returncodes']={'server':sp.returncode if sp else None,'client':cp.returncode if cp else None}
  m['safety_abort']=m.get('safety_abort',False) or any(code in [-signal.SIGXCPU,-signal.SIGXFSZ,-signal.SIGKILL] for code in m['process_returncodes'].values())
  save(out/'verification.json',m)
 if m['verdict']=='PASS_EXECUTION':
  result=subprocess.run(['python3',str(ROOT/'experiments/003/fixtures/verify-stage4.py'),'--run',str(out)],cwd=ROOT)
  m['independent_verifier_exit']=result.returncode;m['final_verdict']='PASS' if not result.returncode else 'FAIL_VERIFICATION'
 else:m['final_verdict']='FAIL'
 registry=RESULTS/'EXCLUSIONS.json';data=json.loads(registry.read_text()) if registry.exists() else {'primary_runs_attempted':0,'attempts':[]}
 data['attempts'].append({'directory':str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out),'profile':profile,'policy':policy,'event_buffer_bytes':buffer_bytes,'verdict':m['final_verdict'],'reason':m.get('error'),'safety_abort':m.get('safety_abort',False)});temp=registry.with_suffix('.pending');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(registry)
 save(out/'outcome.json',{'verdict':m['final_verdict'],'reason':m.get('error')})
 if m['final_verdict']!='PASS':raise SystemExit(1)

def main():
 p=argparse.ArgumentParser();p.add_argument('--profile',choices=['low','overload'],required=True);p.add_argument('--policy',choices=['wait','reject','retry','drop'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--event-buffer-bytes',type=int,choices=[0,65536],default=0);a=p.parse_args()
 def abort(signum,frame):raise KeyboardInterrupt('orchestrator signal '+str(signum))
 signal.signal(signal.SIGTERM,abort)
 with open('/tmp/grpc-under-pressure-e3-stage4.lock','a+') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise SystemExit('another Stage4 pilot owns the run lock')
  run(a.profile,a.policy,a.output.resolve(),a.event_buffer_bytes)
if __name__=='__main__':main()
