# Evidence provenance and integrity

Audit baseline Git commit: `93d23861d617a79dc9d8a94e8ec02dd12649ceec`. This was also `origin/main` when checked with `git ls-remote origin refs/heads/main`. The package's later commit can be obtained with `git log -1 --format=%H -- experiments/001/EVIDENCE-INDEX.md`; it cannot include its own SHA without changing that SHA.

Original implementation/report/results were introduced by commit `2dd3ffd18d54de0325544918139081fac35a010b`. The specification first appeared in `b831de6` (initial scaffold). These are **artifact archival commits, not proven benchmark execution commits**.

The original run manifests contain source and executable SHA256 values, but no contemporaneously captured Git SHA or dirty-tree status. Therefore an exact execution commit is missing and cannot be reconstructed reliably from commit order. Do not cite the audit baseline or implementation commit as the measured checkout. Primary runs used pre-hardening uncommitted server source; the committed implementation includes subsequent cancellation-accounting hardening.

Measured main source snapshots: [Rust](../results/e1/source/server-main.rs) and [Go](../results/e1/source/loadgen-main.go). The audit verifies their hashes against all non-excluded calibration/control/overload/diagnostic manifests. Cargo.lock and go.sum hashes also match. Final smoke hashes match the current committed source. Only these selected input hashes were captured, not a complete build-input manifest. Executable hashes are recorded; original measured executables are not archived in Git. No claim of byte-identical binary reconstruction is made.

`overload-1-direct` has a recorded source-hash mismatch and an explicit exclusion annotation. Its raw files remain intact; `overload-6-direct` replaces it. This audit preserves that original disposition rather than inventing a new successful outcome.

## Verification without running workloads

From the repository root:

```sh
sha256sum -c experiments/001/review/SHA256SUMS
python3 experiments/001/review/verify.py > /tmp/e1-review-audit.json
```

The verification script only reads files. It checks all 28 manifests and companion files, exit/status/final counts, sampled queue/ownership accounting, capacity/safety limits, topology, recorded timing counters, selected source hashes, and recomputes primary queue/producer/consumer rates against stored analysis. The retained [AUDIT.json](AUDIT.json) records this check. It does not establish on-wire transmission, unsampled queue peaks, or historical correctness beyond the retained evidence.

Checksums protect files as packaged, not their original acquisition authenticity. They cover the original tracked Experiment 001 artifacts plus relevant source, manifests, setup scripts and new review documents; the checksum file excludes itself. All original result bytes and the frozen specification remain unchanged by this audit.

## Sensitive and large artifacts

Screened 260 previously tracked evidence/source/setup files for common GitHub/AWS token, private-key and Authorization/Bearer patterns; no matches were found. This is a targeted screening, not a guarantee against every secret format. Existing h2 logs are localhost transport debug logs, not production traffic captures. No credentials, process environment dumps, binaries, build caches, uploads or new packet captures are included.

Existing results total about 12 MiB. The largest files are the two diagnostic server logs (about 7.0 MiB and 2.8 MiB); retain them because they are the original transport evidence. They are already tracked, and are neither duplicated nor rewritten. Generated figures and compact analysis are also retained. No additional large archive is created.

## Reviewer access

All original specification/report/results files are tracked in the baseline above, and the remote main SHA matched it during this audit. That proves Git publication state, not another person's authorization. If a reviewer cannot open the repository links, the owner must grant repository read access or securely share the package; this task cannot infer or change their permissions. A local commit of this review index must also be pushed before remote readers can see the new index.
