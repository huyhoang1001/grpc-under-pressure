#!/usr/bin/env python3
"""Offline Stage 2 control and exploratory analysis; no application execution."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[3]

def read(p):
    with p.open(newline='') as f:return list(csv.DictReader(f))
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def quantile(values,p):
    if not values:return None
    values=sorted(values);return values[max(0,math.ceil(len(values)*p)-1)]
def stats(values,scale=1):
    if not values:return {'count':0}
    return {'count':len(values),'mean':statistics.mean(values)*scale,'p50':quantile(values,.5)*scale,'p95':quantile(values,.95)*scale,'p99':quantile(values,.99)*scale,'min':min(values)*scale,'max':max(values)*scale}
def hquantile(bounds,counts,p):
    rank=math.ceil(sum(counts)*p);seen=0
    for b,n in zip(bounds,counts):
        seen+=n
        if seen>=rank:return b

def one(folder):
    m=json.loads((folder/'manifest.json').read_text());s=read(folder/'server/server.csv');c=json.loads((folder/'client/summary.json').read_text());last=s[-1]
    wall=int(last['worker_busy_ns'])+int(last['worker_idle_ns'])
    event_ns=int(last['event_write_ns'])+int(last['event_flush_ns'])
    hist=json.loads((folder/'server/histograms.json').read_text())
    service_counts=[sum(values) for values in zip(*hist['service_counts'])]
    result={'name':m['name'],'purpose':m['purpose'],'event_io':m['event_io'],'source_commit':m['git_commit'],'valid_for_declared_purpose':m['valid_for_declared_purpose'],'scheduled':c['scheduled'],'skipped':c['skipped'],'attempted':c['attempted'],'successful_sends':c['successful_sends'],'failed_sends':c['failed_sends'],'admitted':int(last['admitted']),'dequeued':int(last['dequeued']),'processed':int(last['processed']),'discarded':int(last['discarded']),'received_not_admitted':int(last['received_not_admitted']),'Qmax':max(int(r['Q']) for r in s),'R_final':int(last['R']),'Q_final':int(last['Q']),'W_final':int(last['W']),'errors':int(last['errors']),'phase_alignment_ms':m['clock']['phase_alignment_error_ns']/1e6,'worker_observed_s':wall/1e9,'worker_busy_s':int(last['worker_busy_ns'])/1e9,'worker_idle_s':int(last['worker_idle_ns'])/1e9,'idle_backlog_ms':int(last['worker_idle_backlog_ns'])/1e6,'event_write_calls':int(last['event_write_calls']),'event_format_write_ms':int(last['event_write_ns'])/1e6,'event_write_max_us':int(last['event_write_max_ns'])/1e3,'event_flush_calls':int(last['event_flush_calls']),'event_flush_ms':int(last['event_flush_ns'])/1e6,'event_flush_max_us':int(last['event_flush_max_ns'])/1e3,'timed_event_io_fraction':event_ns/wall,'service_mean_ms':int(last['service_duration_sum_ns'])/int(last['service_observations'])/1e6,'service_p95_upper_ms':hquantile(hist['bounds_ns'],service_counts,.95)/1e6,'half_close_s':c['half_close_ns']/1e9,'rpc_s':c['rpc_elapsed_ns']/1e9,'rpc_status':c['rpc_error'],'peak_server_rss_mib':max(int(r['rss_bytes']) for r in s)/2**20,'send_gt20ms_calls':c['send_gt20ms_calls'],'send_gt20ms_duration_s':c['send_gt20ms_duration_ns']/1e9,'send_wall_duration_s':c['send_duration_ns']/1e9,'logical_admission_wait_s':int(last['logical_gate_wait_ns'])/1e9,'physical_reservation_wait_s':int(last['physical_reservation_wait_ns'])/1e9}
    if m['event_io']=='buffered':
        e=read(folder/'server/events.csv');sends=read(folder/'client/sends.csv');completed=[v for v in e if v['event']=='processed'];dequeued=[v for v in e if v['event']=='dequeued'];eof=[v for v in e if v['event']=='eof']
        result['server_eof_s']=int(eof[-1]['observed_elapsed_ns'])/1e9
        result['last_completion_s']=max(int(v['completion_ns']) for v in completed)/1e9
        result['server_worker_stop_s']=wall/1e9
        result['server_eof_to_worker_stop_s']=max(0,result['server_worker_stop_s']-result['server_eof_s'])
        result['server_eof_to_last_completion_s']=max(0,result['last_completion_s']-result['server_eof_s'])
        result['service_start_selections']={}
        for p in range(4):
            group=[v for v in dequeued if int(v['service_start_phase'])==p]
            result['service_start_selections'][str(p)]={'count':len(group),'first_start_s':min((int(v['service_start_ns'])/1e9 for v in group),default=None),'selected_ms':sorted(set(int(v['selected_service_ms']) for v in group))}
        slots=[int(v['slot']) for v in sends];seq=[int(v['sequence']) for v in sends]
        assert len(set(slots))==len(slots) and slots==sorted(slots)
        assert seq==list(range(len(seq)))
        phases={}
        for i,(name,a,b) in enumerate([('healthy',0,12),('slowdown',12,24),('recovery',24,36),('drain',36,None)]):
            within=lambda value: value>=a*1e9 and (b is None or value<b*1e9)
            services=[int(v['service_duration_ns']) for v in completed if within(int(v['service_start_ns']))]
            completions=[v for v in completed if within(int(v['completion_ns']))]
            queues=[int(v['queue_residence_ns']) for v in dequeued if within(int(v['enqueue_ns']))]
            sender=[v for v in sends if within(int(v['send_start_ns']))]
            returned=[v for v in sends if within(int(v['send_return_ns'])) and v['outcome']=='success']
            snapshots=[v for v in s if v['started']=='1' and within(int(v['elapsed_ns']))]
            counts=[int(v['Q']) for v in snapshots]
            phases[name]={'bounds_s':[a,b],'actual_service_ms_by_start':stats(services,1e-6),'completion_count':len(completions),'completion_rate_s':len(completions)/(b-a) if b else None,'queue_residence_ms_by_enqueue':stats(queues,1e-6),'Q_mean':statistics.mean(counts) if counts else None,'Q_max':max(counts,default=None),'attempted_sends':len(sender),'successful_sends':sum(v['outcome']=='success' for v in sender),'successful_send_returns':len(returned),'return_rate_s':len(returned)/(b-a) if b else None,'attempt_rate_s':len(sender)/(b-a) if b else None,'send_ms':stats([int(v['send_duration_ns']) for v in sender],1e-6)}
            if i<3 and m['offered_seconds']==36:
                phase_slots=sum(i*960<=slot<(i+1)*960 for slot in slots)
                phases[name]['scheduled_slots']=960;phases[name]['attempted_scheduled_slots']=phase_slots;phases[name]['skipped_scheduled_slots']=960-phase_slots
        result['phases']=phases
        after=[v for v in s if v['started']=='1' and 24e9<=int(v['elapsed_ns'])<=36e9]
        result['first_sampled_Q_zero_after24_s']=next((int(v['elapsed_ns'])/1e9 for v in after if int(v['Q'])==0),None)
        for label,a,b in [('early_recovery',24,28),('late_recovery',32,36)]:
            count=sum(a*1e9<=int(v['completion_ns'])<b*1e9 for v in completed)
            result[label+'_completion_rate_s']=count/(b-a)
        result['phase_markers']=read(folder/'server/phase-transitions.csv')
        if m['service_schedule']=='contract' and m['offered_seconds']==36:
            healthy=phases['healthy'];slow=phases['slowdown'];recover=phases['recovery']
            result['intended_capacity_transition_observed']=(healthy['actual_service_ms_by_start']['mean']<20 and 30<slow['actual_service_ms_by_start']['mean']<70 and recover['actual_service_ms_by_start']['mean']<20 and slow['completion_rate_s']<healthy['completion_rate_s'] and slow['Q_max']==32 and result['early_recovery_completion_rate_s']>slow['completion_rate_s'])
            if not result['intended_capacity_transition_observed']:result['failure_notice']='Frozen workload did not show intended capacity transition; do not retune.'
    if m['offered_seconds']!=36:
        for key in ['phases','first_sampled_Q_zero_after24_s','early_recovery_completion_rate_s','late_recovery_completion_rate_s']:result.pop(key,None)
        result['phase_window_note']='Short control/smoke: full 12-second phase windows were not executed; no phase throughput rates reported.'
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();root=a.directory
    cases=[]
    for path in sorted(root.glob('*/manifest.json')):
        m=json.loads(path.read_text())
        if not m.get('valid_for_declared_purpose'):raise RuntimeError('invalid retained run: '+str(path))
        cases.append(one(path.parent))
    output={'runs':cases,'scope':'instrumentation overhead and one exploratory fixed32 scenario; no primary comparison'}
    controls=[r for r in cases if r['purpose']=='overhead_control']
    if controls:
        output['overhead']={}
        for mode in ['buffered','discard']:
            group=[r for r in controls if r['event_io']==mode]
            output['overhead'][mode]={key:{'median':statistics.median(r[key] for r in group),'min':min(r[key] for r in group),'max':max(r[key] for r in group)} for key in ['timed_event_io_fraction','event_format_write_ms','event_flush_ms','event_flush_max_us','service_mean_ms','service_p95_upper_ms']}
        output['overhead_caveat']='ABBA two cases per mode; same formatting/histograms/locks/200ms counters. Discard has no event ledger, is control-only. Timers include formatting and buffered writes/flush, not all lock/histogram instrumentation or timer overhead. Flush is OS page-cache write, not fsync. Healthy offered-limited controls do not estimate saturated capacity loss; min/max are not confidence intervals.'
    save(root/'analysis.json',output)
    print(json.dumps(output.get('overhead',{r['name']:r.get('intended_capacity_transition_observed') for r in cases}),indent=2))
    exploratory=[r for r in cases if r['purpose']=='single_exploratory_slowdown_recovery']
    if exploratory:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        r=exploratory[0];folder=root/r['name'];s=read(folder/'server/server.csv');events=read(folder/'server/events.csv');client=read(folder/'client/client.csv')
        completed=[v for v in events if v['event']=='processed']
        fig,axes=plt.subplots(5,1,figsize=(11,13),sharex=True)
        axes[0].plot([int(v['service_start_ns'])/1e9 for v in completed],[int(v['service_duration_ns'])/1e6 for v in completed],'.',markersize=2,label='actual service duration, grouped by start')
        axes[0].step([0,12,24,36,37],[10,40,10,10,10],where='post',label='configured ms',color='black');axes[0].set_ylabel('Service ms');axes[0].legend(fontsize=8)
        t=[int(v['elapsed_ns'])/1e9 for v in s if v['started']=='1'];ss=[v for v in s if v['started']=='1']
        axes[1].plot(t,[int(v['Q']) for v in ss],label='physical Q');axes[1].set_ylabel('Queue depth');axes[1].set_ylim(-1,34)
        for data,key,color,label in [(ss,'processed','tab:green','worker completions'),(client,'successful_sends','tab:red','successful Send returns')]:
            stride=5
            xs=[int(b['elapsed_ns'])/1e9 for a,b in zip(data,data[stride:])];ys=[(int(b[key])-int(a[key]))/((int(b['elapsed_ns'])-int(a['elapsed_ns']))/1e9) for a,b in zip(data,data[stride:])]
            axes[2].plot(xs,ys,label=label,color=color)
        axes[2].set_ylabel('messages/s');axes[2].legend(fontsize=8)
        dq=[v for v in events if v['event']=='dequeued']
        axes[3].plot([int(v['enqueue_ns'])/1e9 for v in dq],[int(v['queue_residence_ns'])/1e6 for v in dq],'.',markersize=2);axes[3].set_ylabel('Queue residence ms\nby enqueue time')
        axes[4].plot([int(v['elapsed_ns'])/1e9 for v in client],[int(v['skipped']) for v in client],label='skipped slots');axes[4].set_ylabel('Skipped slots');axes[4].set_xlabel('Local seconds from synchronized workload marker')
        for ax in axes:
            ax.axvspan(12,24,color='orange',alpha=.1)
            for boundary in [12,24,36]:ax.axvline(boundary,color='grey',linestyle='--',alpha=.6)
            ax.grid(alpha=.2)
        fig.suptitle('Stage 2 — ONE exploratory fixed32 run; no adaptive-policy comparison')
        fig.tight_layout();fig.savefig(root/'exploratory.png',dpi=150);fig.savefig(root/'exploratory.svg')
if __name__=='__main__':main()
