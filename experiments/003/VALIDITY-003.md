# VALIDITY-003 — E3 Accounting, Correctness, and Run Acceptance

Status: Stage 0 v1.0. Normative alongside EXPERIMENT-003.md and PROTOCOL-003.md. No results exist at freeze.

## 1. Authoritative populations and reconciliation
N = 2880 immutable original scheduled IDs. A = total application attempts initiated (not successful Send returns). S = grpc-go Send returns success. R = server decoded attempts. F = originals with first attempt initiated. A = F + retries, F<=N, retries<=2N, A<=8640. S<=A and R<=A; S and R have no required ordering because transport failure may occur after server decode and before Send returns. Each attempt has unique attempt_id and exactly one original ID. A retry preserves original payload, deadline and client. Each original has at most one active attempt.

Reconciled terminal partition at t=39 s: N = COMPLETED_ON_TIME + COMPLETED_LATE + REJECTED_FINAL + DROPPED + EXPIRED_BEFORE_SEND + EXPIRED_WAITING_OR_QUEUED + EXPIRED_PROCESSING + CLIENT_BACKLOG_EXHAUSTED + PROCESSING_FAILED + CANCELLED + UNKNOWN. Exactly one classification per original; also retain separate client-observed state and server execution state. Server-completed originals take precedence over client-observed timeout when reconstructing authoritative completion, with completion time determining on-time vs late. Do not infer nonexecution from a missing ACK. Explicit server refusal or drop can be final only if no later valid retry/admission supersedes it. If server completed but client did not see ACK, preserve `ack_missing=true` as an orthogonal attribute.

U = COMPLETED_ON_TIME; primary U/N. Deadline attainment curves use all N originals, not completed-only population. A/N and retries/N include unsent originals. Conditional latency distributions disclose cohort, count, and policy. Report admitted fraction per original, per attempt and completion fraction separately. No dropped or rejected original counts as useful processing.

## 2. Safety invariants (hard run validity)
- `0 <= client_pending <= 32`; `0 <= client_outstanding <= 32`; retry scheduling consumes shared pending capacity.
- `0 <= server_queued + server_running + cancellation_pending <= 32`, with each occupied slot counted exactly once (cancellation-pending running remains running, not double counted).
- `server_running <= 1`; `server_decoded_staging <= 1`; `server_immediate_response_queue <= 32`; `server_reserved_terminal_responses <= 32`; `client_response_queue <= 64`; `event_writer_queue <= 1024`.
- For every acquired permit exactly one release, after removal/worker exit, never merely on cancellation request; no negative occupancy.
- Every admitted original has reserved terminal-response capacity or a recorded failed-stream path; a terminal frame is never fabricated after stream failure.
- `worker_starts(run_id,message_id) <= 1`; completed logical IDs counted once. Duplicate attempt ID across distinct messages is invalid. No identity eviction during run.
- `logical_ledger_entries <= 2880`, `attempt_ledger_entries <= 8640`; any metadata-capacity exhaustion during valid primary workload is a run failure.
- No work starts after original deadline; late completion possible only via race with cooperative cancellation of already-running work. Deadline event never resets for retry.
- Every started worker has exit record or explicit cutoff/unresolved record; summed worker occupancy is reconstructed from start/exit timestamps. `sum(worker_elapsed_by_disposition) = sum(all_worker_elapsed)` to clock precision; never equate timer delay to CPU time.
- No event silently dropped; all event sequence numbers contiguous per process; all original IDs accounted for at cutoff. A stream error does not magically create terminal per-message statuses.

## 3. Deterministic correctness and fault-injection acceptance
| Test | Injection | Required observation |
|---|---|---|
| T01 | All 2880 originals, client never sends | 2880 distinct terminal client-side dispositions, zero server decode, U=0 |
| T02 | Fill client pending and block transport | pending<=32, explicit overflow/expiry, no scheduler stall or missing originals |
| T03 | Fill server admission, WAIT | staging<=1, no extra decoded work, cancellable wait, permit cap maintained |
| T04 | Fill admission, REJECT/RETRY/DROP | correct per-attempt refusal/drop, no worker start for refused/dropped work |
| T05 | Client Send succeeds, abort before confirmed decode | never infer admission from Send success; unresolved reconciled honestly |
| T06 | Deterministic server-writer barrier simulating blocked local server-side outbound progress | bounded ACK buffering; timeout at 1 s of blocked local outbound progress; stream cancellation and cleanup with no leaked permits or deadlock. Successful server writes do not prove client application consumption; stopped client reads alone need not trigger this timeout. No additional client consumption acknowledgments are introduced. |
| T07 | Block server response writer and fill immediate response queue | receiver pauses, no circular wait or unbounded notifications |
| T08 | Block client send while response arrives | independent receive loop drains and releases attempt credit |
| T09 | Client half-close | admitted messages complete/cancel, server responses still drain, clean EOF |
| T10 | Expire pending/queued/running message | correct expiry class, request/observation/exit timestamps, permit held until exit |
| T11 | Completion exactly at deadline | on-time if timestamp<=deadline; deterministic event ordering |
| T12 | Cancel after worker completes, before ACK | completion retained, ACK missing recorded separately |
| T13 | Two concurrent attempts for same logical ID | <=1 worker start; duplicate joins/replays without double execution |
| T14 | Refuse first attempt, retry second | 1 original, 2 attempts, <=1 execution, same immutable deadline |
| T15 | Retry after deadline / >3 attempts | no retry permitted; explicit final disposition |
| T16 | Same ID, different payload/deadline | protocol error, no duplicate execution |
| T17 | Exhaust logical/attempt ledger or event writer | explicit safety error/invalid run, no silent eviction or event loss |
| T18 | Stream abort during processing | cancellation requested/observed/exited recorded, no false completion |
| T19 | Drop terminal frame after server completion | authoritative completion preserved; client observation missing |
| T20 | Delay worker cancellation checkpoint | permit held until actual worker exit; occupied time includes delay |

Use deterministic barriers/fake clocks where possible. Stage 1 acceptance requires all protocol tests applicable to the implemented stage; Stage 2 requires full T01–T20 suite, including repeated runs under race detection/stress where available. Tests are not benchmark results.

## 4. Primary-run validation
Before run: record git SHA, dirty state, Cargo.lock/go.sum/protoc and toolchain versions, binary hashes, workload file SHA256, policy, seed, randomized block order, client count, server limits, OS/kernel, CPU/memory limits, transport settings, compression, gRPC retry configuration, time-calibration method and uncertainty, observation cutoff and expected 2880 IDs. Record startup health and ensure no overlapping run contaminates resources.

During run: preserve per-original scheduled arrivals and actual scheduler wakeups, attempt start/Send return, server decode, admission, queue entry/exit, worker start/exit, response generation/write, client observation, retry scheduling, deadline and cancellation transitions, queue/ledger occupancy, RSS and CPU time series. Collect phase transitions at 12/24/36 s. Verify service delay selected by worker-start phase. Preserve client/server JSONL event logs and monotonic sequence numbers.

After run: flush ledgers; reconcile all 2880 originals and every initiated attempt; verify all safety invariants, payload hashes, exact parameters and time calibration (<5 ms error); verify no unlogged stream failure; report UNKNOWN count explicitly. UNKNOWN >0 does not automatically invalidate a run if caused by a documented transport ambiguity and both ledgers are intact; missing ledger data or inability to attribute UNKNOWN invalidates it. At t=39 s all workers should have exited; any live worker or permit is a validity failure. Verify no unexplained gaps in metrics covering workload and grace window.

## 5. Exclusions and stopping
Exclude only predefined violations: wrong workload/seed/phase, build/config drift, missing originals, duplicate execution, capacity/credit overflow, event loss, unbounded metadata, broken time calibration, unaccounted worker/permit, premature process termination, or unresolved instrumentation fault. Preserve raw files and exclusion reason in `EXCLUSIONS.json`; restart full matched block if a run in that block is invalid, never selectively keep favorable policy runs. Preserve failed startup and restart provenance. Negative performance, high rejection/drop, retry harm, and client expiry are valid results. Stop immediately on safety violations, OOM risk, or corrupted ledgers; do not silently rerun without documenting.

## 6. Statistical and claim validity
At least five valid matched blocks, policy order randomized within each. Same original schedule and seed across policies in a block; independent seeds between blocks. Report per-block U/N, pairwise paired differences, descriptive bootstrap intervals with small-n caveats, raw runs, and sensitivity analyses. No pooled p95 without also showing per-policy and phase-specific p95/p99 and differing cohorts. Distinguish server-authoritative completion from client-observed result; show skipped/unsent original counts. Recovery is censored if no clearance by cutoff; no unqualified full recovery claim from 15 s post-restoration window. Report unknown/ACK-missing rates and time calibration limitations.

## 7. Artifacts and acceptance stages
Per run: `manifest.json`, `client-events.jsonl`, `server-events.jsonl`, `client-metrics.csv`, `server-metrics.csv`, `reconciliation.json`, `verification.json`; per block `block-manifest.json`; experiment `EXCLUSIONS.json`, scripts and charts with reproducible source. Stage 1: protocol tests and deterministic reconciliation fixtures pass. Stage 2: all T01–T20 pass. Stage 3: counters reconcile to event logs and timing calibrated. Stage 4: pilot demonstrates observability and safe stop without changing primary parameters. Stage 5: all matched blocks valid and independently reanalyzable. Stage 6: secondary comparisons preserve aggregate original demand. Stage 7: independent evidence-to-claims review before Blog 3.
