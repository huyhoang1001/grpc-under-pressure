# EXPERIMENT-002 Stage 5 evidence

Start with [STAGE5-REPORT.md](../../STAGE5-REPORT.md), the [pre-run analysis plan](../../stage5/PLAN.md), and the explicit [startup harness amendment](../../stage5/AMENDMENT-1.md).

Two cohorts are retained:

- This directory's `FROZEN.json`, `b01-*`, `ledger.jsonl`, and `matrix-state.json` preserve the original stopped primary attempt: two valid measurements, then the fixed8 marker-reader startup panic/deadline. They are never overwritten or silently pooled into the corrected matrix.
- `primary-v2/` contains the newly frozen whole-matrix restart, identical application/binary/configuration/order/analysis definitions, with atomic marker publication as the sole runtime harness correction. The application is unchanged. This is the final intended complete-block primary cohort.

`freeze-reconciliation.json` proves identical application/configuration/order/analysis across the documented harness correction. `startup-failure-diagnosis.json` describes the original failure; original manifest and logs preserve its original generic validation exception as well.

Each run directory contains exact manifest/source/binary/configuration/commands/clock/exit/validity data, server events/samples/histograms/controller ticks/phase markers, client Send events/samples/Summary, and CPU/RSS process samples. The canonical per-cohort ledger preserves every attempt. A combined fully qualified all-attempt ledger and final report distinguish invalid attempts from valid measurements in the abandoned incomplete cohort.

Offline analysis scripts are byte-pinned before the first primary run. Quantiles use exact events and nearest rank; uncertainty resamples whole paired blocks, not messages. A complete three-policy comparison requires all five valid blocks. Skipped scheduled slots are retained outcomes. No completed-Send-to-processing acknowledgment or isolated HTTP/2 stall inference is made.

Do not overwrite or resume these directories. Executables and environment-variable dumps are excluded. Final checksums are verified from repository root via `sha256sum --check experiments/002/results/stage5/SHA256SUMS`.

## Final primary outputs

- [Primary analysis](primary-v2/analysis.json), [per-run CSV](primary-v2/per-run.csv), [independent verification](primary-v2/verification.json), and [final matrix state](primary-v2/matrix-state.json):15valid runs/five blocks, zero corrected-cohort invalid runs.
- [All attempts](ALL-ATTEMPTS.jsonl) and [cohort disposition/exclusions](EXCLUSIONS.json):18attempts total, including the retained initial startup failure and two valid runs from the abandoned incomplete cohort.
- [Endpoint graph](primary-v2/primary-endpoints.png) / [SVG](primary-v2/primary-endpoints.svg); [all-run trajectories](primary-v2/primary-trajectories.png) / [SVG](primary-v2/primary-trajectories.svg). Recovery graph omits right-censored points; report/JSON retain them explicitly.
- `primary-v2/b*/`:full raw results for all15primary runs. Original `b01-*` remain separate and untouched.
- [Historical integrity](historical-integrity.json):1280historical evidence/report files unchanged. [Source proof](source-proof.json) checks both committed harness versions and fixed application/binaries.
- `checks/`:preflight/build/test/lint/collection/verification/analysis logs. `package-audit.py` and `render-report.py` are **post-run archival/report-formatting helpers**, not revised endpoint definitions. The frozen endpoint analysis remains `../../stage5/analyze.py` unchanged. The helpers record this workspace's paths; raw-data analysis/verifier scripts resolve repository-relative paths.
- No primary hypothesis is declared successful solely from pooled p95. H1/H2 supported; fullH3/H4/H5 not established under the prespecified decision rules. See report for scope and censoring.
