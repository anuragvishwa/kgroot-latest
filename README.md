# KGroot - Knowledge Graph for Root Cause Analysis

**Kubernetes observability platform with knowledge graph-based root cause analysis**

Based on the paper: *"KGroot: Enhancing Root Cause Analysis through Knowledge Graphs and LLM"* (arXiv:2402.13264v1)

## Overview

KGroot automatically builds a knowledge graph from Kubernetes cluster observability data (logs, events, alerts, metrics) and uses graph-based reasoning to identify root causes of failures and performance issues.

### Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│  Prometheus     │────▶│   Vector     │────▶│   Kafka     │
│  Alertmanager   │     │  (normalize) │     │  (topics)   │
└─────────────────┘     └──────────────┘     └──────┬──────┘
                                                     │
┌─────────────────┐                                 │
│  K8s API        │────▶ state-watcher ────────────▶│
│  (events, pods) │                                  │
└─────────────────┘                                 │
                                                     │
┌─────────────────┐     ┌──────────────┐           │
│  Pod Logs       │────▶│ Vector Logs  │───────────▶│
│  (all nodes)    │     │  (DaemonSet) │            │
└─────────────────┘     └──────────────┘            │
                                                     ▼
                        ┌──────────────────────────────┐
                        │   alerts-enricher            │
                        │   (enrich with state/topo)   │
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                        │   kg-builder                 │
                        │   (Neo4j Knowledge Graph)    │
                        └──────────────────────────────┘
                                       │
                        ┌──────────────▼───────────────┐
                        │   Neo4j                      │
                        │   (RCA queries & analysis)   │
                        └──────────────────────────────┘
```

### Key Features

- **Real-time Event Ingestion**: Collects logs, events, alerts, and resource state
- **Unified Knowledge Graph**: Builds connected graph of resources, events, and relationships
- **Automatic Causal Discovery**: Identifies potential root causes using temporal + topological analysis
- **High-Signal Filtering**: Reduces noise by filtering low-value logs
- **Scalable Architecture**: Kafka-based event streaming with compacted state topics

## Quick Start

### Prerequisites

- Minikube (or any Kubernetes cluster)
- kubectl
- Docker
- Helm (for Prometheus)

### 1. Install Prometheus Stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  -f k8s/prom-values.yaml
```

### 2. Deploy Core Infrastructure

```bash
# Deploy Kafka
kubectl apply -f k8s/kafka.yaml

# Wait for Kafka to be ready
kubectl wait --for=condition=ready pod -l app=kafka -n observability --timeout=300s

# Verify topics were created
kubectl exec -n observability kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list
```

### 3. Configure Alertmanager Webhook

```bash
# Get Vector service IP
kubectl get svc -n observability vector

# Update Alertmanager configuration
kubectl edit secret -n monitoring alertmanager-prometheus-kube-prometheus-alertmanager

# Add webhook receiver for Vector:
# receivers:
#   - name: 'vector'
#     webhook_configs:
#       - url: 'http://vector.observability.svc:9000'
```

### 4. Deploy Observability Pipeline

```bash
# Apply ConfigMap with .env-based configuration
kubectl apply -f k8s/kg-builder.yaml  # Creates kgroot-env ConfigMap

# Deploy Vector (events/alerts normalization)
kubectl apply -f k8s/vector-configmap.yaml

# Deploy state-watcher (K8s resource state)
kubectl apply -f k8s/state-watcher.yaml

# Deploy K8s event exporter
kubectl apply -f k8s/k8s-event-exporter.yaml

# Deploy alerts enricher
cd alerts-enricher
./build-and-deploy.sh
cd ..
```

### 5. Deploy Knowledge Graph

```bash
# Deploy Neo4j
kubectl apply -f k8s/neo4j.yaml

# Wait for Neo4j to be ready
kubectl wait --for=condition=ready pod -l app=neo4j -n observability --timeout=300s

# Build and deploy kg-builder
cd kg
./build-and-deploy.sh
cd ..
```

### 6. Create Test Alert

```bash
# Deploy always-firing test alert
kubectl apply -f k8s/always-firing-rule.yaml
```

## Configuration

All services use a unified configuration via `.env` file and Kubernetes ConfigMap `kgroot-env`.

### Key Configuration Parameters

```bash
# Cluster
CLUSTER_NAME=minikube

# Kafka
KAFKA_BROKERS=kafka.observability.svc:9092

# Neo4j
NEO4J_URI=neo4j://neo4j.observability.svc:7687
NEO4J_USER=neo4j
NEO4J_PASS=anuragvishwa

# RCA Settings
RCA_WINDOW_MIN=15                    # Causal link time window
CAUSAL_LINK_MAX_HOPS=3               # Max graph distance
EVENT_CORRELATION_WINDOW_SEC=60      # Event deduplication window

# Feature Flags
ENABLE_LOG_FILTERING=true            # High-signal logs only
ENABLE_FPG_REALTIME=true             # Real-time fault propagation
ENABLE_FEKG_HISTORICAL=true          # Historical pattern learning
```

See `.env` for full configuration options.

## Verification

### Check All Pods Running

```bash
kubectl get pods -n observability
kubectl get pods -n monitoring
```

Expected pods:
- `kafka-0` (StatefulSet)
- `neo4j-0` (StatefulSet)
- `vector-*` (Deployment)
- `vector-logs-*` (DaemonSet)
- `state-watcher-*` (Deployment)
- `alerts-enricher-*` (Deployment)
- `kg-builder-*` (Deployment)
- `k8s-event-exporter-*` (Deployment)

### Check Kafka Topics

```bash
kubectl exec -n observability kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Expected topics:
- `raw.k8s.logs`, `raw.k8s.events`, `raw.prom.alerts`, `raw.events`
- `events.normalized`, `logs.normalized`, `alerts.normalized`, `alerts.enriched`
- `state.k8s.resource`, `state.k8s.topology`, `state.prom.targets`, `state.prom.rules`
- `graph.commands`
- `dlq.raw`, `dlq.normalized`

### Check Messages Flowing

```bash
# Check consumer groups
kubectl exec -n observability kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list

# Check kg-builder lag (should be 0)
kubectl exec -n observability kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group kg-builder --describe
```

### Access Neo4j Browser

```bash
# Forward Neo4j HTTP port
kubectl port-forward -n observability svc/neo4j-external 7474:7474

# Open browser: http://localhost:7474
# Username: neo4j
# Password: anuragvishwa
```

### Access Kafka UI

```bash
# Forward Kafka UI port
kubectl port-forward -n observability svc/kafka-ui 7777:8080

# Open browser: http://localhost:7777
```

## Neo4j RCA Queries

### Find Root Causes for an Event

```cypher
// Given an error event ID, find potential root causes
MATCH (error:Episodic {eid: 'YOUR_EVENT_ID'})
MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(error)
RETURN cause.reason AS root_cause,
       cause.severity AS severity,
       cause.message AS description,
       pc.hops AS distance,
       duration.between(cause.event_time, error.event_time) AS time_lag
ORDER BY pc.hops ASC, cause.event_time DESC
LIMIT 10
```

### Find All Recent Errors

```cypher
MATCH (e:Episodic)
WHERE e.severity IN ['ERROR', 'CRITICAL']
  AND e.event_time > datetime() - duration({hours: 1})
RETURN e.eid AS event_id,
       e.reason AS reason,
       e.message AS message,
       e.event_time AS timestamp
ORDER BY e.event_time DESC
LIMIT 50
```

### Analyze Pod Failures

```cypher
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource:Pod)
WHERE e.severity = 'ERROR'
  AND e.event_time > datetime() - duration({hours: 24})
MATCH (pod)<-[:SELECTS]-(svc:Resource:Service)
OPTIONAL MATCH (svc)<-[:CONTROLS]-(deploy:Resource:Deployment)
RETURN pod.name AS failed_pod,
       pod.ns AS namespace,
       collect(DISTINCT e.reason) AS error_types,
       count(e) AS error_count,
       collect(DISTINCT svc.name) AS affected_services,
       collect(DISTINCT deploy.name) AS deployments
ORDER BY error_count DESC
```

### Common Fault Patterns

```cypher
// Find frequent failure sequences
MATCH path = (e1:Episodic)-[:POTENTIAL_CAUSE]->(e2:Episodic)-[:POTENTIAL_CAUSE]->(e3:Episodic)
WHERE e3.event_time > datetime() - duration({days: 7})
  AND e1.severity IN ['ERROR', 'CRITICAL']
WITH [e1.reason, e2.reason, e3.reason] AS sequence
RETURN sequence, count(*) AS occurrences
ORDER BY occurrences DESC
LIMIT 20
```

### Service Dependency Graph

```cypher
MATCH (pod:Resource:Pod)<-[:SELECTS]-(svc:Resource:Service)
OPTIONAL MATCH (svc)<-[:CONTROLS]-(deploy:Resource:Deployment)
RETURN pod, svc, deploy
LIMIT 100
```

## Kafka Topics Reference

### Raw Streams (Append-only)
- **raw.k8s.logs** (3d retention): Raw pod logs from Vector DaemonSet
- **raw.k8s.events** (14d retention): Raw K8s events from event-exporter
- **raw.prom.alerts** (30d retention): Raw Prometheus/Alertmanager payloads
- **raw.events** (30d retention): Combined raw events with stable keys

### Normalized Events
- **events.normalized** (60d retention): Normalized events (K8s + Prometheus)
- **logs.normalized** (14d retention): Normalized high-signal logs
- **alerts.normalized** (30d retention): Normalized Prometheus alerts
- **alerts.enriched** (30d retention): Alerts enriched with state/topology

### State Topics (Compacted)
- **state.k8s.resource** (1y retention, compacted): K8s resource snapshots
- **state.k8s.topology** (1y retention, compacted): K8s relationships
- **state.prom.targets** (7d retention, compacted): Prometheus scrape targets
- **state.prom.rules** (1y retention, compacted): Prometheus alerting rules

### Control Topics
- **graph.commands** (1y retention, compacted): Commands for kg-builder

### Dead Letter Queues
- **dlq.raw** (7d retention): Failed raw events
- **dlq.normalized** (7d retention): Failed normalized events

## Troubleshooting

### No Messages in Topics

```bash
# Check Vector logs
kubectl logs -n observability -l app=vector -f

# Check state-watcher logs
kubectl logs -n observability -l app=state-watcher -f

# Check alerts-enricher logs
kubectl logs -n observability -l app=alerts-enricher -f
```

### kg-builder Not Consuming

```bash
# Check logs
kubectl logs -n observability -l app=kg-builder -f

# Verify Neo4j connection
kubectl exec -n observability -it kg-builder-xxx -- sh
# Inside container: check connectivity to neo4j:7687
```

### Neo4j Graph Empty

```bash
# Check if schema was created
# In Neo4j Browser:
CALL db.constraints()

# Should show constraints on:
# - Resource.rid
# - Episodic.eid
# - PromTarget.tid
# - Rule.rkey

# Force schema creation
kubectl exec -n observability kafka-0 -- \
  kafka-console-producer.sh --bootstrap-server localhost:9092 \
  --topic graph.commands \
  --property "parse.key=true" \
  --property "key.separator=|"

# Type: cmd|{"op":"ENSURE_SCHEMA"}
# Press Ctrl+D
```

## Performance Tuning

### Reduce Graph Bloat

```bash
# Enable high-signal log filtering (in .env or ConfigMap)
ENABLE_LOG_FILTERING=true
PRUNE_OLD_EVENTS_DAYS=30
PRUNE_RESOLVED_INCIDENTS_DAYS=7
```

### Increase RCA Accuracy

```bash
# Expand causal link discovery window
RCA_WINDOW_MIN=30
CAUSAL_LINK_MAX_HOPS=5
```

### Scale Components

```bash
# Scale Vector for high alert volume
kubectl scale deployment -n observability vector --replicas=3

# Scale alerts-enricher for throughput
kubectl scale deployment -n observability alerts-enricher --replicas=2
```

## Next Steps

1. **Review** `KGROOT_RCA_IMPROVEMENTS.md` for maximum accuracy recommendations
2. **Collect training data** for 2-4 weeks
3. **Tag resolved incidents** with root causes for historical learning
4. **Implement Phase 2** (Historical FEKG) for 75-85% accuracy
5. **Optional**: Deploy GCN service for ML-based similarity (90-95% accuracy)

## Documentation

- [RCA Improvements](./KGROOT_RCA_IMPROVEMENTS.md) - Achieving maximum accuracy
- [Deployment Guide](./DEPLOYMENT.md) - Step-by-step deployment
- [Data Analysis](./RCA_DATA_ANALYSIS.md) - Kafka topic schemas and RCA suitability

## License

MIT

## References

- [KGroot Paper](https://arxiv.org/abs/2402.13264) - arXiv:2402.13264v1
- [Neo4j Documentation](https://neo4j.com/docs/)
- [Apache Kafka](https://kafka.apache.org/)
- [Vector](https://vector.dev/)
