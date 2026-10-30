#!/usr/bin/env python3
"""A01 conforming Go/Rust credit saturation correctness; never a benchmark."""
import argparse,hashlib,json,signal,struct,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):
    with p.open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
def sources():return {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'experiments/003').rglob('*') if p.is_file() and not any(x in p.parts for x in ['target','results','__pycache__'])}
def wait_file(path,proc,seconds=5):
    until=time.monotonic()+seconds
    while not path.exists():
        if proc.poll() is not None or time.monotonic()>until:raise RuntimeError('missing '+str(path))
        time.sleep(.005)
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--policy',required=True,choices=['wait','reject','retry','drop']);p.add_argument('--mode',choices=['drain','cancel'],default='drain');a=p.parse_args()
    assert a.mode=='drain' or a.policy=='wait'
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    payload=b''.join(hashlib.sha256(struct.pack('<QQ',1,i)).digest() for i in range(512));digest=list(hashlib.sha256(payload).digest())
    # Prefix of the frozen80/s schedule with unchanged2s deadlines and payload;
    # only33 originals and a test-only worker barrier. Not a primary run.
    workload={'run_id':'e3-a01-conforming-saturation','payload_seed':1,'originals':[{'message_id':i,'client_id':0,'scheduled_offset_ns':i*12_500_000,'deadline_offset_ns':i*12_500_000+2_000_000_000,'payload_sha256':digest,'expendable':True} for i in range(33)]}
    save(out/'workload.json',workload)
    server=ROOT/'experiments/003/server/target/debug/examples/credit-saturation';client=Path('/workspace/toolchains/bin/e3-a01-credit-smoke');epoch=time.time_ns()+1_000_000_000
    limits=['prlimit','--cpu=5','--fsize=16777216','--core=0','--']
    cmd=limits+[str(server),'--manifest',str(out/'workload.json'),'--output',str(out/'server'),'--epoch-unix-ns',str(epoch),'--policy',a.policy,'--mode',a.mode]
    evidence={'fixture_only':True,'not_primary_or_performance':True,'contract_revision':'A01','client_outstanding_limit':33,'client_pending_limit':32,'server_admission_limit':32,'policy':a.policy,'mode':a.mode,'retry_seed':1,'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'dirty_state':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),'source_sha256':sources(),'binary_sha256':{str(f):sha(f) for f in [server,client]},'server_command':cmd,'epoch_unix_ns':epoch,'workload_sha256':sha(out/'workload.json'),'expected_fault':'controlled worker barrier; stream cancellation only for WAIT/cancel'}
    sp=cp=None
    try:
        with (out/'server.log').open('x') as sl,(out/'client.log').open('x') as cl:
            sp=subprocess.Popen(cmd,cwd=ROOT,stdout=sl,stderr=sl);wait_file(out/'server/ready.json',sp)
            address=json.loads((out/'server/ready.json').read_text())['addr']
            ccmd=limits+[str(client),'--manifest',str(out/'workload.json'),'--addr',address,'--epoch-unix-ns',str(epoch),'--events',str(out/'client-events.jsonl'),'--report',str(out/'client-report.json'),'--server-ledger',str(out/'server/server-ledger.json'),'--policy',a.policy,'--retry-seed','1']
            if a.mode=='cancel':ccmd+=['--expect-cancel']
            evidence['client_command']=ccmd;cp=subprocess.Popen(ccmd,cwd=ROOT,stdout=cl,stderr=cl)
            wait_file(out/'client-report.json.transport',cp,6)
            sp.send_signal(signal.SIGINT);evidence['server_exit']=sp.wait(timeout=5);evidence['client_exit']=cp.wait(timeout=5)
            assert sp.returncode==cp.returncode==0
        s=json.loads((out/'server/server-ledger.json').read_text());c=json.loads((out/'client-report.json').read_text());b=json.loads((out/'server/barrier.json').read_text())['at_full_budget']
        assert b['occupied']==32 and b['running']==1 and b['queued']==31 and b['permits_released']==0
        assert s['occupied']==s['decoded_staging']==s['receive_stage_reservation']==s['terminal_responses_reserved']==s['immediate_responses']==s['event_writer_queue']==0
        assert s['queued_payload_bytes']==s['worker_payload_bytes']==s['staging_payload_bytes']==0
        assert s['permits_acquired']==s['permits_released'];assert all(o['starts']<=1 for o in s['originals'])
        assert c['client']['Pending']==c['client']['Outstanding']==c['client']['EventQueue']==0 and not c['client']['Invalid']
        assert c['server_reconciliation']['N']==33 and sum(c['server_reconciliation']['Counts'].values())==33
        assert c['client']['Attempts']==s['attempt_entries']==(35 if a.policy=='retry' else 33)
        assert c['client']['FirstAttempts']==33 and c['client']['Retries']==(2 if a.policy=='retry' else 0)
        if a.policy!='wait':
            expected=3 if a.policy=='drop' else 2
            assert b['decoded_staging']==0 and b['originals'][32]['starts']==0
            refused=[x for x in s['attempts'] if x['message_id']==32]
            assert len(refused)==(3 if a.policy=='retry' else 1)
            assert all(x['terminal']['outcome']==expected for x in refused)
            assert s['originals'][32]['starts']==0
        else:assert b['decoded_staging']==1 and b['decoded_attempts']==33
        if a.mode=='drain':
            assert s['failed'] is None and not c['exchange_error']
            assert s['permits_acquired']==(33 if a.policy=='wait' else 32)
            assert sum(o['terminal']['outcome']==1 for o in s['originals'])==(33 if a.policy=='wait' else 32)
            for o,v in zip(s['originals'],c['observations']):
                assert v['Seq']==o['terminal']['event_seq'] and v['Offset']==o['terminal']['offset_ns']
        else:
            assert s['failed']=='STREAM_FAILED' and c['exchange_error']
            assert all(o['terminal']['outcome']==6 for o in s['originals'])
            running=s['originals'][0]
            assert running['cancellation_requested_ns'] is not None and running['cancellation_observed_ns'] is not None and running['exit_ns'] is not None
        client_rows=None
        for role,path,tail in [('client',out/'client-events.jsonl',c['client']['EventSeq']),('server',out/'server/server-events.jsonl',s['event_seq'])]:
            rows=[json.loads(x) for x in path.read_text().splitlines()];assert [x['seq'] for x in rows]==list(range(1,tail+1))
            evidence[role+'_events']=len(rows)
            if role=='client':client_rows=rows
            else:
                assert all(x['occupied']<=32 and x['running']<=1 for x in rows)
                assert any(x['kind']=='policy_refusal' and x['occupied']==32 for x in rows) if a.policy!='wait' else not any(x['kind']=='policy_refusal' for x in rows)
        # Independent replay of client credit transitions: do not infer admission
        # from Send. An observed terminal releases its matching credit once.
        active=set();peak=0;initiated=set();arrived=set();released=set();retry_events=[];pending=set();pending_peak=0
        for e in client_rows:
            kind=e['kind'];attempt=e['attempt_id']
            if kind=='original_arrival':
                arrived.add(e['message_id']);assert e['message_id'] not in pending;pending.add(e['message_id'])
            if kind=='attempt_initiated':
                assert e['message_id'] in pending;pending.remove(e['message_id'])
                assert attempt not in initiated;initiated.add(attempt);active.add(attempt);peak=max(peak,len(active));assert len(active)<=33
            if kind=='terminal_observed':assert attempt in active;active.remove(attempt);released.add(attempt)
            if kind=='stream_closed':active.clear();pending.clear()
            if kind=='retry_scheduled':
                retry_events.append(e);assert e['message_id'] not in pending;pending.add(e['message_id'])
            if kind in ['expired_before_send','retry_expired_waiting']:pending.remove(e['message_id'])
            pending_peak=max(pending_peak,len(pending));assert len(pending)<=32
        assert len(arrived)==33 and not active and peak==33
        assert len(initiated)==c['client']['Attempts'] and len(retry_events)==(2 if a.policy=='retry' else 0)
        assert {x['attempt_id'] for x in s['attempts']}==initiated
        assert all(x['ready_offset_ns']>=x['offset_ns'] for x in retry_events)
        evidence['independent_pending_peak']=pending_peak;evidence['independent_credit_peak']=peak;evidence['all_original_arrivals_recorded']=len(arrived);evidence['real_retry_events']=retry_events
        assert sources()==evidence['source_sha256'];evidence['source_hashes_unchanged']=True;evidence['verdict']='PASS'
    except Exception as error:evidence['verdict']='FAIL';evidence['error']=repr(error);raise
    finally:
        for proc in [cp,sp]:
            if proc is not None and proc.poll() is None:proc.kill();proc.wait()
        save(out/'verification.json',evidence)
    print('PASS:',a.policy,a.mode,'conforming credit peak33, full server32, exact cleanup; no performance conclusion')
if __name__=='__main__':main()
