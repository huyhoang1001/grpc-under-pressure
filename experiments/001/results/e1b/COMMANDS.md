# E1B exact recorded child commands

All commands below were executed by the runner. Full workload, environment, limits and outcomes remain in each linked manifest.

## overload-1-bounded

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-bounded/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-bounded/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-bounded/latency.csv
```

## overload-1-direct

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-direct/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-direct/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-direct/latency.csv
```

## overload-1-unbounded

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-unbounded/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-unbounded/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-1-unbounded/latency.csv
```

## overload-2-bounded

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-bounded/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-bounded/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-bounded/latency.csv
```

## overload-2-direct

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-direct/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-direct/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-direct/latency.csv
```

## overload-2-unbounded

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-unbounded/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-unbounded/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-2-unbounded/latency.csv
```

## overload-3-bounded

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-bounded/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-bounded/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-bounded/latency.csv
```

## overload-3-direct

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-direct/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-direct/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-direct/latency.csv
```

## overload-3-unbounded

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-unbounded/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-unbounded/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-3-unbounded/latency.csv
```

## overload-4-bounded

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-bounded/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-bounded/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-bounded/latency.csv
```

## overload-4-direct

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-direct/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-direct/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-direct/latency.csv
```

## overload-4-unbounded

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-unbounded/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-unbounded/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-4-unbounded/latency.csv
```

## overload-5-bounded

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant bounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-bounded/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-bounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-bounded/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-bounded/latency.csv
```

## overload-5-direct

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant direct --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-direct/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-direct/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-direct/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-direct/latency.csv
```

## overload-5-unbounded

Git: `9773403fbb8d156b2773687254fe038c6a5105d1`; cwd: `/workspace/grpc-under-pressure`; runtime `RUST_LOG=warn`.

```sh
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/grpc-under-pressure/server/target/release/pressure-server --variant unbounded --capacity 32 --service-ms 10 --queue-limit 268435456 --rss-limit 536870912 --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-unbounded/server.csv
prlimit --cpu=120 --fsize=67108864 --core=0 -- /workspace/toolchains/bin/pressure-loadgen-e1b --rate 300 --seconds 60 --payload 16384 --timeout 120s --csv /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-unbounded/client.csv --summary /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-unbounded/client.json --telemetry /workspace/grpc-under-pressure/experiments/001/results/e1b/runs/overload-5-unbounded/latency.csv
```
