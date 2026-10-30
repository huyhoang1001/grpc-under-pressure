# Experiment 003 Stage4 evidence

**PASS; GO for Stage5 after review and source/config freeze.** No randomized five-block primary comparison or policy ranking was performed.

- [Stage4 report](../../STAGE4-REPORT.md), [pre-execution plan](../../STAGE4-PLAN.md).
- [Pilot summary](PILOT-SUMMARY.json): per-case activation, all-original partitions, phase cohorts, timing, bounded-resource HWM, CPU/RSS/transport and coverage observations.
- [Instrumentation control](INSTRUMENTATION-CONTROL.json): one nonconsecutive WAIT pair, default direct output vs64KiB batching. Not a total instrumentation-cost estimate or negligible-overhead claim.

Final same-application-source runs:

| Run | Manifest/commands/source/binary hashes | Independent verification |
|---|---|---|
| Low-rate WAIT |[manifest](final-low-wait/verification.json)|[PASS](final-low-wait/pilot-verification.json)|
| Overload WAIT |[manifest](overload-wait/verification.json)|[PASS](overload-wait/pilot-verification.json)|
| Overload REJECT |[manifest](overload-reject/verification.json)|[PASS](overload-reject/pilot-verification.json)|
| Overload RETRY |[manifest](overload-retry/verification.json)|[PASS](overload-retry/pilot-verification.json)|
| Overload DROP |[manifest](overload-drop/verification.json)|[PASS](overload-drop/pilot-verification.json)|
| WAIT buffered control |[manifest](overhead-wait-buffered/verification.json)|[PASS](overhead-wait-buffered/pilot-verification.json)|

Every run directory contains immutable `workload.json`, pre-run `manifest.json`, actual logs, client/server raw JSONL,200ms process metrics CSVs, derived series CSVs, client reconciliation, authoritative server snapshot, clock/phase/finished/cutoff markers and `outcome.json`. Large raw JSONL files are necessary complete evidence, not executables or caches. CPU series are quantized; RSS peaks are sampled lower bounds. Record-storage estimates are not process memory bounds.

- [Whole-run identity/attempt/ACK audit](ADDITIONAL-GATES.json).
- [Final measured-source checks](checks/final/verification.json), [post-bookkeeping checks](checks/post-bookkeeping/verification.json), [normal-target-restoring checks](checks/reproducible-build/verification.json): all tests/builds/lints, exact commands/toolchains; adjacent logs preserve actual outputs.
- [Source provenance](SOURCE-PROVENANCE.json), [historical preservation](preservation.json), [artifact catalog](ARTIFACT-MANIFEST.json), [checksums](SHA256SUMS).
- [Exclusion registry](EXCLUSIONS.json): no live safety abort/failed pilot. `low-wait/` is a preserved pre-hardening PASS, superseded by final-low-wait for common-source acceptance. A pre-pilot compiler rejection is documented.
- [Runner negative checks](runner-checks/verification.json), [external-path check](runner-checks/absolute-path-check.json): explicitly synthetic startup failure and output/lock tests; not live policy outcomes.
- [Stage4 verifier fault tests](verifier-faults/verification.json): five deliberately corrupted metadata/coverage fixtures rejected.
- [Analysis scripts](analysis/): regenerate summaries, series and additional gates. `pilot-measured.py` is the exact measured orchestrator archive (hash provenance; not a standalone relocated entrypoint). Canonical `fixtures/pilot.py` differs only in post-process exclusion-path formatting for external output directories. `check-measured.py` preserves the measured check version; current checks additionally restore/hash the normal main target after Cargo test feature unification. [Binary reconstruction](BINARY-RECONSTRUCTION.json) proves exact pilot executable identity.

`*.initial-analysis.json` retains the initial derived CPU endpoint choice; final summaries use the first sample at/after epoch and first sample at/after cutoff, excluding later reconciliation CPU as far as sampling resolution permits. Raw measurements are unchanged. Existing Stage1/2/A01/Stage3 evidence and normative specifications remain unchanged.
