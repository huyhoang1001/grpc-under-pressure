# Milestone status — 2026-10-26

## M1: BLOCKED / INCOMPLETE

Validated against the uploaded EXPERIMENT-001.md (byte-identical copy).

### Present
- Research directory skeleton and frozen specification
- Conceptual proto3 client-streaming contract
- Rust toolchain target and implementation decision log

### Missing M1 exit criteria
- Rust Cargo package, Go module, compilable generated protobuf bindings
- Exact dependency pins/lockfiles and reproducible build commands
- Source audit of pinned tonic/HTTP2 receive flow-control semantics
- Successful builds and tests on an environment with Rust, Go and protoc

### Actual environment checks
- `go version`: go1.23.2 linux/amd64 (exit 0)
- `go test ./...` at repository root: no main module (exit 1)
- `cargo test`: cargo: command not found (exit 127)
- `protoc --version`: protoc: command not found (exit 127)
- `cmp experiments/001/EXPERIMENT-001.md /mnt/data/EXPERIMENT-001.md`: exit 0

These are environment/scaffold failures, not failing assertions. No application tests exist.

## Technical decisions and unresolved validity risks
- Keep V0/V1/V2 worker and payload behavior identical; only queue policy differs.
- V2 reserves capacity before receiving the next message.
- Count queue-owned, handler-owned, worker-owned bytes separately; RSS is not an attribution mechanism.
- Do not infer wire delivery or server processing from successful grpc-go `Send` calls.
- Pin and audit tonic/h2/grpc-go receive/flow-control behavior before making transport claims.
- Verify unsaturated Go sender capacity, one worker/stream/connection, and memory abort limits before benchmark runs.
- Go package option currently uses `example.com/...`; replace with a stable module path when establishing the Go module, consistently with generated code.

## Gate
M2 is NOT authorized to start until M1 dependencies/source audit and build/test verification pass.
