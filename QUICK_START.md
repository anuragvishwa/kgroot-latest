# KGroot Quick Start Guide

Get your knowledge graph-based RCA system running in 10 minutes!

## Prerequisites

- ✅ Minikube or any Kubernetes cluster
- ✅ kubectl configured
- ✅ Helm installed
- ✅ Docker installed

## One-Command Deployment

```bash
cd /Users/anuragvishwa/Anurag/kgroot_latest

# Deploy everything
./deploy-all.sh
```

This script will:
1. Install Prometheus stack (monitoring namespace)
2. Deploy Kafka (observability namespace)
3. Deploy Neo4j graph database
4. Deploy kg-builder (knowledge graph builder)
5. Deploy Vector (event normalization)
6. Deploy state-watcher (K8s state tracking)
7. Deploy alerts-enricher (alert enrichment)
8. Deploy test alert (always firing)

**Time:** ~10-15 minutes

---

## Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n observability
kubectl get pods -n monitoring

# Expected pods in observability:
# - kafka-0
# - neo4j-0
# - kg-builder-*
# - vector-*
# - vector-logs-* (DaemonSet)
# - state-watcher-*
# - alerts-enricher-*
# - k8s-event-exporter-*
# - kafka-ui-*

# Check Kafka topics (should see 15 topics)
kubectl exec -n observability kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list

# Check messages flowing
kubectl exec -n observability kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group kg-builder --describe
# LAG should be 0 or low
```

---

## Access Services

### Neo4j Browser (Knowledge Graph)

```bash
kubectl port-forward -n observability svc/neo4j-external 7474:7474
```

Open: http://localhost:7474
- **Username:** neo4j
- **Password:** anuragvishwa

Try this query:
```cypher
MATCH (n) RETURN count(n) AS total_nodes;
```

### Kafka UI (Message Inspection)

```bash
kubectl port-forward -n observability svc/kafka-ui 7777:8080
```

Open: http://localhost:7777

Check topics:
- `events.normalized` - All K8s events
- `logs.normalized` - Application logs
- `alerts.normalized` - Prometheus alerts
- `state.k8s.resource` - Resource snapshots
- `state.k8s.topology` - Relationships

### Prometheus (Metrics)

```bash
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
```

Open: http://localhost:9090

### Alertmanager (Alerts)

```bash
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-alertmanager 9093:9093
```

Open: http://localhost:9093

---

## Test RCA System

### Deploy Test Scenarios

```bash
# Run all tests (recommended)
./test/run-all-tests.sh

# Or deploy individual tests:
kubectl apply -f test/01-imagepull-failure.yaml
kubectl apply -f test/02-crashloop.yaml
kubectl apply -f test/05-cascading-failure.yaml
```

### Validate System

```bash
./test/validate-rca.sh

# Expected output:
# ✅ 10+ checks passed
# ⚠️ 0-3 warnings (acceptable)
# ❌ 0 failures
```

### Run RCA Queries

Port-forward Neo4j (if not already):
```bash
kubectl port-forward -n observability svc/neo4j-external 7474:7474
```

**Query 1: Recent Failures**
```cypher
MATCH (e:Episodic)
WHERE e.severity IN ['ERROR', 'CRITICAL']
  AND e.event_time > datetime() - duration({hours: 1})
RETURN e.reason, e.message, e.event_time
ORDER BY e.event_time DESC
LIMIT 10;
```

**Query 2: Find Root Causes**
```cypher
MATCH (symptom:Episodic)
WHERE symptom.reason CONTAINS 'BackOff'
  AND symptom.event_time > datetime() - duration({minutes: 30})
WITH symptom
MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(symptom)
RETURN cause.reason AS root_cause,
       symptom.reason AS symptom,
       duration.between(cause.event_time, symptom.event_time) AS lag
ORDER BY lag;
```

**Query 3: Cascading Failures**
```cypher
MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..3]->(symptom:Episodic)
WHERE root.event_time > datetime() - duration({minutes: 30})
RETURN [e IN nodes(path) | e.reason] AS failure_chain,
       length(path) AS depth
ORDER BY depth DESC
LIMIT 5;
```

More queries: See `NEO4J_QUERIES_CHEATSHEET.md`

---

## Configuration

All services use unified configuration from `.env` file and `kgroot-env` ConfigMap.

### View Current Config

```bash
kubectl get configmap kgroot-env -n observability -o yaml
```

### Update Configuration

```bash
# Edit ConfigMap
kubectl edit configmap kgroot-env -n observability

# Restart services to pick up changes
kubectl rollout restart deployment/kg-builder -n observability
kubectl rollout restart deployment/state-watcher -n observability
kubectl rollout restart deployment/alerts-enricher -n observability
```

### Key Parameters

```bash
# RCA Time Window (minutes)
RCA_WINDOW_MIN=15

# Causal Link Max Distance
CAUSAL_LINK_MAX_HOPS=3

# High-signal log filtering (reduces noise)
ENABLE_LOG_FILTERING=true

# Real-time fault propagation
ENABLE_FPG_REALTIME=true
```

See `.env` for all options.

---

## Troubleshooting

### No Data in Neo4j

```bash
# Check kg-builder logs
kubectl logs -n observability -l app=kg-builder --tail=50

# Common issues:
# - Neo4j not ready: Wait 2-3 minutes after deployment
# - Kafka connection: Check KAFKA_BROKERS in ConfigMap
# - Schema not created: Check logs for "schema ready"
```

### No Messages in Kafka Topics

```bash
# Check Vector logs
kubectl logs -n observability -l app=vector --tail=50

# Check state-watcher logs
kubectl logs -n observability -l app=state-watcher --tail=50

# Common issues:
# - Kafka not ready: Wait for kafka-0 pod to be Running
# - No events generated: Deploy test scenarios
# - Service name resolution: Check DNS (kafka.observability.svc:9092)
```

### Pods Not Starting

```bash
# Check pod status
kubectl get pods -n observability
kubectl describe pod <pod-name> -n observability

# Common issues:
# - Image pull: Run minikube image load <image>
# - ConfigMap not found: Apply k8s/kg-builder.yaml first
# - Resource limits: Check node has enough memory/CPU
```

### Validation Script Fails

```bash
# Check which step failed
./test/validate-rca.sh

# If "Neo4j connection failed":
kubectl get pod -n observability -l app=neo4j
kubectl logs -n observability neo4j-0 --tail=100

# If "No POTENTIAL_CAUSE links":
# System may need more time or events
# Deploy test scenarios to generate events
kubectl apply -f test/05-cascading-failure.yaml
sleep 120
./test/validate-rca.sh
```

---

## Cleanup

### Remove Test Scenarios

```bash
./test/cleanup-tests.sh
```

### Uninstall Everything

```bash
# Remove observability stack
kubectl delete namespace observability

# Remove Prometheus
helm uninstall prometheus -n monitoring
kubectl delete namespace monitoring

# Remove PVCs (if needed)
kubectl get pvc -n observability
kubectl delete pvc <pvc-name> -n observability
```

---

## What's Next?

### 1. Explore the Knowledge Graph

- Open Neo4j Browser
- Run queries from `NEO4J_QUERIES_CHEATSHEET.md`
- Visualize pod/service relationships
- Find causal chains

### 2. Integrate with Alertmanager

Edit Alertmanager config to send alerts to Vector:

```bash
kubectl edit secret -n monitoring alertmanager-prometheus-kube-prometheus-alertmanager

# Add webhook receiver:
receivers:
  - name: 'vector'
    webhook_configs:
      - url: 'http://vector.observability.svc:9000'

# Update route to use vector receiver
```

### 3. Deploy Your Apps

```bash
# Deploy your microservices
kubectl apply -f your-app.yaml

# Watch events flow into Neo4j
kubectl logs -n observability -l app=kg-builder -f

# Query your app's events
# In Neo4j Browser:
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource)
WHERE pod.name CONTAINS 'your-app'
RETURN e.reason, e.message, e.event_time
ORDER BY e.event_time DESC;
```

### 4. Improve RCA Accuracy

Follow the roadmap in `KGROOT_RCA_IMPROVEMENTS.md`:

- **Phase 1 (Current):** 60-70% accuracy ✅
- **Phase 2 (Historical Learning):** 75-85% accuracy
- **Phase 3 (ML/GCN):** 90-95% accuracy

### 5. Integrate External Systems

When ready, add integrations:

- **ArgoCD:** Track deployments and Git commits
- **Jira:** Link incidents to root causes
- **GitHub:** Connect bugs to production failures

See `ANSWERS_TO_YOUR_QUESTIONS.md` for integration details.

---

## Documentation Index

| Document | Purpose |
|----------|---------|
| `README.md` | Full project documentation |
| `QUICK_START.md` | This guide - get started fast |
| `.env` | Unified configuration |
| `ENV_MIGRATION_GUIDE.md` | How .env configuration works |
| `KUBERNETES_FAILURE_PATTERNS.md` | What bugs we catch (85% coverage) |
| `KGROOT_RCA_IMPROVEMENTS.md` | Roadmap to 90-95% accuracy |
| `RCA_TESTING_GUIDE.md` | Test scenarios and verification |
| `NEO4J_QUERIES_CHEATSHEET.md` | 50+ example queries |
| `ANSWERS_TO_YOUR_QUESTIONS.md` | Detailed Q&A |
| `DEPLOYMENT.md` | Step-by-step deployment |
| `RCA_DATA_ANALYSIS.md` | Kafka topic schemas |

---

## Support

- **Issues:** Check logs (kg-builder, vector, state-watcher)
- **Queries:** See `NEO4J_QUERIES_CHEATSHEET.md`
- **Tests:** Run `./test/validate-rca.sh`
- **Config:** Check `kgroot-env` ConfigMap

---

## Success Checklist

- [ ] All pods running in `observability` namespace
- [ ] Neo4j accessible at localhost:7474
- [ ] Kafka has 15 topics with messages
- [ ] `./test/validate-rca.sh` passes
- [ ] Can query events in Neo4j
- [ ] POTENTIAL_CAUSE links exist
- [ ] Test scenarios show correct RCA

**If all checked: Your RCA system is working! 🎉**

---

## Time to First RCA

```
t=0:  ./deploy-all.sh
t=10: All pods running
t=12: Deploy test scenario
t=14: RCA results in Neo4j

Total: ~15 minutes from zero to working RCA!
```

Happy debugging! 🐛🔍
