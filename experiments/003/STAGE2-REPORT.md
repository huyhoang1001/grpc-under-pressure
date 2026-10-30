# Experiment 003 — Stage 2 single-client policy correctness

**Verdict: PASS for Stage 2 correctness (T01–T20). Stop for independent review.** All four strategies use the same bounded Rust admission/worker/response implementation. The Go scheduler and bounded retries pass deterministic ledger tests, actual gRPC fixtures and race detection. No primary workload, policy performance comparison or Blog 3 was run.

**Experimental-design blocker for a later policy comparison:** the frozen single-client outstanding limit32 equals server admission32. In a healthy conforming stream, every occupied server slot belongs to an outstanding client attempt. An admitted attempt's terminal outcome is generated only after queued removal/worker exit; client credit is released only on its terminal response. Thus server occupancy cannot exceed client outstanding, and no33rd outstanding attempt can reach a full32-slot server. Lost ACKs withhold credits; they do not enable additional admissions. With no initial refusal, RETRY has no trigger. Normal backpressure/expiry can still occur, but this configuration cannot exercise full-budget REJECT/RETRY/DROP in a healthy primary run. This is a structural observation, not a measured policy result or a falsification of a research hypothesis.

No limit was changed. Saturation tests explicitly bypass normal client credits, or inject a deterministic refusal, to validate otherwise unreachable policy branches. Do not present these as conforming primary overload runs. Before a later performance comparison, independently review this issue and approve any contract amendment separately. It does not prevent implementation or Stage 2 fault-injection acceptance.

## Changes

| Files | Purpose |
|---|---|
| `server/src/ledger.rs` | Selectable WAIT/REJECT/RETRY/DROP at the existing atomic admission boundary. Full admission stages WAIT; REJECT/RETRY issue REJECTED_OVERLOAD; DROP issues DROPPED_OVERLOAD. All share deadlines, FIFO, dedup, worker, permits and response reservations. Nonexpendable DROP input fails explicitly. |
| `server/src/service.rs`, `server/src/main.rs` | Policy-aware constructor and `--policy wait\|reject\|retry\|drop`; default WAIT preserves Stage 1 callers. No separate handler/worker path. |
| `client/policy.go`, `client/ledger.go` | Fixed-array32-entry pending min heap shared by first attempts and retries, ordered by readiness then insertion order. RETRY is enabled only by a new explicit overload refusal; other strategies do not retry. Exact attempt history, deadline and payload identity remain intact. |
| `client/scheduler.go` | Open-loop monotonic arrivals independent of blocking Send/credit waits, one sender, one receiver, independent bounded response-event drainer and event logger. One polling timer per loop, no per-original goroutines/timers. EOF waits until arrivals finish and pending/outstanding become0. |
| `client/reconcile.go` | Retry-wait expiry and ambiguous later attempts cannot inherit an earlier refusal as a final result. Server completion still takes precedence; old attempt outcomes remain available. |
| `server/tests/policies.rs`, `server/tests/transport.rs` | Seven new core-policy tests, one new TCP saturation/retry/drain test, and policy-selectable transport harness via `E3_TEST_POLICY`. |
| `client/policy_test.go`, `client/scheduler_test.go` | Eight new top-level tests, including all-policy scheduler subtests, blocked Send, shared pending capacity, deterministic jitter, deadline/max-attempt enforcement and ambiguous second attempts. |
| `client/cmd/policy-smoke/main.go` | Guarded <=32-original scheduler interoperability command. It cannot execute the2880-original primary workload. Existing Stage 1 smoke command unchanged. |
| `fixtures/check-stage2.py`, `fixtures/policy-interop.py` | Exclusive output directories; commands, source/binary hashes, dirty state, return codes, logs and bounded correctness verification. |
| `results/stage2/` | Full check transcripts, raw small-fixture ledgers, provenance, preservation audit and explicit exclusions/development history. |

No dependency, protobuf, generated binding, frozen specification, E1/E2 source/evidence or historical Stage 1 report/measurement changed. The preservation audit verifies **1,723 protected files**, byte-for-byte against base commit `5a3cf4f94ba152af14c2720862e484375c5fe323`.

## Semantics and bounds

Admission is the same atomic operation for every policy. Deadline/failed-stream handling precedes the full-budget decision. Refused/dropped work acquires no admission permit and starts no worker. Its payload is removed from the one staging owner; its terminal metadata occupies an immediate-response reservation. Immediate capacity32 stops decoding when full. A free admission slot with exhausted admitted-terminal reservations waits cancellably without acquiring a permit; this response-pressure delay is not disguised as admission fullness.

RETRY uses max3 total attempts, no overlap, unique new attempt IDs, unchanged original/client/payload/deadline, and only explicit REJECTED_OVERLOAD. Refused attempt1 gets inclusive uniform jitter[0,100ms], refused attempt2[0,200ms]; the generic cap remains400ms. SplitMix64 with rejection sampling supplies a reproducible inclusive uniform nanosecond value; per-client seed is explicit (fixtures seed1). New arrivals and retries share32 pending entries and identical ready-time/insertion-order selection. A full pending budget finalizes an eligible refusal as REJECTED_FINAL; reaching the attempt limit does likewise. No retry on stream error, ambiguous delivery, duplicate-result replay, drop, expiry, cancellation or processing failure.

An unsent initial pending expiry is EXPIRED_BEFORE_SEND. Expiry while waiting for a retry is EXPIRED_WAITING_OR_QUEUED, with the preceding refusal preserved in its attempt record. A refusal received at/after the original deadline ends retry eligibility. Starting a new attempt clears only the original's latest-observation pointer; old attempt observations remain immutable. An unobserved later attempt is UNKNOWN after definitive stream closure, never converted to a refusal by an earlier ACK. These distinctions are tested independently of successful Send returns.

Bounds remain: pending32 (including retry heap), outstanding32, response events64, server admitted32 with one worker, decoded staging<=1, admitted terminal reservations32, immediate reservations32, per-process event ring1024, original history<=2880, attempt history<=8640 and<=3/original. Cancellation-pending running work is counted once. Admission release occurs only on removal/actual exit. No payload history, unbounded collection or per-message task was added. Client verification checks pending flags, heap ordering/uniqueness, credit counts and attempt limits. Record-storage estimates are not process RSS guarantees.

## Commands and actual results

Final acceptance execution is recorded in [checks/acceptance-2/verification.json](results/stage2/checks/acceptance-2/verification.json). All20 recorded command steps exited0; their logs are adjacent. Toolchains were Rust/cargo1.99.1 and Go1.27.3 on Linux x86_64; lockfiles are unchanged and hashed. Full exact argv, host/kernel, dirty state and source hashes are recorded, not inferred from this report.

```sh
source scripts/dev-env.sh
python3 experiments/003/fixtures/check-stage2.py --output /tmp/e3-stage2-checks-new
# Expanded principal checks:
cargo fmt --manifest-path experiments/003/server/Cargo.toml -- --check
cargo build --locked --manifest-path experiments/003/server/Cargo.toml
cargo test --locked --manifest-path experiments/003/server/Cargo.toml
cargo clippy --locked --manifest-path experiments/003/server/Cargo.toml --all-targets -- -D warnings
(cd experiments/003/client && go mod verify && go test -mod=readonly -race -count=3 -v ./... && go vet ./...)
# Transport stress: each command executed three times for each of the four policies:
E3_TEST_POLICY=retry cargo test --locked --manifest-path experiments/003/server/Cargo.toml --test transport -- --test-threads=1
cargo test --locked --manifest-path server/Cargo.toml
(cd experiments/002/client && go test -mod=readonly -race ./...)
# Built by check-stage2.py, or build explicitly:
(cd experiments/003/client && go build -mod=readonly -o /workspace/toolchains/bin/e3-stage2-policy-smoke ./cmd/policy-smoke)
python3 experiments/003/fixtures/policy-interop.py --policy wait --output /tmp/e3-stage2-wait-new
# Repeat with reject/retry/drop and a different NEW output directory each time.
```

**30 unique Rust tests passed** (3 library,9 original core ledger,7 policy,11 transport). All22 Stage 1 tests remain passing. The11-test transport suite additionally passed **three serial repetitions under each policy** (132 test executions). **20 top-level Go tests passed three times under `-race`**, including all12 Stage 1 tests. Go module verification/vet/builds and Cargo fmt/build/clippy passed. Existing E1/E2 regression suite passed38 Rust tests; the unchanged E2 Go race suite returned a cached PASS, explicitly recorded as such rather than a fresh run.

## T01–T20 assessment

Every row is PASS for correctness; no performance validity is implied. Test names are searchable in the [Rust](results/stage2/checks/acceptance-2/rust-tests.log), [Go race](results/stage2/checks/acceptance-2/go-checks.log) and [per-policy transport](results/stage2/checks/acceptance-2/) transcripts.

| Case | Verdict | Executed evidence |
|---|---|---|
| T01 | PASS | `TestT01All2880UnsentAndPartition`:2880 distinct unsent outcomes, A=0,U=0, no server decode. |
| T02 | PASS | `TestT02PendingOverflowOutstandingAndExpiry`; `TestT02OpenLoopArrivalsNotBlockedBySend` runs real scheduler under all policies with128 synthetic arrivals and a deterministic blocked Send; arrivals continue, overflow explicit, tasks terminate. |
| T03 | PASS | `t03_t04_shared_policy_boundary_and_refused_work_never_starts`, WAIT full32+staged1, no further decode; TCP saturation and cancellation regression. |
| T04 | PASS | Real full-budget REJECT/RETRY/DROP core and TCP dispatch; correct wire refusal/drop, no start for refused work. Raw saturation injection explicitly exceeds normal client credits. |
| T05 | PASS | `TestT05SendSuccessNeverImpliesAdmissionOrRetry`, abort-before-decode transport fixture; ambiguous Send success never manufactures admission. |
| T06 | PASS | Exact fake-clock999/1000ms local writer barrier plus per-policy TCP timeout; permit retained until exit gate opens, zero final tasks/permits. No stopped-reader consumption guarantee. |
| T07 | PASS | Full32 immediate reservations stop decode; per-policy blocked writer fixture and core refusal-queue saturation; workers exit independently of ACK delivery. |
| T08 | PASS | `TestT08ReceiveReleasesCreditWhileSendBlocked`; direct receive/ledger progress independent of sender. |
| T09 | PASS | Per-policy half-close/ClientDone tests and real scheduler drain; responses continue to clean EOF. |
| T10 | PASS | Pending, retry-pending, staged, queued and running expiry tests; request/observation/exit, correct expiry phase and retained running permit. |
| T11 | PASS | Deterministic exact deadline completion on time and1ns-late case; no controller/timing tuning. |
| T12 | PASS | Completion survives later cancellation/local timeout; missing ACK orthogonal. |
| T13 | PASS | Concurrent registration, linked/replayed duplicates and per-policy stream-failure fixture; worker starts<=1/original. |
| T14 | PASS | `t14_real_refusal_then_first_admission_and_immutable_attempt_history`; TCP saturation test RETRY path; Go retry ledger and actual Go gRPC deterministic refusal server: first/second refusal, third completion without early half-close. This controlled server injects outcomes, not policy performance. |
| T15 | PASS | `TestT15DeadlineAndSharedPendingCapacity`, max3-attempt fixture, jitter due/deadline boundary, actual fourth-attempt rejection after three real refusals. |
| T16 | PASS | Changed payload/hash/deadline/client/run/expendability and cross-original attempt alias fail; per-policy correlated error; nonexpendable DROP explicitly invalid. |
| T17 | PASS | Original/attempt capacity and1024 log backpressure tests; no eviction/loss; logger I/O failure explicitly invalid. |
| T18 | PASS | Abort-before-decode/during processing and healthy per-original cancel tests under every policy; no false completion/orphan tasks. |
| T19 | PASS | Lost terminal preserves server completion; client reconciliation exposes ACK-missing; ambiguous retry cannot reuse prior refusal. |
| T20 | PASS | Delayed cancellation checkpoint/exit barrier retains permit; occupied elapsed time includes delay and reconciles by terminal disposition. |

## Raw cross-language fixtures

[fixture-summary.json](results/stage2/fixture-summary.json) summarizes four separate eight-original Rust/Go correctness fixtures, one per policy, using identical application source and binary hashes. Each has8 attempted/successful Sends,8 unique worker starts/completions,8 acquired/released admission permits, and final occupied/pending/outstanding0. All streams drained successfully. Terminal sequence IDs/timestamps match client observation and server authority. Server JSONL has58 events per fixture; client counts vary with polling, and both complete sequence tails match the final ledgers. All source hashes were unchanged during each execution.

These low-volume fixtures exercise the real open-loop scheduler and interoperability, **not full-budget refusal or useful-completion comparisons**. Their8-ID synthetic manifests are explicitly separate from the frozen2880-ID primary schedule; no36-second run occurred. Refusal/retry correctness comes from the deterministic saturated server and controlled Go transport fixtures above, not from these low-volume outcomes.

Each process was guarded with CPU5s, file size16MiB, core size0; fixture orchestration applies10s client and5s startup/shutdown timeouts and exclusive output paths. All invocations and guards are in each `verification.json`. No binaries/caches are archived.

## Provenance, exclusions and limits

[source-provenance.json](results/stage2/source-provenance.json) records base SHA plus hashed **dirty working-tree source**; the base commit alone is not mislabeled as final application source. Every final fixture records executable hashes, commands, shared epoch, workload hash and source equality. Final check and fixture inputs match. Later report/index additions do not change the measured/tested runtime. [preservation.json](results/stage2/preservation.json) checks historical files. [SHA256SUMS](results/stage2/SHA256SUMS) covers the delivered package and changed implementation.

[EXCLUSIONS.json](results/stage2/EXCLUSIONS.json) preserves preliminary passing checks/fixture and explicitly records two initial development failure groups and their fixes. Complete console transcripts for those early failed invocations were not saved; their absence is disclosed rather than reconstructed as raw evidence. All final test/fixture logs are present. Expected fault injections are passing correctness tests, not hidden failed primary runs. No primary runs were attempted or excluded.

No frozen-specification deviation was made. Concrete unspecified implementation choices are fixed-array heap ordering and the recorded SplitMix64 jitter algorithm. Small synthetic schedules and credit-bypassing saturation frames are labeled fault fixtures, not amended primary parameters. No policy was tuned based on outcomes.

Deferred by stage: calibrated <5ms cross-process timing, independent performance counters/metrics verification, RSS/CPU/transport byte sampling, instrumentation-overhead assessment, safe pilot and primary matched comparison. The inherited log API records no-op pending sweeps on polling; even tiny fixtures produce many client events, so Stage 3 must assess logging/sampling overhead before timing claims. There is no primary runner or39-second performance observation claim. The smoke command is intentionally capped at32 originals.

Stage 2 protocol/policy correctness is ready for independent review. The equal-client/server-capacity issue must be resolved explicitly before designing a meaningful primary overload-policy comparison. **No Stage 3 implementation or performance work has started.**
