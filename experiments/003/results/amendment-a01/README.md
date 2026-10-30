# A01 correctness evidence

Client outstanding credits33; server admission32; no primary benchmark.

- [Amendment report](../../AMENDMENT-A01-REPORT.md): decision, memory/transport/retry implications, commands, observations and GO for Stage3.
- [Original specifications](spec-before/): exact baseline000308b bytes, preserved alongside updated canonical specifications.
- [Final regression manifest](checks/final-2/verification.json): actual commands, exits, toolchains, source hashes and dirty state; adjacent logs preserve every test.
- [Summary](summary.json): acceptance counts for the five final cases.
- [WAIT drain](wait-drain/verification.json), [REJECT](reject-drain/verification.json), [RETRY](retry-drain/verification.json), [DROP](drop-drain/verification.json), [WAIT cancellation](wait-cancel/verification.json): actual Go/Rust saturation with production client credit enforcement. Every directory retains immutable workload, commands, binaries' hashes, raw event ledgers, barrier snapshot, final server truth and Go authoritative reconciliation.
- [Source provenance](source-provenance.json), [preservation audit](preservation.json), [exclusions/development history](EXCLUSIONS.json), [checksums](SHA256SUMS).

`development-*` and `checks/final-1` are retained preliminary passes, not final acceptance. The final five use identical source/binaries matching `checks/final-2`. Worker barriers are explicit correctness injections; reported outcome counts are not policy performance results. Historical E1/E2 and Stage1/2 data were not overwritten.
