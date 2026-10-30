# Stage 3 measurement-validity evidence

No primary benchmark or policy ranking. **PASS; GO for bounded Stage4 pilots**, with overhead/unsupported-counter limits in the [report](../../STAGE3-REPORT.md).

Final acceptance:

- [Final checks](checks/acceptance-4/verification.json): exact commands, exits, source hashes, toolchains, all regressions and repeated race/transport tests.
- Real Go/Rust fixtures: [WAIT](accepted-wait-drain/), [REJECT](accepted-reject-drain/), [RETRY](accepted-retry-drain/), [DROP](accepted-drop-drain/), [WAIT cancellation](accepted-wait-cancel/). Each retains workload, commands, binary hashes, process CSVs, client/server event ledgers, barrier/finished/clock records, snapshots, reconciliation and independent verification. Use `independent-verification-v2.json` for final analysis; original run-time verification is retained.
- [Measurement summary](measurement-summary.json): supported counters, exact HWM, clock uncertainty, sampled RSS/CPU, transport bytes and record-storage estimates. `*-state.csv`/`*-series.csv` are derived; process `*-metrics.csv` is raw. Final allocation estimates repeated in series are labeled references.
- [Fifteen corruption fixtures](accepted-faults-v2/verification.json): invalid data rejected without altering raw evidence.
- [Explicit synthetic fixtures](accepted-synthetic-verification-v2.json):2880 unsent originals, terminal/boundary/retry/ACK/UNKNOWN cases including failed Send before decode. Not measured results.
- [Matched logging plan](sweep-overhead-plan-v4.json), `sweep-v4-*`, [summary](sweep-overhead-summary.json): three identical-source WAIT pairs; only legacy no-op logging toggles. No CPU saving established.
- [Encoding calibration](encoding-overhead/summary.json): three matched JSON/file vs no-encoding micro-pairs. Measures incremental output cost, not total instrumentation cost. No-encoding controls are not valid E3 runs.
- [Legacy Stage1 interoperability regression](stage1-regression/verification.json): supplemental protocol correctness, not Stage3 clock validation.

Provenance and review:

- [Source provenance](source-provenance.json), [historical preservation](preservation.json), [artifact catalog](ARTIFACT-MANIFEST.json), [checksums](SHA256SUMS).
- [Exclusions/development ledger](EXCLUSIONS.json): startup probe failures, an invalid shutdown-race run, and all superseded passing checks/fixtures remain intact. Only `accepted-*`, `sweep-v4-*` and `checks/acceptance-4` establish final application acceptance.
- [Analysis scripts](analysis/): reproduce summaries/synthetic fixtures; archived run-time verifier matches measured provenance. Current verifier differs only in offline failed-Send byte-floor handling and output/hash metadata.

A01 specifications and historical E1/E2/Stage1/2/A01 data are unchanged. The fixture uses33 scheduled originals and a controlled worker barrier; it is not the36-second workload. Stage4 orchestration/coverage and total instrumentation materiality still require pilot validation.
