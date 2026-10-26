# Experiment 001 — evidence index

Start with the [frozen specification](EXPERIMENT-001.md), [research report](REPORT.md), and [audit/provenance caveats](review/PROVENANCE.md). This package organizes existing evidence only. **No benchmarks, builds, tests, or new application features were run/implemented during this audit.**

## What is ready to review

| Material | Location |
|---|---|
| Hypothesis, falsification triggers, acceptance/publication criteria | [EXPERIMENT-001.md](EXPERIMENT-001.md) |
| Measured findings, figures, exclusions and limitations | [REPORT.md](REPORT.md) |
| Architecture/ownership decisions and milestone status | [DECISIONS.md](DECISIONS.md), [MILESTONE-STATUS.md](MILESTONE-STATUS.md) |
| Implementation-specific flow-control source audit | [SOURCE-AUDIT.md](SOURCE-AUDIT.md) |
| Workload/transport/safety configuration | [primary.json](config/primary.json), individual manifests below |
| Exact recorded server/client argument lists, transcribed for review | [COMMANDS.md](review/COMMANDS.md) |
| OS/kernel, compiler versions, dependency graph, debug profile | [environment.json](results/environment.json), [Cargo.lock](../../server/Cargo.lock), [go.sum](../../loadgen/go.sum) |
| Git archival SHA versus missing execution SHA; integrity/access caveats | [PROVENANCE.md](review/PROVENANCE.md) |
| Read-only audit of all 28 runs | [AUDIT.json](review/AUDIT.json), [verification script](review/verify.py) |
| Byte-integrity inventory | [SHA256SUMS](review/SHA256SUMS) |
| Per-run derived values and medians/ranges | [analysis.json](results/e1/analysis.json), [analysis script](analyze.py) |
| Randomized primary run order | [run-order.json](results/e1/run-order.json) |
| Application comparison | [PNG](results/e1/comparison.png), [SVG](results/e1/comparison.svg), [plot script](plot.py) |
| Separate transport diagnostics | [summary JSON](results/e1/transport-summary.json), [PNG](results/e1/transport.png), [SVG](results/e1/transport.svg), [parser](transport.py) |
| Original execution/reproduction instructions | [README.md](README.md), [runner](run.py) |
| Final retained validation logs (historical, not rerun) | [tests](results/final-tests.log), [Clippy](results/final-clippy.log), [bootstrap](results/final-bootstrap.log) |

## Executed versus planned

The read-only audit found all seven companion files for **28 recorded runs**, zero process/RPC errors in these retained runs, and five included overload repetitions per variant. It independently cross-checks cumulative ownership accounting and recomputes producer/consumer/queue slopes from existing CSVs. The excluded run remains excluded despite otherwise successful completion.

| Recorded activity | Executed evidence | Disposition |
|---|---|---|
| Fast-consumer sender calibration | 3 variants × 3 s, 300/s, 1 ms service | Executed, separate from overload |
| Below-capacity baseline | 3 variants × 4 s, 50/s, 10 ms service | Executed; 200 messages received/processed each |
| Saturated worker calibration | Direct, 3 s, 1000/s offered, 10 ms service | Executed |
| Primary short overload | 16 records, 12 s offered at 300/s, then drain | 15 included: 5 per variant; one provenance exclusion with replacement |
| h2 instrumentation | Unbounded and bounded, separate 4 s workloads | Executed; debug frame events, not packets |
| Final hardened-source smoke | 3 variants × 1 s at 300/s | Executed; not primary repeats |
| Proposed 60 s overload / release-build comparison | No matching dataset | **Not executed** |
| K=1 and K=128 sensitivity diagnostics | No matching dataset | **Not executed**; primary K=32 only |
| 10 s traffic warmup | Not used | Replaced by independent calibration and fresh idle server; documented protocol |
| On-wire packet capture, live heap attribution, independent-machine reproduction | No artifacts | **Not executed / absent** |
| Safety abort and cancellation cases | Historical integration test log | Tests executed; temporary per-test raw CSVs were not archived |

No Blog 2/adaptive-concurrency experiments are included.

## Metric coverage and meaning

| Requested evidence | Raw/derived fields | Qualification |
|---|---|---|
| Producer rate | client.csv `scheduled`, `attempts`, `completed`, `skipped`, `elapsed_s`; client.json rate/duration/completed_sends; analysis `steady_send_rate` | Offered, attempted and completed Sends differ; no wire-delivery claim |
| Consumer rate | server.csv `processed`, `elapsed_s`, `service_ns`; analysis `processed_rate`, `worker_capacity` | Measured completions, not nominal 10 ms inverse |
| Queue depth/owned bytes | server.csv `queue_depth`, `queue_bytes`, `enqueued`, `dequeued`, `handler_bytes`, `worker_bytes` | Samples every ~200 ms; ownership consistency checked; not a complete heap inventory |
| RSS and CPU | server/client CSV `rss_bytes`; process.csv RSS, CPU ticks, CLK_TCK, threads | OS RSS, not attributable live heap; CPU averages can include drain |
| Producer blocking proxy | client.csv `send_ns`, `blocked_gt20ms`; client.json `send_total_ns`, Send p50/p95/p99 | **Time inside Send**, including overhead; isolated transport wait not recorded. >20 ms median fraction is zero despite measurable ~12 ms pressure |
| Workload/safety/transport | manifest rate, seconds, payload, seed, service_ms, capacity, windows, limits, deadlines, compression and runtime threads | Exact arguments are retained; binary/source hashes are selected-input provenance, not execution Git SHA |

Primary slopes: server elapsed 2.5–10.5 s; client elapsed 2–10 s. The plot uses an approximate 0.4 s offset only for visualization. Report ranges are observed min/max across five runs, not confidence intervals.

## Complete raw run catalog

Each row links every raw companion file. An empty `client.log` is expected on success because structured output is written to client.json/CSV. Manifests retain start time, exact command arrays, workload settings, exit statuses, and selected source/binary hashes. Follow raw-log links for download if the repository viewer refuses large text rendering.

| Run | Class / disposition | Manifest | Server samples | Client samples / summary | OS process samples | Raw logs |
|---|---|---|---|---|---|---|
| control-bounded | Below-capacity control | [JSON](results/e1/control-bounded/manifest.json) | [CSV](results/e1/control-bounded/server.csv) | [CSV](results/e1/control-bounded/client.csv) / [JSON](results/e1/control-bounded/client.json) | [CSV](results/e1/control-bounded/process.csv) | [server](results/e1/control-bounded/server.log) / [client](results/e1/control-bounded/client.log) |
| control-direct | Below-capacity control | [JSON](results/e1/control-direct/manifest.json) | [CSV](results/e1/control-direct/server.csv) | [CSV](results/e1/control-direct/client.csv) / [JSON](results/e1/control-direct/client.json) | [CSV](results/e1/control-direct/process.csv) | [server](results/e1/control-direct/server.log) / [client](results/e1/control-direct/client.log) |
| control-unbounded | Below-capacity control | [JSON](results/e1/control-unbounded/manifest.json) | [CSV](results/e1/control-unbounded/server.csv) | [CSV](results/e1/control-unbounded/client.csv) / [JSON](results/e1/control-unbounded/client.json) | [CSV](results/e1/control-unbounded/process.csv) | [server](results/e1/control-unbounded/server.log) / [client](results/e1/control-unbounded/client.log) |
| diagnostic-bounded | Separate h2 diagnostic | [JSON](results/e1/diagnostic-bounded/manifest.json) | [CSV](results/e1/diagnostic-bounded/server.csv) | [CSV](results/e1/diagnostic-bounded/client.csv) / [JSON](results/e1/diagnostic-bounded/client.json) | [CSV](results/e1/diagnostic-bounded/process.csv) | [server](results/e1/diagnostic-bounded/server.log) / [client](results/e1/diagnostic-bounded/client.log) |
| diagnostic-unbounded | Separate h2 diagnostic | [JSON](results/e1/diagnostic-unbounded/manifest.json) | [CSV](results/e1/diagnostic-unbounded/server.csv) | [CSV](results/e1/diagnostic-unbounded/client.csv) / [JSON](results/e1/diagnostic-unbounded/client.json) | [CSV](results/e1/diagnostic-unbounded/process.csv) | [server](results/e1/diagnostic-unbounded/server.log) / [client](results/e1/diagnostic-unbounded/client.log) |
| overload-1-bounded | Included overload | [JSON](results/e1/overload-1-bounded/manifest.json) | [CSV](results/e1/overload-1-bounded/server.csv) | [CSV](results/e1/overload-1-bounded/client.csv) / [JSON](results/e1/overload-1-bounded/client.json) | [CSV](results/e1/overload-1-bounded/process.csv) | [server](results/e1/overload-1-bounded/server.log) / [client](results/e1/overload-1-bounded/client.log) |
| overload-1-direct | Excluded provenance; replaced by overload-6-direct | [JSON](results/e1/overload-1-direct/manifest.json) | [CSV](results/e1/overload-1-direct/server.csv) | [CSV](results/e1/overload-1-direct/client.csv) / [JSON](results/e1/overload-1-direct/client.json) | [CSV](results/e1/overload-1-direct/process.csv) | [server](results/e1/overload-1-direct/server.log) / [client](results/e1/overload-1-direct/client.log) |
| overload-1-unbounded | Included overload | [JSON](results/e1/overload-1-unbounded/manifest.json) | [CSV](results/e1/overload-1-unbounded/server.csv) | [CSV](results/e1/overload-1-unbounded/client.csv) / [JSON](results/e1/overload-1-unbounded/client.json) | [CSV](results/e1/overload-1-unbounded/process.csv) | [server](results/e1/overload-1-unbounded/server.log) / [client](results/e1/overload-1-unbounded/client.log) |
| overload-2-bounded | Included overload | [JSON](results/e1/overload-2-bounded/manifest.json) | [CSV](results/e1/overload-2-bounded/server.csv) | [CSV](results/e1/overload-2-bounded/client.csv) / [JSON](results/e1/overload-2-bounded/client.json) | [CSV](results/e1/overload-2-bounded/process.csv) | [server](results/e1/overload-2-bounded/server.log) / [client](results/e1/overload-2-bounded/client.log) |
| overload-2-direct | Included overload | [JSON](results/e1/overload-2-direct/manifest.json) | [CSV](results/e1/overload-2-direct/server.csv) | [CSV](results/e1/overload-2-direct/client.csv) / [JSON](results/e1/overload-2-direct/client.json) | [CSV](results/e1/overload-2-direct/process.csv) | [server](results/e1/overload-2-direct/server.log) / [client](results/e1/overload-2-direct/client.log) |
| overload-2-unbounded | Included overload | [JSON](results/e1/overload-2-unbounded/manifest.json) | [CSV](results/e1/overload-2-unbounded/server.csv) | [CSV](results/e1/overload-2-unbounded/client.csv) / [JSON](results/e1/overload-2-unbounded/client.json) | [CSV](results/e1/overload-2-unbounded/process.csv) | [server](results/e1/overload-2-unbounded/server.log) / [client](results/e1/overload-2-unbounded/client.log) |
| overload-3-bounded | Included overload | [JSON](results/e1/overload-3-bounded/manifest.json) | [CSV](results/e1/overload-3-bounded/server.csv) | [CSV](results/e1/overload-3-bounded/client.csv) / [JSON](results/e1/overload-3-bounded/client.json) | [CSV](results/e1/overload-3-bounded/process.csv) | [server](results/e1/overload-3-bounded/server.log) / [client](results/e1/overload-3-bounded/client.log) |
| overload-3-direct | Included overload | [JSON](results/e1/overload-3-direct/manifest.json) | [CSV](results/e1/overload-3-direct/server.csv) | [CSV](results/e1/overload-3-direct/client.csv) / [JSON](results/e1/overload-3-direct/client.json) | [CSV](results/e1/overload-3-direct/process.csv) | [server](results/e1/overload-3-direct/server.log) / [client](results/e1/overload-3-direct/client.log) |
| overload-3-unbounded | Included overload | [JSON](results/e1/overload-3-unbounded/manifest.json) | [CSV](results/e1/overload-3-unbounded/server.csv) | [CSV](results/e1/overload-3-unbounded/client.csv) / [JSON](results/e1/overload-3-unbounded/client.json) | [CSV](results/e1/overload-3-unbounded/process.csv) | [server](results/e1/overload-3-unbounded/server.log) / [client](results/e1/overload-3-unbounded/client.log) |
| overload-4-bounded | Included overload | [JSON](results/e1/overload-4-bounded/manifest.json) | [CSV](results/e1/overload-4-bounded/server.csv) | [CSV](results/e1/overload-4-bounded/client.csv) / [JSON](results/e1/overload-4-bounded/client.json) | [CSV](results/e1/overload-4-bounded/process.csv) | [server](results/e1/overload-4-bounded/server.log) / [client](results/e1/overload-4-bounded/client.log) |
| overload-4-direct | Included overload | [JSON](results/e1/overload-4-direct/manifest.json) | [CSV](results/e1/overload-4-direct/server.csv) | [CSV](results/e1/overload-4-direct/client.csv) / [JSON](results/e1/overload-4-direct/client.json) | [CSV](results/e1/overload-4-direct/process.csv) | [server](results/e1/overload-4-direct/server.log) / [client](results/e1/overload-4-direct/client.log) |
| overload-4-unbounded | Included overload | [JSON](results/e1/overload-4-unbounded/manifest.json) | [CSV](results/e1/overload-4-unbounded/server.csv) | [CSV](results/e1/overload-4-unbounded/client.csv) / [JSON](results/e1/overload-4-unbounded/client.json) | [CSV](results/e1/overload-4-unbounded/process.csv) | [server](results/e1/overload-4-unbounded/server.log) / [client](results/e1/overload-4-unbounded/client.log) |
| overload-5-bounded | Included overload | [JSON](results/e1/overload-5-bounded/manifest.json) | [CSV](results/e1/overload-5-bounded/server.csv) | [CSV](results/e1/overload-5-bounded/client.csv) / [JSON](results/e1/overload-5-bounded/client.json) | [CSV](results/e1/overload-5-bounded/process.csv) | [server](results/e1/overload-5-bounded/server.log) / [client](results/e1/overload-5-bounded/client.log) |
| overload-5-direct | Included overload | [JSON](results/e1/overload-5-direct/manifest.json) | [CSV](results/e1/overload-5-direct/server.csv) | [CSV](results/e1/overload-5-direct/client.csv) / [JSON](results/e1/overload-5-direct/client.json) | [CSV](results/e1/overload-5-direct/process.csv) | [server](results/e1/overload-5-direct/server.log) / [client](results/e1/overload-5-direct/client.log) |
| overload-5-unbounded | Included overload | [JSON](results/e1/overload-5-unbounded/manifest.json) | [CSV](results/e1/overload-5-unbounded/server.csv) | [CSV](results/e1/overload-5-unbounded/client.csv) / [JSON](results/e1/overload-5-unbounded/client.json) | [CSV](results/e1/overload-5-unbounded/process.csv) | [server](results/e1/overload-5-unbounded/server.log) / [client](results/e1/overload-5-unbounded/client.log) |
| overload-6-direct | Included overload | [JSON](results/e1/overload-6-direct/manifest.json) | [CSV](results/e1/overload-6-direct/server.csv) | [CSV](results/e1/overload-6-direct/client.csv) / [JSON](results/e1/overload-6-direct/client.json) | [CSV](results/e1/overload-6-direct/process.csv) | [server](results/e1/overload-6-direct/server.log) / [client](results/e1/overload-6-direct/client.log) |
| sender-calibration-bounded | Sender calibration | [JSON](results/e1/sender-calibration-bounded/manifest.json) | [CSV](results/e1/sender-calibration-bounded/server.csv) | [CSV](results/e1/sender-calibration-bounded/client.csv) / [JSON](results/e1/sender-calibration-bounded/client.json) | [CSV](results/e1/sender-calibration-bounded/process.csv) | [server](results/e1/sender-calibration-bounded/server.log) / [client](results/e1/sender-calibration-bounded/client.log) |
| sender-calibration-direct | Sender calibration | [JSON](results/e1/sender-calibration-direct/manifest.json) | [CSV](results/e1/sender-calibration-direct/server.csv) | [CSV](results/e1/sender-calibration-direct/client.csv) / [JSON](results/e1/sender-calibration-direct/client.json) | [CSV](results/e1/sender-calibration-direct/process.csv) | [server](results/e1/sender-calibration-direct/server.log) / [client](results/e1/sender-calibration-direct/client.log) |
| sender-calibration-unbounded | Sender calibration | [JSON](results/e1/sender-calibration-unbounded/manifest.json) | [CSV](results/e1/sender-calibration-unbounded/server.csv) | [CSV](results/e1/sender-calibration-unbounded/client.csv) / [JSON](results/e1/sender-calibration-unbounded/client.json) | [CSV](results/e1/sender-calibration-unbounded/process.csv) | [server](results/e1/sender-calibration-unbounded/server.log) / [client](results/e1/sender-calibration-unbounded/client.log) |
| worker-calibration | Worker calibration | [JSON](results/e1/worker-calibration/manifest.json) | [CSV](results/e1/worker-calibration/server.csv) | [CSV](results/e1/worker-calibration/client.csv) / [JSON](results/e1/worker-calibration/client.json) | [CSV](results/e1/worker-calibration/process.csv) | [server](results/e1/worker-calibration/server.log) / [client](results/e1/worker-calibration/client.log) |
| final-bounded | Final hardened-source smoke | [JSON](results/final-smoke/final-bounded/manifest.json) | [CSV](results/final-smoke/final-bounded/server.csv) | [CSV](results/final-smoke/final-bounded/client.csv) / [JSON](results/final-smoke/final-bounded/client.json) | [CSV](results/final-smoke/final-bounded/process.csv) | [server](results/final-smoke/final-bounded/server.log) / [client](results/final-smoke/final-bounded/client.log) |
| final-direct | Final hardened-source smoke | [JSON](results/final-smoke/final-direct/manifest.json) | [CSV](results/final-smoke/final-direct/server.csv) | [CSV](results/final-smoke/final-direct/client.csv) / [JSON](results/final-smoke/final-direct/client.json) | [CSV](results/final-smoke/final-direct/process.csv) | [server](results/final-smoke/final-direct/server.log) / [client](results/final-smoke/final-direct/client.log) |
| final-unbounded | Final hardened-source smoke | [JSON](results/final-smoke/final-unbounded/manifest.json) | [CSV](results/final-smoke/final-unbounded/server.csv) | [CSV](results/final-smoke/final-unbounded/client.csv) / [JSON](results/final-smoke/final-unbounded/client.json) | [CSV](results/final-smoke/final-unbounded/process.csv) | [server](results/final-smoke/final-unbounded/server.log) / [client](results/final-smoke/final-unbounded/client.log) |

Other retained preparation and failed-check logs are under [results/](results/), including the [initial missing-checksum Go failure](results/m1-go-test.log), [Rust inference build failure](results/runtime-build.log), [initial Clippy failure](results/runtime-clippy.log), [historical integration log](results/runtime-integration.log), [calibration runner log](results/calibration-runner.log), [primary runner log](results/measured-runner.log), and [diagnostic runner log](results/diagnostic-runner.log). Passing later checks do not erase those records. `runs/` and `traces/` contain placeholders, not an additional benchmark or packet dataset.

## Gaps that remain

1. **Execution Git SHA was not captured.** The archive baseline and implementation commits are recorded in PROVENANCE.md; neither can honestly be labeled the measured commit. Matching selected source snapshots/hashes are available. Original measured executables and a complete build-input snapshot are not archived.
2. Primary measurements are **12 s debug-build, pre-final-cancellation-hardening** runs. Final code has tests and smoke evidence, but no new five-run primary dataset. Longer release-mode and final-source results remain planned.
3. There is **no isolated transport-blocking-time measurement**, packet capture, precise cross-process timing synchronization, live heap attribution, service-time percentile histogram, or live Prometheus export. h2 debug events and source review provide narrower transport evidence.
4. Controls have one short run per variant; primary variation is five-run min/max, not a statistical confidence analysis. No independent host reproduction or K sensitivity dataset exists.
5. Per-test cancellation/safety raw files were temporary and are missing from the archive; retained test logs and test source show what was asserted, not a reconstructable raw abort dataset.
6. A private repository requires reviewer read access. Original evidence was already present on remote main at audit time; this alone cannot prove reviewer authorization. No access/permission change was made.

The existing data is ready for a scoped independent review; these gaps constrain publication claims. No new measurements were requested or performed to fill them.
