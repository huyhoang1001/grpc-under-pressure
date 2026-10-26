# Recorded execution commands

These commands are transcribed from the retained manifests, not executed during this evidence audit. Working directory: `/workspace/grpc-under-pressure` (reported in REPORT.md). Absolute paths describe the original machine; they are not links or commands for the reviewer to run unchanged.

Primary runs used no h2 tracing. The diagnostic runner sets `RUST_LOG=h2=trace`; this environment setting is visible in the retained runner source, rather than a captured per-run environment dump. See [run.py](../run.py).

## control-bounded

Manifest: [results/e1/control-bounded/manifest.json](../results/e1/control-bounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:50:43Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/control-bounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 50 --seconds 4 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/control-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/control-bounded/client.json
```

## control-direct

Manifest: [results/e1/control-direct/manifest.json](../results/e1/control-direct/manifest.json)

Recorded start (UTC): `2026-10-26T11:50:25Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/control-direct/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 50 --seconds 4 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/control-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/control-direct/client.json
```

## control-unbounded

Manifest: [results/e1/control-unbounded/manifest.json](../results/e1/control-unbounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:50:34Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/control-unbounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 50 --seconds 4 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/control-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/control-unbounded/client.json
```

## diagnostic-bounded

Manifest: [results/e1/diagnostic-bounded/manifest.json](../results/e1/diagnostic-bounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:57:59Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/diagnostic-bounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 4 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/diagnostic-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/diagnostic-bounded/client.json
```

## diagnostic-unbounded

Manifest: [results/e1/diagnostic-unbounded/manifest.json](../results/e1/diagnostic-unbounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:57:45Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/diagnostic-unbounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 4 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/diagnostic-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/diagnostic-unbounded/client.json
```

## overload-1-bounded

Manifest: [results/e1/overload-1-bounded/manifest.json](../results/e1/overload-1-bounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:51:56Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-1-bounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-1-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-1-bounded/client.json
```

## overload-1-direct

Manifest: [results/e1/overload-1-direct/manifest.json](../results/e1/overload-1-direct/manifest.json)

Recorded start (UTC): `2026-10-26T11:52:10Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-1-direct/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-1-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-1-direct/client.json
```

## overload-1-unbounded

Manifest: [results/e1/overload-1-unbounded/manifest.json](../results/e1/overload-1-unbounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:51:15Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-1-unbounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-1-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-1-unbounded/client.json
```

## overload-2-bounded

Manifest: [results/e1/overload-2-bounded/manifest.json](../results/e1/overload-2-bounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:52:23Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-2-bounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-2-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-2-bounded/client.json
```

## overload-2-direct

Manifest: [results/e1/overload-2-direct/manifest.json](../results/e1/overload-2-direct/manifest.json)

Recorded start (UTC): `2026-10-26T11:52:37Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-2-direct/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-2-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-2-direct/client.json
```

## overload-2-unbounded

Manifest: [results/e1/overload-2-unbounded/manifest.json](../results/e1/overload-2-unbounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:52:50Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-2-unbounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-2-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-2-unbounded/client.json
```

## overload-3-bounded

Manifest: [results/e1/overload-3-bounded/manifest.json](../results/e1/overload-3-bounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:53:44Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-3-bounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-3-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-3-bounded/client.json
```

## overload-3-direct

Manifest: [results/e1/overload-3-direct/manifest.json](../results/e1/overload-3-direct/manifest.json)

Recorded start (UTC): `2026-10-26T11:53:31Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-3-direct/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-3-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-3-direct/client.json
```

## overload-3-unbounded

Manifest: [results/e1/overload-3-unbounded/manifest.json](../results/e1/overload-3-unbounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:53:58Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-3-unbounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-3-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-3-unbounded/client.json
```

## overload-4-bounded

Manifest: [results/e1/overload-4-bounded/manifest.json](../results/e1/overload-4-bounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:54:53Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-4-bounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-4-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-4-bounded/client.json
```

## overload-4-direct

Manifest: [results/e1/overload-4-direct/manifest.json](../results/e1/overload-4-direct/manifest.json)

Recorded start (UTC): `2026-10-26T11:54:39Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-4-direct/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-4-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-4-direct/client.json
```

## overload-4-unbounded

Manifest: [results/e1/overload-4-unbounded/manifest.json](../results/e1/overload-4-unbounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:55:06Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-4-unbounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-4-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-4-unbounded/client.json
```

## overload-5-bounded

Manifest: [results/e1/overload-5-bounded/manifest.json](../results/e1/overload-5-bounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:56:29Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-5-bounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-5-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-5-bounded/client.json
```

## overload-5-direct

Manifest: [results/e1/overload-5-direct/manifest.json](../results/e1/overload-5-direct/manifest.json)

Recorded start (UTC): `2026-10-26T11:56:42Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-5-direct/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-5-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-5-direct/client.json
```

## overload-5-unbounded

Manifest: [results/e1/overload-5-unbounded/manifest.json](../results/e1/overload-5-unbounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:55:48Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-5-unbounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-5-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-5-unbounded/client.json
```

## overload-6-direct

Manifest: [results/e1/overload-6-direct/manifest.json](../results/e1/overload-6-direct/manifest.json)

Recorded start (UTC): `2026-10-26T11:57:32Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-6-direct/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 12 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/overload-6-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/overload-6-direct/client.json
```

## sender-calibration-bounded

Manifest: [results/e1/sender-calibration-bounded/manifest.json](../results/e1/sender-calibration-bounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:50:39Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant bounded --capacity 32 --service-ms 1 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/sender-calibration-bounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 3 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/sender-calibration-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/sender-calibration-bounded/client.json
```

## sender-calibration-direct

Manifest: [results/e1/sender-calibration-direct/manifest.json](../results/e1/sender-calibration-direct/manifest.json)

Recorded start (UTC): `2026-10-26T11:50:21Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant direct --capacity 32 --service-ms 1 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/sender-calibration-direct/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 3 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/sender-calibration-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/sender-calibration-direct/client.json
```

## sender-calibration-unbounded

Manifest: [results/e1/sender-calibration-unbounded/manifest.json](../results/e1/sender-calibration-unbounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:50:30Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant unbounded --capacity 32 --service-ms 1 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/sender-calibration-unbounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 3 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/sender-calibration-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/sender-calibration-unbounded/client.json
```

## worker-calibration

Manifest: [results/e1/worker-calibration/manifest.json](../results/e1/worker-calibration/manifest.json)

Recorded start (UTC): `2026-10-26T11:50:49Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1/worker-calibration/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 1000 --seconds 3 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1/worker-calibration/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1/worker-calibration/client.json
```

## final-bounded

Manifest: [results/final-smoke/final-bounded/manifest.json](../results/final-smoke/final-bounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:59:37Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/final-smoke/final-bounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 1 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/final-smoke/final-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/final-smoke/final-bounded/client.json
```

## final-direct

Manifest: [results/final-smoke/final-direct/manifest.json](../results/final-smoke/final-direct/manifest.json)

Recorded start (UTC): `2026-10-26T11:59:30Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/final-smoke/final-direct/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 1 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/final-smoke/final-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/final-smoke/final-direct/client.json
```

## final-unbounded

Manifest: [results/final-smoke/final-unbounded/manifest.json](../results/final-smoke/final-unbounded/manifest.json)

Recorded start (UTC): `2026-10-26T11:59:32Z`. Exit statuses: server `0`, client `0`.

```sh
/workspace/grpc-under-pressure/server/target/debug/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/final-smoke/final-unbounded/server.csv
/workspace/toolchains/bin/pressure-loadgen --rate 300 --seconds 1 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/final-smoke/final-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/final-smoke/final-unbounded/client.json
```
