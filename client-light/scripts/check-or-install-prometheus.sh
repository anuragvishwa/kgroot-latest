#!/usr/bin/env bash
set -euo pipefail

# Simple helper to detect and (optionally) install kube-prometheus-stack
# in namespace "monitoring" for local testing (e.g., minikube).
# - Requires: kubectl, helm
# - Default release name: kps

RELEASE_NAME=${RELEASE_NAME:-kps}
NAMESPACE=${NAMESPACE:-monitoring}
CHART_REPO_NAME=${CHART_REPO_NAME:-prometheus-community}
CHART_REPO_URL=${CHART_REPO_URL:-https://prometheus-community.github.io/helm-charts}
CHART_NAME=${CHART_NAME:-kube-prometheus-stack}

echo "[+] Checking cluster access..."
kubectl version --short >/dev/null 2>&1 || { echo "kubectl cannot reach a cluster"; exit 1; }

echo "[+] Ensuring Helm repo $CHART_REPO_NAME is added..."
if ! helm repo list | grep -q "^$CHART_REPO_NAME\b"; then
  helm repo add "$CHART_REPO_NAME" "$CHART_REPO_URL"
fi
helm repo update >/dev/null

echo "[+] Checking if $RELEASE_NAME ($CHART_NAME) exists in namespace $NAMESPACE..."
if helm status "$RELEASE_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
  echo "[=] Found existing release: $RELEASE_NAME in $NAMESPACE"
else
  echo "[+] Installing $CHART_NAME into $NAMESPACE (lightweight defaults for minikube)..."
  kubectl get ns "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"
  # Lightweight install (no Grafana). Tune as needed.
  helm install "$RELEASE_NAME" "$CHART_REPO_NAME/$CHART_NAME" \
    -n "$NAMESPACE" \
    --create-namespace \
    --set grafana.enabled=false \
    --set kubeStateMetrics.enabled=true \
    --set nodeExporter.enabled=false \
    --set alertmanager.enabled=true \
    --wait
fi

echo "[+] Discovering Prometheus service..."
PROM_SVC=$(kubectl get svc -n "$NAMESPACE" -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [[ -z "$PROM_SVC" ]]; then
  # common fallback name
  PROM_SVC="${RELEASE_NAME}-kube-prometheus-prometheus"
fi

PROM_URL="http://${PROM_SVC}.${NAMESPACE}.svc:9090"
echo "[=] Prometheus URL (in-cluster): $PROM_URL"
echo
echo "Paste this into your client-light values file:"
echo
cat <<YAML
stateWatcher:
  prometheusUrl: "$PROM_URL"
YAML
echo
echo "Then run: helm upgrade --install <release> ./helm-chart -f <values.yaml>"
