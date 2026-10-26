#!/usr/bin/env python3
"""Analyze retained cumulative counters; no third-party dependencies."""
import argparse
import csv
import json
from pathlib import Path
import statistics

def load(path):
    with path.open() as f:return [{k:float(v) for k,v in r.items()} for r in csv.DictReader(f)]
def slope(rows, key):
    if len(rows)<2:raise ValueError('insufficient steady-state samples')
    ts=[r['elapsed_s'] for r in rows]; ys=[r[key] for r in rows]
    x=statistics.mean(ts);y=statistics.mean(ys)
    return sum((a-x)*(b-y) for a,b in zip(ts,ys))/sum((a-x)**2 for a in ts)
def load_process(path):
    with path.open() as f:return list(csv.DictReader(f))

def analyze(folder):
    manifest=json.loads((folder/'manifest.json').read_text())
    client=json.loads((folder/'client.json').read_text())
    server=load(folder/'server.csv');sender=load(folder/'client.csv')
    final=server[-1]
    # 0.4s pre-traffic idle + <=0.02s server readiness polling; avoid boundaries.
    steady=[r for r in server if 2.5<=r['elapsed_s']<=10.5]
    client_steady=[r for r in sender if 2<=r['elapsed_s']<=10]
    errors=[]
    if manifest.get('excluded'):errors.append(manifest['excluded'])
    if manifest.get('client_exit')!=0 or manifest.get('server_exit')!=0:errors.append('process exit')
    if int(final['received'])!=int(final['processed']):errors.append('final loss')
    if final['queue_depth']!=0 or final['worker_bytes']!=0 or final['handler_bytes']!=0:errors.append('not drained')
    for r in server:
        if r['errors']!=0:errors.append('stream error');break
        if r['queue_depth']!=r['enqueued']-r['dequeued']:errors.append('queue accounting');break
        if r['queue_bytes']!=r['queue_depth']*manifest['payload']:errors.append('queue byte accounting');break
        if r['received']!=r['processed']+r['queue_depth']+(r['worker_bytes']/manifest['payload'])+(r['handler_bytes']/manifest['payload']):errors.append('ownership accounting');break
    if max(r['connections_accepted'] for r in server)!=1:errors.append('connection count')
    if max(r['active_streams'] for r in server)>1:errors.append('stream count')
    if manifest['variant']=='bounded' and max(r['queue_depth'] for r in server)>manifest['capacity']:errors.append('capacity')
    if max(r['queue_bytes'] for r in server)>manifest['queue_limit'] or max(r['rss_bytes'] for r in server)>manifest['server_rss_limit']:errors.append('safety threshold')
    result={'name':folder.name,'variant':manifest['variant'],'valid':not errors,'invalid_reasons':errors,'completed_sends':client['completed_sends'],'send_rate_total':client['completed_sends']/client['send_seconds'],'send_p95_ms':client['send_p95_ms'],'send_p99_ms':client['send_p99_ms'],'blocked_fraction':client['send_blocked_gt20ms']/client['attempts'],'send_total_seconds':client['send_total_ns']/1e9,'skipped_slots':client['skipped_slots'],'max_queue_depth':max(r['queue_depth'] for r in server),'max_queue_bytes':max(r['queue_bytes'] for r in server),'peak_rss_bytes':max(r['rss_bytes'] for r in server),'idle_rss_bytes':server[0]['rss_bytes'],'post_drain_rss_bytes':final['rss_bytes'],'worker_capacity':final['processed']/(final['service_ns']/1e9),'final_received':int(final['received']),'final_processed':int(final['processed'])}
    process=load_process(folder/'process.csv')
    for role in ['server','client']:
        samples=[r for r in process if r['role']==role]
        if len(samples)>1:
            a,b=samples[0],samples[-1]
            cpu=((float(b['utime_ticks'])+float(b['stime_ticks']))-(float(a['utime_ticks'])+float(a['stime_ticks'])))/float(b['clock_ticks_per_second'])
            result[role+'_cpu_seconds']=cpu
            result[role+'_cpu_fraction']=cpu/(float(b['elapsed_s'])-float(a['elapsed_s']))
            result[role+'_peak_rss_bytes']=max(int(r['rss_bytes']) for r in samples)
    if manifest['name'].startswith('overload'):
        result.update(queue_slope_msg_s=slope(steady,'queue_depth'),queue_slope_bytes_s=slope(steady,'queue_bytes'),rss_slope_bytes_s=slope(steady,'rss_bytes'),enqueue_rate=slope(steady,'enqueued'),dequeue_rate=slope(steady,'dequeued'),processed_rate=slope(steady,'processed'),steady_send_rate=slope(client_steady,'completed'))
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
    results=[]
    for folder in sorted(args.directory.iterdir()):
        if folder.is_dir() and (folder/'client.json').exists() and 'client_exit' in json.loads((folder/'manifest.json').read_text()):results.append(analyze(folder))
    summary={}
    for variant in ['direct','unbounded','bounded']:
        runs=[r for r in results if r['name'].startswith('overload') and r['variant']==variant]
        if not runs:continue
        summary[variant]={'runs':len(runs),'valid_runs':sum(r['valid'] for r in runs)}
        runs=[r for r in runs if r['valid']]
        if not runs:continue
        for key in ['queue_slope_msg_s','queue_slope_bytes_s','max_queue_depth','max_queue_bytes','peak_rss_bytes','post_drain_rss_bytes','steady_send_rate','processed_rate','send_p95_ms','send_p99_ms','blocked_fraction','send_total_seconds','rss_slope_bytes_s']:
            vals=[r[key] for r in runs];summary[variant][key]={'median':statistics.median(vals),'min':min(vals),'max':max(vals)}
    output={'sample_windows':{'server_s':[2.5,10.5],'client_s':[2,10]},'runs':results,'summary':summary}
    (args.directory/'analysis.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    failures=[r for r in results if not r['valid'] and not json.loads((args.directory/r['name']/'manifest.json').read_text()).get('excluded')]
    if failures:raise SystemExit('invalid runs: '+str([(r['name'],r['invalid_reasons']) for r in failures]))
if __name__=='__main__':main()
