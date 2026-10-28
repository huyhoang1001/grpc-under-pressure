# Stage 4 validation protocol (declared before execution)

The frozen contract `../EXPERIMENT-002.md` is unchanged. `--policy adaptive` starts B=16; fixed32/fixed8 retain B=32/8. All share K=32, gate, handler, worker, 10/40/10 ms schedule, 200 ms sampler and now a 500 ms observation task. Fixed policies compute/log identical feedback/proposals but never apply budget changes (`fixed_policy_hold`). No tunable controller flags or additional workers.

The first tick is at workload-start +500 ms, then every 500 ms on that monotonic grid (no tick at zero). Feedback is count/sum of completed measured service durations between actual tick snapshots; the first window begins at workload start. Delayed ticks do not replay synthetic feedback. Scheduled time, observed time, lateness and actual window boundaries are logged. Missing grid ticks or >100 ms lateness invalidate the evidence instead of hiding timing gaps. Ineligible (<5 completion) windows preserve EWMA, reset both streaks and hold B. Eligible feedback initializes EWMA from the first mean, thereafter alpha=.2; strict >125/<75 thresholds, two consecutive eligible ticks, near-full Q+R>=B-1, ceil-halving/increment and [1,32] bounds are unchanged. Tick trace contains pre/post streaks, proposal and actual decision.

All tick decisions and queue ownership transitions use the same state lock. A shrink records O_at_last_shrink and preserves work/R. New reservation still requires O<B regardless of carryover; physical K stays32. Growth/shrink wake registered waiters. Existing reservations may hand off or release after shrink. State assertions use the frozen carryover bound plus exact counters/bytes. Both worker and tick tasks are handler-owned; EOF stops ticks atomically with EOF before drain, cancellation/failure wakes and stops both; unexpected controller termination is supervised. Controller CSV streams through a fixed 64KiB buffer, flushed each tick; additional lock-held I/O cost is measured separately. No event/vector history in the controller (only EWMA, streaks, counter snapshots and scalar carryover).

Validation order: Rust/Go build/test/lint; source pin; short fresh-process fixed32/fixed8 regressions, adaptive healthy and schedule smoke (1.6s at80/s, at least3ticks), adaptive cancellation (1000/s,1200ms deadline, exercising shrink while over budget), first-message worker error/panic fixtures. Deterministic units cover boundaries, insufficient feedback, shrink/R/no-read-ahead, growth wake, receive error, EOF, abort supervision, races and paced healthy progress. All fixtures retain failures, limits, hashes and exact argv. Independent offline audit replays each feedback decision from streamed completions, merges ticks/events to check instantaneous admission, and verifies final accounting. Only after acceptance is assessed may ONE explicitly labeled exploratory adaptive run execute80/s for36s; never retry/tune based on results. No primary five-repeat matrix.

Exploratory frozen parameters match accepted Stages2/3: same debug Rust/default optimized Go, exact retained client SHA, payload16384/seed1, 65535 HTTP/2 stream/connection windows (adaptive windows off), Tokio/GOMAXPROCS2, one fresh server, 200ms sampling, inherited affinity. RSS guards512/128MiB; CPU10s/process, file16MiB, no core, RPC120s including drain, wall125s. Client slots are never caught up. Binaries remain outside Git. Each manifest separately pins new server/harness and accepted client source8450954, hashes and dirty state. No historical file is altered.

Compare descriptively with the accepted fixed32 Stage2 and fixed8 Stage3 runs; source/version/time/admitted-cohort differences are confounders. No primary/adaptive advantage claimed. Report pooled enqueue-[12,36) residence p95, separate phases, worker throughput, all skips/completed Sends, Send-call duration (not pure HTTP/2 blocking), drain and byte/count accounting. Recovery: report first sampled empty queue; optionally a labeled 200ms-grid exploratory three-second enqueue-cohort window screen against each policy's own healthy p95 and >=95% healthy throughput, with window start and confirmation end, censored if none. This window screen does not prove continuous instantaneous recovery or satisfy primary H4.

```sh
source scripts/dev-env.sh
cargo fmt --manifest-path server/Cargo.toml -- --check
cargo test --locked --manifest-path server/Cargo.toml -j4
cargo clippy --locked --manifest-path server/Cargo.toml --all-targets -- -D warnings
cargo build --locked --manifest-path server/Cargo.toml -j4
(cd experiments/002/client && go mod verify && go test -mod=readonly -race -v ./... && go vet ./... && go build -mod=readonly -o /workspace/toolchains/bin/pressure-stage4-client-buildcheck .)
python3 experiments/002/stage4/run.py --output experiments/002/results/stage4 --phase acceptance
python3 experiments/002/stage4/verify.py experiments/002/results/stage4
python3 experiments/002/stage4/analyze.py experiments/002/results/stage4
python3 experiments/002/stage4/run.py --output experiments/002/results/stage4 --phase exploratory
MPLCONFIGDIR=/workspace/toolchains/matplotlib python3 experiments/002/stage4/analyze.py experiments/002/results/stage4
python3 experiments/002/stage4/verify.py experiments/002/results/stage4
```

Use a fresh directory to reproduce. Existing attempts are exclusive-create and exploration is refused if any prior exploratory directory exists. The runner requires the retained client hash from accepted Stage2; code is unchanged. Archives contain raw metrics/manifests, not executables or environment-variable dumps.

## Recorded acceptance-fixture correction

The original 1200ms cancellation attempt `adaptive-cancel` was preserved invalid: RPC time includes ~350ms setup/barrier, so only one 500ms tick occurred; accounting passed but shrink coverage did not. Do not alter it. A distinct `adaptive-cancel-after-shrink` fixture uses1000/s,2.5s offered schedule,2s RPC deadline to allow two ticks before deliberate cancellation. Frozen36s workload/120s deadline, safety guards and controller unchanged. Current session resumes only the missing fixtures via `--phase acceptance-completion`; passing fixtures are not repeated. `declared-exclusions.json` records the original issue; verification/analysis expose it, not treat it as a passing run. Fresh `--phase acceptance` uses the corrected named fixture.
