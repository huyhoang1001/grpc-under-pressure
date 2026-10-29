#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
source scripts/dev-env.sh
protoc_e3=$(rg --files "$CARGO_HOME/registry/src" | rg '/protoc-bin-vendored-linux-x86_64-3.2.0/bin/protoc$' | head -1)
"$protoc_e3" --version
protoc-gen-go --version
protoc-gen-go-grpc --version
"$protoc_e3" -I experiments/003/proto --go_out=experiments/003/client --go_opt=module=github.com/huyhoang1001/grpc-under-pressure/experiments/003/client --go-grpc_out=experiments/003/client --go-grpc_opt=module=github.com/huyhoang1001/grpc-under-pressure/experiments/003/client experiments/003/proto/overload.proto
