#!/usr/bin/env python3
"""Stage5 sequential primary matrix; all attempts preserved, stop on invalidity."""
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
    from stage5.verify import validate as check
    return check(folder)

def run(root,name,seconds,policy='fixed32',schedule='constant',purpose='primary_controlled_comparison',fault=None,rate=80,deadline='120s'):
    folder=root/name;folder.mkdir(parents=True,exist_ok=False)
    sd=folder/'server';cd=folder/'client';marker=folder/'marker.txt'
    executable=SERVER
    server=[str(executable),'--output',str(sd),'--marker',str(marker),'--service-schedule',schedule,'--event-io','buffered']
    server+=['--policy',policy]
    if fault in ['worker_error','worker_panic']:server+=['--test-fail-after' if fault=='worker_error' else '--test-panic-after','1']
    client=[str(CLIENT),'--output',str(cd),'--marker',str(marker),'--rate',str(rate),'--seconds',str(seconds),'--timeout',deadline]
    limits=['prlimit','--cpu=10','--fsize=16777216','--core=0','--']
    inputs=git('ls-files','server','loadgen','proto','rust-toolchain.toml','experiments/002').splitlines()
    inputs=[p for p in inputs if '/results/' not in p]
    accepted=json.loads((BASE/'results/stage2/environment.json').read_text())
    assert sha(CLIENT)==accepted['binary_sha256'][str(CLIENT)], 'client must match the accepted shared Stage2 client'
    server_commit=FROZEN['application_source_commit']
    server_paths=git('ls-files','server','proto','rust-toolchain.toml','experiments/002/server').splitlines()
    server_hashes={p:hashlib.sha256(subprocess.check_output(['git','show',server_commit+':'+p],cwd=ROOT)).hexdigest() for p in server_paths}
    m={'schema':'e2-stage5-primary-run-v1','name':name,'purpose':purpose,'primary_run':True,'expected_fault':fault,'git_commit':git('rev-parse','HEAD'),'git_status_porcelain':git('status','--porcelain=v1','--untracked-files=all'),'source_sha256':{p:sha(ROOT/p) for p in inputs},'binary_sha256':{str(p):sha(p) for p in [executable,CLIENT]},'server_command':limits+server,'client_command':limits+client,'cwd':str(ROOT),'event_io':'buffered','policy':policy,'server_source_commit':server_commit,'server_source_sha256':server_hashes,'client_source_commit':'84509545abf6a5f139687250757e67703477a5c1','full_event_evidence':True,'service_schedule':schedule,'sample_ms':200,'rate':rate,'offered_seconds':seconds,'payload_bytes':16384,'seed':1,'physical_K':32,'initial_budget':{'fixed32':32,'fixed8':8,'adaptive':16}[policy],'dynamic_budget':policy=='adaptive','controller':{'period_ms':500,'alpha':0.2,'minimum_completions':5,'high_ms':125,'low_ms':75,'streak_ticks':2,'range':[1,32],'feedback_window':'deltas between actual tick snapshots, first from workload marker','fixed_policies_observe_only':True},'windows':{'stream':65535,'connection':65535,'server_adaptive':False},'runtime':{'tokio_workers':2,'gomaxprocs':2,'compression':False,'retries':False,'max_message_bytes':1048576},'build_mode':'debug Rust; default optimized Go','cpu_affinity':sorted(os.sched_getaffinity(0)),'kernel':platform.release(),'limits':{'server_rss':536870912,'client_rss':134217728,'cpu_seconds':10,'file_bytes':16777216,'wall_seconds':125,'rpc_deadline':deadline},'started_unix_ns':time.time_ns(),'started_monotonic_ns':time.monotonic_ns(),'events':[]}
    m.update(freeze_sha256=FREEZE_SHA,block=ROW['block'],position=ROW['position'],frozen_checks_before=freeze_check(FROZEN),frozen_application_commit=FROZEN['application_source_commit'])
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
        m['frozen_checks_after']=freeze_check(FROZEN)
        m['source_hashes_unchanged']=all(sha(ROOT/p)==digest for p,digest in m['source_sha256'].items())
        try:
            sc=json.loads((sd/'clock.json').read_text());cc=json.loads((cd/'clock.json').read_text())
            m['clock']={'server':sc,'client':cc,'phase_alignment_error_ns':abs(sc['actual_start_unix_ns']-cc['actual_start_unix_ns'])}
        except FileNotFoundError:m['runner_error']='clock evidence missing'
        save(folder/'manifest.json',m)
    try:issues=validate(folder)
    except Exception as e:issues=['validation failed '+repr(e)]
    m['validation_issues']=issues;m['valid_for_declared_purpose']=not issues;save(folder/'manifest.json',m)
    with (root/'ledger.jsonl').open('a') as f:f.write(json.dumps({'name':name,'block':ROW['block'],'position':ROW['position'],'purpose':purpose,'policy':policy,'expected_fault':fault,'issues':issues,'valid':not issues})+'\n')
    print(name,'PASS' if not issues else issues,flush=True)
    if issues:raise RuntimeError('Stop and diagnose; all attempted data retained')

from stage5.freeze import check as freeze_check
FROZEN=None
FREEZE_SHA=None
ROW=None

def main():
    global FROZEN,FREEZE_SHA,ROW
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();root=a.output.resolve()
    FREEZE_SHA=sha(root/'FROZEN.json');FROZEN=json.loads((root/'FROZEN.json').read_text())
    if freeze_check(FROZEN):raise RuntimeError('Frozen environment/source/binary mismatch')
    if any(root.glob('b*')) or (root/'ledger.jsonl').exists():raise RuntimeError('Primary attempts already exist; no automatic repeat/resume')
    state={'status':'running','freeze_sha256':FREEZE_SHA,'started_unix_ns':time.time_ns(),'attempts':0}
    save(root/'matrix-state.json',state)
    try:
        for ROW in FROZEN['order']:
            if sha(root/'FROZEN.json')!=FREEZE_SHA or freeze_check(FROZEN):raise RuntimeError('Freeze changed; stop')
            state['current']=ROW;state['attempts']+=1;save(root/'matrix-state.json',state)
            run(root,ROW['name'],36,policy=ROW['policy'],schedule='contract')
        state['status']='complete'
    except Exception as error:
        state['status']='stopped_partial';state['error']=repr(error);raise
    finally:
        state['finished_unix_ns']=time.time_ns();save(root/'matrix-state.json',state)
if __name__=='__main__':main()
