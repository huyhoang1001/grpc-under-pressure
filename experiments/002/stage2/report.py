#!/usr/bin/env python3
"""Render the Stage 2 report from retained results; never executes workloads."""
import json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'results/stage2'
x=json.loads((OUT/'analysis.json').read_text())
r=next(v for v in x['runs'] if v['purpose']=='single_exploratory_slowdown_recovery')
old=json.loads((OUT/'historical-integrity.json').read_text())
ov=x['overhead']
text=f"""# Experiment 002 — Stage 2 report

**Stage 2 completed: the frozen fixed32 workload produced the intended capacity disturbance and recovered.** Exactly one exploratory 36-second run was executed, without adjusting parameters afterward. No fixed8, dynamic budget, adaptive controller, primary five-repeat matrix, or article was added.

Baseline: accepted Stage 1 commit `b92d2c77a64714de99694a8e0561ffc94d0276a2`. Measured application/harness commit: `{r['source_commit']}`. The [frozen contract](EXPERIMENT-002.md) is unchanged. **{old['files_unchanged']} historical files** match the baseline byte-for-byte, covering E1/E1B and Stage 1 raw evidence/report/README/contract; see [historical-integrity.json](results/stage2/historical-integrity.json).

## Files changed

- `server/mod.rs`: opt-in contract schedule, monotonic service-start selection, selected-delay metadata, actual phase markers, completed-service/queue observation sums, and event-format/write/flush wall timers. Default remains Stage 1 constant 10 ms. Discard event destination is explicitly control-only.
- `server/tests.rs`: four targeted tests for exact boundaries/drain, start versus enqueue/completion selection, failure wakeup during slowdown, and sink equivalence. Existing cancellation/EOF/accounting/bounded-storage tests remain.
- `stage2/run.py`, `analyze.py`, `report.py`, [README.md](stage2/README.md): exclusive-create runner, overhead-before-exploration gate, one-attempt guard, predeclared analysis and reproducible report. Post-run edits clarified actor-local drain and slot/Send-return phase attribution, omitted unexecuted full phase windows from short controls, and rendered this report; measured binaries and inputs were unchanged.
- `results/stage2/` and this report: all controls, smoke/integration and exploratory evidence, ledgers, manifests, environment, checks and graphs. No Go client, dependency declaration, lockfile, protocol, E1/E1B source/report/data, or historical Stage 1 report/data was changed.

The worker selects 10 ms before t=12 s, 40 ms for service starts in [12,24), and 10 ms at every start >=24 s, including drain. An executing job is never retimed. Enqueue-phase histogram assignment remains independent of service-start phase. K/static pending limit stay 32; reservation ordering, EOF release, terminal disposition, busy/idle accounting and 200 ms collection remain. Phase-log I/O errors signal terminal failure rather than silently continuing.

## Commands and checks

Executed from `/workspace/grpc-under-pressure` after `source scripts/dev-env.sh`:

```sh
cargo build --locked --manifest-path server/Cargo.toml -j4
cargo test --locked --manifest-path server/Cargo.toml -j4
cargo clippy --locked --manifest-path server/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path server/Cargo.toml -- --check
(cd experiments/002/client && go mod verify && go test -mod=readonly -race -v ./... && go vet ./...)
(cd experiments/002/client && go build -mod=readonly -o /workspace/toolchains/bin/pressure-stage1-client .)
# Source frozen as 8450954 before collecting measurements.
python3 experiments/002/smoke.py --output experiments/002/results/stage2/stage1-regression
python3 experiments/002/stage2/run.py --output experiments/002/results/stage2 --phase smoke
python3 experiments/002/stage2/run.py --output experiments/002/results/stage2 --phase overhead
python3 experiments/002/stage2/analyze.py experiments/002/results/stage2
python3 experiments/002/stage2/run.py --output experiments/002/results/stage2 --phase exploratory
MPLCONFIGDIR=/workspace/toolchains/matplotlib python3 experiments/002/stage2/analyze.py experiments/002/results/stage2
python3 experiments/002/stage2/report.py
```

**20 Rust tests passed** (16 E2 including four additions, plus four original protocol/channel tests); **four E2 Go tests passed with race detection**. Build, formatting, warnings-denied Clippy, Go vet and module verification passed. Six Stage 1 lifecycle fixtures and a short opt-in schedule fixture passed before collection. Synthetic tests cover real 12/24/36 s decisions without accelerating the exploratory schedule. [Check logs](results/stage2/checks/) retain actual output. Zero-test doc/generated packages are not counted.

Every buffered run passed the Stage 1 verifier: physical/counter/byte invariants, reservations, exact timestamp differences, histogram reconstruction and unique final message dispositions. Every selected delay was also checked against its service-start timestamp. Controls, integration and exploratory outcomes are retained; [ledger](results/stage2/ledger.jsonl). No invalid run was replaced or hidden. Discard controls intentionally lack per-message events, and are not full experiment evidence.

## Observer assessment before exploration

Four fresh constant-10-ms, 80/s, 4-second controls ran **buffered, discard, discard, buffered**. Each processed all 320 scheduled messages. Discard retains formatting, the 64 KiB buffer, histograms, locks, counters and sampling; only the event destination changes to a no-retention sink. Aggregate byte/counter/histogram/final Summary checks passed. [Pre-exploration assessment](results/stage2/checks/overhead-assessment-before-exploratory.log) and order are retained.

| Observation: median [min,max], two cases/mode | Buffered file | Discard sink |
|---|---:|---:|
"""
for label,key,scale,d in [
 ('Timed event write+flush / worker-observed wall (%)','timed_event_io_fraction',100,4),
 ('Event formatting/write total (ms)','event_format_write_ms',1,3),
 ('Event flush total (ms)','event_flush_ms',1,3),
 ('Largest flush (microseconds)','event_flush_max_us',1,3),
 ('Actual completed-service mean (ms)','service_mean_ms',1,4),
 ('Service p95 upper histogram bucket (ms)','service_p95_upper_ms',1,4)]:
    values=[]
    for mode in ['buffered','discard']:
        v=ov[mode][key];values.append(f"{v['median']*scale:.{d}f} [{v['min']*scale:.{d}f}, {v['max']*scale:.{d}f}]")
    text+='| '+label+' | '+' | '.join(values)+' |\n'
text+=f"""
Buffered flushes cost more, but discard was not consistently faster in every component; means overlap and the approximate p95 bucket is identical. Two offered-limited controls per mode do not establish saturated-capacity loss, statistical confidence, or zero overhead. Timers cover writeln/buffered-write and flush portions under the lock, not all field preparation, timer bookkeeping, histogram/check/snapshot work, other I/O or contention. Wall time can include descheduling. Flush is an OS/page-cache write, not fsync/durable-disk latency.

In the exploratory run the timed portions totaled **{r['event_format_write_ms']:.3f} ms** formatting/write plus **{r['event_flush_ms']:.3f} ms** flush: **{r['timed_event_io_fraction']*100:.4f}%** of worker-observed time. Largest write/format and flush were {r['event_write_max_us']:.3f} and {r['event_flush_max_us']:.3f} microseconds. I/O under the lock can still delay admission/dequeue/completion and inflate measured service/residence. These are partial observer costs, not a total overhead bound; the caveat remains for later policy comparisons.

## Workload and reproducibility

One fixed32 run: 80 scheduled slots/s for 36 s; 16,384-byte seeded pseudorandom payloads; one connection/stream/handler/worker; two Tokio workers/GOMAXPROCS=2; 65,535-byte stream/connection windows; server adaptive windows off; no retries/compression; 1 MiB message limit; same debug-Rust/default-optimized-Go build and inherited CPU placement as controls. [Environment](results/stage2/environment.json) records compilers, dependencies, OS/kernel, cgroup, affinity and hashes.

Manifests retain exact child command arrays, Git SHA/dirty state, input/binary hashes, parameters, clock offsets and exits. Binaries and inherited affinity are identical across four controls, the short schedule fixture and exploratory run; [integrity check](results/stage2/run-integrity.json). New results make the overall tree dirty; source inputs stayed unchanged and match pinned Git objects. Historical full-package checksums describe baseline source, not the intentionally extended current server.

Guards remain 512 MiB server RSS, 128 MiB client RSS, 10 s process CPU, 16 MiB per file and no core dumps; RPC deadline stays 120 s from creation. External wall timeout is 125 s rather than the 12 s short-smoke guard, to encompass this scenario and its existing RPC deadline. No safety guard, forced shutdown, RPC error or telemetry gap occurred.

## Phase transitions and measured behavior

Marker release alignment error: **{r['phase_alignment_ms']:.3f} ms**, below 100 ms. Logger wakeup is independent of the monotonic function choosing service delay.

| Boundary s | Observed marker s | Lateness ms | Configured delay ms |
|---:|---:|---:|---:|
"""
for v in r['phase_markers']:
    text+=f"| {int(v['scheduled_ns'])/1e9:.0f} | {int(v['observed_ns'])/1e9:.6f} | {int(v['lateness_ns'])/1e6:.3f} | {v['configured_ms']} |\n"
text+="""
First 40 ms service: **12.001448 s**. First recovery 10 ms service: **24.005989 s**. A job starting at **23.965018 s** kept its 40 ms choice and completed at **24.005964 s**, demonstrating selection at start rather than completion. No message began service at >=36 s: the retained 10 ms drain setting is logged/tested, not invented as a measured drain distribution.

| Metric | Healthy [0,12) | Slowdown [12,24) | Recovery [24,36) |
|---|---:|---:|---:|
"""
phases=[r['phases'][name] for name in ['healthy','slowdown','recovery']]
for label,func,d in [
 ('Actual service mean ms, grouped by start',lambda p:p['actual_service_ms_by_start']['mean'],3),
 ('Actual service p95 ms, grouped by start',lambda p:p['actual_service_ms_by_start']['p95'],3),
 ('Worker completions/s, by completion time',lambda p:p['completion_rate_s'],3),
 ('Successful Send returns/s, by return time',lambda p:p['return_rate_s'],3),
 ('Skipped scheduled slots',lambda p:p['skipped_scheduled_slots'],0),
 ('Maximum sampled physical Q',lambda p:p['Q_max'],0),
 ('Queue-residence p95 ms, grouped by enqueue',lambda p:p['queue_residence_ms_by_enqueue']['p95'],3),
 ('Send wall-duration p95 ms',lambda p:p['send_ms']['p95'],3)]:
    text+='| '+label+' | '+' | '.join(f'{func(p):.{d}f}' for p in phases)+' |\n'
text+=f"""
The slowdown was capacity-constrained: 80/s offered exceeded **24.25/s** worker completion, Q reached 32, Send durations increased, and 628 slowdown slots were skipped. One additional slot was skipped during recovery. Boundary-crossing jobs retain their start-selected delay; service is grouped by start, worker throughput by completion, Send-return throughput by return time, Send-duration distributions by call start, queue residence by enqueue, and skipped slots by planned slot phase.

After the delay returned, early recovery [24,28) completed **{r['early_recovery_completion_rate_s']:.2f}/s** while clearing backlog; late recovery [32,36) completed **{r['late_recovery_completion_rate_s']:.2f}/s**, near offered load. First sampled Q=0 after t=24: **{r['first_sampled_Q_zero_after24_s']:.6f} s**. Capacity recovery precedes queue-delay recovery. The pooled recovery p95 includes initial backlog and does not establish H4's three-second healthy-delay band or adaptive benefit.

Cumulative logical admission wait: **{r['logical_admission_wait_s']:.6f} s**; physical-acquisition wait/bookkeeping: **{r['physical_reservation_wait_s']*1000:.3f} ms**. Send calls consumed **{r['send_wall_duration_s']:.6f} s** wall time; {r['send_gt20ms_calls']} exceeded 20 ms and their whole durations summed to **{r['send_gt20ms_duration_s']:.6f} s**. These are backpressure indicators, not isolated HTTP/2 stalls or message end-to-end latency.

![Single exploratory service, queue, throughput, residence and skips](results/stage2/exploratory.png)

## Successful EOF/drain and work accounting

**{r['scheduled']} scheduled = {r['skipped']} skipped + {r['attempted']} attempted**. All **{r['successful_sends']} Sends succeeded**; failed Sends=0. Final received=admitted=dequeued=processed=Summary.accepted=Summary.processed=2251. Discarded and received-not-admitted=0; R=Q=W and payload-owner byte gauges=0. One accepted connection and stream; exactly one processed disposition per admitted sequence. Successful Sends remain distinct from server acknowledgments.

Client half-close: **{r['half_close_s']:.9f} s** on its workload clock. Server last service completion: **{r['last_completion_s']:.9f} s**; server EOF: **{r['server_eof_s']:.9f} s**; worker stop: **{r['server_worker_stop_s']:.9f} s**. Server-local EOF-to-worker-stop: **{r['server_eof_to_worker_stop_s']*1e6:.3f} microseconds**, since payload work was already complete before EOF. Worker-stop time comes from continuous busy+idle accounting, which freezes at exit; this excludes response/JoinHandle overhead. Client whole-RPC elapsed: **{r['rpc_s']:.6f} s**, including setup/marker wait, sends and response—not an inferred drain time of RPC duration minus 36. No cross-process monotonic subtraction invents per-message latency.

[Exploratory manifest/commands](results/stage2/exploratory-1/manifest.json) · [Analysis](results/stage2/analysis.json) · [Exact events](results/stage2/exploratory-1/server/events.csv) · [Transitions](results/stage2/exploratory-1/server/phase-transitions.csv) · [Send records](results/stage2/exploratory-1/client/sends.csv) · [Run output](results/stage2/checks/exploratory.log)

## Remaining limitations and decision

**No Stage 2 blocker remains.** This one run demonstrates the requested deterministic disturbance and successful fixed32 recovery/drain on this host. It does not establish repeatability, adaptive superiority, H2–H5, or bounded process memory. Periodic samples miss brief occupancy changes; source invariants and exact records supplement them. Marker alignment is not wire-event timing. Phase percentiles above use exact streams rather than approximate histogram upper bounds.

The small, healthy/offered-limited I/O study does not isolate all instrumentation or storage-tail overhead and must not be generalized to another host or a primary policy comparison. No workload retuning, second exploratory attempt, primary matrix, later policy or blog work was performed.
"""
(BASE/'STAGE2-REPORT.md').write_text(text)
