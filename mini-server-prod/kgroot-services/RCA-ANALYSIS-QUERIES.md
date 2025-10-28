# RCA Analysis Queries - Blast Radius, Causality & Root Cause

> Deep-dive queries for analyzing failure propagation, identifying root causes, and understanding blast radius with confidence scores.

---

## 🎯 Quick Start: Full RCA Analysis

### Find Recent Failures with Full Context
```cypher
// Get failures with their causes, confidence scores, and resource info
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 60})
  AND e.client_id = 'ab-01'
  AND e.severity = 'WARNING'

// Get the resource this event is about
OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource)

// Get all potential causes with confidence scores
OPTIONAL MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(e)

RETURN
  e.reason as failure_reason,
  e.message as failure_message,
  e.event_time as when_failed,
  r.kind as resource_type,
  r.name as resource_name,
  r.ns as namespace,
  collect({
    cause_reason: cause.reason,
    cause_message: cause.message,
    cause_time: cause.event_time,
    confidence: pc.confidence,
    temporal_score: pc.temporal_score,
    distance_score: pc.distance_score,
    domain_score: pc.domain_score
  }) as root_causes
ORDER BY e.event_time DESC
LIMIT 10
```

**This shows:**
- ✅ What failed (failure event)
- ✅ Which resource failed (Pod, Service, etc.)
- ✅ What caused it (root cause candidates)
- ✅ Confidence scores (how sure we are)
- ✅ Multi-dimensional scores (temporal, distance, domain)

---

## 🔍 Query 1: Find Root Causes with Confidence Scores

### Get Causal Chain for a Specific Failure

```cypher
// Find a specific failure event
MATCH (failure:Episodic {client_id: 'ab-01'})
WHERE failure.reason IN ['BackOff', 'Failed', 'Unhealthy', 'OOMKilled']
  AND failure.event_time > datetime() - duration({hours: 1})

// Get all causes leading to this failure
OPTIONAL MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..5]->(failure)

// Get resource info
OPTIONAL MATCH (failure)-[:ABOUT]->(r:Resource)

RETURN
  failure.reason as symptom,
  failure.message as symptom_message,
  failure.event_time as symptom_time,
  r.name as affected_resource,

  // Causal chain
  [node in nodes(path) | {
    reason: node.reason,
    message: node.message,
    time: node.event_time,
    service: node.service
  }] as causal_chain,

  // Confidence scores from relationships
  [rel in relationships(path) | {
    confidence: rel.confidence,
    temporal: rel.temporal_score,
    distance: rel.distance_score,
    domain: rel.domain_score
  }] as confidence_scores,

  length(path) as propagation_hops

ORDER BY failure.event_time DESC
LIMIT 5
```

**Output Interpretation:**
- `causal_chain`: Full path from root cause → symptom
- `confidence_scores`: How confident each link is
- `propagation_hops`: Number of steps in propagation

---

## 💥 Query 2: Blast Radius Analysis

### Find All Events Affected by a Root Cause

```cypher
// Start with a root cause event (e.g., OOMKilled)
MATCH (root:Episodic {client_id: 'ab-01'})
WHERE root.reason = 'OOMKilled'
  AND root.event_time > datetime() - duration({hours: 1})

// Find all downstream failures it caused
OPTIONAL MATCH path = (root)-[:POTENTIAL_CAUSE*1..5]->(affected:Episodic)

// Get affected resources
OPTIONAL MATCH (affected)-[:ABOUT]->(r:Resource)

RETURN
  root.reason as root_cause,
  root.message as root_cause_message,
  root.event_time as root_cause_time,

  // Blast radius
  count(DISTINCT affected) as total_affected_events,
  count(DISTINCT r) as total_affected_resources,

  // Affected events by type
  collect(DISTINCT affected.reason) as failure_types,

  // Propagation paths
  collect(DISTINCT {
    target: affected.reason,
    target_message: affected.message,
    target_time: affected.event_time,
    hops: length(path),
    resource: r.name,
    resource_type: r.kind
  }) as blast_radius_details

ORDER BY root.event_time DESC
```

**Blast Radius Interpretation:**
- `total_affected_events`: How many events were triggered
- `total_affected_resources`: How many resources impacted
- `hops`: Distance from root cause (1=direct, 2+=cascading)

---

## 🌊 Query 3: Service-Level Blast Radius

### Find Service Dependencies and Impact

```cypher
// Get service topology and failures
MATCH (e:Episodic {client_id: 'ab-01'})
WHERE e.event_time > datetime() - duration({hours: 1})
  AND e.severity = 'WARNING'

OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource)

// Get service dependencies (topology)
OPTIONAL MATCH (r)-[dep:SELECTS|RUNS_ON|CONTROLS*1..3]-(related:Resource)

RETURN
  r.kind as failed_resource_type,
  r.name as failed_resource,
  r.ns as namespace,
  e.reason as failure_reason,

  // Service dependencies
  count(DISTINCT related) as dependent_resources,
  collect(DISTINCT {
    type: type(dep),
    resource: related.name,
    resource_kind: related.kind
  }) as dependency_graph,

  // Impact radius
  CASE
    WHEN count(DISTINCT related) = 0 THEN 'ISOLATED'
    WHEN count(DISTINCT related) < 5 THEN 'LOW'
    WHEN count(DISTINCT related) < 10 THEN 'MEDIUM'
    ELSE 'HIGH'
  END as blast_radius_level

ORDER BY count(DISTINCT related) DESC
```

**Service Impact Levels:**
- `ISOLATED`: No dependencies (0 resources)
- `LOW`: 1-4 dependent resources
- `MEDIUM`: 5-9 dependent resources
- `HIGH`: 10+ dependent resources

---

## 🎯 Query 4: Top Root Cause Candidates (Ranked by Confidence)

### Find Most Likely Root Causes

```cypher
// Get all WARNING events in last hour
MATCH (symptom:Episodic {client_id: 'ab-01', severity: 'WARNING'})
WHERE symptom.event_time > datetime() - duration({hours: 1})

// Get potential causes with relationships
MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(symptom)

// Get resource info
OPTIONAL MATCH (symptom)-[:ABOUT]->(symptom_resource:Resource)
OPTIONAL MATCH (cause)-[:ABOUT]->(cause_resource:Resource)

RETURN
  symptom.reason as symptom,
  symptom_resource.name as symptom_resource,
  cause.reason as root_cause_candidate,
  cause_resource.name as root_cause_resource,

  // Multi-dimensional confidence
  pc.confidence as overall_confidence,
  pc.temporal_score as temporal_proximity,
  pc.distance_score as graph_distance,
  pc.domain_score as domain_knowledge,

  // Time analysis
  duration.between(cause.event_time, symptom.event_time).seconds as seconds_before_symptom,

  // Ranking
  CASE
    WHEN pc.confidence > 0.9 THEN 'VERY HIGH'
    WHEN pc.confidence > 0.7 THEN 'HIGH'
    WHEN pc.confidence > 0.5 THEN 'MEDIUM'
    ELSE 'LOW'
  END as confidence_level

ORDER BY pc.confidence DESC, seconds_before_symptom ASC
LIMIT 20
```

**Confidence Score Breakdown:**
- `temporal_proximity`: How close in time (closer = higher score)
- `graph_distance`: How close in graph topology (closer = higher score)
- `domain_knowledge`: Domain rules (e.g., OOMKilled → Pod restart = 0.95)
- `overall_confidence`: Weighted combination of all factors

**Formula:**
```
overall_confidence = 0.4 × temporal + 0.3 × distance + 0.3 × domain
```

---

## 📊 Query 5: Failure Propagation Timeline

### Visualize How Failure Propagated Over Time

```cypher
// Find a failure cascade
MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..5]->(leaf:Episodic)
WHERE root.client_id = 'ab-01'
  AND root.event_time > datetime() - duration({hours: 1})
  AND NOT ()-[:POTENTIAL_CAUSE]->(root)  // root has no causes (actual root)

WITH path, root, leaf,
     length(path) as hops,
     nodes(path) as event_chain,
     relationships(path) as confidence_chain

// Get timeline
RETURN
  root.reason as root_cause,
  root.event_time as t0_root_cause,

  // Timeline of propagation
  [i in range(0, size(event_chain)-1) | {
    time_offset_seconds: duration.between(root.event_time, event_chain[i].event_time).seconds,
    event: event_chain[i].reason,
    message: event_chain[i].message,
    confidence: confidence_chain[i-1].confidence
  }] as propagation_timeline,

  leaf.reason as final_symptom,
  duration.between(root.event_time, leaf.event_time).seconds as total_propagation_time,
  hops as propagation_steps

ORDER BY hops DESC, total_propagation_time DESC
LIMIT 10
```

**Timeline Output Example:**
```
t=0s:   OOMKilled (root cause)
t=2s:   Pod restart (confidence: 0.95)
t=15s:  Service unavailable (confidence: 0.82)
t=30s:  Increased latency (confidence: 0.68)
Total: 30 seconds, 3 hops
```

---

## 🔬 Query 6: Identify Culprits (Most Problematic Resources)

### Find Resources Causing the Most Failures

```cypher
// Find resources that are root causes of many failures
MATCH (cause:Episodic {client_id: 'ab-01'})-[pc:POTENTIAL_CAUSE]->(symptom:Episodic)
WHERE cause.event_time > datetime() - duration({days: 1})
  AND NOT ()-[:POTENTIAL_CAUSE]->(cause)  // No upstream causes (true root)

OPTIONAL MATCH (cause)-[:ABOUT]->(culprit:Resource)

RETURN
  culprit.kind as resource_type,
  culprit.name as resource_name,
  culprit.ns as namespace,

  // Impact metrics
  count(DISTINCT symptom) as failures_caused,
  count(DISTINCT cause) as root_cause_events,
  avg(pc.confidence) as avg_confidence,

  // Failure types caused
  collect(DISTINCT symptom.reason) as failure_types_caused,
  collect(DISTINCT cause.reason) as root_cause_types,

  // Time span
  min(cause.event_time) as first_incident,
  max(cause.event_time) as last_incident,

  // Culprit severity
  CASE
    WHEN count(DISTINCT symptom) > 20 THEN 'CRITICAL'
    WHEN count(DISTINCT symptom) > 10 THEN 'HIGH'
    WHEN count(DISTINCT symptom) > 5 THEN 'MEDIUM'
    ELSE 'LOW'
  END as culprit_severity

ORDER BY failures_caused DESC
LIMIT 10
```

**Top Culprits = Resources to Fix First!**

---

## 🧪 Query 7: Check if Causal Relationships Exist

### Verify POTENTIAL_CAUSE Relationships are Created

```cypher
// Check if graph-builder created causal relationships
MATCH (e1:Episodic {client_id: 'ab-01'})-[pc:POTENTIAL_CAUSE]->(e2:Episodic)
WHERE e1.event_time > datetime() - duration({hours: 2})

RETURN
  count(*) as total_causal_relationships,
  count(DISTINCT e1) as unique_causes,
  count(DISTINCT e2) as unique_symptoms,
  avg(pc.confidence) as avg_confidence,
  min(pc.confidence) as min_confidence,
  max(pc.confidence) as max_confidence,

  // Confidence distribution
  count(CASE WHEN pc.confidence > 0.9 THEN 1 END) as very_high_confidence,
  count(CASE WHEN pc.confidence > 0.7 THEN 1 END) as high_confidence,
  count(CASE WHEN pc.confidence > 0.5 THEN 1 END) as medium_confidence
```

**Expected Output (if working):**
```
total_causal_relationships: 50-200
unique_causes: 20-80
unique_symptoms: 30-100
avg_confidence: 0.6-0.8
```

**If you get 0:**
- ⚠️ graph-builder is not creating relationships
- Check if graph-builder service is running
- Verify FPG construction is enabled

---

## 🎯 Query 8: End-to-End RCA for Specific Failure

### Complete Analysis for One Failure

```cypher
// Pick a specific failure (e.g., BackOff event)
MATCH (failure:Episodic {client_id: 'ab-01'})
WHERE failure.reason = 'BackOff'
  AND failure.event_time > datetime() - duration({minutes: 60})

// Get the full causal chain
OPTIONAL MATCH rootPath = (root:Episodic)-[:POTENTIAL_CAUSE*1..5]->(failure)
WHERE NOT ()-[:POTENTIAL_CAUSE]->(root)

// Get affected resource
OPTIONAL MATCH (failure)-[:ABOUT]->(resource:Resource)

// Get downstream impact (blast radius)
OPTIONAL MATCH downstreamPath = (failure)-[:POTENTIAL_CAUSE*1..3]->(downstream:Episodic)

WITH failure, resource,
     rootPath, root,
     collect(DISTINCT downstream) as downstream_events,
     nodes(rootPath) as causal_chain,
     relationships(rootPath) as causal_links

RETURN
  // === FAILURE INFO ===
  failure.reason as failure_type,
  failure.message as failure_message,
  failure.event_time as failure_time,
  resource.kind + '/' + resource.name as affected_resource,

  // === ROOT CAUSE ANALYSIS ===
  root.reason as root_cause,
  root.message as root_cause_message,
  root.event_time as root_cause_time,
  duration.between(root.event_time, failure.event_time).seconds as propagation_time_seconds,

  // === CAUSAL CHAIN (ROOT → FAILURE) ===
  [i in range(0, size(causal_chain)-1) |
    causal_chain[i].reason + ' (' +
    duration.between(root.event_time, causal_chain[i].event_time).seconds + 's, conf=' +
    toString(round(causal_links[i-1].confidence * 100)/100.0) + ')'
  ] as propagation_path,

  length(rootPath) as hops_from_root,

  // === CONFIDENCE SCORES ===
  [link in causal_links | {
    confidence: link.confidence,
    temporal: link.temporal_score,
    distance: link.distance_score,
    domain: link.domain_score
  }] as confidence_breakdown,

  // === BLAST RADIUS (DOWNSTREAM IMPACT) ===
  size(downstream_events) as downstream_failures,
  [e in downstream_events | e.reason] as downstream_failure_types

ORDER BY failure.event_time DESC
LIMIT 1
```

**Complete RCA Report for One Failure!**

---

## 📈 Query 9: RCA Summary Statistics

### Overall Health of RCA System

```cypher
MATCH (e:Episodic {client_id: 'ab-01'})
WHERE e.event_time > datetime() - duration({hours: 24})

// Count events by type
WITH
  count(CASE WHEN e.severity = 'WARNING' OR e.severity = 'ERROR' THEN 1 END) as failures,
  count(CASE WHEN e.severity = 'INFO' THEN 1 END) as normal_events,
  count(*) as total_events

// Count causal relationships
MATCH ()-[pc:POTENTIAL_CAUSE]->()

RETURN
  total_events,
  normal_events,
  failures,
  count(pc) as causal_relationships,

  // RCA coverage
  toFloat(count(pc)) / failures as avg_causes_per_failure,

  // Health metrics
  CASE
    WHEN failures = 0 THEN 'HEALTHY'
    WHEN failures < 10 THEN 'MINOR ISSUES'
    WHEN failures < 50 THEN 'MODERATE ISSUES'
    ELSE 'CRITICAL'
  END as system_health
```

---

## 🚨 Troubleshooting: No Causal Relationships?

### If Queries Return Empty Results

#### Check 1: Do POTENTIAL_CAUSE relationships exist?
```cypher
MATCH ()-[pc:POTENTIAL_CAUSE]->()
RETURN count(pc) as total_relationships
```

**If 0:** graph-builder is not running or not creating relationships.

#### Check 2: Are there any WARNING events?
```cypher
MATCH (e:Episodic {client_id: 'ab-01', severity: 'WARNING'})
WHERE e.event_time > datetime() - duration({hours: 24})
RETURN count(e) as warning_count
```

**If 0:** System is healthy (no failures to analyze).

#### Check 3: Check graph-builder service
```bash
# Check if graph-builder is running
kubectl get pods -n observability | grep graph-builder

# Check graph-builder logs
kubectl logs -f <graph-builder-pod> -n observability

# Look for: "Building online FPG", "Creating POTENTIAL_CAUSE relationships"
```

---

## 🎯 Example: Real RCA Workflow

### Step-by-Step Analysis

**Step 1: Find recent failures**
```cypher
MATCH (e:Episodic {client_id: 'ab-01', severity: 'WARNING'})
WHERE e.event_time > datetime() - duration({hours: 1})
RETURN e.reason, count(*) as count
ORDER BY count DESC
```

**Step 2: Pick a failure and find root causes** (Use Query 4)

**Step 3: Analyze blast radius** (Use Query 2)

**Step 4: Identify culprits** (Use Query 6)

**Step 5: Get complete RCA report** (Use Query 8)

---

## 📚 Understanding Confidence Scores

### Score Components

| Score Type | Range | Meaning | Weight |
|------------|-------|---------|--------|
| **Temporal** | 0.0-1.0 | Events closer in time = higher score | 40% |
| **Distance** | 0.0-1.0 | Events closer in graph = higher score | 30% |
| **Domain** | 0.0-1.0 | Known causal patterns (rules) | 30% |
| **Overall** | 0.0-1.0 | Weighted combination | 100% |

### Confidence Interpretation

| Overall Score | Meaning | Action |
|---------------|---------|--------|
| 0.9 - 1.0 | **Very High** | Definitely the root cause |
| 0.7 - 0.9 | **High** | Very likely the root cause |
| 0.5 - 0.7 | **Medium** | Possible root cause, investigate |
| 0.3 - 0.5 | **Low** | Weak correlation, may not be related |
| 0.0 - 0.3 | **Very Low** | Unlikely to be the root cause |

### Domain Knowledge Examples

| Causal Pair | Domain Score | Reasoning |
|-------------|--------------|-----------|
| OOMKilled → Pod Restart | 0.95 | Direct causation (Kubernetes kills pod) |
| Pod Restart → Service Down | 0.80 | Strong correlation (no pods = no service) |
| Config Change → Pod Restart | 0.60 | Possible but not certain |
| CPU High → Latency High | 0.65 | Correlation, may have other causes |

---

## 🔗 Related Queries

- **Pattern Matching**: See [NEO4J-QUERIES-REFERENCE.md](NEO4J-QUERIES-REFERENCE.md) Query 4-6
- **Topology Analysis**: See Query 9-11 in reference guide
- **Performance Analysis**: See Query Analysis & Performance section

---

## 💡 Pro Tips

1. **Always check confidence scores** - Don't trust low-confidence relationships
2. **Look for short propagation times** - Root causes usually appear within seconds/minutes
3. **Verify with domain knowledge** - Does the causal chain make sense?
4. **Check blast radius** - High blast radius = urgent fix needed
5. **Identify culprits first** - Fix the resources causing most failures
6. **Use temporal ordering** - Root causes always come BEFORE symptoms

---

## 📊 Next Steps

After running these queries:

1. ✅ **Identify top culprits** (Query 6)
2. ✅ **Analyze blast radius** (Query 2-3)
3. ✅ **Verify confidence scores** (Query 4)
4. ✅ **Generate LLM recommendations** (use GraphRAG)
5. ✅ **Apply fixes to high-impact resources**
6. ✅ **Monitor for resolution**

---

For more details, see:
- [NEO4J-QUERIES-REFERENCE.md](NEO4J-QUERIES-REFERENCE.md) - Complete query reference
- [TEST-NEO4J-QUERIES.md](TEST-NEO4J-QUERIES.md) - Testing and verification
- [pattern_matcher.py](core/pattern_matcher.py) - Pattern matching implementation
- [root_cause_ranker.py](core/root_cause_ranker.py) - Confidence scoring algorithm
