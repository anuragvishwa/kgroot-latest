# Control Plane Architecture - Dynamic Consumer Spawning

## The Big Idea 💡

**Instead of:**
- Manual graph-builder deployment per cluster
- OR single graph-builder for all clusters

**We create:**
- **Control Plane** that watches for new clusters
- **Auto-spawns** graph-builder containers dynamically
- **Auto-cleans up** when clusters disappear
- **Self-healing** multi-tenant system!

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Kafka Cluster                            │
│                                                             │
│  Regular Topics:              Control Topic:                │
│  - events.normalized          - cluster.registry ← NEW!    │
│  - logs.normalized            - cluster.heartbeat ← NEW!   │
│  - state.k8s.resource                                       │
└──────────────────┬────────────────────────┬─────────────────┘
                   │                        │
                   │                        │ (watches)
                   │                        │
                   │              ┌─────────▼──────────────┐
                   │              │  Control Plane Manager │
                   │              │  (New Component!)      │
                   │              │                        │
                   │              │  - Watches registry    │
                   │              │  - Spawns consumers    │
                   │              │  - Monitors health     │
                   │              │  - Auto-cleanup        │
                   │              └─────────┬──────────────┘
                   │                        │
                   │                        │ (spawns/kills)
                   │                        │
                   ↓                        ↓
    ┌──────────────────────────────────────────────────┐
    │         Docker Host / Kubernetes                 │
    │                                                  │
    │  ┌──────────────┐  ┌──────────────┐            │
    │  │ Graph-Builder│  │ Graph-Builder│  (dynamic) │
    │  │   af-10      │  │   af-11      │            │
    │  └──────────────┘  └──────────────┘            │
    │                                                  │
    │  ┌──────────────┐                               │
    │  │ Graph-Builder│  (auto-spawned)               │
    │  │   af-12      │                               │
    │  └──────────────┘                               │
    └──────────────────────────────────────────────────┘
```

---

## New Kafka Topics

### 1. `cluster.registry` (Cluster Registration)

**Purpose:** Clusters announce their presence and configuration

**Message Format:**
```json
{
  "client_id": "af-10",
  "cluster_name": "prod-us-east",
  "version": "1.0.47",
  "registered_at": "2025-10-23T10:00:00Z",
  "metadata": {
    "region": "us-east-1",
    "environment": "production",
    "contact": "ops@company.com"
  }
}
```

**Kafka Key:** `af-10` (client_id)
**Retention:** Compacted (keeps latest registration per cluster)

**Who Sends:**
- Helm post-install hook (one-time registration)
- State-watcher (periodic re-registration every 5 minutes)

### 2. `cluster.heartbeat` (Liveness Detection)

**Purpose:** Clusters send heartbeats to prove they're alive

**Message Format:**
```json
{
  "client_id": "af-10",
  "timestamp": "2025-10-23T10:05:00Z",
  "status": "healthy",
  "metrics": {
    "events_sent": 12345,
    "logs_sent": 67890,
    "resources_sent": 4567
  }
}
```

**Kafka Key:** `af-10` (client_id)
**Retention:** 1 hour (recent heartbeats only)

**Who Sends:**
- State-watcher (every 30 seconds)
- Vector (piggyback on log batches)
- Event-exporter (piggyback on event batches)

---

## Control Plane Manager (New Component)

### Core Responsibilities

```go
type ControlPlane struct {
    docker        *docker.Client
    kafka         sarama.Client
    neo4j         *neo4j.Driver

    // Tracks active clusters
    clusters      map[string]*ClusterInfo

    // Tracks spawned consumers
    consumers     map[string]*ConsumerProcess
}

type ClusterInfo struct {
    ClientID          string
    Name              string
    RegisteredAt      time.Time
    LastHeartbeat     time.Time
    Status            string // "active", "stale", "dead"
    GraphBuilderID    string // Docker container ID
}

type ConsumerProcess struct {
    ClientID      string
    ContainerID   string
    StartedAt     time.Time
    Status        string
    RestartCount  int
}
```

### Main Loop

```go
func (cp *ControlPlane) Run() {
    // 1. Watch cluster.registry topic
    go cp.WatchRegistry()

    // 2. Watch cluster.heartbeat topic
    go cp.WatchHeartbeats()

    // 3. Reconcile loop (every 30 seconds)
    ticker := time.NewTicker(30 * time.Second)
    for range ticker.C {
        cp.Reconcile()
    }
}

func (cp *ControlPlane) Reconcile() {
    // For each registered cluster:
    for clientID, cluster := range cp.clusters {

        // Check if heartbeat is stale (> 2 minutes)
        if time.Since(cluster.LastHeartbeat) > 2*time.Minute {
            cluster.Status = "stale"
        }

        // If dead (> 5 minutes), cleanup
        if time.Since(cluster.LastHeartbeat) > 5*time.Minute {
            cp.CleanupCluster(clientID)
            continue
        }

        // Check if graph-builder exists
        if cluster.GraphBuilderID == "" {
            // Spawn new graph-builder!
            cp.SpawnGraphBuilder(clientID)
        } else {
            // Verify it's still running
            if !cp.IsContainerRunning(cluster.GraphBuilderID) {
                // Restart it
                cp.SpawnGraphBuilder(clientID)
            }
        }
    }
}
```

### Spawn Graph-Builder

```go
func (cp *ControlPlane) SpawnGraphBuilder(clientID string) error {
    log.Printf("Spawning graph-builder for cluster: %s", clientID)

    container, err := cp.docker.ContainerCreate(ctx, &container.Config{
        Image: "anuragvishwa/kg-graph-builder:1.0.21",
        Env: []string{
            fmt.Sprintf("CLIENT_ID=%s", clientID),
            fmt.Sprintf("KAFKA_GROUP=kg-builder-%s", clientID),
            "KAFKA_BROKERS=kafka:9092",
            "NEO4J_URI=neo4j://neo4j:7687",
            "NEO4J_USER=neo4j",
            "NEO4J_PASS=password",
        },
    }, &container.HostConfig{
        NetworkMode: "mini-server-prod_kg-network",
        RestartPolicy: container.RestartPolicy{
            Name: "unless-stopped",
        },
        Resources: container.Resources{
            Memory: 256 * 1024 * 1024, // 256MB
            NanoCPUs: 500000000,       // 0.5 CPU
        },
    }, nil, nil, fmt.Sprintf("kg-graph-builder-%s", clientID))

    if err != nil {
        return err
    }

    if err := cp.docker.ContainerStart(ctx, container.ID, types.ContainerStartOptions{}); err != nil {
        return err
    }

    // Update cluster info
    cp.clusters[clientID].GraphBuilderID = container.ID
    cp.consumers[clientID] = &ConsumerProcess{
        ClientID:    clientID,
        ContainerID: container.ID,
        StartedAt:   time.Now(),
        Status:      "running",
    }

    log.Printf("✅ Spawned graph-builder-%s (container: %s)", clientID, container.ID[:12])
    return nil
}
```

### Cleanup Dead Clusters

```go
func (cp *ControlPlane) CleanupCluster(clientID string) error {
    log.Printf("Cleaning up dead cluster: %s", clientID)

    cluster := cp.clusters[clientID]

    // 1. Stop graph-builder container
    if cluster.GraphBuilderID != "" {
        log.Printf("Stopping container: %s", cluster.GraphBuilderID)
        cp.docker.ContainerStop(ctx, cluster.GraphBuilderID, nil)
        cp.docker.ContainerRemove(ctx, cluster.GraphBuilderID, types.ContainerRemoveOptions{})
    }

    // 2. Delete Kafka consumer group
    log.Printf("Deleting consumer group: kg-builder-%s", clientID)
    admin, _ := sarama.NewClusterAdmin([]string{"kafka:9092"}, nil)
    admin.DeleteConsumerGroup(fmt.Sprintf("kg-builder-%s", clientID))

    // 3. (Optional) Archive Neo4j data
    log.Printf("Archiving Neo4j data for: %s", clientID)
    // Could move to separate database, export to S3, etc.

    // 4. Remove from active clusters
    delete(cp.clusters, clientID)
    delete(cp.consumers, clientID)

    log.Printf("✅ Cleaned up cluster: %s", clientID)
    return nil
}
```

---

## Client-Side Changes (Minimal!)

### 1. Helm Post-Install Hook

Add a Job that registers the cluster:

```yaml
# client-light/helm-chart/templates/register-cluster-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "kg-rca-agent.fullname" . }}-register-cluster
  annotations:
    "helm.sh/hook": post-install
    "helm.sh/hook-weight": "1"
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: register
        image: confluentinc/cp-kafka:latest
        command:
        - /bin/bash
        - -c
        - |
          echo "Registering cluster {{ .Values.client.id }}..."

          cat <<EOF | kafka-console-producer \
            --bootstrap-server {{ .Values.client.kafka.brokers }} \
            --topic cluster.registry \
            --property "parse.key=true" \
            --property "key.separator=:"
          {{ .Values.client.id }}:{"client_id":"{{ .Values.client.id }}","cluster_name":"{{ .Values.cluster.name | default .Values.client.id }}","version":"{{ .Chart.Version }}","registered_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","metadata":{"namespace":"{{ .Release.Namespace }}"}}
          EOF

          echo "✅ Cluster registered!"
```

### 2. State-Watcher Heartbeat

Add heartbeat to existing state-watcher:

```go
// In kg-state-watcher

func (w *Watcher) SendHeartbeat() {
    ticker := time.NewTicker(30 * time.Second)
    for range ticker.C {
        msg := &sarama.ProducerMessage{
            Topic: "cluster.heartbeat",
            Key:   sarama.StringEncoder(w.clientID),
            Value: sarama.StringEncoder(fmt.Sprintf(`{
                "client_id": "%s",
                "timestamp": "%s",
                "status": "healthy",
                "metrics": {
                    "resources_sent": %d,
                    "uptime_seconds": %d
                }
            }`, w.clientID, time.Now().Format(time.RFC3339), w.messagesSent, int(time.Since(w.startTime).Seconds()))),
        }
        w.producer.SendMessage(msg)
    }
}
```

### 3. Helm Pre-Delete Hook

Add a Job that deregisters the cluster:

```yaml
# client-light/helm-chart/templates/deregister-cluster-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "kg-rca-agent.fullname" . }}-deregister-cluster
  annotations:
    "helm.sh/hook": pre-delete
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: deregister
        image: confluentinc/cp-kafka:latest
        command:
        - /bin/bash
        - -c
        - |
          echo "Deregistering cluster {{ .Values.client.id }}..."

          # Send tombstone (null value) to remove from registry
          echo "{{ .Values.client.id }}:" | kafka-console-producer \
            --bootstrap-server {{ .Values.client.kafka.brokers }} \
            --topic cluster.registry \
            --property "parse.key=true" \
            --property "key.separator=:" \
            --property "null.marker="

          echo "✅ Cluster deregistered!"
```

---

## Control Plane Deployment

### Docker Compose

```yaml
# docker-compose.yml on mini-server
version: '3.8'

services:
  # ... existing services (kafka, neo4j, etc.)

  # NEW: Control Plane Manager
  kg-control-plane:
    build: ./control-plane
    image: anuragvishwa/kg-control-plane:1.0.0
    container_name: kg-control-plane
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # Docker API access
    environment:
      KAFKA_BROKERS: "kafka:9092"
      NEO4J_URI: "neo4j://neo4j:7687"
      NEO4J_USER: "neo4j"
      NEO4J_PASS: "password"
      DOCKER_NETWORK: "mini-server-prod_kg-network"

      # Reconciliation settings
      HEARTBEAT_TIMEOUT: "2m"       # Mark stale after 2min
      CLEANUP_TIMEOUT: "5m"          # Cleanup after 5min
      RECONCILE_INTERVAL: "30s"      # Check every 30s

      # Resource limits per graph-builder
      GB_MEMORY_LIMIT: "256M"
      GB_CPU_LIMIT: "0.5"
    networks:
      - kg-network
    restart: unless-stopped
    depends_on:
      - kafka
      - neo4j
```

### Kubernetes Deployment (Alternative)

```yaml
# For running control-plane in Kubernetes
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kg-control-plane
spec:
  replicas: 1
  template:
    spec:
      serviceAccountName: kg-control-plane
      containers:
      - name: control-plane
        image: anuragvishwa/kg-control-plane:1.0.0
        env:
        - name: KAFKA_BROKERS
          value: "kafka.example.com:9092"
        - name: K8S_MODE
          value: "true"  # Deploy as K8s Jobs instead of Docker containers
```

---

## Lifecycle Examples

### Scenario 1: New Cluster Deployed

```
Time  Event
----  -----
10:00 helm install kg-rca-agent --set client.id="af-13"
10:00   → Post-install hook sends registration to cluster.registry
10:01 Control Plane sees new cluster in registry
10:01   → Spawns kg-graph-builder-af-13 container
10:01   → Container starts consuming from Kafka topics
10:02 State-watcher starts sending heartbeats
10:02   → Control Plane marks cluster as "active"

Result: ✅ Fully automated cluster onboarding!
```

### Scenario 2: Cluster Deleted

```
Time  Event
----  -----
11:00 helm delete kg-rca-agent -n observability
11:00   → Pre-delete hook sends tombstone to cluster.registry
11:01 Control Plane sees tombstone
11:01   → Stops kg-graph-builder-af-13 container
11:01   → Deletes consumer group kg-builder-af-13
11:01   → Archives Neo4j data (optional)
11:02 Cleanup complete

Result: ✅ Fully automated cluster cleanup!
```

### Scenario 3: Cluster Crash/Network Partition

```
Time  Event
----  -----
12:00 Kubernetes cluster crashes (network down)
12:00   → No more heartbeats received
12:02 Control Plane notices missing heartbeats (>2min)
12:02   → Marks cluster as "stale"
12:05 Still no heartbeats (>5min)
12:05   → Stops kg-graph-builder-af-13
12:05   → Keeps consumer group (in case cluster comes back)
12:05   → Keeps Neo4j data

12:30 Cluster recovers and sends heartbeat
12:30   → Control Plane sees heartbeat
12:30   → Respawns kg-graph-builder-af-13
12:31 Processing resumes from last committed offset

Result: ✅ Self-healing system!
```

---

## Benefits

### 1. Zero-Touch Operations

**Before (Manual):**
```bash
# Deploy cluster
helm install kg-rca-agent --set client.id="af-13"

# SSH to mini-server
ssh mini-server

# Manually start graph-builder
docker run -d \
  --name kg-graph-builder-af-13 \
  -e CLIENT_ID=af-13 \
  ...

# Delete cluster
helm delete kg-rca-agent

# SSH to mini-server again
ssh mini-server

# Manually cleanup
docker stop kg-graph-builder-af-13
docker rm kg-graph-builder-af-13
kafka-consumer-groups.sh --delete --group kg-builder-af-13
```

**After (Automated):**
```bash
# Deploy cluster
helm install kg-rca-agent --set client.id="af-13"
# ✅ DONE! Graph-builder auto-spawned

# Delete cluster
helm delete kg-rca-agent
# ✅ DONE! Everything auto-cleaned up
```

### 2. Self-Healing

- Graph-builder crashes → Auto-restarts
- Cluster goes down → Auto-marks stale
- Cluster comes back → Auto-resumes
- Network partition → Auto-recovers

### 3. Observability

Control Plane provides metrics:

```
# Prometheus metrics exposed by control-plane
kg_control_plane_clusters_total{status="active"}   5
kg_control_plane_clusters_total{status="stale"}    1
kg_control_plane_clusters_total{status="dead"}     0

kg_control_plane_graph_builders_total              5
kg_control_plane_spawn_operations_total            12
kg_control_plane_cleanup_operations_total          7
```

### 4. Cost Efficiency

- Only runs graph-builders for active clusters
- Auto-stops for dead clusters
- Resource limits prevent runaway containers

### 5. Audit Trail

All operations logged to separate topic:

```json
// cluster.audit topic
{
  "timestamp": "2025-10-23T12:05:00Z",
  "action": "cleanup_cluster",
  "client_id": "af-13",
  "reason": "heartbeat_timeout",
  "details": {
    "last_heartbeat": "2025-10-23T12:00:00Z",
    "container_stopped": "kg-graph-builder-af-13",
    "consumer_group_deleted": "kg-builder-af-13"
  }
}
```

---

## Implementation Complexity

### Control Plane (New Code)

**Lines of Code:** ~500-800 lines

**Components:**
1. Kafka consumer (registry + heartbeat topics)
2. Docker API client
3. Reconciliation loop
4. Spawn/cleanup logic
5. Metrics exporter

**Effort:** 2-3 days development + 2 days testing

### Client-Side Changes (Minimal)

1. Add post-install hook (10 lines YAML)
2. Add pre-delete hook (10 lines YAML)
3. Add heartbeat to state-watcher (20 lines Go)

**Effort:** 2-3 hours

### Kafka Topics (New)

1. `cluster.registry` (compacted)
2. `cluster.heartbeat` (1 hour retention)
3. `cluster.audit` (7 days retention, optional)

**Effort:** 1 hour

---

## Comparison with Other Options

| Feature | Manual (v1.0.47) | Single GB (v1.1.0) | Control Plane (v2.0.0) |
|---------|------------------|--------------------|-----------------------|
| Auto-Discovery | ❌ | ✅ | ✅ |
| Auto-Cleanup | ❌ | ❌ | ✅ |
| Self-Healing | ❌ | ⚠️ Partial | ✅ |
| Isolated Failures | ✅ | ❌ | ✅ |
| Resource Efficient | ⚠️ | ✅ | ✅ |
| Zero-Touch Ops | ❌ | ⚠️ Partial | ✅ |
| Observability | ❌ | ⚠️ Limited | ✅ |
| Audit Trail | ❌ | ❌ | ✅ |
| Complexity | Low | Low | Medium |
| Development Effort | 0 days | 1 day | 4-5 days |

---

## Next Steps

### Phase 1: Proof of Concept (1 week)

1. Build basic control-plane (spawn + cleanup only)
2. Add cluster.registry topic
3. Test with 2 clusters (af-10, af-11)
4. Verify auto-spawn works

### Phase 2: Heartbeat + Self-Healing (1 week)

1. Add cluster.heartbeat topic
2. Implement heartbeat in state-watcher
3. Add staleness detection
4. Test recovery scenarios

### Phase 3: Production Hardening (1 week)

1. Add metrics/monitoring
2. Add audit logging
3. Handle edge cases
4. Load testing with 50 clusters

### Phase 4: Release v2.0.0 (1 week)

1. Documentation
2. Migration guide
3. Helm chart updates
4. Docker Hub publishing

**Total:** ~4 weeks to production-ready v2.0.0

---

## Alternative: Hybrid Approach

Keep it simple but add cluster registry:

1. ✅ Add `cluster.registry` topic
2. ✅ Auto-register on Helm install
3. ✅ Script to list all clusters
4. ⚠️ Manual graph-builder spawn (but you know which clusters exist!)
5. ✅ Script to cleanup dead clusters

**Effort:** 1 day
**Benefit:** Visibility without full automation

---

## Decision Time!

**Option A:** Keep v1.0.47 (manual, works great)
**Option B:** Implement v1.1.0 (single graph-builder, auto-discovery via Kafka key)
**Option C:** Implement v2.0.0 (control plane, full automation) ⭐
**Option D:** Hybrid (cluster registry + manual spawn)

What do you think? The control plane approach is the most "out of the box" and provides true zero-touch operations! 🚀
