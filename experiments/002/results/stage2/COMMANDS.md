# Stage 2 exact recorded child commands

These commands are transcribed from retained manifests; this file does not execute them.

## buffered-1

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `None`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/buffered-1/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/buffered-1/marker.txt --service-schedule constant --event-io buffered
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/buffered-1/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/buffered-1/marker.txt --rate 80 --seconds 4 --timeout 120s
```

## buffered-2

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `None`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/buffered-2/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/buffered-2/marker.txt --service-schedule constant --event-io buffered
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/buffered-2/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/buffered-2/marker.txt --rate 80 --seconds 4 --timeout 120s
```

## discard-1

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `None`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/discard-1/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/discard-1/marker.txt --service-schedule constant --event-io discard
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/discard-1/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/discard-1/marker.txt --rate 80 --seconds 4 --timeout 120s
```

## discard-2

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `None`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/discard-2/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/discard-2/marker.txt --service-schedule constant --event-io discard
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/discard-2/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/discard-2/marker.txt --rate 80 --seconds 4 --timeout 120s
```

## exploratory-1

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `None`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/exploratory-1/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/exploratory-1/marker.txt --service-schedule contract --event-io buffered
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/exploratory-1/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/exploratory-1/marker.txt --rate 80 --seconds 36 --timeout 120s
```

## schedule-smoke

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `None`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/schedule-smoke/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/schedule-smoke/marker.txt --service-schedule contract --event-io buffered
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/schedule-smoke/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/schedule-smoke/marker.txt --rate 80 --seconds 0.8 --timeout 120s
```

## stage1-regression/cancel-capacity

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `cancellation`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --addr 127.0.0.1:50053 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/cancel-capacity/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/cancel-capacity/marker.txt
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/cancel-capacity/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/cancel-capacity/marker.txt --rate 1000 --seconds 2 --timeout 1200ms
```

## stage1-regression/normal-1

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `None`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --addr 127.0.0.1:50053 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-1/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-1/marker.txt
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-1/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-1/marker.txt --rate 80 --seconds 0.8 --timeout 120s
```

## stage1-regression/normal-2

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `None`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --addr 127.0.0.1:50053 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-2/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-2/marker.txt
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-2/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-2/marker.txt --rate 80 --seconds 0.8 --timeout 120s
```

## stage1-regression/normal-3

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `None`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --addr 127.0.0.1:50053 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-3/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-3/marker.txt
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-3/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/normal-3/marker.txt --rate 80 --seconds 0.8 --timeout 120s
```

## stage1-regression/worker-error

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `worker_error`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --addr 127.0.0.1:50053 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/worker-error/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/worker-error/marker.txt --test-fail-after 1
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/worker-error/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/worker-error/marker.txt --rate 80 --seconds 0.8 --timeout 120s
```

## stage1-regression/worker-panic

Source `84509545abf6a5f139687250757e67703477a5c1`; expected fault `worker_panic`; working directory `/workspace/grpc-under-pressure`.

```sh
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/grpc-under-pressure/server/target/debug/pressure-stage1 --addr 127.0.0.1:50053 --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/worker-panic/server --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/worker-panic/marker.txt --test-panic-after 1
prlimit --cpu=10 --fsize=16777216 --core=0 -- /workspace/toolchains/bin/pressure-stage1-client --output /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/worker-panic/client --marker /workspace/grpc-under-pressure/experiments/002/results/stage2/stage1-regression/worker-panic/marker.txt --rate 80 --seconds 0.8 --timeout 120s
```
