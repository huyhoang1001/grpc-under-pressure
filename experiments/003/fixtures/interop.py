#!/usr/bin/env python3
"""Two-message cross-language correctness fixture; never a performance workload."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import struct
import subprocess
import time
ROOT=Path(__file__).resolve().parents[3]

def save(p,value):
    with p.open('x') as out:json.dump(value,out,indent=2);out.write('\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    payload=b''.join(hashlib.sha256(struct.pack('<QQ',1,i)).digest() for i in range(512));digest=list(hashlib.sha256(payload).digest())
    manifest={'run_id':'e3-stage1-two-message-fixture','payload_seed':1,'originals':[{'message_id':i,'client_id':0,'scheduled_offset_ns':i*12_500_000,'deadline_offset_ns':i*12_500_000+2_000_000_000,'payload_sha256':digest,'expendable':True} for i in range(2880)]}
    save(out/'workload.json',manifest);source_hashes={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'experiments/003').rglob('*') if p.is_file() and '/target/' not in str(p) and '/results/' not in str(p) and '__pycache__' not in str(p)};epoch=time.time_ns()+1_000_000_000
    server=ROOT/'experiments/003/server/target/debug/pressure-e3-stage1';client=Path('/workspace/toolchains/bin/e3-stage1-smoke')
    limits=['prlimit','--cpu=5','--fsize=16777216','--core=0','--'];cmd=limits+[str(server),'--manifest',str(out/'workload.json'),'--output',str(out/'server'),'--epoch-unix-ns',str(epoch),'--addr','127.0.0.1:0']
    evidence={'source_sha256':source_hashes,'fixture_only':True,'messages_sent':2,'not_a_primary_or_performance_run':True,'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'git_status':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),'epoch_unix_ns':epoch,'server_command':cmd,'workload_sha256':sha(out/'workload.json'),'binary_sha256':{str(p):sha(p) for p in [server,client]},'synthetic_reconciliation_cutoff_ns':39_000_000_000}
    proc=None
    try:
        with (out/'server.log').open('x') as sl,(out/'client.log').open('x') as cl:
            proc=subprocess.Popen(cmd,cwd=ROOT,stdout=sl,stderr=sl)
            ready=out/'server/ready.json';deadline=time.monotonic()+5
            while not ready.exists():
                if proc.poll() is not None or time.monotonic()>deadline:raise RuntimeError('server startup failure')
                time.sleep(.01)
            address=json.loads(ready.read_text())['addr'];ccmd=limits+[str(client),'--manifest',str(out/'workload.json'),'--addr',address,'--epoch-unix-ns',str(epoch),'--events',str(out/'client-events.jsonl'),'--report',str(out/'client-report.json')];evidence['client_command']=ccmd
            run=subprocess.run(ccmd,cwd=ROOT,stdout=cl,stderr=cl,timeout=10);evidence['client_exit']=run.returncode
            if run.returncode:raise RuntimeError('client fixture failed')
            proc.send_signal(signal.SIGINT);evidence['server_exit']=proc.wait(timeout=5)
            if proc.returncode:raise RuntimeError('server fixture failed')
        s=json.loads((out/'server/server-ledger.json').read_text());c=json.loads((out/'client-report.json').read_text());assert not s['failed'];assert s['occupied']==s['decoded_staging']==s['terminal_responses_reserved']==s['immediate_responses']==0
        assert s['permits_acquired']==s['permits_released']==2;assert s['logical_entries']==s['attempt_entries']==2
        assert all(o['starts']==1 and o['terminal']['outcome']==1 for o in s['originals']);assert all(a['write_accepted'] for a in s['attempts'])
        assert c['client']['Outstanding']==c['client']['Pending']==0;assert c['client']['Attempts']==c['client']['SendSuccess']==2
        rec=c['client_observed_reconciliation'];assert rec['N']==2880 and rec['U']==2 and sum(rec['Counts'].values())==2880
        for id,obs in enumerate(c['observations']):assert obs['Seq']==s['originals'][id]['terminal']['event_seq'] and obs['Offset']==s['originals'][id]['terminal']['offset_ns']
        for role,path in [('server',out/'server/server-events.jsonl'),('client',out/'client-events.jsonl')]:
            rows=[json.loads(v) for v in path.read_text().splitlines()];assert [v['seq'] for v in rows]==list(range(1,len(rows)+1));assert len(rows)==(s['event_seq'] if role=='server' else c['client']['EventSeq']);evidence[role+'_events']=len(rows)
        assert all(sha(ROOT/name)==digest for name,digest in source_hashes.items());evidence['source_hashes_unchanged']=True
        evidence['verdict']='PASS'
    except Exception as error:evidence['verdict']='FAIL';evidence['error']=repr(error);raise
    finally:
        if proc is not None and proc.poll() is None:proc.kill();proc.wait()
        save(out/'verification.json',evidence)
    print('PASS: 2 Rust/Go messages, stable terminal IDs/timestamps, exact permits, bounded ownership, contiguous logs; synthetic 2880-ID partition')
if __name__=='__main__':main()
