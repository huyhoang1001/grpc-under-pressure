# Milestone status

## Implemented and validated

- M1: pinned Rust/Go/codegen foundation, generated protobuf bindings, locked dependencies and transport source audit.
- Experiment 001 runtime: V0 direct, V1 unbounded, V2 reserve-before-receive bounded queue; paced sequential Go sender, consistent ownership/queue counters, CSV/RSS/CPU sampling, cancellation cleanup and safety thresholds.
- Four Rust unit tests, two Go tests and eight process integration tests pass; both builds and warnings-denied Clippy pass.
- Sender/worker calibration, all three below-capacity controls, five valid short overload repetitions per variant, and separate h2 diagnostics executed. Original excluded run and replacement are retained.
- Raw samples/manifests/source snapshots, analysis, figures and REPORT.md are present. Final cancellation hardening passed regression tests and three additional smoke runs.

## Remaining research/publication work

The primary dataset uses 12 s debug-build overloads and predates the final cancellation-only accounting hardening. Re-run the final source in release mode with longer predeclared workloads/controls before publication. No wire packet capture, heap attribution, confidence intervals or independent-machine reproduction exists. Service-time percentiles and a live Prometheus exporter are not implemented; cumulative service timing and CSV collection are available. See REPORT.md for exact supported conclusions. Do not begin adaptive concurrency as part of this experiment.
