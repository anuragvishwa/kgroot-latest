# ✅ Docker Migration Completed

## What Was Migrated

Successfully moved from Minikube to Docker:
- ✅ Kafka + Zookeeper
- ✅ Neo4j
- ✅ Kafka-UI
- ✅ graph-builder (kg)
- ✅ alerts-enricher
- ✅ kafka-init

## What Stays in Minikube

These services require Kubernetes API access:
- ✅ state-watcher (watches K8s resources, produces to Docker Kafka)
- ✅ k8s-event-exporter
- ✅ vector + vector-logs
- ✅ Prometheus stack (monitoring namespace)

## Fixed Issues

1. **KAFKA_BOOTSTRAP env var** - Updated state-watcher to point to Docker Kafka:
   ```bash
   KAFKA_BOOTSTRAP=host.minikube.internal:29092
   ```

2. **ZSTD compression** - Added ZSTD codec support to alerts-enricher to handle compressed messages from state-watcher

## Current Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   DOCKER (localhost)                      │
│                                                           │
│  Kafka:9092 ──┬── Neo4j:7687 ── graph-builder            │
│               │                                           │
│               ├── Kafka-UI:7777                           │
│               │                                           │
│               └── alerts-enricher                         │
│                      (enriches alerts with K8s context)   │
└───────────────────────────▲──────────────────────────────┘
                            │
                            │ host.minikube.internal:29092
                            │
┌───────────────────────────┴──────────────────────────────┐
│                     MINIKUBE                              │
│                                                           │
│  state-watcher ──────┐                                    │
│   (watches K8s API)  │                                    │
│                      ├── Produces to Docker Kafka         │
│  k8s-event-exporter ─┘                                    │
│                                                           │
│  Prometheus Stack                                         │
│   (monitoring namespace)                                  │
└───────────────────────────────────────────────────────────┘
```

## Cleanup Minikube (Remove Redundant Pods)

### Already Deleted ✅
```bash
# These were already removed:
# - kafka-0 (StatefulSet)
# - neo4j-0 (StatefulSet)
# - kafka-ui
# - kg-builder (from observability namespace)
# - kg-init-schema (Job)
```

### Optional: Clean Up Orphaned Resources

```bash
# Check for orphaned PVCs
kubectl get pvc -n observability

# Delete if kafka/neo4j PVCs exist:
kubectl delete pvc data-kafka-0 -n observability
kubectl delete pvc neo4j-data-neo4j-0 -n observability

# Check for ConfigMaps (keep kgroot-env, it's used by state-watcher)
kubectl get configmap -n observability
# DON'T DELETE: kgroot-env, kafka-init-script, k8s-event-exporter-config

# Check for Services
kubectl get svc -n observability
# Delete old services if they exist:
kubectl delete svc kafka neo4j kafka-ui -n observability 2>/dev/null || echo "Already deleted"
```

## Verification Commands

### Check Docker Services
```bash
# Check all containers are running
docker ps

# Check Kafka topics
docker exec kgroot_latest-kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 --list

# Check messages in state.k8s.resource topic
docker exec kgroot_latest-kafka-1 kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic state.k8s.resource \
  --from-beginning \
  --max-messages 5

# Check consumer groups
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
```

### Check Minikube Services
```bash
# Check pods
kubectl get pods -n observability

# Check state-watcher logs
kubectl logs -f deployment/state-watcher -n observability

# Verify state-watcher is producing to Docker Kafka
kubectl exec -n observability deployment/state-watcher -- \
  env | grep KAFKA
```

### Check Logs
```bash
# Docker services
docker logs -f kgroot_latest-graph-builder-1
docker logs -f kgroot_latest-alerts-enricher-1

# State-watcher (minikube)
kubectl logs -f deployment/state-watcher -n observability
```

## Access UIs

- **Kafka UI**: http://localhost:7777
- **Neo4j Browser**: http://localhost:7474 (neo4j/anuragvishwa)
- **Grafana**: Run `minikube service prometheus-grafana -n monitoring`

## Start/Stop Commands

### Docker
```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart specific service
docker compose restart alerts-enricher

# Rebuild and restart
docker compose build alerts-enricher && docker compose up -d alerts-enricher
```

### Minikube
```bash
# Start minikube
minikube start

# Stop minikube
minikube stop

# Restart deployment
kubectl rollout restart deployment/state-watcher -n observability

# Update environment variable
kubectl set env deployment/state-watcher -n observability KEY=value
```

## Troubleshooting

### Problem: No messages in Kafka topics

**Check state-watcher logs:**
```bash
kubectl logs deployment/state-watcher -n observability --tail 50
```

**Verify env vars:**
```bash
kubectl get deployment state-watcher -n observability -o yaml | grep KAFKA
```

**Should see:**
```yaml
KAFKA_BOOTSTRAP: host.minikube.internal:29092
KAFKA_BROKERS: host.minikube.internal:29092
```

### Problem: alerts-enricher crashes

**Check logs:**
```bash
docker logs kgroot_latest-alerts-enricher-1
```

**Common issues:**
- ZSTD compression not supported → Fixed by adding zstd-codec package
- Kafka connection failed → Check `docker ps` to ensure Kafka is running

### Problem: graph-builder not consuming messages

**Check consumer lag:**
```bash
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group kg-builder
```

**Check logs:**
```bash
docker logs kgroot_latest-graph-builder-1 --tail 50
```

## Environment Variables

### state-watcher (Minikube)
```yaml
KAFKA_BOOTSTRAP: host.minikube.internal:29092
KAFKA_BROKERS: host.minikube.internal:29092
TOPIC_STATE: state.k8s.resource
TOPIC_TOPO: state.k8s.topology
TOPIC_PROM_TARGETS: state.prom.targets
TOPIC_PROM_RULES: state.prom.rules
PROM_URL: http://prometheus-kube-prometheus-prometheus.monitoring.svc:9090
```

### alerts-enricher (Docker)
```yaml
KAFKA_BROKERS: kafka:9092
KAFKA_GROUP: alerts-enricher
INPUT_TOPIC: events.normalized
OUTPUT_TOPIC: alerts.enriched
STATE_RESOURCE_TOPIC: state.k8s.resource
STATE_TOPOLOGY_TOPIC: state.k8s.topology
```

### graph-builder (Docker)
```yaml
KAFKA_BROKERS: kafka:9092
KAFKA_GROUP: kg-builder
NEO4J_URI: neo4j://neo4j:7687
NEO4J_USER: neo4j
NEO4J_PASS: anuragvishwa
TOPIC_LOGS: logs.normalized
```

## What's Next?

1. **Monitor for a few hours** - Ensure messages are flowing correctly
2. **Check Neo4j** - Verify graph is being built (http://localhost:7474)
3. **Test alerting pipeline** - Verify alerts flow through enrichment
4. **Consider moving vector** - If you want to move log collection to Docker (optional)

## Rollback (If Needed)

If something goes wrong, you can rollback:

```bash
# 1. Stop Docker services
docker compose down

# 2. Reapply minikube manifests
kubectl apply -f k8s/

# 3. Update state-watcher to use minikube Kafka
kubectl set env deployment/state-watcher -n observability \
  KAFKA_BOOTSTRAP=kafka.observability.svc:9092
```

## Performance Benefits

✅ Faster development iteration (no minikube image loading)
✅ Lower resource usage (fewer minikube pods)
✅ Easier debugging (Docker logs vs kubectl logs)
✅ Better separation of concerns (data in Docker, K8s watchers in minikube)
