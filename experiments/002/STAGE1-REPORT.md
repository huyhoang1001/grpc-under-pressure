# Experiment 002 — Stage 1 report

**Stage 1 acceptance is met.** This is instrumentation/acceptance evidence only; no controller, dynamic budget, service slowdown schedule, primary matrix, or article was implemented or executed.

## Contract and compatibility

The supplied contract is saved unchanged at [EXPERIMENT-002.md](EXPERIMENT-002.md), SHA256 `fdd38c609ca7802f9f4a07ecc1d865a707aa9daed258034b943c66361e147b6a`. The final smoke application source is pinned to `f463d4bc01485e2de4df8f058d1d468576b89015`; initial smoke used `7c3e492`. Later changes strengthen tests/reporting only, not the measured application code. Each fixture records source/binary hashes, dirty state, commands and runtime/clock settings. New result files make the overall checkout dirty; source contents are verified against the recorded Git objects.

The existing E1 aggregate discard/reset model and first-N latency samples were insufficient for E2. This conflict was reported before implementation. E2 uses separate queue/worker dispositions and fixed-memory histograms, retaining E1 executables and telemetry semantics. A static K=32 gate accounts its reservation R in the same transaction as physical reservation, before receive; no changing logical admission budget exists. All 496 tracked historical experiment files match baseline `25c3dc0` byte-for-byte; see [historical-integrity.json](results/historical-integrity.json).

## Files and purpose

- `server/src/bin/pressure-stage1.rs`: thin new executable bridge; existing Cargo.lock/toolchain/protobuf pins are reused. No existing E1 Rust/Go application file, dependency declaration, lockfile, report or measurement was changed.
- `experiments/002/server/{mod,histogram,tests}.rs`: fixed-capacity handler/worker, transactional counters and byte ownership, reservations, cancellation/failure cleanup, partial busy/idle accounting, physical receiver length, supervised 200 ms sampling, exact streamed event timestamps and fixed histograms.
- `experiments/002/client/`: isolated Go module sharing existing generated bindings. One sequential sender, zero-capacity rendezvous, explicit skipped/attempted/successful/failed/inflight counters, actual Send records, fixed histograms and 200 ms snapshots. No growing latency sample vector.
- `smoke.py`, `verify.py`, `config.json`, `.gitattributes`, `README.md`: exclusive-create smoke runner, offline invariants/histogram verifier, explicit test settings, raw CSV byte preservation and detailed acceptance mapping.
- `results/`: source/environment manifests, process/clock samples, exact events and histograms, both smoke ledgers, final validation and retained resolved-error diagnostics.

## Exact checks executed

From `/workspace/grpc-under-pressure` after `source scripts/dev-env.sh`:

```sh
cargo build --locked --manifest-path server/Cargo.toml -j4
cargo test --locked --manifest-path server/Cargo.toml -j4
cargo clippy --locked --manifest-path server/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path server/Cargo.toml -- --check
(cd experiments/002/client && go mod verify && go test -mod=readonly -race -v ./... && go vet ./...)
(cd experiments/002/client && go build -mod=readonly -o /workspace/toolchains/bin/pressure-stage1-client .)
bash scripts/check.sh
(cd loadgen && go mod verify && go vet ./... && go test -mod=readonly -race ./...)
python3 experiments/002/smoke.py --output experiments/002/results/smoke-v1
python3 experiments/002/smoke.py --output experiments/002/results/smoke-v2
python3 experiments/002/verify.py experiments/002/results/smoke-v1
python3 experiments/002/verify.py experiments/002/results/smoke-v2
```

Final results: **16 Rust tests passed** (12 Stage 1, 4 original protocol/channel tests), **4 E2 Go tests passed with race detection**, and the **3 existing Go tests and 8 E1 process regression tests passed**. Both builds, both Go module verifications/vet/race checks, Rust formatting and warnings-denied Clippy passed. Rust doc tests and generated-only Go packages execute zero tests and are not counted. Logs: [checks/](results/checks/). Synthetic tests additionally cover 65-message bounded drain/EOF progress, actual full-queue worker failure, enqueue-phase assignment across a dequeue boundary, the strict >20 ms threshold and sampler-failure supervision.

## Smoke evidence

All six final fixtures passed their expected outcome. Three normal fresh-process RPCs offered 80 slots/s for 0.8 s (64 slots), with constant 10 ms worker service. Cancellation deliberately used a labeled 1000/s, 2 s fixture and a 1200 ms deadline to fill capacity; worker error/panic used explicit test injections. These deviations are fault-test inputs, not changes to or results from the frozen 36 s primary experiment. Original pre-supervision smoke-v1 remains intact and is superseded for final acceptance by smoke-v2. No failed or aborted RPC is labeled a successful drain.

| Final fixture | Scheduled / skipped / attempted | Successful / failed Sends | Admitted / processed / discarded | Sampled Q max | Phase alignment ms |
|---|---|---|---|---:|---:|
| [cancel-capacity](results/smoke-v2/cancel-capacity/manifest.json) | 895 / 774 / 121 | 120 / 1 | 112 / 79 / 33 | 32 | 0.239 |
| [normal-1](results/smoke-v2/normal-1/manifest.json) | 64 / 0 / 64 | 64 / 0 | 64 / 64 / 0 | 0 | 0.828 |
| [normal-2](results/smoke-v2/normal-2/manifest.json) | 64 / 0 / 64 | 64 / 0 | 64 / 64 / 0 | 0 | 0.166 |
| [normal-3](results/smoke-v2/normal-3/manifest.json) | 64 / 0 / 64 | 64 / 0 | 64 / 64 / 0 | 0 | 0.670 |
| [worker-error](results/smoke-v2/worker-error/manifest.json) | 3 / 0 / 3 | 2 / 1 | 1 / 0 / 1 | 0 | 0.855 |
| [worker-panic](results/smoke-v2/worker-panic/manifest.json) | 4 / 0 / 4 | 3 / 1 | 1 / 0 / 1 | 0 | 0.875 |

Every normal result returned Summary accepted=processed=64, with R=Q=W=0 and zero discards/errors. Each run had one accepted connection and one active stream. Normal sampled Q=0 does not imply messages never briefly queued: exact dequeue events retain all 64 residence observations. Cancellation ended with 32 queued plus one worker-owned message explicitly discarded. Worker error/panic each recorded the worker-owned discard and woke the waiting handler. Successful Sends greater than admission in failed RPCs are transport/client buffering, not per-message acknowledgments or admitted-work discards.

Final server periodic gaps were approximately **199.1–201.0 ms**; client periodic sampling uses 200 ms plus a terminal snapshot. Shared runner barriers measured **0.166–0.875 ms** server/client release differences, below the 100 ms rejection threshold. This synchronizes workload markers, not per-message end-to-end latency. CPU/RSS process samples and epoch/monotonic timestamps are retained.

## Invariants and bounded storage

Checked continuously in Rust and independently across raw samples:

```text
Q = physical receiver length = admitted - dequeued - discarded_from_queue
W = dequeued - processed - discarded_from_worker
0 <= Q <= 32; 0 <= W,R <= 1; Q + R <= 32
received = admitted + received_not_admitted
admitted = processed + discarded + Q + W
reservations_acquired = admitted + reservations_released + R
queued_bytes = admitted_bytes - dequeued_bytes - discarded_queue_bytes
worker_bytes = dequeued_bytes - processed_bytes - discarded_worker_bytes
scheduled = skipped + attempted
attempted = successful_sends + failed_sends + inflight
```

Normal EOF additionally requires reservations/queue/worker empty and accepted=admitted=dequeued=processed. Each admitted sequence has exactly one processed/discarded terminal event. Cancellation/completion races were exercised 200 times under simultaneous threads, and a received-before-failed-handoff case increments received-not-admitted separately. Negative residence violations and telemetry-error counters stayed zero. The verifier reconstructs queue/service histograms from exact streamed records and checks explicit enqueue/dequeue/completion timestamp differences, sample gaps and final counters.

Histograms contain 1024 fixed buckets per distribution, with approximately 2% spacing after 1 microsecond and an overflow bucket; quantiles are nearest-rank upper bounds. Exact append-only event/Send records retain durations for offline exact quantiles. Fixed-size buffers and arrays replace retained per-message latency vectors; no payload is stored in telemetry. Sampling includes partial worker busy/idle intervals and idle-with-backlog. Queue bytes remain separate from RSS/other memory. A sampler crash now terminates the server instead of silently leaving a telemetry gap.

## Scope, resolved issues and remaining limits

All ten Stage 1 acceptance categories are covered; see [README mapping](README.md#stage-1-acceptance-mapping). Enqueue-phase assignment and histogram boundaries are tested synthetically; no real slowdown/recovery schedule ran. Budget shrinking is explicitly deferred to the later stage specified by the contract. No Stage 2 hypotheses or performance thresholds are claimed validated.

Resolved implementation diagnostics are retained: initial Rust type/borrow errors, Clippy argument-count warning, and one test-fixture edit that changed five inputs to 65 but initially retained an expected histogram count of five. The expectation was corrected to 65; final stricter bounded-drain checks passed. No application assertion was disabled or experiment parameter retuned to make tests pass.

The only planned adaptations are isolated E2 executables/schemas, approximate fixed histograms paired with exact streams, shortened smoke durations and explicitly labeled fault inputs. The frozen contract is unchanged. No unresolved Stage 1 blocker remains. Instrumentation overhead and buffered disk I/O under the state lock remain observer effects to quantify before any performance study. `send_gt20ms_duration_ns` is whole wall time of completed calls above the threshold; `send_excess_gt20ms_ns` is their excess. Neither is isolated HTTP/2 blocking. Bounded application queues/histograms do not imply a bound on every process allocation.
