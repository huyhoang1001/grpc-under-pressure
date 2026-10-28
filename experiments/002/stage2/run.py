#!/usr/bin/env python3
"""Stage 2 only: overhead controls, targeted checks, ONE exploratory contract run."""
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
from verify import verify,read
SERVER=ROOT/'server/target/debug/pressure-stage1'
CLIENT=Path('/workspace/toolchains/bin/pressure-stage1-client')

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def expected_delay(t):return 40 if 12_000_000_000<=t<24_000_000_000 else 10

def validate(folder):
    m=json.loads((folder/'manifest.json').read_text());issues=[]
    if m['event_io']=='buffered':issues+=verify(folder)
    else:
        # No fake event ledger for controls: audit counters/bytes/histograms explicitly.
        s=read(folder/'server/server.csv');c=json.loads((folder/'client/summary.json').read_text())
        h=json.loads((folder/'server/histograms.json').read_text())
        for r in s:
            q,w,res=[int(r[k]) for k in ['Q','W','R']]
            if not(0<=q<=32 and 0<=w<=1 and 0<=res<=1 and q+res<=32):issues.append('occupancy')
            if q!=int(r['physical_queue_depth']) or q!=int(r['admitted'])-int(r['dequeued'])-int(r['discarded_from_queue']):issues.append('queue counter')
            if w!=int(r['dequeued'])-int(r['processed'])-int(r['discarded_from_worker']):issues.append('worker counter')
            if int(r['queued_payload_bytes'])!=int(r['admitted_bytes'])-int(r['dequeued_bytes'])-int(r['discarded_queue_bytes']):issues.append('queue bytes')
            if int(r['worker_payload_bytes'])!=int(r['dequeued_bytes'])-int(r['processed_bytes'])-int(r['discarded_worker_bytes']):issues.append('worker bytes')
            if int(r['received'])!=int(r['admitted'])+int(r['received_not_admitted']):issues.append('receive balance')
            if int(r['reservations_acquired'])!=int(r['admitted'])+int(r['reservations_released'])+res:issues.append('reservation balance')
            if int(r['errors']) or int(r['telemetry_errors']):issues.append('instrumentation/stream error')
        last=s[-1]
        if any(int(last[k]) for k in ['Q','R','W','active_streams','discarded']):issues.append('control not drained')
        if not(int(last['processed'])==int(last['admitted'])==c['successful_sends']==c['summary']['accepted']==c['summary']['processed']):issues.append('control final counts')
        if sum(sum(p) for p in h['service_counts'])!=int(last['processed']):issues.append('control histogram counts')
        for r in read(folder/'client/client.csv'):
            if int(r['scheduled'])!=int(r['skipped'])+int(r['attempted']) or int(r['attempted'])!=int(r['successful_sends'])+int(r['failed_sends'])+int(r['inflight']):issues.append('client counter')
        if c['rpc_error']!='<nil>' or c['failed_sends']:issues.append('control client error')
        if m.get('server_exit')!=0 or m.get('client_exit')!=0:issues.append('control exit')
        if m['clock']['phase_alignment_error_ns']>100_000_000:issues.append('control alignment')
    if m.get('events') or m.get('runner_error') or not m['source_hashes_unchanged']:issues.append('runner/resource/source error')
    if m['service_schedule']=='contract' and m['event_io']=='buffered':
        for e in read(folder/'server/events.csv'):
            if e['event'] in ['dequeued','processed','discarded_worker']:
                start=int(e['service_start_ns']);chosen=int(e['selected_service_ms'])
                if start!=int(e['dequeue_ns']) or chosen!=expected_delay(start):issues.append('service-start schedule mismatch')
        if m['offered_seconds']==36:
            transitions=read(folder/'server/phase-transitions.csv')
            if [int(r['scheduled_ns']) for r in transitions]!=[0,12_000_000_000,24_000_000_000,36_000_000_000]:issues.append('missing phase markers')
            if any(int(r['lateness_ns'])>100_000_000 for r in transitions):issues.append('phase marker >100ms late')
            if [int(r['configured_ms']) for r in transitions]!=[10,40,10,10]:issues.append('wrong phase delays')
            c=json.loads((folder/'client/summary.json').read_text())
            if c['scheduled']!=2880 or c['half_close_ns']<36_000_000_000:issues.append('frozen schedule incomplete')
    return sorted(set(issues))

def run(root,name,seconds,schedule='constant',event_io='buffered',purpose='overhead_control'):
    folder=root/name;folder.mkdir(parents=True,exist_ok=False)
    sd=folder/'server';cd=folder/'client';marker=folder/'marker.txt'
    server=[str(SERVER),'--output',str(sd),'--marker',str(marker),'--service-schedule',schedule,'--event-io',event_io]
    client=[str(CLIENT),'--output',str(cd),'--marker',str(marker),'--rate','80','--seconds',str(seconds),'--timeout','120s']
    limits=['prlimit','--cpu=10','--fsize=16777216','--core=0','--']
    inputs=git('ls-files','server','loadgen','proto','rust-toolchain.toml','experiments/002').splitlines()
    inputs=[p for p in inputs if '/results/' not in p]
    m={'schema':'e2-stage2-run-v1','name':name,'purpose':purpose,'primary_run':False,'expected_fault':None,'git_commit':git('rev-parse','HEAD'),'git_status_porcelain':git('status','--porcelain=v1','--untracked-files=all'),'source_sha256':{p:sha(ROOT/p) for p in inputs},'binary_sha256':{str(p):sha(p) for p in [SERVER,CLIENT]},'server_command':limits+server,'client_command':limits+client,'cwd':str(ROOT),'event_io':event_io,'full_event_evidence':event_io=='buffered','service_schedule':schedule,'sample_ms':200,'rate':80,'offered_seconds':seconds,'payload_bytes':16384,'seed':1,'physical_K':32,'static_pending_limit':32,'dynamic_budget':False,'windows':{'stream':65535,'connection':65535,'server_adaptive':False},'runtime':{'tokio_workers':2,'gomaxprocs':2,'compression':False,'retries':False,'max_message_bytes':1048576},'build_mode':'debug Rust; default optimized Go','cpu_affinity':sorted(os.sched_getaffinity(0)),'kernel':platform.release(),'limits':{'server_rss':536870912,'client_rss':134217728,'cpu_seconds':10,'file_bytes':16777216,'wall_seconds':125,'rpc_deadline':'120s'},'started_unix_ns':time.time_ns(),'started_monotonic_ns':time.monotonic_ns(),'events':[]}
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
    with (root/'ledger.jsonl').open('a') as f:f.write(json.dumps({'name':name,'purpose':purpose,'event_io':event_io,'issues':issues,'valid':not issues})+'\n')
    print(name,'PASS' if not issues else issues,flush=True)
    if issues:raise RuntimeError('Stop and diagnose; all attempted data retained')

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--phase',required=True,choices=['overhead','exploratory','smoke']);a=p.parse_args();root=a.output.resolve();root.mkdir(parents=True,exist_ok=True)
    if a.phase=='overhead':
        with (root/'overhead-order.json').open('x') as f:json.dump(['buffered-1','discard-1','discard-2','buffered-2'],f);f.write('\n')
        for name,mode in [('buffered-1','buffered'),('discard-1','discard'),('discard-2','discard'),('buffered-2','buffered')]:run(root,name,4,event_io=mode)
    elif a.phase=='smoke':run(root,'schedule-smoke',.8,schedule='contract',purpose='short_integration_fixture')
    else:
        assessment=json.loads((root/'analysis.json').read_text())
        if 'overhead' not in assessment:raise RuntimeError('Assess overhead controls before exploratory run')
        if any(root.glob('exploratory-*/manifest.json')):raise RuntimeError('An exploratory attempt already exists; inspect it instead of silently repeating')
        run(root,'exploratory-1',36,schedule='contract',purpose='single_exploratory_slowdown_recovery')
if __name__=='__main__':main()
