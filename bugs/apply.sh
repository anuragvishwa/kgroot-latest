#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
kubectl apply -k "$SCRIPT_DIR"
echo "Applied bug scenarios in namespace 'buglab'"
