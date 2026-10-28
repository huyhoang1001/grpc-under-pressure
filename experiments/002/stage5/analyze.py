#!/usr/bin/env python3
"""Frozen primary endpoint analysis. Offline only; runs/blocks are uncertainty units."""
import argparse
from collections import Counter
import csv
from functools import lru_cache
import itertools
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[3];BASE=ROOT/'experiments/002'
sys.path.insert(0,str(BASE))
from stage2.analyze import one,read,quantile,stats
from stage5.verify import validate
POLICIES=['fixed32','fixed8','adaptive']


def cohort(events,start,end):
    return [int(e['queue_residence_ns']) for e in events if e['event']=='dequeued' and start<=int(e['enqueue_ns'])<end]


def recovery(events):
    healthy=cohort(events,0,12_000_000_000);limit=quantile(healthy,.95)
    done=[int(e['completion_ns']) for e in events if e['event']=='processed']
    healthy_rate=sum(0<=t<12_000_000_000 for t in done)/12
    windows=[]
    for step in range(46):
        start=24_000_000_000+step*200_000_000;end=start+3_000_000_000
        values=cohort(events,start,end);completed=sum(start<=t<end for t in done)
        p95=quantile(values,.95)
        okay=bool(len(values)>=5 and completed>=5 and p95<=limit and completed/3>=.95*healthy_rate)
        windows.append({'start_s':start/1e9,'confirmation_s':end/1e9,'queue_count':len(values),'completion_count':completed,'p95_ms':p95/1e6 if p95 is not None else None,'completion_rate_s':completed/3,'qualifies':okay})
    first=next((w for w in windows if w['qualifies']),None)
    return {'healthy_p95_ms':limit/1e6,'healthy_completion_rate_s':healthy_rate,'start_delay_s':first['start_s']-24 if first else None,'confirmation_delay_s':first['confirmation_s']-24 if first else None,'right_censored':first is None,'censor_confirmation_delay_s':12 if first is None else None,'windows':windows}


def ownership(events,end_ns=36_000_000_000):
    transitions=[]
    for e in events:
        kind=e['event']
        if kind=='admitted':transitions.append((int(e['enqueue_ns']),1,0))
        elif kind=='dequeued':transitions.append((int(e['dequeue_ns']),-1,1))
        elif kind=='processed':transitions.append((int(e['completion_ns']),0,-1))
    q=w=0;last=0;busy=backlog=idle_backlog=0
    for stamp,dq,dw in sorted(transitions):
        if stamp>end_ns:break
        duration=stamp-last
        assert duration>=0
        busy+=duration*(w>0);backlog+=duration*(q>0);idle_backlog+=duration*(q>0 and w==0)
        q+=dq;w+=dw;last=stamp
        assert q>=0 and 0<=w<=1
    duration=end_ns-last
    busy+=duration*(w>0);backlog+=duration*(q>0);idle_backlog+=duration*(q>0 and w==0)
    return {'busy_s':busy/1e9,'idle_s':(end_ns-busy)/1e9,'utilization':busy/end_ns,'backlog_s':backlog/1e9,'idle_backlog_s':idle_backlog/1e9,'idle_backlog_fraction':idle_backlog/backlog if backlog else 0}


def summarize(folder):
    m=json.loads((folder/'manifest.json').read_text());r=one(folder)
    r.pop('intended_capacity_transition_observed',None);r.pop('failure_notice',None)
    events=read(folder/'server/events.csv');s=read(folder/'server/server.csv');last=s[-1];c=read(folder/'client/client.csv');sends=read(folder/'client/sends.csv');ticks=read(folder/'server/controller.csv')
    changes=[t for t in ticks if t['B_before']!=t['B_after']]
    r.update(block=m['block'],position=m['position'],policy=m['policy'],primary_run=True)
    r['queue_cohort_ns']=cohort(events,12_000_000_000,36_000_000_000)
    r['pooled_queue_ms']=stats(r['queue_cohort_ns'],1e-6)
    r['recovery']=recovery(events);r['offered_ownership']=ownership(events)
    full=ownership(events,int(last['worker_busy_ns'])+int(last['worker_idle_ns']))
    r['full_span_ownership']=full
    r['ownership_crosscheck_delta_ns']={'busy':round(full['busy_s']*1e9)-int(last['worker_busy_ns']),'idle_backlog':round(full['idle_backlog_s']*1e9)-int(last['worker_idle_backlog_ns'])}
    r['offered_completions']=sum(0<=int(e['completion_ns'])<36_000_000_000 for e in events if e['event']=='processed')
    r['offered_completion_rate_s']=r['offered_completions']/36
    r['send_ms_overall']=stats([int(e['send_duration_ns']) for e in sends],1e-6)
    client=json.loads((folder/'client/summary.json').read_text())
    r['send_excess_gt20ms_s']=client['send_excess_gt20ms_ns']/1e9
    r['peak_client_rss_mib']=max(int(v['rss_bytes']) for v in c)/2**20
    r['peak_payload_bytes']={key:max(int(v[key]) for v in s) for key in ['queued_payload_bytes','handler_payload_bytes','worker_payload_bytes']}
    r['final_accounting']={k:last[k] for k in ['received','admitted','dequeued','processed','discarded','received_not_admitted','reservations_acquired','reservations_released','Q','R','W','queued_payload_bytes','handler_payload_bytes','worker_payload_bytes','received_bytes','admitted_bytes','processed_bytes','active_streams','controller_running','physical_available_capacity','terminal_reason']}
    r['controller']={'tick_count':len(ticks),'update_count':len(changes),'updates':changes,'final_B':int(last['B']),'min_B':min([m['initial_budget']]+[int(t['B_after']) for t in ticks]),'max_B':max([m['initial_budget']]+[int(t['B_after']) for t in ticks]),'reversals':sum((int(a['B_after'])>int(a['B_before']))!=(int(b['B_after'])>int(b['B_before'])) for a,b in zip(changes,changes[1:])),'max_tick_lateness_ms':max((int(t['lateness_ns'])/1e6 for t in ticks),default=None),'timed_controller_io_ms':int(last['controller_io_ns'])/1e6}
    r['sample_gaps_ms']={}
    for role,rows in [('server',s),('client',c)]:
        times=[int(v['elapsed_ns']) for v in rows if v.get('started','1')=='1'];delta=[b-a for a,b in zip(times,times[1:])]
        r['sample_gaps_ms'][role]=stats(delta,1e-6)
    r['sampled_Q_mean']=statistics.mean(int(v['Q']) for v in s if v['started']=='1' and int(v['elapsed_ns'])<36e9)
    process=read(folder/'process.csv');r['process']={}
    for role in ['server','client']:
        rows=[v for v in process if v['role']==role];a,b=rows[0],rows[-1]
        cpu=(int(b['utime_ticks'])+int(b['stime_ticks'])-int(a['utime_ticks'])-int(a['stime_ticks']))/int(b['CLK_TCK'])
        wall=(int(b['monotonic_ns'])-int(a['monotonic_ns']))/1e9
        r['process'][role]={'cpu_s':cpu,'observed_wall_s':wall,'one_core_percent':100*cpu/wall,'peak_rss_mib':max(int(v['rss_bytes']) for v in rows)/2**20}
    return r


def describe(values):
    present=[v for v in values if v is not None]
    return {'values':values,'count':len(present),'censored_or_missing':len(values)-len(present),'median':statistics.median(present) if present else None,'mean':statistics.mean(present) if present else None,'min':min(present,default=None),'max':max(present,default=None)}


def metric(r,key):
    paths={'queue_p95':('pooled_queue_ms','p95'),'queue_p99':('pooled_queue_ms','p99'),'slow_p95':('phases','slowdown','queue_residence_ms_by_enqueue','p95'),'slow_p99':('phases','slowdown','queue_residence_ms_by_enqueue','p99'),'recovery_p95':('phases','recovery','queue_residence_ms_by_enqueue','p95'),'recovery_confirmation':('recovery','confirmation_delay_s'),'throughput':('offered_completion_rate_s',),'rpc':('rpc_s',),'idle_backlog_fraction':('offered_ownership','idle_backlog_fraction'),'skipped':('skipped',),'send_wall':('send_wall_duration_s',),'logical_wait':('logical_admission_wait_s',)}
    out=r
    for part in paths[key]:out=out[part]
    return out


def interval(values):return [quantile(values,.025),quantile(values,.975)]


def pooled_bootstrap(cohorts,counts):
    pairs=sorted((value,index) for index,values in enumerate(cohorts) for value in values)
    n=sum(len(values)*counts[i] for i,values in enumerate(cohorts));rank=math.ceil(.95*n);seen=0
    for value,index in pairs:
        seen+=counts[index]
        if seen>=rank:return value/1e6
    raise AssertionError('empty pooled bootstrap')


def comparisons(groups):
    results={};draws=list(itertools.product(range(5),repeat=5))
    for baseline in ['fixed32','fixed8']:
        a=groups['adaptive'];b=groups[baseline];out={'paired_blocks':[r['block'] for r in a]}
        cache={}
        for key in ['queue_p95','queue_p99','slow_p95','slow_p99','recovery_p95','throughput','rpc','idle_backlog_fraction','recovery_confirmation','skipped','send_wall','logical_wait']:
            av=[metric(r,key) for r in a];bv=[metric(r,key) for r in b]
            if any(v is None for v in av+bv):out[key]={'status':'censored, no complete-pair effect interval','adaptive':av,'baseline':bv};continue
            difference=[x-y for x,y in zip(av,bv)];ratios=[x/y if y else None for x,y in zip(av,bv)]
            diffs=[];rs=[]
            for indices in draws:
                aa=statistics.mean(av[i] for i in indices);bb=statistics.mean(bv[i] for i in indices)
                diffs.append(aa-bb)
                if bb:rs.append(aa/bb)
            mean_a=statistics.mean(av);mean_b=statistics.mean(bv)
            out[key]={'adaptive':av,'baseline':bv,'paired_differences':difference,'paired_ratios':ratios,'mean_difference':statistics.mean(difference),'difference_ci95':interval(diffs),'ratio_of_means':mean_a/mean_b if mean_b else None,'ratio_ci95':interval(rs) if rs else None,'pairs_lower':sum(x<y for x,y in zip(av,bv)),'pairs_higher':sum(x>y for x,y in zip(av,bv))}
        pooled_a=[r['queue_cohort_ns'] for r in a];pooled_b=[r['queue_cohort_ns'] for r in b]
        reductions=[]
        for indices in draws:
            counts=tuple(Counter(indices).get(i,0) for i in range(5))
            if counts not in cache:cache[counts]=1-pooled_bootstrap(pooled_a,counts)/pooled_bootstrap(pooled_b,counts)
            reductions.append(cache[counts])
        out['pooled_primary_reduction']={'point':1-quantile(list(itertools.chain.from_iterable(pooled_a)),.95)/quantile(list(itertools.chain.from_iterable(pooled_b)),.95),'ci95':interval(reductions),'bootstrap_samples':len(draws),'unique_cluster_compositions':len(cache)}
        results['adaptive_vs_'+baseline]=out
    return results


def hypotheses(compare,complete):
    if not complete:return {'status':'Incomplete matrix; no full primary hypothesis decision'}
    c=compare['adaptive_vs_fixed32'];f8=compare['adaptive_vs_fixed8'];h2=c['pooled_primary_reduction'];h3=c['throughput'];idle=c['idle_backlog_fraction'];h4=c['recovery_confirmation'];rpc=c['rpc']
    latency=h2['point']>=.2 and h2['ci95'][0]>=.2
    rate=h3['ratio_of_means']>=.95 and h3['ratio_ci95'][0]>=.95
    idle_supported=idle['difference_ci95'][1]<=0
    recovery_supported='difference_ci95' in h4 and h4['pairs_lower']==5 and h4['difference_ci95'][1]<0 and rpc['ratio_of_means']<=1.1 and rpc['ratio_ci95'][1]<=1.1
    directions={key:1 for key in ['queue_p95','queue_p99','slow_p95','slow_p99','recovery_p95','rpc','skipped','recovery_confirmation']}
    directions['throughput']=-1
    effects={key:(f8[key].get('mean_difference')*direction if 'mean_difference' in f8[key] else None) for key,direction in directions.items()}
    complete_endpoints=all(value is not None for value in effects.values())
    adaptive_pareto=complete_endpoints and all(value<=0 for value in effects.values()) and any(value<0 for value in effects.values())
    fixed8_pareto=complete_endpoints and all(value>=0 for value in effects.values()) and any(value>0 for value in effects.values())
    h5_status=('strong multi-endpoint added-value evidence; qualitative materiality review still required' if adaptive_pareto else ('not supported: fixed8 dominates observed mean endpoints' if fixed8_pareto else 'mixed/incomplete tradeoff; necessity and overall material benefit not established'))
    return {'H1':{'status':'supported in observed valid runs','scope':'All lifecycle/physical/admission/byte checks passed, not a universal guarantee'},'H2':{'status':'supported' if latency else 'not established / fails uncertainty criterion','pooled_reduction':h2},'H3':{'status':'supported' if rate and idle_supported else 'not fully established','throughput_criterion_met':rate,'throughput_ratio':h3['ratio_of_means'],'throughput_ratio_ci95':h3['ratio_ci95'],'idle_nonincrease_supported':idle_supported,'idle_difference_fraction_ci95':idle['difference_ci95'],'qualification':'Frozen contract has no numerical material-idle margin; do not equate a CI containing zero with noninferiority'},'H4':{'status':'supported at prespecified window/grid resolution' if recovery_supported else 'not established','recovery':h4,'rpc_ratio':rpc['ratio_of_means'],'rpc_ratio_ci95':rpc['ratio_ci95']},'H5':{'status':h5_status,'adaptive_pareto_on_observed_mean_endpoints':adaptive_pareto,'fixed8_pareto_on_observed_mean_endpoints':fixed8_pareto,'signed_mean_effects_lower_favors_adaptive':effects,'qualification':'No frozen materiality margin or endpoint weights; evaluate the full fixed8 tradeoff, including repeated worse slowdown tails. Pooled p95 alone is insufficient.','slow_p95_pairs_adaptive_worse':f8['slow_p95']['pairs_higher'],'slow_p99_pairs_adaptive_worse':f8['slow_p99']['pairs_higher']},'null':{'status':'not formally rejected; assess consistency with waiting moved upstream and fixed bounded sufficiency','qualification':'Qualitative engineering null, no prespecified probabilistic null model; local latency is not end-to-end improvement'}}


def plots(root,groups,summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors={'fixed32':'tab:blue','fixed8':'tab:orange','adaptive':'tab:green'}
    fig,axes=plt.subplots(2,3,figsize=(12,7))
    for ax,key,title in zip(axes.flat,['queue_p95','slow_p95','queue_p99','recovery_p95','throughput','recovery_confirmation'],['Primary pooled-window p95, ms','Slowdown-only p95, ms','Pooled-window p99, ms','Recovery-only p95, ms','Offered-interval completions/s','Recovery confirmation delay, s']):
        for block in range(5):
            values=[metric(groups[p][block],key) for p in POLICIES]
            ax.plot(range(3),[v if v is not None else float('nan') for v in values],color='grey',alpha=.25,linewidth=.8)
        for i,p in enumerate(POLICIES):
            ax.scatter([i]*5,[metric(r,key) if metric(r,key) is not None else float('nan') for r in groups[p]],color=colors[p],s=20)
        ax.set_xticks(range(3),POLICIES);ax.set_title(title,fontsize=10);ax.grid(alpha=.2)
    fig.suptitle('Primary controlled comparison: five interleaved blocks; dots are independent runs')
    fig.tight_layout();fig.savefig(root/'primary-endpoints.png',dpi=140);fig.savefig(root/'primary-endpoints.svg');plt.close(fig)
    fig,axes=plt.subplots(4,1,figsize=(12,10),sharex=True)
    for p in POLICIES:
        for i,r in enumerate(groups[p]):
            folder=root/r['name'];s=[v for v in read(folder/'server/server.csv') if v['started']=='1'];t=[int(v['elapsed_ns'])/1e9 for v in s];c=read(folder/'client/client.csv')
            for ax,values in [(axes[0],[int(v['B']) for v in s]),(axes[1],[int(v['Q']) for v in s])]:ax.plot(t,values,color=colors[p],alpha=.45,label=p if i==0 else None)
            axes[2].plot([int(v['elapsed_ns'])/1e9 for v in c],[int(v['skipped']) for v in c],color=colors[p],alpha=.45,label=p if i==0 else None)
            stride=5
            axes[3].plot(t[stride:],[(int(b['processed'])-int(a['processed']))/((int(b['elapsed_ns'])-int(a['elapsed_ns']))/1e9) for a,b in zip(s,s[stride:])],color=colors[p],alpha=.45,label=p if i==0 else None)
    for ax,title in zip(axes,['Logical B','Physical Q (K=32)','Skipped scheduled slots','Worker completions/s']):
        ax.set_ylabel(title);ax.grid(alpha=.2);ax.legend(fontsize=8);ax.axvspan(12,24,alpha=.08,color='grey')
        for edge in [12,24,36]:ax.axvline(edge,color='grey',alpha=.3,linestyle='--')
    axes[-1].set_xlabel('Seconds from synchronized workload marker')
    fig.suptitle('All 15 runs: same source, binaries and instrumentation; per-policy colors')
    fig.tight_layout();fig.savefig(root/'primary-trajectories.png',dpi=140);fig.savefig(root/'primary-trajectories.svg');plt.close(fig)


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--no-plots',action='store_true');a=p.parse_args();root=a.directory
    runs=[];invalid=[]
    for path in sorted(root.glob('b*/manifest.json')):
        try:issues=validate(path.parent)
        except Exception as error:issues=['validation exception '+repr(error)]
        if issues:invalid.append({'name':path.parent.name,'issues':issues});continue
        runs.append(summarize(path.parent))
    groups={p:sorted([r for r in runs if r['policy']==p],key=lambda r:r['block']) for p in POLICIES}
    complete=not invalid and all(len(rows)==5 and [r['block'] for r in rows]==list(range(1,6)) for rows in groups.values())
    summary={}
    keys=['queue_p95','queue_p99','slow_p95','slow_p99','recovery_p95','recovery_confirmation','throughput','rpc','idle_backlog_fraction','skipped','send_wall','logical_wait']
    for policy,rows in groups.items():
        summary[policy]={key:describe([metric(r,key) for r in rows]) for key in keys}
        summary[policy]['pooled_queue_ms']=stats(list(itertools.chain.from_iterable(r['queue_cohort_ns'] for r in rows)),1e-6)
        summary[policy]['pooled_phases']={phase:stats(list(itertools.chain.from_iterable(cohort(read(root/r['name']/'server/events.csv'),start,end) for r in rows)),1e-6) for phase,start,end in [('healthy',0,12_000_000_000),('slowdown',12_000_000_000,24_000_000_000),('recovery',24_000_000_000,36_000_000_000)]}
    comp=comparisons(groups) if complete else {}
    decisions=hypotheses(comp,complete)
    if invalid:decisions['H1']={'status':'inspect invalid runs; do not infer all-attempt safety from valid subset','invalid':invalid}
    result={'analysis_plan':'experiments/002/stage5/PLAN.md','complete':complete,'valid_runs':len(runs),'invalid_attempts':invalid,'summary':summary,'paired_comparisons':comp,'hypotheses':decisions,'runs':[{k:v for k,v in r.items() if k!='queue_cohort_ns'} for r in runs]}
    (root/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    fields=['name','block','position','policy','queue_p95','queue_p99','slow_p95','slow_p99','recovery_p95','recovery_confirmation','throughput','rpc','idle_backlog_fraction','scheduled','skipped','attempted','successful_sends','failed_sends','processed','send_wall','logical_wait']
    with (root/'per-run.csv').open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
        for r in runs:writer.writerow({k:metric(r,k) if k in keys else r[k] for k in fields})
    if complete and not a.no_plots:plots(root,groups,summary)
    print(json.dumps({'complete':complete,'valid_runs':len(runs),'invalid':invalid,'hypotheses':decisions},indent=2))
if __name__=='__main__':main()
