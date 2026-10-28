#!/usr/bin/env python3
"""Stage 3 static policies: targeted fixtures, baseline overhead controls, at most one fixed8 exploration."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'experiments/002'
sys.path.insert(0,str(BASE))
from stage2.run import validate as stage2_validate
from verify import read
SERVER=ROOT/'server/target/debug/pressure-stage1'
CLIENT=Path('/workspace/toolchains/bin/pressure-stage1-client')

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def expected_delay(t):return 40 if 12_000_000_000<=t<24_000_000_000 else 10

def validate(folder):
    m=json.loads((folder/'manifest.json').read_text())
    issues=stage2_validate(folder)
    budget=m['static_pending_limit']
    samples=read(folder/'server/server.csv')
    for row in samples:
        q,r,w=[int(row[k]) for k in ['Q','R','W']]
        if int(row['B'])!=budget or q+r>budget:issues.append('static logical budget violation')
        if not m['accepted_stage2_binary']:
            if int(row['physical_capacity'])!=32:issues.append('physical K changed')
            if int(row['physical_available_capacity'])+q+r!=32:issues.append('physical reservation accounting')
            if int(row['logical_pending'])!=q+r:issues.append('pending gauge disagrees')
    if m['expected_fault']=='cancellation' and m['policy']=='fixed8':
        if not any(int(r['Q'])==8 and int(r['W'])==1 and int(r['physical_available_capacity'])==24 for r in samples):issues.append('logical cancellation fixture did not reach budget with unused physical slots')
    if m.get('source_hashes_unchanged') is not True:issues.append('harness/source changed during run')
    return sorted(set(issues))

def run(root,name,seconds,policy='fixed32',schedule='constant',purpose='integration_fixture',fault=None,rate=80,deadline='120s',baseline=False,implicit=False):
    folder=root/name;folder.mkdir(parents=True,exist_ok=False)
    sd=folder/'server';cd=folder/'client';marker=folder/'marker.txt'
    executable=Path('/workspace/toolchains/bin/pressure-stage2-accepted') if baseline else SERVER
    server=[str(executable),'--output',str(sd),'--marker',str(marker),'--service-schedule',schedule,'--event-io','buffered']
    if not baseline and not implicit:server+=['--policy',policy]
    if fault in ['worker_error','worker_panic']:server+=['--test-fail-after' if fault=='worker_error' else '--test-panic-after','1']
    client=[str(CLIENT),'--output',str(cd),'--marker',str(marker),'--rate',str(rate),'--seconds',str(seconds),'--timeout',deadline]
    limits=['prlimit','--cpu=10','--fsize=16777216','--core=0','--']
    inputs=git('ls-files','server','loadgen','proto','rust-toolchain.toml','experiments/002').splitlines()
    inputs=[p for p in inputs if '/results/' not in p]
    accepted=json.loads((BASE/'results/stage2/environment.json').read_text())
    if baseline:
        assert sha(executable)==accepted['binary_sha256']['/workspace/grpc-under-pressure/server/target/debug/pressure-stage1'], 'accepted baseline binary hash mismatch'
    assert sha(CLIENT)==accepted['binary_sha256'][str(CLIENT)], 'client must match the accepted shared Stage2 client'
    server_commit='84509545abf6a5f139687250757e67703477a5c1' if baseline else git('rev-parse','HEAD')
    server_paths=git('ls-files','server','proto','rust-toolchain.toml','experiments/002/server').splitlines()
    server_hashes={p:hashlib.sha256(subprocess.check_output(['git','show',server_commit+':'+p],cwd=ROOT)).hexdigest() for p in server_paths}
    m={'schema':'e2-stage3-run-v1','name':name,'purpose':purpose,'primary_run':False,'expected_fault':fault,'git_commit':git('rev-parse','HEAD'),'git_status_porcelain':git('status','--porcelain=v1','--untracked-files=all'),'source_sha256':{p:sha(ROOT/p) for p in inputs},'binary_sha256':{str(p):sha(p) for p in [executable,CLIENT]},'server_command':limits+server,'client_command':limits+client,'cwd':str(ROOT),'event_io':'buffered','policy':policy,'accepted_stage2_binary':baseline,'policy_flag_omitted':implicit or baseline,'server_source_commit':server_commit,'server_source_sha256':server_hashes,'client_source_commit':'84509545abf6a5f139687250757e67703477a5c1','full_event_evidence':True,'service_schedule':schedule,'sample_ms':200,'rate':rate,'offered_seconds':seconds,'payload_bytes':16384,'seed':1,'physical_K':32,'static_pending_limit':8 if policy=='fixed8' else 32,'dynamic_budget':False,'windows':{'stream':65535,'connection':65535,'server_adaptive':False},'runtime':{'tokio_workers':2,'gomaxprocs':2,'compression':False,'retries':False,'max_message_bytes':1048576},'build_mode':'debug Rust; default optimized Go','cpu_affinity':sorted(os.sched_getaffinity(0)),'kernel':platform.release(),'limits':{'server_rss':536870912,'client_rss':134217728,'cpu_seconds':10,'file_bytes':16777216,'wall_seconds':125,'rpc_deadline':deadline},'started_unix_ns':time.time_ns(),'started_monotonic_ns':time.monotonic_ns(),'events':[]}
    save(folder/'manifest.json',m)
    done=threading.Event();sp=None;cp=None;thread=None
    def collect():
        try:
            with (folder/'process.csv').open('w',newline='') as f:
                out=csv.writer(f);out.writerow(['unix_ns','monotonic_ns','role','pid','utime_ticks','stime_ticks','rss_bytes','threads','CLK_TCK'])
                while not done.is_set():
                    for role,proc in [('server',sp),('client',cp)]:
                        if proc is None:continue
                        try:
                            r=Path(f'/proc/{proc.pid}/stat').read_text().split();rss=int(r[23])*os.sysconf('SC_PAGE_SIZE')
                            out.writerow([time.time_ns(),time.monotonic_ns(),role,proc.pid,r[13],r[14],rss,r[19],os.sysconf('SC_CLK_TCK')])
                            if rss>m['limits'][role+'_rss']:m['events'].append(role+' RSS safety abort');proc.send_signal(signal.SIGINT)
                        except (FileNotFoundError,ProcessLookupError):pass
                    f.flush();done.wait(.2)
        except Exception as e:m['events'].append('collector failure '+repr(e))
    try:
        with (folder/'server.log').open('w') as sl,(folder/'client.log').open('w') as cl:
            sp=subprocess.Popen(limits+server,cwd=ROOT,stdout=sl,stderr=sl)
            for _ in range(200):
                if 'stage1 ready' in (folder/'server.log').read_text():break
                if sp.poll() is not None:raise RuntimeError('server readiness failure')
                time.sleep(.01)
            else:raise RuntimeError('readiness timeout')
            cp=subprocess.Popen(limits+client,cwd=ROOT,stdout=cl,stderr=cl)
            for _ in range(200):
                if (cd/'ready').exists():break
                if cp.poll() is not None:raise RuntimeError('client readiness failure')
                time.sleep(.01)
            else:raise RuntimeError('client barrier timeout')
            target=time.time_ns()+300_000_000;marker.write_text(str(target)+'\n');m['marker_target_unix_ns']=target;m['marker_written_unix_ns']=time.time_ns()
            thread=threading.Thread(target=collect);thread.start()
            m['client_exit']=cp.wait(timeout=125);time.sleep(.5)
    except Exception as e:m['runner_error']=repr(e)
    finally:
        if cp is not None and cp.poll() is None:cp.kill();m['client_exit']=cp.wait()
        done.set()
        if thread:thread.join()
        if sp is not None:
            if sp.poll() is None:
                sp.send_signal(signal.SIGINT)
                try:sp.wait(timeout=3)
                except subprocess.TimeoutExpired:sp.kill();sp.wait();m['events'].append('forced server shutdown')
            m['server_exit']=sp.returncode
        m['finished_unix_ns']=time.time_ns();m['finished_monotonic_ns']=time.monotonic_ns()
        m['source_hashes_unchanged']=all(sha(ROOT/p)==digest for p,digest in m['source_sha256'].items())
        try:
            sc=json.loads((sd/'clock.json').read_text());cc=json.loads((cd/'clock.json').read_text())
            m['clock']={'server':sc,'client':cc,'phase_alignment_error_ns':abs(sc['actual_start_unix_ns']-cc['actual_start_unix_ns'])}
        except FileNotFoundError:m['runner_error']='clock evidence missing'
        save(folder/'manifest.json',m)
    try:issues=validate(folder)
    except Exception as e:issues=['validation failed '+repr(e)]
    m['validation_issues']=issues;m['valid_for_declared_purpose']=not issues;save(folder/'manifest.json',m)
    with (root/'ledger.jsonl').open('a') as f:f.write(json.dumps({'name':name,'purpose':purpose,'policy':policy,'baseline':baseline,'expected_fault':fault,'issues':issues,'valid':not issues})+'\n')
    print(name,'PASS' if not issues else issues,flush=True)
    if issues:raise RuntimeError('Stop and diagnose; all attempted data retained')

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--phase',required=True,choices=['acceptance','overhead','exploratory']);a=p.parse_args();root=a.output.resolve();root.mkdir(parents=True,exist_ok=True)
    if git('diff','HEAD','--','server','loadgen','proto','rust-toolchain.toml','experiments/002/server','experiments/002/client','experiments/002/stage3'):raise RuntimeError('commit source/harness before evidence collection')
    if a.phase=='acceptance':
        run(root,'fixed32-default',.8,implicit=True)
        run(root,'fixed32-explicit',.8)
        run(root,'fixed8-normal',.8,policy='fixed8')
        run(root,'fixed8-cancel',2,policy='fixed8',rate=1000,deadline='1200ms',fault='cancellation')
        run(root,'fixed8-worker-error',.8,policy='fixed8',fault='worker_error')
        run(root,'fixed8-worker-panic',.8,policy='fixed8',fault='worker_panic')
        run(root,'fixed32-schedule-smoke',.8,schedule='contract')
        run(root,'fixed8-schedule-smoke',.8,policy='fixed8',schedule='contract')
    elif a.phase=='overhead':
        for name,baseline in [('accepted32-1',True),('shared32-1',False),('shared32-2',False),('accepted32-2',True)]:
            run(root,name,4,purpose='stage2_baseline_overhead_control',baseline=baseline)
    else:
        required=['fixed32-default','fixed32-explicit','fixed8-normal','fixed8-cancel','fixed8-worker-error','fixed8-worker-panic','fixed32-schedule-smoke','fixed8-schedule-smoke','accepted32-1','shared32-1','shared32-2','accepted32-2']
        for name in required:
            m=json.loads((root/name/'manifest.json').read_text())
            if not m.get('valid_for_declared_purpose'):raise RuntimeError('acceptance/control gate not passed: '+name)
        if not (root/'analysis.json').exists():raise RuntimeError('assess control overhead before exploration')
        if any(root.glob('exploratory-*/manifest.json')):raise RuntimeError('An exploratory attempt already exists; do not silently replace it')
        run(root,'exploratory-fixed8',36,policy='fixed8',schedule='contract',purpose='single_exploratory_fixed8')
if __name__=='__main__':main()
