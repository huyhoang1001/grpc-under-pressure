# Stage 2 — deterministic fixed32 capacity disturbance

Scope: add only the frozen service schedule and observer assessment. Default server invocation stays Stage 1 constant 10 ms. `--service-schedule contract` chooses 10 ms at service starts in [0,12), 40 ms in [12,24), 10 ms at >=24 (including >=36 drain), measured on the server monotonic marker. A running service interval is never retimed when a boundary passes. Physical K/static pending limit remain 32; no fixed8, dynamic budget or controller exists.

New event fields identify exact service-start time, selected delay and service-start phase. Queue/service histograms remain assigned by enqueue phase as before. A separate phase log records nominal boundaries and actual timer wakeups; selection does not depend on that logger. The 200 ms snapshot distinguishes configured delay at snapshot time from the in-flight message's selected delay.

## Observer assessment before exploratory execution

The accepted Stage 1 logger formats buffered records while holding the state lock, and flushes there every 200 ms. File writes can delay admission/dequeue/completion and inflate measured service/queue residence; histograms, consistency checks, snapshot formatting and lock contention also cost time.

Use four **constant-10-ms, 80/s, 4-second** controls in ABBA order:

1. buffered event file
2. discard sink
3. discard sink
4. buffered event file

The sink keeps the same formatting, 64 KiB buffering, histogram updates, counter transitions and sampling, replacing only the event-file destination with a no-retention sink. Both remain bounded-memory. Sink runs intentionally lack a per-message event ledger and are **control-only**, never complete E2 experiment evidence. Counter/byte/histogram/clock/final Summary checks still apply. Neither mode calls fsync for server events; flush timings concern writes to the OS/page cache, not durable disk latency.

Measure cumulative/max event-format/write and flush wall times under the lock, completed-service mean and histogram p95, CPU/RSS and whole-RPC timing. Direct timings exclude their own timer/counter overhead and other instrumentation/lock costs. Offered-limited healthy controls do not measure saturated capacity loss. Two cases per mode are an exploratory observer check, not a precise overhead confidence interval. Report all differences, including noise; do not infer zero overhead from equal message counts.

## Frozen single exploratory scenario

After overhead assessment, run exactly one fixed32, buffered-event, 80 scheduled slots/s × 36 s run (2,880 slots) with 16,384-byte seeded payloads. Keep the Stage 1 debug build, two Tokio workers/GOMAXPROCS=2, fixed 65,535-byte transport windows, no compression/retries, 200 ms sampling, marker barrier, 120 s RPC deadline, 512 MiB server/128 MiB client RSS, 10 s process CPU and 16 MiB per-file limits. The runner's wall guard becomes 125 s to encompass the existing 120 s RPC deadline; the former 12 s acceptance-smoke wall guard cannot run a 36 s scenario. CPU placement is inherited unchanged and recorded. All processes run sequentially with fresh output directories and a source/binary manifest.

Analysis windows are prespecified: healthy [0,12), slowdown [12,24), recovery [24,36), drain >=36; additionally early recovery [24,28) and late recovery [32,36). Service durations are grouped by service start, queue residence by enqueue, throughput by actual completion time, and Send duration by actual call start. Distinguish nominal phase wakeup from the first worker start selecting the new delay. Report client half-close, server EOF, last worker completion and whole RPC separately. Cross-process marker alignment does not establish per-message end-to-end latency. Any failure or lack of capacity transition is retained/reported without retuning the frozen inputs or rerunning silently.

## Exact workflow

From the repository root after `source scripts/dev-env.sh`:

```sh
cargo build --locked --manifest-path server/Cargo.toml -j4
cargo test --locked --manifest-path server/Cargo.toml -j4
cargo clippy --locked --manifest-path server/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path server/Cargo.toml -- --check
(cd experiments/002/client && go mod verify && go test -mod=readonly -race -v ./... && go vet ./...)
(cd experiments/002/client && go build -mod=readonly -o /workspace/toolchains/bin/pressure-stage1-client .)
# Commit source/harness and rebuild before collecting evidence.
python3 experiments/002/smoke.py --output experiments/002/results/stage2/stage1-regression
python3 experiments/002/stage2/run.py --output experiments/002/results/stage2 --phase smoke
python3 experiments/002/stage2/run.py --output experiments/002/results/stage2 --phase overhead
python3 experiments/002/stage2/analyze.py experiments/002/results/stage2
python3 experiments/002/stage2/run.py --output experiments/002/results/stage2 --phase exploratory
MPLCONFIGDIR=/workspace/toolchains/matplotlib python3 experiments/002/stage2/analyze.py experiments/002/results/stage2
```

Existing directories are not overwritten. The runner refuses a second exploratory attempt in this output root. Ledgers retain every control and exploratory outcome. Historical E1/E1B and Stage 1 reports/raw data remain unchanged. This is not the primary five-repeat policy comparison and does not test adaptive hypotheses.
