#!/usr/bin/env python3
"""Package already-collected E1B data. No workload execution."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'experiments/001'
OUT=BASE/'results/e1b'
PIN='9773403fbb8d156b2773687254fe038c6a5105d1'

def main():
    data=json.loads((OUT/'analysis.json').read_text());summary=data['summary'];runs=data['runs']
    assert len(runs)==15
    assert all(s['run_count']==5 and s['valid_60s_intervals']==5 for s in summary.values())
    manifests={r['name']:json.loads((OUT/'runs'/r['name']/'manifest.json').read_text()) for r in runs}
    assert all(m['git_commit']==PIN and m['source_tree_clean'] and m['source_hashes_unchanged'] for m in manifests.values())
    assert len({json.dumps(m['binary_sha256'],sort_keys=True) for m in manifests.values()})==1
    assert all(m['server_exit']==0 and not m['events'] and not m['resource_guard_events'] and not m['monitor_errors'] and not m.get('runner_error') for m in manifests.values())
    preserved=[]
    for line in (OUT/'baseline-evidence-sha256.txt').read_text().splitlines():
        expected,name=line.split('  ',1);assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name;preserved.append(name)
    hashes=next(iter(manifests.values()))['binary_sha256']
    source_checks={}
    for name,m in manifests.items():
        matched=[]
        for path,digest in m['source_sha256'].items():
            original=subprocess.check_output(['git','show',PIN+':'+path],cwd=ROOT)
            assert hashlib.sha256(original).hexdigest()==digest,(name,path)
            matched.append(path)
        source_checks[name]=len(matched)
    audit={'source_commit':PIN,'all_fifteen_source_tree_clean':True,'binary_hashes_identical':hashes,'baseline_evidence_files_unchanged':len(preserved),'source_inputs_verified_against_git_commit':source_checks,'outcomes':{v:s['outcomes'] for v,s in summary.items()},'no_source_or_workload_execution_in_packaging':True}
    (OUT/'integrity-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    old=json.loads((BASE/'results/e1/analysis.json').read_text())['summary']
    fig,axes=plt.subplots(2,3,figsize=(14,8))
    specs=[('queue_slope_msg_s','Queue growth (messages/s)',1),('max_queue_bytes','Peak queued payload (MiB)',1/2**20),('peak_server_rss_bytes','Peak server RSS (MiB)',1/2**20),('producer_completion_rate','Completed Send/s',1),('worker_rate','Worker completions/s',1),('send_p95_ms','Send p95 (ms)',1)]
    old_keys={'peak_server_rss_bytes':'peak_rss_bytes','producer_completion_rate':'steady_send_rate','worker_rate':'processed_rate'}
    variants=['direct','unbounded','bounded']
    for ax,(key,label,scale) in zip(axes.flat,specs):
        for offset,src,name,color in [(-.18,old,'E1: debug/12s/pre-hardening','tab:blue'),(.18,summary,'E1B: release/60s/hardened+telemetry','tab:orange')]:
            stats=[src[v][old_keys.get(key,key) if src is old else key] for v in variants]
            means=[r['median']*scale for r in stats];err=[[r['median']*scale-r['min']*scale for r in stats],[r['max']*scale-r['median']*scale for r in stats]]
            ax.bar([i+offset for i in range(3)],means,.36,label=name,color=color,yerr=err,capsize=3)
        ax.set_xticks(range(3),variants);ax.set_ylabel(label);ax.grid(axis='y',alpha=.2)
    axes.flat[0].legend(fontsize=7)
    fig.suptitle('Descriptive comparison: medians and observed ranges, not confidence intervals\nProfile, duration, source and telemetry change together; V1 E1B drain is deadline-censored')
    fig.tight_layout();fig.savefig(OUT/'e1-versus-e1b.png',dpi=150);fig.savefig(OUT/'e1-versus-e1b.svg');plt.close(fig)
    def stat(v,key,scale=1,digits=2):
        s=summary[v][key]
        def fmt(value):
            x=value*scale
            if abs(x)<.5*10**(-digits):x=0
            return f'{x:.{digits}f}'
        return f"{fmt(s['median'])} [{fmt(s['min'])}, {fmt(s['max'])}]"
    lines=['# EXPERIMENT-001B — Release-Build Sustained Overload Validation','',f'Measured source/harness commit: `{PIN}`. Baseline E1 evidence: `3374f126e3009991ec97c95e64dabd03c734b575`.','',
    '## Outcome','',
    'All **15 requested 60-second offered intervals** were collected (five per variant). All ten direct/bounded RPCs completed and drained. All five unbounded RPCs completed their offered interval but **hit the unchanged 120-second whole-RPC deadline during drain**. They are retained as deadline-aborted runs, not successful drains. No RSS/queue/CPU/file/wall safety guard fired, and there were no unexplained collection or accounting failures.','',
    'Repeated positive unbounded queue/RSS growth, bounded occupancy at K=32, and direct/bounded producer throughput near measured worker throughput are consistent with E1. The lifecycle timeout prevents a complete-drain or post-drain RSS conclusion for unbounded E1B.','',
    '## Protocol, environment and provenance','',
    'The [predeclared extension](EXTENSION-001B.md) preserves the workload: 300 scheduled/s; 16 KiB payload; seed 1; one worker with 10 ms sleep; K=32; fixed 65,535-byte windows; adaptive server windows off; no compression/retries; two Tokio workers and GOMAXPROCS=2; no traffic warmup. Offered duration and Rust profile are the intended experimental changes; telemetry and the already-hardened server source are explicit comparison differences. The explicitly declared optional Go telemetry adds timestamped cumulative latency percentiles, snapshot-copy/sort and an additional file sync every 200 ms. It is an observer-effect confounder, not a pacing or transport change.','',
    'The Rust application source is byte-identical to baseline 3374f12 (the final hardened source). Go was already optimized by default in E1; E1B changes the Rust build to release and adds observer telemetry to Go. [environment.json](results/e1b/environment.json) records compiler versions, dependency tree, OS/kernel, cgroup/disk/CPU and build commands. Original E1 had an earlier pre-cancellation-hardening server snapshot. No separate independent-review file was found; the user supplied the EXTEND decision.','',
    'Each [run manifest](results/e1b/runs/) records the exact Git SHA, full dirty-tree status, source-clean flag, source-input SHA256, binary SHA256, start/finish clocks, command arrays, parameters, limits and exit/error outcome. Source/harness was committed before primary measurement and remained unchanged. New result files made the overall working tree dirty; this is recorded rather than represented as a clean checkout. Binaries were built before that freeze commit with matching source content; the captured Go build metadata still records the earlier revision and dirty flag. The pinned source-input hashes, not that embedded VCS stamp, establish the measured source. No byte-identical compiler-rebuild guarantee is made.','',
    f'[integrity-audit.json](results/e1b/integrity-audit.json) checks all source inputs against the pinned Git objects, identical binaries across primary runs, and **{len(preserved)} original evidence files unchanged**. [Baseline integrity inventory](results/e1b/baseline-evidence-sha256.txt) preserves their hashes. The older full-package E1 checksum inventory and recursive review verifier describe the baseline checkout; run those on 3374f12 rather than treating the expanded results tree as the old package. New Go telemetry legitimately changes application source, not historical raw measurements. Postmeasurement plot annotation and packaging scripts do not alter the pinned measured binaries.','',
    '## Commands and validation','',
    'Executed from `/workspace/grpc-under-pressure` after `source scripts/dev-env.sh`:','',
    '```sh','cargo build --release --locked --manifest-path server/Cargo.toml -j 4','(cd loadgen && go test -mod=readonly -v ./...)','(cd loadgen && go build -mod=readonly -o /workspace/toolchains/bin/pressure-loadgen-e1b ./cmd/loadgen)','python3 experiments/001/e1b/run.py --phase preflight','# Protocol/harness/telemetry committed as 9773403 before this phase:','python3 experiments/001/e1b/run.py --phase measured','MPLCONFIGDIR=/workspace/toolchains/matplotlib python3 experiments/001/e1b/analyze.py','MPLCONFIGDIR=/workspace/toolchains/matplotlib python3 experiments/001/e1b/finalize.py','```','',
    'The original eight integration tests were also executed against release binaries by loading `tests/test_runtime.py`, replacing its SERVER and CLIENT constants with the release executable paths, and running unittest. [Integration log](results/e1b/release-integration.log), [Go tests/build](results/e1b/build-go.log), [Rust build](results/e1b/build-rust-release.log), and [preflight log](results/e1b/preflight-runner.log) retain results. The two Go protocol tests plus the new percentile test passed, as did all eight process integration tests. Integration-test temporary safety/cancellation CSVs were not archived; primary deadline-aborted runs are fully retained.','',
    'Preflight used independent fresh processes: 3 s sender calibrations with a 1 ms worker, 4 s 50/s controls with a 10 ms worker, and 3 s saturated direct-worker calibration. These are not counted as primary repetitions. [Preflight raw data](results/e1b/preflight/) and analysis include all seven runs. Calibration showed >=285/s sender capability in each variant and no sustained control queue growth.','',
    'All primary child commands are wrapped with `prlimit --cpu=120 --fsize=67108864 --core=0`. Original limits remain 256 MiB queued payload, 512 MiB server RSS, 120 s RPC deadline; supplemental guards use 128 MiB client RSS and 125 s external wall timeout. The deadline is not raised to conceal unbounded drain failure. The inspected cgroup allows 32 GiB; see environment evidence. Execution is sequential, with fresh processes and seed-1 shuffled order in [run-order.json](results/e1b/run-order.json).','',
    '## Measurement definitions and synchronization','',
    'Each run retains `server.csv`, `client.csv`, `latency.csv`, `process.csv`, `observations.csv`, `client.json`, stdout/stderr logs and manifest. Offline `synchronized.csv` aligns observer snapshots on the same host monotonic clock. Process samples and observation brackets carry common timestamps; latency.csv carries native wall timestamp and elapsed time. Server clock origin is inferred from export-visibility brackets, with width/method retained in analysis. This is bounded sampling alignment with unmeasured export overhead, not exact event synchronization. Native values may be held for a ~200 ms sample interval; export ages are explicit. No cross-host timestamps are subtracted.','',
    'Steady slopes use **5–55 s after client start**. Early 5–20 s and late 40–55 s windows check sustained behavior. Rates are derived from counter increments on native actor time; Send throughput is not computed by dividing completed Sends by the entire RPC/drain lifetime. Latency series are **cumulative p50/p95/p99**, not interval histograms. Send call time includes serialization/scheduling and possible blocking; it is never labeled isolated HTTP/2 transport wait. Calls >20 ms are a coarse indicator and can be zero despite worker-paced ~11 ms Send latency. CPU is sampled from Linux ticks and expressed as a fraction of one core, with tick quantization and finite sampling. E1B CPU uses the offered interval; E1 reported a full-RPC average including drain, so those CPU averages are not directly comparable. RSS is OS process memory, separate from logical owned payload bytes.','',
    '## Measured primary results','',
    'Medians [observed minimum, maximum] across five offered intervals per variant; ranges are not confidence intervals. Full per-run/early/late/CPU/clock statistics are in [analysis.json](results/e1b/analysis.json).','',
    '| Metric | Direct | Unbounded | Bounded K=32 |','|---|---:|---:|---:|']
    metrics=[('Queue growth, messages/s','queue_slope_msg_s',1,3),('Queue bytes growth, MiB/s','queue_slope_bytes_s',1/2**20,3),('RSS growth, MiB/s','rss_slope_bytes_s',1/2**20,3),('Peak queued messages','max_queue_depth',1,0),('Peak queued payload, MiB','max_queue_bytes',1/2**20,2),('Peak server RSS during offered load, MiB','peak_server_rss_bytes',1/2**20,2),('Attempted Sends/s','producer_attempt_rate',1,2),('Completed Sends/s','producer_completion_rate',1,2),('Worker completions/s','worker_rate',1,2),('Send p50, ms','send_p50_ms',1,3),('Send p95, ms','send_p95_ms',1,3),('Send p99, ms','send_p99_ms',1,3),('Cumulative time inside Send, s','send_call_time_s',1,3),('Fraction Send calls >20 ms','fraction_gt20ms',1,4)]
    for label,key,scale,digits in metrics:lines.append('| '+label+' | '+' | '.join(stat(v,key,scale,digits) for v in ['direct','unbounded','bounded'])+' |')
    widths=[r['clock_alignment']['intersection_width_ms'] for r in runs]
    lines += ['', f'All primary server clock-origin estimates had nonempty export-visibility bracket intersections (widths {min(widths):.3f}–{max(widths):.3f} ms). These widths exclude unmeasured exporter overhead and do not remove the ~200 ms native sampling/held-value uncertainty.']
    lines += ['', '### Sustained growth and CPU','']
    for v in ['direct','unbounded','bounded']:
        vr=[r for r in runs if r['variant']==v]
        early=[r['early']['queue_slope_msg_s'] for r in vr];late=[r['late']['queue_slope_msg_s'] for r in vr]
        sc=[r['cpu']['server']['offered_interval_mean_fraction_one_core']*100 for r in vr];cc=[r['cpu']['client']['offered_interval_mean_fraction_one_core']*100 for r in vr]
        cr=max(r['cpu']['client']['peak_sampled_rss_bytes'] for r in vr)/2**20
        lines.append(f"- **{v}**: early queue slopes {min(early):.3f}–{max(early):.3f} msg/s; late {min(late):.3f}–{max(late):.3f} msg/s. Median offered-window CPU: server {statistics.median(sc):.2f}%, client {statistics.median(cc):.2f}% of one core. Peak sampled client RSS {cr:.2f} MiB.")
    lines += ['', '![All repetitions: queue, RSS, throughput and Send p95](results/e1b/comparison.png)','', '![CPU, client RSS and cumulative Send percentiles](results/e1b/telemetry.png)','',
    '### Every primary outcome, including aborted drains','',
    '| Run | 60 s data eligible | RPC outcome | Completed Sends | Processed at cleanup | Explicitly discarded | Manifest |','|---|---|---|---:|---:|---:|---|']
    for r in runs:
        name=r['name'];lines.append(f"| {name} | {r['valid_offered_interval']} | {r['outcome']} | {r['completed_sends']} | {int(r['final_processed'])} | {int(r['final_discarded'])} | [JSON](results/e1b/runs/{name}/manifest.json) |")
    lines += ['',
    'The five unbounded `client_exit=1` outcomes are real DeadlineExceeded errors after a full offered interval; server cleanup exits zero. Discarded bytes/messages are not called processed. Their post-cancellation zero queue does not indicate a successful drain. No primary run was silently excluded, replaced or retried. Sampling/ownership equations passed before and after cleanup, with discarded counts included after cancellation. A finite sampler cannot prove every transient occupancy; bounded capacity also follows from the unchanged reserve-before-receive/channel implementation.','',
    '## E1 comparison and contradictions','',
    '![E1 versus E1B descriptive medians and ranges](results/e1b/e1-versus-e1b.png)','',
    '[e1-comparison.json](results/e1b/e1-comparison.json) retains both summaries. E1 measured 12 s debug-build overloads using pre-hardening server source; E1B uses 60 s release runs on the final hardened server plus Go telemetry. The longer unbounded interval accumulates more queue-owned bytes and RSS. Throughput remains close to measured consumer capacity in direct/bounded and materially higher in unbounded. These changes occur together; the experiment cannot isolate a build-profile, duration, source-version or instrumentation causal effect.','',
    '**No observed result contradicts E1’s central application-level finding.** A material lifecycle difference is that E1 drained normally whereas all E1B unbounded RPCs exceed the retained deadline during drain. This limits drain/reconciliation interpretation; it is not evidence that the queue stopped growing or transport flow control failed. Small rate/RSS changes are measured differences, not proof of a particular cause.','',
    '## Acceptance and limitations','',
    '- Sustained unbounded occupancy: repeated positive early/late and pooled queue/byte slopes support it for the finite 60 s load window.','- Queue/RSS correspondence: compare separately measured slopes and time series; observed joint growth supports correspondence, not heap attribution or byte-for-byte allocator identity.','- Bounded occupancy: K=32 plateau in every repetition; this is not a bound on all process memory.','- Backpressure: direct/bounded completed Send rates approach worker rates, with much longer Send calls than unbounded; no isolated transport-wait duration is inferred.','- Repeatability: five release-build offered intervals per variant, with original resource/time limits and all deadline outcomes retained. This does not mean fifteen successful, fully drained RPCs.','',
    'Remaining limits: single localhost host, fixed windows, sleep-based service, five-run ranges rather than confidence intervals, source/duration/profile/telemetry confounding, observer overhead, periodic RSS/CPU/counter sampling, no isolated HTTP/2 wait, no new wire trace/packet capture, no allocator/live-heap attribution, no independent-machine reproduction, and V1 drain censored by the unchanged deadline. The client binary was built from dirty pre-freeze source content, whose hashes match the pinned commit; embedded Go VCS metadata alone is insufficient provenance.','',
    'A separately approved follow-up could extend only the drain deadline (not weaken memory limits) to measure full unbounded reconciliation/post-drain RSS, and use a factorial comparison to isolate release/source/duration effects. That follow-up was **not executed**. No adaptive concurrency or blog content was started.','']
    (BASE/'EXTENSION-001B-REPORT.md').write_text('\n'.join(lines))
    commands=['# E1B exact recorded child commands','', 'All commands below were executed by the runner. Full workload, environment, limits and outcomes remain in each linked manifest.','']
    import shlex
    for folder in sorted((OUT/'runs').iterdir()):
        if not (folder/'manifest.json').exists():continue
        m=json.loads((folder/'manifest.json').read_text());commands += ['## '+m['name'],'',f"Git: `{m['git_commit']}`; cwd: `{m['cwd']}`; runtime `RUST_LOG=warn`.",'','```sh',shlex.join(m['server_command']),shlex.join(m['client_command']),'```','']
    (OUT/'COMMANDS.md').write_text('\n'.join(commands))
    inputs=[p for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256SUMS']+[BASE/'EXTENSION-001B.md',BASE/'EXTENSION-001B-REPORT.md']+list((BASE/'e1b').glob('*.py'))+[ROOT/'loadgen/cmd/loadgen/main.go',ROOT/'loadgen/cmd/loadgen/main_test.go']
    (OUT/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT)}\n' for p in sorted(inputs)))
    print(json.dumps(audit,indent=2))
if __name__=='__main__':main()
