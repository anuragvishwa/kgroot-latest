#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
kubectl delete -k "$SCRIPT_DIR" --ignore-not-found
echo "Deleted bug scenarios from namespace 'buglab'"
