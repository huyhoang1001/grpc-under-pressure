# Experiment 002 — Stage 1 instrumentation only

The [frozen contract](EXPERIMENT-002.md) is a byte-identical copy of the supplied attachment. This implementation does not activate fixed8/adaptive policies, a controller, a changing logical budget, or the 10/40/10 ms service schedule. It exercises only fixed K=32 admission and constant 10 ms service. No primary matrix is provided.

## Separation from E1

- `server/src/bin/pressure-stage1.rs` is a thin executable bridge into `server/` here. It shares the existing protocol/dependency pins, not the E1 handler or CSV schema. Select binaries explicitly with `--bin` when invoking Cargo.
- `client/` is a separate Go module, using the existing generated bindings through a local module replacement. Versions remain pinned to the E1 grpc/protobuf versions; its own go.sum is verified.
- No historical E1/E1B source/report/measurement is edited. New outputs use fresh directories under this experiment.

The new fixed admission gate accounts `R` for the physical reservation; Q+R never exceeds 32. It introduces no dynamic B. Checking fixed capacity and obtaining its physical permit occur under the same transaction lock before any receive. Thus logical wait captures the fixed pending-slot wait; physical-reservation wait measures the immediate physical acquisition after that check. E1's `enqueue_wait_ns` schema/semantics remain unchanged in its executable.

## Build and check

From the repository root, after `source scripts/dev-env.sh`:

```sh
cargo build --locked --manifest-path server/Cargo.toml -j 4
cargo test --locked --manifest-path server/Cargo.toml -j 4
cargo clippy --locked --manifest-path server/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path server/Cargo.toml -- --check
(cd experiments/002/client && go mod verify && go test -mod=readonly -race ./... && go vet ./...)
(cd experiments/002/client && go build -mod=readonly -o /workspace/toolchains/bin/pressure-stage1-client .)
```

Then run only short acceptance fixtures, selecting an unused output directory:

```sh
python3 experiments/002/smoke.py --output experiments/002/results/smoke-v1
python3 experiments/002/verify.py experiments/002/results/smoke-v1
```

The runner starts fresh server/client processes, waits for their readiness, writes a shared target marker 300 ms in the future, and checks actual release offsets and alignment <=100 ms. Normal smoke uses 80/s for 0.8 s, not the primary 36 s. Cancellation-capacity uses 1000/s for up to 2 s and a 1200 ms RPC deadline solely as a labeled fault fixture. Worker-error/panic flags are test-only injections, not downstream schedules. All production Stage 1 service is constant 10 ms. A 512 MiB server-RSS guard, 128 MiB client-RSS guard, 10 s CPU/16 MiB file/no-core process limits and a 12 s smoke wall timeout protect the host. Fault fixtures deliberately fail RPCs, retain samples and verify terminal disposition; they are not successful workload drains.

A source commit, dirty status, complete tracked source hashes, binary hashes, commands, resource/transport/runtime settings, epoch/monotonic clock markers and exit statuses are stored per fixture. Failed smoke evidence is retained and stops the runner; do not overwrite it. `ledger.jsonl` enumerates every attempt. The runner is intentionally not a primary benchmark runner.

## Metrics and memory

All ownership transitions and snapshots share one lock. Physical receiver length is compared with Q on every transition/sample; counts and byte-flow conservation are also checked. Reserved slots do not count as queued messages; worker ownership is excluded from fixed pending capacity. A completed receive followed by terminal handoff failure increments received-not-admitted, not discarded. Queue/worker drops increment separate admitted-work dispositions before ownership ends. Worker error/panic wakes gate and receive waits; cancellation and completion serialize and cannot dispose one message twice. Normal EOF releases its unused reservation and drains before Summary.

Events stream to `server/events.csv` through a fixed 64 KiB BufWriter; per-message payloads are not retained in telemetry and events never go to console. Queue/service histograms have 1024 fixed buckets (approximately 2% spacing after 1 microsecond, explicit zero/overflow buckets), nearest-rank upper-bound quantiles and enqueue-time phase assignment. All successful dequeue/completion observations are counted, without a first-N cutoff. Four phase histograms use the contract's [0,12), [12,24), [24,36), [36,infinity) boundaries, **without activating a slowdown schedule**. Stage 1 smoke observations fall in the healthy phase. Exact streamed durations permit independent histogram/quantile reconstruction. Interrupted service contributes busy time and a discarded-worker event, not a successful-service histogram observation.

Gauges/counters and cumulative overall quantiles sample every 200 ms. Busy/idle accounting includes partial current intervals and stops when the worker exits; idle-with-backlog is separate. Queue, handler, and worker payload bytes remain distinct from RSS and transport allocations. The schema is `e2-stage1`, not an extension/redefinition of E1 columns.

The client has one sequential sender and a zero-capacity rendezvous (no queued work, no per-message tasks). Scheduled slots are classified as skipped or attempted. Snapshots satisfy scheduled=skipped+attempted and attempted=successful+failed+inflight; final snapshots have inflight=0. Successful Send is not admission/processing acknowledgment. `sends.csv` records actual invocation-wrapper start/return/duration and outcome, with monotonically increasing attempted-message IDs. Fixed histograms count both successful/failed calls; there is no growing latency vector.

`send_gt20ms_duration_ns` sums whole completed Send-call wall durations whose duration exceeded 20 ms; `send_excess_gt20ms_ns` sums only their excess over 20 ms. These are explicitly defined backpressure indicators, **not isolated transport blocking time**. Inflight elapsed wall duration is separately visible. The client worker dispatch and metric bookkeeping add small measurement overhead; timestamps bracket the invocation wrapper, not network delivery. Phase-level actual send rates can be reconstructed from raw timestamps, without subtracting server/client monotonic clocks for end-to-end latency.

## Stage 1 acceptance mapping

| Contract test | Coverage |
|---|---|
| 1 Exact handoff/dequeue/completion | Rust handoff/drain test + offline event ledger |
| 2 Capacity before receive; no read-ahead | Fake inbound checks actual reserved capacity; fills Q=32,W=1 and asserts only 33 receives |
| 3 Unused EOF reservation | Empty and nonempty EOF tests; acquired=admitted+released+R |
| 4 Cancel capacity wait | Full-queue wakeup unit test and network cancellation fixture |
| 5 Cancel during service / races | Service cancellation test and 200 concurrent completion/cancel races |
| 6 Worker error wakes handler | Worker error and panic unit/network fixtures |
| 7 Payload ownership | Variable-sized unit payloads, byte-flow counters and all-sample verifier |
| 8 Histogram values / phases | Rust and Go synthetic-duration tests; verifier reconstructs buckets from streamed dequeue records |
| 9 Client counters | Successful/failed/skipped unit test; every sample and final result verified |
| 10 Repeated fresh-process smoke | Three normal RPCs with one accepted connection/stream and matching Summary |

Budget shrinking, controller ticks and slowdown/recovery behavior are later-stage work and have no implementation or performance claims here. See STAGE1-REPORT.md for actual results, deviations and retained failure diagnostics.
