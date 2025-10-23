# Control Plane Manager

**Zero-touch multi-tenant observability with dynamic consumer spawning.**

## Overview

The Control Plane Manager automatically discovers Kubernetes clusters through Kafka topics and dynamically spawns/manages graph-builder containers for each cluster.

## Features

- **🚀 Zero-Touch Operations**: Helm install automatically spawns graph-builder
- **🧹 Auto-Cleanup**: Helm delete automatically removes graph-builder and consumer groups
- **💓 Heartbeat Monitoring**: Detects stale clusters (>2min) and dead clusters (>5min)
- **🔄 Self-Healing**: Automatically restarts crashed graph-builder containers
- **📊 Prometheus Metrics**: Exposes cluster and operation metrics
- **🔍 Audit Trail**: Logs all spawn/cleanup operations

## Architecture

```
Kubernetes Cluster (af-10)
  ├── helm install → cluster.registry (registration)
  ├── state-watcher → cluster.heartbeat (every 30s)
  └── helm delete → cluster.registry (tombstone)
                       ↓
            Control Plane Manager
              ├── Watches registry & heartbeats
              ├── Spawns graph-builder-af-10
              └── Cleans up when dead
                       ↓
               Docker Host / K8s
                 ├── kg-graph-builder-af-10
                 ├── kg-graph-builder-af-11
                 └── kg-graph-builder-af-12
```

## Kafka Topics

### cluster.registry (Compacted)

Clusters register themselves via Helm post-install hook:

```json
{
  "client_id": "af-10",
  "cluster_name": "prod-us-east",
  "version": "2.0.0",
  "registered_at": "2025-10-23T10:00:00Z",
  "metadata": {
    "namespace": "observability",
    "release_name": "kg-rca-agent"
  }
}
```

**Kafka Key**: `af-10` (client_id)

### cluster.heartbeat (1 Hour Retention)

State-watcher sends heartbeats every 30 seconds:

```json
{
  "client_id": "af-10",
  "timestamp": "2025-10-23T10:05:00Z",
  "status": "healthy",
  "metrics": {
    "resources_sent": 12345,
    "uptime_seconds": 3600
  }
}
```

**Kafka Key**: `af-10` (client_id)

## Reconciliation Loop

Every 30 seconds, the control plane:

1. **Check Heartbeats**
   - No heartbeat for >2min → Mark as "stale"
   - No heartbeat for >5min → Cleanup cluster

2. **Spawn Missing Graph-Builders**
   - If cluster has no graph-builder → Spawn new container
   - If container stopped → Respawn

3. **Cleanup Dead Clusters**
   - Stop graph-builder container
   - Delete Kafka consumer group
   - Remove from active clusters map

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BROKERS` | `kafka:9092` | Kafka bootstrap servers |
| `NEO4J_URI` | `neo4j://neo4j:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASS` | `password` | Neo4j password |
| `DOCKER_NETWORK` | `mini-server-prod_kg-network` | Docker network for spawned containers |
| `HEARTBEAT_TIMEOUT` | `2m` | Time before marking cluster as stale |
| `CLEANUP_TIMEOUT` | `5m` | Time before cleaning up dead cluster |
| `RECONCILE_INTERVAL` | `30s` | Reconciliation loop interval |
| `GRAPH_BUILDER_IMAGE` | `anuragvishwa/kg-graph-builder:1.0.20` | Graph-builder Docker image |
| `GB_MEMORY_LIMIT` | `256M` | Memory limit per graph-builder |
| `GB_CPU_LIMIT` | `0.5` | CPU limit per graph-builder |

## Building

```bash
# Build multi-arch image
docker buildx build --platform linux/amd64,linux/arm64 \
  -t anuragvishwa/kg-control-plane:1.0.0 \
  --push .
```

## Deployment

### Docker Compose

```yaml
kg-control-plane:
  image: anuragvishwa/kg-control-plane:1.0.0
  container_name: kg-control-plane
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
  environment:
    KAFKA_BROKERS: "kafka:9092"
    NEO4J_URI: "neo4j://neo4j:7687"
    NEO4J_USER: "neo4j"
    NEO4J_PASS: "password"
    DOCKER_NETWORK: "mini-server-prod_kg-network"
  ports:
    - "9090:9090"
  networks:
    - kg-network
  restart: unless-stopped
```

### Kubernetes

```yaml
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
        ports:
        - containerPort: 9090
          name: metrics
```

## Prometheus Metrics

Exposed on `:9090/metrics`:

```
# Clusters by status
kg_control_plane_clusters_total{status="active"} 5
kg_control_plane_clusters_total{status="stale"} 1
kg_control_plane_clusters_total{status="dead"} 0

# Operations
kg_control_plane_spawn_operations_total 12
kg_control_plane_cleanup_operations_total 7
```

## Lifecycle Examples

### New Cluster Deployed

```
10:00 helm install kg-rca-agent --set client.id="af-13"
10:00   → Post-install hook sends registration to cluster.registry
10:01 Control Plane sees new cluster in registry
10:01   → Spawns kg-graph-builder-af-13 container
10:01   → Container starts consuming from Kafka topics
10:02 State-watcher starts sending heartbeats
10:02   → Control Plane marks cluster as "active"
```

### Cluster Deleted

```
11:00 helm delete kg-rca-agent -n observability
11:00   → Pre-delete hook sends tombstone to cluster.registry
11:01 Control Plane sees tombstone
11:01   → Stops kg-graph-builder-af-13 container
11:01   → Deletes consumer group kg-builder-af-13
11:02 Cleanup complete
```

### Cluster Crash/Recovery

```
12:00 Kubernetes cluster crashes (network down)
12:00   → No more heartbeats received
12:02 Control Plane notices missing heartbeats (>2min)
12:02   → Marks cluster as "stale"
12:05 Still no heartbeats (>5min)
12:05   → Stops kg-graph-builder-af-13
12:05   → Keeps consumer group (in case cluster comes back)

12:30 Cluster recovers and sends heartbeat
12:30   → Control Plane sees heartbeat
12:30   → Respawns kg-graph-builder-af-13
12:31 Processing resumes from last committed offset
```

## Monitoring

### Check Control Plane Logs

```bash
docker logs -f kg-control-plane
```

### Check Active Clusters

```bash
# View registry
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic cluster.registry \
  --property print.key=true \
  --from-beginning

# View heartbeats
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic cluster.heartbeat \
  --property print.key=true
```

### Check Spawned Containers

```bash
docker ps | grep kg-graph-builder
```

### Check Prometheus Metrics

```bash
curl http://localhost:9090/metrics | grep kg_control_plane
```

## Troubleshooting

### Control Plane Not Starting

**Check Docker socket access:**
```bash
docker logs kg-control-plane
```

**Verify Kafka connection:**
```bash
docker exec kg-control-plane nc -zv kafka 9092
```

### Graph-Builder Not Spawning

**Check control plane logs:**
```bash
docker logs kg-control-plane | grep "Spawning graph-builder"
```

**Verify cluster registration:**
```bash
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic cluster.registry \
  --property print.key=true \
  --from-beginning
```

### Heartbeats Not Received

**Check state-watcher logs:**
```bash
kubectl logs -n observability deployment/kg-rca-agent-state-watcher | grep heartbeat
```

**Verify heartbeat topic:**
```bash
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic cluster.heartbeat \
  --property print.key=true
```

## Development

### Running Locally

```bash
# Set environment variables
export KAFKA_BROKERS=localhost:9092
export NEO4J_URI=neo4j://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASS=password
export DOCKER_NETWORK=bridge

# Run
go run main.go
```

### Testing

```bash
# Send test registration
echo "test-cluster:{\"client_id\":\"test-cluster\",\"cluster_name\":\"test\",\"version\":\"2.0.0\",\"registered_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" | \
  docker exec -i kg-kafka kafka-console-producer.sh \
    --bootstrap-server localhost:9092 \
    --topic cluster.registry \
    --property "parse.key=true" \
    --property "key.separator=:"

# Send test heartbeat
echo "test-cluster:{\"client_id\":\"test-cluster\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"status\":\"healthy\"}" | \
  docker exec -i kg-kafka kafka-console-producer.sh \
    --bootstrap-server localhost:9092 \
    --topic cluster.heartbeat \
    --property "parse.key=true" \
    --property "key.separator=:"

# Watch logs
docker logs -f kg-control-plane
```

## Related Documentation

- [CONTROL-PLANE-ARCHITECTURE.md](../CONTROL-PLANE-ARCHITECTURE.md) - Architecture design
- [AUTO-DISCOVERY-DESIGN.md](../AUTO-DISCOVERY-DESIGN.md) - Design alternatives
- [MULTI-TENANT-ARCHITECTURE.md](../MULTI-TENANT-ARCHITECTURE.md) - Multi-tenant overview

## License

Apache 2.0
