#!/bin/bash
# ==============================================================================
# Update kg-rca-agent Helm Chart for Control Plane V2 (13-topic architecture)
# ==============================================================================

set -e

REPO_ROOT="/Users/anuragvishwa/Anurag/kgroot_latest"
HELM_CHART_DIR="$REPO_ROOT/client-light/helm-chart"

echo "🚀 Updating kg-rca-agent Helm chart for Control Plane V2..."
echo "============================================================"

# 1. Update Chart.yaml version
echo "📝 Updating Chart.yaml to version 2.1.0..."
sed -i '' 's/version: 2.0.2/version: 2.1.0/' "$HELM_CHART_DIR/Chart.yaml"
sed -i '' 's/appVersion: "2.0.0"/appVersion: "2.1.0"/' "$HELM_CHART_DIR/Chart.yaml"

# 2. Create cluster-registry Job
echo "📝 Creating cluster-registry-job.yaml..."
cat > "$HELM_CHART_DIR/templates/cluster-registry-job.yaml" <<'EOF'
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "kg-rca-agent.fullname" . }}-registry
  labels:
    {{- include "kg-rca-agent.labels" . | nindent 4 }}
  annotations:
    "helm.sh/hook": post-install
    "helm.sh/hook-weight": "1"
    "helm.sh/hook-delete-policy": hook-succeeded
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: register
        image: confluentinc/cp-kafka:7.5.0
        command:
          - /bin/sh
          - -c
          - |
            echo '{{ .Values.client.id }}::{"client_id":"{{ .Values.client.id }}","cluster_name":"{{ .Values.cluster.name }}","region":"{{ .Values.cluster.region | default "unknown" }}","timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","chart_version":"{{ .Chart.Version }}"}' | \
            kafka-console-producer \
              --bootstrap-server {{ .Values.client.kafka.brokers }} \
              --topic cluster.registry \
              --property "parse.key=true" \
              --property "key.separator=::"
EOF

# 3. Create heartbeat CronJob
echo "📝 Creating heartbeat-cronjob.yaml..."
cat > "$HELM_CHART_DIR/templates/heartbeat-cronjob.yaml" <<'EOF'
{{- if .Values.heartbeat.enabled | default true }}
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {{ include "kg-rca-agent.fullname" . }}-heartbeat
  labels:
    {{- include "kg-rca-agent.labels" . | nindent 4 }}
spec:
  schedule: "*/1 * * * *"  # Every minute
  concurrencyPolicy: Replace
  successfulJobsHistoryLimit: 1
  failedJobsHistoryLimit: 1
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
          - name: heartbeat
            image: confluentinc/cp-kafka:7.5.0
            command:
              - /bin/sh
              - -c
              - |
                echo '{{ .Values.client.id }}::{"client_id":"{{ .Values.client.id }}","timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}' | \
                kafka-console-producer \
                  --bootstrap-server {{ .Values.client.kafka.brokers }} \
                  --topic cluster.heartbeat \
                  --property "parse.key=true" \
                  --property "key.separator=::"
{{- end }}
EOF

# 4. Add heartbeat config to values.yaml
echo "📝 Adding heartbeat configuration to values.yaml..."
cat >> "$HELM_CHART_DIR/values.yaml" <<'EOF'

# ==============================================================================
# Heartbeat Configuration (V2 Control Plane)
# ==============================================================================
heartbeat:
  enabled: true
  interval: "30s"  # Sends heartbeat every minute via CronJob
EOF

echo ""
echo "✅ Helm chart updated successfully!"
echo ""
echo "📦 Next steps:"
echo "   1. cd $REPO_ROOT/client-light"
echo "   2. helm package helm-chart/"
echo "   3. helm repo index . --url https://anuragvishwa.github.io/kgroot-latest/client-light/"
echo "   4. git add kg-rca-agent-2.1.0.tgz index.yaml helm-chart/"
echo "   5. git commit -m 'feat: Release kg-rca-agent v2.1.0 for Control Plane V2'"
echo "   6. git push"
echo ""
echo "🎯 Test installation:"
echo "   helm install kg-rca-agent anuragvishwa/kg-rca-agent \\"
echo "     --version 2.1.0 \\"
echo "     --namespace observability \\"
echo "     --set client.id='test-cluster' \\"
echo "     --set cluster.name='test-k8s' \\"
echo "     --set client.kafka.brokers='98.90.147.12:9092'"
