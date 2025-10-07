# KGroot Access Guide

## Quick Access Commands

### Neo4j Browser Access

**Credentials:**
- Username: `neo4j`
- Password: `anuragvishwa`

**Method 1: Port Forward (Recommended)**
```bash
kubectl port-forward -n observability svc/neo4j-external 7474:7474 7687:7687
```
Then open: **http://localhost:7474**

**Method 2: Minikube Service**
```bash
minikube service neo4j-external -n observability --url
# Use the first URL (port 7474)
```

**Method 3: NodePort Direct**
```bash
# Get the URL
echo "http://$(minikube ip):30474"
# Open this URL in your browser
```

---

### Kafka UI Access

**Method 1: Port Forward**
```bash
kubectl port-forward -n observability svc/kafka-ui 8080:8080
```
Then open: **http://localhost:8080**

**Method 2: Minikube Service (Opens Automatically)**
```bash
minikube service kafka-ui -n observability
```

**Method 3: NodePort Direct**
```bash
# Get the URL
echo "http://$(minikube ip):30777"
# Open this URL in your browser
```

---

## Useful Neo4j Queries

Once you're in Neo4j Browser (http://localhost:7474), try these:

### 1. Check Total Nodes
```cypher
MATCH (n)
RETURN count(n) AS total_nodes;
```

### 2. See All Relationship Types
```cypher
MATCH ()-[r]->()
RETURN type(r) AS relationship_type, count(r) AS count
ORDER BY count DESC;
```

### 3. View RCA (Root Cause Analysis) Chains
```cypher
MATCH path = (source)-[:POTENTIAL_CAUSE*1..3]->(target)
WHERE source:Alert OR source:Event
RETURN path
LIMIT 25;
```

### 4. Find Failed Pods and Their Causes
```cypher
MATCH (pod:Resource {kind: 'Pod'})
WHERE pod.phase = 'Failed' OR pod.ready = 'false'
OPTIONAL MATCH path = (pod)<-[:POTENTIAL_CAUSE*1..3]-(cause)
RETURN pod.name AS failed_pod,
       pod.namespace AS namespace,
       collect(cause.name) AS potential_causes
LIMIT 10;
```

### 5. View Recent Events with Context
```cypher
MATCH (e:Event)
WHERE e.timestamp > datetime() - duration('PT1H')
OPTIONAL MATCH (e)-[:ABOUT]->(resource)
RETURN e.message AS event,
       e.reason AS reason,
       resource.kind AS resource_type,
       resource.name AS resource_name
ORDER BY e.timestamp DESC
LIMIT 20;
```

### 6. See Resource Dependencies
```cypher
MATCH path = (a:Resource)-[r:CONTROLS|SELECTS|RUNS_ON*1..2]->(b:Resource)
RETURN path
LIMIT 50;
```

---

## Checking System Health

### Check All Pods
```bash
kubectl get pods -n observability
```

### Check kg-builder Logs
```bash
kubectl logs -n observability -l app=kg-builder --tail=50 -f
```

### Check Kafka Consumer Status
```bash
kubectl exec -n observability kafka-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group kg-builder --describe
```

### Check State-Watcher Logs
```bash
kubectl logs -n observability -l app=state-watcher --tail=50 -f
```

### Check Alerts-Enricher Logs
```bash
kubectl logs -n observability -l app=alerts-enricher --tail=50 -f
```

---

## Troubleshooting Access Issues

### Neo4j Not Connecting

**Issue:** "Unable to connect" or timeout errors

**Solutions:**
1. Check if port-forward is running:
   ```bash
   ps aux | grep "port-forward.*7474"
   ```

2. Kill old port-forwards and restart:
   ```bash
   pkill -f "port-forward.*7474"
   kubectl port-forward -n observability svc/neo4j-external 7474:7474 7687:7687
   ```

3. Check if Neo4j pod is ready:
   ```bash
   kubectl get pods -n observability -l app=neo4j
   kubectl logs -n observability neo4j-0 --tail=20
   ```

### Kafka UI Not Loading

**Issue:** Page doesn't load or connection refused

**Solutions:**
1. Check if port-forward is running:
   ```bash
   ps aux | grep "port-forward.*8080"
   ```

2. Use minikube service instead (easier):
   ```bash
   minikube service kafka-ui -n observability
   ```

3. Check kafka-ui pod:
   ```bash
   kubectl get pods -n observability -l app=kafka-ui
   kubectl logs -n observability -l app=kafka-ui --tail=20
   ```

### Port Already in Use

**Issue:** "bind: address already in use"

**Solution:**
```bash
# Find what's using the port (e.g., 7474)
lsof -i :7474

# Kill the process
kill -9 <PID>

# Or use a different local port
kubectl port-forward -n observability svc/neo4j-external 7475:7474 7688:7687
# Then access via http://localhost:7475
```

---

## Current System Status

```
✅ Neo4j: Running (2,599 nodes, 2,327 RCA links)
✅ Kafka: Running (15+ topics)
✅ kg-builder: Running (LAG=0, all messages processed)
✅ state-watcher: Running (watching K8s resources)
✅ alerts-enricher: Running (enriching alerts)
```

Run `./VERIFY_DEPLOYMENT.sh` to check current status anytime!
