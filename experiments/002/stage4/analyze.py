#!/usr/bin/env python3
"""Descriptive Stage4 audit/analysis; no primary or end-to-end inference."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3];BASE=ROOT/'experiments/002'
sys.path.insert(0,str(BASE))
from stage2.analyze import one, read, quantile
from stage3.analyze import pooled
from stage4.verify import validate


def recovery_screen(folder):
    events=read(folder/'server/events.csv')
    dq=[e for e in events if e['event']=='dequeued'];done=[e for e in events if e['event']=='processed']
    healthy=[int(e['queue_residence_ns']) for e in dq if 0<=int(e['enqueue_ns'])<12e9]
    baseline=quantile(healthy,.95);rate=sum(0<=int(e['completion_ns'])<12e9 for e in done)/12
    candidates=[]
    for step in range(46):
        start=24_000_000_000+step*200_000_000;end=start+3_000_000_000
        values=[int(e['queue_residence_ns']) for e in dq if start<=int(e['enqueue_ns'])<end]
        p95=quantile(values,.95);observed=sum(start<=int(e['completion_ns'])<end for e in done)/3
        candidates.append({'start_s':start/1e9,'confirmation_end_s':end/1e9,'cohort_messages':len(values),'queue_p95_ms':p95/1e6 if p95 is not None else None,'completions_per_s':observed,'passes_window_screen':bool(len(values)>=5 and p95<=baseline and observed>=.95*rate)})
    first=next((row for row in candidates if row['passes_window_screen']),None)
    return {'method':'exploratory 200ms-grid 3s enqueue-cohort window; not proof of continuous instantaneous recovery or primary H4','healthy_p95_ms':baseline/1e6,'healthy_completion_rate_s':rate,'first_passing_window':first,'status':'window observed' if first else 'censored: no passing window by36s','windows':candidates}


def summarize(folder):
    m=json.loads((folder/'manifest.json').read_text());ticks=read(folder/'server/controller.csv');server=read(folder/'server/server.csv');last=server[-1]
    if m['expected_fault']:
        client=json.loads((folder/'client/summary.json').read_text())
        r={'name':m['name'],'purpose':m['purpose'],'expected_fault':m['expected_fault'],'admitted':int(last['admitted']),'processed':int(last['processed']),'discarded':int(last['discarded']),'rpc_status':client['rpc_error'],'failed_sends':client['failed_sends']}
    else:
        r=one(folder);r.pop('intended_capacity_transition_observed',None);r.pop('failure_notice',None)
    changes=[t for t in ticks if t['B_before']!=t['B_after']]
    r.update(policy=m['policy'],controller_ticks=len(ticks),budget_updates=len(changes),budget_trajectory=changes,final_budget=int(last['B']),max_tick_lateness_ms=max((int(t['lateness_ns'])/1e6 for t in ticks),default=None),controller_io_ms=int(last['controller_io_ns'])/1e6)
    if m['purpose']=='single_exploratory_adaptive':
        r['pooled_residence_12_36']=pooled(folder);r['recovery_window_screen']=recovery_screen(folder)
        r['budget_direction_reversals']=sum((int(a['B_after'])>int(a['B_before']))!=(int(b['B_after'])>int(b['B_before'])) for a,b in zip(changes,changes[1:]))
    return r


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();root=a.directory
    cases=[]
    for path in sorted(root.glob('*/manifest.json')):
        issues=validate(path.parent);assert not issues,(path,issues)
        cases.append(summarize(path.parent))
    result={'scope':'Stage4 correctness and at most one exploratory adaptive run, not primary comparison','runs':cases}
    exploratory=[r for r in cases if r['purpose']=='single_exploratory_adaptive']
    if exploratory:
        adaptive=exploratory[0];comparison={}
        folders=[(BASE/'results/stage2/exploratory-1','fixed32'),(BASE/'results/stage3/exploratory-fixed8','fixed8'),(root/adaptive['name'],'adaptive')]
        for folder,label in folders:
            r=one(folder);r.pop('intended_capacity_transition_observed',None);r.pop('failure_notice',None)
            r['pooled_residence_12_36']=pooled(folder);r['recovery_window_screen']=recovery_screen(folder)
            comparison[label]=r
        result['comparison']=comparison
        result['caveat']='Three single runs at separate times/source versions, different admitted cohorts; no repeated primary comparison, uncertainty estimate, isolated transport stall or end-to-end claim.'
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(5,1,figsize=(12,13),sharex=True)
        for folder,label in folders:
            s=[v for v in read(folder/'server/server.csv') if v['started']=='1'];t=[int(v['elapsed_ns'])/1e9 for v in s]
            ev=read(folder/'server/events.csv');dq=[v for v in ev if v['event']=='dequeued'];c=read(folder/'client/client.csv')
            axes[0].plot(t,[int(v['B']) for v in s],label=label)
            axes[1].plot(t,[int(v['Q']) for v in s],label=label)
            axes[2].plot([int(v['enqueue_ns'])/1e9 for v in dq],[int(v['queue_residence_ns'])/1e6 for v in dq],'.',markersize=2,label=label)
            stride=5
            axes[3].plot([int(b['elapsed_ns'])/1e9 for b in s[stride:]],[(int(b['processed'])-int(a['processed']))/((int(b['elapsed_ns'])-int(a['elapsed_ns']))/1e9) for a,b in zip(s,s[stride:])],label=label)
            axes[4].plot([int(v['elapsed_ns'])/1e9 for v in c],[int(v['skipped']) for v in c],label=label)
        for ax,title in zip(axes,['Logical B','Physical Q (K32)','Queue residence ms\nby enqueue time','Worker completions/s','Skipped slots']):
            ax.set_ylabel(title);ax.grid(alpha=.2);ax.legend(fontsize=8);ax.axvspan(12,24,color='grey',alpha=.1)
            for edge in [12,24,36]:ax.axvline(edge,color='grey',alpha=.4,linestyle='--')
        axes[-1].set_xlabel('Seconds from each aligned workload marker')
        fig.suptitle('Exploratory only: separate executions/source versions; no primary conclusion')
        fig.tight_layout();fig.savefig(root/'exploratory-comparison.png',dpi=140);fig.savefig(root/'exploratory-comparison.svg')
    else:
        assessment={'acceptance_passed':True,'cases':[r['name'] for r in cases],'note':'Verified fixtures and tick/gate replay before one exploration; no performance conclusion.'}
        assert len(cases)==7
        (root/'acceptance-assessment.json').write_text(json.dumps(assessment,indent=2)+'\n')
    (root/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Validated',len(cases),'cases; exploratory',len(exploratory))
    if exploratory:print(json.dumps({k:adaptive[k] for k in ['final_budget','controller_ticks','budget_updates','pooled_residence_12_36','budget_direction_reversals']},indent=2))
if __name__=='__main__':main()
