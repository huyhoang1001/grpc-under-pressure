# E1 implementation decisions — M1

Source of truth: `EXPERIMENT-001.md`. These are implementation clarifications, not changes to H1.

- One client-streaming RPC, one HTTP/2 connection, one stream, one worker; no per-message tasks.
- V0 processes sequentially. V1 receives then transfers owned payload to an unbounded Tokio MPSC. V2 reserves bounded MPSC capacity before requesting the next message; K=32 for the primary comparison.
- Handler-local, queued, and worker-owned payload bytes are distinct. A successful Go Send is **not** a delivery acknowledgment.
- Summary `accepted` counts successful application handoffs (or direct processing admission); `processed` counts completed service intervals. Normal completion waits for worker drain. Aborts/errors have separately documented semantics.
- Queue accounting requires precise ownership transition points and consistent snapshots; independent atomic gauge loads are not a transactional snapshot.
- Main comparison uses identical payload generation, service time, transport settings, runtime settings, and offered-load schedule; calibration must demonstrate an unsaturated sender.
- Warmup must not leave an unmeasured backlog at the start of a measurement. Choose and document a precise warmup protocol before M5.
- Cancellation is cleanup only in E1; no cancellation treatment group.
- RSS cannot be attributed to h2, tonic, or the application queue without additional evidence.

## Open source-audit questions (blocking a transport-mechanism claim)

1. Pin exact tonic, tokio, prost, h2/hyper, grpc-go and codegen versions, then commit lockfiles and checksums.
2. Inspect pinned `tonic::Streaming::message` / receive polling and h2 window-release paths; record commit hashes and file/line references.
3. Verify grpc-go client Send buffering semantics and applicable stream/connection flow-control settings.
4. Choose and record OS/kernel, cleartext h2c capture setup, and host-specific RSS abort limit before measured runs.
5. Confirm whether bounded `reserve` + receive handles EOF/errors without leaking permits and how server shutdown is coordinated.
