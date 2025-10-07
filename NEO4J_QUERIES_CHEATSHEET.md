# Neo4j RCA Queries - Cheatsheet

Quick reference for common RCA queries in Neo4j Browser.

## Access Neo4j

```bash
# Port-forward Neo4j
kubectl port-forward -n observability svc/neo4j-external 7474:7474

# Open browser: http://localhost:7474
# Username: neo4j
# Password: anuragvishwa
```

---

## Basic Exploration Queries

### Count All Nodes and Relationships

```cypher
// Count all node types
MATCH (n)
RETURN labels(n) AS type, count(*) AS count
ORDER BY count DESC;

// Count all relationship types
MATCH ()-[r]->()
RETURN type(r) AS relationship, count(*) AS count
ORDER BY count DESC;
```

### View Graph Schema

```cypher
CALL db.schema.visualization();
```

### List All Constraints and Indexes

```cypher
CALL db.constraints();
CALL db.indexes();
```

---

## Resource Queries

### Find All Pods

```cypher
MATCH (p:Resource:Pod)
RETURN p.name, p.ns, p.node, p.podIP, p.image
LIMIT 20;
```

### Find All Services

```cypher
MATCH (s:Resource:Service)
RETURN s.name, s.ns, s.labels_kv
LIMIT 20;
```

### Find Pod-to-Service Mappings

```cypher
MATCH (svc:Resource:Service)-[:SELECTS]->(pod:Resource:Pod)
RETURN svc.name AS service,
       svc.ns AS namespace,
       collect(pod.name) AS pods
ORDER BY service;
```

### Find Deployments and Their Pods

```cypher
MATCH (deploy:Resource:Deployment)-[:CONTROLS]->(pod:Resource:Pod)
RETURN deploy.name AS deployment,
       deploy.ns AS namespace,
       collect(pod.name) AS pods
ORDER BY deployment;
```

### Find Pods on Specific Node

```cypher
MATCH (pod:Resource:Pod)-[:RUNS_ON]->(node:Resource:Node)
WHERE node.name = 'minikube'  // Change to your node name
RETURN pod.name, pod.ns
ORDER BY pod.ns, pod.name;
```

---

## Event Queries

### Recent Events (Last Hour)

```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({hours: 1})
RETURN e.eid, e.etype, e.severity, e.reason, e.message, e.event_time
ORDER BY e.event_time DESC
LIMIT 50;
```

### Filter by Severity

```cypher
MATCH (e:Episodic)
WHERE e.severity IN ['ERROR', 'CRITICAL']
  AND e.event_time > datetime() - duration({hours: 24})
RETURN e.reason, e.message, e.event_time
ORDER BY e.event_time DESC;
```

### Filter by Event Type

```cypher
// K8s events
MATCH (e:Episodic {etype: 'k8s.event'})
WHERE e.event_time > datetime() - duration({hours: 1})
RETURN e.reason, e.message, e.event_time
LIMIT 20;

// Prometheus alerts
MATCH (e:Episodic {etype: 'prom.alert'})
WHERE e.event_time > datetime() - duration({hours: 1})
RETURN e.reason, e.message, e.severity, e.event_time
LIMIT 20;

// Log events
MATCH (e:Episodic {etype: 'k8s.log'})
WHERE e.severity IN ['ERROR', 'FATAL']
  AND e.event_time > datetime() - duration({hours: 1})
RETURN e.reason, e.message, e.event_time
LIMIT 20;
```

### Events About Specific Pod

```cypher
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource:Pod)
WHERE pod.name CONTAINS 'test-crashloop'  // Change pod name
RETURN e.reason, e.message, e.severity, e.event_time
ORDER BY e.event_time DESC;
```

---

## RCA Queries (Root Cause Analysis)

### Find Root Cause of Specific Event

```cypher
// Replace 'YOUR_EVENT_ID' with actual event ID
MATCH (error:Episodic {eid: 'YOUR_EVENT_ID'})
MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(error)
RETURN cause.reason AS root_cause,
       cause.severity AS severity,
       cause.message AS description,
       pc.hops AS distance,
       duration.between(cause.event_time, error.event_time) AS time_lag
ORDER BY pc.hops ASC, cause.event_time DESC
LIMIT 10;
```

### Find All Causal Chains

```cypher
MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..3]->(symptom:Episodic)
WHERE root.event_time > datetime() - duration({hours: 1})
RETURN [e IN nodes(path) | e.reason] AS causal_chain,
       length(path) AS chain_length,
       root.event_time AS started
ORDER BY chain_length DESC, started DESC
LIMIT 10;
```

### Find Common Failure Patterns

```cypher
// Find frequent reason pairs (cause → effect)
MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(effect:Episodic)
WHERE cause.event_time > datetime() - duration({days: 7})
RETURN cause.reason AS root_cause,
       effect.reason AS symptom,
       count(*) AS occurrences
ORDER BY occurrences DESC
LIMIT 20;
```

### Trace Cascading Failures

```cypher
// Find multi-hop cascading failures
MATCH path = (e1:Episodic)-[:POTENTIAL_CAUSE]->(e2:Episodic)-[:POTENTIAL_CAUSE]->(e3:Episodic)
WHERE e3.event_time > datetime() - duration({hours: 1})
WITH path, nodes(path) AS events
UNWIND events AS evt
MATCH (evt)-[:ABOUT]->(res:Resource)
RETURN [e IN events | e.reason] AS failure_chain,
       [r IN collect(DISTINCT res) | r.kind + ':' + r.name] AS affected_resources,
       events[0].event_time AS root_time,
       events[size(events)-1].event_time AS final_time
LIMIT 10;
```

---

## Test Scenario Verification

### Test 1: ImagePullBackOff

```cypher
MATCH (e:Episodic)
WHERE (e.reason CONTAINS 'Pull' OR e.reason CONTAINS 'BackOff')
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN e.reason, e.message, e.event_time
ORDER BY e.event_time DESC;

// Find affected pod
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource)
WHERE e.reason CONTAINS 'Pull'
RETURN pod.name, pod.ns, pod.image, e.message;
```

### Test 2: CrashLoopBackOff with Log Correlation

```cypher
// Find crash events
MATCH (crash:Episodic)
WHERE crash.reason CONTAINS 'BackOff'
  AND crash.event_time > datetime() - duration({minutes: 30})
RETURN crash.reason, crash.message, crash.event_time;

// Find correlated log errors
MATCH (log:Episodic {etype: 'k8s.log'})-[:ABOUT]->(pod:Resource)
WHERE log.severity IN ['ERROR', 'FATAL']
  AND pod.name CONTAINS 'test-crashloop'
  AND log.event_time > datetime() - duration({minutes: 30})
RETURN log.message, log.event_time;

// Find causal link
MATCH (log:Episodic)-[pc:POTENTIAL_CAUSE]->(crash:Episodic)
WHERE log.etype = 'k8s.log'
  AND crash.reason CONTAINS 'BackOff'
  AND log.event_time > datetime() - duration({minutes: 30})
RETURN log.message AS root_cause,
       crash.reason AS symptom,
       pc.hops,
       duration.between(log.event_time, crash.event_time) AS lag;
```

### Test 3: OOMKilled

```cypher
MATCH (e:Episodic)
WHERE e.reason CONTAINS 'OOM' OR e.message CONTAINS 'OOMKilled'
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN e.reason, e.message, e.event_time;

// Check pod status
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource)
WHERE e.reason CONTAINS 'OOM'
RETURN pod.name, pod.status_json;
```

### Test 4: Service Selector Mismatch

```cypher
// Find service with no endpoints
MATCH (svc:Resource:Service {name: 'test-backend'})
OPTIONAL MATCH (svc)-[:SELECTS]->(pod:Resource:Pod)
RETURN svc.name, svc.ns, svc.labels_json, count(pod) AS pod_count;

// Find orphaned pods
MATCH (pod:Resource:Pod)
WHERE pod.labels_kv CONTAINS 'app=backend'
  AND pod.ns = 'default'
WITH pod
MATCH (svc:Resource:Service {name: 'test-backend'})
WHERE NOT exists((svc)-[:SELECTS]->(pod))
RETURN svc.name AS service,
       pod.name AS orphaned_pod,
       svc.labels_json AS svc_selector,
       pod.labels_json AS pod_labels;
```

### Test 5: Cascading Failure (DB → API → Frontend)

```cypher
// Find all failures in cascade test
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource)
WHERE (pod.name CONTAINS 'test-db'
    OR pod.name CONTAINS 'test-api'
    OR pod.name CONTAINS 'test-frontend')
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN pod.name AS component,
       e.reason AS failure,
       e.severity,
       e.event_time
ORDER BY e.event_time ASC;

// Find root cause (earliest)
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource)
WHERE (pod.name CONTAINS 'test-db' OR pod.name CONTAINS 'test-api' OR pod.name CONTAINS 'test-frontend')
  AND e.severity IN ['ERROR', 'CRITICAL']
  AND e.event_time > datetime() - duration({minutes: 30})
WITH e, pod
ORDER BY e.event_time ASC
LIMIT 1
RETURN pod.name AS root_component, e.reason, e.message;

// Visualize cascade
MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..3]->(symptom:Episodic)
WHERE root.event_time > datetime() - duration({minutes: 30})
WITH path, nodes(path) AS chain
WHERE size(chain) > 1
UNWIND chain AS evt
MATCH (evt)-[:ABOUT]->(res:Resource)
WHERE res.name CONTAINS 'test-'
RETURN path, chain, collect(DISTINCT res) AS resources
LIMIT 5;
```

### Test 6: Missing Environment Variable

```cypher
// Find FATAL log about env var
MATCH (e:Episodic {etype: 'k8s.log'})
WHERE e.severity = 'FATAL'
  AND e.message CONTAINS 'environment variable'
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN e.reason, e.message, e.event_time;

// Link to crash
MATCH (log:Episodic {etype: 'k8s.log'})-[:ABOUT]->(pod:Resource)
WHERE log.message CONTAINS 'environment variable'
WITH log, pod
MATCH (crash:Episodic)-[:ABOUT]->(pod)
WHERE crash.reason CONTAINS 'BackOff'
  AND crash.event_time > log.event_time
RETURN pod.name, log.message AS cause, crash.reason AS effect;
```

---

## Topology Visualization

### Visualize Full Cluster Topology

```cypher
MATCH (n:Resource)
WHERE n.kind IN ['Pod', 'Service', 'Deployment', 'Node']
OPTIONAL MATCH (n)-[r]-(m:Resource)
RETURN n, r, m
LIMIT 100;
```

### Visualize Specific Namespace

```cypher
MATCH (n:Resource)
WHERE n.ns = 'default'  // Change namespace
OPTIONAL MATCH (n)-[r]-(m:Resource)
WHERE m.ns = 'default'
RETURN n, r, m
LIMIT 100;
```

### Visualize Service Dependencies

```cypher
MATCH (svc:Resource:Service)-[:SELECTS]->(pod:Resource:Pod)
OPTIONAL MATCH (pod)-[:RUNS_ON]->(node:Resource:Node)
OPTIONAL MATCH (deploy:Resource:Deployment)-[:CONTROLS]->(pod)
RETURN svc, pod, node, deploy
LIMIT 50;
```

---

## Prometheus Integration

### Find Prometheus Targets

```cypher
MATCH (t:PromTarget)
RETURN t.tid, t.labels_json, t.health, t.lastScrape
LIMIT 20;

// Find unhealthy targets
MATCH (t:PromTarget)
WHERE t.health <> 'UP'
RETURN t.tid, t.health, t.lastError;
```

### Find Alerting Rules

```cypher
MATCH (r:Rule)
WHERE r.type = 'alerting'
RETURN r.name, r.group, r.expr, r.labels_json
LIMIT 20;
```

### Link Alerts to Rules

```cypher
MATCH (rule:Rule)-[:EMITS]->(alert:Episodic)
RETURN rule.name AS rule,
       alert.reason AS alert_name,
       alert.severity,
       alert.event_time
ORDER BY alert.event_time DESC
LIMIT 20;
```

---

## Cleanup and Maintenance

### Delete Old Events (Older than 30 days)

```cypher
MATCH (e:Episodic)
WHERE e.event_time < datetime() - duration({days: 30})
DETACH DELETE e;
```

### Delete All Test Data

```cypher
// Delete events related to test pods
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource)
WHERE pod.name CONTAINS 'test-'
DETACH DELETE e;

// Delete test resources
MATCH (r:Resource)
WHERE r.name CONTAINS 'test-'
DETACH DELETE r;
```

### Clear Entire Graph (USE WITH CAUTION!)

```cypher
MATCH (n)
DETACH DELETE n;
```

---

## Performance Queries

### Find Slowest Queries

```cypher
// Check query performance
CALL dbms.listQueries() YIELD query, elapsedTimeMillis, queryId
WHERE elapsedTimeMillis > 1000
RETURN query, elapsedTimeMillis
ORDER BY elapsedTimeMillis DESC;
```

### Graph Statistics

```cypher
// Node count by label
MATCH (n)
RETURN labels(n) AS label, count(*) AS count
ORDER BY count DESC;

// Relationship count by type
MATCH ()-[r]->()
RETURN type(r) AS relationship, count(*) AS count
ORDER BY count DESC;

// Average causal chain length
MATCH path = ()-[:POTENTIAL_CAUSE*]->()
RETURN avg(length(path)) AS avg_chain_length,
       max(length(path)) AS max_chain_length;
```

---

## Export Data

### Export Events to JSON

```cypher
// Export recent events
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({hours: 24})
RETURN {
  eid: e.eid,
  etype: e.etype,
  severity: e.severity,
  reason: e.reason,
  message: e.message,
  event_time: toString(e.event_time)
} AS event
LIMIT 1000;
```

### Export Topology

```cypher
MATCH (svc:Resource:Service)-[:SELECTS]->(pod:Resource:Pod)
RETURN {
  service: svc.name,
  namespace: svc.ns,
  pods: collect(pod.name)
} AS topology;
```

---

## Tips

1. **Use LIMIT**: Always add `LIMIT` to queries during exploration to avoid overwhelming results

2. **Filter by Time**: Use time filters for better performance:
   ```cypher
   WHERE e.event_time > datetime() - duration({hours: 1})
   ```

3. **Visualize in Browser**: Click the graph icon (📊) in Neo4j Browser for visual exploration

4. **Export Results**: Click the download icon to export query results as CSV or JSON

5. **Save Favorites**: Use `:play favorites` in Neo4j Browser to save frequently used queries

6. **Profile Queries**: Use `PROFILE` or `EXPLAIN` prefix to analyze query performance:
   ```cypher
   PROFILE MATCH (e:Episodic) RETURN e LIMIT 10;
   ```
