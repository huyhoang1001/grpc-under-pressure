# gRPC Under Pressure

Rust/Tokio/tonic receiver and Go/grpc-go load generator for [Experiment 001](experiments/001/EXPERIMENT-001.md): where transport flow control stops and application backpressure begins. No external services are required.

The direct, unbounded and bounded scenarios are implemented. Short repeated measurements, limitations and exact commands are in [REPORT.md](experiments/001/REPORT.md), with raw samples under [results/](experiments/001/results/). These are research results for this stack/workload, not production memory-safety guarantees. Adaptive concurrency is out of scope.

On Linux x86_64 with Bash, Python 3.12+, a C linker and network access, from this checkout:

```sh
bash scripts/bootstrap.sh
source scripts/dev-env.sh
bash scripts/check.sh
```

Tools and caches use `/workspace/toolchains`; these cloud scripts assume this layout. Bootstrap prepares checksum-verified Rust 1.99.1 / Go 1.27.3 and verified locked dependencies. Generated Go bindings are committed; Rust bindings are generated at build time using pinned protoc 31.1.

For a functional smoke test with all three variants, fresh processes and cleanup:

```sh
python3 experiments/001/run.py --output /tmp/pressure-calibration --phase calibration
```

Use a new output directory on each invocation. See [experiment instructions](experiments/001/README.md) for individual startup, measurements and analysis. Optional code regeneration: `bash scripts/generate-go.sh`.
