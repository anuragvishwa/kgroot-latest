# Environment Configuration Migration Guide

## Overview

All services now use a **unified `.env` configuration** instead of manually exporting environment variables. This ensures consistency, makes deployment easier, and follows best practices.

## What Changed

### Before (Manual Environment Variables)

```bash
# Had to export variables manually before running each service
export KAFKA_BOOTSTRAP=kafka.observability.svc:9092
export NEO4J_URI=neo4j://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASS=anuragvishwa
# ... and many more
```

### After (Unified .env File)

```bash
# Single .env file at project root
# All services read from Kubernetes ConfigMap: kgroot-env
# No manual exports needed!
```

## File Structure

```
kgroot_latest/
├── .env                          # ✨ NEW: Unified configuration
├── README.md                     # ✨ NEW: Complete documentation
├── KGROOT_RCA_IMPROVEMENTS.md    # ✨ NEW: Accuracy improvements
├── ENV_MIGRATION_GUIDE.md        # ✨ THIS FILE
├── deploy-all.sh                 # ✨ NEW: One-command deployment
│
├── kg/
│   ├── graph-builder.go          # No changes (already uses getenv)
│   ├── Dockerfile                # ✨ UPDATED: Handles missing go.sum
│   ├── build-and-deploy.sh       # ✨ NEW: Build script
│   └── go.mod
│
├── k8s/
│   ├── kafka.yaml                # No changes
│   ├── vector-configmap.yaml     # No changes
│   ├── state-watcher.yaml        # ✨ UPDATED: Uses ConfigMap
│   ├── alerts-enricher.yaml      # ✨ UPDATED: Uses ConfigMap
│   ├── kg-builder.yaml           # ✨ NEW: Deployment + ConfigMap
│   └── neo4j.yaml                # ✨ NEW: Neo4j deployment
│
├── alerts-enricher/
│   └── (existing files)          # No changes
│
└── scripts/
    └── kafka-init.sh             # No changes
```

## Configuration Mapping

### Kubernetes ConfigMap: `kgroot-env`

All services now load configuration from the `kgroot-env` ConfigMap in the `observability` namespace.

**Location**: `k8s/kg-builder.yaml` (lines 5-51)

**Contents**:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kgroot-env
  namespace: observability
data:
  CLUSTER_NAME: "minikube"
  KAFKA_BROKERS: "kafka.observability.svc:9092"
  NEO4J_URI: "neo4j://neo4j.observability.svc:7687"
  NEO4J_USER: "neo4j"
  NEO4J_PASS: "anuragvishwa"
  # ... all other config values
```

### Service Integration

#### 1. kg-builder (graph-builder.go)

**Before**:
```bash
export KAFKA_BROKERS=kafka:9092
export NEO4J_URI=neo4j://neo4j:7687
export NEO4J_USER=neo4j
export NEO4J_PASS=anuragvishwa
./graph-builder
```

**After**:
```yaml
# In k8s/kg-builder.yaml
spec:
  containers:
    - name: kg-builder
      image: anuragvishwa/kg-builder:latest
      envFrom:
        - configMapRef:
            name: kgroot-env  # ✨ Loads all variables automatically
```

**Code** (graph-builder.go):
```go
// No changes needed! Already uses getenv()
brokers := strings.Split(getenv("KAFKA_BROKERS", "localhost:9092"), ",")
neo4jURI := getenv("NEO4J_URI", "neo4j://localhost:7687")
neo4jUser := getenv("NEO4J_USER", "neo4j")
neo4jPass := getenv("NEO4J_PASS", "password")
```

#### 2. state-watcher

**Before**:
```yaml
env:
  - name: CLUSTER_NAME
    value: "minikube"
  - name: KAFKA_BOOTSTRAP
    value: "kafka.observability.svc:9092"
  # ... many more hardcoded values
```

**After**:
```yaml
envFrom:
  - configMapRef:
      name: kgroot-env  # ✨ All values from ConfigMap
env:
  # Override specific values if needed
  - name: TOPIC_STATE
    valueFrom:
      configMapKeyRef:
        name: kgroot-env
        key: TOPIC_STATE_RESOURCE
```

**Changes**: `k8s/state-watcher.yaml` lines 60-74

#### 3. alerts-enricher

**Before**:
```yaml
env:
  - name: KAFKA_BROKERS
    value: "kafka.observability.svc:9092"
  - name: INPUT_TOPIC
    value: "events.normalized"
  # ... hardcoded values
```

**After**:
```yaml
envFrom:
  - configMapRef:
      name: kgroot-env  # ✨ All values from ConfigMap
env:
  # Override only what's different
  - name: KAFKA_GROUP
    value: "alerts-enricher-alerts"
```

**Changes**: `k8s/alerts-enricher.yaml` lines 25-51

## How to Use .env Configuration

### For Local Development (Docker Compose)

```bash
# Load .env file automatically
docker-compose up

# Docker Compose reads .env by default
# No manual exports needed!
```

### For Kubernetes Deployment

```bash
# Option 1: Use deploy-all.sh (recommended)
./deploy-all.sh

# Option 2: Manual deployment
kubectl apply -f k8s/kg-builder.yaml  # Creates ConfigMap
kubectl apply -f k8s/state-watcher.yaml
kubectl apply -f k8s/alerts-enricher.yaml
# ... etc
```

### Updating Configuration

#### Update ConfigMap
```bash
# Edit the ConfigMap
kubectl edit configmap kgroot-env -n observability

# Or update from .env file
kubectl create configmap kgroot-env --from-env-file=.env \
  -n observability --dry-run=client -o yaml | kubectl apply -f -
```

#### Restart Pods to Pick Up Changes
```bash
kubectl rollout restart deployment/kg-builder -n observability
kubectl rollout restart deployment/state-watcher -n observability
kubectl rollout restart deployment/alerts-enricher -n observability
```

## Configuration Categories

### 1. Cluster Configuration
```bash
CLUSTER_NAME=minikube
```

### 2. Kafka Configuration
```bash
KAFKA_BROKERS=kafka.observability.svc:9092
KAFKA_BOOTSTRAP=kafka.observability.svc:9092
KAFKA_GROUP=kg-builder
```

### 3. Neo4j Configuration
```bash
NEO4J_URI=neo4j://neo4j.observability.svc:7687
NEO4J_USER=neo4j
NEO4J_PASS=anuragvishwa
```

### 4. Prometheus Configuration
```bash
PROM_URL=http://prometheus-kube-prometheus-prometheus.monitoring.svc:9090
PROM_SCRAPE_INTERVAL=30s
```

### 5. Kafka Topics
```bash
# Raw streams
TOPIC_RAW_LOGS=raw.k8s.logs
TOPIC_RAW_EVENTS=raw.k8s.events
TOPIC_RAW_PROM_ALERTS=raw.prom.alerts

# Normalized
TOPIC_EVENTS_NORMALIZED=events.normalized
TOPIC_LOGS_NORMALIZED=logs.normalized
TOPIC_ALERTS_NORMALIZED=alerts.normalized
TOPIC_ALERTS_ENRICHED=alerts.enriched

# State (compacted)
TOPIC_STATE_RESOURCE=state.k8s.resource
TOPIC_STATE_TOPOLOGY=state.k8s.topology
TOPIC_STATE_PROM_TARGETS=state.prom.targets
TOPIC_STATE_PROM_RULES=state.prom.rules
```

### 6. RCA Configuration
```bash
RCA_WINDOW_MIN=15                    # Causal link time window
CAUSAL_LINK_MAX_HOPS=3               # Max graph distance
CAUSAL_LINK_TIME_THRESHOLD_SEC=300   # 5 minutes
EVENT_CORRELATION_WINDOW_SEC=60      # Event deduplication
```

### 7. Feature Flags
```bash
ENABLE_LOG_FILTERING=true            # High-signal logs only
ENABLE_FPG_REALTIME=true             # Fault propagation graph
ENABLE_FEKG_HISTORICAL=true          # Historical patterns
ENABLE_TEMPORAL_SNAPSHOTS=true       # Graph snapshots
ENABLE_GCN_SIMILARITY=false          # ML-based similarity (future)
```

### 8. Graph Pruning
```bash
PRUNE_OLD_EVENTS_DAYS=30             # Delete old events
PRUNE_RESOLVED_INCIDENTS_DAYS=7      # Archive resolved incidents
```

## Benefits of Unified .env

### ✅ Consistency
- All services use same configuration source
- No duplicate/conflicting values
- Easy to audit and verify

### ✅ Maintainability
- Single file to update
- Clear documentation of all settings
- Version controlled with code

### ✅ Deployment Simplicity
- No manual variable exports
- Works with docker-compose and Kubernetes
- ConfigMap auto-loaded by all pods

### ✅ Security
- Sensitive values (passwords) in one place
- Easy to migrate to Kubernetes Secrets
- Can use external secret managers

### ✅ Flexibility
- Override per-service as needed
- Support multiple environments (dev/staging/prod)
- Feature flags for gradual rollout

## Migration Checklist

- [x] Create `.env` file at project root
- [x] Create `kgroot-env` ConfigMap in `k8s/kg-builder.yaml`
- [x] Update `k8s/state-watcher.yaml` to use ConfigMap
- [x] Update `k8s/alerts-enricher.yaml` to use ConfigMap
- [x] Update `kg/Dockerfile` to handle missing go.sum
- [x] Create `kg/build-and-deploy.sh`
- [x] Create `k8s/neo4j.yaml` deployment
- [x] Create `deploy-all.sh` for automated deployment
- [x] Update `README.md` with new deployment instructions
- [x] Create `KGROOT_RCA_IMPROVEMENTS.md` for accuracy guide
- [x] Create this migration guide

## Troubleshooting

### ConfigMap Not Found

```bash
# Verify ConfigMap exists
kubectl get configmap kgroot-env -n observability

# If missing, create it
kubectl apply -f k8s/kg-builder.yaml
```

### Pods Not Picking Up Config

```bash
# Check pod environment variables
kubectl exec -n observability kg-builder-xxx -- env | grep KAFKA

# Restart pods to reload ConfigMap
kubectl rollout restart deployment/kg-builder -n observability
```

### Different Values in Dev vs. Prod

```bash
# Create environment-specific ConfigMaps
kubectl create configmap kgroot-env-prod --from-env-file=.env.prod -n observability
kubectl create configmap kgroot-env-dev --from-env-file=.env.dev -n observability

# Reference the appropriate ConfigMap in deployment
envFrom:
  - configMapRef:
      name: kgroot-env-prod  # or kgroot-env-dev
```

## Next Steps

1. **Review** `.env` file and adjust values for your environment
2. **Deploy** using `./deploy-all.sh` or manually
3. **Verify** all services are using ConfigMap: `kubectl get pods -n observability`
4. **Test** by updating a config value and restarting a service
5. **Read** `KGROOT_RCA_IMPROVEMENTS.md` for accuracy optimization

## Questions?

See `README.md` for full documentation or check individual component READMEs.
