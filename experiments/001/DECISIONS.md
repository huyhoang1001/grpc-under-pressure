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

## M1 implementation increment

- The Go module path is `github.com/huyhoang1001/grpc-under-pressure/loadgen`; the proto option and committed generated bindings agree.
- Pin protoc via `protoc-bin-vendored` 3.2.0 (compiler 31.1), tonic/tonic-prost/build 0.14.2, prost 0.14.1, Tokio 1.48.0, grpc-go 1.76.0, Go protobuf 1.36.10, Go codegen 1.36.10 / grpc codegen 1.5.1. Transitive versions/checksums are locked.
- Source audit is in SOURCE-AUDIT.md; runtime/packet verification remains outstanding. Do not carry forward the original open items as evidence of missing toolchains: current capabilities are in REPORT.md.
- Raw evidence lives under `results/` per the current implementation request. No measured runs exist in this increment.

## Runtime and measured increment

- Source audit questions 1–3 now have pinned sources and paths in SOURCE-AUDIT.md; packet-level timing remains unverified. Explicit server receive windows are 65,535 bytes each, adaptive receive windows disabled; transport settings match across variants.
- A shared lock covers queue ownership transitions and sampling. Worker dequeue uses try_recv under that lock, with Notify for idle waits, so freeing a bounded slot cannot precede its accounting transition. No per-message tasks are created.
- Measurements use a fresh process and no traffic warmup; independent calibration precedes the runs. Missed sender slots are skipped/counted with no catch-up bursts.
- Initial overload is 12 s per variant, 300/s, 16 KiB, with 10 ms sleep service and K=32. This shared shortened calibration-scale run does not change H1 or imply 60 s stability. Five valid repeats and 50/s controls were executed.
- Safety: 256 MiB queued payload checked before unbounded handoff; 512 MiB server RSS sampled every 200 ms; 120 s whole-RPC deadline includes drain. The machine's cgroup limit is 32 GiB. Both abort paths are tested. Partial evidence is retained.
- CSV instrumentation replaces a live Prometheus exporter for this increment. Connection counter is total accepts; paired with a single RPC and disabled retries it verifies the one-connection topology. Service timing is cumulative rather than a percentile histogram.
- Cancellation guard aborts the worker. A postmeasurement cancellation flag prevents a completion racing discarded-message accounting. Primary evidence retains the earlier exact source snapshot; final hardened source passed tests and smoke runs, but primary measurements were not repeated after this change.
- One outcome-independent provenance exclusion is annotated in overload-1-direct's manifest and replaced by overload-6-direct. All original samples remain.
- Results support a scoped short-run application queue claim. h2 stack logs and source audit support the transport explanation; no packet capture was available. See REPORT.md before drawing article conclusions.
