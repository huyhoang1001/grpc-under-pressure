#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/dev-env.sh
bash scripts/check-m1.sh
(cd loadgen && go build -mod=readonly -o "$GOBIN/pressure-loadgen" ./cmd/loadgen)
python3 -m unittest discover -s experiments/001/tests -v
