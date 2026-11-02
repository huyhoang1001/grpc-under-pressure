#!/usr/bin/env python3
"""Independent Stage6 replay, derived from frozen Stage3 gates; no app imports."""
import argparse,collections,csv,hashlib,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
S=importlib.util.spec_from_file_location('base',ROOT/'experiments/003/fixtures/verify-stage3.py');V=importlib.util.module_from_spec(S);S.loader.exec_module(V)
need,disposition=V.need,V.disposition
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def client_replay(m,w,c,ce,cid):
    originals=w['originals'];n=len(originals)
    need(0<n<=2880 and [x['message_id'] for x in originals]==list(range(n)),'original population')
    pending=set();active={};attempts={};returned={};send_start={};observed={};arrived=set();state={};retry_count=0
    cp={'Pending':0,'Outstanding':0,'Events':0,'Responses':0}
    for e in ce:
        k,i,a=e['kind'],e['message_id'],e['attempt_id']
        if k=='original_arrival':
            need(i not in arrived and 0<=i<n,'duplicate/foreign arrival');arrived.add(i);state[i]=e['state'] if 'state' in e else ''
            if state[i] not in ['CLIENT_BACKLOG_EXHAUSTED','EXPIRED_BEFORE_SEND']:pending.add(i)
        if k=='attempt_initiated':
            need(i in pending and a not in attempts and i not in active.values(),'attempt ownership/overlap')
            pending.remove(i);active[a]=i;attempts[a]=i
            need(1<=e['attempt_number']<=3,'attempt limit')
        if k=='grpc_send_start':need(a in attempts and a not in send_start,'send start');send_start[a]=e['offset_ns']
        if k=='grpc_send_return':
            need(a in attempts and a not in returned and a in send_start,'Send return without initiated/start')
            need(e['send_timing_exact'] and e['send_duration_ns']==e['offset_ns']-send_start[a],'Send duration')
            returned[a]=e['send_success']
        terminal_event=k=='terminal_observed' or k=='retry_scheduled' or k.startswith('retry_final_')
        if terminal_event:
            v=e['result'];need(v is not None and a in attempts,'missing observation')
            if a not in observed:
                need(a in active,'terminal credit already released');active.pop(a);observed[a]=v
            else:need(observed[a]==v,'inconsistent observation')
            state[i]=e.get('state','')
        if k=='retry_scheduled':
            need(m['policy']=='retry' and observed[a]['Outcome']==2 and i not in pending,'illegal retry')
            need(e['offset_ns']<originals[i]['deadline_offset_ns'],'retry after deadline')
            number=e['attempt_number'];need(number<3 and 0<=e['ready_offset_ns']-e['offset_ns']<=min(100_000_000*2**(number-1),400_000_000),'retry jitter/limit')
            pending.add(i);retry_count+=1
        if k in ['expired_before_send','retry_expired_waiting']:
            need(i in pending,'expiry not pending');pending.remove(i);state[i]=e.get('state','')
        if k=='stream_closed':
            for i in pending:state[i]='CANCELLED'
            pending.clear();active.clear()
        need(e['pending']==len(pending) and e['outstanding']==len(active),'client resource/counter replay')
        vals=[e['pending'],e['outstanding'],e['event_queue'],e['response_queue']]
        need(all(0<=v<=cap for v,cap in zip(vals,[32,33,1024,64])),'client resource bound')
        for name,value in zip(cp,vals):cp[name]=max(cp[name],value)
    need(all(a['commit_offset_ns']<=b['commit_offset_ns'] for a,b in zip(ce,ce[1:])), 'client commit time order')
    need(not active and not pending and c['client']['ResponseQueue']==0,'client cleanup')
    need(cp==c['client']['HighWater'],'client high-water mismatch')
    need(c['client']['Attempts']==len(attempts) and c['client']['FirstAttempts']==len(set(attempts.values())) and c['client']['Retries']==len(attempts)-len(set(attempts.values())),'attempt counters')
    need(c['client']['SendSuccess']==sum(returned.values()) and len(returned)==len(attempts),'send counters')
    need(c['client']['Retries']<=retry_count<=2*n,'retry scheduled/initiated bounds')
    owned={x['message_id'] for x in originals if x['client_id']==cid}
    need(arrived==owned,'all owned scheduled originals / foreign arrivals')
    need([e['seq'] for e in ce]==list(range(1,c['client']['EventSeq']+1)),'client sequence/tail')
    need(not c['client']['Invalid'] and not c['exchange_error'],'client invalid/stream failure')
    need(c['secondary_only'] and c['client_id']==cid and c['client_count']==m['clients'],'secondary ownership metadata')
    need(c['deadline_ns']==m['deadline_ns'] and c['retry_mode']==m['retry_mode'] and c['retry_seed']==m['client_seeds'][cid],'secondary configuration drift')
    need(list(attempts)==[cid+j*m['clients'] for j in range(len(attempts))],'attempt namespace / sequence')
    by={}
    rng=m['client_seeds'][cid];mask=(1<<64)-1
    for e in ce:
        i=e['message_id'];k=e['kind']
        if k=='attempt_initiated':
            need(i in owned and originals[i]['scheduled_offset_ns']<=e['offset_ns']<originals[i]['deadline_offset_ns'],'send schedule/deadline')
            by.setdefault(i,[]).append(e['attempt_number'])
        if k=='retry_scheduled':
            cap=min(100_000_000*2**(e['attempt_number']-1),400_000_000)
            if m['retry_mode']=='deterministic':delay=cap
            else:
                while True:
                    rng=(rng+0x9e3779b97f4a7c15)&mask;z=rng
                    z=((z^(z>>30))*0xbf58476d1ce4e5b9)&mask;z=((z^(z>>27))*0x94d049bb133111eb)&mask;z=z^(z>>31)
                    if z>=((1<<64)%(cap+1)):delay=z%(cap+1);break
            need(e['ready_offset_ns']-e['offset_ns']==delay,'retry generator replay')
    need(all(numbers==list(range(1,len(numbers)+1)) and len(numbers)<=3 for numbers in by.values()),'attempt numbers')
    need(len(attempts)<=3*len(owned) and c['client']['Retries']<=2*len(owned),'owned attempt bounds')
    transport=c['transport'];need(transport['grpc_out_messages']==sum(returned.values()),'grpc successful send counter')
    need(transport['tcp_stream_write_bytes']>=transport['grpc_out_wire_bytes']>=16384*sum(returned.values()),'transport bytes')
    return {'attempts':attempts,'observed':observed,'state':state,'high_water':cp,'retry_scheduled':retry_count,'owned':sorted(owned)}
def server_replay(s,c,w,se,attempts,observed,state,cutoff):
    originals=w['originals'];n=len(originals)
    need([e['seq'] for e in se]==list(range(1,s['event_seq']+1)),'server sequence/tail')
    need(all(a['offset_ns']<=b['offset_ns'] for a,b in zip(se,se[1:])),'server monotonic event order')
    queue=[];running=None;starts={};exits={};decoded={};admitted={};acquired=released=0;residence=[];wait=[];busy=0
    peaks={key:0 for key in s['high_water']};caps=dict(queued=32,running=1,staging=1,receive=1,terminal=32,immediate=32,events=1024)
    for e in se:
        k,i=e['kind'],e['message_id'];now=e['offset_ns']
        if k in ['decoded','duplicate_linked']:need(e['attempt_id'] in attempts,'foreign decode');decoded[e['attempt_id']]=i
        if k=='decoded':decoded[('last',i)]=now
        if k=='admitted':
            need(i not in queue and running!=i and ('last',i) in decoded,'admission without decode')
            queue.append(i);admitted[i]=now;wait.append(now-decoded[('last',i)]);acquired+=1
        if k=='worker_start':
            need(running is None and i not in starts and queue and queue[0]==i,'duplicate execution/FIFO')
            need(now<originals[i]['deadline_offset_ns'],'start after deadline');queue.pop(0);running=i;starts[i]=now;residence.append(now-admitted[i])
        if k=='worker_exit':
            need(running==i and i not in exits,'exit without worker');running=None;released+=1;exits[i]=now
            need(e['terminal'] and e['terminal']['worker_service_ns']==now-starts[i],'worker occupied-time accounting');busy+=now-starts[i]
        if k=='queued_removed':need(i in queue,'remove absent queue');queue.remove(i);released+=1
        if k=='policy_refusal':need(e['occupied']==32 and e['terminal']['outcome'] in [2,3] and i not in starts,'invalid overload refusal/drop')
        need(e['queued']==len(queue) and e['running']==int(running is not None) and e['occupied']==len(queue)+int(running is not None),'server ownership replay')
        r=e['resources'];need(r['staging']+r['receive']<=1,'receive reservation/staging bound')
        for key,cap in caps.items():need(0<=r[key]<=cap,'server resource bound '+key);peaks[key]=max(peaks[key],r[key])
    need(queue==[] and running is None and acquired==released==s['permits_acquired']==s['permits_released'],'server permits/cleanup')
    need(peaks==s['high_water'],'server high-water mismatch')
    need(s['writer_calls']>=len([e for e in se if e['kind']=='local_write_accepted']) and s['writer_progress_ns']>=0,'writer counters')
    need(len(starts)==sum(o['starts'] for o in s['originals']) and all(o['starts']<=1 for o in s['originals']),'duplicate execution counter')
    need({a['attempt_id'] for a in s['attempts']}=={a for a in decoded if isinstance(a,int)},'server decode count')
    need(s['decoded_frames']==len([e for e in se if e['kind'] in ['decoded','duplicate_linked','attempt_replay']]),'decoded frame counter')
    server_attempts={a['attempt_id']:a for a in s['attempts']}
    for a,v in observed.items():
        t=server_attempts[a]['terminal'];need(v['Outcome']==t['outcome'] and v['Seq']==t['event_seq'] and v['Offset']==t['offset_ns'] and v['Service']==t['worker_service_ns'],'observation/server terminal contradiction')
    by_id={o['message_id']:o for o in s['originals']};need(len(by_id)==len(s['originals']),'duplicate server identity')
    partition={};missing={}
    for i in range(n):
        ids=[a for a,owner in attempts.items() if owner==i];latest=ids[-1] if ids else None
        o=by_id.get(i);t=o['terminal'] if o else None;v=observed.get(latest)
        partition[i]=disposition(t,originals[i]['deadline_offset_ns'],state.get(i),len(ids),v,latest in server_attempts,bool(s['failed'] or c['exchange_error']))
        if not ids:need(originals[i]['deadline_offset_ns']<=cutoff,'cutoff before unsent deadline')
        missing[i]=bool(t and (v is None or (v['Outcome'],v['Seq'],v['Offset'],v['Service'])!=(t['outcome'],t['event_seq'],t['offset_ns'],t['worker_service_ns']))) if partition[i]!='UNKNOWN' else False
        if o and o['starts']:need(i in exits and t['worker_service_ns']==exits[i]-starts[i],'final worker duration')
    need(sum(o['terminal']['worker_service_ns'] for o in by_id.values() if o['terminal'])==busy,'worker disposition total')
    rec=c['server_reconciliation'];need(rec['N']==n and rec['Attempts']==len(attempts),'reconciliation population')
    outcomes={x['message_id']:x['disposition'] for x in rec['Outcomes']}
    need(len(outcomes)==len(rec['Outcomes'])==n and outcomes==partition,'incorrect terminal partition')
    counts=dict(collections.Counter(partition.values()));need(all(x['ack_missing']==missing[x['message_id']] for x in rec['Outcomes']),'ACK-missing reconciliation')
    need(rec['Counts']==counts and rec['U']==counts.get('COMPLETED_ON_TIME',0),'incorrect terminal counters')
    need(not s['failed'],'server failure')
    need(s['occupied']==s['decoded_staging']==s['receive_stage_reservation']==s['terminal_responses_reserved']==s['immediate_responses']==s['event_writer_queue']==0,'server final resources')
    need(s['queued_payload_bytes']==s['worker_payload_bytes']==s['staging_payload_bytes']==0,'payload final ownership')
    reserved=False
    for e in se:
        if e['kind']=='decode_reserved':need(not reserved,'double receive reservation');reserved=True
        if e['kind'] in ['decoded','duplicate_linked','attempt_replay']:
            need(reserved,'decode without reservation');reserved=False
        if e['kind'] in ['client_done','half_close']:reserved=False
    need(not reserved,'leaked receive reservation')
    for o in s['originals']:
        if o['starts']:
            need(o['exit_ns'] is not None and o['exit_ns']<=cutoff,'worker beyond cutoff')
            if o['terminal']['outcome']==1:need(o['exit_ns']-o['start_ns'] >= (40_000_000 if 12e9<=o['start_ns']<24e9 else 10_000_000),'service phase')
    return {'partition':counts,'U':counts.get('COMPLETED_ON_TIME',0),'A':len(attempts),'F':len(set(attempts.values())),'R':len(server_attempts),'admitted':acquired,'worker_starts':len(starts),'worker_exits':len(exits),'worker_occupied_ns':busy,'queue_residence_ns':residence,'admission_wait_ns':wait,'server_high_water':peaks,'ack_missing':sum(missing.values())}
def verify(run):
    m=read(run/'verification.json');w=read(run/'workload.json');s=read(run/'server/server-ledger.json');clock=read(run/'server/clock.json');cutoff=m['cutoff_ns'];n=len(w['originals']);clients=m['clients']
    plan=read(ROOT/'experiments/003/results/stage6/RUN-PLAN.json')
    need(any(all(m[k]==case[k] for k in case) for block in plan['blocks'] for case in block['cases']),'preregistered case/seed/configuration')
    cfg=m['configuration'];need(cfg['http2_stream_window']==cfg['http2_connection_window']==65535 and cfg['worker_count']==1 and cfg['service_ms']==[10,40,10] and cfg['boundaries_s']==[12,24] and cfg['client_event_buffer_bytes']==0 and cfg['server_global_staging']==1 and cfg['server_global_terminal_slots']==cfg['server_global_immediate_slots']==32,'runtime settings')
    need(m['secondary_only'] and not m['primary_run'] and m['contract_revision']=='A01','study classification')
    need(m['source_sha256'] and m['binary_sha256'] and m['source_unchanged'] and all(v==0 for v in m['process_returncodes'].values()) and not m['safety_abort'],'source/process status')
    need((m['client_outstanding_limit'],m['client_pending_limit'],m['server_admission_limit'])==(33,32,32),'A01')
    need(n==(80 if m['profile']=='secondary-smoke' else 2880),'population')
    need(w['payload_seed']==1 and sha(run/'workload.json')==m['workload_sha256'],'workload hash')
    for i,o in enumerate(w['originals']):need(o['message_id']==i and o['client_id']==i%clients and o['scheduled_offset_ns']==i*12_500_000 and o['deadline_offset_ns']==i*12_500_000+m['deadline_ns'] and o['expendable'],'immutable original demand')
    need(cutoff>=w['originals'][-1]['deadline_offset_ns']+1_000_000_000,'insufficient cancellation grace')
    intervals=[];reports=[];events=[];replays=[];attempts={};observed={};state={};outcomes=[];counter=collections.Counter();rpc=[]
    def bracket(b,go):
        lo=b['EpochMinNS' if go else 'epoch_min_ns'];hi=b['EpochMaxNS' if go else 'epoch_max_ns'];samples=b['Samples' if go else 'samples']
        need(samples==8 and 0<=hi-lo<5_000_000,'clock bracket');intervals.append((lo,hi));return (lo+hi)//2
    epochs={'server':bracket(clock['start'],False)};bracket(clock['end'],False)
    for cid in range(clients):
        c=read(run/f'client-{cid}/report.json');ce=[json.loads(x) for x in (run/f'client-{cid}/events.jsonl').read_text().splitlines()]
        replay=client_replay(m,w,c,ce,cid);replays.append(replay);reports.append(c);events.extend(ce)
        need(not(set(attempts)&set(replay['attempts'])),'global attempt-ID collision');attempts.update(replay['attempts']);observed.update(replay['observed']);state.update(replay['state'])
        rec=c['server_reconciliation'];need(rec['N']==len(replay['owned']) and {o['message_id'] for o in rec['Outcomes']}==set(replay['owned']),'client reconciliation ownership')
        outcomes.extend(rec['Outcomes']);counter.update(rec['Counts'])
        need(rec['U']==rec['Counts'].get('COMPLETED_ON_TIME',0),'local U')
        epochs[f'client-{cid}']=bracket(c['client']['ClockStart'],True);bracket(c['client']['ClockEnd'],True)
        half=[e for e in ce if e['kind']=='client_half_close'];need(len(half)==1 and half[0]['offset_ns']<=c['rpc_end_offset_ns']<=cutoff,'client EOF/drain')
        need(c['observation_end_offset_ns']>=cutoff and c['client']['Pending']==c['client']['Outstanding']==c['client']['EventQueue']==c['client']['ResponseQueue']==0,'client observation/final ownership')
        rpc.append(c['rpc_end_offset_ns'])
    uncertainty=max(hi for lo,hi in intervals)-min(lo for lo,hi in intervals);need(uncertainty<5_000_000,'cross-process clock uncertainty')
    combined={'exchange_error':'','server_reconciliation':{'N':n,'Attempts':len(attempts),'Outcomes':outcomes,'Counts':dict(counter),'U':counter.get('COMPLETED_ON_TIME',0)}}
    se=[json.loads(x) for x in (run/'server/server-events.jsonl').read_text().splitlines()]
    result=server_replay(s,combined,w,se,attempts,observed,state,cutoff)
    initiated={e['attempt_id']:(e['message_id'],e['attempt_number']) for e in events if e['kind']=='attempt_initiated'}
    need({a['attempt_id']:(a['message_id'],a['attempt_number']) for a in s['attempts']}==initiated,'global attempt correspondence')
    need(result['A']<=8640 and len(outcomes)==n and sum(result['partition'].values())==n,'global accounting')
    need(sum(e['kind']=='client_done' for e in se)==clients and sum(e['kind']=='half_close' for e in se)==1,'all streams EOF')
    io=clock['bounded_io'];need(all(io[k]==0 for k in ['bridge_current','writer_current','logger_current']) and io['bridge_peak']<=clients and io['writer_peak']<=1 and io['logger_peak']<=1,'bounded IO')
    phases=[json.loads(x) for x in (run/'server/phases.jsonl').read_text().splitlines()];expected=sorted(set(x for x in [0,12_000_000_000,24_000_000_000,36_000_000_000,cutoff] if x<=cutoff))
    need([x['expected_offset_ns'] for x in phases]==expected and all(x['actual_offset_ns']>=x['expected_offset_ns'] for x in phases),'phase/cutoff observations')
    finished=read(run/'server/finished.json');need(finished['supervised_tasks_joined'] and finished['logs_flushed'],'supervision/flush')
    coverage={}
    for role,epoch in epochs.items():
        samples=list(csv.DictReader((run/f'{role}-metrics.csv').open()));times=[int(x['host_monotonic_ns']) for x in samples]
        need(len(times)>=2 and times[0]<=epoch and times[-1]>=epoch+cutoff,'sampling coverage '+role)
        need(all(a<b for a,b in zip(times,times[1:])) and max(b-a for a,b in zip(times,times[1:]))<500_000_000,'sampling gap '+role)
        need(all(int(x['rss_bytes'])<=268435456 for x in samples),'RSS guard')
        coverage[role]={'samples':len(times),'max_gap_ns':max(b-a for a,b in zip(times,times[1:])),'rss_peak_bytes':max(int(x['rss_bytes']) for x in samples),'cpu_last_ns':int(samples[-1]['cpu_user_ns'])+int(samples[-1]['cpu_system_ns'])}
    result.update({'verdict':'PASS','secondary_only':True,'clock_uncertainty_ns':uncertainty,'client_high_water':[x['high_water'] for x in replays],'sampling':coverage,'rpc_end_ns':rpc,'phase_lateness_ns':[x['actual_offset_ns']-x['expected_offset_ns'] for x in phases],'genuine_refusals':sum(a['terminal']['outcome']==2 for a in s['attempts']),'genuine_drops':sum(a['terminal']['outcome']==3 for a in s['attempts']),'worker_final_zero':True,'bounded_io':io,'verifier_sha256':sha(Path(__file__))})
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);args=parser.parse_args()
    try:result=verify(args.run)
    except (V.Invalid,KeyError,ValueError,AssertionError) as error:result={'verdict':'FAIL','error':str(error)}
    (args.run/'independent-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(result['verdict'],result.get('error',''))
    if result['verdict']!='PASS':raise SystemExit(1)
