# 🔍 Neo4j Query Library with Visualizations

**Purpose**: Production-ready Cypher queries for KGroot RCA platform
**Audience**: SRE teams, DevOps engineers, Data analysts
**Version**: 1.0

---

## 📋 Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Root Cause Analysis](#root-cause-analysis)
3. [Incident Investigation](#incident-investigation)
4. [Performance Analysis](#performance-analysis)
5. [Topology Exploration](#topology-exploration)
6. [Pattern Detection](#pattern-detection)
7. [Custom Dashboards](#custom-dashboards)
8. [Troubleshooting Queries](#troubleshooting-queries)

---

## Quick Diagnostics

### Q1: Health Check - Is System Working?

```cypher
// Check if data is flowing
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 5})
WITH count(e) AS recent_events

MATCH (r:Resource)
WITH recent_events, count(r) AS total_resources

MATCH ()-[rc:POTENTIAL_CAUSE]->()
RETURN
  recent_events AS events_last_5_min,
  total_resources AS total_resources,
  count(rc) AS rca_links,
  CASE
    WHEN recent_events > 0 THEN '✅ HEALTHY'
    ELSE '❌ NO RECENT DATA'
  END AS status;
```

**Expected**: `events_last_5_min > 0`, `rca_links > 10000`

**Visualization**: Single-stat panels (Grafana)

---

### Q2: Current Active Incidents

```cypher
MATCH (incident:Episodic)
WHERE incident.severity IN ['ERROR', 'CRITICAL', 'FATAL']
  AND incident.event_time > datetime() - duration({hours: 1})

OPTIONAL MATCH (incident)-[:ABOUT]->(resource:Resource)
OPTIONAL MATCH (cause:Episodic)-[rc:POTENTIAL_CAUSE]->(incident)

WITH incident, resource,
     collect({reason: cause.reason, confidence: rc.confidence})[0] AS top_cause,
     count(cause) AS cause_count

RETURN
  incident.event_time AS timestamp,
  incident.reason AS incident_type,
  incident.severity AS severity,
  resource.kind AS resource_kind,
  resource.name AS resource_name,
  resource.ns AS namespace,
  top_cause.reason AS likely_root_cause,
  round(coalesce(top_cause.confidence, 0.0), 2) AS confidence,
  cause_count AS total_causes
ORDER BY timestamp DESC
LIMIT 20;
```

**Use**: Real-time dashboard of active incidents

**Visualization**: Table with color-coded severity

| Timestamp | Incident | Severity | Resource | Root Cause | Confidence |
|-----------|----------|----------|----------|------------|------------|
| 10:45:23 | CrashLoop | ERROR | Pod/myapp | OOMKilled | 0.92 |

---

### Q3: Top 10 Failure Reasons (Last 24 Hours)

```cypher
MATCH (e:Episodic)
WHERE e.severity IN ['ERROR', 'CRITICAL', 'FATAL']
  AND e.event_time > datetime() - duration({days: 1})

WITH e.reason AS failure_reason, count(*) AS occurrences
ORDER BY occurrences DESC
LIMIT 10

RETURN
  failure_reason,
  occurrences,
  round(occurrences * 100.0 / sum(occurrences) OVER (), 2) AS percentage
ORDER BY occurrences DESC;
```

**Visualization**: Horizontal bar chart

```
OOMKilled        ████████████████ 45 (28%)
CrashLoopBackOff ████████████     32 (20%)
ImagePullError   ████████         21 (13%)
...
```

---

## Root Cause Analysis

### Q4: Deep RCA for Specific Incident

```cypher
// Replace with your incident ID
WITH "event-abc123" AS incident_id

MATCH (symptom:Episodic {eid: incident_id})

// Get direct causes
MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(symptom)

// Get affected resource
OPTIONAL MATCH (symptom)-[:ABOUT]->(resource:Resource)

// Get resource topology
OPTIONAL MATCH (resource)<-[:SELECTS]-(svc:Resource:Service)
OPTIONAL MATCH (resource)<-[:CONTROLS]-(controller:Resource)
OPTIONAL MATCH (resource)-[:RUNS_ON]->(node:Resource:Node)

// Return comprehensive RCA
RETURN
  symptom.eid AS incident_id,
  symptom.reason AS symptom,
  symptom.severity AS severity,
  symptom.event_time AS when_occurred,
  symptom.message AS error_message,

  collect({
    cause_id: cause.eid,
    reason: cause.reason,
    severity: cause.severity,
    message: cause.message,
    confidence: round(coalesce(r.confidence, 0.0), 3),
    time_before: duration.between(cause.event_time, symptom.event_time).seconds,
    graph_hops: coalesce(r.hops, 0)
  }) AS root_causes,

  {
    kind: resource.kind,
    name: resource.name,
    namespace: resource.ns,
    labels: resource.labels_kv,
    status: resource.status_json,
    service: svc.name,
    controller: controller.name,
    node: node.name
  } AS affected_resource;
```

**Output**: Complete incident report with RCA

**Visualization**: Multi-panel layout:
- Panel 1: Incident summary card
- Panel 2: Root causes ranked table
- Panel 3: Resource topology diagram
- Panel 4: Timeline

---

### Q5: Find Causal Chain (Root → Intermediate → Symptom)

```cypher
WITH "event-final-symptom" AS symptom_id

MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..5]->(symptom:Episodic {eid: symptom_id})
WHERE NOT (()-[:POTENTIAL_CAUSE]->(root)) // root has no causes

WITH path, length(path) AS chain_length
ORDER BY chain_length DESC
LIMIT 1

// Extract all events in path
UNWIND nodes(path) AS event
WITH DISTINCT event
ORDER BY event.event_time ASC

RETURN
  event.eid AS event_id,
  event.reason AS event_type,
  event.severity AS severity,
  event.event_time AS timestamp,
  event.message AS description,
  CASE
    WHEN NOT (()-[:POTENTIAL_CAUSE]->(event)) THEN '🔴 ROOT CAUSE'
    WHEN NOT ((event)-[:POTENTIAL_CAUSE]->()) THEN '🔥 FINAL SYMPTOM'
    ELSE '🔗 INTERMEDIATE'
  END AS role_in_chain;
```

**Visualization**: Sankey diagram or flowchart

```
OOMKilled → CrashLoopBackOff → PodEvicted → ServiceUnavailable
  🔴            🔗                🔗              🔥
```

---

### Q6: Accuracy at K (A@K) - Measure RCA Quality

```cypher
// Check if correct root cause is in top K suggestions
MATCH (symptom:Episodic)
WHERE symptom.severity IN ['ERROR', 'FATAL']
  AND symptom.reason IN ['CrashLoopBackOff', 'FailedScheduling', 'Evicted']
  AND symptom.event_time > datetime() - duration({days: 7})

MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(symptom)

WITH symptom,
     collect({
       reason: cause.reason,
       confidence: coalesce(r.confidence, 0.0)
     }) AS causes

WITH symptom,
     [c IN causes | c.reason] AS cause_list,
     CASE symptom.reason
       WHEN 'CrashLoopBackOff' THEN 'OOMKilled'
       WHEN 'FailedScheduling' THEN 'ImagePullBackOff'
       WHEN 'Evicted' THEN 'NodeNotReady'
     END AS expected_cause

WITH symptom.reason AS symptom_type,
     cause_list,
     expected_cause,
     CASE
       WHEN size([c IN cause_list WHERE c = expected_cause]) > 0
         THEN apoc.coll.indexOf(cause_list, expected_cause) + 1
       ELSE null
     END AS actual_rank

RETURN
  symptom_type,
  count(*) AS total_cases,
  count(CASE WHEN actual_rank = 1 THEN 1 END) AS correct_at_1,
  count(CASE WHEN actual_rank <= 3 THEN 1 END) AS correct_at_3,
  count(CASE WHEN actual_rank <= 5 THEN 1 END) AS correct_at_5,
  round(count(CASE WHEN actual_rank <= 3 THEN 1 END) * 100.0 / count(*), 2) AS accuracy_at_3
ORDER BY total_cases DESC;
```

**Target**: A@3 > 85% (KGroot paper: 93.5%)

**Visualization**: Bar chart showing A@1, A@3, A@5

---

## Incident Investigation

### Q7: Timeline of Events Around Incident

```cypher
// Get 30-minute window around incident
WITH "event-abc123" AS incident_id, 30 AS window_minutes

MATCH (incident:Episodic {eid: incident_id})
MATCH (incident)-[:ABOUT]->(resource:Resource)

// All events affecting same resource in time window
MATCH (related:Episodic)-[:ABOUT]->(resource)
WHERE related.event_time >= incident.event_time - duration({minutes: window_minutes})
  AND related.event_time <= incident.event_time + duration({minutes: window_minutes})

RETURN
  related.event_time AS timestamp,
  related.etype AS event_type,
  related.reason AS reason,
  related.severity AS severity,
  related.message AS description,
  duration.between(incident.event_time, related.event_time).seconds AS seconds_from_incident,
  CASE
    WHEN related.eid = incident_id THEN '>>> INCIDENT <<<'
    ELSE ''
  END AS marker
ORDER BY timestamp ASC;
```

**Visualization**: Timeline with incident highlighted

```
10:30:00  INFO    ContainerStarted
10:32:15  WARNING MemoryHigh
10:35:42  ERROR   OOMKilled
10:35:45  >>> INCIDENT <<< CrashLoopBackOff
10:36:10  WARNING BackOff
```

---

### Q8: What Else Failed at Same Time?

```cypher
// Find other failures in same 5-minute window
WITH "event-abc123" AS incident_id

MATCH (incident:Episodic {eid: incident_id})

MATCH (other:Episodic)
WHERE other.severity IN ['ERROR', 'CRITICAL', 'FATAL']
  AND other.eid <> incident_id
  AND abs(duration.between(incident.event_time, other.event_time).seconds) <= 300

OPTIONAL MATCH (other)-[:ABOUT]->(resource:Resource)

RETURN
  other.event_time AS timestamp,
  other.reason AS failure_type,
  resource.kind AS resource_kind,
  resource.name AS resource_name,
  resource.ns AS namespace,
  duration.between(incident.event_time, other.event_time).seconds AS seconds_apart
ORDER BY abs(seconds_apart) ASC
LIMIT 20;
```

**Use**: Find correlated failures (cascading issues)

---

### Q9: Blast Radius - What Was Impacted?

```cypher
// Starting from root cause, find all downstream effects
WITH "event-root-cause" AS root_id

MATCH (root:Episodic {eid: root_id})
MATCH (root)-[:POTENTIAL_CAUSE*1..3]->(symptom:Episodic)

OPTIONAL MATCH (symptom)-[:ABOUT]->(resource:Resource)

WITH resource.kind AS resource_type,
     resource.ns AS namespace,
     count(DISTINCT symptom) AS incident_count,
     collect(DISTINCT resource.name)[0..10] AS affected_resources,
     min(symptom.event_time) AS first_impact,
     max(symptom.event_time) AS last_impact

RETURN
  resource_type,
  namespace,
  incident_count,
  affected_resources,
  duration.between(first_impact, last_impact) AS impact_duration
ORDER BY incident_count DESC;
```

**Visualization**: Horizontal bar chart (resource type → incident count)

---

## Performance Analysis

### Q10: Slowest RCA Queries (Need Optimization)

```cypher
// Identify patterns that generate too many RCA links
MATCH (symptom:Episodic)
WHERE symptom.event_time > datetime() - duration({days: 1})

MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(symptom)

WITH symptom.reason AS symptom_type,
     count(cause) AS num_causes,
     collect(cause.reason)[0..5] AS top_causes

WHERE num_causes > 50 // Too many causes = noisy

RETURN
  symptom_type,
  num_causes AS causes_found,
  top_causes
ORDER BY num_causes DESC
LIMIT 10;
```

**Action**: Tune RCA window or add filters for these patterns

---

### Q11: Confidence Score Distribution

```cypher
MATCH ()-[r:POTENTIAL_CAUSE]->()
WHERE r.confidence IS NOT NULL

WITH
  CASE
    WHEN r.confidence >= 0.9 THEN '🟢 0.9-1.0 (High)'
    WHEN r.confidence >= 0.8 THEN '🟢 0.8-0.9'
    WHEN r.confidence >= 0.7 THEN '🟡 0.7-0.8'
    WHEN r.confidence >= 0.6 THEN '🟡 0.6-0.7'
    WHEN r.confidence >= 0.5 THEN '🟠 0.5-0.6'
    ELSE '🔴 <0.5 (Low)'
  END AS confidence_range,
  r.confidence AS score

WITH confidence_range,
     count(*) AS link_count,
     round(avg(score), 3) AS avg_score

RETURN
  confidence_range,
  link_count,
  avg_score
ORDER BY confidence_range DESC;
```

**Visualization**: Donut chart or histogram

**Target**: >80% of links should have confidence > 0.7

---

### Q12: RCA Coverage by Namespace

```cypher
// Which namespaces have good/poor RCA coverage?
MATCH (incident:Episodic)-[:ABOUT]->(resource:Resource)
WHERE incident.severity IN ['ERROR', 'FATAL']
  AND incident.event_time > datetime() - duration({days: 7})

OPTIONAL MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(incident)

WITH resource.ns AS namespace,
     count(DISTINCT incident) AS total_incidents,
     count(DISTINCT CASE WHEN cause IS NOT NULL THEN incident END) AS incidents_with_rca

RETURN
  namespace,
  total_incidents,
  incidents_with_rca,
  round(incidents_with_rca * 100.0 / total_incidents, 2) AS rca_coverage_percent,
  CASE
    WHEN incidents_with_rca * 100.0 / total_incidents >= 90 THEN '✅ Excellent'
    WHEN incidents_with_rca * 100.0 / total_incidents >= 70 THEN '🟡 Good'
    ELSE '❌ Needs Improvement'
  END AS status
ORDER BY total_incidents DESC;
```

**Action**: Improve instrumentation for namespaces with low coverage

---

## Topology Exploration

### Q13: Full Service Map

```cypher
// Visualize service mesh
MATCH (svc:Resource:Service)
WHERE svc.ns = 'default' // or your namespace

MATCH (svc)-[:SELECTS]->(pod:Resource:Pod)
OPTIONAL MATCH (deploy:Resource:Deployment)-[:CONTROLS]->(pod)
OPTIONAL MATCH (pod)-[:RUNS_ON]->(node:Resource:Node)

RETURN
  // Nodes
  collect(DISTINCT {
    id: svc.rid,
    label: svc.name,
    type: 'service',
    color: '#1f77b4'
  }) +
  collect(DISTINCT {
    id: pod.rid,
    label: pod.name,
    type: 'pod',
    color: '#ff7f0e'
  }) +
  collect(DISTINCT {
    id: deploy.rid,
    label: deploy.name,
    type: 'deployment',
    color: '#2ca02c'
  }) +
  collect(DISTINCT {
    id: node.rid,
    label: node.name,
    type: 'node',
    color: '#d62728'
  }) AS nodes,

  // Edges
  collect(DISTINCT {
    source: svc.rid,
    target: pod.rid,
    label: 'SELECTS'
  }) +
  collect(DISTINCT {
    source: deploy.rid,
    target: pod.rid,
    label: 'CONTROLS'
  }) +
  collect(DISTINCT {
    source: pod.rid,
    target: node.rid,
    label: 'RUNS_ON'
  }) AS edges;
```

**Visualization**: Force-directed graph (D3.js, Cytoscape.js)

---

### Q14: Pod Dependency Chain

```cypher
// Find all resources a pod depends on
MATCH (pod:Resource:Pod {name: 'myapp-pod-123', ns: 'default'})

OPTIONAL MATCH (pod)-[:RUNS_ON]->(node:Resource:Node)
OPTIONAL MATCH (svc:Resource:Service)-[:SELECTS]->(pod)
OPTIONAL MATCH (controller:Resource)-[:CONTROLS]->(pod)
OPTIONAL MATCH (deploy:Resource:Deployment)-[:OWNS]->(controller)

RETURN
  pod.name AS pod,
  pod.podIP AS ip,
  pod.status_json AS status,
  node.name AS runs_on_node,
  collect(DISTINCT svc.name) AS exposed_by_services,
  controller.kind + '/' + controller.name AS controlled_by,
  deploy.name AS deployment
ORDER BY pod.name;
```

**Visualization**: Hierarchy tree

```
Deployment: myapp
  └─ ReplicaSet: myapp-abc123
      └─ Pod: myapp-pod-123
          ├─ Service: myapp-service
          └─ Node: node-1
```

---

### Q15: Node Resource Distribution

```cypher
// See which nodes have most pods
MATCH (pod:Resource:Pod)-[:RUNS_ON]->(node:Resource:Node)

WITH node.name AS node,
     count(pod) AS pod_count,
     collect(DISTINCT pod.ns) AS namespaces

RETURN
  node,
  pod_count,
  size(namespaces) AS namespace_count,
  namespaces
ORDER BY pod_count DESC;
```

**Visualization**: Treemap (size = pod count)

---

## Pattern Detection

### Q16: Recurring Failure Patterns

```cypher
// Find common failure sequences (A → B → C)
MATCH path = (e1:Episodic)-[:POTENTIAL_CAUSE]->(e2:Episodic)-[:POTENTIAL_CAUSE]->(e3:Episodic)
WHERE e3.event_time > datetime() - duration({days: 7})
  AND e1.severity IN ['ERROR', 'WARNING']

WITH [e1.reason, e2.reason, e3.reason] AS pattern,
     count(*) AS occurrences

WHERE occurrences >= 3 // Pattern repeats at least 3 times

RETURN
  pattern[0] + ' → ' + pattern[1] + ' → ' + pattern[2] AS failure_pattern,
  occurrences,
  'Fix ' + pattern[0] + ' to prevent ' + pattern[2] AS recommendation
ORDER BY occurrences DESC
LIMIT 20;
```

**Example Output**:
| Failure Pattern | Occurrences | Recommendation |
|----------------|-------------|----------------|
| OOMKilled → CrashLoop → BackOff | 15 | Fix OOMKilled to prevent BackOff |
| ImagePullError → FailedScheduling → Pending | 8 | Fix ImagePullError to prevent Pending |

---

### Q17: Noisy Resources (Frequent Failures)

```cypher
// Find resources that fail repeatedly
MATCH (e:Episodic)-[:ABOUT]->(resource:Resource)
WHERE e.severity IN ['ERROR', 'CRITICAL', 'FATAL']
  AND e.event_time > datetime() - duration({days: 7})

WITH resource.kind AS kind,
     resource.ns AS namespace,
     resource.name AS name,
     count(e) AS failure_count,
     collect(DISTINCT e.reason)[0..5] AS common_failures

WHERE failure_count >= 5 // Failed at least 5 times

RETURN
  kind,
  namespace,
  name,
  failure_count,
  common_failures
ORDER BY failure_count DESC
LIMIT 20;
```

**Action**: Investigate resources at top of list (likely have underlying issues)

---

### Q18: Silent Failures (No RCA Found)

```cypher
// Find incidents without root causes (gaps in RCA)
MATCH (incident:Episodic)
WHERE incident.severity IN ['ERROR', 'CRITICAL', 'FATAL']
  AND incident.event_time > datetime() - duration({days: 3})
  AND NOT ((:Episodic)-[:POTENTIAL_CAUSE]->(incident))

OPTIONAL MATCH (incident)-[:ABOUT]->(resource:Resource)

RETURN
  incident.event_time AS timestamp,
  incident.reason AS failure_type,
  resource.kind AS resource_kind,
  resource.name AS resource_name,
  resource.ns AS namespace,
  'No root cause identified' AS issue
ORDER BY timestamp DESC
LIMIT 50;
```

**Action**: Improve instrumentation to capture precursor events

---

## Custom Dashboards

### Q19: Executive Dashboard Query

```cypher
// Single query for exec summary
WITH datetime() - duration({hours: 24}) AS window_start

// Count incidents
MATCH (incident:Episodic)
WHERE incident.severity IN ['ERROR', 'CRITICAL', 'FATAL']
  AND incident.event_time >= window_start
WITH window_start, count(incident) AS total_incidents

// Count incidents with RCA
MATCH (incident2:Episodic)
WHERE incident2.severity IN ['ERROR', 'CRITICAL', 'FATAL']
  AND incident2.event_time >= window_start
  AND ((:Episodic)-[:POTENTIAL_CAUSE]->(incident2))
WITH window_start, total_incidents, count(incident2) AS incidents_with_rca

// Count total RCA links
MATCH ()-[r:POTENTIAL_CAUSE]->()

RETURN
  total_incidents AS incidents_last_24h,
  incidents_with_rca,
  round(incidents_with_rca * 100.0 / total_incidents, 2) AS rca_coverage_percent,
  count(r) AS total_rca_links,
  '✅ System Operational' AS status;
```

**Visualization**: Single-stat panels

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Incidents   │  │ RCA Coverage│  │ RCA Links   │
│     42      │  │    95.2%    │  │   51,568    │
└─────────────┘  └─────────────┘  └─────────────┘
```

---

### Q20: SRE On-Call Dashboard

```cypher
// Active incidents needing attention
MATCH (incident:Episodic)
WHERE incident.severity IN ['CRITICAL', 'FATAL']
  AND incident.event_time > datetime() - duration({hours: 1})

OPTIONAL MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(incident)
WITH incident, cause, r
ORDER BY r.confidence DESC

WITH incident,
     collect({
       reason: cause.reason,
       confidence: round(coalesce(r.confidence, 0.0), 2)
     })[0] AS top_cause

OPTIONAL MATCH (incident)-[:ABOUT]->(resource:Resource)

RETURN
  '🚨 ' + incident.reason AS alert,
  incident.severity AS severity,
  resource.kind + '/' + resource.name AS resource,
  resource.ns AS namespace,
  top_cause.reason AS likely_cause,
  top_cause.confidence AS confidence,
  duration.between(incident.event_time, datetime()).minutes AS minutes_ago
ORDER BY minutes_ago ASC;
```

**Visualization**: Alert table with auto-refresh

---

## Troubleshooting Queries

### Q21: Why No RCA Links?

```cypher
// Diagnose RCA pipeline issues
WITH datetime() - duration({minutes: 30}) AS recent

RETURN
  'Total Events' AS metric,
  count{MATCH (e:Episodic) WHERE e.event_time >= recent} AS value
UNION
RETURN
  'Events with ABOUT relationship' AS metric,
  count{MATCH (e:Episodic)-[:ABOUT]->() WHERE e.event_time >= recent} AS value
UNION
RETURN
  'Error Events' AS metric,
  count{MATCH (e:Episodic {severity: 'ERROR'}) WHERE e.event_time >= recent} AS value
UNION
RETURN
  'RCA Links Created (last 30min)' AS metric,
  count{MATCH ()-[r:POTENTIAL_CAUSE]->(:Episodic)
        WHERE exists(r.created_at) AND datetime(r.created_at) >= recent} AS value;
```

**Expected**: All values > 0, RCA Links > 10% of Error Events

---

### Q22: Find Orphaned Resources (No Events)

```cypher
// Resources with no events (might indicate missing instrumentation)
MATCH (resource:Resource)
WHERE NOT ((:Episodic)-[:ABOUT]->(resource))
  AND resource.kind IN ['Pod', 'Service', 'Deployment']

RETURN
  resource.kind AS kind,
  resource.ns AS namespace,
  resource.name AS name,
  'No events linked' AS issue
LIMIT 50;
```

**Action**: Verify Vector/state-watcher is capturing events

---

### Q23: Data Freshness Check

```cypher
// Check when latest data was ingested
MATCH (e:Episodic)
WITH max(e.event_time) AS latest_event

MATCH (r:Resource)
WITH latest_event, max(r.updated_at) AS latest_resource

RETURN
  latest_event AS latest_event_time,
  latest_resource AS latest_resource_update,
  duration.between(latest_event, datetime()).minutes AS minutes_since_event,
  duration.between(latest_resource, datetime()).minutes AS minutes_since_resource,
  CASE
    WHEN duration.between(latest_event, datetime()).minutes < 10 THEN '✅ Fresh'
    WHEN duration.between(latest_event, datetime()).minutes < 60 THEN '🟡 Delayed'
    ELSE '❌ Stale'
  END AS data_freshness;
```

---

## Bonus: Advanced Queries

### Q24: Graph Database Stats

```cypher
// Overall graph statistics
CALL apoc.meta.stats() YIELD labelCount, relTypeCount, propertyKeyCount, nodeCount, relCount
RETURN
  nodeCount AS total_nodes,
  relCount AS total_relationships,
  labelCount AS node_types,
  relTypeCount AS relationship_types,
  propertyKeyCount AS unique_properties;
```

---

### Q25: Schema Visualization

```cypher
// Show graph schema (node labels + relationships)
CALL db.schema.visualization()
```

**Visualization**: Neo4j Browser renders schema diagram automatically

---

## Usage Tips

### 1. Parameterize Queries

```cypher
// In Neo4j Browser:
:param incident_id => 'event-abc123'

// Then use:
MATCH (e:Episodic {eid: $incident_id})
```

### 2. Export Results to CSV

```cypher
// In Neo4j Browser, after running query:
// Click download icon → Export CSV
```

### 3. Create Query Bookmarks

Save frequently-used queries in Neo4j Browser favorites.

---

**End of Query Library**

📚 For API documentation, see [NEO4J_API_COMPLETE.md](NEO4J_API_COMPLETE.md)
