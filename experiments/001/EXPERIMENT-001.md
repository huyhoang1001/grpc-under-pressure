# EXPERIMENT-001 — Where Does gRPC Backpressure Stop?

**Status:** Design frozen for first implementation, subject to dependency/version audit  
**Scope:** Rust/Tokio/tonic server; Go/grpc-go client; one client-streaming RPC  
**Purpose:** Isolate how an application can retain unbounded queued messages even while HTTP/2 transport flow control operates as designed.  
**No implementation code is specified here.**

## 1. Research question and precise claim

**Question:** If gRPC already provides HTTP/2 flow control, how can an application still accumulate unbounded memory under a slow-consumer workload?

**Hypothesis H1:** Under sustained offered load above a single worker's processing capacity, a tonic handler that continuously receives complete messages and successfully transfers ownership to an **unbounded** application channel can accumulate an increasing number of live, decoded messages. The transport can continue granting receive-window credit as data is consumed by the gRPC stack, despite downstream application work remaining queued. Replacing that channel with a **bounded** channel and awaiting capacity *before reading further messages* should cap that queue and eventually propagate pressure toward the Go client's streaming Send calls.

This is a statement about the **application queue**, not a claim that all process memory is intrinsically unbounded, nor that transport flow control is defective. In any finite run, memory is finite; “unbounded” means no configured application capacity limit, with positive queue-growth slope while overload persists, until resource limits intervene.

**Mechanistic prediction:** During the overloaded interval, for the unbounded variant, `enqueue_rate > completion_rate`, `queue_depth` increases approximately as the integral of that difference, and `queued_payload_bytes` rises with depth. For the bounded variant, `queue_depth <= K` (excluding the message temporarily held by the handler and the one held by the worker), and sustained achieved client send rate tends toward consumption capacity after initial buffering fills.

**Falsification / revision triggers:**
1. The unbounded variant's application-owned queue does not grow even though independently verified successful enqueue rate persistently exceeds dequeue rate. This indicates faulty accounting or a false premise; investigate before concluding.
2. The unbounded queue grows, but measured live queued bytes do not; inspect payload ownership, zero-sized/reused payloads, or metric definitions.
3. The bounded variant exceeds its declared queue capacity, as measured by the actual queue rather than a lagging metric; investigate instrumentation/implementation.
4. A bounded queue fills but the sender never experiences sustained throughput reduction *under conditions that rule out other sinks or stream termination*; inspect receive semantics, hidden buffering, and client-side buffering. This challenges the proposed propagation mechanism, not necessarily queue boundedness.
5. Packet evidence shows no relevant HTTP/2 flow-control behavior or contradicts the asserted causal path; narrow the protocol claim.

## 2. Confounders to eliminate first

| Confounder | Why it matters | Control / diagnostic |
|---|---|---|
| Go client `Send` is synchronous and can block | Nominal offered rate is not actual transmitted rate | Record scheduled attempts, completed Send calls, Send latency and block time; distinguish offered vs achieved |
| grpc-go and tonic/h2 buffer internally | Delayed client blocking does not imply absent backpressure | Record versions/configuration; capture DATA/WINDOW_UPDATE in diagnostic run; avoid claims about exact credit release without source/capture evidence |
| Message decoding/ownership | A queue item might be a clone, metadata only, or shared buffer | Record serialized payload length and application-owned payload bytes; ensure unique retained payload per message |
| Worker uses `sleep` rather than CPU | Demonstrates queueing, not CPU overload | State workload is intentionally deterministic and non-CPU-bound; CPU saturation is out of scope |
| OS RSS includes allocator retained pages | RSS can remain high after queue drains | Pair RSS with logical queue bytes; observe drain and post-drain; optionally profile live heap |
| Channel send ordering | If handler reads ahead before waiting for capacity, one or more messages remain outside queue | Define receive/send ordering precisely; account for in-handler and in-worker messages |
| Streaming response lifecycle | A client-streaming RPC can remain open until sends finish and server returns | Hold stream open for controlled load interval, then close sends and drain; set explicit deadline and cancellation rules |
| HTTP/2 stream/window settings | Different windows change buffering and timing | Pin connection/stream windows, max message size, adaptive window setting, keepalive and max concurrent streams where supported |
| Flow control applies to DATA bytes, not arbitrary application allocations | Misinterpreting window as a memory cap | Separate wire bytes, decoded bytes, and queue-owned bytes |
| Compression / payload representation | Compression can change bytes-on-wire vs retained memory | Disable compression; use deterministic, incompressible or fixed content; document generator |
| Load generator bottleneck | Sender CPU/network limits may hide overload | Record Go CPU/RSS, achieved throughput; verify worker service rate below sender's unsaturated capability |
| Multiple hidden tasks/queues | Spawned tasks can introduce another unbounded sink | One handler, one worker, no per-message spawn; explicit task ownership |
| Observability overhead | High-cardinality labels or per-message logging distort results | Aggregate counters/histograms, no per-message logs in measurement runs |
| Memory exhaustion | Unbounded variant can kill machine before evidence is collected | Memory/queue-byte abort threshold, short duration, isolated process and resource budget |
| Clock drift | Client/server timestamps cannot be directly subtracted | Compute durations within each process; align charts with run markers, not raw cross-host timestamps |

## 3. Minimum topology and contract

```
Go load generator
  paced sender / Send timing / client counters
          |
          | one client-streaming gRPC RPC, one HTTP/2 connection
          v
Rust tonic streaming handler
  read message -> [queue policy] -> single slow worker
                      |                  |
              queue accounting     processed counter
          |
  Prometheus metrics + process RSS sampler
```

**RPC contract (conceptual):** A client-streaming `Ingest(stream Payload) -> Summary` call. Each Payload has a sequence number and fixed-size opaque byte payload. Summary contains accepted and processed counts if the stream closes normally. No application acknowledgment per message is required. Client `Send` completion must not be called a server-processing acknowledgment.

**Handler:** In the unbounded variant, await the next complete inbound message, then enqueue its owned payload without a capacity wait. In the bounded variant, await the channel's capacity reservation **before requesting the next message** when feasible, then receive and enqueue; this ordering prevents accidental read-ahead. If a reservation is obtained but the stream ends, release it. In the direct variant, receive and process sequentially. A single worker processes one message per configured service interval. Avoid detached per-message tasks.

**Lifecycle:** Start metrics sampling before traffic; warm up; start one stream; run a fixed offered-load schedule; stop new sends; close the send side; allow bounded drain up to timeout; collect final counters and RSS. Cancellation is a separate later experiment, not mixed into the main comparison.

## 4. Buffer inventory and ownership boundaries

| Location | What may accumulate | Capacity/constraint | How observed |
|---|---|---|---|
| **Producer (Go)** | Payload currently generated; pacing backlog; grpc-go send/connection buffers | Generator design and grpc-go limits; `Send` may block | Send attempt/completion counters, duration, client RSS, client-side queue depth (must be zero by design) |
| **gRPC/HTTP/2 sender transport** | Encoded messages, DATA waiting on stream/connection windows, socket send buffers | Implementation settings, flow-control windows, OS buffers | Send duration, grpc-go instrumentation if available, targeted packet capture |
| **Network / kernel** | TCP send/receive buffers, packets in flight | Socket/kernel/network settings | Host network stats and optional packet capture |
| **gRPC/HTTP/2 receiver transport** | DATA frames, stream reassembly, decoded protobuf messages before handler consumption | Window limits, max message size, implementation internals | Source audit + diagnostic trace/capture; not inferred from RSS alone |
| **Handler local** | One received decoded message, possible reserved channel slot | One message per handler if ordering enforced | Explicit in-handler bytes/count gauge |
| **Application channel** | Owned decoded messages awaiting processing | Unbounded or exactly K queued entries | Queue depth and summed payload bytes on successful enqueue/dequeue |
| **Worker** | One message in service | One in-flight message | In-worker bytes/count and completion rate |
| **Receiver / downstream processing** | Any retained processed results | None permitted in E1; discard payload after work | Worker completion count and stable retained-results metric (=0) |

**Terminology:** In client-streaming, the Rust server is the **network receiver**, but the slow worker is the **application consumer**. Do not conflate the two. HTTP/2 flow-control credit may be replenished before the slow worker finishes; exact timing is an implementation detail to verify against pinned source and traces.

## 5. Experiment matrix

| Variant | Handler behavior | Application queue | Expected qualitative behavior |
|---|---|---|---|
| V0 Direct | Receive, process, repeat | None | Slow receive rate; eventual sender pressure |
| V1 Unbounded | Receive, enqueue, repeat | Tokio unbounded MPSC | Queue growth when successful enqueue rate > worker rate; potentially increasing live memory |
| V2 Bounded | Reserve capacity, receive, enqueue, repeat | Tokio bounded MPSC, K=32 | Queue saturates at K; eventual sender pressure |

**Secondary diagnostic (not a fourth required result):** Repeat V2 with K=1 and K=128 to check whether initial burst/lag scales with queue capacity. Do not tune K separately per workload to manufacture a favorable result.

**Proposed initial parameters (to calibrate, not claims):** 16 KiB payload; one worker; nominal 10 ms service time (~100 msg/s); target 300 messages/s; 60 s measurement interval; 10 s warmup if appropriate; K=32; compression off; one connection and stream. Calibrate achieved sender rate first. At a persistent 200 msg/s queue surplus for 60 s, expected accumulation is 12,000 messages (~187.5 MiB payload), before metadata and allocator overhead. Abort well before machine exhaustion.

**Run order:** Perform one smoke/calibration run per variant; then at least five measured repetitions per variant, randomized/interleaved run order, fresh server process for each run, identical resource constraints and fixed workload seed. Also include a below-capacity control (e.g. offered 50 msg/s) for each variant: no sustained queue growth should occur when offered load is truly below processing capacity.

## 6. Metrics and definitions

**Server (sample at ~1 s for gauges, counters continuously):**
- `grpc_messages_received_total`: complete messages delivered to handler.
- `app_enqueue_total`, `app_dequeue_total`, `app_processed_total`: define exact increment sites.
- `app_queue_depth`: number of successfully enqueued, not-yet-dequeued messages; cross-check `enqueue - dequeue`.
- `app_queue_payload_bytes`: sum of payload lengths for queued messages; add on enqueue and subtract on dequeue.
- `app_handler_payload_bytes`, `app_worker_payload_bytes`: message bytes held outside queue, if feasible.
- `app_enqueue_wait_seconds`: time waiting for bounded capacity; for V1 this should be approximately zero, excluding instrumentation.
- `app_worker_service_seconds`: measured service interval distribution.
- `process_resident_memory_bytes`: OS RSS; record process CPU and optionally allocator live bytes.
- `grpc_active_streams`, `grpc_active_connections`: expected 1 each during active run.
- `app_stream_errors_total`: errors/termination reasons.

**Client:** scheduled offered messages/sec, successful `Send` calls/sec, `Send` latency p50/p95/p99, blocked fraction (define threshold, e.g. >20 ms), send errors, payload bytes, CPU/RSS, final stream result and deadline status. A completed `Send` means accepted by client library, **not** necessarily delivered or processed.

**Derived:** queue growth slope (messages/s and bytes/s) during a prespecified steady overload window; arrival-to-service ratio; measured client send-rate decline after bounded queue saturation; maximum queue bytes; peak RSS; post-drain RSS; final accounting discrepancy (`received - processed - queued - handler - worker`, adjusting for rejected/errors). Report medians and run-to-run ranges; avoid false precision from one trace.

## 7. Test procedure

1. **Version/source audit:** Pin Rust toolchain, Tokio, tonic, h2/hyper, prost, Go, grpc-go, protobuf compiler, OS/kernel, and config. Inspect source/documentation for inbound receive flow-control credit and `Streaming::message` behavior; record file/commit references. Note uncertain internals explicitly.
2. **Baseline calibration:** Validate payload sizes and processing interval; verify a low offered rate completes without queue growth. Confirm client can achieve 300 msg/s when not transport-blocked and that no application-generated backlog exists.
3. **Overload comparison:** For V0, V1, V2, run identical scheduled offered load. Capture server metrics and client results. Preserve raw samples and stdout/stderr.
4. **Memory accounting:** Compare V1 queue byte slope to RSS slope; examine V2 queue maximum and total tracked bytes. Do not require RSS to drop immediately after drain.
5. **Propagation evidence:** Compare `Send` completion rate and latency before/after V2 saturation, against V1 and V0. Identify transient buffering before client blocking.
6. **Protocol diagnostic:** In a selected V1 and V2 run, collect HTTP/2 DATA and WINDOW_UPDATE evidence. Prefer a controlled cleartext h2c environment for readable capture if supported; otherwise use supported HTTP/2 instrumentation or TLS key logging where safe. Record that packet capture may alter timing. Correlate observed window-credit changes with server receive behavior; verify against pinned implementation.
7. **Repeatability:** Re-run across five independent fresh processes per variant; analyze slope intervals and variability. Confirm a below-capacity negative control.
8. **Archive:** Commit configs, exact commands, tool versions, dataset, analysis scripts (later), figure definitions, and notes on failed or aborted runs. Never silently discard failures.

## 8. Acceptance criteria

### Instrumentation and validity (must pass)
- [ ] Exact dependency versions, OS and transport settings captured in a machine-readable manifest.
- [ ] One connection, one stream, one worker, no per-message spawned tasks; confirmed with counters/review.
- [ ] Queue depth agrees with enqueue-minus-dequeue accounting at consistent sample boundaries; no unexplained message loss.
- [ ] Payload ownership and retained-byte accounting validated with a small deterministic test.
- [ ] Offered load and achieved Send rate are reported separately; worker capacity is independently measured.
- [ ] At least five valid fresh-process runs per variant and below-capacity controls, with documented exclusion criteria.
- [ ] All runs honor RSS/queue-byte abort thresholds and preserve partial data on abort.

### Evidence for the central claim (required to claim H1 supported)
- [ ] V1 shows a sustained positive application queue-depth and queue-byte slope during a verified interval where enqueue rate exceeds dequeue rate; repeatability demonstrated.
- [ ] V2 never exceeds K queued entries (allow separately reported handler/worker ownership), and its queue-byte accumulation reaches a plateau rather than sustained growth.
- [ ] The sender exhibits measurable pressure in V0/V2 (achieved throughput reduction and/or Send latency increase), with its location and timing described; do not infer wire transmission solely from `Send` returns.
- [ ] A source audit plus transport trace/diagnostic provides evidence that HTTP/2 flow control is active and explains why V1 can continue consuming transport data while application work accumulates.
- [ ] The paper distinguishes logical retained queue memory from RSS and reports any discrepancies or alternative explanations.

### Publication gate
- [ ] A single figure overlays queue bytes, RSS, worker throughput and achieved sender throughput across V0/V1/V2 using clearly marked scales.
- [ ] A second figure or trace illustrates transport credit/backpressure with implementation-specific caveats.
- [ ] Results include configurations, confidence/variability, failure modes, and raw data location.
- [ ] Claims are limited to this stack/version/workload; no blanket statement that gRPC transport flow control is broken or that bounded channels bound all memory.
- [ ] An independent reader can follow the README and reproduce the experiment on one machine without Kubernetes or external services.

## 9. Stop rules and interpretation

Set a predeclared safety threshold (initial proposal: stop V1 at 256 MiB **queued payload bytes** or a configured process RSS limit, whichever comes first). Stop sending, close/cancel the stream according to the run protocol, preserve samples, and record whether draining completed. The precise RSS limit must be selected for the test host before the first measurement.

**If V1 queue grows but RSS is flat:** Claim application-owned live queued bytes grew, not that RSS grew; investigate allocator and measurement period.

**If V2 queue is bounded but RSS grows:** Do not call V2 memory-safe; identify other retained buffers/tasks before publication.

**If client Send does not visibly block in 60 s:** Extend the observation safely or use lower transport windows in a separately labeled diagnostic run; do not change settings only for V2 in the primary comparison.

**If protocol capture is inconclusive:** Publish the application-level result with a narrower claim and explicitly label the transport explanation as source-supported or hypothetical, not packet-proven.

## 10. Reproducibility artifacts (planned; not implemented)

```
experiments/001/
  EXPERIMENT-001.md
  config/                  # shared workload and transport settings
  runs/<run-id>/           # manifest, client.csv, server.csv, process.csv, logs
  traces/                  # optional diagnostic pcap or HTTP/2 traces
  analysis/                # later: plots and analysis scripts
  README.md                # exact build/run/cleanup commands
```

**Not in E1:** adaptive concurrency, retries, multiple streams/connections, bidirectional streaming, cancellations as a treatment, production benchmarking, CPU saturation, Grafana dashboards, or full OpenTelemetry tracing. These require their own hypotheses and controls.

## 11. Authoritative starting references

- gRPC, *Flow Control*: https://grpc.io/docs/guides/flow-control/
- RFC 9113, *HTTP/2*, especially flow control: https://www.rfc-editor.org/rfc/rfc9113
- Tokio, *mpsc channel documentation*: https://docs.rs/tokio/latest/tokio/sync/mpsc/index.html
- tonic, *Streaming API*: https://docs.rs/tonic/latest/tonic/struct.Streaming.html
- grpc-go repository: https://github.com/grpc/grpc-go

**Research TODO before implementation:** Verify the exact tonic/h2 receive-window-credit semantics in the chosen pinned versions, including whether receiving, decoding, polling, or dropping buffers triggers credit replenishment. Do not treat a generic description of flow control as evidence of a specific implementation path.
