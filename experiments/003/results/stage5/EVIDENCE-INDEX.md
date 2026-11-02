# E3 Stage5 evidence index

Primary source/preregistration commit `905e2db815705cbd3edf2071b0d7dacee6e6a62d`;20 attempts,5 matched blocks, all valid, no replacements. All raw evidence is preserved.

- [Report](../../STAGE5-REPORT.md)
- [Frozen human plan](../../STAGE5-PLAN.md)
- [Machine plan](RUN-PLAN.json) and [immutable workload](WORKLOAD.json)
- [Frozen source/config/binary/environment manifest](FROZEN-MANIFEST.json)
- [Matrix](MATRIX.json), [attempt registry](RUN-LEDGER.json), [exclusions](EXCLUSIONS.json), [execution log](execution.log)
- [Frozen analysis script](../../fixtures/analyze-stage5.py), [results](analysis/RESULTS.json), [per-run CSV](analysis/runs.csv)
- [Independent audit script](analysis/audit-stage5.py) and [output](analysis/OFFLINE-AUDIT.json)
- [Post-matrix tables/display script](analysis/publish-stage5.py) and [supplement](analysis/SUPPLEMENTARY.json)
- [Figures](analysis/figures/): paired differences, all-original goodput/outcomes, conditional latency, CPU/RSS, recovery; PNG/SVG
- [Legacy raw client label explanation](LEGACY-CLIENT-LABEL.md)
- [Preflight](preflight.log), normal builds [0](freeze-build-0.log) / [1](freeze-build-1.log)

## Raw run directories

|Block|WAIT|REJECT|RETRY|DROP|
|---|---|---|---|---|
|1|[wait](block-01-attempt-01/wait/)|[reject](block-01-attempt-01/reject/)|[retry](block-01-attempt-01/retry/)|[drop](block-01-attempt-01/drop/)|
|2|[wait](block-02-attempt-01/wait/)|[reject](block-02-attempt-01/reject/)|[retry](block-02-attempt-01/retry/)|[drop](block-02-attempt-01/drop/)|
|3|[wait](block-03-attempt-01/wait/)|[reject](block-03-attempt-01/reject/)|[retry](block-03-attempt-01/retry/)|[drop](block-03-attempt-01/drop/)|
|4|[wait](block-04-attempt-01/wait/)|[reject](block-04-attempt-01/reject/)|[retry](block-04-attempt-01/retry/)|[drop](block-04-attempt-01/drop/)|
|5|[wait](block-05-attempt-01/wait/)|[reject](block-05-attempt-01/reject/)|[retry](block-05-attempt-01/retry/)|[drop](block-05-attempt-01/drop/)|

Each directory contains exact process/config/source manifests (`verification.json`), independent validity (`primary-verification.json`), workload copy, Go report/events, Rust authoritative ledger/events/clock/phases/finished markers, process RSS/CPU CSVs and stdout/stderr. `outcome.json` preserves attempt outcome. No binary, credential, cache or payload-content archive is required. Large JSONL and ledger snapshots are intentional raw evidence below declared file guards.

[Package checks](PACKAGE-VERIFICATION.json) record source/historical preservation, artifact bounds and known credential-pattern scans. [SHA256SUMS.json](SHA256SUMS.json) binds raw and derived evidence to exact content; regenerate after offline analysis if derived figures are rebuilt.

The report links every proposed finding to measured evidence. Analysis can be repeated offline without new benchmark execution. Preserve original raw measurements and verification files; the audit replays in memory.
