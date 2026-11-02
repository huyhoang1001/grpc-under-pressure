# E3 Stage6 secondary evidence index

Source/preregistration `ec97c831d085bd96c102a3af6beaadfda6e92669`; B2 orchestration `5c2ccfd5d2db0228ac9d1b5e1fb6a1648e8e1dbc`; Stage5/primary baseline4638543 unchanged. MatrixCOMPLETE;50 attempted study runs. No Stage5 observations enter the secondary analysis.

- [Plan](../../STAGE6-PLAN.md) and [report](../../STAGE6-REPORT.md)
- [Original machine run plan](RUN-PLAN.json), [B2 seed amendment](../../STAGE6-B-SEED-AMENDMENT.md), [B2 machine plan](RUN-PLAN-B2.json), [B2 freeze](FROZEN-MANIFEST-B2.json), [seed discovery note](SEED-STREAM-REVIEW.md), [boundary proof](BOUNDARY-VERIFICATION.json), [workloads](workloads/), [source/binary/environment freeze](FROZEN-MANIFEST.json)
- [Original matrix](MATRIX.json), [B2 matrix](MATRIX-B2.json), [combined derived matrix](MATRIX-COMBINED.json), [all exclusions/attempts](EXCLUSIONS-COMBINED.json), [original log](execution.log), [B2 log](execution-B2.log)
- [Isolated runtime/implementation differences](../../secondary/README.md)
- [B2 pinned fixtures](preflight/b2-pinned/) and [B2 verifier fault checks](checks/fault-verification-b2-pinned.json)
- [Structured correctness checks](checks/validated/COMMANDS.json), [pinned correctness fixtures](preflight/pinned/), [synthetic verifier faults](checks/fault-verification-pinned.json)
- [Original frozen analysis](../../secondary/fixtures/analyze.py), [versioned combined-input analysis](analysis/analyze_b2.py), [results](analysis/RESULTS.json), [per-run CSV](analysis/runs.csv), [figures](analysis/figures/)
- [Offline audit script](analysis/audit.py), [output/common39 supplement](analysis/OFFLINE-AUDIT.json), [table/report generator](analysis/publish.py)
- [Pre-study primary preservation](checks/PRIMARY-PRESERVATION-BEFORE.json)
- [Package/source/credential checks](PACKAGE-VERIFICATION.json), [content checksums](SHA256SUMS.json), [package checker](analysis/verify-package.py)

## Every measurement attempt
Original superseded B startup/plan records are retained in the original matrix and boundary proof; they contain zero traffic.

|Study|Block/attempt|Condition|Verdict|Evidence directory|
|---|---|---|---|---|
|A|1/1|a500-drop|PASS|[a500-drop](A-block-01-attempt-01/a500-drop/)|
|A|1/1|a5000-retry|PASS|[a5000-retry](A-block-01-attempt-01/a5000-retry/)|
|A|1/1|a500-retry|PASS|[a500-retry](A-block-01-attempt-01/a500-retry/)|
|A|1/1|a500-wait|PASS|[a500-wait](A-block-01-attempt-01/a500-wait/)|
|A|1/1|a500-reject|PASS|[a500-reject](A-block-01-attempt-01/a500-reject/)|
|A|1/1|a5000-wait|PASS|[a5000-wait](A-block-01-attempt-01/a5000-wait/)|
|A|1/1|a5000-drop|PASS|[a5000-drop](A-block-01-attempt-01/a5000-drop/)|
|A|1/1|a5000-reject|PASS|[a5000-reject](A-block-01-attempt-01/a5000-reject/)|
|A|2/1|a500-wait|PASS|[a500-wait](A-block-02-attempt-01/a500-wait/)|
|A|2/1|a5000-wait|PASS|[a5000-wait](A-block-02-attempt-01/a5000-wait/)|
|A|2/1|a500-drop|PASS|[a500-drop](A-block-02-attempt-01/a500-drop/)|
|A|2/1|a500-reject|PASS|[a500-reject](A-block-02-attempt-01/a500-reject/)|
|A|2/1|a5000-reject|PASS|[a5000-reject](A-block-02-attempt-01/a5000-reject/)|
|A|2/1|a5000-drop|PASS|[a5000-drop](A-block-02-attempt-01/a5000-drop/)|
|A|2/1|a5000-retry|PASS|[a5000-retry](A-block-02-attempt-01/a5000-retry/)|
|A|2/1|a500-retry|PASS|[a500-retry](A-block-02-attempt-01/a500-retry/)|
|A|3/1|a500-retry|PASS|[a500-retry](A-block-03-attempt-01/a500-retry/)|
|A|3/1|a5000-reject|PASS|[a5000-reject](A-block-03-attempt-01/a5000-reject/)|
|A|3/1|a500-wait|PASS|[a500-wait](A-block-03-attempt-01/a500-wait/)|
|A|3/1|a500-drop|PASS|[a500-drop](A-block-03-attempt-01/a500-drop/)|
|A|3/1|a500-reject|PASS|[a500-reject](A-block-03-attempt-01/a500-reject/)|
|A|3/1|a5000-wait|PASS|[a5000-wait](A-block-03-attempt-01/a5000-wait/)|
|A|3/1|a5000-retry|PASS|[a5000-retry](A-block-03-attempt-01/a5000-retry/)|
|A|3/1|a5000-drop|PASS|[a5000-drop](A-block-03-attempt-01/a5000-drop/)|
|A|4/1|a5000-wait|PASS|[a5000-wait](A-block-04-attempt-01/a5000-wait/)|
|A|4/1|a500-wait|PASS|[a500-wait](A-block-04-attempt-01/a500-wait/)|
|A|4/1|a500-reject|PASS|[a500-reject](A-block-04-attempt-01/a500-reject/)|
|A|4/1|a500-retry|PASS|[a500-retry](A-block-04-attempt-01/a500-retry/)|
|A|4/1|a5000-drop|PASS|[a5000-drop](A-block-04-attempt-01/a5000-drop/)|
|A|4/1|a5000-reject|PASS|[a5000-reject](A-block-04-attempt-01/a5000-reject/)|
|A|4/1|a500-drop|PASS|[a500-drop](A-block-04-attempt-01/a500-drop/)|
|A|4/1|a5000-retry|PASS|[a5000-retry](A-block-04-attempt-01/a5000-retry/)|
|A|5/1|a5000-retry|PASS|[a5000-retry](A-block-05-attempt-01/a5000-retry/)|
|A|5/1|a5000-reject|PASS|[a5000-reject](A-block-05-attempt-01/a5000-reject/)|
|A|5/1|a500-drop|PASS|[a500-drop](A-block-05-attempt-01/a500-drop/)|
|A|5/1|a500-retry|PASS|[a500-retry](A-block-05-attempt-01/a500-retry/)|
|A|5/1|a5000-wait|PASS|[a5000-wait](A-block-05-attempt-01/a5000-wait/)|
|A|5/1|a5000-drop|PASS|[a5000-drop](A-block-05-attempt-01/a5000-drop/)|
|A|5/1|a500-reject|PASS|[a500-reject](A-block-05-attempt-01/a500-reject/)|
|A|5/1|a500-wait|PASS|[a500-wait](A-block-05-attempt-01/a500-wait/)|
|B|1/1|b-deterministic|PASS|[b-deterministic](B2-block-01-attempt-01/b-deterministic/)|
|B|1/1|b-jitter|PASS|[b-jitter](B2-block-01-attempt-01/b-jitter/)|
|B|2/1|b-deterministic|PASS|[b-deterministic](B2-block-02-attempt-01/b-deterministic/)|
|B|2/1|b-jitter|PASS|[b-jitter](B2-block-02-attempt-01/b-jitter/)|
|B|3/1|b-deterministic|PASS|[b-deterministic](B2-block-03-attempt-01/b-deterministic/)|
|B|3/1|b-jitter|PASS|[b-jitter](B2-block-03-attempt-01/b-jitter/)|
|B|4/1|b-jitter|PASS|[b-jitter](B2-block-04-attempt-01/b-jitter/)|
|B|4/1|b-deterministic|PASS|[b-deterministic](B2-block-04-attempt-01/b-deterministic/)|
|B|5/1|b-deterministic|PASS|[b-deterministic](B2-block-05-attempt-01/b-deterministic/)|
|B|5/1|b-jitter|PASS|[b-jitter](B2-block-05-attempt-01/b-jitter/)|

Each directory contains immutable workload, startup/final manifests and exact argv/hashes/configuration, server authoritative ledger/events/clock/phases/finished/cutoff markers, each client’s report/events/transport/exit markers,200ms per-process CPU/RSS CSVs, process logs, independent verification and attempt outcome. Every failed attempt and its available partial artifacts are preserved.

Developmental v1/final/rc fixtures and initial failed Clippy/reader-only abort checks remain under checks/preflight with their source hashes; they are not study runs. The final pinned fixtures use the committed study version. No executable, build cache, credential or full payload-content archive is needed. Large JSONL/ledger files are intentional raw evidence below the file guard.
