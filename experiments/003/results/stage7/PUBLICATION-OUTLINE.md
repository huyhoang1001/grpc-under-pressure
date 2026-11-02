# Blog 3 publication outline — not an article draft

## Central thesis

**Backpressure limits where work can accumulate; an overload policy decides what happens to demand that cannot be served in time. Waiting, rejecting, retrying and dropping move costs rather than creating capacity.** The experiment supports choosing those costs deliberately, not a universal policy winner.

Working title: **Backpressure Is Not an Overload Policy: Wait, Reject, Retry, or Drop?**

## Intended reader and evidence hierarchy

Experienced backend engineers deciding what their service should promise when capacity is gone. Lead with outcomes and the decision, not the ledger implementation. Primary evidence is Stage5’s single-client2s comparison. Stage6 deadline and eight-client studies are separate secondary evidence with their own context. Never merge their runs or draw a500ms→2s→5s curve across different runtime families.

## Outline

1. **The decision a full queue cannot make.** Define the central question and the four per-message outcomes. Distinguish flow control/local Send acceptance from useful work completed by an original deadline. Keep the gRPC internals recap to a short link to the earlier article; E3 does not isolate HTTP/2 blocking.
2. **The small controlled model.** A compact methods box:80 scheduled originals/s for36s,2,880 originals including never-sent work,16KiB payload, one serial timer worker10→40→10ms in12s phases,32 total admitted slots including the running worker/cancellation-pending work,2s application-level deadline per scheduled original (not a2s gRPC stream deadline), five matched blocks. Mention bounded client credits/pending and Rust debug/default Go instrumentation; full settings belong in the evidence appendix. Actual timer service exceeds nominal10/40ms. This is not a production CPU-saturation benchmark.
3. **Where each policy puts the bill.** Use a decision table, not a fastest-to-slowest leaderboard. WAIT relocates pressure to client queues/credits and can still expire or overflow originals. REJECT gives explicit refusal, but does not by itself decide the caller’s response. RETRY is server rejection plus a bounded client retry contract. DROP explicitly discards expendable work and is not successful processing or a no-ACK transport optimization in this protocol. Use the primary all-original outcome chart.
4. **The primary retry tradeoff.** Report+1.410pp RETRY−REJECT on-time completion, descriptive interval+0.889 to+2.042, n5. Pair that with attempt counts and conditional recovery p95. Explain why conversion IDs are not the net counterfactual gain and why a completed-only tail cannot stand in for all demand. WAIT/REJECT/DROP goodput ordering remains inconclusive, not equivalent.
5. **The deadline changes the decision — secondary A.** Show actual500ms and5s executions in separate panels. Longer deadlines improved U/N here, yet did not make RETRY uniformly best. Keep the valid WAIT block1 point at51.5625% visible; list its363 late completions and say its cause is unresolved. Show the all-five mean and median rather than silently substituting the other four runs. No reclassification of the primary2s population.
6. **A negative result worth keeping — secondary B2.** Eight clients divide the same80/s originals; they do not multiply demand. Under staggered arrivals and common fixed relative backoff, deterministic retry concentration was lower than full jitter in all five pairs. Define the20ms collision metric briefly and link exact denominators/bins. Disclose that no synchronized burst was injected and that fixed-cap versus uniform jitter changes mean backoff too. Do not turn this into “jitter is bad.” Footnote the pre-traffic B2 seed correction with its audit trail.
7. **Choose semantics and budgets before slogans.** An engineering checklist: Is late work still valuable? Is explicit loss acceptable? Who may retry, under what original deadline and attempt budget? Where can waiting accumulate? Which outcomes must the caller observe? What does the service do when those bounds fill? Present this as design guidance informed by the model, not experimentally proven universal deployment advice. Close the outline with unresolved questions and the reproducibility link, not a winner.

## Decision table to explain, not rank

|Policy|Decision at full admission|Who pays / what to inspect|Required distinction|
|---|---|---|---|
|WAIT|Hold admission cancellably|Client pending/credits, transport, elapsed original deadline, expiry/overflow|Bounded waiting is not lossless delivery|
|REJECT|Explicit refusal|Caller receives a refusal; final-refusal count, client backlog and retained server payload-time|Nonblocking admission is not zero response latency|
|RETRY|Reject, then possibly repeat under bounded original deadline|Additional attempts, selected rescued originals, shifted waiting and conditional tails|Never retry ambiguous delivery; benefit is conditional|
|DROP|Explicitly discard expendable full-budget work|Counted loss and workload value|Dropped work is not useful processing; semantics matter even if throughput resembles REJECT|

## Chart shortlist and required captions

**Main chart1 — primary all-original outcomes.** Use [Stage5 outcomes](../stage5/analysis/figures/outcomes.png), with a readable legend. Every bar represents mean fractions of all2,880 scheduled originals/run, five blocks, including backlog-exhausted/never-sent originals. Mark rejection/drop/expiry as non-success; show late completion separately. Do not imply every missing original was received by the server.

**Main chart2 — primary benefit and cost together.** Prefer [Stage7 primary review chart](figures/primary-tradeoff.png) and its [data/caption registry](CHARTS.json), plus the [original paired effect chart](../stage5/analysis/figures/paired-differences.png). Explain the small absolute gain, extra attempts, and higher per-run p95 among completed recovery-scheduled originals. Recovery p95 cohorts differ (RETRY n934–956, REJECT n900–932). The plotted per-run p95 values are not a pooled p95 or a fixed-cohort causal delay. Provide the count table if space is tight.

**Main chart3 — secondary A deadline panels.** Use [deadline goodput](../stage6/analysis/figures/deadline-goodput.png). Caption: separate500ms and5s secondary executions, five matched blocks, all-original denominator, same secondary application binaries. Preserve the block1 WAIT outlier and label it valid/unexplained. Do not add the primary2s points to the same trend line.

**Main chart4 — secondary B2 concentration.** Use a paired plot/table of collision values from [Stage7 audit](audit/REVIEW-AUDIT.json), or the left panel of [retry pairs](../stage6/analysis/figures/retry-pairs.png). Caption must specify actual initiated retries in[12,24),600 bins of20ms, probability that two distinct retries share a bin, five matched pairs, and no forced synchronization. The original right panel’s narrow U/N axis must be labeled as a zoom if retained; its roughly0.208pp difference is not a universal winner. Explain that mean backoff changes and include retry counts.

**Appendix — recovery and sensitivities.** Only use the [boundary-correct Stage5 recovery display](../stage5/analysis/figures/recovery-observed-intervals.png), whose rate bins end at[38,39); occupancy at39s is a separate endpoint. The frozen original `recovery.png` includes a zero39s closure sentinel that is not an observed[39,40) rate: retain it as evidence, do not promote it. Link B2 bin-width/offset sensitivities and per-run raw metrics. Cohort clearance is not whole-system recovery.

Do not use Stage5’s whole-workload `conditional-latency.png` as evidence for recovery-only latency; it answers a different cohort question. Do not compare the area of truncated bars or interpret a zoomed axis as a large practical effect.

## Mandatory disclosure block / appendix

- Primary vs secondary source/runtime/client/deadline families; no pooled estimate. StudyB uses8 connections and aggregate client limits264 outstanding/256 pending, with one server budget32/worker1.
- All-original U/N and the distinction between N scheduled, F first-attempt originals, A attempts, S Send successes and R decoded attempts. The experiment’s U/36s is useful completions per offered-workload second, including eligible drain completions, not an instantaneous processing rate or U/observation-cutoff.
- Five paired blocks, shared host, descriptive bootstrap intervals only; original messages and millions of retry pairs are not independent experimental replications. No significance, equivalence, universal winner or production recommendation is established.
- The original deadline is application metadata, beginning at the scheduled slot; it is separate from the long-lived RPC context deadline. Admission32 includes running work and counts cancellation-pending work once.
- Completion/queue/admission/ACK cohorts and n; immutable deadlines, late completions, unsent/expiry/backlog outcomes and exact accounting. ACK observation is not necessarily final retry-resolution time.
-39s observation versus42s for5s deadlines; use labeled/common windows for CPU/integral comparisons. One-second-plus grace is not a hard real-time guarantee.
- Simulated timer service, Rust debug/default Go builds, polling/logging/shared-lock and native multi-stream overhead, plus late-A supervisory activity; overhead was not proved negligible. Payload generation/hashing/serialization are included in the implemented model.
- RSS sampled peaks are lower bounds, CPU is quantized, payload ownership/ledger estimates/transport allocations are distinct. Local Send/writer elapsed does not isolate HTTP/2 blocking. Successful writes do not prove client application consumption.
- B2 chronology and exact hashed seed derivation/finite-range nonoverlap. Preserve the superseded original plan and zero-traffic boundary record. No B result selected the new seed method.
- Retained anomalous WAIT run, its effect on mean/median, unresolved cause; no post-outcome exclusion or tuning. No crash durability or exactly-once-across-restart claim.
- Link the full evidence index and per-run data; keep build hashes, seed algebra, internal ledgers and checker implementation details out of the main narrative unless needed for a claim.

## Claim-bound drafting rule

Use SUPPORTED claims and QUALIFIED claims with their stated restrictions from [CLAIMS.md](CLAIMS.md). Preserve INCONCLUSIVE findings as unresolved. Do not promote UNSUPPORTED extrapolations. This outline authorizes no new experiment, policy tuning, article draft or amendment to frozen evidence.
