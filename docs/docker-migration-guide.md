# Docker vs Minikube Migration Guide

## Current Architecture Overview

### ✅ Already in Docker (Keep as-is)
- **Kafka + Zookeeper** - Message broker
- **Neo4j** - Graph database
- **Kafka-UI** - Web interface for Kafka
- **graph-builder** (kg) - Builds knowledge graph from Kafka events

### 🔄 Migration Candidates

| Service | Current | Recommendation | Reason |
|---------|---------|----------------|---------|
| **state-watcher** | Minikube | ❌ **Keep in Minikube** | Uses K8s API (client-go) to watch pods, services, deployments |
| **alerts-enricher** | Minikube | ✅ **Move to Docker** | Only uses Kafka topics, no K8s dependencies |
| **kg-init** | Minikube | ✅ **Move to Docker** | Just Neo4j schema initialization |

---

## Why state-watcher Must Stay in Minikube

The `state-watcher` service:
- Uses `k8s.io/client-go` to create Kubernetes informers
- Watches K8s resources: Pods, Services, Deployments, ReplicaSets, DaemonSets, Jobs
- Fetches Prometheus targets from in-cluster Prometheus
- Requires in-cluster ServiceAccount RBAC permissions

**Moving it to Docker would require:**
- External kubeconfig access (less secure)
- Network access to cluster services
- Additional complexity for no real benefit

---

## Option 1: Minimal Migration (Recommended for Simplicity)

**Keep everything as-is.** Your Docker setup handles data layer, Minikube handles K8s-aware services.

### Benefits
✅ Clear separation: Docker = data, Minikube = K8s watchers
✅ No migration work needed
✅ state-watcher has proper RBAC and cluster access

### When to use
- You're comfortable with current setup
- You want to minimize changes
- Minikube is running reliably

---

## Option 2: Move alerts-enricher to Docker

**Move only alerts-enricher** since it's purely Kafka-based.

### Steps

#### 1. Add alerts-enricher to docker-compose.yml

```yaml
services:
  # ... existing services (kafka, neo4j, etc.) ...

  alerts-enricher:
    build: ./alerts-enricher
    depends_on:
      kafka:
        condition: service_healthy
    environment:
      KAFKA_BROKERS: kafka:9092
      KAFKA_GROUP: alerts-enricher
      INPUT_TOPIC: events.normalized
      OUTPUT_TOPIC: alerts.enriched
      STATE_RESOURCE_TOPIC: state.k8s.resource
      STATE_TOPOLOGY_TOPIC: state.k8s.topology
    restart: unless-stopped
```

#### 2. Build and run

```bash
docker-compose up -d alerts-enricher
```

#### 3. Remove from Minikube

```bash
kubectl delete deployment alerts-enricher -n observability
```

### Benefits
✅ One less pod in minikube
✅ alerts-enricher near Kafka (lower latency)
✅ Easier to develop/debug locally

---

## Option 3: Hybrid with kg-init in Docker

Add Neo4j schema initialization to docker-compose.

### Add kg-init to docker-compose.yml

```yaml
services:
  # ... existing services ...

  kg-init:
    build: ./kg  # same image as graph-builder
    depends_on:
      neo4j:
        condition: service_started
    environment:
      NEO4J_URI: neo4j://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASS: anuragvishwa
    command: ["/bin/sh", "-c", "sleep 10 && /app/kg-init && echo 'Schema initialized'"]
    restart: "no"  # Run once and exit
```

**Note:** You'll need to ensure kg-init script exists in your kg/ directory or adjust the command.

---

## Network Configuration

### Docker → Minikube Communication

For services in Docker to talk to services in Minikube:

```yaml
# In docker-compose.yml, use host.minikube.internal
environment:
  PROMETHEUS_URL: http://host.minikube.internal:9090
```

### Minikube → Docker Communication

For Minikube pods to access Docker Kafka:

```yaml
# In k8s deployments, use host.minikube.internal:29092
KAFKA_BROKERS: host.minikube.internal:29092
```

**Your docker-compose.yml already exposes this correctly:**
```yaml
kafka:
  ports:
    - "29092:29092"  # For K8s pods
  environment:
    KAFKA_CFG_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,PLAINTEXT_HOST://host.minikube.internal:29092
```

---

## Updated state-watcher Configuration (If Kafka in Docker)

If you keep state-watcher in Minikube but Kafka in Docker:

```yaml
# k8s/state-watcher.yaml
env:
  - name: KAFKA_BROKERS
    value: "host.minikube.internal:29092"  # Changed from kafka.observability.svc:9092
```

Apply:
```bash
kubectl set env deployment/state-watcher -n observability KAFKA_BROKERS=host.minikube.internal:29092
kubectl rollout restart deployment/state-watcher -n observability
```

---

## Testing the Migration

### 1. Check Kafka topics are being produced to

```bash
# From your host
docker exec -it kgroot_latest-kafka-1 kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic state.k8s.resource \
  --from-beginning \
  --max-messages 5
```

### 2. Check alerts-enricher logs

```bash
# If in Docker
docker logs -f kgroot_latest-alerts-enricher-1

# If still in Minikube
kubectl logs -f deployment/alerts-enricher -n observability
```

### 3. Verify enriched alerts are produced

```bash
docker exec -it kgroot_latest-kafka-1 kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic alerts.enriched \
  --from-beginning \
  --max-messages 5
```

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LOCAL DOCKER                          │
│                                                          │
│  ┌──────────┐  ┌────────┐  ┌────────┐  ┌──────────┐   │
│  │  Kafka   │  │ Neo4j  │  │Kafka-UI│  │  graph-  │   │
│  │   +ZK    │  │        │  │        │  │ builder  │   │
│  └────┬─────┘  └───┬────┘  └────────┘  └────┬─────┘   │
│       │            │                         │          │
│       │            │    ┌──────────────┐    │          │
│       └────────────┴────│  alerts-     │────┘          │
│                         │ enricher     │                │
│                         └──────────────┘                │
└─────────────────────────────────────────────────────────┘
                              ▲
                              │ host.minikube.internal:29092
                              │
┌─────────────────────────────┼───────────────────────────┐
│                    MINIKUBE │                            │
│                             │                            │
│  ┌──────────────────────────┼─────────────┐             │
│  │         state-watcher    │             │             │
│  │  (watches K8s resources) │             │             │
│  │  - Pods, Services, etc   │             │             │
│  │  - Produces to Kafka ────┘             │             │
│  └────────────────────────────────────────┘             │
│                                                          │
│  ┌─────────────────────────────────────────┐            │
│  │         Prometheus Stack                │            │
│  │  (monitoring K8s cluster)               │            │
│  └─────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────┘
```

---

## Quick Command Reference

### Start/Stop Services

```bash
# Docker services
docker-compose up -d
docker-compose down

# Check Docker status
docker ps

# View logs
docker logs -f kgroot_latest-graph-builder-1
```

### Minikube services

```bash
# Check pods
kubectl get pods -n observability

# View logs
kubectl logs -f deployment/state-watcher -n observability

# Restart a deployment
kubectl rollout restart deployment/state-watcher -n observability
```

### Access UIs

- Kafka UI: http://localhost:7777
- Neo4j Browser: http://localhost:7474 (neo4j/anuragvishwa)
- Grafana: `minikube service prometheus-grafana -n monitoring`

---

## Troubleshooting

### Problem: Minikube can't reach Docker Kafka

**Solution:** Ensure minikube can resolve `host.minikube.internal`

```bash
minikube ssh
ping host.minikube.internal  # Should work
```

### Problem: Docker containers can't reach minikube services

**Solution:** Use port-forwards

```bash
# Forward Prometheus from minikube to localhost
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
```

Then in docker-compose:
```yaml
environment:
  PROMETHEUS_URL: http://host.docker.internal:9090
```

### Problem: Kafka connectivity issues

**Check listeners:**
```bash
docker exec kgroot_latest-kafka-1 kafka-broker-api-versions.sh --bootstrap-server localhost:9092
```

**Check topics:**
```bash
docker exec kgroot_latest-kafka-1 kafka-topics.sh --bootstrap-server localhost:9092 --list
```

---

## My Recommendation

**Keep it simple: Option 1 (no migration)** unless you have specific issues with minikube.

Your current setup is actually ideal:
- ✅ Kafka/Neo4j in Docker = fast, reliable, easy to manage
- ✅ state-watcher in Minikube = proper K8s access
- ✅ Clear separation of concerns

Only migrate alerts-enricher if:
- You're having minikube stability issues
- You want to reduce minikube resource usage
- You're actively developing alerts-enricher and want faster iteration

---

## Need Help?

If you decide to migrate, I can:
1. Update your docker-compose.yml
2. Update kubernetes deployment configs
3. Help test the migration
4. Create rollback scripts

Just let me know which option you'd like to pursue!
