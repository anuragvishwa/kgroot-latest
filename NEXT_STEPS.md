# Next Steps - After Minikube Restarts

## What Was Done

✅ **Fixed:**
1. Neo4j config issue (disabled strict validation)
2. kg-builder Dockerfile (removed problematic COPY)
3. kg-builder imagePullPolicy (set to IfNotPresent)
4. Built kg-builder Docker image
5. Loaded image into Minikube

✅ **Deployed:**
- Neo4j (StatefulSet)
- kg-builder (Deployment + ConfigMap)

✅ **.env file is correct:**
- `NEO4J_URI=neo4j://neo4j.observability.svc:7687` ✓

## Quick Start (After Minikube is Back)

### 1. Restart Minikube (if needed)

```bash
# If Minikube stopped or has connectivity issues
minikube stop
minikube start

# Wait for cluster to be ready
kubectl get nodes
```

### 2. Verify Everything is Running

```bash
cd /Users/anuragvishwa/Anurag/kgroot_latest

# Run comprehensive verification
./VERIFY_DEPLOYMENT.sh
```

This script will check:
- ✓ All pods are running
- ✓ Kafka topics exist (15+)
- ✓ Neo4j is accessible
- ✓ Knowledge graph has data
- ✓ Consumers are active
- ✓ RCA links are being created

### 3. Expected Output

**If everything is working:**
```
✅ KGroot is WORKING! Knowledge graph is being built.

Next steps:
  1. Access Neo4j Browser
  2. Run test scenarios
  3. Query the knowledge graph
```

**If partially working:**
```
⚠ KGroot is PARTIALLY working

Kafka is running but Neo4j graph is empty.
This usually means kg-builder is not running or no events yet.
```

### 4. Check Individual Components

```bash
# Check all pods
kubectl get pods -n observability

# Expected pods:
# - kafka-0 (Running)
# - neo4j-0 (Running)
# - kg-builder-* (Running)
# - vector-* (Running)
# - state-watcher-* (Running)
# - alerts-enricher-* (Running)
```

**Check kg-builder specifically:**
```bash
kubectl get pods -n observability -l app=kg-builder

# Should show:
# NAME                         READY   STATUS    RESTARTS   AGE
# kg-builder-967d779cb-xxxxx   1/1     Running   0          5m

# Check logs
kubectl logs -n observability -l app=kg-builder --tail=30

# Look for:
# - "schema ready"
# - "consuming topics: [...]"
# - No errors
```

**Check Neo4j:**
```bash
kubectl get pods -n observability -l app=neo4j

# Should show:
# NAME      READY   STATUS    RESTARTS   AGE
# neo4j-0   1/1     Running   0          10m

# Check logs
kubectl logs -n observability neo4j-0 --tail=20

# Look for:
# - "Bolt enabled on 0.0.0.0:7687"
# - "Remote interface available at http://localhost:7474/"
# - "Started."
```

### 5. Verify Consumers are Running

```bash
# List Kafka consumer groups
kubectl exec -n observability kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list

# Expected output:
# kg-builder
# alerts-enricher-alerts

# Check kg-builder consumer details
kubectl exec -n observability kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group kg-builder --describe

# Look for:
# - LAG should be 0 or low (< 100)
# - STATE should be "Stable"
# - All topics assigned to consumer
```

### 6. Verify Knowledge Graph is Being Created

```bash
# Port-forward Neo4j
kubectl port-forward -n observability svc/neo4j-external 7474:7474 &

# Or check via command line
kubectl exec -n observability neo4j-0 -- \
  cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (n) RETURN count(n) AS total_nodes;"

# Expected:
# total_nodes
# 100+  (or any number > 0)

# Check for specific node types
kubectl exec -n observability neo4j-0 -- \
  cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (n) RETURN labels(n) AS type, count(*) AS count ORDER BY count DESC;"

# Expected:
# type          count
# [:Resource]   50+
# [:Episodic]   20+
# [:Pod]        10+
# [:Service]    5+
# etc...

# Check for RCA relationships
kubectl exec -n observability neo4j-0 -- \
  cypher-shell -u neo4j -p anuragvishwa \
  "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r) AS rca_links;"

# Expected:
# rca_links
# 5+  (or any number > 0 means RCA is working!)
```

### 7. Generate Test Data (if graph is empty)

```bash
# Deploy test scenarios to generate events
kubectl apply -f test/05-cascading-failure.yaml

# Wait for events to propagate
sleep 120

# Check messages in Kafka
kubectl exec -n observability kafka-0 -- \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic events.normalized --from-beginning --max-messages 10

# Check knowledge graph again
kubectl exec -n observability neo4j-0 -- \
  cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (n) RETURN count(n) AS total;"

# Should now have data!
```

### 8. Access Neo4j Browser

```bash
# Port-forward Neo4j HTTP interface
kubectl port-forward -n observability svc/neo4j-external 7474:7474
```

Open browser: **http://localhost:7474**

- **Username:** neo4j
- **Password:** anuragvishwa

**Run sample queries:**
```cypher
// 1. Count all nodes
MATCH (n) RETURN count(n) AS total;

// 2. Show node types
MATCH (n) RETURN labels(n) AS type, count(*) AS count ORDER BY count DESC;

// 3. Show recent events
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({hours: 1})
RETURN e.reason, e.severity, e.message
ORDER BY e.event_time DESC
LIMIT 10;

// 4. Find RCA links
MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(effect:Episodic)
RETURN cause.reason AS root_cause,
       effect.reason AS symptom,
       r.hops AS distance
LIMIT 10;

// 5. Visualize pod topology
MATCH (svc:Resource:Service)-[:SELECTS]->(pod:Resource:Pod)
RETURN svc, pod
LIMIT 20;
```

## Troubleshooting

If things aren't working, see **`TROUBLESHOOTING.md`** for detailed fixes.

**Common issues:**

1. **kg-builder not running:** Check image is loaded in Minikube
2. **No data in Neo4j:** Wait 2-3 minutes or deploy test scenarios
3. **Consumer lag increasing:** Restart kg-builder pod
4. **Neo4j connection refused:** Check pod logs, may still be starting

## Full Test Suite

Once everything is verified:

```bash
# Run all test scenarios
./test/run-all-tests.sh

# This will:
# 1. Deploy 6 intentional bugs
# 2. Wait for events to propagate
# 3. Verify RCA system detected them
# 4. Show you example Neo4j queries

# Access Neo4j Browser and run queries from:
# - RCA_TESTING_GUIDE.md
# - NEO4J_QUERIES_CHEATSHEET.md
```

## Summary

**What you need to do:**

1. ✅ Restart Minikube (if needed)
2. ✅ Run `./VERIFY_DEPLOYMENT.sh`
3. ✅ Check kg-builder and Neo4j are Running
4. ✅ Verify consumers are active
5. ✅ Check knowledge graph has data
6. ✅ Access Neo4j Browser and query

**Files to refer to:**

- **`VERIFY_DEPLOYMENT.sh`** - Automated verification (run this first!)
- **`TROUBLESHOOTING.md`** - Fixes for common issues
- **`NEO4J_QUERIES_CHEATSHEET.md`** - 50+ example queries
- **`RCA_TESTING_GUIDE.md`** - Test scenarios
- **`QUICK_START.md`** - Getting started guide

**Your system is ready! Just need Minikube to come back up.** 🚀
