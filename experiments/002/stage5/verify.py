#!/usr/bin/env python3
"""Independent primary provenance checks plus accepted event/controller replay."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'experiments/002'))
from stage4.verify import validate as replay
from verify import read


def validate(folder):
    issues=replay(folder)
    frozen_path=folder.parent/'FROZEN.json';frozen=json.loads(frozen_path.read_text());m=json.loads((folder/'manifest.json').read_text())
    if hashlib.sha256(frozen_path.read_bytes()).hexdigest()!=m['freeze_sha256']:issues.append('freeze digest changed')
    if m['frozen_checks_before'] or m['frozen_checks_after']:issues.append('frozen checks failed')
    if m['server_source_sha256']!={k:v for k,v in frozen['application_source_sha256'].items() if k.startswith(('server/','proto/','experiments/002/server/')) or k=='rust-toolchain.toml'}:issues.append('server source pin')
    if m['binary_sha256']!=frozen['binary_sha256']:issues.append('binary hash mismatch')
    for key,value in frozen['configuration'].items():
        if m[key]!=value:issues.append('configuration drift '+key)
    if m['primary_run'] is not True or m['expected_fault'] is not None or m['purpose']!='primary_controlled_comparison':issues.append('primary purpose/fault flags')
    if m['initial_budget']!=frozen['policy_initial_budgets'][m['policy']]:issues.append('initial budget')
    matches=[row for row in frozen['order'] if row['name']==m['name']]
    if len(matches)!=1 or any(m[k]!=matches[0][k] for k in ['block','position','policy']):issues.append('order/block mismatch')
    for row in read(folder/'server/events.csv'):
        if row['event']=='admitted' and int(row['payload_bytes'])!=16384:issues.append('payload mismatch')
    summary=json.loads((folder/'client/summary.json').read_text());last=read(folder/'server/server.csv')[-1]
    if not(summary['successful_sends']==int(last['received'])==int(last['admitted'])==int(last['processed'])):issues.append('completed sends/server totals mismatch')
    if any(summary[k]!=v for k,v in [('scheduled',2880),('planned_slots',2880),('payload_bytes',16384),('seed',1),('rate',80),('offered_seconds',36)]):issues.append('client workload mismatch')
    return sorted(set(issues))


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();result={}
    for path in sorted(a.directory.glob('b*/manifest.json')):
        try:problems=validate(path.parent)
        except Exception as error:problems=['verification exception '+repr(error)]
        result[path.parent.name]=problems;print(path.parent.name,'PASS' if not problems else problems)
    (a.directory/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    if any(result.values()):raise SystemExit(1)
if __name__=='__main__':main()
