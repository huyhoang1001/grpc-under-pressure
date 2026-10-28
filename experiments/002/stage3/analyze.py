#!/usr/bin/env python3
"""Offline exploratory observations, never a primary policy conclusion."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'experiments/002'
sys.path.insert(0,str(BASE))
from stage2.analyze import one,read,quantile

def pooled(folder):
    events=read(folder/'server/events.csv')
    values=[int(e['queue_residence_ns']) for e in events if e['event']=='dequeued' and 12_000_000_000<=int(e['enqueue_ns'])<36_000_000_000]
    return {'count':len(values),'p50_ms':quantile(values,.50)/1e6,'p95_ms':quantile(values,.95)/1e6,'p99_ms':quantile(values,.99)/1e6}

def analyze(root):
    records=[]
    for p in sorted(root.glob('*/manifest.json')):
        m=json.loads(p.read_text());assert m['valid_for_declared_purpose'],(p,m['validation_issues'])
        if m['expected_fault']:
            c=json.loads((p.parent/'client/summary.json').read_text());s=read(p.parent/'server/server.csv')[-1]
            records.append({'name':m['name'],'purpose':m['purpose'],'policy':m['policy'],'expected_fault':m['expected_fault'],'valid_for_declared_purpose':True,'successful_sends':c['successful_sends'],'failed_sends':c['failed_sends'],'admitted':int(s['admitted']),'processed':int(s['processed']),'discarded':int(s['discarded'])})
            continue
        r=one(p.parent)
        r.update(policy=m['policy'],server_source_commit=m['server_source_commit'],accepted_stage2_binary=m['accepted_stage2_binary'])
        # Stage2's operational transition predicate required Q=32. That is not a Stage3 B=8 criterion.
        r.pop('intended_capacity_transition_observed',None);r.pop('failure_notice',None)
        if m['purpose']=='single_exploratory_fixed8':
            r['pooled_residence_12_36']=pooled(p.parent)
            r['budget_enforced']=r['Qmax']<=8
        records.append(r)
    result={'runs':records,'scope':'static-budget acceptance/overhead and at most one fixed8 exploratory run; no primary comparison'}
    controls=[r for r in records if r['purpose']=='stage2_baseline_overhead_control']
    if controls:
        result['overhead']={}
        for baseline in [True,False]:
            group=[r for r in controls if r['accepted_stage2_binary']==baseline]
            result['overhead']['accepted_stage2' if baseline else 'stage3_fixed32']={key:{'median':statistics.median(r[key] for r in group),'min':min(r[key] for r in group),'max':max(r[key] for r in group)} for key in ['service_mean_ms','service_p95_upper_ms','timed_event_io_fraction','event_format_write_ms','event_flush_ms','rpc_s','worker_observed_s']}
        result['overhead_caveat']='Two healthy 4s controls per executable in ABBA order, identical client bytes, build mode/config/affinity and 80/s workload. This checks gross regressions, not equivalence proof or saturated-capacity overhead. Direct event timers omit some telemetry/locking costs and include descheduling; ranges are not confidence intervals.'
    exploratory=[r for r in records if r['purpose']=='single_exploratory_fixed8']
    if exploratory:
        r=exploratory[0];old_folder=BASE/'results/stage2/exploratory-1';old=one(old_folder)
        result['comparison']={'accepted_stage2_fixed32':old,'accepted_stage2_pooled_residence_12_36':pooled(old_folder),'stage3_fixed8':r,'caveat':'One historical fixed32 and one new fixed8 run; shared gate healthy-load overhead checked separately, but source version/time/host noise and admitted cohorts are confounded. Skips are outcomes, not exclusions; local residence is not end-to-end latency.'}
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(4,1,figsize=(11,11),sharex=True)
        for folder,label,color in [(old_folder,'accepted Stage2 fixed32','tab:blue'),(root/r['name'],'Stage3 fixed8','tab:orange')]:
            server=[s for s in read(folder/'server/server.csv') if s['started']=='1'];client=read(folder/'client/client.csv');events=read(folder/'server/events.csv')
            axes[0].plot([int(s['elapsed_ns'])/1e9 for s in server],[int(s['Q']) for s in server],label=label,color=color)
            dq=[s for s in events if s['event']=='dequeued']
            axes[1].plot([int(s['enqueue_ns'])/1e9 for s in dq],[int(s['queue_residence_ns'])/1e6 for s in dq],'.',markersize=2,color=color,label=label)
            stride=5
            axes[2].plot([int(b['elapsed_ns'])/1e9 for a,b in zip(server,server[stride:])],[(int(b['processed'])-int(a['processed']))/((int(b['elapsed_ns'])-int(a['elapsed_ns']))/1e9) for a,b in zip(server,server[stride:])],label=label,color=color)
            axes[3].plot([int(s['elapsed_ns'])/1e9 for s in client],[int(s['skipped']) for s in client],label=label,color=color)
        for ax in axes:
            ax.axvspan(12,24,alpha=.1,color='grey');ax.grid(alpha=.2);ax.legend(fontsize=8)
            for boundary in [12,24,36]:ax.axvline(boundary,linestyle='--',color='grey',alpha=.5)
        for ax,title in zip(axes,['Physical Q (K=32 both)','Queue residence ms\nby enqueue time','Worker completions/s','Skipped slots']):ax.set_ylabel(title)
        axes[-1].set_xlabel('Local seconds from aligned workload marker')
        fig.suptitle('Exploratory only: historical fixed32 vs one static fixed8 run; no primary conclusion')
        fig.tight_layout();fig.savefig(root/'exploratory-comparison.png',dpi=150);fig.savefig(root/'exploratory-comparison.svg')
    (root/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result.get('overhead',{}),indent=2))
    if exploratory:print(json.dumps({'comparison':result['comparison']['stage3_fixed8']['pooled_residence_12_36']},indent=2))

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();analyze(a.directory)
if __name__=='__main__':main()
