#!/usr/bin/env python3
"""Offline byte ownership, lifecycle, marker and histogram verification."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

def read(p):
    with p.open(newline='') as f:return list(csv.DictReader(f))
def verify(folder):
    m=json.loads((folder/'manifest.json').read_text());errors=[]
    if m.get('runner_error'):errors.append(m['runner_error'])
    if m.get('events'):errors+=m['events']
    if not m.get('source_hashes_unchanged'):errors.append('source changed')
    if m.get('server_exit')!=0:errors.append('server process exit')
    fault=m['expected_fault']
    if (m.get('client_exit')==0)!=(fault is None):errors.append('unexpected RPC outcome')
    clocks=m.get('clock',{})
    if not clocks or clocks['phase_alignment_error_ns']>100_000_000:errors.append('phase alignment >100ms or absent')
    if clocks and any(abs(clocks[r]['start_offset_ns'])>100_000_000 for r in ['server','client']):errors.append('marker release >100ms late')
    try:
        server=read(folder/'server/server.csv');client=read(folder/'client/client.csv');events=read(folder/'server/events.csv');sends=read(folder/'client/sends.csv')
        result=json.loads((folder/'client/summary.json').read_text());hist=json.loads((folder/'server/histograms.json').read_text())
    except (FileNotFoundError,ValueError) as e:return errors+[str(e)]
    if not server or not client:return errors+['empty metrics']
    for rows in [server,client]:
        times=[int(r['elapsed_ns']) for r in rows if r.get('started','1')=='1']
        if any(b-a>500_000_000 or b<a for a,b in zip(times,times[1:])):errors.append('sampling gap or nonmonotonic clock')
    for row in server:
        c={k:int(v) for k,v in row.items() if k not in ['service_phase','terminal_reason']}
        checks=[c['Q']==c['physical_queue_depth']==c['admitted']-c['dequeued']-c['discarded_from_queue'],c['W']==c['dequeued']-c['processed']-c['discarded_from_worker'],0<=c['Q']<=32,0<=c['R']<=1,0<=c['W']<=1,c['Q']+c['R']<=32,c['received']==c['admitted']+c['received_not_admitted'],c['admitted']==c['processed']+c['discarded']+c['Q']+c['W'],c['discarded']==c['discarded_from_queue']+c['discarded_from_worker'],c['reservations_acquired']==c['admitted']+c['reservations_released']+c['R'],c['queued_payload_bytes']==c['admitted_bytes']-c['dequeued_bytes']-c['discarded_queue_bytes'],c['worker_payload_bytes']==c['dequeued_bytes']-c['processed_bytes']-c['discarded_worker_bytes'],c['queue_residence_violations']==0,c['telemetry_errors']==0]
        if not all(checks):errors.append('server sample invariant');break
    for row in client:
        c={k:int(v) for k,v in row.items()}
        if c['scheduled']!=c['skipped']+c['attempted'] or c['attempted']!=c['successful_sends']+c['failed_sends']+c['inflight']:errors.append('client sample balance');break
    last={k:int(v) for k,v in server[-1].items() if k not in ['service_phase','terminal_reason']}
    if any(last[k] for k in ['Q','R','W','queued_payload_bytes','handler_payload_bytes','worker_payload_bytes','active_streams']):errors.append('terminal ownership not empty')
    if last['connections']!=1 or max(int(r['active_streams']) for r in server)!=1:errors.append('topology')
    if result['scheduled']!=result['skipped']+result['attempted'] or result['attempted']!=result['successful_sends']+result['failed_sends']:errors.append('final client balance')
    if len(sends)!=result['attempted'] or sum(r['outcome']=='success' for r in sends)!=result['successful_sends']:errors.append('Send event completeness')
    if sum(result['send_histogram_counts'])!=result['attempted']:errors.append('Send histogram completeness')
    if sum(sum(h) for h in hist['queue_counts'])!=last['dequeued'] or sum(sum(h) for h in hist['service_counts'])!=last['processed']:errors.append('server histogram completeness')
    dispositions=Counter()
    for e in events:
        if e['event'] in ['processed','discarded_queue','discarded_worker']:dispositions[e['sequence']]+=1
    admitted=[r['sequence'] for r in events if r['event']=='admitted']
    if len(admitted)!=last['admitted'] or any(dispositions[s]!=1 for s in admitted):errors.append('missing/double message disposition')
    if any(int(r['queue_residence_ns'])<0 for r in events):errors.append('negative residence')
    # Recompute exact per-message queue residence and fixed histogram bins from streamed events.
    bounds=hist['bounds_ns'];expected=[[0]*len(bounds) for _ in range(4)]
    import bisect
    for e in events:
        if e['event']=='dequeued':expected[int(e['enqueue_phase'])][bisect.bisect_left(bounds,int(e['queue_residence_ns']))]+=1
    if expected!=hist['queue_counts']:errors.append('histogram differs from exact streamed durations')
    expected_service=[[0]*len(bounds) for _ in range(4)]
    for e in events:
        if e['event']=='processed':expected_service[int(e['enqueue_phase'])][bisect.bisect_left(bounds,int(e['service_duration_ns']))]+=1
        if 'dequeue_ns' in e and e['event'] in ['dequeued','processed','discarded_worker']:
            if int(e['dequeue_ns'])-int(e['enqueue_ns'])!=int(e['queue_residence_ns']):errors.append('queue timestamps disagree')
        if 'completion_ns' in e and e['event']=='processed':
            if int(e['completion_ns'])-int(e['dequeue_ns'])!=int(e['service_duration_ns']):errors.append('service timestamps disagree')
    if expected_service!=hist['service_counts']:errors.append('service histogram differs from exact streamed durations')
    if fault is None:
        if not(last['admitted']==last['dequeued']==last['processed']==result['summary']['accepted']==result['summary']['processed']):errors.append('normal Summary/drain')
        if last['discarded'] or last['errors']:errors.append('normal error/discard')
        if result['scheduled']!=result['planned_slots']:errors.append('normal schedule incomplete')
        if result['rpc_error']!='<nil>':errors.append('normal RPC error')
    else:
        if not last['errors'] or result['rpc_error']=='<nil>':errors.append('fault not recorded')
        if fault in ['worker_error','worker_panic'] and server[-1]['terminal_reason']!=fault:errors.append('worker fault reason')
    return sorted(set(errors))

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();failures=[]
    for manifest in sorted(a.directory.glob('*/manifest.json')):
        issues=verify(manifest.parent);print(manifest.parent.name,'PASS' if not issues else issues)
        if issues:failures.append((manifest.parent.name,issues))
    if failures:raise SystemExit(1)
if __name__=='__main__':main()
