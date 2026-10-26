#!/usr/bin/env python3
"""Read-only audit of existing evidence. Never launches workloads or rewrites results."""
import csv
import hashlib
import json
from pathlib import Path
import statistics

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]

def rows(path):
    with path.open(newline='') as f:
        return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]

def slope(data, key):
    x = statistics.mean(r['elapsed_s'] for r in data)
    y = statistics.mean(r[key] for r in data)
    return sum((r['elapsed_s']-x)*(r[key]-y) for r in data)/sum((r['elapsed_s']-x)**2 for r in data)

def main():
    stored = json.loads((BASE/'results/e1/analysis.json').read_text())
    analyses = {r['name']:r for r in stored['runs']}
    inventory = []
    for path in sorted((BASE/'results').rglob('manifest.json')):
        m = json.loads(path.read_text())
        folder = path.parent
        errors = []
        required = ['manifest.json','server.csv','client.csv','client.json','process.csv','server.log','client.log']
        for name in required:
            if not (folder/name).is_file(): errors.append('missing '+name)
        if errors:
            inventory.append({'run':folder.name,'errors':errors});continue
        s = rows(folder/'server.csv');c = rows(folder/'client.csv')
        with (folder/'process.csv').open(newline='') as f: process = list(csv.DictReader(f))
        result = json.loads((folder/'client.json').read_text())
        if not s or not c or not process: errors.append('empty samples')
        for key in ['server_command','client_command','source_sha256','binary_sha256','windows','payload','capacity','queue_limit','server_rss_limit','started_utc']:
            if key not in m:errors.append('missing workload/provenance field '+key)
        for key in ['send_total_ns','send_blocked_gt20ms','send_p50_ms','send_p95_ms','send_p99_ms','skipped_slots','send_seconds']:
            if key not in result:errors.append('missing producer timing field '+key)
        if c[-1]['send_ns'] != result['send_total_ns'] or c[-1]['blocked_gt20ms'] != result['send_blocked_gt20ms']:errors.append('client timing counter mismatch')
        if not {'server','client'}.issubset({r['role'] for r in process}):errors.append('missing process role')
        if m.get('client_exit') != 0 or m.get('server_exit') != 0: errors.append('nonzero/missing exit')
        if result['send_error'] != '<nil>' or result['rpc_error'] != '<nil>':errors.append('RPC/send error')
        if not (int(s[-1]['received']) == int(s[-1]['processed']) == result['completed_sends'] == result['summary']['accepted'] == result['summary']['processed']):errors.append('final message counts')
        for r in s:
            if r['queue_depth'] != r['enqueued']-r['dequeued']:errors.append('queue accounting');break
            if r['queue_bytes'] != r['queue_depth']*m['payload']:errors.append('queue bytes');break
            if r['received'] != r['processed']+r['queue_depth']+(r['worker_bytes']+r['handler_bytes'])/m['payload']:errors.append('ownership accounting');break
        if s[-1]['queue_bytes'] or s[-1]['worker_bytes'] or s[-1]['handler_bytes']:errors.append('incomplete drain')
        if max(r['connections_accepted'] for r in s) != 1 or max(r['active_streams'] for r in s) != 1:errors.append('topology')
        if any(r['errors'] for r in s):errors.append('stream error')
        if m['variant']=='bounded' and max(r['queue_depth'] for r in s)>m['capacity']:errors.append('bounded capacity')
        if max(r['queue_bytes'] for r in s)>m['queue_limit'] or max(r['rss_bytes'] for r in s)>m['server_rss_limit']:errors.append('safety limit')
        source_matches = {}
        for key,digest in m['source_sha256'].items():
            p=ROOT/key
            if folder.parent.name=='e1' and key=='server/src/main.rs':p=BASE/'results/e1/source/server-main.rs'
            if folder.parent.name=='e1' and key=='loadgen/cmd/loadgen/main.go':p=BASE/'results/e1/source/loadgen-main.go'
            source_matches[key]=p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==digest
        if not all(source_matches.values()) and not m.get('excluded'):errors.append('source snapshot hash')
        checked_slopes={}
        if folder.name.startswith('overload'):
            steady=[r for r in s if 2.5<=r['elapsed_s']<=10.5]
            sender=[r for r in c if 2<=r['elapsed_s']<=10]
            for key,column,data in [('queue_slope_msg_s','queue_depth',steady),('processed_rate','processed',steady),('steady_send_rate','completed',sender)]:
                value=slope(data,column);checked_slopes[key]=value
                if abs(value-analyses[folder.name][key])>1e-8:errors.append('stored analysis mismatch '+key)
        inventory.append({'run':folder.name,'path':str(folder.relative_to(BASE)),'variant':m['variant'],'offered_rate':m['rate'],'offered_seconds':m['seconds'],'service_ms':m['service_ms'],'sample_counts':{'server':len(s),'client':len(c),'process':len(process)},'excluded':m.get('excluded'),'source_hash_matches':source_matches,'execution_git_sha_recorded':any(k in m for k in ['git_sha','git_commit','commit_sha']),'checked_slopes':checked_slopes,'errors':errors})
    included={v:sum(r['run'].startswith('overload') and r['variant']==v and not r['excluded'] and not r['errors'] for r in inventory) for v in ['direct','unbounded','bounded']}
    audit={'scope':'Existing files only; no benchmarks, builds, or test suites executed','runs_found':len(inventory),'included_overload_counts':included,'runs':inventory}
    print(json.dumps(audit,indent=2))
    if any(r['errors'] for r in inventory) or included!={'direct':5,'unbounded':5,'bounded':5}:raise SystemExit(1)

if __name__=='__main__':main()
