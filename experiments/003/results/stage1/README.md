# Stage 1 correctness evidence — not performance results

Start with [STAGE1-REPORT.md](../../STAGE1-REPORT.md).

- `checks/`: final build/test/lint checks, repeated transport and Go race tests, unchanged E1/E2 regressions, protobuf versions/regeneration.
- `interop-4/`: final committed-source **two-message** Rust/Go fixture; `verification.json` records hashes, commands and assertions; server JSONL/ledger, client JSONL/report and immutable identity artifact are retained.
- `interop-1..3/`: earlier development correctness fixtures, retained with their own provenance. They are not repetitions of a benchmark.
- `environment.json`: final code/toolchain and lockfile hashes.
- `specifications.json`: original upload/current hashes and the approved clarification scope.
- `preservation.json`:1658 preexisting E1/E2/source/evidence files byte-identical to f82d3ba.

Interop uses a synthetic offline39s reconciliation cutoff for unsent IDs; only two actual messages are sent. No primary traffic, performance matrix, calibration claim or policy comparison is included. Executables/build caches are excluded.
