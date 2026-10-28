# Stage 4 evidence

Start with [STAGE4-REPORT.md](../../STAGE4-REPORT.md) and [predeclared protocol plus recorded fixture correction](../../stage4/README.md).

- `environment.json`: compiler/dependency/build/cgroup/affinity data and binary digests. Build source a6942a3; fixture-only harness correction40bb23f has identical server inputs (`source-reconciliation.json`).
- `ledger.jsonl`: every attempt, including the invalid original cancellation fixture. Eight valid purpose-specific runs (including three expected failed RPCs) and one invalid coverage attempt; one full adaptive exploration.
- `declared-exclusions.json`: original cancellation deadline failed to allow two ticks; original data are untouched. The distinct corrected fixture is labeled separately.
- `verification.json`: per-run independent accounting, gate/event and controller replay results; the declared invalid attempt remains visibly invalid.
- `analysis.json`: descriptive run metrics, full budget changes and historical fixed32/fixed8 comparisons, recovery-window screen and caveats.
- `exploratory-adaptive/`: full36-second workload; each run directory contains exact manifest/commands/hashes/clock/exit data, controller ticks, message/service events, histograms, 200ms server/client/process samples, Send events, Summary and logs.
- `exploratory-comparison.png` / `.svg`: separate-run/source-version comparison; no primary inference.
- `supplement.json`: raw-counter-derived CPU/RSS and final server accounting.
- `checks/`: build/test/lint, acceptance failure/correction, exploration and audit stdout/stderr.
- `historical-integrity.json`:1106 historical files byte-identical to e32bc0a.
- `SHA256SUMS`: verify from repository root using `sha256sum --check experiments/002/results/stage4/SHA256SUMS`.

Do not overwrite run directories or retune after observing results. No primary matrix, extra workers or blog artifact is included. Executables and environment-variable dumps are excluded.
