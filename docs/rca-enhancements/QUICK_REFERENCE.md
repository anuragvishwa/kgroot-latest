# RCA Enhancements - Quick Reference

Fast reference for deployment, access, and common operations.

---

## Quick Deploy (New Cluster)

```bash
# 1. Build and load enhanced image
cd /Users/anuragvishwa/Anurag/kgroot_latest
docker build -t kg-builder:enhanced -f kg/Dockerfile .
minikube image load kg-builder:enhanced

# 2. Apply enhanced vector config
kubectl apply -f k8s/vector-configmap.yaml

# 3. Restart vector components
kubectl rollout restart deployment/vector -n observability
kubectl rollout restart daemonset/vector-logs -n observability

# 4. Deploy enhanced kg-builder
kubectl set image deployment/kg-builder kg-builder=kg-builder:enhanced -n observability

# 5. Verify
kubectl get pods -n observability
```

---

## Quick Access

### Neo4j Browser
```bash
# Port-forward
kubectl port-forward -n observability pod/neo4j-0 7474:7474 7687:7687 &

# Open: http://localhost:7474/browser/
# Connect: bolt://localhost:7687
# Username: neo4j
# Password: anuragvishwa
```

### Kafka UI
```bash
minikube service kafka-ui -n observability --url
# Or: http://127.0.0.1:50040
```

---

## Essential Queries

### Check System Status
```cypher
// Total events by severity
MATCH (e:Episodic)
RETURN e.severity, count(*) AS count
ORDER BY count DESC

// Total RCA links
MATCH ()-[r:POTENTIAL_CAUSE]->()
RETURN count(r) AS total_links

// RCA links with confidence scores
MATCH ()-[r:POTENTIAL_CAUSE]->()
WHERE r.confidence IS NOT NULL
RETURN count(r) AS links_with_confidence
```

### Top Confidence Scores
```cypher
MATCH (c:Episodic)-[r:POTENTIAL_CAUSE]->(e:Episodic)
WHERE r.confidence IS NOT NULL
RETURN c.reason, e.reason, r.confidence
ORDER BY r.confidence DESC
LIMIT 10
```

### Recent High-Severity Events
```cypher
MATCH (e:Episodic)
WHERE e.severity IN ['ERROR', 'FATAL']
  AND e.event_time >= datetime() - duration('PT1H')
RETURN e.reason, e.message, e.severity
ORDER BY e.event_time DESC
LIMIT 20
```

### Escalated Events
```cypher
MATCH (e:Episodic)
WHERE e.escalated = true
RETURN e.reason, e.severity, e.repeat_count, e.event_time
ORDER BY e.event_time DESC
LIMIT 10
```

### Incident Clusters
```cypher
MATCH (i:Incident)
RETURN i.resource_id, i.event_count, i.window_start
ORDER BY i.event_count DESC
LIMIT 10
```

### RCA for Specific Event
```cypher
// Replace 'event-id-here' with actual eid
MATCH path = (c:Episodic)-[r:POTENTIAL_CAUSE*1..3]->(e:Episodic {eid: 'event-id-here'})
RETURN c.reason AS cause, e.reason AS effect, length(path) AS distance,
       [rel in relationships(path) | rel.confidence] AS confidences
ORDER BY distance
```

---

## Common Commands

### Check Pod Status
```bash
kubectl get pods -n observability
kubectl logs -n observability -l app=kg-builder --tail=50
kubectl logs -n observability -l app=vector-logs --tail=50
```

### Restart Components
```bash
kubectl rollout restart deployment/kg-builder -n observability
kubectl rollout restart daemonset/vector-logs -n observability
kubectl delete pod kafka-0 -n observability  # Restart Kafka
```

### Check Feature Flags
```bash
kubectl exec -n observability -l app=kg-builder -- printenv | grep -E "SEVERITY|INCIDENT"
```

### Check Kafka Topics
```bash
kubectl exec -n observability kafka-0 -- \
  /opt/kafka/bin/kafka-topics.sh \
  --list --bootstrap-server localhost:9092
```

---

## Troubleshooting Quick Fixes

### Vector-logs CrashLoopBackOff
```bash
# Check logs for VRL errors
kubectl logs -n observability -l app=vector-logs --tail=30

# Fix is already applied in k8s/vector-configmap.yaml
# Just restart:
kubectl rollout restart daemonset/vector-logs -n observability
```

### Kafka OOMKilled
```bash
# Increase memory (edit statefulset)
kubectl edit statefulset kafka -n observability

# Add under spec.template.spec.containers[0]:
resources:
  limits:
    memory: "1Gi"
  requests:
    memory: "512Mi"
```

### No Confidence Scores
```bash
# Restart kg-builder to trigger reprocessing
kubectl rollout restart deployment/kg-builder -n observability

# Check logs
kubectl logs -n observability -l app=kg-builder --tail=100 | grep LinkRCAWithScore
```

### Neo4j Connection Error
```bash
# Check port-forward
ps aux | grep "port-forward.*neo4j"

# Restart if needed
pkill -f "kubectl port-forward.*neo4j"
kubectl port-forward -n observability pod/neo4j-0 7474:7474 7687:7687 &
```

---

## Feature Flags (.env)

```bash
# Enhanced RCA Features
SEVERITY_ESCALATION_ENABLED=true
SEVERITY_ESCALATION_WINDOW_MIN=5
SEVERITY_ESCALATION_THRESHOLD=3
INCIDENT_CLUSTERING_ENABLED=true
OPENAI_EMBEDDINGS_ENABLED=false
```

---

## File References

| Feature | File | Lines |
|---------|------|-------|
| Multi-format Log Parsing | k8s/vector-configmap.yaml | 397-475 |
| K8s Event Severity Mapping | k8s/vector-configmap.yaml | 126-191 |
| Expanded Error Patterns | kg/graph-builder.go | 810-902 |
| Severity Escalation | kg/graph-builder.go | 629-661 |
| Incident Clustering | kg/graph-builder.go | 663-705 |
| RCA Confidence Scoring | kg/graph-builder.go | 707-769 |
| Enhanced Schema | kg/graph-builder.go | 241-270 |
| Enhanced Event Handling | kg/graph-builder.go | 860-907 |

---

## Expected Metrics

- **RCA Links:** 7,879+
- **High-Severity Events:** 2,712+
- **Error Patterns:** 40+ across 10 categories
- **Confidence Range:** 0.40-0.95
- **Escalation Window:** 5 minutes
- **Escalation Threshold:** 3 repeats
- **Incident Clustering:** 2+ events in 5-min window

---

## Quick Test

```bash
# 1. Check all pods running
kubectl get pods -n observability

# 2. Access Neo4j
kubectl port-forward -n observability pod/neo4j-0 7474:7474 7687:7687 &

# 3. Run test queries (see Essential Queries section)

# 4. Verify confidence scores
# (May be 0 initially - wait for new events after Kafka stabilizes)
```

---

## Documentation

- **Full Guide:** [README.md](README.md)
- **Testing Guide:** [TESTING_GUIDE.md](TESTING_GUIDE.md)
- **Main Project:** [../../README.md](../../README.md)

---

## Support

### Check Logs
```bash
# kg-builder
kubectl logs -n observability -l app=kg-builder --tail=100

# vector-logs
kubectl logs -n observability -l app=vector-logs --tail=100

# kafka
kubectl logs -n observability kafka-0 --tail=100

# neo4j
kubectl logs -n observability neo4j-0 --tail=100
```

### Common Issues
1. **No confidence scores** → Wait for Kafka to stabilize and new events to flow
2. **Kafka OOMKilled** → Increase memory limits (see troubleshooting)
3. **Vector-logs crash** → VRL syntax errors (already fixed in configmap)
4. **Neo4j connection** → Check port-forward is running

---

## What's Enhanced

✅ Multi-format log parsing (JSON, glog, plain text)
✅ K8s event severity mapping (15+ mappings)
✅ Expanded error patterns (40+ patterns)
✅ Severity escalation (WARNING→ERROR→FATAL)
✅ Incident clustering (groups related events)
✅ RCA confidence scoring (0.40-0.95)
✅ Enhanced Neo4j schema (indexes for fast queries)

**Target Accuracy:** 90%+
**Status:** All enhancements deployed and operational
