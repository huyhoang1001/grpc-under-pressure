# Experiment 001

[Specification](EXPERIMENT-001.md) · [Decisions](DECISIONS.md) · [Source audit](SOURCE-AUDIT.md) · [Report](REPORT.md)

From `/workspace/grpc-under-pressure`:

```sh
bash scripts/bootstrap.sh
source scripts/dev-env.sh
bash scripts/check.sh
```

The checks build both executables and run 4 Rust, 2 Go and 8 process integration tests. The compiler/codegen/dependency pins are in repository manifests and lockfiles. No secrets, databases or external runtime services are needed.

For one RPC, use two shells. Start a fresh server for each workload:

```sh
# Shell 1, repository root, after sourcing scripts/dev-env.sh
server/target/debug/pressure-server --variant bounded --capacity 32 \
  --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 \
  --csv /tmp/pressure-server.csv
# Wait for stderr: ready 127.0.0.1:50051 variant=bounded ...
```

```sh
# Shell 2, repository root, after sourcing scripts/dev-env.sh
pressure-loadgen --rate 50 --seconds 4 --timeout 120s \
  --csv /tmp/pressure-client.csv --summary /tmp/pressure-client.json
```

A successful functional check exits zero and returns matching nonzero accepted/processed counts in the JSON Summary; server queue/worker bytes should drain to zero. Stop the server with Ctrl-C. Readiness text alone is not application validation. Choose `direct`, `unbounded`, or `bounded`; the server intentionally permits just one RPC per fresh process. Compression/retries are off. These executables are not production servers.

For repeatable runs and automatic cleanup:

```sh
# Always choose an unused output directory. Each run retains its own manifest/logs/CSVs.
python3 experiments/001/run.py --output /tmp/e1-reproduction --phase calibration
python3 experiments/001/run.py --output /tmp/e1-reproduction --phase measured
python3 experiments/001/run.py --output /tmp/e1-reproduction --phase diagnostic
python3 experiments/001/analyze.py /tmp/e1-reproduction
# Optional figures require matplotlib (present on this machine):
MPLCONFIGDIR=/workspace/toolchains/matplotlib python3 experiments/001/plot.py /tmp/e1-reproduction
MPLCONFIGDIR=/workspace/toolchains/matplotlib python3 experiments/001/transport.py /tmp/e1-reproduction
```

Review calibration before proceeding to measurement: sender capability should be at least 285 completed Sends/s in fast-consumer runs, worker capacity about 89–90/s here, and below-capacity controls should drain without sustained queue growth. Inspect failures instead of repeating unchanged commands. `config/primary.json` documents the executed initial plan; runner arguments and per-run manifests are the authoritative settings. The default measurement is 12 s per overload, then drain, not the proposed longer publication run. RSS is sampled, so abrupt RSS exhaustion can overshoot a threshold between checks. The queued-payload cap is checked at enqueue.

`analyze.py` verifies consistent ownership and queue accounting, topology, final drain and safety limits, then reports medians/ranges from valid overload runs. It retains explicit exclusions; it never silently drops failed runs. Failed/aborted runs keep partial data; investigate them before deciding whether and how to replace a run. The checked-in dataset includes an annotated source-provenance exclusion and replacement; see REPORT.md.

CSV column mapping: `received` → grpc_messages_received_total; `enqueued/dequeued/processed` → application counters; `queue_depth/queue_bytes` → owned queue gauges; `handler_bytes/worker_bytes` → payload held outside queue; `enqueue_wait_ns/service_ns` → cumulative durations; `rss_bytes` → Linux RSS. Client columns distinguish scheduled slots, attempts, completed Sends, skipped slots, cumulative Send duration and calls >20 ms. Per-run JSON adds Send percentiles and final Summary/status. `process.csv` records Linux CPU ticks, RSS and thread counts; CPU ticks are converted with the recorded CLK_TCK, not an assumed frequency. Connection instrumentation counts accepted connections, not active socket lifetimes.

Raw results use `results/` per the implementation request, rather than the frozen specification's planned `runs/` location. Existing evidence and generated figures are committed as research artifacts; compiled binaries, caches and packet captures are not.
