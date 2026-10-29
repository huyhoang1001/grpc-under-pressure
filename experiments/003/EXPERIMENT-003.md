# EXPERIMENT-003 — Backpressure Is Not an Overload Policy

Status: Stage 0 contract v1.0 — implementation authorized subject to Stage 1 correctness gates; no measured findings.
Companion contracts: PROTOCOL-003.md and VALIDITY-003.md. These three files are normative together.

## 1. Question and scope
When a bounded gRPC service runs out of capacity, which costs move to clients, which remain on the server, and how do WAIT, REJECT, RETRY, and DROP affect unique on-time completion, latency, resources, amplification, and recovery?

Continuity: E1 exposed application buffering despite transport flow control; E2 compared admission budgets. E3 fixes the admission budget and compares outcomes. This is an in-memory, deterministic service-delay experiment, not a durable messaging or CPU-saturation benchmark. Do not tune an adaptive controller, add a database, or infer exactly-once processing across crashes.

## 2. Falsifiable hypotheses
- H1 (WAIT): waiting relocates pressure to bounded client/transport queues and produces deadline/backlog failures under sustained overload. Falsified if there is no measurable upstream waiting or expiry despite verified capacity deficit; unbounded memory is a correctness violation, not falsification.
- H2 (REJECT): immediate refusal reduces retained server work at the expense of terminal refusal. Falsified if, under equivalent offered originals, it does not reduce retention compared with WAIT; any useful-completion comparison uses all originals.
- H3 (RETRY): bounded retries may convert temporary refusals into unique on-time completions, with additional attempts and possibly recovery costs. Falsified if retries yield no additional on-time originals; a negative result is publishable.
- H4 (DROP): explicit drop-on-full trades unique completions for bounded admission and lower waiting. Falsified if drop-on-full produces no discernible difference from REJECT under the frozen workload; missing drop accounting is invalid.
- H5 (recovery): strategies differ in post-restoration outstanding work and deadline goodput. Falsified if differences are indistinguishable within uncertainty.
- H6 (multi-client secondary): deterministic synchronized retries create more concentrated attempt bursts than full jitter. Falsified if burst metrics do not differ materially.

## 3. Frozen primary workload
| Item | Value |
|---|---|
| RPC | versioned E3 bidirectional streaming, one stream, one Go client |
| Original schedule | 80/s, every 12.5 ms from t=0 inclusive to t<36 s; N=2880 |
| Payload | exactly 16,384 application payload bytes, compression disabled |
| Service | one worker, deterministic cancellable timer delay: [0,12) s 10 ms; [12,24) s 40 ms; [24,36) s 10 ms |
| Service phase selection | delay selected at worker START using elapsed run time, never retroactively changed |
| Server admission | 32 total occupied slots = queued + running + cancellation-pending |
| Deadline | original scheduled timestamp + 2,000 ms, immutable across attempts |
| Client original pending | 32 slots; local backlog-full becomes CLIENT_BACKLOG_EXHAUSTED immediately |
| Client outstanding | 32 attempt credits; one attempt per original at a time |
| Server decoded staging | at most 1 request outside admission/identity records |
| Server terminal response reservations | 32 admitted-work reservations plus 32 immediate-response slots |
| Client response processing | direct nonblocking ledger update; bounded response-event channel capacity 64, drained independently |
| RETRY | 3 total application attempts; after refusal delay min(100 ms * 2^(attempt_index-1), 400 ms) with deterministic full jitter [0,delay], seed in manifest; no retry after deadline; retry only on explicit overload refusal |
| Run | 36 s arrivals, then observation through t=39 s (last deadline 38 s + 1 s cancellation/ACK grace); no new originals after t=36 s |
| Transport | one connection, explicit pinned tonic/h2 and grpc-go transport settings in run manifest; no compression; application retries only; verify automatic retries disabled/effective behavior |
| Host | single machine, separate client/server processes, clock alignment/calibration recorded; CPU/memory resource limits and versions pinned in manifest before runs |

The 32-slot server budget includes active work, so at 40 ms nominal single-worker capacity is 25/s against 80/s offered. At 10 ms nominal capacity is 100/s. A 32-item backlog costs up to 1.28 s at 40 ms before upstream waiting, so 2 s is a meaningful but not universally optimal deadline. The workload is intentionally synthetic. Preserve 500 ms and 5 s deadline sensitivity runs as secondary, without choosing the headline based on their outcomes.

## 4. Policies and identical work
- WAIT: receiver does not decode additional work when admission is full; it waits cancellably for a permit. No application-level refusal on full. Client sends within outstanding credits and pending budget; locally unsendable originals expire or overflow explicitly. A single decoded staging item is counted separately and bounded.
- REJECT: nonblocking permit acquisition; on full emit terminal REJECTED_OVERLOAD, no client retry.
- RETRY: identical server behavior to REJECT; only client changes. Explicit refusal may schedule retry, same logical ID/payload/deadline, new attempt ID; no overlapping attempts for one logical original. No retries on unknown delivery, stream failure, or deadline.
- DROP: nonblocking permit acquisition; on full emit terminal DROPPED_OVERLOAD, never report successful processing; only expendable primary messages are eligible.

All policies share worker, queue discipline (FIFO), admission budget, deadline enforcement, deduplication, response path, original schedule, payload, client pending capacity, and transport configuration. Policy-dependent achieved sends, queueing, expiries and retained work are measured outcomes, not reasons to alter offered originals.

## 5. Primary and secondary measures
Primary: U/N, where U is distinct original IDs with authoritative server completion timestamp <= original deadline, and N=2880. Report deadline goodput U/36 s separately; no completed-only denominator for headline.

Required per-original mutually exclusive reconciled outcome: COMPLETED_ON_TIME, COMPLETED_LATE, REJECTED_FINAL, DROPPED, EXPIRED_BEFORE_SEND, EXPIRED_WAITING_OR_QUEUED, EXPIRED_PROCESSING, CLIENT_BACKLOG_EXHAUSTED, PROCESSING_FAILED, CANCELLED, UNKNOWN. Keep client-observed disposition separately from server-authoritative execution. Reconciliation rules in VALIDITY-003.

Also record scheduled vs actual first send; first attempts; retries; successful grpc-go Send returns; server decoded attempts; admission waits; server queue residence; per-attempt terminal disposition; unique starts and completions; worker occupied time by final disposition; queue counts/bytes; ledger bytes and entries; client/server RSS and CPU; stream failures; ACK writer blocking; transport bytes; cancellation requested/observed/terminated; client-observed terminal latency; authoritative completion latency; unresolved fraction. Report amplification A/N and retries/N, including unsent originals in denominator.

Recovery anchored at t=24 s. Predeclare: per-second unique on-time completion counts and outstanding originals for [24,39] s; backlog clearance time (first time no pre-24 admitted/queued originals remain, or censored at cutoff); no claim of recovered steady state solely from a short window. Plot useful completion rate and client retry/backlog time series. Report all-censored/zero-backlog cases explicitly.

Latency: original scheduled -> server completion for successfully completed originals (server and client clocks calibrated); original scheduled -> client terminal observation as a separate metric. Compare conditional p50/p95/p99 only with cohort labels and sample counts. Primary all-original deadline-attainment curves count noncompletions as not attained, not as zero-latency. Use server queue and client wait distributions separately.

## 6. Fair comparison and analysis
One immutable generated workload file (ID, client, schedule, payload seed/hash, deadline) shared by policies; preserve original demand regardless of client queue overflow. Precompute payload deterministically; avoid materializing all 2880 full payloads in the live client. The original manifest is a fixed experiment artifact, not a hidden runtime queue.

Primary: minimum 5 independent valid matched blocks; each block uses one original schedule and a predeclared jitter seed, and executes all four policies in randomized order. More repetitions only by a preregistered rule, never because a result looks weak. Record all runs, including failures and exclusions. Report paired per-block differences and descriptive bootstrap intervals with explicit small-n caveat. No claim of statistical significance from a tiny n. Secondary: 8 clients with same aggregate 80/s and same originals, deterministic vs full-jitter RETRY; additional deadline sensitivities; optional unary protocol cross-check only after primary.

Comparisons valid on all originals: U/N, outcome fractions, attempts/N, byte amplification/N, resource peaks, worker-time/original, client/server RSS, recovery and deadline-attainment. Conditional only: admitted-work service time, successful-completion latency, ACK latency, rejection among decoded attempts, queue residence among admitted; always display denominators and differing cohorts.

## 7. Validity and provenance
See VALIDITY-003.md. Require exact manifest identity, pinned commit and lockfiles, toolchain versions, transport and resource limits, run ordering/seeds, host information, time calibration, raw client/server event ledgers, metrics traces, reconciliation and verification reports, exclusion registry, and generated chart scripts. No fabricated results. Run invalid on violated safety invariants, missing events, unknown source populations, duplicate execution, unbounded queue, metadata overflow, or uncontrolled configuration drift. A negative policy outcome is valid evidence.

## 8. Stages and gates
- Stage 0 (this contract): freeze three mutually consistent documents, parameter manifest schema, and acceptance tests. Gate: no unresolved correctness ambiguity.
- Stage 1 (protocol): protobuf + bidi client/server skeleton, bounded loops, ledger, deterministic barriers, no load comparison. Gate: identity, terminal ACK, half-close, blocked response, cancellation and reconciliation tests pass.
- Stage 2 (policies): WAIT/REJECT/RETRY/DROP behind shared budget. Gate: resource, retry, deadline, dedup and queue tests pass; no duplicate worker start.
- Stage 3 (instrumentation): independent client/server event logs, counters, RSS, queue and worker-time metrics, clock calibration. Gate: synthetic event fixtures reconcile exactly and intentional faults are detected.
- Stage 4 (pilot): one policy at a time, low-rate then controlled overload, no policy tuning. Gate: manifest equality, no invalid accounting, no deadlocks, sampling and cutoff adequate; pilot results not primary evidence.
- Stage 5 (primary): randomized matched repetitions; preserve all raw outputs and exclusions. Gate: preregistered validity checks and independent re-analysis.
- Stage 6 (secondary): 8-client synchronization, deadline sensitivities and optional unary cross-check. Gate: original aggregate demand unchanged and conditional claims labeled.
- Stage 7 (publication review): evidence-to-claims audit, negative results and limitations; Blog 3 written only afterward.

## 9. Boundaries
No durable exactly-once semantics, crash recovery, database, adaptive tuning, retries on ambiguous delivery, production CPU saturation, automatic transport-level guarantee of message delivery, or universal policy ranking. E3 assesses a fixed, bounded simulated service and explicit application-level outcomes.
