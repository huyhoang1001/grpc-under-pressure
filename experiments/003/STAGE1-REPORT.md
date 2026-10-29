# Experiment 003 — Stage 1 protocol and ledger correctness

**Verdict: PASS for Stage 1 under the user-approved specification clarification.** The implementation and deterministic acceptance tests cover identity, terminal outcomes, bounded ownership, half-close, blocked local responses, cancellation and reconciliation. No overload-policy dispatcher, retry scheduler, performance benchmark or Stage 2 implementation was added. Stage 2 remains pending review.

## Specification review and approved change

The uploaded three specifications are installed at their canonical paths. [EXPERIMENT-003.md](EXPERIMENT-003.md) is byte-identical to the upload. Only [PROTOCOL-003.md §4](PROTOCOL-003.md#4-fixed-bounded-resources) and [VALIDITY-003.md T06](VALIDITY-003.md#3-deterministic-correctness-and-fault-injection-acceptance) changed, exactly for the confirmed resolution:

- One second measures **blocked local server-side outbound progress**, not detection of a client application that stops reading.
- Successful local writes do not prove application consumption.
- T06 uses a deterministic server-writer barrier and checks timeout, bounded buffering, permit cleanup and lack of deadlock.
- No additional client-consumption acknowledgment mechanism.

The remaining Stage 1 identity, resource, lifecycle and reconciliation requirements are consistent. No further Stage 1 blocker remains. [Specification provenance](results/stage1/specifications.json) records uploaded/current hashes. No hypotheses, workload settings or four-policy decisions were rewritten.

## Files changed and implementation

| Files | Purpose |
|---|---|
| `EXPERIMENT-003.md`, `PROTOCOL-003.md`, `VALIDITY-003.md` | Preserve supplied documents; apply only the approved two-section clarification. |
| [proto/overload.proto](proto/overload.proto) | Versioned `pressure.e3.v1.OverloadService/Exchange`; Work/CancelOriginal/ClientDone and TerminalOutcome/ProtocolError. No ACCEPTED or consumption-ACK frame. Nested TerminalReference carries the specified duplicate disposition and original timestamp/sequence. |
| [server/Cargo.toml](server/Cargo.toml), Cargo.lock, build.rs, src/lib.rs | Isolated Rust/tonic crate and generated Rust protocol, leaving E1/E2 crates and protobuf unchanged. |
| [server/src/ledger.rs](server/src/ledger.rs) | Immutable manifest expectations, payload/hash validation, fixed identity/attempt tables, atomic duplicate linking/replay, FIFO ownership, deadline/cancellation state, bounded response reservations and event log. |
| [server/src/service.rs](server/src/service.rs), [main.rs](server/src/main.rs) | Bidi adapter, one serial worker, independent response/event writers, cancellable waits, timeout supervision, task joining, loopback fixture executable and atomic ready-file publication. |
| [server/tests/ledger.rs](server/tests/ledger.rs), [transport.rs](server/tests/transport.rs) | Deterministic core/clock tests and actual tonic bidi transport tests, including fault barriers. |
| [client/ledger.go](client/ledger.go), [reconcile.go](client/reconcile.go), [session.go](client/session.go) | Go bounded pending/attempt/event accounting, independent receive and idempotent terminal handling, explicit ambiguity, authoritative reconciliation, monotonic epoch mapping. |
| client/go.mod, go.sum, [gen/](client/gen/), [cmd/smoke](client/cmd/smoke/main.go), [ledger_test.go](client/ledger_test.go) | Separate Go module/generated bindings, two-message fixture command and race-detected tests. |
| [fixtures/](fixtures/) | Test/check and protobuf-generation scripts, immutable identity-artifact schema, bounded two-message cross-language fixture. |
| [README.md](README.md), [results/stage1/](results/stage1/) | Implementation decisions, reproduction commands, test transcripts, source/specification preservation and fixture evidence. |
| Root `.gitignore`, E3 `.gitattributes` | Exclude new build artifacts and preserve raw fixture bytes. |

The skeleton has no policy name/flag, full-budget refusal/drop decision, application retry timer or overload comparison. Cancellable bounded staging/admission is the shared correctness substrate, not a claim to have implemented/tested the four policy strategies. A private test-only refusal fixture exercises refusal→new-attempt ledger semantics; there is no live refusal policy path.

## Ownership, identity and bounds

The Rust state lock makes identity registration and admission transitions atomic. Expected run/message/client/schedule/deadline/payload hash/expendability come from an immutable manifest. SHA256 is recomputed over the actual 16384-byte payload. Attempt IDs are unique across originals; changed identity and malformed attempt numbers are explicit errors. Active duplicates join existing work; completed duplicates replay the stable referenced outcome. A new attempt following explicit refusal can obtain its **first** admission without changing deadline or overwriting the earlier attempt's terminal result. Original worker starts remain <=1. No identity eviction or crash/durable exactly-once claim.

| Resource | Enforced bound / ownership rule |
|---|---|
| Original/attempt identity records | Fixed allocations <=2880 / <=8640, <=3 attempts/original; explicit metadata-capacity failure, no eviction. |
| Admitted payload owners | Queued + running <=32. Cancellation-pending is a subset of running, never counted twice. |
| Receive/staging | One shared lease: `receive_stage_reservation + decoded_staging <=1`. A decoded frame waiting for ledger/log progress stays in that same receive lease. |
| Admission release | Only when queued ownership is actually removed or per-message worker execution exits; cancellation request alone releases nothing. |
| Terminal responses | 32 slots reserved at admission through writer acceptance or failed-stream cleanup; worker does not wait for client ACK. |
| Immediate responses | 32 reserved/queued slots, including active duplicate followers awaiting a result. Full capacity stops decoding; no spill into an extra response queue. |
| Writer/tonic bridge | One writer-owned frame and capacity1 transport bridge, explicitly distinct from consumption acknowledgment. |
| Client pending/outstanding | Separate32-slot budgets; initiation acquires credit before Send. No overlapping normal attempts for an original. |
| Client response events | Capacity64, independently drained. Overflow cancels/invalidates explicitly. Receive does not wait for Send or send credits. |
| Event logs | Capacity1024 per process, append-only JSONL and shutdown flush. Full server logging waits before mutation and supports cancellation; client full-log cancellation is explicit invalidation rather than silent loss. |

There are no unbounded channels or per-message spawned tasks in E3. One serial worker and a bounded deadline sweep replace per-queued-message timers. Payloads are not stored in identity/attempt history; terminal records carry metadata only. Record-storage byte estimates are separate from payload bytes and do not claim total allocator, transport or RSS bounds. CLI manifest reads are guarded at2MiB, wire messages at1MiB; valid application payloads remain exactly16384 bytes. Full RSS/CPU/transport instrumentation belongs to Stage 3.

Worker service is selected at monotonic service **start**, with the prescribed10/40/10ms phase rule. Queued/waiting expiry removes ownership; running cancellation records request, observation and exit separately and holds the slot through delayed checkpoints. Completion at deadline is on time. Completion after deadline but before cancellation observation is represented as late, not silently changed into expiry. Cancellation after completion preserves completion. EOF drains; ClientDone is diagnostic and is neither required for progress nor treated as half-close.

RPC/task shutdown is supervised. Faulted logging/unresolved shutdown is explicitly invalid even if the client saw application completion; it cannot be called a valid run. A forced unresolved snapshot is taken only after child tasks have actually exited. Normal and injected response-stall/cancellation tests join all owned tasks, verify zero occupancy and check permit releases. No terminal frame is generated after failed-stream state; already-constructed frames are not evidence of client consumption.

## Reconciliation and client behavior

A is recorded on attempt initiation, separately from successful grpc-go Send returns S. Send success never manufactures admission or completion. The independent receive loop records terminal observations and returns attempt credit without waiting for a blocked sender. Replayed results are idempotent, including stable server sequence/time; duplicate observation never releases a second credit.

Local outstanding deadline observation retains its credit until a terminal or definitive stream closure. Stream failure stops attempts and leaves ambiguous delivery UNKNOWN, never per-message overload rejection. No ambiguous-delivery retry exists. Reconciliation iterates the entire immutable original population, preserves client-observed state and server-authoritative execution separately, gives authoritative completion precedence over local timeout/missing ACK, and allows a later valid completion to supersede an earlier refusal. ACK-missing is orthogonal. Unknown/cross-original server populations, conflicting terminal data, duplicate worker starts and unsafe server snapshots are detected.

The fixture client disables configured retries, uses a zero replay buffer, and waits for initial gRPC response headers before sending Work, committing the RPC in pinned grpc-go. grpc-go's pre-commit transparent establishment retries are distinguished from application Work retries; no Work has been initiated before that header barrier. No extra application acknowledgment was introduced. Static65535 transport windows, max1MiB messages and no compression are recorded for fixtures; transport-byte/retry telemetry and calibrated <5ms clock uncertainty must still be verified in Stage 3 before any performance run.

## Tests executed and results

**22 Rust tests passed**:3 library tests (including fake-clock timeout),9 core-ledger tests and10 real-transport tests. **12 Go tests passed under `-race`**. All builds, Cargo fmt, warnings-denied clippy, module verification, Go vet and deterministic protobuf regeneration passed. The transport suite was repeated three times with serial test execution after the final ledger changes; Go's race suite also passed three repetitions. Existing E1/E2 tests passed unchanged:38 Rust tests and four Go tests.

| Validity case | Stage 1 evidence / scope |
|---|---|
| T01 | All2880 unsent originals receive distinct reconciled outcomes; U=0, A=0, zero server decode. |
| T02 | Pending32 + outstanding32 saturation, explicit overflow/expiry, nonblocking arrival APIs; transport-send blocking covered separately. No complete open-loop scheduler claimed. |
| T03 | Core fills all32 admitted owners and permits one staged request; further decoding/admission blocks cancellably. WAIT policy itself remains Stage 2. |
| T04 | Deferred: actual REJECT/RETRY/DROP full-budget policy decisions are not implemented. |
| T05 | S=1 before confirmed decode does not imply admission; transport closure reconciles UNKNOWN honestly, with no retry. |
| T06 | Fake-clock barrier: no timeout at999ms, timeout at1000ms; actual bidi barrier verifies cancellation, bounded buffering and permit held until worker exit. No remote-read detection claim. |
| T07 | Fill32 duplicate/immediate reservations behind blocked writer, stop receiver, allow workers to exit independently of ACK; resume and drain without deadlock. Raw fault fixture deliberately bypasses normal client credit gating. |
| T08 | Independent receive releases credit while Send remains blocked. |
| T09 | Half-close drains terminal/duplicate responses and clean EOF; optional ClientDone does not terminate input prematurely. |
| T10 | Pending, server-staged, queued and running deadline/cancellation fixtures; explicit phases/timestamps and retained running permit. |
| T11 | Exact deadline completion on time; one-nanosecond-late race remains late when cancellation was not observed. |
| T12 | Cancellation after completion does not erase it; local timeout remains distinct and missing ACK recorded. |
| T13 | Atomic concurrent same-ID registration and actual bidi duplicate frames produce one worker start with linked/replayed terminal reference. |
| T14 | Deterministic protocol/refusal-history and reconciliation fixtures: one original, two attempts, <=1 execution and unchanged deadline. Actual retry scheduling/server overload policy remains Stage 2. |
| T15 | Wire attempt-number bounds and no attempt after stream closure; pending/outstanding expiry. Actual retry-after-deadline/backoff scheduler tests remain Stage 2. |
| T16 | Changed payload/hash/deadline/client/run/expendability and cross-original attempt reuse fail explicitly without duplicate execution. |
| T17 | Reduced metadata-capacity exhaustion, full1024-event buffers, cancellable log wait, and I/O-failure invalidation; no silent eviction/loss promoted to success. |
| T18 | Stream abort before decode and during service; cancellation request/observation/exit, no false completion or orphan task. |
| T19 | Dropped terminal after completion preserves server authority; client reconciliation exposes ACK-missing. |
| T20 | Delayed cancellation checkpoint retains slot through actual exit; worker elapsed by final disposition equals summed worker elapsed. |

This is **not** a claim that the full Stage 2 T01–T20 policy suite passes. Applicable Stage 1 protocol gates and deterministic reconciliation fixtures pass; deferred policy behavior is listed above.

## Cross-language correctness evidence

[interop-4/verification.json](results/stage1/interop-4/verification.json) pins runtime source `4cdeee3a569e7642902b3f5a51184868d6d6efef`, source/binary hashes, commands and unchanged-source checks. Both processes exited0. Exactly **two** messages were sent; no80/s or36s experiment was executed.

- Server logical/attempt entries2/2, two unique starts/completions, acquired/released admission2/2.
- Final admitted/staged/receive/response ownership0; no server failure.
- Client pending/outstanding0, attempts2, successful Sends2, retries0; no invalid-ledger flag.
- Terminal sequence IDs and completion offsets match across Rust wire output, Go observation and authoritative server snapshot.
- Server/client JSONL sequences are contiguous (16/11 events); buffers empty after flush.
- Synthetic offline cutoff39s reconciles all2880 immutable IDs:2 COMPLETED_ON_TIME +2878 EXPIRED_BEFORE_SEND. This is a fixture partition, **not** observed primary goodput or a39s run.
- Reported fixed record-storage estimates are1,391,133 bytes server and654,341 bytes client for this build; they are not process memory measurements.

A final additional transport regression exercises an actual CancelOriginal frame on a healthy stream; it changes tests only, not runtime source. Earlier two-message fixture runs are retained under interop-1..3 with their own versions. The final fixture is the acceptance evidence for the final code; these are development correctness repetitions, not benchmark repetitions. Wall epoch coordination maps once onto local monotonic clocks. No Stage 3 calibration or primary-run validity is claimed from these smoke results.

## Exact reproduction commands

From repository root:

```sh
source scripts/dev-env.sh
experiments/003/fixtures/check-stage1.sh
# Or the expanded checks:
cargo fmt --manifest-path experiments/003/server/Cargo.toml -- --check
cargo build --locked --manifest-path experiments/003/server/Cargo.toml
cargo test --locked --manifest-path experiments/003/server/Cargo.toml
cargo clippy --locked --manifest-path experiments/003/server/Cargo.toml --all-targets -- -D warnings
(cd experiments/003/client && go mod verify && go test -mod=readonly -race -count=1 -v ./... && go vet ./... && go build -mod=readonly -o /workspace/toolchains/bin/e3-stage1-smoke ./cmd/smoke)
# Additional targeted repetitions executed:
for e3_repeat in 1 2 3; do cargo test --locked --manifest-path experiments/003/server/Cargo.toml --test transport -- --test-threads=1; done
(cd experiments/003/client && go test -mod=readonly -race -count=3 ./...)
# Deterministic generation check (protoc31.1, protoc-gen-go1.36.10, go-grpc1.5.1):
experiments/003/fixtures/generate-proto.sh
# Reproduce interoperability with a NEW output directory:
python3 experiments/003/fixtures/interop.py --output /tmp/e3-stage1-new-fixture
# Existing experiment regression checks executed:
cargo test --locked --manifest-path server/Cargo.toml
(cd experiments/002/client && go test -mod=readonly -race ./...)
```

[Check transcripts](results/stage1/checks/) and [environment/lock hashes](results/stage1/environment.json) preserve actual results. The independent E3 Cargo/Go lockfiles pin dependencies; Rust1.99.1/Go1.27.3 follow the existing toolchain setup. Old protobuf/bindings and Cargo/Go files are untouched. [Preservation audit](results/stage1/preservation.json) verifies1658 existing E1/E2/source/evidence files against baseline `f82d3ba7f4b1d118fd4a9eb7c98014ff147b2145`.

## Deviations and review boundary

No deviation from the approved Stage 1 protocol semantics or specified resource limits is required. The approved T06 clarification is the only normative change. Proto field numbers, the nested duplicate reference, immutable manifest schema and fail-stop correlated protocol errors are concrete representations of the specified protocol, not new overload outcomes. The deterministic payload expander is shared/verified across languages; no full payload collection is materialized in a live ledger.

Explicit limits: Stage 1 fixture-only sender, one stream/run, no policy/retry scheduler, no calibrated primary timing or full performance metric runner, no durable crash recovery/exactly-once guarantee, and record-storage estimates rather than full RSS accounting. Event-file loss invalidates even otherwise completed work; primary measurement completeness cannot be inferred from a build, RPC success or this Stage 1 PASS. Full Stage 2 policy tests and later instrumentation/clock calibration remain mandatory.

**Stop here for Stage 1 review. Stage 2 has not begun.**
