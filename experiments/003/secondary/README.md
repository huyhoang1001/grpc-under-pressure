# Secondary-only E3 runtime v1

Forked from accepted primary application at4638543. Neither `../server`, `../client`, normative specifications nor historical results are modified. Same Cargo/go module names are retained for copied regression tests/generated bindings; executables build into **this directory's separate target** and a private /tmp path. They must not replace the Stage5 executable. Git commit plus frozen source/binary manifests version this runtime separately.

Runtime deltas:

- Rust `service.rs`: fixed1/8 stream registration by client metadata; one shared decoder reservation with round-robin polling, one ledger/admission32/worker/sweep/logger/writer; immutable-ID response routing, bounded per-stream bridge1, global EOF after all half-closes. Work/cancel ownership must match stream client. One stream failure cancels the whole secondary run; it is not a claim of independent per-client failure isolation.
- Rust `main.rs`: explicit client count, secondary readiness marker. Ledger, deadlines, worker schedule, protocol generation and measurement source otherwise remain copied from the primary.
- Go `ledger.go`, `policy.go`, `scheduler.go`, `reconcile.go`: bounded global ID indexes with local partition ownership, disjoint attempt namespaces, owned-only arrivals/reconciliation, optional fixed-cap backoff. Primary-library regression defaults remain unchanged in this fork.
- Go `cmd/secondary`: validates exact500ms/2s/5s immutable manifests,1/8 clients, secondary/smoke profiles, direct output0, and cutoff39/42s (8s for labeled80-original fixtures); filters authoritative snapshot by client before reconciliation. Clock/transport/queue telemetry remains enabled.
- No adaptive policy, added worker, unbounded queue, changed payload/service schedule, extra original demand, forced retry barrier, or implicit gRPC retry.

Per-client original/attempt arrays retain capacities2880/8640 for global IDs, explicitly multiplying bounded metadata by8; server capacities do not multiply. Client credits33/pending32 are per-process. All this differs from single-client primary resource capacity and must be disclosed rather than attributed to retry jitter. Only the two eight-client variants are directly matched for H6.

Dependencies/locks are copied/pinned; vendored protoc package3.2.0 is pinned by Cargo.lock. Use `source scripts/dev-env.sh`, then Cargo test/clippy/normal build under secondary/server and Go race/vet/build under secondary/client. Always restore and repeat the normal Cargo build after tests before binary freeze.
