#!/usr/bin/env python3
"""Independent offline E3 verifier. Does not import Rust/Go reconciliation code."""
import argparse,collections,csv,hashlib,json
from pathlib import Path
class Invalid(ValueError):pass
def need(ok,reason):
    if not ok:raise Invalid(reason)
def load(run):
    read=lambda name:json.loads((run/name).read_text())
    return {'manifest':read('verification.json'),'workload':read('workload.json'),'server':read('server/server-ledger.json'),'client':read('client-report.json'),'clock':read('server/clock.json'),'server_events':[json.loads(x) for x in (run/'server/server-events.jsonl').read_text().splitlines()],'client_events':[json.loads(x) for x in (run/'client-events.jsonl').read_text().splitlines()],'metrics':{role:list(csv.DictReader((run/(role+'-metrics.csv')).open())) for role in ['server','client']}}
def classify(t,deadline):
    code=t['outcome']
    if code==1:return 'COMPLETED_ON_TIME' if t['offset_ns']<=deadline else 'COMPLETED_LATE'
    if code==2:return 'REJECTED_FINAL'
    if code==3:return 'DROPPED'
    if code==4:return 'EXPIRED_PROCESSING' if t['detail_code']=='EXPIRED_PROCESSING' else 'EXPIRED_WAITING_OR_QUEUED'
    if code==5:return 'PROCESSING_FAILED'
    if code==6:return 'CANCELLED'
    raise Invalid('unknown terminal outcome')
def disposition(terminal,deadline,local,attempt_count,latest_observed,latest_decoded,ambiguous_closed):
    if terminal and terminal['outcome']==2:
        if local=='EXPIRED_WAITING_OR_QUEUED' and latest_observed is not None:return local
        if attempt_count>1 and latest_observed is None and not latest_decoded:
            need(ambiguous_closed,'unexplained ambiguous retry');return 'UNKNOWN'
    if terminal:return classify(terminal,deadline)
    if not attempt_count:return local if local in ['CLIENT_BACKLOG_EXHAUSTED','CANCELLED'] else 'EXPIRED_BEFORE_SEND'
    need(ambiguous_closed,'unexplained UNKNOWN');return 'UNKNOWN'
def verify(d):
    m,w,s,c=d['manifest'],d['workload'],d['server'],d['client'];ce,se=d['client_events'],d['server_events']
    need(m['contract_revision']=='A01' and (m['client_outstanding_limit'],m['client_pending_limit'],m['server_admission_limit'])==(33,32,32),'A01 config')
    need(m['source_sha256'] and m['binary_sha256'] and m['toolchains'] and m['server_command'] and m['client_command'],'missing provenance')
    need(not c['client']['Invalid'],'client instrumentation invalid')
    if m['mode']=='drain':need(s['failed'] is None and not c['exchange_error'],'unexpected stream failure')
    if m['mode']=='cancel':need(s['failed']=='STREAM_FAILED' and bool(c['exchange_error']),'expected cancellation missing')
    need(s['failed'] not in ['UNRESOLVED_SHUTDOWN','METADATA_CAPACITY_EXHAUSTED','EVENT_WRITER_FAILED'],'server instrumentation invalid')
    for role,rows,tail in [('client',ce,c['client']['EventSeq']),('server',se,s['event_seq'])]:
        need([e['seq'] for e in rows]==list(range(1,tail+1)),role+' missing/reordered event or tail')
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
        if not ids:need(originals[i]['deadline_offset_ns']<=39_000_000_000,'cutoff before unsent deadline')
        missing[i]=bool(t and (v is None or (v['Outcome'],v['Seq'],v['Offset'],v['Service'])!=(t['outcome'],t['event_seq'],t['offset_ns'],t['worker_service_ns']))) if partition[i]!='UNKNOWN' else False
        if o and o['starts']:need(i in exits and t['worker_service_ns']==exits[i]-starts[i],'final worker duration')
    need(sum(o['terminal']['worker_service_ns'] for o in by_id.values() if o['terminal'])==busy,'worker disposition total')
    rec=c['server_reconciliation'];need(rec['N']==n and rec['Attempts']==len(attempts),'reconciliation population')
    outcomes={x['message_id']:x['disposition'] for x in rec['Outcomes']}
    need(len(outcomes)==len(rec['Outcomes'])==n and outcomes==partition,'incorrect terminal partition')
    counts=dict(collections.Counter(partition.values()));need(all(x['ack_missing']==missing[x['message_id']] for x in rec['Outcomes']),'ACK-missing reconciliation')
    need(rec['Counts']==counts and rec['U']==counts.get('COMPLETED_ON_TIME',0),'incorrect terminal counters')
    intervals=[]
    for role in ['server','client']:
        for point in ['start','end']:
            b=d['clock'][point] if role=='server' else c['client']['Clock'+point.capitalize()]
            low=b['epoch_min_ns'] if role=='server' else b['EpochMinNS'];high=b['epoch_max_ns'] if role=='server' else b['EpochMaxNS'];samples=b['samples'] if role=='server' else b['Samples']
            need(samples==8 and 0<=high-low<5_000_000,'clock bracket uncertainty')
            intervals.append((low,high))
    uncertainty=max(x[1] for x in intervals)-min(x[0] for x in intervals)
    need(uncertainty<5_000_000,'cross-process alignment/drift >=5ms')
    io=d['clock']['bounded_io'];need(all(io[k]==0 for k in ['bridge_current','writer_current','logger_current']) and all(io[k]<=1 for k in ['bridge_peak','writer_peak','logger_peak']),'bounded IO cleanup')
    for role,rows in d['metrics'].items():
        need(len(rows)>=2,'missing '+role+' process samples')
        times=[int(x['host_monotonic_ns']) for x in rows];need(all(a<b for a,b in zip(times,times[1:])),'metric time order')
        need(max(b-a for a,b in zip(times,times[1:]))<500_000_000,'metric sampling gap')
        need(all(x['contract_revision']=='A01' and int(x['rss_bytes'])>=0 for x in rows),'process metrics')
    transport=c['transport'];need(transport['grpc_out_messages']==sum(returned.values()),'grpc outbound message counter')
    need(transport['tcp_stream_write_bytes']>=transport['grpc_out_wire_bytes']>=len(attempts)*16384,'transport byte accounting')
    return {'verdict':'PASS','contract_revision':'A01','clock_uncertainty_ns':uncertainty,'counter_populations':{'N':n,'A':len(attempts),'F':len(set(attempts.values())),'S':sum(returned.values()),'R':len(server_attempts),'retries':len(attempts)-len(set(attempts.values())),'retry_scheduled':retry_count,'admitted':acquired,'worker_starts':len(starts),'worker_exits':len(exits)},'partition':counts,'queue_residence_ns':residence,'logical_admission_wait_ns':wait,'worker_occupied_ns':busy,'worker_elapsed_by_disposition':{str(code):sum(o['terminal']['worker_service_ns'] for o in by_id.values() if o['terminal']['outcome']==code) for code in range(1,7)},'client_high_water':cp,'server_high_water':peaks,'writer_local_progress_ns':s['writer_progress_ns'],'send_duration_ns':[e['send_duration_ns'] for e in ce if e['kind']=='grpc_send_return'],'process_metrics':{role:{'sampled_rss_peak_bytes':max(int(x['rss_bytes']) for x in rows),'last_observed_cpu_ns':int(rows[-1]['cpu_user_ns'])+int(rows[-1]['cpu_system_ns']),'cpu_resolution_ns':int(rows[-1]['cpu_tick_ns'])} for role,rows in d['metrics'].items()},'limitations':['RSS peaks are sampled lower bounds; CPU is /proc jiffy-quantized and final observation precedes exit.','Send and local writer elapsed include scheduling/serialization effects, not isolated HTTP/2 blocking.','Clock bound assumes shared host/time namespace and CLOCK_MONOTONIC; start/end bound does not prove arbitrary unobserved transients.','gRPC wire payload bytes exclude HTTP/2; plaintext TCP-stream counts include HTTP/2 but exclude packets/retransmissions.']}
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    try:result=verify(load(a.run))
    except (Invalid,KeyError,ValueError) as e:result={'verdict':'FAIL','error':str(e)}
    (a.run/'independent-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    if result['verdict']=='PASS':
        d=load(a.run)
        for role in ['server','client']:
            rows=d['metrics'][role];events=d[role+'_events']
            b=d['clock']['start'] if role=='server' else d['client']['client']['ClockStart']
            epoch=(b['epoch_min_ns']+b['epoch_max_ns'])//2 if role=='server' else (b['EpochMinNS']+b['EpochMaxNS'])//2
            with (a.run/(role+'-state.csv')).open('w') as f:
                writer=csv.writer(f);writer.writerow(['contract_revision','host_monotonic_ns','offset_ns','event_seq','queue_or_pending','running_or_outstanding','cumulative_worker_exits_or_sends','ledger_record_bytes_estimate'])
                for row in rows:
                    offset=int(row['host_monotonic_ns'])-epoch
                    prior=[e for e in events if (e['offset_ns'] if role=='server' else e['commit_offset_ns'])<=offset]
                    last=prior[-1] if prior else None
                    q=(last['queued'] if role=='server' else last['pending']) if last else 0
                    running=(last['running'] if role=='server' else last['outstanding']) if last else 0
                    count=sum(e['kind']==('worker_exit' if role=='server' else 'grpc_send_return') for e in prior)
                    estimate=d['server']['allocated_ledger_bytes'] if role=='server' else d['client']['client']['LedgerAllocatedBytes']
                    writer.writerow(['A01',row['host_monotonic_ns'],offset,last['seq'] if last else 0,q,running,count,estimate])
    print('Independent verifier:',result['verdict'],result.get('error',''))
    if result['verdict']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
