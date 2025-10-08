# Quick Start Guide - Testing in 5 Minutes

## 1. Deploy Test Apps (1 minute)

```bash
cd test-scenarios/scripts
./build-and-deploy.sh
```

Wait for the script to complete. You'll see pod status at the end.

---

## 2. Watch What Happens (2-3 minutes)

**Terminal 1 - Watch pods:**
```bash
kubectl get pods -n kg-testing -w
```

You should see:
- `crashloop-test`: CrashLoopBackOff
- `oom-test`: OOMKilled or Running (will be killed soon)
- `slow-startup-test`: Not Ready → Ready after 90s
- `error-logger-test`: Running
- `intermittent-fail-test`: Running (may crash eventually)
- `image-pull-fail`: ImagePullBackOff

**Terminal 2 - Watch events:**
```bash
cd test-scenarios/scripts
./watch-events.sh
```

You'll see Kubernetes events like `BackOff`, `OOMKilled`, `Unhealthy`, etc.

---

## 3. Check Data Pipeline (30 seconds)

**Check Kafka:**
```bash
cd test-scenarios/scripts
./check-kafka-topics.sh
```

Or open Kafka UI: http://localhost:7777

**Expected:** Topics should have new messages.

---

## 4. Run Neo4j Queries (1 minute)

```bash
cd test-scenarios/queries
./run-test-queries.sh
```

This runs all 8 query categories and shows results.

**Or use Neo4j Browser:**
- Open http://localhost:7474
- Login: `neo4j` / `anuragvishwa`
- Run any query from `queries/*.cypher` files

---

## 5. Key Queries to Try

**See all errors:**
```cypher
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing' AND e.severity IN ['ERROR', 'FATAL']
RETURN e.event_time, e.reason, r.name
ORDER BY e.event_time DESC LIMIT 20;
```

**Find CrashLoops:**
```cypher
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing' AND e.reason CONTAINS 'Crash'
RETURN e.event_time, e.reason, r.name
ORDER BY e.event_time DESC;
```

**Root cause analysis:**
```cypher
MATCH (s:Episodic)-[:POTENTIAL_CAUSE]->(r:Episodic)
WHERE exists((s)-[:ABOUT]->(:Resource {ns: 'kg-testing'}))
RETURN s.reason as symptom, r.reason as root_cause
LIMIT 10;
```

**Count events by severity:**
```cypher
MATCH (e:Episodic)-[:ABOUT]->(:Resource {ns: 'kg-testing'})
RETURN e.severity, count(*) as count
ORDER BY count DESC;
```

---

## 6. Cleanup

```bash
cd test-scenarios/scripts
./cleanup.sh
```

---

## Visual Tools

- **Kafka UI:** http://localhost:7777
- **Neo4j Browser:** http://localhost:7474 (neo4j/anuragvishwa)
- **Grafana:** http://localhost:3000 (admin/admin)

---

## What Should You See?

### In Neo4j (after 2-3 minutes):

✅ **Resources:**
- 7+ Pod resources in `kg-testing` namespace
- 5+ Deployment/ReplicaSet resources
- 5+ Service resources

✅ **Events:**
- 50+ Episodic events (k8s.event, k8s.log)
- Multiple severity levels (INFO, WARNING, ERROR, FATAL)
- Event types: CrashLoopBackOff, OOMKilled, Unhealthy, ImagePullBackOff

✅ **Relationships:**
- ABOUT: Events linked to resources
- POTENTIAL_CAUSE: Errors linked to root causes
- CONTROLS: Deployment → ReplicaSet → Pod

### Expected Event Reasons:

| Event Reason | Pod | Severity |
|--------------|-----|----------|
| BackOff, CrashLoopBackOff | crashloop-test | FATAL |
| OOMKilled | oom-test | FATAL |
| Unhealthy, ProbeWarning | slow-startup-test | WARNING |
| ImagePullBackOff | image-pull-fail | ERROR |
| LOG_ERROR | error-logger-test | ERROR |

---

## Troubleshooting

**No events in Neo4j?**
```bash
# Check graph-builder logs
docker logs kgroot_latest-graph-builder-1 --tail=50

# Check consumer lag
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --group kg-builder --describe
```

**Pods not starting?**
```bash
kubectl describe pod -n kg-testing <pod-name>
```

**Image not found?**
```bash
minikube image load kg-test-apps:latest
```

---

## Next Steps

📖 Read full documentation: [README.md](README.md)

🔍 Explore all queries: `cd queries && ls *.cypher`

📊 Create custom dashboards in Grafana

🧪 Add your own test scenarios

---

**Total time: ~5 minutes** ⏱️
