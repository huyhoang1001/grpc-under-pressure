# Experiment 003 — Stage 4 controlled pilots

**PASS. GO for Stage5 primary runs after independent review and final source/binary/configuration freeze.** All five planned natural-traffic pilots passed, as did the predeclared matched instrumentation control. Full-budget REJECT, RETRY and DROP activated without worker barriers or fabricated outcomes. This establishes runner/measurement readiness, not a policy winner or a research-hypothesis conclusion. No randomized five-block primary comparison was run.

## Predeclared configurations and execution

[STAGE4-PLAN.md](STAGE4-PLAN.md) was written before execution. Runs were serial, with fresh real Go/Rust processes:

- Low-rate WAIT:10 originals/s for4s,N40, observation through7s. This separate pilot profile is explicitly not the frozen overload workload.
- WAIT, REJECT, RETRY, DROP overload pilots: unchanged80 originals/s for36s,N2880; worker delay10/40/10ms selected at worker start with12/24s boundaries; observation through39s.
- One additional WAIT overload pilot changes only client event-output buffering0→65536 bytes. It is a matched instrumentation control, not a replicated policy comparison.

A01 remains outstanding33/pending32/server admission32, one worker, staging<=1, terminal/immediate32 each, response notifications64, event rings1024. All runs preserve16KiB payloads, seed1/jitter seed1, scheduled+2s deadlines, max3 attempts, static65535 HTTP/2 windows, no compression/configured retry/replay buffering. Rust debug profile is retained from Stage3. The five overload/control cases have the **same immutable workload hash and identical final application source/binaries**.

Pilot safety limits were declared before runs: CPU30s/process, externally monitored RSS256MiB/process,64MiB/output file, core0, wall cutoff+12s. These explicitly scale Stage3's short-fixture guards to39s; no guard changed after an abort. Host cgroup limits were4 CPU cores/32GiB. No live pilot failed or triggered a safety guard. Sampled peaks remained well below the RSS guard; this is not a bound on unsampled process memory.

## Runner changes and documented blocker

| Files | Change |
|---|---|
| `server/src/main.rs` | Production server/default hooks only; bounded phase observer; atomic readiness/finished/cutoff markers; task/log-flush acknowledgement; graceful shutdown after EOF. No worker gate, admission or service-schedule implementation changed. |
| `client/cmd/pilot/main.go` | Real scheduler/client CLI validates exact low/overload manifests, configures recorded transport counters, supports only the declared output-buffer control, retains process/ledger through cutoff, then reconciles from server truth. Atomic RPC-end marker. |
| `client/scheduler.go`, `client/measurement.go` | Optional declared RPC cutoff and explicit client half-close event; existing short-fixture entry point retains its previous deadline calculation. The new pilot API aligns RPC observation with the contract's39s; original per-message deadlines are unchanged. |
| `client/ledger.go` | **Measurement-correctness fix:** bulk pending expiry previously logged each removal while `pendingN` still held its pre-removal value. Pending removal now precedes that event, under the same lock; final heap ordering, dispositions, deadlines and scheduling semantics are unchanged. |
| `client/pilot_test.go` | New regression reconstructs every bulk-expiry event's post-removal occupancy. No preexisting correctness test was modified. |
| `fixtures/pilot.py`, `verify-stage4.py`, `check-stage4.py` | Exclusive directories, single-active-run lock,200ms external process sampling, CPU/RSS/file/wall guards, process-group supervision/reaping, independent replay plus phase/cutoff gates, and failure registry. |
| `results/stage4/analysis/` | Reproducible summaries, CPU/RSS/resource series, additional whole-run identity/attempt/ACK audit and synthetic runner-failure checks. |

The bulk-expiry defect was identified and documented before live pilots; it would make legitimate expiry traces fail independent occupancy replay. The new test passes. No normative specification, hypothesis, policy or budget changed. An initial low-rate run passed before marker/locking hardening; it is preserved, and `final-low-wait` reruns low-rate validation on the exact source used by all final cases.

## Pilot verdicts and genuine activation

The following are **pilot accounting/activation observations**, not policy-performance comparisons. `Unsent=N−F`; A counts initiated attempts, R independently decoded attempts. Full refusals/drops are per-attempt server decisions at observed occupancy32.

| Pilot | Verdict | N | A / R | Unsent | Full refusals | Actual retries | Full drops |
|---|---|---:|---:|---:|---:|---:|---:|
| Low WAIT |PASS|40|40 /40|0|0|0|0|
| Overload WAIT |PASS|2880|2349 /2349|531|0|0|0|
| Overload REJECT |PASS|2880|2527 /2527|353|289|0|0|
| Overload RETRY |PASS|2880|2645 /2645|374|369|139|0|
| Overload DROP |PASS|2880|2522 /2522|358|0|0|303|
| WAIT buffered control |PASS|2880|2349 /2349|531|0|0|0|

RETRY used2506 originals with first attempts,2645 total attempts and at most3 attempts/original. Its369 refusal attempts are distinct from230 final refused originals; retries never became new logical IDs. Every observed terminal matched server sequence/time/disposition. No duplicate execution, UNKNOWN, missing ACK, safety abort or instrumentation failure occurred.

All scheduled originals, including unsent ones, reconcile exactly. Nonzero final partitions were:

| Pilot | On-time complete | Late complete | Final refusal/drop | Queued/waiting expiry | Processing expiry | Client backlog exhausted |
|---|---:|---:|---:|---:|---:|---:|
| Low WAIT |40|0|0|0|0|0|
| WAIT |2199|1|0|0|149|531|
| REJECT |2201|7|289 refused|0|30|353|
| RETRY |2248|3|230 refused|20|5|374|
| DROP |2178|4|303 dropped|0|37|358|
| WAIT buffered |2196|5|0|0|148|531|

Late completion is the frozen cooperative-cancellation race, not an exclusion. RETRY's20 queued removals explain2276 acquired/released permits versus2256 worker starts/exits. Processing expiry retains its permit until actual exit. Final queue/worker/staging/receive/response ownership and payload bytes were0 in every case. Server occupied32 and client outstanding33/pending32 were reached naturally in overload; event-ring peaks were<=32/1024 and response-notification peaks<=5/64. Separate high-water maxima are not simultaneous occupancy sums.

Backlog overflow also occurred for refusal/drop policies. The runner does not equate the offered80/s schedule with achieved Send/decode rates. Actual arrival p99 lateness was<=1.89ms and maximum<=9.07ms; all initial-phase960 originals started/completed in each overload pilot. Most backlog-full arrivals occurred at33 outstanding credits. A small number of backlog-full snapshots showed available credit; these are retained as sender/scheduler/transport timing confounders without causal attribution. No source or rate was changed to eliminate these outcomes. Send durations are recorded, not interpreted as isolated HTTP/2 blocking.

## Service disturbance, cutoff and measurement gates

Every overload run observed genuine initial, slowdown, recovery and drain worker-start cohorts. Completed-only median worker occupied time was approximately11.68–11.76ms initially/recovery and41.58–41.66ms during slowdown; requested delays remain10/40/10ms. Cancellation-shortened executions are reported separately and must not be treated as40ms processing capacity. Phase markers were present at0/12/24/36/39s, with maximum observed marker lateness3.388ms; markers observe time and do not drive the worker's phase choice.

Low-rate RPC EOF occurred around3.918s, with both processes sampled/retained beyond7s. Overload RPC EOFs were36.347–36.725s; all workers exited before39s and both ledgers/processes were retained through the39s observation boundary. Server finished markers follow task joins/log flush. Shutdown then publishes authoritative snapshots, and the client reconciles without inventing a wire Summary/ACCEPTED frame.

Strict cross-process monotonic calibration spans were **1.262–2.304µs**, below5ms. Sampling started before epoch and continued beyond cutoff; observed maximum gap was211.18ms against a200ms target and the declared<500ms gap guard. Event sequences/tails, counters, payload/permit ownership, high-water bounds, worker durations, all-original terminal/ACK partitions and gRPC/socket-byte counters passed independent replay. Supplemental identity audit confirms exact attempt-ID/number correspondence and max3 attempts, not merely aggregate counters.

RSS is a sampled lower-bound peak, CPU is10ms-quantized `/proc` time, and final record-storage estimates are distinct from process/transport allocation. Across final overload/control runs, sampled RSS stayed approximately9.5–9.8MiB server and22.0–24.0MiB client. Socket bytes count observed plaintext TCP-stream traffic including HTTP/2, not packets/retransmissions/NIC bytes; gRPC payload wire bytes are separate. No isolated HTTP/2-window blocked-time or whole-process memory bound is claimed. Clock-domain inheritance/endpoint assumptions and unsupported counters remain as documented in Stage3.

## Instrumentation perturbation assessment

The predeclared control repeats WAIT with the exact same workload/source/binaries/guards, changing only event-output buffer0→65536. Baseline/control both reconciled2880 originals, initiated2349 attempts and had531 unsent originals. Partitions differed slightly: on-time2199→2196, late1→5, processing expiry149→148. Client/server log volumes stayed approximately5.51/5.87MB with complete tails.

Using the first sample at/after epoch through the first sample at/after cutoff, approximate CPU deltas (buffered−direct) were **−50ms client, +60ms server**. Endpoints are sampled and10ms-quantized. This is one nonconsecutive pair on a shared host; there is no confidence interval or causal attribution of the outcome/CPU differences. No default was changed based on it: all four policy pilots use direct output0.

The control does not isolate rich event construction/state-lock accounting, producer polling, transport statistics or external sampling. Actual timer occupancy exceeds requested delays. Initial demand was nevertheless sustained at80/s and all measurement queues remained far below capacity; no evidence-loss or instrumentation-failure gate failed. These findings support proceeding to a common, frozen instrumentation configuration, **not a claim of negligible overhead**. Primary results must disclose this implemented simulated-service/instrumentation cost; a different profile/buffer/measurement implementation requires renewed pilot validation.

## Reproduction, tests and provenance

```sh
source scripts/dev-env.sh
python3 experiments/003/fixtures/check-stage4.py --output /tmp/e3-stage4-checks-new
python3 experiments/003/fixtures/pilot.py --profile low --policy wait --output /tmp/e3-stage4-low-new
python3 experiments/003/fixtures/pilot.py --profile overload --policy wait --output /tmp/e3-stage4-wait-new
python3 experiments/003/fixtures/pilot.py --profile overload --policy reject --output /tmp/e3-stage4-reject-new
python3 experiments/003/fixtures/pilot.py --profile overload --policy retry --output /tmp/e3-stage4-retry-new
python3 experiments/003/fixtures/pilot.py --profile overload --policy drop --output /tmp/e3-stage4-drop-new
python3 experiments/003/fixtures/pilot.py --profile overload --policy wait --event-buffer-bytes 65536 --output /tmp/e3-stage4-control-new
python3 experiments/003/fixtures/verify-stage4.py --run /tmp/e3-stage4-wait-new
```

The orchestrator's exclusion registry is repository-local; a refused existing directory never overwrites evidence. See [measured-source checks](results/stage4/checks/final/verification.json) and [reproducible-build checks](results/stage4/checks/reproducible-build/verification.json) for all exact build/test commands and exits:32 Rust tests,27 Go top-level tests repeated3 times under `-race`, Cargo fmt/build/clippy warnings denied, Go module verification/vet/builds, and three serial11-test transport-suite repetitions per policy passed. Existing E1/E2 regressions passed38 Rust tests and the unchanged Go race suite (cached PASS recorded). [Runner checks](results/stage4/runner-checks/verification.json) prove exclusive output, overlap refusal and preserved simulated startup failure with no child leak; no policy outcome was injected. Five additional synthetic Stage4 verifier corruptions (early client exit, early sampler stop, enabled worker barrier, RPC beyond cutoff and missing cutoff phase) were rejected without modifying real data.

[SOURCE-PROVENANCE.json](results/stage4/SOURCE-PROVENANCE.json) records baseline `1c8464d1b558ac4105092d9fb17074ab2ed82ce4` plus exact dirty-source hashes, executable hashes, toolchains and common overload workload hash. It does not label an uncommitted tree as committed source. Final six cases share the same measured application inputs. After execution, the registry path formatter was corrected to also accept absolute output directories outside the repository (including the /tmp reproduction commands above). This changes only exclusion bookkeeping after processes exit; the measured driver is archived and its exact hash retained. [Preservation](results/stage4/preservation.json) verifies3,000 protected preexisting files unchanged, including normative contracts, all historical evidence and existing tests. [EXCLUSIONS.json](results/stage4/EXCLUSIONS.json) retains the preliminary low run and the pre-pilot compiler rejection; synthetic startup failures are separate from real pilots. [Artifact index](results/stage4/EVIDENCE-INDEX.md) links raw ledgers, metrics, reconciliation, verification and analysis scripts. Full-workload raw JSONL and authoritative snapshots over2MiB are expected necessary evidence, not executable/cache artifacts.

A final integrity check found that Cargo integration tests had overwritten the on-disk main executable with a dev/test-feature-unified build. The plain normal build reproduced the exact server hash recorded by every pilot; client hashes also matched. [BINARY-RECONSTRUCTION.json](results/stage4/BINARY-RECONSTRUCTION.json) records this proof. The current check script restores/hashes the normal target after tests (22 successful steps in the reproducible-build check), preventing accidental feature/profile drift before future runs. The measured check-script version is archived. No data or application behavior was changed for this bookkeeping/build restoration.

## Readiness decision and remaining risks

**GO for Stage5, using the validated final source/debug binaries, default direct logging0 and frozen A01 configuration, after this independent review.** Before the first primary run, freeze the committed source/binaries/configuration and prespecified randomized matched-block order/seeds/analysis; Stage4 does not substitute for the five-block design. Maintain clock, coverage, bounds, event-tail, all-original accounting and exclusion gates on every run.

Risks remain: unreplicated shared-host pilots and buffering control; non-isolated total instrumentation cost; sampled RSS/quantized CPU; inherited runtime defaults under recorded cgroup limits; synthetic timer service rather than CPU saturation; cancellation races and transport/backpressure effects; no cross-host clock guarantee. None caused a pilot validity failure. Do not infer superiority, tune policies, pool pilot data into primary results, or change profile/limits to manufacture favorable outcomes. **Stop after Stage4 for review.**
