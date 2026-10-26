# M1 source audit

Inspected the registry/module sources actually installed for this build, rather than latest documentation. Rust source archive checksums are in `server/Cargo.lock`; Go module checksums are in `loadgen/go.sum`. Complete resolved versions and host details are in `results/m1-manifest.json`.

## Receiver credit path

- tonic 0.14.2, crate VCS commit `03894a2708c562d6b31c155b1ddc850510ed6c0e`, `tonic/src/codec/decode.rs`: `Streaming::message` (327) polls the stream; `poll_next` (399–403) decodes buffered data first, then polls more body frames; `poll_frame` (246–280) appends DATA to its decode buffer. There can be transport/decoder buffering outside the application queue.
- Hyper 1.12.0, crate VCS commit `7f67699ce32d717081deb7018b4da7d679277ac0`, `src/body/incoming.rs` (180–192): after `h2.poll_data` returns bytes, Hyper calls `h2.flow_control().release_capacity(bytes.len())` before returning the DATA frame. This precedes application worker completion and can precede completion of an entire protobuf message.
- h2 0.4.20, crate VCS commit `b0e890842ac16d3c76836fd4fcc06421acb15fa7`, `src/share.rs` (164–170, 532–539): capacity release delegates to the internal receive flow controller; documentation explicitly describes thresholded/coalesced WINDOW_UPDATE emission. Release does not imply one immediate WINDOW_UPDATE frame per message.

Source-supported interpretation: repeatedly consuming tonic messages can replenish transport credit independently of queued application work. Awaiting bounded capacity before polling the next message stops that application's receive loop; it does not remove bytes already buffered in the decoder, transport, socket, or peer. This is not packet evidence; no DATA/WINDOW_UPDATE trace was collected in M1.

## Sender semantics

- grpc-go v1.76.0, `stream.go` (119–128, 902 onward): SendMsg waits for scheduling capacity or termination, and explicitly does not wait for server receipt. Completion is not application acknowledgment.
- `internal/transport/flowcontrol.go` (28–68): write quota is a soft scheduling limit; exhausted quota waits for replenishment or stream termination.
- `internal/transport/controlbuf.go` (989–1028): the writer considers stream and connection quotas before writing DATA, and replenishes local write quota as data moves onward.

A sequential sender still has library buffering. M2 must record Send attempts/completions/latency separately from worker completions, disable retries, and never enqueue a paced workload in a second application producer queue.

## Channel ownership and lifecycle

Tokio 1.48.0, crate VCS commit `556820ff84030b37e74e11b86b7733f5795770ea`, `tokio/src/sync/mpsc/bounded.rs` (1080–1120, 1692 onward) supplies capacity reservation and permit handoff. Tests demonstrate a full channel prevents reservation, dropping an EOF permit restores capacity, and closing the sender permits drain. These tests validate primitives; they do not validate a future network handler's cancellation behavior.

Required implementation controls before measurements:

1. V0/V1/V2 use identical payload, service interval, runtime, compression and transport settings; K=32 for primary V2. Explicit fixed receive windows and adaptive-window settings must be captured in run manifests.
2. Use one handler, one worker, no per-message spawn. The handler owns a worker task guard so cancellation aborts and joins cleanup rather than detaching a draining unbounded backlog.
3. Serialize enqueue/dequeue ownership transitions and metric snapshots. Never present independent atomic loads as a consistent accounting snapshot. Distinguish queued, handler and worker bytes, discarded-on-error bytes, and transport memory.
4. Independently calibrate worker capacity and the unsaturated sender. Do not catch up missed pacing deadlines with bursts; specify scheduled, attempted and skipped work.
5. Use a fresh process, no workload warmup backlog, fixed seed and randomized/interleaved run order. Predeclare queue/RSS abort limits and drain timeout; preserve partial results and failures.
6. Add network integration tests for EOF, cancellation, capacity-before-read ordering and exact final accounting. Primitive tests alone cannot pass the experiment validity gate.

No experimental claims, fixed-window configuration, cancellation integration guarantees, or memory safety claims are established by this audit.

## Runtime follow-up

The runtime now implements the listed queue ordering, serialized accounting, independent calibration, fresh-process lifecycle and safety controls. Separate h2 diagnostics and exact observed limits are in REPORT.md and results/e1/. The earlier statements about no trace refer to M1: later instrumentation records stack DATA/WINDOW_UPDATE events, still without a wire packet capture. Final integration tests cover EOF/drain, deadlines and both safety aborts. Service-time percentiles and a live Prometheus exporter remain omitted; explicit CSV counters and cumulative service timing are documented.
