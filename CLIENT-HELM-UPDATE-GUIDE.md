# Client Helm Chart Update Guide for Control Plane V2

## Overview
This guide updates the `kg-rca-agent` Helm chart (version 2.0.2 → 2.1.0) to work with the new 13-topic Control Plane V2 architecture.

## Key Changes

### 1. Message Key Format
**OLD (V1)**: `event::abc123`
**NEW (V2)**: `{client-id}::event::abc123`

All Kafka producers must now include the client ID in the message key.

### 2. Topics Architecture
- **13 topics total** (vs 4 in V1)
- New topics: `cluster.registry`, `cluster.heartbeat`, `state.k8s.topology`, `state.prom.targets`, etc.

### 3. Control Plane Integration
- Client registers via `cluster.registry`
- Sends heartbeats to `cluster.heartbeat` every 30s
- Control plane auto-spawns per-client containers

## Files to Update

### File 1: Chart.yaml
**Location**: `client-light/helm-chart/Chart.yaml`

Update version to 2.1.0:
```yaml
version: 2.1.0
appVersion: "2.1.0"
```

Add to `artifacthub.io/changes`:
```yaml
  artifacthub.io/changes: |
    - kind: changed
      description: Updated for 13-topic Control Plane V2 architecture
    - kind: added
      description: Kafka message keys now include client ID prefix (client-id::type::id)
    - kind: added
      description: Support for state.k8s.topology and state.prom.targets topics
    - kind: changed
      description: Cluster registration and heartbeat integration
```

### File 2: values.yaml
**Location**: `client-light/helm-chart/values.yaml`

Key sections to update:

```yaml
client:
  id: "CHANGEME"  # MUST be unique per cluster
  kafka:
    brokers: "98.90.147.12:9092"  # Your control plane server

# Add new topics
topics:
  clusterRegistry: "cluster.registry"
  clusterHeartbeat: "cluster.heartbeat"
  stateTopology: "state.k8s.topology"
  stateTargets: "state.prom.targets"
  rawEvents: "raw.k8s.events"
  rawLogs: "raw.k8s.logs"

# Heartbeat configuration
heartbeat:
  enabled: true
  interval: "30s"
  topic: "cluster.heartbeat"
```

### File 3: Create cluster-registry Job
**Location**: `client-light/helm-chart/templates/cluster-registry-job.yaml`

```yaml
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
            echo '{{ .Values.client.id }}::{"client_id":"{{ .Values.client.id }}","cluster_name":"{{ .Values.cluster.name }}","region":"{{ .Values.cluster.region }}","timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","chart_version":"{{ .Chart.Version }}"}' | \
            kafka-console-producer \
              --bootstrap-server {{ .Values.client.kafka.brokers }} \
              --topic cluster.registry \
              --property "parse.key=true" \
              --property "key.separator=::"
```

### File 4: Create heartbeat CronJob
**Location**: `client-light/helm-chart/templates/heartbeat-cronjob.yaml`

```yaml
{{- if .Values.heartbeat.enabled }}
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
```

### File 5: Update Event Exporter ConfigMap
**Location**: `client-light/helm-chart/templates/event-exporter-configmap.yaml`

Add client ID to Kafka message keys:

```yaml
route:
  routes:
    - match:
        - receiver: "kafka"
receivers:
  - name: "kafka"
    kafka:
      brokers:
        - {{ .Values.client.kafka.brokers }}
      topic: {{ .Values.topics.rawEvents | default "raw.k8s.events" }}
      # KEY CHANGE: Add client ID prefix
      key: "{{ .Values.client.id }}::event::{{ .Event.InvolvedObject.Name }}-{{ .Event.InvolvedObject.UID | substr 0 8 }}"
```

### File 6: Update Vector ConfigMap
**Location**: `client-light/helm-chart/templates/vector-configmap.yaml`

Add client ID to log message keys:

```yaml
sinks:
  kafka:
    type: kafka
    inputs: ["kubernetes_logs"]
    bootstrap_servers: "{{ .Values.client.kafka.brokers }}"
    topic: {{ .Values.topics.rawLogs | default "raw.k8s.logs" }}
    # KEY CHANGE: Add client ID prefix
    key_field: "kafka_key"
    encoding:
      codec: json

transforms:
  add_kafka_key:
    type: remap
    inputs: ["kubernetes_logs"]
    source: |
      .kafka_key = "{{ .Values.client.id }}::log::" + uuid_v4()
```

## Testing Locally

### Step 1: Package the chart

```bash
cd /Users/anuragvishwa/Anurag/kgroot_latest/client-light

# Update Chart.yaml version to 2.1.0
# Make all the changes above

# Package the chart
helm package helm-chart/

# This creates: kg-rca-agent-2.1.0.tgz
```

### Step 2: Update Helm repo index

```bash
# Update index.yaml
helm repo index . --url https://anuragvishwa.github.io/kgroot-latest/client-light/

# Commit and push
git add kg-rca-agent-2.1.0.tgz index.yaml
git commit -m "feat: Release kg-rca-agent v2.1.0 for Control Plane V2"
git push
```

### Step 3: Test installation

```bash
# Add/update repo
helm repo add anuragvishwa https://anuragvishwa.github.io/kgroot-latest/client-light/
helm repo update

# Install with your server IP
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.1.0 \
  --namespace observability \
  --create-namespace \
  --set client.id="test-k8s-001" \
  --set cluster.name="test-cluster" \
  --set client.kafka.brokers="98.90.147.12:9092"
```

## Verification Steps

After installation:

### 1. Check pods are running
```bash
kubectl get pods -n observability
```

### 2. Check registration job succeeded
```bash
kubectl get jobs -n observability
kubectl logs job/kg-rca-agent-registry -n observability
```

### 3. On control plane server, verify client registered
```bash
docker logs kg-control-plane --tail 50
# Should see: "📋 New client registered: test-k8s-001"
```

### 4. Check containers spawned
```bash
docker ps | grep test-k8s-001
# Should see 3 containers:
# - kg-event-normalizer-test-k8s-001
# - kg-log-normalizer-test-k8s-001
# - kg-graph-builder-test-k8s-001
```

### 5. Check heartbeat is working
```bash
kubectl logs cronjob/kg-rca-agent-heartbeat -n observability
```

## Quick Install Command

After publishing, clients can install with:

```bash
# Install Prometheus (if not already installed)
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace

# Install KG RCA Agent v2.1.0
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.1.0 \
  --namespace observability \
  --set client.id="YOUR-UNIQUE-ID" \
  --set cluster.name="YOUR-CLUSTER-NAME" \
  --set client.kafka.brokers="98.90.147.12:9092"
```

## Next Steps

1. Update the Helm chart files as described above
2. Test locally with a test Kubernetes cluster
3. Package and publish to GitHub Pages
4. Update documentation with new installation command
5. Test with real client cluster

Would you like me to create a script that automates all these updates?
