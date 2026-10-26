# EXPERIMENT-001B — Release-Build Sustained Overload Validation

## Decision and scope

Independent review decision supplied by the user: **EXTEND**. Baseline evidence commit: `3374f126e3009991ec97c95e64dabd03c734b575`. No separate independent-review document was found in the repository. Read the [E1 specification](EXPERIMENT-001.md), [report](REPORT.md), [evidence index](EVIDENCE-INDEX.md), and provenance notes before interpreting this extension.

Test whether E1's application-level findings persist with the final hardened server source, an optimized Rust release build, and 60 seconds of offered overload. No adaptive concurrency, transport-window change, retries, or blog writing. Preserve every E1 raw artifact byte-for-byte. New artifacts go only under `results/e1b/`.

## Fixed workload and deliberate differences

| Parameter | E1B value |
|---|---|
| Variants | Direct; unbounded Tokio MPSC; bounded Tokio MPSC K=32 |
| Offered workload | 300 scheduled messages/s, 16,384-byte deterministic pseudorandom payload, seed 1 |
| Worker | One worker, configured 10 ms sleep; direct variant processes serially in handler |
| Runtime | Two Tokio worker threads; Go GOMAXPROCS=2 |
| Windows | Server stream/connection 65,535 bytes each; adaptive disabled; client receive windows 65,535 each |
| Compression/retries/message limit | Off/off/1 MiB |
| Pacing | Single sequential sender, missed slots skipped/countable, no catch-up bursts |
| Warmup | No traffic warmup; separate preflight and fresh idle process per run |
| Offered duration | **60 seconds**, replacing E1's 12 seconds |
| Build | **Rust release** (`cargo build --release --locked -j 4`); Go remains default optimized build |
| Source | Final hardened server unchanged from baseline; optional Go observer telemetry added without modifying workload/transport logic |
| Replication | Five fresh processes per variant, shuffled within each repetition, PRNG seed 1 |

The additional Go `--telemetry` output records sampled cumulative Send p50/p95/p99 and wall timestamps from the existing sampler; a copied latency snapshot is sorted outside the sender-statistics lock. This is an explicit observability difference, not an unmentioned workload change. A same-host external collector records CSV export visibility brackets and server/client OS samples against a shared monotonic clock. Native counters remain separately available; collection synchronization is not proof of exact network event timing. The full source/harness commit, dirty status, all selected source files, binaries and exact command arrays are captured per run. Source/harness changes are committed before primary runs and must remain unchanged during execution.

## Safety and lifecycle, unchanged deadline

Retain E1's **256 MiB queued-payload cap**, **512 MiB server RSS cap**, and **120 s whole-RPC deadline**. Server queue enforcement occurs before enqueue; RSS is sampled every ~200 ms. Supplemental runner guards cap client RSS at 128 MiB, wall lifetime at 125 s, CPU time at 120 s per process, each output file at 64 MiB and core dumps at zero. Resource guards never expand E1's limits. Fresh processes run sequentially; no concurrent experiment workloads.

The inspected host has a 32 GiB cgroup limit and ~28 GiB free workspace disk. At E1's roughly 210 messages/s queue surplus, 60 seconds is projected to retain ~197 MiB queued payload, below the existing cap; projected RSS is below 512 MiB. These are preflight estimates, not results. Stop on any actual RSS/queue/resource guard or unexplained failure and retain partial files. Do not lower offered rate, shrink payloads, shorten duration, change windows, or increase limits to make the test pass.

**Expected lifecycle limitation:** 18,000 admitted messages need about 200 seconds to process at E1's ~90/s worker rate. The unchanged 120 s whole-RPC deadline is therefore expected to cancel unbounded drain after a full 60 s offered interval. Retain these as explicit deadline-aborted runs, not completed/drained successes. The 60 s overload interval may answer queue/throughput questions, but cannot establish complete drain or post-drain RSS for V1. Do not replace these outcomes or extend the deadline silently.

## Predeclared sequence and analysis

1. Build release server and instrumented client; run existing process integration tests against those binaries and the client percentile unit test.
2. Separate preflight: three 3 s fast-worker sender calibrations (300/s, 1 ms service), three 4 s controls (50/s, 10 ms service), one 3 s direct-worker calibration (1000/s). Confirm sender capacity >=285/s, no sustained control backlog, and accounting consistency.
3. Freeze/commit source and harness; save compiler/linker/OS/kernel/resource details, build commands and hashes. Primary measurements record their actual pinned commit and full dirty status (new result files may make the overall tree dirty; source must remain clean).
4. Run five shuffled fresh-process repetitions per variant, each 60 s offered load. Retain all deadline/error/guard outcomes. The unchanged deadline is not grounds to pretend V1 drained; an early safety abort is a blocker.
5. Primary steady window: **5–55 seconds after client start**, using shared-host timestamps/export-origin estimates with recorded uncertainty. Also compute native per-process-window slopes; retain cumulative raw samples and synchronized observer rows. Plot the complete 60 s offered interval and later drain/cancellation separately.
6. Derive attempted/completed Send rates, worker throughput, queue/byte and RSS slopes, maxima, CPU, cumulative Send duration and calls >20 ms, cumulative latency percentiles. Report each run and medians/min/max; no confidence-interval claim from five samples. Compare native early/late windows to check continued growth, not just a pooled slope.
7. Compare E1 and E1B descriptively. Build profile, duration, hardened-server version, client telemetry, host/time effects and censored V1 drain are confounded; this is not a factorial estimate of each cause.

Acceptance concerns the sustained offered interval: repeated positive V1 queue/byte slopes, correspondence with RSS growth where observed, V2 depth <=32/plateau, and V0/V2 Send completions near measured worker throughput. Never equate Send call duration to isolated HTTP/2 blocking, owned queue bytes to all heap allocations, or a bounded queue to bounded process memory. No new packet-level transport claim is planned.

## Commands

From `/workspace/grpc-under-pressure`, after `source scripts/dev-env.sh`:

```sh
cargo build --release --locked --manifest-path server/Cargo.toml -j 4
(cd loadgen && go test -mod=readonly -v ./...)
(cd loadgen && go build -mod=readonly -o /workspace/toolchains/bin/pressure-loadgen-e1b ./cmd/loadgen)
python3 experiments/001/e1b/run.py --phase preflight
# Commit protocol/harness/telemetry before measured phase; record resulting SHA.
python3 experiments/001/e1b/run.py --phase measured
python3 experiments/001/e1b/analyze.py
```

Runner output directories are exclusive-create and never overwrite an earlier run. Historical E1 analysis and raw data are read-only inputs. See the extension report for actual execution outcomes and any deviation from this predeclared plan.
