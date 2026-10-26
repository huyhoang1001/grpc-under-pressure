#!/usr/bin/env python3
"""E1B fresh-process runner. Append-only runs; original E1 data is never opened for writing."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import signal
import subprocess
import threading
import time

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'experiments/001/results/e1b'
SERVER=ROOT/'server/target/release/pressure-server'
CLIENT=Path('/workspace/toolchains/bin/pressure-loadgen-e1b')

def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')
def limited(command):return ['prlimit','--cpu=120','--fsize=67108864','--core=0','--',*command]

def run(name,variant,seconds=60,rate=300,service=10,preflight=False):
    folder=OUT/('preflight' if preflight else 'runs')/name
    folder.mkdir(parents=True,exist_ok=False)
    server_args=[str(SERVER),'--variant',variant,'--capacity','32','--service-ms',str(service),'--queue-limit','268435456','--rss-limit','536870912','--csv',str(folder/'server.csv')]
    client_args=[str(CLIENT),'--rate',str(rate),'--seconds',str(seconds),'--payload','16384','--timeout','120s','--csv',str(folder/'client.csv'),'--summary',str(folder/'client.json'),'--telemetry',str(folder/'latency.csv')]
    paths=git('ls-files','server','loadgen','proto','rust-toolchain.toml','scripts','experiments/001/e1b').splitlines()
    source_hashes={p:digest(ROOT/p) for p in paths}
    manifest={'name':name,'variant':variant,'preflight':preflight,'git_commit':git('rev-parse','HEAD'),'git_status_porcelain':git('status','--porcelain=v1','--untracked-files=all'),'tracked_diff_sha256':hashlib.sha256(subprocess.check_output(['git','diff','HEAD'],cwd=ROOT)).hexdigest(),'source_tree_clean':not git('diff','HEAD','--','server','loadgen','proto','scripts','rust-toolchain.toml','experiments/001/e1b'),'source_sha256':source_hashes,'binary_sha256':{str(p):digest(p) for p in [SERVER,CLIENT]},'build_profile':'Rust release; Go default optimized build','rate':rate,'seconds':seconds,'service_ms':service,'payload':16384,'seed':1,'capacity':32,'queue_limit':268435456,'server_rss_limit':536870912,'client_rss_limit':134217728,'rpc_deadline_s':120,'external_wall_limit_s':125,'cpu_limit_s_per_process':120,'file_limit_bytes':67108864,'core_limit_bytes':0,'windows':{'server_stream':65535,'server_connection':65535,'server_adaptive':False,'client_stream':65535,'client_connection':65535},'runtime_threads':{'tokio_workers':2,'gomaxprocs':2},'compression':False,'max_message_bytes':1048576,'warmup':'none; separate preflight and fresh idle process','missed_schedule_policy':'skip; no catch-up bursts','server_command':limited(server_args),'client_command':limited(client_args),'cwd':str(ROOT),'runtime_environment':{'RUST_LOG':'warn'},'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'started_unix_ns':time.time_ns(),'started_monotonic_ns':time.monotonic_ns(),'clock':'same-host CLOCK_MONOTONIC observation brackets; no cross-host subtraction','poll_s':.02,'process_sample_s':.2,'drain_rule':'original unchanged 120s whole-RPC deadline, then record cancellation/cleanup; no extension','events':[]}
    save(folder/'manifest.json',manifest)
    done=threading.Event();server=None;client=None;thread=None;monitor_errors=[];guard=[]
    def collect():
        handles={};readers={};headers={};previous=time.monotonic_ns();next_process=0
        try:
            with (folder/'observations.csv').open('w',newline='') as observations,(folder/'process.csv').open('w',newline='') as processes:
                ow=csv.writer(observations);pw=csv.writer(processes)
                ow.writerow(['source','observed_unix_ns','lower_monotonic_ns','upper_monotonic_ns','native_row_json'])
                pw.writerow(['unix_ns','monotonic_ns','role','pid','utime_ticks','stime_ticks','rss_bytes','threads','clock_ticks_per_second'])
                while not done.is_set():
                    poll_start=time.monotonic_ns()
                    for kind in ['server','client','latency']:
                        path=folder/(kind+'.csv')
                        if kind not in handles and path.exists():
                            handle=path.open(newline='');header=handle.readline()
                            if not header.endswith('\n'):handle.close();continue
                            handles[kind]=handle;headers[kind]=next(csv.reader([header]))
                        if kind not in handles:continue
                        handle=handles[kind]
                        while True:
                            offset=handle.tell();line=handle.readline()
                            if not line:break
                            if not line.endswith('\n'):handle.seek(offset);break
                            native=dict(zip(headers[kind],next(csv.reader([line]))))
                            ow.writerow([kind,time.time_ns(),previous,time.monotonic_ns(),json.dumps(native,separators=(',',':'))])
                    now=time.monotonic_ns()
                    if now>=next_process:
                        for role,proc in [('server',server),('client',client)]:
                            if proc is None:continue
                            try:
                                fields=Path(f'/proc/{proc.pid}/stat').read_text().split();rss=int(fields[23])*os.sysconf('SC_PAGE_SIZE')
                                pw.writerow([time.time_ns(),time.monotonic_ns(),role,proc.pid,fields[13],fields[14],rss,fields[19],os.sysconf('SC_CLK_TCK')])
                                limit=536870912 if role=='server' else 134217728
                                if rss>limit:
                                    guard.append({'role':role,'reason':'external RSS safety limit','rss_bytes':rss,'limit':limit,'monotonic_ns':now})
                                    proc.send_signal(signal.SIGINT)
                            except (FileNotFoundError,ProcessLookupError):pass
                        next_process=now+200000000
                    observations.flush();processes.flush();previous=poll_start
                    done.wait(.02)
        except Exception as exc:monitor_errors.append(repr(exc))
        finally:
            for handle in handles.values():handle.close()
    env=os.environ.copy();env['RUST_LOG']='warn'
    try:
        with (folder/'server.log').open('w') as slog,(folder/'client.log').open('w') as clog:
            thread=threading.Thread(target=collect);thread.start()
            manifest['server_launch_bracket_ns']=[time.monotonic_ns()]
            server=subprocess.Popen(limited(server_args),cwd=ROOT,stdout=slog,stderr=slog,env=env)
            manifest['server_launch_bracket_ns'].append(time.monotonic_ns())
            for _ in range(200):
                if 'ready ' in (folder/'server.log').read_text():break
                if server.poll() is not None:raise RuntimeError('server startup failed')
                time.sleep(.02)
            else:raise RuntimeError('readiness timeout')
            time.sleep(.4)
            manifest['client_launch_bracket_ns']=[time.monotonic_ns()]
            client=subprocess.Popen(limited(client_args),cwd=ROOT,stdout=clog,stderr=clog,env=env)
            manifest['client_launch_bracket_ns'].append(time.monotonic_ns())
            try:manifest['client_exit']=client.wait(timeout=125)
            except subprocess.TimeoutExpired:
                manifest['events'].append('external 125s wall timeout');client.kill();manifest['client_exit']=client.wait()
            time.sleep(.8)
            manifest['server_early_exit']=server.poll()
    except Exception as exc:manifest['runner_error']=repr(exc)
    finally:
        if client is not None and client.poll() is None:client.kill();manifest['client_exit']=client.wait()
        done.set()
        if thread is not None:thread.join(timeout=5)
        if server is not None:
            if server.poll() is None:
                server.send_signal(signal.SIGINT)
                try:server.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    server.kill();server.wait();manifest['events'].append('forced server cleanup after 4s')
            manifest['server_exit']=server.returncode
        manifest['resource_guard_events']=guard;manifest['monitor_errors']=monitor_errors
        manifest['finished_unix_ns']=time.time_ns();manifest['finished_monotonic_ns']=time.monotonic_ns()
        manifest['source_hashes_unchanged']=all((ROOT/p).is_file() and digest(ROOT/p)==h for p,h in source_hashes.items())
        result=json.loads((folder/'client.json').read_text()) if (folder/'client.json').exists() else {}
        if manifest.get('client_exit')==0 and manifest.get('server_exit')==0:outcome='completed_and_drained'
        elif 'DeadlineExceeded' in result.get('rpc_error',''):outcome='rpc_deadline_abort'
        else:outcome='failed_or_safety_aborted'
        manifest['outcome']=outcome
        save(folder/'manifest.json',manifest)
    print(name,manifest['outcome'],'client=',manifest.get('client_exit'),'server=',manifest.get('server_exit'),flush=True)
    if guard or monitor_errors or not manifest['source_hashes_unchanged'] or manifest.get('runner_error') or manifest['outcome']=='failed_or_safety_aborted':
        raise RuntimeError(f'Unexpected failure/safety stop: {folder}; data retained; inspect before continuing')
    return folder

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',required=True,choices=['preflight','measured']);args=parser.parse_args()
    if args.phase=='preflight':
        for v in ['direct','unbounded','bounded']:
            run('sender-'+v,v,3,300,1,True)
            run('control-'+v,v,4,50,10,True)
        run('worker','direct',3,1000,10,True)
    else:
        assert not git('diff','HEAD','--','server','loadgen','proto','scripts','rust-toolchain.toml','experiments/001/e1b'), 'commit source/harness before measurement'
        order=[];rng=random.Random(1)
        for rep in range(1,6):
            variants=['direct','unbounded','bounded'];rng.shuffle(variants)
            order.extend((rep,v) for v in variants)
        order_path=OUT/'run-order.json'
        with order_path.open('x') as f:json.dump(order,f,indent=2);f.write('\n')
        for rep,v in order:run(f'overload-{rep}-{v}',v)
if __name__=='__main__':main()
