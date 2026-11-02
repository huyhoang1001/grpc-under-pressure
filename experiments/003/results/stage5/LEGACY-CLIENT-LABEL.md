# Legacy client metadata label

The committed Stage4 client binary is deliberately unchanged. Its report contains a compile-time `pilot_only: true` field and the source command is named `cmd/pilot`; these describe the inherited CLI, not whether a new invocation belongs to the primary study. Actual Stage5 membership is fixed by the preregistered RUN-PLAN, matched-block manifests and primary-run manifests (`primary_run: true`, `pilot_only: false`). Fresh primary traffic is generated for every run; no pilot data is reused. The primary verifier tests the authoritative run manifest and all measurement gates. The original client label is preserved verbatim rather than rewritten.

This clarification changes no endpoint, workload, exclusion or analysis rule and was recorded during execution before primary numerical outcomes were inspected.
