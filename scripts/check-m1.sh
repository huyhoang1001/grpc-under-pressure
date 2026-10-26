#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/dev-env.sh
cargo test --locked --manifest-path server/Cargo.toml -j 4
cargo build --locked --manifest-path server/Cargo.toml -j 4
(cd loadgen && go test -mod=readonly -v ./... && go build -mod=readonly ./...)
