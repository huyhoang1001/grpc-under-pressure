#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
source scripts/dev-env.sh
cargo fmt --manifest-path experiments/003/server/Cargo.toml -- --check
cargo build --locked --manifest-path experiments/003/server/Cargo.toml
cargo test --locked --manifest-path experiments/003/server/Cargo.toml
cargo clippy --locked --manifest-path experiments/003/server/Cargo.toml --all-targets -- -D warnings
(cd experiments/003/client && go mod verify && go test -mod=readonly -race -count=1 -v ./... && go vet ./... && go build -mod=readonly -o /workspace/toolchains/bin/e3-stage1-smoke ./cmd/smoke)
# Optional two-message correctness fixture, never the 36s performance workload.
if [[ $# -eq 1 ]]; then
  python3 experiments/003/fixtures/interop.py --output "$1"
fi
