#!/usr/bin/env python3
"""Offline independent controller replay and event-ordered gate/accounting audit."""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'experiments/002'))
from stage2.run import validate as original_validate
from verify import read


def validate(folder):
    issues=original_validate(folder)
    m=json.loads((folder/'manifest.json').read_text())
    server=read(folder/'server/server.csv'); events=read(folder/'server/events.csv')
    ticks=read(folder/'server/controller.csv')
    adaptive=m['policy']=='adaptive'; initial=m['initial_budget']
    for row in server:
        q,r,b,carry=[int(row[k]) for k in ['Q','R','B','shrink_occupancy']]
        if not (1<=b<=32 and q+r<=max(b,carry)<=32):issues.append('shrink-safe sample bound')
        if not adaptive and (b!=initial or carry):issues.append('fixed policy changed')
        if int(row['physical_capacity'])!=32 or int(row['physical_available_capacity'])+q+r!=32:issues.append('physical slot accounting')
        if int(row['logical_pending'])!=q+r:issues.append('pending gauge')
        if bool(int(row['adaptive_policy']))!=adaptive:issues.append('policy gauge')
    if int(server[-1]['controller_running']):issues.append('controller not stopped')
    if int(server[-1]['controller_ticks'])!=len(ticks):issues.append('tick log incomplete')
    # Merge state-lock transactions. Event timestamps are captured while holding the same lock.
    timeline=[(int(e['observed_elapsed_ns']),0,e) for e in events]
    timeline += [(int(t['observed_ns']),1,t) for t in ticks]
    q=r=w=carry=0;b=initial;terminal=False;eof=False
    processed=total_service=last_n=last_sum=0
    high=low=0;ewma=None;last_observed=0;updates=0
    for stamp,kind,row in sorted(timeline,key=lambda x:(x[0],x[1])):
        if kind==0:
            event=row['event']
            if event=='reservation_acquired':
                if q+r>=b or terminal or eof:issues.append('acquisition outside O<B/pre-EOF')
                r+=1
            elif event=='reservation_released':r-=1
            elif event=='admitted':q+=1;r-=1
            elif event=='dequeued':q-=1;w+=1
            elif event=='processed':w-=1;processed+=1;total_service+=int(row['service_duration_ns'])
            elif event=='discarded_queue':q-=1
            elif event=='discarded_worker':w-=1
            elif event=='terminal':terminal=True
            elif event=='eof':eof=True
            if not (0<=q<=32 and 0<=r<=1 and 0<=w<=1 and q+r<=max(b,carry)<=32):issues.append('event occupancy')
            continue
        t=row
        if terminal or eof:issues.append('tick after terminal/EOF')
        if [q,r,w,b]!=[int(t[k]) for k in ['Q','R','W','B_before']]:issues.append('tick/event state disagreement')
        i=ticks.index(t)+1
        if int(t['scheduled_ns'])!=i*500_000_000 or not 0<=int(t['lateness_ns'])<=100_000_000:issues.append('tick cadence/jitter invalid')
        if int(t['window_start_ns'])!=last_observed or int(t['observed_ns'])-int(t['scheduled_ns'])!=int(t['lateness_ns']):issues.append('feedback window timing')
        n=processed-last_n;service=total_service-last_sum
        if n!=int(t['interval_completions']) or service!=int(t['interval_service_ns']):issues.append('feedback differs from completed events')
        if processed!=int(t['total_completions']) or total_service!=int(t['total_service_ns']):issues.append('feedback cumulative totals')
        if (high,low)!=(int(t['high_before']),int(t['low_before'])):issues.append('input streak trace')
        mean=service/n/1e6 if n else None
        near=q+r>=b-1;proposed=b;reason='insufficient_feedback'
        if n<5:high=low=0
        else:
            ewma=mean if ewma is None else .2*mean+.8*ewma
            delay=q*ewma
            high=high+1 if delay>125 else 0
            low=low+1 if delay<75 and near else 0
            reason='hold'
            if high>=2:proposed=max(1,math.ceil(b/2));reason='decrease';high=low=0
            elif low>=2:proposed=min(32,b+1);reason='increase';high=low=0
        for key,expected in [('interval_mean_ms',mean),('ewma_ms',ewma),('estimated_delay_ms',None if ewma is None else q*ewma)]:
            if expected is None:
                if t[key]!='':issues.append('unexpected '+key)
            elif not t[key] or not math.isclose(float(t[key]),expected,rel_tol=1e-10,abs_tol=1e-8):issues.append('incorrect '+key)
        if (high,low,near,proposed,reason)!=(int(t['high_after']),int(t['low_after']),bool(int(t['near_full'])),int(t['B_proposed']),t['proposal_reason']):issues.append('frozen decision mismatch')
        if t['decision_reason']!=(reason if adaptive else 'fixed_policy_hold'):issues.append('policy decision reason')
        after=proposed if adaptive else b
        if after!=b:
            updates+=1
            if after<b:carry=q+r
        b=after
        if (b,carry)!=(int(t['B_after']),int(t['shrink_occupancy'])):issues.append('update/carryover trace')
        last_n=processed;last_sum=total_service;last_observed=stamp
    if any([q,r,w]):issues.append('event terminal ownership nonzero')
    if updates!=int(server[-1]['budget_updates']):issues.append('update count')
    if m['expected_fault']=='cancellation':
        if not any(int(t['B_after'])<int(t['B_before']) and int(t['Q'])+int(t['R'])>int(t['B_after']) for t in ticks):issues.append('cancel fixture did not exercise live shrink')
    if m['purpose']=='integration_fixture' and m['expected_fault'] is None:
        if len(ticks)<3:issues.append('too few acceptance ticks')
        if int(server[-1]['budget_updates']):issues.append('healthy workload budget unexpectedly changed')
        client=json.loads((folder/'client/summary.json').read_text())
        if client['skipped']:issues.append('healthy acceptance skipped slots')
    return sorted(set(issues))


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
    results={}
    for manifest in sorted(a.directory.glob('*/manifest.json')):
        problems=validate(manifest.parent);results[manifest.parent.name]=problems
        print(manifest.parent.name,'PASS' if not problems else problems)
    (a.directory/'verification.json').write_text(json.dumps(results,indent=2)+'\n')
    if any(results.values()):raise SystemExit(1)
if __name__=='__main__':main()
