# 📊 Neo4j Knowledge Graph - Complete API Reference

**Version**: 1.0
**Last Updated**: 2025-10-10
**System**: KGroot RCA Platform

---

## 📑 Table of Contents

1. [Overview](#overview)
2. [Graph Schema](#graph-schema)
3. [Node Types](#node-types)
4. [Relationship Types](#relationship-types)
5. [RCA Query APIs](#rca-query-apis)
6. [Incident Analysis APIs](#incident-analysis-apis)
7. [Topology Query APIs](#topology-query-apis)
8. [Metrics & Analytics APIs](#metrics--analytics-apis)
9. [Visualization Queries](#visualization-queries)
10. [Performance Optimization](#performance-optimization)

---

## Overview

The Neo4j Knowledge Graph stores:
- **Resources**: Kubernetes objects (Pods, Services, Deployments, Nodes)
- **Episodes**: Events, logs, alerts representing incidents
- **Relationships**: Causal links (POTENTIAL_CAUSE), topology (SELECTS, RUNS_ON, CONTROLS)

### Graph Statistics
- **Nodes**: ~50,000 (Resources + Episodes)
- **Relationships**: ~150,000
- **RCA Links**: 51,568 POTENTIAL_CAUSE relationships
- **Event Types**: 37 types
- **Resource Types**: 14 types

---

## Graph Schema

### Node Labels

```cypher
// Show all node labels
CALL db.labels()
```

**Core Labels**:
- `Resource` - Kubernetes resources (Pod, Service, Deployment, etc.)
- `Episodic` - Events, logs, alerts
- `PromTarget` - Prometheus scrape targets
- `Rule` - Prometheus alerting rules

**Sub-labels (Resource types)**:
- `Resource:Pod`
- `Resource:Service`
- `Resource:Deployment`
- `Resource:ReplicaSet`
- `Resource:StatefulSet`
- `Resource:DaemonSet`
- `Resource:Node`
- `Resource:Namespace`
- `Resource:ConfigMap`
- `Resource:Secret`

### Relationship Types

```cypher
// Show all relationship types
CALL db.relationshipTypes()
```

**Topology Relationships**:
- `SELECTS` - Service → Pod
- `RUNS_ON` - Pod → Node
- `CONTROLS` - Deployment/ReplicaSet → Pod
- `OWNS` - Deployment → ReplicaSet

**Event Relationships**:
- `ABOUT` - Episodic → Resource (event affects resource)
- `POTENTIAL_CAUSE` - Episodic → Episodic (causal relationship)

### Constraints & Indexes

```cypher
// Show all constraints
CALL db.constraints()

// Show all indexes
CALL db.indexes()
```

**Existing Constraints**:
```cypher
CREATE CONSTRAINT resource_rid IF NOT EXISTS
FOR (r:Resource) REQUIRE r.rid IS UNIQUE;

CREATE CONSTRAINT episodic_eid IF NOT EXISTS
FOR (e:Episodic) REQUIRE e.eid IS UNIQUE;

CREATE CONSTRAINT promtarget_tid IF NOT EXISTS
FOR (p:PromTarget) REQUIRE p.tid IS UNIQUE;

CREATE CONSTRAINT rule_rkey IF NOT EXISTS
FOR (r:Rule) REQUIRE r.rkey IS UNIQUE;
```

**Recommended Indexes** (for performance):
```cypher
// Index on event time for temporal queries
CREATE INDEX episodic_event_time IF NOT EXISTS
FOR (e:Episodic) ON (e.event_time);

// Index on severity for filtering
CREATE INDEX episodic_severity IF NOT EXISTS
FOR (e:Episodic) ON (e.severity);

// Index on reason for pattern matching
CREATE INDEX episodic_reason IF NOT EXISTS
FOR (e:Episodic) ON (e.reason);

// Index on resource kind
CREATE INDEX resource_kind IF NOT EXISTS
FOR (r:Resource) ON (r.kind);

// Index on namespace for filtering
CREATE INDEX resource_namespace IF NOT EXISTS
FOR (r:Resource) ON (r.ns);
```

---

## Node Types

### 1. Resource Node

**Properties**:
```cypher
{
  rid: "pod:default:myapp-pod-abc123",  // Unique resource ID
  kind: "Pod",                           // Resource type
  uid: "k8s-uid-12345",                  // Kubernetes UID
  ns: "default",                         // Namespace
  name: "myapp-pod-abc123",              // Resource name
  cluster: "minikube",                   // Cluster name
  labels_kv: ["app=myapp", "env=prod"],  // Labels as array
  labels_json: "{\"app\":\"myapp\"}",    // Labels as JSON
  status_json: "{\"phase\":\"Running\"}", // Status as JSON
  spec_json: "{}",                       // Spec as JSON
  node: "minikube-node-1",               // Node name (for Pods)
  podIP: "10.244.0.5",                   // Pod IP (for Pods)
  image: "myapp:v1.2.3",                 // Container image (for Pods)
  updated_at: datetime("2025-10-10T...")  // Last update time
}
```

**Example Query**:
```cypher
// Get all pods in namespace
MATCH (p:Resource:Pod {ns: "default"})
RETURN p.name, p.podIP, p.status_json
LIMIT 10;
```

### 2. Episodic Node (Events/Logs/Alerts)

**Properties**:
```cypher
{
  eid: "event-abc123",                   // Unique event ID
  etype: "k8s.event",                    // Event type (k8s.event, k8s.log, prom.alert)
  event_time: datetime("2025-10-10T..."), // When event occurred
  severity: "ERROR",                     // INFO, WARNING, ERROR, FATAL, CRITICAL
  reason: "CrashLoopBackOff",            // Event reason
  message: "Container crashed...",       // Full event message
  subject_rid: "pod:default:myapp-pod",  // Affected resource RID
  cluster: "minikube"                    // Cluster name
}
```

**Example Query**:
```cypher
// Get recent errors
MATCH (e:Episodic)
WHERE e.severity IN ['ERROR', 'FATAL', 'CRITICAL']
  AND e.event_time > datetime() - duration({hours: 1})
RETURN e.eid, e.reason, e.message, e.event_time
ORDER BY e.event_time DESC
LIMIT 20;
```

---

## RCA Query APIs

### API 1: Find Root Causes for Incident

**Use Case**: Given an incident (error event), find all potential root causes

**Query**:
```cypher
// Replace $incident_id with your event ID
MATCH (symptom:Episodic {eid: $incident_id})
MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(symptom)
RETURN
  cause.eid AS root_cause_id,
  cause.reason AS root_cause_reason,
  cause.severity AS severity,
  cause.message AS description,
  cause.event_time AS occurred_at,
  coalesce(r.confidence, 0.0) AS confidence_score,
  coalesce(r.hops, 0) AS graph_distance,
  duration.between(cause.event_time, symptom.event_time) AS time_lag
ORDER BY confidence_score DESC, time_lag ASC
LIMIT 10;
```

**Parameters**:
- `incident_id`: Event ID of the symptom (e.g., "event-abc123")

**Returns**:
| Column | Type | Description |
|--------|------|-------------|
| `root_cause_id` | String | Event ID of root cause |
| `root_cause_reason` | String | Reason (e.g., OOMKilled) |
| `severity` | String | ERROR, WARNING, etc. |
| `description` | String | Full error message |
| `occurred_at` | DateTime | When root cause happened |
| `confidence_score` | Float | 0.0-1.0 confidence |
| `graph_distance` | Int | Hops in topology graph |
| `time_lag` | Duration | Time between cause and symptom |

**Visualization**: Network graph showing symptom node connected to cause nodes

---

### API 2: Find Symptoms for Root Cause

**Use Case**: Given a root cause event, find all downstream symptoms

**Query**:
```cypher
MATCH (cause:Episodic {eid: $root_cause_id})
MATCH (cause)-[r:POTENTIAL_CAUSE]->(symptom:Episodic)
RETURN
  symptom.eid AS symptom_id,
  symptom.reason AS symptom_reason,
  symptom.severity AS severity,
  symptom.event_time AS occurred_at,
  coalesce(r.confidence, 0.0) AS confidence_score,
  duration.between(cause.event_time, symptom.event_time) AS propagation_time
ORDER BY symptom.event_time ASC;
```

**Returns**: List of all symptoms caused by this root event

---

### API 3: Find Complete Causal Chain

**Use Case**: Trace full incident timeline from root cause to final symptom

**Query**:
```cypher
MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..5]->(symptom:Episodic {eid: $incident_id})
WITH path, length(path) AS chain_length
ORDER BY chain_length DESC
LIMIT 1
UNWIND nodes(path) AS event
RETURN
  event.eid AS event_id,
  event.reason AS reason,
  event.severity AS severity,
  event.event_time AS timestamp,
  event.message AS description
ORDER BY event.event_time ASC;
```

**Returns**: Chronological sequence of events in causal chain

**Visualization**: Timeline view or sankey diagram

---

### API 4: Get RCA with Affected Resources

**Use Case**: Show incident with both root causes and affected resources

**Query**:
```cypher
MATCH (symptom:Episodic {eid: $incident_id})

// Get root causes
OPTIONAL MATCH (cause:Episodic)-[rc:POTENTIAL_CAUSE]->(symptom)

// Get affected resources
OPTIONAL MATCH (symptom)-[:ABOUT]->(resource:Resource)

// Get related resources via topology
OPTIONAL MATCH (resource)<-[:SELECTS]-(svc:Resource:Service)
OPTIONAL MATCH (resource)<-[:CONTROLS]-(controller:Resource)

RETURN
  symptom.eid AS incident_id,
  symptom.reason AS incident_reason,
  symptom.severity AS severity,
  symptom.event_time AS occurred_at,

  collect(DISTINCT {
    id: cause.eid,
    reason: cause.reason,
    confidence: coalesce(rc.confidence, 0.0),
    time_lag: duration.between(cause.event_time, symptom.event_time)
  }) AS root_causes,

  collect(DISTINCT {
    rid: resource.rid,
    kind: resource.kind,
    name: resource.name,
    namespace: resource.ns
  }) AS affected_resources,

  collect(DISTINCT svc.name) AS affected_services,
  collect(DISTINCT controller.name) AS affected_controllers;
```

**Returns**: Complete incident context with RCA and topology

---

### API 5: Top N Root Causes Across All Incidents

**Use Case**: Find most common root causes across all recent incidents

**Query**:
```cypher
MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(symptom:Episodic)
WHERE symptom.event_time > datetime() - duration({days: 7})
  AND symptom.severity IN ['ERROR', 'CRITICAL', 'FATAL']
WITH cause.reason AS root_cause,
     count(DISTINCT symptom) AS incidents_caused,
     avg(coalesce(r.confidence, 0.0)) AS avg_confidence
WHERE incidents_caused >= 3
RETURN
  root_cause,
  incidents_caused,
  round(avg_confidence, 3) AS avg_confidence_score
ORDER BY incidents_caused DESC
LIMIT 20;
```

**Returns**: Ranked list of most impactful root causes

**Visualization**: Horizontal bar chart

---

## Incident Analysis APIs

### API 6: Get All Active Incidents

**Use Case**: Dashboard view of ongoing incidents

**Query**:
```cypher
MATCH (incident:Episodic)
WHERE incident.severity IN ['ERROR', 'CRITICAL', 'FATAL']
  AND incident.event_time > datetime() - duration({hours: 24})

OPTIONAL MATCH (incident)-[:ABOUT]->(resource:Resource)
OPTIONAL MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(incident)

WITH incident, resource,
     collect(cause.reason)[0..3] AS top_causes,
     count(cause) AS num_causes

RETURN
  incident.eid AS incident_id,
  incident.reason AS incident_type,
  incident.severity AS severity,
  incident.event_time AS occurred_at,
  incident.message AS description,
  resource.kind AS affected_kind,
  resource.name AS affected_resource,
  resource.ns AS namespace,
  top_causes,
  num_causes AS total_root_causes
ORDER BY incident.event_time DESC
LIMIT 50;
```

**Returns**: List of recent incidents with brief RCA summary

---

### API 7: Incident Timeline

**Use Case**: Show all events related to an incident in chronological order

**Query**:
```cypher
MATCH (incident:Episodic {eid: $incident_id})
MATCH (incident)-[:ABOUT]->(resource:Resource)

// Get events about same resource within time window
MATCH (related:Episodic)-[:ABOUT]->(resource)
WHERE related.event_time >= incident.event_time - duration({minutes: 30})
  AND related.event_time <= incident.event_time + duration({minutes: 30})

RETURN
  related.eid AS event_id,
  related.etype AS event_type,
  related.reason AS reason,
  related.severity AS severity,
  related.event_time AS timestamp,
  related.message AS description,
  CASE
    WHEN related.eid = incident.eid THEN 'INCIDENT'
    WHEN related.event_time < incident.event_time THEN 'BEFORE'
    ELSE 'AFTER'
  END AS timeline_position
ORDER BY related.event_time ASC;
```

**Visualization**: Timeline with incident marked as key event

---

### API 8: Blast Radius Analysis

**Use Case**: Find all resources affected by a root cause

**Query**:
```cypher
MATCH (root_cause:Episodic {eid: $root_cause_id})

// Find all symptoms
MATCH (root_cause)-[:POTENTIAL_CAUSE*1..3]->(symptom:Episodic)

// Find affected resources
MATCH (symptom)-[:ABOUT]->(resource:Resource)

// Count by resource type
WITH resource.kind AS resource_type,
     count(DISTINCT resource) AS affected_count,
     collect(DISTINCT resource.name)[0..10] AS example_resources

RETURN
  resource_type,
  affected_count,
  example_resources
ORDER BY affected_count DESC;
```

**Returns**: Impact scope of root cause

---

## Topology Query APIs

### API 9: Service Dependency Map

**Use Case**: Visualize how services are interconnected

**Query**:
```cypher
MATCH (pod:Resource:Pod)<-[:SELECTS]-(svc:Resource:Service)
WHERE svc.ns = $namespace
OPTIONAL MATCH (deploy:Resource:Deployment)-[:CONTROLS]->(pod)
OPTIONAL MATCH (pod)-[:RUNS_ON]->(node:Resource:Node)

RETURN
  svc.name AS service,
  collect(DISTINCT pod.name) AS pods,
  collect(DISTINCT deploy.name) AS deployments,
  collect(DISTINCT node.name) AS nodes,
  count(DISTINCT pod) AS pod_count;
```

**Visualization**: Service mesh diagram

---

### API 10: Pod Topology

**Use Case**: Show full topology for a specific pod

**Query**:
```cypher
MATCH (pod:Resource:Pod {name: $pod_name, ns: $namespace})

// Get service
OPTIONAL MATCH (svc:Resource:Service)-[:SELECTS]->(pod)

// Get controller
OPTIONAL MATCH (controller:Resource)-[:CONTROLS]->(pod)

// Get node
OPTIONAL MATCH (pod)-[:RUNS_ON]->(node:Resource:Node)

// Get parent deployment
OPTIONAL MATCH (deploy:Resource:Deployment)-[:OWNS]->(controller)

RETURN
  pod.name AS pod,
  pod.podIP AS pod_ip,
  pod.status_json AS status,
  svc.name AS service,
  controller.name AS controller,
  controller.kind AS controller_type,
  deploy.name AS deployment,
  node.name AS node;
```

**Returns**: Complete topology context for pod

---

## Metrics & Analytics APIs

### API 11: RCA Quality Metrics

**Use Case**: Validate RCA accuracy and coverage

**Query**:
```cypher
// Overall RCA statistics
MATCH (symptom:Episodic)
WHERE symptom.severity IN ['ERROR', 'FATAL', 'CRITICAL']
  AND symptom.event_time > datetime() - duration({hours: 24})

OPTIONAL MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(symptom)

WITH symptom,
     count(cause) AS num_causes,
     coalesce(max(r.confidence), 0.0) AS max_confidence

RETURN
  count(symptom) AS total_incidents,
  count(CASE WHEN num_causes > 0 THEN 1 END) AS incidents_with_rca,
  round(avg(num_causes), 2) AS avg_causes_per_incident,
  round(avg(max_confidence), 3) AS avg_top_confidence,
  round(
    count(CASE WHEN num_causes > 0 THEN 1 END) * 100.0 / count(symptom),
    2
  ) AS rca_coverage_percent;
```

**Returns**: RCA health metrics

---

### API 12: Confidence Score Distribution

**Use Case**: Analyze quality of RCA confidence scores

**Query**:
```cypher
MATCH ()-[r:POTENTIAL_CAUSE]->()
WHERE r.confidence IS NOT NULL

WITH
  CASE
    WHEN r.confidence >= 0.9 THEN '0.9-1.0'
    WHEN r.confidence >= 0.8 THEN '0.8-0.9'
    WHEN r.confidence >= 0.7 THEN '0.7-0.8'
    WHEN r.confidence >= 0.6 THEN '0.6-0.7'
    WHEN r.confidence >= 0.5 THEN '0.5-0.6'
    ELSE '<0.5'
  END AS confidence_range,
  count(*) AS link_count

RETURN confidence_range, link_count
ORDER BY confidence_range DESC;
```

**Visualization**: Histogram

---

### API 13: Event Type Distribution

**Use Case**: Understand what types of events are most common

**Query**:
```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({days: 7})

WITH e.severity AS severity, e.reason AS reason, count(*) AS occurrences
ORDER BY occurrences DESC

RETURN severity, reason, occurrences
LIMIT 30;
```

**Visualization**: Treemap (severity → reason → count)

---

## Visualization Queries

### VIZ 1: RCA Network Graph

**Query** (for D3.js/Cytoscape):
```cypher
MATCH (symptom:Episodic {eid: $incident_id})
MATCH path = (cause:Episodic)-[r:POTENTIAL_CAUSE*1..2]->(symptom)

WITH [node IN nodes(path) | {
  id: node.eid,
  label: node.reason,
  type: 'event',
  severity: node.severity
}] AS node_list,
[rel IN relationships(path) | {
  source: startNode(rel).eid,
  target: endNode(rel).eid,
  confidence: coalesce(rel.confidence, 0.5)
}] AS edge_list

UNWIND node_list AS node
UNWIND edge_list AS edge

RETURN
  collect(DISTINCT node) AS nodes,
  collect(DISTINCT edge) AS edges;
```

**Output Format**:
```json
{
  "nodes": [
    {"id": "event-1", "label": "OOMKilled", "type": "event", "severity": "ERROR"},
    {"id": "event-2", "label": "CrashLoopBackOff", "type": "event", "severity": "WARNING"}
  ],
  "edges": [
    {"source": "event-1", "target": "event-2", "confidence": 0.92}
  ]
}
```

---

### VIZ 2: Service Topology Graph

**Query**:
```cypher
MATCH (svc:Resource:Service {ns: $namespace})
MATCH (svc)-[:SELECTS]->(pod:Resource:Pod)
OPTIONAL MATCH (pod)-[:RUNS_ON]->(node:Resource:Node)

RETURN
  collect(DISTINCT {
    id: svc.rid,
    label: svc.name,
    type: 'service'
  }) +
  collect(DISTINCT {
    id: pod.rid,
    label: pod.name,
    type: 'pod'
  }) +
  collect(DISTINCT {
    id: node.rid,
    label: node.name,
    type: 'node'
  }) AS nodes,

  collect(DISTINCT {
    source: svc.rid,
    target: pod.rid,
    type: 'SELECTS'
  }) +
  collect(DISTINCT {
    source: pod.rid,
    target: node.rid,
    type: 'RUNS_ON'
  }) AS edges;
```

---

### VIZ 3: Incident Heatmap (Time vs Resource)

**Query**:
```cypher
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE e.event_time > datetime() - duration({days: 7})
  AND e.severity IN ['ERROR', 'CRITICAL']

WITH
  r.name AS resource,
  date(e.event_time) AS day,
  count(*) AS incident_count

RETURN resource, day, incident_count
ORDER BY day ASC, incident_count DESC;
```

**Visualization**: Calendar heatmap (rows=resources, columns=days, color=incident count)

---

## Performance Optimization

### Index Usage Check

```cypher
// Explain query to see if indexes are used
EXPLAIN
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({hours: 1})
RETURN count(e);

// Profile query to see actual execution
PROFILE
MATCH (e:Episodic {reason: "CrashLoopBackOff"})
RETURN e
LIMIT 10;
```

### Pagination

```cypher
// Use SKIP and LIMIT for pagination
MATCH (e:Episodic)
WHERE e.severity = 'ERROR'
RETURN e
ORDER BY e.event_time DESC
SKIP $offset
LIMIT $page_size;
```

### Query Optimization Tips

1. **Use Parameters**: Prevent query cache pollution
```cypher
// Bad
MATCH (e:Episodic {eid: 'event-123'}) RETURN e

// Good
MATCH (e:Episodic {eid: $event_id}) RETURN e
```

2. **Filter Early**: Push WHERE clauses close to MATCH
```cypher
// Bad
MATCH (e:Episodic)
MATCH (e)-[:ABOUT]->(r:Resource)
WHERE e.severity = 'ERROR'

// Good
MATCH (e:Episodic {severity: 'ERROR'})
MATCH (e)-[:ABOUT]->(r:Resource)
```

3. **Limit Variable-Length Paths**
```cypher
// Always limit max hops
MATCH path = (a)-[*1..3]->(b)  // Good
MATCH path = (a)-[*]->(b)      // Bad (can explode)
```

4. **Use PROFILE for Slow Queries**
```cypher
PROFILE
MATCH (e:Episodic)-[:POTENTIAL_CAUSE]->(s)
RETURN e, s
LIMIT 100;
```

---

## API Usage Examples (REST)

### Example 1: Get RCA via HTTP API

```bash
# Assuming kg-api exposes Neo4j queries
curl -X POST http://localhost:8080/api/v1/rca/incident \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "event-abc123",
    "limit": 10
  }'
```

**Response**:
```json
{
  "incident_id": "event-abc123",
  "incident_reason": "CrashLoopBackOff",
  "severity": "ERROR",
  "root_causes": [
    {
      "id": "event-xyz789",
      "reason": "OOMKilled",
      "confidence": 0.92,
      "time_lag_seconds": 15
    }
  ],
  "affected_resources": [
    {
      "kind": "Pod",
      "name": "myapp-pod-123",
      "namespace": "default"
    }
  ]
}
```

---

## Appendix: Quick Reference

### Most Common Queries

1. **Find root causes**: `MATCH (c)-[:POTENTIAL_CAUSE]->(s {eid: $id})`
2. **Recent errors**: `MATCH (e:Episodic {severity: 'ERROR'}) WHERE e.event_time > datetime() - duration({hours: 1})`
3. **Pod topology**: `MATCH (p:Pod {name: $name})-[:RUNS_ON]->(n), (s)-[:SELECTS]->(p)`
4. **RCA stats**: `MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r), avg(r.confidence)`

### Useful Cypher Functions

- `datetime()` - Current time
- `duration({hours: 1})` - Time duration
- `duration.between(t1, t2)` - Time difference
- `coalesce(val, default)` - Return first non-null
- `collect(DISTINCT x)` - Aggregate unique values
- `count(DISTINCT x)` - Count unique
- `round(x, decimals)` - Round float

---

**End of Document**
