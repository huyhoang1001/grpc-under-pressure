# gRPC Under Pressure

Reproducible research codebase for EXPERIMENT-001: application queue growth despite HTTP/2 flow control.

- [`experiments/001/EXPERIMENT-001.md`](experiments/001/EXPERIMENT-001.md): frozen specification
- [`experiments/001/DECISIONS.md`](experiments/001/DECISIONS.md): decisions and open audit items
- [`proto/ingest.proto`](proto/ingest.proto): conceptual client-streaming contract

## Status

**M1 blocked / incomplete (validation 2026-10-26).** Protocol and directory skeleton exist. Rust server, Go load generator, dependency lockfiles, transport source audit and build commands are not yet implemented or validated. Do not use this skeleton to make experimental claims.

Rust target: 1.99.1 (`rust-toolchain.toml`). Go target: 1.27.3 (to be pinned in `go.mod` when the Go module is implemented).

See [`experiments/001/MILESTONE-STATUS.md`](experiments/001/MILESTONE-STATUS.md) for executed checks, blockers, and gate status.
