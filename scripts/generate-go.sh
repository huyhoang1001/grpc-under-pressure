#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/dev-env.sh
go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.10
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1
# cargo fetch verifies registry checksums, including the pinned protoc package.
cargo fetch --locked --manifest-path server/Cargo.toml
mapfile -t compilers < <(find "$CARGO_HOME/registry/src" -path '*/protoc-bin-vendored-linux-x86_64-3.2.0/bin/protoc')
[[ ${#compilers[@]} == 1 ]] || { echo 'Expected one pinned linux/amd64 protoc' >&2; exit 1; }
"${compilers[0]}" -I proto --go_out=loadgen \
 --go_opt=module=github.com/huyhoang1001/grpc-under-pressure/loadgen \
 --go-grpc_out=loadgen \
 --go-grpc_opt=module=github.com/huyhoang1001/grpc-under-pressure/loadgen proto/ingest.proto
