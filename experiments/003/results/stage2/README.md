# Stage 2 correctness evidence

No primary benchmark or policy-performance comparison was executed.

- [Stage 2 report](../../STAGE2-REPORT.md): implementation, commands and T01–T20 verdicts; includes the equal32-credit/admission experimental-design blocker.
- [Final acceptance](checks/acceptance-2/verification.json): actual commands, exits, environment, dirty state and source hashes; adjacent logs include all tests and repeated all-policy TCP checks.
- [Fixture summary](fixture-summary.json): four eight-original scheduled interoperability fixtures, not overload runs.
- [WAIT](final-interop-wait/verification.json), [REJECT](final-interop-reject/verification.json), [RETRY](final-interop-retry/verification.json), [DROP](final-interop-drop/verification.json): commands, executable/source/workload hashes, full raw client/server event ledgers and snapshots in each directory.
- [Source provenance](source-provenance.json): base commit plus dirty source, not a claim of committed final runtime.
- [Preservation audit](preservation.json):1,723 unchanged protected files.
- [Exclusions/development history](EXCLUSIONS.json): preliminary/failed development work distinguished from final acceptance. Missing early console transcripts disclosed.
- [Checksums](SHA256SUMS): package/source integrity, relative to repository root.

`checks/acceptance-1/`, `interop-wait/` and the initial regression transcript remain as development provenance; use `acceptance-2/` and `final-interop-*/` for final-source acceptance. No files from historical E1/E2 or Stage 1 were overwritten.
