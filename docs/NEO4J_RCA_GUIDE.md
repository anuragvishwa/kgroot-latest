# Neo4j RCA (Root Cause Analysis) Guide

## Current Implementation Analysis

### What's Actually Being Used ✅

Based on graph-builder.go analysis:

| Topic | Used | Purpose |
|-------|------|---------|
| `state.k8s.resource` | ✅ Yes | Creates Resource nodes (Pods, Deployments, Services, etc.) |
| `state.k8s.topology` | ✅ Yes | Creates relationships (SELECTS, RUNS_ON, CONTROLS) |
| `events.normalized` | ✅ Yes | Creates Episodic nodes (K8s events, Prom alerts) |
| `logs.normalized` | ✅ Yes | Creates Episodic nodes from pod logs |
| `state.prom.targets` | ✅ Yes | Creates PromTarget nodes |
| `state.prom.rules` | ✅ Yes | Stores Prometheus alert/recording rules |
| **`alerts.enriched`** | ❌ **NO** | **Not consumed by graph-builder** |
| `graph.commands` | ✅ Yes | Manual graph manipulation commands |

### alerts.enriched Topic - NOT USED ⚠️

**Status**: `alerts-enricher` produces to this topic, but **graph-builder doesn't consume it**.

**Why it exists**:
- Originally designed for enriched alert data with K8s context
- Currently, `events.normalized` already contains both K8s events AND Prometheus alerts
- `alerts.enriched` is **redundant** in current architecture

**Recommendation**:
- ✅ **Keep alerts-enricher running** - it's working correctly
- ⚠️ **Not critical for RCA** - graph-builder uses `events.normalized` directly
- 💡 **Future use**: Could be used for external alert consumers or dashboards

---

## Graph Schema

### Node Types

```cypher
// Check current node distribution
MATCH (n) RETURN labels(n)[0] as type, count(n) as count ORDER BY count DESC

// Expected output:
// "Episodic"   - 1063 (events + logs)
// "Resource"   - 149  (Pods, Services, Deployments, etc.)
// "PromTarget" - 14   (Prometheus scrape targets)
```

### 1. Resource Nodes

**Properties:**
- `uid` - Kubernetes UID (unique)
- `kind` - Pod, Service, Deployment, etc.
- `namespace` - K8s namespace
- `name` - Resource name
- `cluster` - Cluster name
- `labels` - K8s labels (map)
- `node` - Node name (for Pods)
- `podIP` - Pod IP address
- `image` - Container image (for Pods)
- `updatedAt` - Last update timestamp

**Query:**
```cypher
// List all resource types
MATCH (r:Resource)
RETURN r.kind as kind, count(r) as count
ORDER BY count DESC

// Find a specific pod
MATCH (r:Resource {kind: 'Pod', name: 'vector-6bc489d745-fzltd'})
RETURN r
```

### 2. Episodic Nodes (Events & Logs)

**Properties:**
- `eventId` - Unique event ID
- `eventTime` - When the event occurred
- `etype` - Event type (k8s.event, k8s.log, prom.alert)
- `severity` - NORMAL, WARNING, ERROR, CRITICAL, FATAL
- `reason` - Event reason (OOMKilled, CrashLoopBackOff, etc.)
- `message` - Full event/log message
- `subjectKind`, `subjectNS`, `subjectName` - What the event is about

**Query:**
```cypher
// Count events by severity
MATCH (e:Episodic)
RETURN e.severity as severity, count(e) as count
ORDER BY count DESC

// Find all ERROR and FATAL events
MATCH (e:Episodic)
WHERE e.severity IN ['ERROR', 'FATAL', 'CRITICAL']
RETURN e.eventTime, e.severity, e.reason, e.message
ORDER BY e.eventTime DESC
LIMIT 20

// Find events for a specific pod
MATCH (e:Episodic)
WHERE e.subjectKind = 'Pod' AND e.subjectName CONTAINS 'vector'
RETURN e.eventTime, e.severity, e.reason, e.message
ORDER BY e.eventTime DESC
LIMIT 10
```

### 3. PromTarget Nodes

**Properties:**
- `scrapeUrl` - Prometheus scrape endpoint
- `labels` - Target labels
- `health` - up/down/unknown
- `lastScrape` - Last scrape timestamp
- `lastError` - Error message if failed

**Query:**
```cypher
// List all Prometheus targets
MATCH (pt:PromTarget)
RETURN pt.scrapeUrl, pt.health, pt.lastError
LIMIT 20

// Find unhealthy targets
MATCH (pt:PromTarget)
WHERE pt.health <> 'up'
RETURN pt.scrapeUrl, pt.health, pt.lastError
```

---

## Relationships

### Available Relationship Types

```cypher
// List all relationship types
MATCH ()-[r]->()
RETURN type(r) as relType, count(r) as count
ORDER BY count DESC
```

**Common types:**
- `SELECTS` - Service → Pod (via label selector)
- `RUNS_ON` - Pod → Node
- `CONTROLS` - Deployment → ReplicaSet → Pod
- `OWNS` - General ownership relationships

### Topology Queries

```cypher
// Find all pods selected by a service
MATCH (svc:Resource {kind: 'Service', name: 'prometheus-kube-prometheus-prometheus'})
      -[:SELECTS]->(pod:Resource {kind: 'Pod'})
RETURN pod.name, pod.namespace, pod.podIP

// Find which node a pod runs on
MATCH (pod:Resource {kind: 'Pod', name: 'vector-6bc489d745-fzltd'})
      -[:RUNS_ON]->(node:Resource {kind: 'Node'})
RETURN node.name

// Find deployment hierarchy
MATCH path = (deploy:Resource {kind: 'Deployment', name: 'vector'})
             -[:CONTROLS*]->(pod:Resource {kind: 'Pod'})
RETURN path
LIMIT 5
```

---

## RCA Queries

### 1. Find Root Cause of Pod Failures

```cypher
// Find a failing pod and all related events
MATCH (pod:Resource {kind: 'Pod'})
WHERE pod.name CONTAINS 'state-watcher'
OPTIONAL MATCH (e:Episodic)
WHERE e.subjectKind = 'Pod'
  AND e.subjectName = pod.name
  AND e.severity IN ['ERROR', 'FATAL', 'CRITICAL']
RETURN pod.name, pod.namespace,
       collect({
         time: e.eventTime,
         severity: e.severity,
         reason: e.reason,
         message: e.message
       }) as events
ORDER BY pod.updatedAt DESC
LIMIT 10
```

**Expected Output:**
```
pod.name                      | pod.namespace | events
------------------------------|---------------|------------------
state-watcher-77f896977c-k87bh| observability | [{time: "2025-10-08...", severity: "ERROR", reason: "BackOff", message: "..."}]
```

### 2. Find Impact Radius (Blast Radius)

```cypher
// Given a failing pod, find all affected services and dependents
MATCH (pod:Resource {kind: 'Pod', name: 'kafka-0'})
OPTIONAL MATCH (svc:Resource {kind: 'Service'})-[:SELECTS]->(pod)
OPTIONAL MATCH (pod)-[:RUNS_ON]->(node:Resource {kind: 'Node'})
OPTIONAL MATCH (deploy:Resource)-[:CONTROLS*]->(pod)
RETURN pod.name as failingPod,
       collect(DISTINCT svc.name) as affectedServices,
       collect(DISTINCT deploy.name) as owningDeployments,
       node.name as runningOnNode
```

**Expected Output:**
```
failingPod | affectedServices          | owningDeployments | runningOnNode
-----------|---------------------------|-------------------|---------------
kafka-0    | ['kafka', 'kafka-headless']| ['kafka']        | minikube
```

### 3. Time-Based Correlation (Causal Chain)

```cypher
// Find cascading failures within 5-minute window
MATCH (e1:Episodic)
WHERE e1.severity IN ['ERROR', 'FATAL', 'CRITICAL']
  AND e1.eventTime > datetime() - duration('PT1H') // Last hour
WITH e1
MATCH (e2:Episodic)
WHERE e2.eventTime >= e1.eventTime
  AND e2.eventTime <= e1.eventTime + duration('PT5M')
  AND e2.severity IN ['ERROR', 'FATAL', 'CRITICAL']
  AND e2.eventId <> e1.eventId
RETURN e1.eventTime as rootCauseTime,
       e1.subjectName as rootCausePod,
       e1.reason as rootCauseReason,
       e1.message as rootCauseMessage,
       collect({
         time: e2.eventTime,
         pod: e2.subjectName,
         reason: e2.reason,
         message: e2.message
       }) as cascadingFailures
ORDER BY rootCauseTime DESC
LIMIT 10
```

**Expected Output:**
```
rootCauseTime        | rootCausePod | rootCauseReason | cascadingFailures
---------------------|--------------|-----------------|-------------------
2025-10-08T08:10:00Z | kafka-0      | CrashLoopBackOff| [{time: "08:10:05", pod: "kg-builder", reason: "BackOff", ...}]
```

### 4. Find All Errors Related to a Namespace

```cypher
// Namespace-wide issue detection
MATCH (e:Episodic)
WHERE e.subjectNS = 'observability'
  AND e.severity IN ['ERROR', 'FATAL', 'CRITICAL']
  AND e.eventTime > datetime() - duration('PT1H')
RETURN e.subjectKind as resourceType,
       e.subjectName as resourceName,
       e.severity,
       e.reason,
       e.message,
       e.eventTime
ORDER BY e.eventTime DESC
LIMIT 50
```

### 5. Log Pattern Analysis (Find Common Errors)

```cypher
// Find most common error patterns in logs
MATCH (e:Episodic)
WHERE e.etype = 'k8s.log'
  AND e.severity IN ['ERROR', 'FATAL']
  AND e.eventTime > datetime() - duration('PT6H')
RETURN e.subjectName as pod,
       e.severity,
       substring(e.message, 0, 100) as errorPattern,
       count(*) as occurrences
ORDER BY occurrences DESC
LIMIT 20
```

### 6. Service Dependency Map

```cypher
// Build service dependency graph
MATCH (svc1:Resource {kind: 'Service'})
MATCH (pod:Resource {kind: 'Pod'})<-[:SELECTS]-(svc1)
MATCH (svc2:Resource {kind: 'Service'})-[:SELECTS]->(pod)
WHERE svc1 <> svc2
RETURN DISTINCT svc1.name as service,
       svc2.name as dependsOn,
       collect(DISTINCT pod.name) as sharedPods
LIMIT 50
```

### 7. Health Dashboard Query

```cypher
// Overall cluster health summary
MATCH (r:Resource)
OPTIONAL MATCH (e:Episodic)
WHERE e.eventTime > datetime() - duration('PT15M')
  AND e.severity IN ['ERROR', 'FATAL', 'CRITICAL']
RETURN
  count(DISTINCT r) as totalResources,
  count(DISTINCT CASE WHEN r.kind = 'Pod' THEN r END) as totalPods,
  count(DISTINCT e) as recentErrors,
  count(DISTINCT CASE WHEN e.severity = 'FATAL' THEN e END) as fatalErrors,
  count(DISTINCT CASE WHEN e.severity = 'ERROR' THEN e END) as errors,
  count(DISTINCT CASE WHEN e.severity = 'CRITICAL' THEN e END) as criticalErrors
```

**Expected Output:**
```
totalResources | totalPods | recentErrors | fatalErrors | errors | criticalErrors
---------------|-----------|--------------|-------------|--------|---------------
149           | 43        | 15           | 1           | 12     | 2
```

---

## Advanced RCA: Find Root Cause with Context

```cypher
// Complete RCA for a specific alert/issue
// Step 1: Find the issue
MATCH (alert:Episodic {reason: 'CrashLoopBackOff'})
WHERE alert.eventTime > datetime() - duration('PT1H')

// Step 2: Get the affected resource
MATCH (pod:Resource {kind: 'Pod', name: alert.subjectName})

// Step 3: Find related events (before and after)
OPTIONAL MATCH (relatedEvent:Episodic)
WHERE relatedEvent.subjectName = pod.name
  AND relatedEvent.eventTime >= alert.eventTime - duration('PT10M')
  AND relatedEvent.eventTime <= alert.eventTime + duration('PT5M')

// Step 4: Get topology context
OPTIONAL MATCH (svc:Resource {kind: 'Service'})-[:SELECTS]->(pod)
OPTIONAL MATCH (deploy:Resource)-[:CONTROLS*]->(pod)
OPTIONAL MATCH (pod)-[:RUNS_ON]->(node:Resource {kind: 'Node'})

// Step 5: Get recent logs
OPTIONAL MATCH (log:Episodic)
WHERE log.etype = 'k8s.log'
  AND log.subjectName = pod.name
  AND log.eventTime >= alert.eventTime - duration('PT5M')
  AND log.eventTime <= alert.eventTime
  AND log.severity IN ['ERROR', 'FATAL']

RETURN
  alert.eventTime as alertTime,
  pod.name as affectedPod,
  pod.namespace as namespace,
  pod.image as containerImage,
  node.name as node,
  collect(DISTINCT svc.name) as exposedByServices,
  collect(DISTINCT deploy.name) as ownedByDeployments,
  collect(DISTINCT {
    time: relatedEvent.eventTime,
    severity: relatedEvent.severity,
    reason: relatedEvent.reason,
    message: substring(relatedEvent.message, 0, 100)
  }) as timelineEvents,
  collect(DISTINCT {
    time: log.eventTime,
    severity: log.severity,
    message: substring(log.message, 0, 200)
  }) as errorLogs
ORDER BY alertTime DESC
LIMIT 5
```

---

## Testing Your Setup

### 1. Verify Graph is Populated

```cypher
// Check node counts
MATCH (n)
RETURN labels(n)[0] as nodeType, count(n) as count
ORDER BY count DESC

// Expected:
// Episodic:   1000+  (events + logs)
// Resource:   100+   (K8s resources)
// PromTarget: 10+    (Prometheus targets)
```

### 2. Verify Relationships Exist

```cypher
// Check relationship counts
MATCH ()-[r]->()
RETURN type(r) as relType, count(r) as count
ORDER BY count DESC

// Expected:
// SELECTS: 50+   (Service → Pod)
// CONTROLS: 30+  (Deployment → Pod)
// RUNS_ON: 40+   (Pod → Node)
```

### 3. Verify Recent Events

```cypher
// Check recent events are being ingested
MATCH (e:Episodic)
WHERE e.eventTime > datetime() - duration('PT5M')
RETURN count(e) as recentEvents

// Should return: 10+ (depends on cluster activity)
```

### 4. Verify Logs are Flowing

```cypher
// Check recent log entries
MATCH (e:Episodic)
WHERE e.etype = 'k8s.log'
  AND e.eventTime > datetime() - duration('PT1M')
RETURN count(e) as recentLogs

// Should return: 50+ (depends on pod activity)
```

---

## Production Readiness Assessment

### ✅ What's Production-Ready

1. **Graph Schema**: Well-designed, normalized structure
2. **Data Ingestion**: Real-time Kafka → Neo4j pipeline
3. **Topology Tracking**: K8s relationships properly modeled
4. **Event Correlation**: Time-based event linking works
5. **Log Aggregation**: Pod logs with severity detection

### ⚠️ What Needs Improvement for Production

1. **Index Creation** - Add indexes for faster queries:
   ```cypher
   CREATE INDEX resource_uid IF NOT EXISTS FOR (r:Resource) ON (r.uid);
   CREATE INDEX resource_name IF NOT EXISTS FOR (r:Resource) ON (r.name, r.namespace);
   CREATE INDEX episodic_time IF NOT EXISTS FOR (e:Episodic) ON (e.eventTime);
   CREATE INDEX episodic_severity IF NOT EXISTS FOR (e:Episodic) ON (e.severity);
   CREATE INDEX episodic_subject IF NOT EXISTS FOR (e:Episodic) ON (e.subjectName);
   ```

2. **TTL/Retention Policy** - Implement data cleanup:
   ```cypher
   // Delete episodic events older than 7 days
   MATCH (e:Episodic)
   WHERE e.eventTime < datetime() - duration('P7D')
   DETACH DELETE e
   ```

3. **Monitoring & Alerting**:
   - Add Prometheus metrics for graph-builder
   - Alert on consumer lag
   - Monitor Neo4j query performance

4. **High Availability**:
   - Neo4j cluster (3+ nodes)
   - Multiple graph-builder instances (Kafka consumer groups)
   - Load balancer for Neo4j reads

5. **Security**:
   - ✅ Neo4j authentication enabled
   - ⚠️ Add RBAC for different query users
   - ⚠️ Encrypt Neo4j → graph-builder connection
   - ⚠️ Add network policies in K8s

6. **Performance Tuning**:
   ```properties
   # Neo4j config optimizations
   dbms.memory.heap.initial_size=2G
   dbms.memory.heap.max_size=4G
   dbms.memory.pagecache.size=2G
   ```

7. **Backup & Recovery**:
   - Automated Neo4j backups
   - Point-in-time recovery
   - Disaster recovery plan

---

## state.prom.rules - Is It Required?

### Current Usage: ✅ YES, it's being consumed

**Purpose**: Stores Prometheus alerting/recording rules metadata

**Use case**:
- Track which alerts are configured
- Link fired alerts to their rule definitions
- Useful for alert lifecycle tracking

**Query to see what's stored:**
```cypher
// Not stored as nodes currently, would need code update
// Currently just consumed but might be used for future features
```

**Recommendation**: **Keep it** - even if not creating nodes yet, it's prepared for future RCA enhancements where you'd want to see:
- Which alert rule triggered
- Alert rule configuration (threshold, duration, etc.)
- Changes to alert rules over time

---

## kg-init - Do You Need It?

### Answer: ❌ NO, it's commented out in docker-compose.yml

**Why?**
- `graph-builder` automatically creates Neo4j schema on startup
- No separate initialization needed
- `kg-init` was probably for creating indexes/constraints

**Recommendation**:
- ✅ Keep it commented out (as it is now)
- 💡 Use it only if you want to pre-create indexes before graph-builder starts

---

## Quick Reference Card

```bash
# Access Neo4j Browser
open http://localhost:7474
# Username: neo4j
# Password: anuragvishwa

# Quick health check
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (n) RETURN labels(n)[0] as type, count(n) ORDER BY count DESC"

# Find recent errors
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic) WHERE e.severity IN ['ERROR','FATAL'] AND e.eventTime > datetime()-duration('PT1H') RETURN e.subjectName, e.reason, e.message LIMIT 10"
```

---

## Next Steps to Improve RCA

1. **Create indexes** (see above)
2. **Add TTL cleanup job** (cronjob to delete old events)
3. **Build Grafana dashboard** querying Neo4j
4. **Add ML-based anomaly detection** on event patterns
5. **Create RCA API** (REST/GraphQL wrapper around Neo4j)
6. **Add alert → log correlation** (automatic linking)

---

**Your setup is functional and can do RCA!** It needs production hardening (indexes, HA, monitoring) but the core architecture is solid.
