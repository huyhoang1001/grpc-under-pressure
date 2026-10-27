#!/usr/bin/env python3
"""Stage 1 acceptance fixtures only; never executes the 36s primary workload."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
SERVER=ROOT/'server/target/debug/pressure-stage1'
CLIENT=Path('/workspace/toolchains/bin/pressure-stage1-client')

def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def run(root,name,rate=80,seconds=.8,deadline='120s',fault=None):
    folder=root/name;folder.mkdir(exist_ok=False)
    server_dir=folder/'server';client_dir=folder/'client';marker=folder/'marker.txt'
    server=[str(SERVER),'--addr','127.0.0.1:50053','--output',str(server_dir),'--marker',str(marker)]
    if fault in ['worker_error','worker_panic']:server+=['--test-fail-after' if fault=='worker_error' else '--test-panic-after','1']
    client=[str(CLIENT),'--output',str(client_dir),'--marker',str(marker),'--rate',str(rate),'--seconds',str(seconds),'--timeout',deadline]
    limits=['prlimit','--cpu=10','--fsize=16777216','--core=0','--']
    paths=git('ls-files','server','loadgen','proto','rust-toolchain.toml','experiments/002').splitlines()
    paths=[p for p in paths if '/results/' not in p]
    manifest={'schema':'e2-stage1-run-v1','purpose':'instrumentation acceptance smoke; not primary benchmark','name':name,'expected_fault':fault,'git_commit':git('rev-parse','HEAD'),'git_status_porcelain':git('status','--porcelain=v1','--untracked-files=all'),'source_sha256':{p:sha(ROOT/p) for p in paths},'binary_sha256':{str(p):sha(p) for p in [SERVER,CLIENT]},'server_command':limits+server,'client_command':limits+client,'cwd':str(ROOT),'rate':rate,'offered_seconds':seconds,'payload_bytes':16384,'seed':1,'physical_K':32,'static_pending_limit':32,'dynamic_budget':False,'service_ms':10,'service_schedule':'constant; no slowdown schedule','windows':{'stream':65535,'connection':65535,'server_adaptive':False},'runtime':{'tokio_workers':2,'gomaxprocs':2,'compression':False,'retries':False,'max_message_bytes':1048576},'sample_ms':200,'limits':{'server_rss':536870912,'client_rss':134217728,'cpu_seconds':10,'file_bytes':16777216,'wall_seconds':12,'rpc_deadline':deadline},'build_mode':'debug Rust; default optimized Go','kernel':platform.release(),'started_unix_ns':time.time_ns(),'events':[]}
    save(folder/'manifest.json',manifest)
    done=threading.Event();server_process=None;client_process=None;thread=None
    def sample():
        with (folder/'process.csv').open('w',newline='') as f:
            out=csv.writer(f);out.writerow(['unix_ns','monotonic_ns','role','pid','utime_ticks','stime_ticks','rss_bytes','threads','CLK_TCK'])
            while not done.is_set():
                for role,proc in [('server',server_process),('client',client_process)]:
                    if proc is None:continue
                    try:
                        fields=Path(f'/proc/{proc.pid}/stat').read_text().split();rss=int(fields[23])*os.sysconf('SC_PAGE_SIZE')
                        out.writerow([time.time_ns(),time.monotonic_ns(),role,proc.pid,fields[13],fields[14],rss,fields[19],os.sysconf('SC_CLK_TCK')])
                        if rss>manifest['limits'][role+'_rss']:
                            manifest['events'].append(role+' RSS safety abort');proc.send_signal(signal.SIGINT)
                    except (FileNotFoundError,ProcessLookupError):pass
                f.flush();done.wait(.2)
    try:
        with (folder/'server.log').open('w') as sl,(folder/'client.log').open('w') as cl:
            server_process=subprocess.Popen(limits+server,cwd=ROOT,stdout=sl,stderr=sl)
            for _ in range(200):
                if 'stage1 ready' in (folder/'server.log').read_text():break
                if server_process.poll() is not None:raise RuntimeError('server failed readiness')
                time.sleep(.01)
            else:raise RuntimeError('server readiness timeout')
            client_process=subprocess.Popen(limits+client,cwd=ROOT,stdout=cl,stderr=cl)
            for _ in range(200):
                if (client_dir/'ready').exists():break
                if client_process.poll() is not None:raise RuntimeError('client failed barrier')
                time.sleep(.01)
            else:raise RuntimeError('client barrier timeout')
            target=time.time_ns()+300_000_000
            marker.write_text(str(target)+'\n');manifest['marker_target_unix_ns']=target;manifest['marker_written_unix_ns']=time.time_ns()
            thread=threading.Thread(target=sample);thread.start()
            manifest['client_exit']=client_process.wait(timeout=12)
            time.sleep(.5) # final 200ms samples after EOF/error cleanup
    except Exception as e:manifest['runner_error']=repr(e)
    finally:
        if client_process is not None and client_process.poll() is None:client_process.kill();manifest['client_exit']=client_process.wait()
        done.set()
        if thread:thread.join()
        if server_process is not None:
            if server_process.poll() is None:
                server_process.send_signal(signal.SIGINT)
                try:server_process.wait(timeout=3)
                except subprocess.TimeoutExpired:server_process.kill();server_process.wait();manifest['events'].append('forced server shutdown')
            manifest['server_exit']=server_process.returncode
        manifest['finished_unix_ns']=time.time_ns()
        manifest['source_hashes_unchanged']=all(sha(ROOT/p)==v for p,v in manifest['source_sha256'].items())
        try:
            sc=json.loads((server_dir/'clock.json').read_text());cc=json.loads((client_dir/'clock.json').read_text())
            manifest['clock']={'server':sc,'client':cc,'phase_alignment_error_ns':abs(sc['actual_start_unix_ns']-cc['actual_start_unix_ns'])}
        except FileNotFoundError:manifest['clock_error']='missing clock marker record'
        save(folder/'manifest.json',manifest)
    from verify import verify
    errors=verify(folder)
    manifest['acceptance_errors']=errors;manifest['valid_smoke']=not errors;save(folder/'manifest.json',manifest)
    with (root/'ledger.jsonl').open('a') as f:f.write(json.dumps({'run':name,'fault':fault,'valid_smoke':not errors,'errors':errors})+'\n')
    print(name,'PASS' if not errors else errors,flush=True)
    if errors:raise RuntimeError('Smoke failed; data preserved, stop and diagnose')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);a=parser.parse_args();root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    for i in range(1,4):run(root,f'normal-{i}')
    run(root,'cancel-capacity',rate=1000,seconds=2,deadline='1200ms',fault='cancellation')
    run(root,'worker-error',fault='worker_error')
    run(root,'worker-panic',fault='worker_panic')
if __name__=='__main__':main()
