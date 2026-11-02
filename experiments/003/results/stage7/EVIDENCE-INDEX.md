# E3 Stage7 review evidence index

Verdict:PUBLISH for qualified drafting/publication readiness; no article draft. Reviewed inputs at25771cd. No performance runs executed; previous artifacts preserved.

- [Review report](../../STAGE7-REPORT.md)
- [Claim matrix](CLAIMS.md), [CSV](CLAIMS.csv), [JSON](CLAIMS.json), [generator](claims.py)
- [Publication outline/thesis/disclosures](PUBLICATION-OUTLINE.md)
- [Chart registry/captions](CHARTS.json), [data](CHART-DATA.json), [review rendering](figures/primary-tradeoff.png), [generator](charts.py)
- [New raw-arithmetic audit](audit.py), [output](audit/REVIEW-AUDIT.json), [run inventory](audit/RUNS.csv), [final execution log](audit-execution-final.log)
- [Context arithmetic checks](CONTEXT-CHECKS.json), [raw CPU/RSS/sampling guard checks](METRIC-CHECKS.json), [report generator](report.py), [publication/preservation checks](checks.py), [check output](PUBLICATION-CHECKS.json), [review checksums](SHA256SUMS.json)

## Reviewed inputs (read-only)

- [Experiment](../../EXPERIMENT-003.md), [protocol](../../PROTOCOL-003.md), [validity](../../VALIDITY-003.md), [A01 report](../../AMENDMENT-A01-REPORT.md)
- Primary:[plan](../../STAGE5-PLAN.md), [report](../../STAGE5-REPORT.md), [index](../stage5/EVIDENCE-INDEX.md), [original offline audit](../stage5/analysis/OFFLINE-AUDIT.json), [analysis](../../fixtures/analyze-stage5.py), [results](../stage5/analysis/RESULTS.json), [freeze](../stage5/FROZEN-MANIFEST.json), [matrix](../stage5/MATRIX.json), [exclusions](../stage5/EXCLUSIONS.json), [checksums](../stage5/SHA256SUMS.json)
- Secondary:[plan](../../STAGE6-PLAN.md), [B2 amendment](../../STAGE6-B-SEED-AMENDMENT.md), [report](../../STAGE6-REPORT.md), [index](../stage6/EVIDENCE-INDEX.md), [original offline audit](../stage6/analysis/OFFLINE-AUDIT.json), [analysis](../stage6/analysis/analyze_b2.py), [results](../stage6/analysis/RESULTS.json), [A freeze](../stage6/FROZEN-MANIFEST.json), [B2 freeze](../stage6/FROZEN-MANIFEST-B2.json), [A/interrupted matrix](../stage6/MATRIX.json), [B2 matrix](../stage6/MATRIX-B2.json), [derived matrix](../stage6/MATRIX-COMBINED.json), [exclusions](../stage6/EXCLUSIONS-COMBINED.json), [checksums](../stage6/SHA256SUMS.json)
- B2 chronology:[discovery note](../stage6/SEED-STREAM-REVIEW.md), [boundary proof](../stage6/BOUNDARY-VERIFICATION.json), [interrupted matrix](../stage6/MATRIX-AT-BOUNDARY.json), [B2 plan](../stage6/RUN-PLAN-B2.json)

## Direct run references

Every row represents a new arithmetic/gate replay of preserved evidence, not a new run. Statistical comparisons retain separate five-block primary/A/B2 families. JSON field locators in claims refer to the audit’s named keys.

|Family|Block|Condition|U/N|Raw run directory|Archived verifier|
|---|---|---|---|---|---|
|PRIMARY|1|wait|2198/2880|[raw](../stage5/block-01-attempt-01/wait/)|[verification](../stage5/block-01-attempt-01/wait/primary-verification.json)|
|PRIMARY|1|drop|2191/2880|[raw](../stage5/block-01-attempt-01/drop/)|[verification](../stage5/block-01-attempt-01/drop/primary-verification.json)|
|PRIMARY|1|retry|2236/2880|[raw](../stage5/block-01-attempt-01/retry/)|[verification](../stage5/block-01-attempt-01/retry/primary-verification.json)|
|PRIMARY|1|reject|2161/2880|[raw](../stage5/block-01-attempt-01/reject/)|[verification](../stage5/block-01-attempt-01/reject/primary-verification.json)|
|PRIMARY|2|retry|2223/2880|[raw](../stage5/block-02-attempt-01/retry/)|[verification](../stage5/block-02-attempt-01/retry/primary-verification.json)|
|PRIMARY|2|reject|2201/2880|[raw](../stage5/block-02-attempt-01/reject/)|[verification](../stage5/block-02-attempt-01/reject/primary-verification.json)|
|PRIMARY|2|wait|2155/2880|[raw](../stage5/block-02-attempt-01/wait/)|[verification](../stage5/block-02-attempt-01/wait/primary-verification.json)|
|PRIMARY|2|drop|2163/2880|[raw](../stage5/block-02-attempt-01/drop/)|[verification](../stage5/block-02-attempt-01/drop/primary-verification.json)|
|PRIMARY|3|drop|2199/2880|[raw](../stage5/block-03-attempt-01/drop/)|[verification](../stage5/block-03-attempt-01/drop/primary-verification.json)|
|PRIMARY|3|reject|2201/2880|[raw](../stage5/block-03-attempt-01/reject/)|[verification](../stage5/block-03-attempt-01/reject/primary-verification.json)|
|PRIMARY|3|wait|2196/2880|[raw](../stage5/block-03-attempt-01/wait/)|[verification](../stage5/block-03-attempt-01/wait/primary-verification.json)|
|PRIMARY|3|retry|2235/2880|[raw](../stage5/block-03-attempt-01/retry/)|[verification](../stage5/block-03-attempt-01/retry/primary-verification.json)|
|PRIMARY|4|drop|2188/2880|[raw](../stage5/block-04-attempt-01/drop/)|[verification](../stage5/block-04-attempt-01/drop/primary-verification.json)|
|PRIMARY|4|wait|2202/2880|[raw](../stage5/block-04-attempt-01/wait/)|[verification](../stage5/block-04-attempt-01/wait/primary-verification.json)|
|PRIMARY|4|reject|2197/2880|[raw](../stage5/block-04-attempt-01/reject/)|[verification](../stage5/block-04-attempt-01/reject/primary-verification.json)|
|PRIMARY|4|retry|2244/2880|[raw](../stage5/block-04-attempt-01/retry/)|[verification](../stage5/block-04-attempt-01/retry/primary-verification.json)|
|PRIMARY|5|drop|2205/2880|[raw](../stage5/block-05-attempt-01/drop/)|[verification](../stage5/block-05-attempt-01/drop/primary-verification.json)|
|PRIMARY|5|retry|2233/2880|[raw](../stage5/block-05-attempt-01/retry/)|[verification](../stage5/block-05-attempt-01/retry/primary-verification.json)|
|PRIMARY|5|wait|2199/2880|[raw](../stage5/block-05-attempt-01/wait/)|[verification](../stage5/block-05-attempt-01/wait/primary-verification.json)|
|PRIMARY|5|reject|2208/2880|[raw](../stage5/block-05-attempt-01/reject/)|[verification](../stage5/block-05-attempt-01/reject/primary-verification.json)|
|A|1|a500-drop|1965/2880|[raw](../stage6/A-block-01-attempt-01/a500-drop/)|[verification](../stage6/A-block-01-attempt-01/a500-drop/independent-verification.json)|
|A|1|a5000-retry|2258/2880|[raw](../stage6/A-block-01-attempt-01/a5000-retry/)|[verification](../stage6/A-block-01-attempt-01/a5000-retry/independent-verification.json)|
|A|1|a500-retry|1963/2880|[raw](../stage6/A-block-01-attempt-01/a500-retry/)|[verification](../stage6/A-block-01-attempt-01/a500-retry/independent-verification.json)|
|A|1|a500-wait|1485/2880|[raw](../stage6/A-block-01-attempt-01/a500-wait/)|[verification](../stage6/A-block-01-attempt-01/a500-wait/independent-verification.json)|
|A|1|a500-reject|1959/2880|[raw](../stage6/A-block-01-attempt-01/a500-reject/)|[verification](../stage6/A-block-01-attempt-01/a500-reject/independent-verification.json)|
|A|1|a5000-wait|2259/2880|[raw](../stage6/A-block-01-attempt-01/a5000-wait/)|[verification](../stage6/A-block-01-attempt-01/a5000-wait/independent-verification.json)|
|A|1|a5000-drop|2233/2880|[raw](../stage6/A-block-01-attempt-01/a5000-drop/)|[verification](../stage6/A-block-01-attempt-01/a5000-drop/independent-verification.json)|
|A|1|a5000-reject|2233/2880|[raw](../stage6/A-block-01-attempt-01/a5000-reject/)|[verification](../stage6/A-block-01-attempt-01/a5000-reject/independent-verification.json)|
|A|2|a500-wait|1966/2880|[raw](../stage6/A-block-02-attempt-01/a500-wait/)|[verification](../stage6/A-block-02-attempt-01/a500-wait/independent-verification.json)|
|A|2|a5000-wait|2263/2880|[raw](../stage6/A-block-02-attempt-01/a5000-wait/)|[verification](../stage6/A-block-02-attempt-01/a5000-wait/independent-verification.json)|
|A|2|a500-drop|1965/2880|[raw](../stage6/A-block-02-attempt-01/a500-drop/)|[verification](../stage6/A-block-02-attempt-01/a500-drop/independent-verification.json)|
|A|2|a500-reject|1963/2880|[raw](../stage6/A-block-02-attempt-01/a500-reject/)|[verification](../stage6/A-block-02-attempt-01/a500-reject/independent-verification.json)|
|A|2|a5000-reject|2236/2880|[raw](../stage6/A-block-02-attempt-01/a5000-reject/)|[verification](../stage6/A-block-02-attempt-01/a5000-reject/independent-verification.json)|
|A|2|a5000-drop|2227/2880|[raw](../stage6/A-block-02-attempt-01/a5000-drop/)|[verification](../stage6/A-block-02-attempt-01/a5000-drop/independent-verification.json)|
|A|2|a5000-retry|2253/2880|[raw](../stage6/A-block-02-attempt-01/a5000-retry/)|[verification](../stage6/A-block-02-attempt-01/a5000-retry/independent-verification.json)|
|A|2|a500-retry|1949/2880|[raw](../stage6/A-block-02-attempt-01/a500-retry/)|[verification](../stage6/A-block-02-attempt-01/a500-retry/independent-verification.json)|
|A|3|a500-retry|1963/2880|[raw](../stage6/A-block-03-attempt-01/a500-retry/)|[verification](../stage6/A-block-03-attempt-01/a500-retry/independent-verification.json)|
|A|3|a5000-reject|2234/2880|[raw](../stage6/A-block-03-attempt-01/a5000-reject/)|[verification](../stage6/A-block-03-attempt-01/a5000-reject/independent-verification.json)|
|A|3|a500-wait|1966/2880|[raw](../stage6/A-block-03-attempt-01/a500-wait/)|[verification](../stage6/A-block-03-attempt-01/a500-wait/independent-verification.json)|
|A|3|a500-drop|1964/2880|[raw](../stage6/A-block-03-attempt-01/a500-drop/)|[verification](../stage6/A-block-03-attempt-01/a500-drop/independent-verification.json)|
|A|3|a500-reject|1954/2880|[raw](../stage6/A-block-03-attempt-01/a500-reject/)|[verification](../stage6/A-block-03-attempt-01/a500-reject/independent-verification.json)|
|A|3|a5000-wait|2263/2880|[raw](../stage6/A-block-03-attempt-01/a5000-wait/)|[verification](../stage6/A-block-03-attempt-01/a5000-wait/independent-verification.json)|
|A|3|a5000-retry|2256/2880|[raw](../stage6/A-block-03-attempt-01/a5000-retry/)|[verification](../stage6/A-block-03-attempt-01/a5000-retry/independent-verification.json)|
|A|3|a5000-drop|2234/2880|[raw](../stage6/A-block-03-attempt-01/a5000-drop/)|[verification](../stage6/A-block-03-attempt-01/a5000-drop/independent-verification.json)|
|A|4|a5000-wait|2256/2880|[raw](../stage6/A-block-04-attempt-01/a5000-wait/)|[verification](../stage6/A-block-04-attempt-01/a5000-wait/independent-verification.json)|
|A|4|a500-wait|1956/2880|[raw](../stage6/A-block-04-attempt-01/a500-wait/)|[verification](../stage6/A-block-04-attempt-01/a500-wait/independent-verification.json)|
|A|4|a500-reject|1959/2880|[raw](../stage6/A-block-04-attempt-01/a500-reject/)|[verification](../stage6/A-block-04-attempt-01/a500-reject/independent-verification.json)|
|A|4|a500-retry|1965/2880|[raw](../stage6/A-block-04-attempt-01/a500-retry/)|[verification](../stage6/A-block-04-attempt-01/a500-retry/independent-verification.json)|
|A|4|a5000-drop|2233/2880|[raw](../stage6/A-block-04-attempt-01/a5000-drop/)|[verification](../stage6/A-block-04-attempt-01/a5000-drop/independent-verification.json)|
|A|4|a5000-reject|2229/2880|[raw](../stage6/A-block-04-attempt-01/a5000-reject/)|[verification](../stage6/A-block-04-attempt-01/a5000-reject/independent-verification.json)|
|A|4|a500-drop|1963/2880|[raw](../stage6/A-block-04-attempt-01/a500-drop/)|[verification](../stage6/A-block-04-attempt-01/a500-drop/independent-verification.json)|
|A|4|a5000-retry|2256/2880|[raw](../stage6/A-block-04-attempt-01/a5000-retry/)|[verification](../stage6/A-block-04-attempt-01/a5000-retry/independent-verification.json)|
|A|5|a5000-retry|2249/2880|[raw](../stage6/A-block-05-attempt-01/a5000-retry/)|[verification](../stage6/A-block-05-attempt-01/a5000-retry/independent-verification.json)|
|A|5|a5000-reject|2235/2880|[raw](../stage6/A-block-05-attempt-01/a5000-reject/)|[verification](../stage6/A-block-05-attempt-01/a5000-reject/independent-verification.json)|
|A|5|a500-drop|1964/2880|[raw](../stage6/A-block-05-attempt-01/a500-drop/)|[verification](../stage6/A-block-05-attempt-01/a500-drop/independent-verification.json)|
|A|5|a500-retry|1966/2880|[raw](../stage6/A-block-05-attempt-01/a500-retry/)|[verification](../stage6/A-block-05-attempt-01/a500-retry/independent-verification.json)|
|A|5|a5000-wait|2263/2880|[raw](../stage6/A-block-05-attempt-01/a5000-wait/)|[verification](../stage6/A-block-05-attempt-01/a5000-wait/independent-verification.json)|
|A|5|a5000-drop|2230/2880|[raw](../stage6/A-block-05-attempt-01/a5000-drop/)|[verification](../stage6/A-block-05-attempt-01/a5000-drop/independent-verification.json)|
|A|5|a500-reject|1972/2880|[raw](../stage6/A-block-05-attempt-01/a500-reject/)|[verification](../stage6/A-block-05-attempt-01/a500-reject/independent-verification.json)|
|A|5|a500-wait|1944/2880|[raw](../stage6/A-block-05-attempt-01/a500-wait/)|[verification](../stage6/A-block-05-attempt-01/a500-wait/independent-verification.json)|
|B2|1|b-deterministic|2228/2880|[raw](../stage6/B2-block-01-attempt-01/b-deterministic/)|[verification](../stage6/B2-block-01-attempt-01/b-deterministic/independent-verification.json)|
|B2|1|b-jitter|2222/2880|[raw](../stage6/B2-block-01-attempt-01/b-jitter/)|[verification](../stage6/B2-block-01-attempt-01/b-jitter/independent-verification.json)|
|B2|2|b-deterministic|2231/2880|[raw](../stage6/B2-block-02-attempt-01/b-deterministic/)|[verification](../stage6/B2-block-02-attempt-01/b-deterministic/independent-verification.json)|
|B2|2|b-jitter|2225/2880|[raw](../stage6/B2-block-02-attempt-01/b-jitter/)|[verification](../stage6/B2-block-02-attempt-01/b-jitter/independent-verification.json)|
|B2|3|b-deterministic|2233/2880|[raw](../stage6/B2-block-03-attempt-01/b-deterministic/)|[verification](../stage6/B2-block-03-attempt-01/b-deterministic/independent-verification.json)|
|B2|3|b-jitter|2227/2880|[raw](../stage6/B2-block-03-attempt-01/b-jitter/)|[verification](../stage6/B2-block-03-attempt-01/b-jitter/independent-verification.json)|
|B2|4|b-jitter|2226/2880|[raw](../stage6/B2-block-04-attempt-01/b-jitter/)|[verification](../stage6/B2-block-04-attempt-01/b-jitter/independent-verification.json)|
|B2|4|b-deterministic|2230/2880|[raw](../stage6/B2-block-04-attempt-01/b-deterministic/)|[verification](../stage6/B2-block-04-attempt-01/b-deterministic/independent-verification.json)|
|B2|5|b-deterministic|2230/2880|[raw](../stage6/B2-block-05-attempt-01/b-deterministic/)|[verification](../stage6/B2-block-05-attempt-01/b-deterministic/independent-verification.json)|
|B2|5|b-jitter|2222/2880|[raw](../stage6/B2-block-05-attempt-01/b-jitter/)|[verification](../stage6/B2-block-05-attempt-01/b-jitter/independent-verification.json)|

The archived gate functions are reused in memory as shared-logic checks; raw arithmetic/histogram/bootstrap code is newly implemented in Stage7. Existing audits were read, not run via their writing mains. Internal Git/time/hash coherence is not independent-laboratory replication or external trusted attestation. The scope and source/runtime limitations are in the report.
