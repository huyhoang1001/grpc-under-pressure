#!/usr/bin/env python3
"""E1B offline analysis: never launches applications or writes E1 files."""
import csv
import json
import math
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'experiments/001/results/e1b'

def read(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))
def numeric(path):
    output=[]
    for row in read(path):
        converted={}
        for k,v in row.items():
            try:converted[k]=float(v) if v else math.nan
            except ValueError:converted[k]=v
        output.append(converted)
    return output
def slope(data,key):
    if len(data)<3:raise ValueError('too few samples for '+key)
    x=statistics.mean(r['t'] for r in data);y=statistics.mean(r[key] for r in data)
    return sum((r['t']-x)*(r[key]-y) for r in data)/sum((r['t']-x)**2 for r in data)
def window(data,a,b):return [r for r in data if a<=r['t']<=b]
def percentile_final_check(latency,result):
    return all(abs(float(latency[-1]['cumulative_send_p'+str(p)+'_ms'])-result['send_p'+str(p)+'_ms'])<1e-7 for p in [50,95,99])

def analyze(folder):
    m=json.loads((folder/'manifest.json').read_text())
    result=json.loads((folder/'client.json').read_text())
    server=numeric(folder/'server.csv');client=numeric(folder/'client.csv');latency=read(folder/'latency.csv');proc=read(folder/'process.csv');obs=read(folder/'observations.csv')
    issues=[]
    if not m['source_hashes_unchanged']:issues.append('source changed during run')
    if m['resource_guard_events'] or m['monitor_errors']:issues.append('resource/monitor event')
    if m.get('runner_error'):issues.append('runner error')
    if m['outcome']=='failed_or_safety_aborted':issues.append('unexplained failure or safety abort')
    if not percentile_final_check(latency,result):issues.append('percentiles disagree with final client summary')
    clock_offset=statistics.median(int(r['observed_unix_ns'])-int(r['upper_monotonic_ns']) for r in obs)
    client_origin=statistics.median(int(r['unix_ns'])-float(r['elapsed_s'])*1e9 for r in latency)-clock_offset
    exported=[r for r in obs if r['source']=='server']
    lower=max(int(r['lower_monotonic_ns'])-float(json.loads(r['native_row_json'])['elapsed_s'])*1e9 for r in exported)
    upper=min(int(r['upper_monotonic_ns'])-float(json.loads(r['native_row_json'])['elapsed_s'])*1e9 for r in exported)
    if lower<=upper:server_origin=(lower+upper)/2;method='intersection of CSV visibility brackets'
    else:
        server_origin=statistics.median((int(r['lower_monotonic_ns'])+int(r['upper_monotonic_ns']))/2-float(json.loads(r['native_row_json'])['elapsed_s'])*1e9 for r in exported)
        method='median export-origin estimate; bracket intersection empty'
    for r in server:r['t']=r['elapsed_s']+(server_origin-client_origin)/1e9
    for r in client:r['t']=r['elapsed_s']
    offered=window(server,0,m['seconds']+.05)
    for r in server:
        if r['errors']==0:
            if r['queue_depth']!=r['enqueued']-r['dequeued']:issues.append('queue accounting');break
            if r['queue_bytes']!=r['queue_depth']*m['payload']:issues.append('queue byte accounting');break
            if r['received']!=r['processed']+r['queue_depth']+(r['handler_bytes']+r['worker_bytes'])/m['payload']:issues.append('ownership accounting');break
        else:
            if r['received']!=r['processed']+r['discarded']+r['queue_depth']+(r['handler_bytes']+r['worker_bytes'])/m['payload']:issues.append('error ownership accounting');break
    if max(r['connections_accepted'] for r in server)!=1 or max(r['active_streams'] for r in server)!=1:issues.append('topology')
    if m['variant']=='bounded' and max(r['queue_depth'] for r in server)>32:issues.append('capacity exceeded')
    if max(r['queue_bytes'] for r in server)>m['queue_limit'] or max(r['rss_bytes'] for r in server)>m['server_rss_limit']:issues.append('resource threshold crossed')
    if result['send_error']!='<nil>':issues.append('send error before normal send-side completion')
    if m['outcome']=='rpc_deadline_abort' and (m['variant']!='unbounded' or result['send_seconds']<m['seconds']):issues.append('unexpected deadline timing/variant')
    if m['outcome']=='completed_and_drained' and not (server[-1]['received']==server[-1]['processed']==result['completed_sends']==result['summary']['processed']):issues.append('normal final counts')
    if server[-1]['queue_bytes'] or server[-1]['worker_bytes']:issues.append('cleanup incomplete')
    cpu={}
    for role in ['server','client']:
        ps=[r for r in proc if r['role']==role]
        samples=[]
        for a,b in zip(ps,ps[1:]):
            dt=(int(b['monotonic_ns'])-int(a['monotonic_ns']))/1e9
            used=(int(b['utime_ticks'])+int(b['stime_ticks'])-int(a['utime_ticks'])-int(a['stime_ticks']))/int(b['clock_ticks_per_second'])
            samples.append({'t':(int(b['monotonic_ns'])-client_origin)/1e9,'cpu_fraction_one_core':used/dt,'rss_bytes':int(b['rss_bytes'])})
        active=window(samples,0,m['seconds'])
        cpu[role]={'offered_interval_mean_fraction_one_core':statistics.mean(r['cpu_fraction_one_core'] for r in active),'peak_sampled_fraction_one_core':max(r['cpu_fraction_one_core'] for r in active),'peak_sampled_rss_bytes':max(r['rss_bytes'] for r in samples)}
    row={'name':m['name'],'variant':m['variant'],'git_commit':m['git_commit'],'source_tree_clean':m['source_tree_clean'],'outcome':m['outcome'],'valid_offered_interval':not issues and result['send_seconds']>=m['seconds']-.05,'issues':sorted(set(issues)),'offered_seconds':m['seconds'],'send_seconds':result['send_seconds'],'rpc_seconds':result['rpc_seconds'],'attempts':result['attempts'],'completed_sends':result['completed_sends'],'skipped_slots':result['skipped_slots'],'send_p50_ms':result['send_p50_ms'],'send_p95_ms':result['send_p95_ms'],'send_p99_ms':result['send_p99_ms'],'send_call_time_s':result['send_total_ns']/1e9,'send_calls_gt20ms':result['send_blocked_gt20ms'],'fraction_gt20ms':result['send_blocked_gt20ms']/result['attempts'],'max_queue_depth':max(r['queue_depth'] for r in offered),'max_queue_bytes':max(r['queue_bytes'] for r in offered),'peak_server_rss_bytes':max(r['rss_bytes'] for r in offered),'server_rss_near_load_end_bytes':offered[-1]['rss_bytes'],'final_processed':server[-1]['processed'],'final_discarded':server[-1]['discarded'],'fully_drained':m['outcome']=='completed_and_drained','cpu':cpu,'clock_alignment':{'client_origin_monotonic_ns':client_origin,'server_origin_monotonic_ns':server_origin,'server_origin_lower_ns':lower,'server_origin_upper_ns':upper,'intersection_width_ms':max(0,upper-lower)/1e6,'method':method,'limitation':'CSV export visibility, not exact ownership snapshot time; exporter overhead is not separately measured. Aligned snapshots may hold native values for one ~200ms sampling interval.'}}
    if not m['preflight']:
        for label,a,b in [('steady',5,55),('early',5,20),('late',40,55)]:
            ss=window(server,a,b);cc=window(client,a,b)
            row[label]={'queue_slope_msg_s':slope(ss,'queue_depth'),'queue_slope_bytes_s':slope(ss,'queue_bytes'),'rss_slope_bytes_s':slope(ss,'rss_bytes'),'enqueue_rate':slope(ss,'enqueued'),'dequeue_rate':slope(ss,'dequeued'),'worker_rate':slope(ss,'processed'),'producer_attempt_rate':slope(cc,'attempts'),'producer_completion_rate':slope(cc,'completed')}
    else:
        row['send_rate']=result['completed_sends']/result['send_seconds']
        row['worker_capacity']=server[-1]['processed']/(server[-1]['service_ns']/1e9)
    # All common-clock snapshots preserve native row age instead of interpolating counters.
    by_source={source:[] for source in ['server','client','latency']}
    for o in obs:
        by_source[o['source']].append((int(o['upper_monotonic_ns']),json.loads(o['native_row_json'])))
    for series in by_source.values():series.sort(key=lambda v:v[0])
    indices={k:0 for k in by_source};latest={};last_proc={};proc_indices={role:0 for role in ['server','client']}
    process_series={role:[p for p in proc if p['role']==role] for role in ['server','client']}
    columns=['client_elapsed_s','monotonic_ns','phase','queue_depth','queue_bytes','server_rss_bytes','client_rss_bytes','attempts','completed','processed','send_ns','blocked_gt20ms','cumulative_send_p50_ms','cumulative_send_p95_ms','cumulative_send_p99_ms','server_native_elapsed_s','client_native_elapsed_s','server_export_age_ms','client_export_age_ms','latency_export_age_ms','server_cpu_fraction_one_core','client_cpu_fraction_one_core']
    with (folder/'synchronized.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        endpoint=max(r['t'] for r in server)
        for step in range(math.ceil(endpoint*5)+1):
            t=step/5;stamp=int(client_origin+t*1e9)
            for source,series in by_source.items():
                while indices[source]<len(series) and series[indices[source]][0]<=stamp:
                    latest[source]=series[indices[source]];indices[source]+=1
            if not all(k in latest for k in ['server','client','latency']):continue
            sv=latest['server'][1];cl=latest['client'][1];la=latest['latency'][1]
            snapshot={'client_elapsed_s':t,'monotonic_ns':stamp,'phase':'offered_load' if t<=m['seconds'] else 'drain_or_cancellation','queue_depth':sv['queue_depth'],'queue_bytes':sv['queue_bytes'],'server_rss_bytes':sv['rss_bytes'],'client_rss_bytes':cl['rss_bytes'],'attempts':cl['attempts'],'completed':cl['completed'],'processed':sv['processed'],'send_ns':cl['send_ns'],'blocked_gt20ms':cl['blocked_gt20ms'],'cumulative_send_p50_ms':la['cumulative_send_p50_ms'],'cumulative_send_p95_ms':la['cumulative_send_p95_ms'],'cumulative_send_p99_ms':la['cumulative_send_p99_ms'],'server_native_elapsed_s':sv['elapsed_s'],'client_native_elapsed_s':cl['elapsed_s']}
            for source in latest:snapshot[source+'_export_age_ms']=(stamp-latest[source][0])/1e6
            for role,series in process_series.items():
                i=proc_indices[role]
                while i<len(series) and int(series[i]['monotonic_ns'])<=stamp:i+=1
                proc_indices[role]=i
                if i>=2:
                    a,b=series[i-2:i];used=(int(b['utime_ticks'])+int(b['stime_ticks'])-int(a['utime_ticks'])-int(a['stime_ticks']))/int(b['clock_ticks_per_second'])
                    snapshot[role+'_cpu_fraction_one_core']=used/((int(b['monotonic_ns'])-int(a['monotonic_ns']))/1e9)
            writer.writerow(snapshot)
    return row,server,client

def main():
    runs=[];preflight=[];series={}
    for phase,target in [('preflight',preflight),('runs',runs)]:
        for folder in sorted((OUT/phase).glob('*')):
            if not (folder/'manifest.json').exists():continue
            if not (folder/'client.json').exists():raise RuntimeError('Missing client result: '+str(folder))
            row,s,c=analyze(folder);target.append(row);series[row['name']]=(s,c)
    summary={}
    metrics=['queue_slope_msg_s','queue_slope_bytes_s','rss_slope_bytes_s','producer_attempt_rate','producer_completion_rate','worker_rate']
    for v in ['direct','unbounded','bounded']:
        vs=[r for r in runs if r['variant']==v]
        summary[v]={'run_count':len(vs),'valid_60s_intervals':sum(r['valid_offered_interval'] for r in vs),'outcomes':{k:sum(r['outcome']==k for r in vs) for k in sorted(set(r['outcome'] for r in vs))}}
        for key in metrics:
            values=[r['steady'][key] for r in vs if r['valid_offered_interval']]
            if values:summary[v][key]={'median':statistics.median(values),'min':min(values),'max':max(values)}
        for key in ['max_queue_depth','max_queue_bytes','peak_server_rss_bytes','send_p50_ms','send_p95_ms','send_p99_ms','send_call_time_s','fraction_gt20ms']:
            values=[r[key] for r in vs if r['valid_offered_interval']]
            if values:summary[v][key]={'median':statistics.median(values),'min':min(values),'max':max(values)}
    output={'steady_client_window_s':[5,55],'early_window_s':[5,20],'late_window_s':[40,55],'preflight':preflight,'runs':runs,'summary':summary,'interpretation':'Deadline-aborted drain is not a completed run. valid_60s_intervals only describes sustained load data, and never hides the recorded outcome.'}
    (OUT/'analysis.json').write_text(json.dumps(output,indent=2)+'\n')
    if any(r['issues'] for r in preflight+runs):raise RuntimeError([(r['name'],r['issues']) for r in preflight+runs if r['issues']])
    if runs:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(4,3,figsize=(16,12),sharex=True)
        for col,v in enumerate(['direct','unbounded','bounded']):
            candidates=[r for r in runs if r['variant']==v]
            for r in candidates:
                s,c=series[r['name']];t=[a['t'] for a in s]
                axes[0,col].plot(t,[a['queue_bytes']/2**20 for a in s],alpha=.6)
                axes[1,col].plot(t,[a['rss_bytes']/2**20 for a in s],alpha=.6)
                stride=5
                for key,data,color,label in [('processed',s,'tab:green','worker'),('completed',c,'tab:red','completed Send'),('attempts',c,'tab:purple','attempted Send')]:
                    xs=[b['t'] for a,b in zip(data,data[stride:])];ys=[(b[key]-a[key])/(b['t']-a['t']) for a,b in zip(data,data[stride:])]
                    axes[2,col].plot(xs,ys,color=color,alpha=.25,label=label if r==candidates[0] else None)
                l=numeric(OUT/'runs'/r['name']/'latency.csv')
                axes[3,col].plot([a['elapsed_s'] for a in l],[a['cumulative_send_p95_ms'] for a in l],alpha=.6)
            axes[0,col].set_title(v+' — all repetitions')
            for ax in axes[:,col]:ax.axvline(60,color='black',linestyle='--',alpha=.5);ax.grid(alpha=.2)
            axes[2,col].legend(fontsize=7);axes[3,col].set_xlabel('Client elapsed seconds (load ends at 60s)')
        axes[0,1].annotate('120s RPC deadline:\nremaining queue discarded', xy=(120,0), xytext=(63,75), arrowprops={'arrowstyle':'->','color':'black'}, fontsize=8)
        for i,label in enumerate(['Queued payload MiB','Server RSS MiB','messages/s','Cumulative Send p95 ms']):axes[i,0].set_ylabel(label)
        fig.suptitle('E1B release / final hardened server — offered load vs drain/deadline; finite sampled observations')
        fig.tight_layout();fig.savefig(OUT/'comparison.png',dpi=150);fig.savefig(OUT/'comparison.svg');plt.close(fig)
        fig,axes=plt.subplots(3,3,figsize=(16,9),sharex=True)
        for col,v in enumerate(['direct','unbounded','bounded']):
            for r in [a for a in runs if a['variant']==v]:
                data=numeric(OUT/'runs'/r['name']/'synchronized.csv')
                for field,ax,color,label in [('server_cpu_fraction_one_core',axes[0,col],'tab:blue','server'),('client_cpu_fraction_one_core',axes[0,col],'tab:orange','client'),('client_rss_bytes',axes[1,col],'tab:orange','client RSS')]:
                    ax.plot([a['client_elapsed_s'] for a in data],[a[field]*(100 if 'cpu' in field else 1/2**20) for a in data],alpha=.3,color=color)
                for p,color in [(50,'tab:green'),(95,'tab:orange'),(99,'tab:red')]:axes[2,col].plot([a['client_elapsed_s'] for a in data],[a[f'cumulative_send_p{p}_ms'] for a in data],alpha=.35,color=color)
            axes[0,col].set_title(v);axes[2,col].set_xlabel('Client elapsed seconds')
            for ax in axes[:,col]:ax.axvline(60,color='black',linestyle='--',alpha=.5);ax.grid(alpha=.2)
        axes[0,0].set_ylabel('CPU % of one core\nblue server / orange client');axes[1,0].set_ylabel('Client RSS MiB');axes[2,0].set_ylabel('Cumulative Send ms\ngreen p50 / orange p95 / red p99')
        fig.tight_layout();fig.savefig(OUT/'telemetry.png',dpi=150);fig.savefig(OUT/'telemetry.svg');plt.close(fig)
        baseline=json.loads((ROOT/'experiments/001/results/e1/analysis.json').read_text())
        (OUT/'e1-comparison.json').write_text(json.dumps({'e1_reference_commit':'3374f126e3009991ec97c95e64dabd03c734b575','e1_summary':baseline['summary'],'e1b_summary':summary,'caveat':'Source, release profile, duration and telemetry differ together; no isolated causal effect size. V1 drain may be deadline-censored.'},indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
