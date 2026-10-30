# Experiment 003 — A01: minimal bounded client credit headroom

**GO for Stage 3 instrumentation after independent review.** The structural overload-reachability blocker is resolved. No primary benchmark, policy-performance comparison or Stage 3 implementation was performed.

## Decision and authority

The user authorized selection and consistent amendment of the three specifications. A01 changes **client outstanding credits32 →33 for every policy**, while server admission remains32.33 is the smallest integer greater than32: it permits one credited attempt to reach a full server.32 cannot do so under the existing ownership rules.64 would also permit it, but adds31 more credits than necessary and changes upstream retention much more. The choice was declared before saturation tests and follows arithmetic, not observed policy performance.

[EXPERIMENT-003.md](EXPERIMENT-003.md), [PROTOCOL-003.md](PROTOCOL-003.md) and [VALIDITY-003.md](VALIDITY-003.md) now identify revision1.1/A01. Their original bytes from baseline `000308b79d07228d47cfd52458591893d9c02d7b` are retained under [spec-before/](results/amendment-a01/spec-before/). Research hypotheses, offered originals, service schedule, deadlines, policies and analysis definitions are unchanged. Stage 1/2 reports and raw evidence remain historical32-credit evidence; they were not edited.

## Consequences and unchanged bounds

| Area | A01 impact |
|---|---|
| Client pending | Still32 entries shared by new originals and retries. Maximum pending+outstanding originals becomes65, previously64. No extra pending/retry queue or per-message timer. |
| Admission/staging | Server remains32 admitted owners, one worker and<=1 decoded staging request. WAIT may retain the33rd attempt in staging and withhold its response; further initiation stops at33 credits. |
| Responses | Still32 admitted-terminal reservations,32 immediate-response reservations,64 client response events. Full immediate capacity pauses decoding; independent writer never needs admission. No enlarged ACK buffer or new ACK protocol. |
| Flow control | Static stream/connection windows65535 and compression/retry configuration unchanged. Additional application credit does not bypass HTTP/2 flow control, guarantee Send progress, or prove server/client consumption. Local writer timeout remains1s. |
| Retry/deadline | Same explicit-refusal-only retries, max3 attempts/original, immutable scheduled+2s deadline and seeded full jitter. One active attempt/original. Full shared pending capacity still yields final refusal/expiry. |
| Memory | At most one additional unacknowledged application's payload volume (16KiB) can be in flight. Fixed identity/attempt arrays remain2880/8640; their allocation does not grow with credits. Server admitted-plus-staged payload bound remains33×16384=540672 bytes. These ownership limits do not bound allocator/serialization/transport copies or whole-process RSS. |

The amendment removes a structural impossibility; it does **not** guarantee a large policy effect or a favorable RETRY result. Later pilots must report achieved overload and outcomes honestly. All policies must use A01 identically. Run/configuration manifests must record A01 and credit limit33; the immutable original-identity workload format does not change. Do not pool future A01 results with32-credit runs or attribute cross-revision differences solely to policy. No primary results existed to reclassify.

## Implementation and tests

Production changes are confined to `client/ledger.go`: credit constant33 and verification using the named capacity constants rather than a hard-coded32. Existing admission/worker/response implementations, scheduler, retry engine, protobuf and lockfiles are unchanged. `client/ledger_test.go` now saturates the amended capacity and retains pending overflow/deadline/UNKNOWN assertions. New `client/credit_test.go` proves33 outstanding is valid, the34th blocks, and releasing one credit admits exactly one replacement. It also locks pending32/response64 against accidental changes. README reflects A01.

The new `server/examples/credit-saturation.rs` is a **test-only executable**, using the actual Service, ledger, policy dispatcher and worker. It starts with an empty ledger and one real RPC. An existing worker-service barrier holds the first running worker while the other31 slots fill. The Go `client/cmd/credit-smoke` uses the actual open-loop scheduler, production33-credit enforcement, independent Receive and real retry engine. No raw sender, prefilled admissions, extra client, fabricated outcome or wire-protocol extension is used.

Each fixture sends the first33 originals of the unchanged80/s schedule with16KiB payloads, seed1 and immutable2s deadlines. This is a labeled short correctness fixture, not the36-second workload. The barrier is released after actual full-budget decisions (after three real refusals for RETRY), or requests cancellation for the WAIT cancellation case. It deliberately disturbs worker progress only in the test executable; no primary service-delay parameter was changed.

## Observed correctness evidence

All five final fresh-process fixtures passed. These counts are acceptance observations, **not policy-performance comparisons**:

| Fixture | Attempts / retries | Required outcomes | Acquired/released permits |
|---|---:|---|---:|
| WAIT drain |33 /0|33 completed; staged request later admitted; no refusal|33/33|
| REJECT |33 /0|32 completed,1 real REJECTED_OVERLOAD; refused work never started|32/32|
| RETRY |35 /2|32 completed; same remaining original received3 real refusals, max-attempt finalization; no execution for that original|32/32|
| DROP |33 /0|32 completed,1 real DROPPED_OVERLOAD; dropped work never started|32/32|
| WAIT cancel |33 /0|33 authoritative cancellations, including staged/queued/running ownership; request/observation/exit recorded|32/32|

In every case independent client-event replay reached **33 outstanding and never exceeded33**, pending peak1, and all33 scheduled originals reconciled. At the barrier, server occupancy was32 (31 queued+1 running); WAIT additionally had exactly1 staged payload. Server events never exceeded32 owners/one worker. Final admitted/staged/receive/terminal/immediate ownership and payload bytes were0. Worker starts<=1/original. All JSONL sequences were contiguous and matched final ledger tails. For normal drain, observed terminal sequence/time matched server authority. WAIT cancellation is an explicitly expected stream failure, not a hidden exclusion.

[summary.json](results/amendment-a01/summary.json) and each fixture's `verification.json`, `barrier.json`, raw client/server logs and reconciled snapshots preserve these checks. Resource guards were CPU5s/process, file size16MiB, no cores,3s barrier timeout and bounded orchestration/startup/shutdown waits. All processes/tasks were joined; no unsafe/unresolved shutdown occurred.

## Reproduction and regressions

```sh
source scripts/dev-env.sh
python3 experiments/003/fixtures/check-amendment-a01.py --output /tmp/e3-a01-checks-new
# The check script builds both fixture executables and records every exact command.
python3 experiments/003/fixtures/credit-saturation.py --policy wait --output /tmp/e3-a01-wait-new
python3 experiments/003/fixtures/credit-saturation.py --policy reject --output /tmp/e3-a01-reject-new
python3 experiments/003/fixtures/credit-saturation.py --policy retry --output /tmp/e3-a01-retry-new
python3 experiments/003/fixtures/credit-saturation.py --policy drop --output /tmp/e3-a01-drop-new
python3 experiments/003/fixtures/credit-saturation.py --policy wait --mode cancel --output /tmp/e3-a01-cancel-new
```

[Final check manifest](results/amendment-a01/checks/final-2/verification.json) records21 successful steps: Cargo fmt/build/test/clippy warnings denied, example build, Go module verification/build/vet, **30 Rust tests** and **21 top-level Go tests repeated3 times under `-race`**, plus three serial11-test TCP-suite repetitions under each policy. All affected Stage 1/2 tests pass with amended capacity expectations; T02/T03/T04/T14/T15 now additionally have conforming A01 evidence. Existing E1/E2 regressions passed38 Rust tests and the unchanged Go race suite (cached PASS disclosed in its log). No benchmark was executed. Rust/cargo1.99.1 and Go1.27.3 versions and host details are recorded.

[Source provenance](results/amendment-a01/source-provenance.json) records base commit plus exact dirty-source hashes, executable hashes and spec hashes. All final fixtures used identical binaries and source matching the final regression inputs; this is not mislabeled as committed final source. [Preservation audit](results/amendment-a01/preservation.json) verifies1,846 protected preexisting files unchanged, including all E1/E2, Stage1/2 evidence and production Rust source. [EXCLUSIONS.json](results/amendment-a01/EXCLUSIONS.json) retains preliminary passes; no fixture failed and no primary run was attempted. Later report/index additions are documentary only.

## Review gate

**GO for Stage 3 instrumentation.** The amended model remains bounded and fair, and actual full-budget decisions are reachable without breaking client credits. No further primary-parameter change is needed for reachability. Clock calibration, measurement overhead, independent metric reconciliation, safe pilots and primary comparison remain future gates; this test does not establish primary-run validity or a policy ranking. Stop here for independent review.
