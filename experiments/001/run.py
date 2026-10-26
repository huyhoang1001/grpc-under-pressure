#!/usr/bin/env python3
"""Sequential, fresh-process E1 runs; retain every run, including failures."""
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

ROOT=Path(__file__).resolve().parents[2]
SERVER=ROOT/'server/target/debug/pressure-server'
CLIENT=Path('/workspace/toolchains/bin/pressure-loadgen')

def run(out, name, variant, rate, seconds, service=10, diagnostic=False):
    folder=out/name
    folder.mkdir(parents=True,exist_ok=False)
    server_cmd=[str(SERVER),'--variant',variant,'--capacity','32','--service-ms',str(service),'--queue-limit','268435456','--rss-limit','536870912','--csv',str(folder/'server.csv')]
    client_cmd=[str(CLIENT),'--rate',str(rate),'--seconds',str(seconds),'--timeout','120s','--csv',str(folder/'client.csv'),'--summary',str(folder/'client.json')]
    manifest={'name':name,'variant':variant,'rate':rate,'seconds':seconds,'service_ms':service,'payload':16384,'seed':1,'capacity':32,'queue_limit':268435456,'server_rss_limit':536870912,'rpc_deadline_s':120,'drain_rule':'CloseAndRecv waits within whole RPC deadline','warmup':'none; start fresh idle process, sample before traffic','windows':{'server_stream':65535,'server_connection':65535,'server_adaptive':False,'client_stream':65535,'client_connection':65535},'max_message_bytes':1048576,'compression':False,'runtime_threads':{'tokio_workers':2,'gomaxprocs':2},'server_command':server_cmd,'client_command':client_cmd,'kernel':platform.release(),'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'server/src/main.rs',ROOT/'loadgen/cmd/loadgen/main.go',ROOT/'server/Cargo.lock',ROOT/'loadgen/go.sum']},'binary_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SERVER,CLIENT]}}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    env=os.environ.copy();env['RUST_LOG']='h2=trace' if diagnostic else 'warn'
    done=threading.Event()
    server=None; client=None
    def monitor():
        with (folder/'process.csv').open('w') as f:
            writer=csv.writer(f);writer.writerow(['elapsed_s','role','pid','utime_ticks','stime_ticks','rss_bytes','threads','clock_ticks_per_second'])
            start=time.monotonic()
            while not done.is_set():
                for role,proc in [('server',server),('client',client)]:
                    if proc is None: continue
                    try:
                        values=Path(f'/proc/{proc.pid}/stat').read_text().split()
                        writer.writerow([time.monotonic()-start,role,proc.pid,values[13],values[14],int(values[23])*os.sysconf('SC_PAGE_SIZE'),values[19],os.sysconf('SC_CLK_TCK')])
                    except FileNotFoundError: pass
                f.flush();done.wait(.2)
    worker=None
    try:
        with (folder/'server.log').open('w') as slog, (folder/'client.log').open('w') as clog:
            server=subprocess.Popen(server_cmd,stdout=slog,stderr=slog,env=env)
            for _ in range(200):
                if 'ready ' in (folder/'server.log').read_text():break
                if server.poll() is not None:raise RuntimeError('server exited before readiness')
                time.sleep(.02)
            else:raise RuntimeError('server startup timeout')
            worker=threading.Thread(target=monitor);worker.start()
            time.sleep(.4) # idle pre-traffic samples; no extra readiness TCP connection
            client=subprocess.Popen(client_cmd,stdout=clog,stderr=clog)
            code=client.wait(timeout=125)
            time.sleep(.6) # record drain completion and post-drain RSS
            manifest['client_exit']=code
            if server.poll() is not None:manifest['server_early_exit']=server.returncode
    except Exception as exc:
        manifest['runner_error']=repr(exc)
        raise
    finally:
        if client is not None and client.poll() is None:client.kill();client.wait()
        done.set()
        if worker is not None:worker.join()
        if server is not None:
            if server.poll() is None:
                server.send_signal(signal.SIGINT)
                try:server.wait(timeout=4)
                except subprocess.TimeoutExpired:server.kill();server.wait();manifest['server_forced_kill']=True
            manifest['server_exit']=server.returncode
        (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(name, 'client_exit=',manifest.get('client_exit'),'server_exit=',manifest.get('server_exit'),flush=True)
    if manifest.get('client_exit')!=0 or manifest.get('server_exit')!=0:raise RuntimeError(f'failed run retained: {folder}')
    return folder

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);parser.add_argument('--phase',choices=['calibration','measured','diagnostic'],required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if args.phase=='calibration':
        for v in ['direct','unbounded','bounded']:
            run(out,'sender-calibration-'+v,v,300,3,1)
            run(out,'control-'+v,v,50,4)
        run(out,'worker-calibration','direct',1000,3)
    elif args.phase=='measured':
        order=[];rng=random.Random(1)
        for repetition in range(1,6):
            variants=['direct','unbounded','bounded'];rng.shuffle(variants)
            for v in variants:order.append((repetition,v))
        (out/'run-order.json').write_text(json.dumps(order,indent=2)+'\n')
        for repetition,v in order:run(out,f'overload-{repetition}-{v}',v,300,12)
    else:
        for v in ['unbounded','bounded']:run(out,'diagnostic-'+v,v,300,4,diagnostic=True)
if __name__=='__main__':main()
