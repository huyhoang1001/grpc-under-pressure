# E3 Stage5 preregistration — frozen before primary outcomes

Authority: the three normative E3/A01 specifications. Application baseline: committed Stage4 source `e1370b0e625eec48fb39b94c6a5b4487f1abd962`. No Rust/Go application source, lockfile, policy, workload, deadline, queue or instrumentation setting is changed. A separate Stage5 launcher supplies block seeds to the existing client flag. This plan, machine plan/workload and runner/verifier/analysis scripts will be committed before normal builds/freeze. The preregistration commit, compiler/lock/source hashes and final executable hashes are then sealed in `results/stage5/FROZEN-MANIFEST.json` before the first primary run. The freeze file is exclusive-create, never overwritten.

## Fixed configuration

One real client-streaming bidirectional RPC/client/server process pair and one serial worker; no worker barriers. N2880 at80 scheduled originals/s for36s,16KiB payloads/seed1, immutable scheduled+2s deadlines;10/40/10ms service selected at start with12/24s boundaries; cutoff39s. A01 outstanding33/pending32/admission32; staging1, terminal32/immediate32, response64, event1024. Direct event logging0 bytes for every policy; normal Rust debug build; no compression/configured gRPC retry/replay buffer; HTTP/2 windows65535. Preserve validated guards: CPU30s/process, sampled RSS256MiB/process, file64MiB, core0, cutoff+12s wall,200ms sampling/<500ms gaps. Existing runtime defaults/cgroup limits and relevant environment are recorded and checked for drift. No settings will change after outcomes.

The immutable `WORKLOAD.json` is shared byte-for-byte across all policies/blocks; the run ID is study-scoped, while every physical run gets fresh in-memory ledgers/processes and an exclusive directory. Original demand is unchanged by overflow, achieved Send rate or retries. No additional warmup runs or cache clearing; host/cache/order effects are limitations.

Cargo tests can replace the main target through dev-feature unification. Freeze uses only explicit normal `cargo build --locked` after any tests, repeats both normal builds to verify hashes, and copies executables to a read-only private `/tmp` directory. No test/build runs may replace those copies. Go VCS revision metadata may differ from Stage4 because the preregistration commit is new; application content must hash-identically to the accepted baseline. Both normal build and copied executable hashes are recorded.

## Matched design

Exactly five complete valid matched blocks; no extra valid repetitions based on outcome or interval width. Independent fresh processes, serial runs. Ordering uses Python3.12 `random.Random(20261030)` shuffles; block jitter seeds independently use `random.Random(3005).getrandbits(64)`. Same block seed is passed to every policy (only RETRY uses it). No reseeding/reordering after results.

| Block | Jitter seed | Frozen execution order |
|---|---:|---|
|1|1134903123497516951|WAIT,DROP,RETRY,REJECT|
|2|7335427334695112769|RETRY,REJECT,WAIT,DROP|
|3|9136803124150509004|DROP,REJECT,WAIT,RETRY|
|4|1435626977494426790|DROP,WAIT,REJECT,RETRY|
|5|16813872846671630229|DROP,RETRY,WAIT,REJECT|

`RUN-PLAN.json` is the machine-readable authority for this order, configuration and analysis. Frozen inputs and copied binary hashes are checked before every run. Validity reuses Stage3 event replay and all Stage4 phase/cutoff/supervision gates, adds primary-label/seed and complete attempt-ID/number correspondence. Pilot artifacts are not primary evidence.

## Invalidity, replacement and stopping

Preserve every attempted run and block, including prior valid runs in an invalid block; do not overwrite. Valid low goodput, unfavorable tails, rejection/drop/expiry/backlog, late completion or absence of activation are not exclusions. UNKNOWN alone is not an exclusion if both ledgers and documented ambiguity reconcile; the existing healthy-drain runner can still invalidate an RPC failure that loses required coverage/EOF, rather than silently relabeling it.

On a transient startup/operational failure, clock calibration failure or sampling gap, stop that block immediately and exclude its entire partial block from paired analysis. One replacement of the **whole block**, same predeclared seed/order/configuration, is permitted (max2 full-block attempts). Do not complete the remaining policies in an already-invalid attempt. Stop for independent review on any safety abort; source/binary/config drift; violated ownership/identity/counter/partition/event-tail invariant; a repeated transient category anywhere; or any failure in the replacement attempt. No automatic source fixes/guard relaxation during the matrix. A partial matrix remains evidence but cannot earn Stage5 PASS.

## Frozen analysis

Primary endpoint U/N: authoritative unique completion timestamp<=original deadline, N2880 including unsent originals. Report U/36s separately. Report every run, all-original outcome partition, A/N, retries/N, F,S,R, admission fractions, ACK/UNKNOWN, limits and activation. Primary six comparisons are paired within each block: REJECT−WAIT, RETRY−WAIT, DROP−WAIT, RETRY−REJECT, DROP−REJECT, DROP−RETRY. Estimate arithmetic mean of the five paired differences; retain all differences, median and direction counts. Enumerate all5^5=3125 ordered paired-block bootstrap resamples and use linearly interpolated2.5/97.5 percentiles. These intervals are descriptive with n5; no p-values, significance/equivalence proof or universal winner.

Secondary descriptive metrics: scheduled→authoritative completion for completed and on-time-only cohorts, with n/p50/p95/p99 per run; initial/slowdown/recovery cohorts by original schedule, not pooled p95 headlines. Client terminal observation is a separate ACK-observed cohort, including refusals/drop. Admission wait applies to admitted messages; queue residence to started messages. Keep differing denominators explicit. All-original attainment at0.5/1/2/5s is a curve on this unchanged2s-deadline workload, not secondary deadline experiments.

Resource endpoints: server queued+running payload-byte-time integral[0,39] (primary retention operationalization), staging separately; worker occupied time by disposition and utilization over39s; idle-with-backlog time; sampled RSS/CPU and recorded storage estimates; observed gRPC/TCP-stream bytes per original; local writer elapsed and wrapped Send durations, never isolated HTTP/2 blocking. CPU window starts at first sample>=0 and ends at first sample>=39, with quantized/sampled endpoint limitations.

Recovery: anchor24s; first time no pre24s-admitted queued/running originals remain. Report0 if none at24; censor if unresolved at39, without substituting0 or silently dropping censored pairs. Plot per-second unique on-time completions and separate client pending/outstanding/server occupied counts[24,39]. No steady-state proof from this short window. Paired recovery intervals require all5 uncensored complete pairs.

Operational H1–H5 rules (do not rewrite the normative hypotheses):

- H1: descriptive support if all5 WAIT runs show measured slowdown capacity constraint(completed service median>=40ms), occupied32, upstream pending and backlog/expiry. Mixed otherwise; no pressure under confirmed deficit is contrary evidence.
- H2: support if mean paired REJECT−WAIT retention integral<0 and>=4/5 negative, with refusal in all REJECT. Also report peak occupancy/unique admitted fractions; equal peaks alone do not refute retention differences.
- H3: support only if paired RETRY−REJECT U/N mean>0, descriptive interval lower>0,>=4/5 positive, and retry-converted on-time originals in>=4 blocks. Zero conversions is contrary to a conversion benefit. Do not explain aggregate noise as successful retries.
- H4: explicit label differences alone are insufficient. Compare DROP−REJECT U/N and retention (conditional timing disclosed). No consistent>=4/5 direction and intervals crossing0 means no distinct tradeoff established, not equivalence proof.
- H5: descriptive recovery differentiation if any uncensored paired clearance interval excludes0 with>=4/5 consistent direction; censored/mixed evidence remains inconclusive.

Negative and inconclusive findings remain reportable. All claims stay within this single-host/debug/in-memory/timer-service/instrumented model. The matched design does not remove shared-host/cache/time drift or establish total instrumentation negligibility.

## Deliverables and boundary

`STAGE5-REPORT.md`, raw runs/block manifests, validity/exclusion ledger, source/binary freeze, reproducible analysis, figures, per-block policy verdicts, hypothesis assessments and evidence-to-claims table. Exact scripts are preregistered with this plan. Changes to analysis after outcomes, if unavoidable for a coding error, must be versioned/disclosed and cannot redefine endpoints or exclusions. Stop after Stage5 for review; no Stage6 or Blog3.
