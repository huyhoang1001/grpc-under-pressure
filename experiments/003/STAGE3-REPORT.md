# Experiment 003 — Stage 3 instrumentation and measurement validity

**PASS. GO for bounded Stage 4 pilots after independent review.** Supported measurements reconcile independently, clock calibration meets the strict<5ms criterion, intentional data corruption is detected, and Stage1/2/A01 regressions pass. This is not approval for a primary comparison: total instrumentation overhead is not established as negligible, and the uncertainty/unsupported counters below remain explicit pilot considerations. No36-second primary workload, policy ranking, controller or Blog3 was run.

## Contract and implementation

A01 is unchanged: client outstanding33, pending/retry heap32, server admission32, one worker, staging<=1, admitted terminal reservations32, immediate responses32, client response notifications64 and event rings1024. The three normative specifications are byte-identical to baseline `6039d205eac243c0389c270b701de6ddeabc1c8d`. Historical E1/E2 and Stage1/2/A01 evidence is untouched; [preservation.json](results/stage3/preservation.json) verifies1,988 protected files.

| Files changed/added | Purpose |
|---|---|
| `server/src/ledger.rs` | Fixed-size resource state and exact high-water records on lifecycle events; decoded/admitted/start/exit timestamps, terminal metadata, cumulative local writer-progress time/calls. Existing queue/policy paths retained. |
| `server/src/service.rs` | Measure local writer elapsed and bounded bridge/writer/logger ownership. Serialization/file I/O remains outside the shared state lock. Bridge reservations are capacity1; publication uses the existing channel. |
| `server/src/measurement.rs`, `server/src/main.rs`, `server/src/lib.rs` | Linux monotonic calibration and final clock/bounded-I/O artifact. Direct libc dependency uses already-locked0.2.191; only its root dependency edge was added. |
| `client/ledger.go`, `client/measurement.go`, `client/session.go`, `client/scheduler.go` | Send wrapper start/return/success/duration; exact bounded resource state/HWM; monotonic commit timestamps distinct from operation timestamps; clock brackets. No-op pending sweeps emit no events; real expiry and retry transitions remain logged. Polling cadence, admission, deadlines and retry timing unchanged. |
| `client/notifications.go` | Fixed64-entry diagnostic ring replaces the diagnostic channel so physical occupancy/HWM can be measured under its lock. Same nonblocking full->invalid behavior, independent drain, and credit release before notification. No business queue enlargement. |
| `client/transport.go`, `client/cmd/credit-smoke/main.go` | Atomic grpc-go payload counters and counting plaintext TCP connection; preserve pinned grpc-go TCP keepalive defaults and socket-option access. Record measurement fields and an explicitly labeled legacy-sweep calibration control. |
| `client/reconcile.go` | Accounting correction: a definitive latest server refusal survives loss of its ACK as REJECTED_FINAL with ack_missing=true. A later attempt absent from server evidence remains UNKNOWN. No policy, worker or retry-scheduling behavior changed. |
| `server/examples/credit-saturation.rs` | Test-only clock/IO records and finished marker after supervised tasks join/log flush. Prevent orchestrator SIGINT from racing normal completion. |
| `server/examples/measurement-cost.rs` | Bounded fake-time calibration of incremental encoding/file I/O; no network/service-rate or policy benchmark. |
| Go/Rust measurement tests, updated Go log-pressure test | Capacity/HWM, silent no-op sweeps, real expiry, clock bounds, socket settings, queue/writer timing and ACK-loss regressions. Log saturation now uses explicit diagnostic events. |
| `fixtures/check-stage3.py`, `stage3-fixture.py`, `verify-stage3.py`, `faults-stage3.py`, `overhead-stage3.py` | Reproducible checks,200ms process sampling, independent replay/reconciliation, semantic corruption fixtures and predeclared matched overhead controls. |

## Measurement definitions and validity

Client JSONL records scheduled arrivals/actual observation offsets, attempt identity/number, explicit Send start/return/success, wrapped Send duration, retry scheduling/due time, expiry, terminal observation and closure. A is initiated attempts; F is originals first attempted; retries=A−F; S is successful Send returns. Scheduled retries are a separate population: they may expire before initiation. Success is never treated as decode/admission. `commit_offset_ns` is measured under the ledger lock for event ordering; `offset_ns` retains the operation's measurement point. Send timing includes the explicit marker's instrumentation/caller scheduling; it is **not isolated HTTP/2 blocking**.

Server JSONL independently records decode R, admission, FIFO worker start/exit, refusal/drop, removal/expiry/cancellation and response progress. Queue residence=start−admitted; logical admission wait=admitted−decoded. Worker elapsed is exit−start, including service gates/checkpoint delays; it is not CPU time or merely the requested timer delay. Per-disposition occupied time sums to total worker elapsed. Payload ownership remains separate: queued/running/staged counts×16384; history contains metadata only.

Resource state/HWM covers client pending/outstanding/events/physical notification ring and server queue/running/staging/receive lease/terminal/immediate/events. Bridge slot reservations, writer-owned frames and logger-owned events have current/peak counters with bound1 in `server/clock.json`; buffered logger capacity remains65536 bytes. Fixed control wakeups/error channels are control plumbing, not work queues; their capacities are unchanged. Event construction/resource accounting remains under the state lock; JSON encoding and buffered writes occur outside it. The latter distinction does not establish zero instrumentation overhead.

`client-metrics.csv`/`server-metrics.csv` contain externally sampled `/proc` RSS and user/system CPU, targeting200ms. State CSVs join event state to calibrated sample offsets; series CSVs add quantized CPU percent of one core. RSS peaks are sampled lower bounds; CPU resolution is10ms and last observation precedes exit. Final ledger record-storage estimates are retained separately; a repeated final estimate in series files is explicitly labeled a reference, not sampled allocation/RSS. Full allocator/transport copies, unsampled RSS peaks and exact process-lifetime CPU totals are unsupported.

Transport support: grpc-go `WireLength` counts message bytes including the5-byte gRPC envelope, excluding HTTP/2 framing; compression is disabled. Socket Read/Write counts plaintext TCP-stream bytes including HTTP/2 headers/preface/frames, excluding IP/TCP headers, retransmissions and NIC traffic. They are observed counters at snapshot, not guaranteed connection-close totals. Server-direction traffic is observed at the client's peer socket, not independently instrumented inside tonic/h2. HTTP/2 window state and isolated transport-blocked time are unsupported; neither Send nor writer elapsed is labeled as such.

## Clock alignment

Each process brackets its local monotonic epoch against Linux CLOCK_MONOTONIC eight times at start and end, retaining the narrowest valid interval. The independent verifier takes the envelope over both processes/both endpoints and rejects a span>=5000000ns. No timestamp correction hides a failed calibration. The five final acceptance spans were **491–831ns**, all below5ms. Raw bounds are in client snapshots and `server/clock.json`.

The host does not expose `/proc/.../ns/time`; that limitation is recorded rather than inventing namespace identities. Processes are inherited fork/exec children on the same host/boot, without namespace changes; CLOCK_MONOTONIC is the shared calibration domain. The bound assumes that inherited domain and the Linux Go/std/Tokio clock mapping. Start/end checks do not prove arbitrary unobserved transient clock faults. Cross-host operation is unsupported.

## Independent verification and fault evidence

The Python verifier imports no Rust/Go reconciliation code. It replays client credits/pending/retries/Send results and server FIFO ownership/permits; checks complete sequence tails, bounded resources/HWM, no duplicate starts, worker durations, source/config presence, clock span, sampling coverage, transport counts and all-original terminal partition/ACK-missing state. It rejects undocumented UNKNOWN and unexpected failure in a predeclared healthy-drain fixture. Documented transport ambiguity is distinct from missing/corrupt ledgers.

Five final real Go/Rust cases under `accepted-*/` passed: WAIT drain, REJECT, RETRY, DROP and WAIT cancellation. Each used the conforming client limit33, an initially empty server ledger and the existing deterministic worker barrier. No refusal was fabricated and no credits were bypassed. Every case reached client outstanding33/server occupied32 and reconciled all33 originals. Final ownership/permits and bounded IO counters returned to0; starts<=1/original; complete event tails matched snapshots. These are deliberately short correctness fixtures, not policy-performance comparisons.

[accepted-faults-v2/](results/stage3/accepted-faults-v2/) proves rejection of15 semantic corruptions: unexpected stream failure, missing middle/tail, renumbered duplicate start, wrong Send count/partition, client/server overflow, clock drift, missing samples/sampling gap, A01 drift, wrong HWM, transport count and missing provenance. Faults mutate in-memory copies; real raw evidence remains intact. [Synthetic fixtures](results/stage3/accepted-synthetic-verification-v2.json) reconcile all2880 unsent IDs (A=0), exact/late deadline boundaries, expiry/failure/cancellation classifications, retry-wait expiry, known lost-refusal ACK, ambiguous later retry, backlog overflow and failed Send before decode (A=1,S=0,R=0,UNKNOWN=1). Synthetic results are not measured findings.

The final offline verifier revision corrects the byte floor to S successful Sends rather than A attempts, so a failed pre-transmission attempt is not falsely invalidated. Original run-time verification outputs/code are preserved; `independent-verification-v2.json` records the final verifier hash. No application source changed for that post-run analysis correction.

## Overhead assessment

Two controlled calibrations were predeclared; neither compares policies:

1. **No-op sweep logging:** three fresh-process WAIT pairs, order optimized/legacy, legacy/optimized, optimized/legacy; identical final source/binaries,33 originals, payload, seed, clocks, barrier and guards. Only `--legacy-sweeps` differs. Lifecycle populations/partitions matched exactly in every pair. Optimized logs had232 events/~69KB versus2370–2420 events/~681–695KB with legacy no-op logging. Last-observed client CPU differences (legacy−optimized) were+20,−40,0ms, with10ms CPU quantization. **These data do not establish a CPU saving.** They demonstrate removal of redundant output without losing meaningful transitions. Polling frequency was not tuned.
2. **Encoding/file I/O:** three matched file/no-encoding micro-pairs, AB/BA/AB order,2240 identical constructed events and320 fake-time ledger completions per mode. Both retain ledger/event construction; file mode additionally serializes/writes. Paired CPU deltas were15.79–114.24ms (median75.83ms), with1µs rusage resolution; wall deltas were14.80–112.70ms. The broad three-pair range is descriptive, not a confidence interval. No-encoding controls intentionally lack raw event output and are not valid E3 runs.

This measures incremental output cost and sweep-log effects, **not total instrumentation overhead or its effect at primary load**. Rich event construction/verification under the shared lock is not isolated from the application baseline; process sampling and transport counters also incur cost. Shared-host variability is substantial. No negligibility, throughput improvement or policy ranking is claimed. Stage4 pilots must assess instrumentation materiality/coverage before any primary comparison; no policy parameter should be adjusted to compensate.

## Commands, regressions and provenance

```sh
source scripts/dev-env.sh
python3 experiments/003/fixtures/check-stage3.py --output /tmp/e3-stage3-checks-new
python3 experiments/003/fixtures/stage3-fixture.py --policy wait --output /tmp/e3-stage3-wait-new
# Repeat with reject/retry/drop and distinct NEW output directories.
python3 experiments/003/fixtures/stage3-fixture.py --policy wait --mode cancel --output /tmp/e3-stage3-cancel-new
python3 experiments/003/fixtures/verify-stage3.py --run /tmp/e3-stage3-wait-new
python3 experiments/003/fixtures/faults-stage3.py --run /tmp/e3-stage3-wait-new --output /tmp/e3-stage3-faults-new
python3 experiments/003/fixtures/overhead-stage3.py --output /tmp/e3-stage3-encoding-new
# Logging controls: run three fresh WAIT pairs in the order in sweep-overhead-plan-v4.json;
# legacy member adds --legacy-sweeps, optimized member omits it.
python3 experiments/003/fixtures/interop.py --output /tmp/e3-stage1-regression-new
```

[checks/acceptance-4/](results/stage3/checks/acceptance-4/) records all21 command steps, exact argv/toolchains/exits and source hashes. Cargo fmt/build/test/clippy warnings denied, example builds, Go module verification/vet/builds passed. **32 Rust tests and26 top-level Go tests repeated3 times under `-race` passed**, plus three serial11-test transport-suite repetitions per policy. Existing E1/E2 regressions passed38 Rust tests and the unchanged Go race suite (cached PASS explicitly recorded). A real two-message legacy Stage1 interoperability regression also passed; it is supplemental correctness evidence, not Stage3 clock validation.

[Source provenance](results/stage3/source-provenance.json) records base commit plus exact dirty-source hashes and executable hashes. The five accepted cases and six final logging-control runs used identical application source/binaries matching final checks. The independent analysis revision is separately pinned; its run-time predecessor is archived. The Rust microfixture binary/inputs match the final Rust build even though unrelated client/harness development continued afterward. [Artifact catalog](results/stage3/ARTIFACT-MANIFEST.json) binds raw files to A01/configuration, commands/toolchains/source provenance; [SHA256SUMS](results/stage3/SHA256SUMS) covers the delivered package. No committed-final-source claim is made for a dirty tree.

## Unexpected findings, exclusions and review boundary

The matched calibration exposed a harness race: SIGINT immediately after clean client EOF could mark a drained server STREAM_FAILED before log/task flush completed. The invalid `sweep-1-legacy` remains intact. The finished marker now precedes shutdown; all matched pairs were restarted with final source. Early namespace-probe startup failures and preliminary passing runs remain under [EXCLUSIONS.json](results/stage3/EXCLUSIONS.json); one failure occurred before manifest initialization and only its workload file exists. Missing early console transcripts are disclosed, not reconstructed. No primary run was attempted or selectively retained.

No A01/specification deviation was made. Known measurement limits above prevent a primary-performance claim, but do not block bounded pilots using the validated supported counters and strict clock/error gates. Stage4 needs a pilot orchestration profile without the correctness worker barrier and must validate observation/cutoff coverage and overhead at its intended workload. A complete primary matrix runner and39-second measurement coverage are not claimed from these fixtures. **Stop after Stage3 for review.**
