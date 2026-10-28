# Stage 3 — static logical admission over K=32

Frozen contract unchanged. Two startup policies share the SAME receive, gate, worker, schedule, histograms and logger:

- `--policy fixed32` (default): B=32, physical K=32.
- `--policy fixed8`: B=8, physical K=32.

B is stored once during construction; there is no update API, tick or controller. Gate admission requires Q+R<B, with worker W excluded. Logical acquisition increments R before physical reservation; a physical acquisition error rolls R into released rather than leaking it. Both reservations precede receive. EOF/error/cancellation drops physical ownership and releases unused R. Successful handoff transfers R to Q. Dequeue frees physical capacity and wakes logical waits. Additional numeric gauges show physical capacity, actual available physical slots and logical pending count, without changing old metric meanings.

No ambiguity was found in the static contract. With B=8, eight pending plus one executing message is legal: this is neither physical capacity eight nor worker/RPC concurrency eight. Q+R<=B is the static invariant. Stage 4 MUST NOT merely assign a smaller B: legal shrink below occupancy requires a carryover invariant and blocked-wait notification tests, preserving existing reservations/messages. No shrink/update implementation is included here.

## Predeclared validation and overhead sequence

Run boundary/lifecycle tests, then short fresh-process fixtures: default/explicit fixed32, fixed8 normal, fixed8 capacity cancellation, worker error/panic, and short schedule fixtures for both policies. No primary workload is run by these fixtures.

The accepted Stage 2 server executable was still present and matched its recorded SHA256. It is copied outside Git as `/workspace/toolchains/bin/pressure-stage2-accepted`. The retained accepted client is verified against the Stage 2 digest and is used identically in all cases. The baseline server source is pinned separately to 8450954; the new server and harness are pinned before execution. Manifests distinguish harness commit, actual server source commit/hashes, shared client commit/hash, binary and configuration. Binaries are not committed.

Assess unintended overhead with ABBA **healthy constant-10-ms, 80/s, 4-second buffered-I/O controls**: accepted32-1, shared32-1, shared32-2, accepted32-2. Every process is fresh, same client bytes, compiler/build mode, CPU placement, windows, resource limits and 200 ms collection. This compares accepted baseline to the new shared gate/three extra numeric gauges, not buffering on/off. It can reveal gross healthy-load regressions, not prove equivalence or saturated-capacity loss; event-I/O timers omit other telemetry/lock costs and two repetitions are not confidence intervals. No historical Stage 2 run is overwritten or repeated at 36 seconds.

Only after all checks pass, at most ONE explicitly labeled exploratory fixed8 run may execute the frozen 80/s × 36 s, 16,384-byte seed-1 workload and 10/40/10 ms service schedule. Compare descriptively with accepted Stage 2 fixed32: pooled queue-residence p95 for enqueue t=[12,36), slowdown/recovery separately, actual worker throughput, skipped slots, Send wall time, whole-RPC/drain and exact accounting. Version/time/host/cohort differences remain confounders. Local residence improvement does not establish end-to-end improvement or a primary performance conclusion. No tuning/retry/controller or primary matrix is authorized.

All limits remain: K=32, server/client RSS 512/128 MiB, CPU 10 s/process, file 16 MiB, no core dumps, whole-RPC deadline 120 s, external wall guard 125 s; same debug Rust/default optimized Go and inherited affinity. Fault fixtures explicitly use 1000/s and a 1200 ms deadline to fill the logical gate; they are not primary measurements.

## Commands

From repository root, after `source scripts/dev-env.sh`:

```sh
cargo build --locked --manifest-path server/Cargo.toml -j4
cargo test --locked --manifest-path server/Cargo.toml -j4
cargo clippy --locked --manifest-path server/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path server/Cargo.toml -- --check
(cd experiments/002/client && go mod verify && go test -mod=readonly -race -v ./... && go vet ./...)
(cd experiments/002/client && go build -mod=readonly -o /workspace/toolchains/bin/pressure-stage3-client-buildcheck .)
# Source committed before collecting data; accepted shared client bytes retained.
python3 experiments/002/stage3/run.py --output experiments/002/results/stage3 --phase acceptance
python3 experiments/002/stage3/run.py --output experiments/002/results/stage3 --phase overhead
python3 experiments/002/stage3/analyze.py experiments/002/results/stage3
python3 experiments/002/stage3/run.py --output experiments/002/results/stage3 --phase exploratory
MPLCONFIGDIR=/workspace/toolchains/matplotlib python3 experiments/002/stage3/analyze.py experiments/002/results/stage3
python3 experiments/002/stage3/audit.py experiments/002/results/stage3
```

Directories are exclusive-create; every attempt enters ledger.jsonl. The runner blocks exploration without accepted fixtures/controls and an overhead assessment, and refuses a second exploratory attempt. Historical E1, Stage 1 and Stage 2 raw files/reports remain unchanged. Stage 3 is exploratory static budgeting only.
