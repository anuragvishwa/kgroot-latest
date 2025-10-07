# RCA Enhancements - Testing Guide

Complete guide for testing all enhanced RCA features with real examples and expected outputs.

---

## Table of Contents

1. [Pre-Testing Setup](#pre-testing-setup)
2. [Test 1: Multi-Format Log Parsing](#test-1-multi-format-log-parsing)
3. [Test 2: K8s Event Severity Mapping](#test-2-k8s-event-severity-mapping)
4. [Test 3: RCA Confidence Scoring](#test-3-rca-confidence-scoring)
5. [Test 4: Severity Escalation](#test-4-severity-escalation)
6. [Test 5: Incident Clustering](#test-5-incident-clustering)
7. [Test 6: Enhanced Error Pattern Detection](#test-6-enhanced-error-pattern-detection)
8. [End-to-End RCA Scenario](#end-to-end-rca-scenario)
9. [Performance Testing](#performance-testing)

---

## Pre-Testing Setup

### 1. Verify All Pods Are Running

```bash
kubectl get pods -n observability

# Expected output (all Running):
# kg-builder-xxx     1/1     Running
# neo4j-0            1/1     Running
# vector-xxx         1/1     Running
# vector-logs-xxx    1/1     Running
# kafka-0            1/1     Running
```

### 2. Access Neo4j Browser

```bash
# Start port-forward if not already running
kubectl port-forward -n observability pod/neo4j-0 7474:7474 7687:7687 &

# Open browser: http://localhost:7474/browser/
# Connect with:
#   bolt://localhost:7687
#   Username: neo4j
#   Password: anuragvishwa
```

### 3. Verify Enhanced Schema

```cypher
CALL db.indexes()
YIELD name, type, properties
WHERE name CONTAINS 'epi' OR name CONTAINS 'inc'
RETURN name, type, properties
```

**Expected Output:**
```
name              type   properties
epi_severity      RANGE  [severity]
epi_event_time    RANGE  [event_time]
epi_reason        RANGE  [reason]
inc_resource      RANGE  [resource_id, window_start]
```

---

## Test 1: Multi-Format Log Parsing

### Goal
Verify Vector can parse JSON, glog, and plain text log formats and extract severity correctly.

### Test 1.1: JSON Structured Logs

**Expected Behavior:** Extract severity from `{"level": "ERROR"}` format

```cypher
// Find logs parsed from JSON format
MATCH (e:Episodic)
WHERE e.etype = 'k8s.log'
  AND e.severity IN ['ERROR', 'FATAL']
  AND e.message =~ '.*\\{.*level.*\\}.*'
RETURN e.severity, e.message
LIMIT 5
```

**Example Output:**
```
severity | message
---------|--------------------------------------------------
ERROR    | {"level":"error","msg":"Connection refused"}
FATAL    | {"level":"fatal","msg":"Panic: out of memory"}
```

### Test 1.2: Glog-Style Logs (Go/K8s Format)

**Expected Behavior:** Extract severity from `E1007 12:34:56` prefix

```cypher
// Find glog-style FATAL logs
MATCH (e:Episodic)
WHERE e.etype = 'k8s.log'
  AND e.reason = 'LOG_FATAL'
  AND e.message =~ '^F\\d{4}.*'
RETURN e.message
LIMIT 5
```

**Example Output:**
```
message
---------------------------------------------------------------
F1007 07:53:25.128205 1 main.go:39] error getting server version
F1007 07:57:09.539534 1 controller.go:913] leaderelection lost
```

### Test 1.3: Plain Text Logs

**Expected Behavior:** Extract severity from `ERROR:` or `[ERROR]` prefix

```cypher
// Find plain text ERROR logs
MATCH (e:Episodic)
WHERE e.etype = 'k8s.log'
  AND e.severity = 'ERROR'
  AND (e.message STARTS WITH 'ERROR:' OR e.message STARTS WITH '[ERROR]')
RETURN e.message
LIMIT 5
```

### Test 1.4: Keyword-Based Escalation

**Expected Behavior:** Escalate to ERROR when message contains "exception", "traceback", "stack trace"

```cypher
// Find logs escalated due to keywords
MATCH (e:Episodic)
WHERE e.etype = 'k8s.log'
  AND e.severity = 'ERROR'
  AND (e.message CONTAINS 'exception'
    OR e.message CONTAINS 'traceback'
    OR e.message CONTAINS 'stack trace')
RETURN e.message
LIMIT 5
```

### Verification Steps

```bash
# Check vector-logs is processing logs
kubectl logs -n observability -l app=vector-logs --tail=50 | grep "Healthcheck passed"

# Generate test logs (optional)
kubectl run test-logger --image=busybox --restart=Never -- sh -c "
  echo 'INFO: Normal log message';
  echo 'ERROR: Database connection failed';
  echo 'FATAL: System panic detected';
"

# Wait 30 seconds for processing
sleep 30

# Query Neo4j for the test logs
```

**Result:** ✅ Pass if logs are parsed and severity is correctly extracted

---

## Test 2: K8s Event Severity Mapping

### Goal
Verify K8s events are mapped to correct severity levels.

### Test 2.1: FATAL Severity Events

```cypher
// Find K8s events mapped to FATAL
MATCH (e:Episodic)
WHERE e.etype = 'k8s.event'
  AND e.severity = 'FATAL'
RETURN e.reason, count(*) AS count
ORDER BY count DESC
```

**Expected Output:**
```
reason              count
OOMKilled           12
CrashLoopBackOff    45
Error               23
BackoffRestart      8
```

### Test 2.2: ERROR Severity Events

```cypher
// Find K8s events mapped to ERROR
MATCH (e:Episodic)
WHERE e.etype = 'k8s.event'
  AND e.severity = 'ERROR'
RETURN e.reason, count(*) AS count
ORDER BY count DESC
LIMIT 10
```

**Expected Output:**
```
reason                count
ImagePullBackOff      23
FailedScheduling      18
FailedMount           7
FailedCreatePodContainer  5
NetworkNotReady       4
```

### Test 2.3: WARNING Severity Events

```cypher
// Find K8s events mapped to WARNING
MATCH (e:Episodic)
WHERE e.etype = 'k8s.event'
  AND e.severity = 'WARNING'
RETURN e.reason, count(*) AS count
ORDER BY count DESC
LIMIT 10
```

**Expected Output:**
```
reason           count
Evicted          15
BackOff          42
Unhealthy        11
FailedSync       8
```

### Test 2.4: Verify Specific Mappings

```cypher
// Test specific K8s event → severity mappings
MATCH (e:Episodic)
WHERE e.etype = 'k8s.event'
  AND e.reason IN ['OOMKilled', 'CrashLoopBackOff', 'ImagePullBackOff', 'FailedScheduling', 'Evicted']
RETURN e.reason, e.severity, count(*) AS occurrences
ORDER BY e.reason
```

**Expected Output:**
| reason | severity | occurrences |
|--------|----------|-------------|
| CrashLoopBackOff | FATAL | 45 |
| Evicted | WARNING | 15 |
| FailedScheduling | ERROR | 18 |
| ImagePullBackOff | ERROR | 23 |
| OOMKilled | FATAL | 12 |

**Result:** ✅ Pass if mappings match expectations

---

## Test 3: RCA Confidence Scoring

### Goal
Verify confidence scores are calculated correctly for POTENTIAL_CAUSE relationships.

### Test 3.1: Check for Confidence Scores

```cypher
// Count RCA links with confidence scores
MATCH ()-[r:POTENTIAL_CAUSE]->()
WHERE r.confidence IS NOT NULL
RETURN count(r) AS links_with_confidence
```

**Note:** If result is 0, confidence scores will appear after new events are processed (Kafka must be stable).

### Test 3.2: View Top Confidence Scores

```cypher
// View highest confidence RCA links
MATCH (c:Episodic)-[r:POTENTIAL_CAUSE]->(e:Episodic)
WHERE r.confidence IS NOT NULL
RETURN
  c.reason AS cause_reason,
  c.message AS cause_message,
  e.reason AS effect_reason,
  r.confidence AS confidence,
  r.temporal_score AS temporal,
  r.distance_score AS distance,
  r.domain_score AS domain
ORDER BY r.confidence DESC
LIMIT 10
```

**Expected Output:**
```
cause_reason | effect_reason    | confidence | temporal | distance | domain
OOMKilled    | CrashLoopBackOff | 0.95       | 0.98     | 1.0      | 0.95
OOMKilled    | CrashLoopBackOff | 0.94       | 0.92     | 1.0      | 0.95
ImagePullBackOff | FailedScheduling | 0.90  | 0.95     | 0.95     | 0.90
```

### Test 3.3: Verify Domain Score Heuristics

```cypher
// Check OOMKilled → CrashLoop links (should have 0.95 domain score)
MATCH (c:Episodic)-[r:POTENTIAL_CAUSE]->(e:Episodic)
WHERE c.reason CONTAINS 'OOMKilled'
  AND e.reason CONTAINS 'CrashLoop'
  AND r.confidence IS NOT NULL
RETURN
  r.domain_score AS domain_score,
  count(*) AS occurrences
```

**Expected:** domain_score = 0.95

```cypher
// Check ImagePull → FailedScheduling links (should have 0.90 domain score)
MATCH (c:Episodic)-[r:POTENTIAL_CAUSE]->(e:Episodic)
WHERE c.reason CONTAINS 'ImagePull'
  AND e.reason CONTAINS 'FailedScheduling'
  AND r.confidence IS NOT NULL
RETURN
  r.domain_score AS domain_score,
  count(*) AS occurrences
```

**Expected:** domain_score = 0.90

### Test 3.4: Verify Confidence Formula

```cypher
// Manually verify confidence calculation
MATCH (c:Episodic)-[r:POTENTIAL_CAUSE]->(e:Episodic)
WHERE r.confidence IS NOT NULL
WITH
  r.temporal_score AS t,
  r.distance_score AS d,
  r.domain_score AS dom,
  r.confidence AS conf
RETURN
  t, d, dom,
  conf AS stored_confidence,
  round((t * 0.3 + d * 0.3 + dom * 0.4) * 100) / 100 AS calculated_confidence,
  abs(conf - (t * 0.3 + d * 0.3 + dom * 0.4)) < 0.01 AS matches
LIMIT 10
```

**Expected:** matches = true for all rows

**Result:** ✅ Pass if confidence scores are present and calculated correctly

---

## Test 4: Severity Escalation

### Goal
Verify WARNING→ERROR→FATAL escalation when events repeat 3+ times in 5 minutes.

### Test 4.1: Find Escalated Events

```cypher
// Find all escalated events
MATCH (e:Episodic)
WHERE e.escalated = true
RETURN
  e.reason AS reason,
  e.severity AS escalated_severity,
  e.repeat_count AS repeat_count,
  e.event_time AS event_time
ORDER BY e.event_time DESC
LIMIT 10
```

**Expected Output:**
```
reason              | escalated_severity | repeat_count | event_time
BackOff             | ERROR              | 5            | 2025-10-07T10:30:00Z
FailedSync          | ERROR              | 4            | 2025-10-07T10:28:00Z
ConnectionRefused   | FATAL              | 3            | 2025-10-07T10:25:00Z
```

### Test 4.2: Verify Escalation Logic

```cypher
// Check if events were escalated correctly
MATCH (e:Episodic)
WHERE e.escalated = true
WITH e
MATCH (e)-[:ABOUT]->(r:Resource)<-[:ABOUT]-(prev:Episodic)
WHERE prev.reason = e.reason
  AND prev.event_time >= e.event_time - duration('PT5M')
  AND prev.event_time < e.event_time
  AND prev.eid <> e.eid
RETURN
  e.reason AS reason,
  e.severity AS escalated_to,
  e.repeat_count AS stored_count,
  count(prev) AS actual_count
ORDER BY e.event_time DESC
LIMIT 10
```

**Expected:** stored_count ≈ actual_count

### Test 4.3: Simulate Escalation (Optional)

```bash
# Generate repeating events to trigger escalation
for i in {1..5}; do
  kubectl run test-escalation-$i --image=invalid-image --restart=Never
  sleep 60  # Wait 1 minute between each
done

# Wait for processing (30 seconds)
sleep 30

# Query for escalated ImagePullBackOff
```

```cypher
MATCH (e:Episodic)
WHERE e.reason = 'ImagePullBackOff'
  AND e.escalated = true
  AND e.event_time >= datetime() - duration('PT10M')
RETURN e.severity, e.repeat_count
```

**Expected:** severity = 'ERROR', repeat_count ≥ 3

**Result:** ✅ Pass if escalation occurs after 3+ repeats in 5 minutes

---

## Test 5: Incident Clustering

### Goal
Verify related ERROR/FATAL events are grouped into Incident nodes.

### Test 5.1: Find All Incidents

```cypher
// List all incident clusters
MATCH (i:Incident)
RETURN
  i.resource_id AS resource,
  i.event_count AS event_count,
  i.window_start AS window_start,
  i.window_end AS window_end
ORDER BY i.event_count DESC
LIMIT 10
```

**Expected Output:**
```
resource                     | event_count | window_start         | window_end
pod/kafka-0                  | 8           | 2025-10-07T10:20:00Z | 2025-10-07T10:25:00Z
pod/vector-logs-xxx          | 5           | 2025-10-07T09:15:00Z | 2025-10-07T09:18:00Z
```

### Test 5.2: View Events in Specific Incident

```cypher
// Get all events in the largest incident
MATCH (i:Incident)
WITH i
ORDER BY i.event_count DESC
LIMIT 1
MATCH (i)<-[:PART_OF]-(e:Episodic)
RETURN
  e.severity AS severity,
  e.reason AS reason,
  e.message AS message,
  e.event_time AS event_time
ORDER BY e.event_time
```

**Expected:** 2+ related ERROR/FATAL events within 5-minute window

### Test 5.3: Verify Incident Clustering Logic

```cypher
// Check incident has events from same resource within 5-min window
MATCH (i:Incident)<-[:PART_OF]-(e:Episodic)-[:ABOUT]->(r:Resource)
WITH i, r, collect(e) AS events, min(e.event_time) AS min_time, max(e.event_time) AS max_time
RETURN
  i.resource_id AS incident_resource,
  r.rid AS actual_resource,
  i.event_count AS stored_count,
  size(events) AS actual_count,
  duration.between(datetime(min_time), datetime(max_time)).minutes AS time_span_minutes
LIMIT 10
```

**Expected:**
- incident_resource = actual_resource
- stored_count = actual_count
- time_span_minutes ≤ 5

### Test 5.4: Incident Timeline

```cypher
// Visualize incident timeline
MATCH (i:Incident)<-[:PART_OF]-(e:Episodic)
WHERE i.resource_id CONTAINS 'kafka'
RETURN
  duration.between(datetime(i.window_start), datetime(e.event_time)).seconds AS seconds_into_window,
  e.severity AS severity,
  e.reason AS reason
ORDER BY seconds_into_window
```

**Result:** ✅ Pass if incidents group 2+ related events within 5-minute windows

---

## Test 6: Enhanced Error Pattern Detection

### Goal
Verify 40+ error patterns are detected across 10 categories.

### Test 6.1: Category 1 - Pod/Container Failures

```cypher
MATCH (e:Episodic)
WHERE e.message =~ '(?i).*(crashloopbackoff|oom killed|exit code|container terminated).*'
  AND e.severity IN ['ERROR', 'FATAL']
RETURN e.reason, count(*) AS count
ORDER BY count DESC
LIMIT 5
```

### Test 6.2: Category 4 - Network/Connectivity

```cypher
MATCH (e:Episodic)
WHERE e.message =~ '(?i).*(connection refused|connection timeout|dns lookup failed|no route to host|network unreachable|tls handshake).*'
  AND e.severity IN ['ERROR', 'FATAL']
RETURN substring(e.message, 0, 80) AS message_preview, e.severity
LIMIT 10
```

**Example Output:**
```
message_preview                                          | severity
---------------------------------------------------------|----------
Get "https://10.96.0.1:443": connection refused         | ERROR
dial tcp 10.244.0.1:9092: connection timeout            | ERROR
DNS lookup failed for kafka.observability.svc           | ERROR
```

### Test 6.3: Category 7 - Database Errors

```cypher
MATCH (e:Episodic)
WHERE e.message =~ '(?i).*(database|db).*(deadlock|timeout|connection pool).*'
RETURN e.message, e.severity
LIMIT 5
```

### Test 6.4: Category 10 - Leader Election

```cypher
MATCH (e:Episodic)
WHERE e.message =~ '(?i).*(leaderelection lost|lease expired).*'
RETURN e.reason, e.message, e.severity
LIMIT 5
```

**Example Output:**
```
reason     | message                                    | severity
-----------|--------------------------------------------|---------
LOG_FATAL  | F1007 07:57:09 controller.go:913] leaderelection lost | FATAL
```

### Test 6.5: Verify High-Signal Logs

```cypher
// Count events by error pattern category
MATCH (e:Episodic)
WHERE e.severity IN ['ERROR', 'FATAL']
WITH e,
  CASE
    WHEN e.message =~ '(?i).*(crashloop|oom|exit code).*' THEN 'Pod Failures'
    WHEN e.message =~ '(?i).*(image pull|manifest|registry).*' THEN 'Image Issues'
    WHEN e.message =~ '(?i).*(insufficient|evicted).*' THEN 'Resource Constraints'
    WHEN e.message =~ '(?i).*(connection|network|dns|timeout).*' THEN 'Network Issues'
    WHEN e.message =~ '(?i).*(unauthorized|forbidden|authentication).*' THEN 'Auth Issues'
    WHEN e.message =~ '(?i).*(failedscheduling|no nodes).*' THEN 'Scheduling Issues'
    WHEN e.message =~ '(?i).*(database|deadlock).*' THEN 'Database Issues'
    WHEN e.message =~ '(?i).*(readiness|liveness).*(probe).*' THEN 'Probe Failures'
    WHEN e.message =~ '(?i).*(volume|persistentvolume).*' THEN 'Storage Issues'
    WHEN e.message =~ '(?i).*(leaderelection|lease).*' THEN 'Leader Election'
    ELSE 'Other'
  END AS category
RETURN category, count(*) AS occurrences
ORDER BY occurrences DESC
```

**Expected:** Multiple categories with significant occurrences

**Result:** ✅ Pass if diverse error patterns are detected

---

## End-to-End RCA Scenario

### Scenario: OOMKilled → CrashLoopBackOff → FailedScheduling

This tests the complete RCA pipeline: event ingestion → severity mapping → confidence scoring → incident clustering.

### Step 1: Create the Failure

```bash
# Deploy a pod that will OOM
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: oom-test
  namespace: observability
spec:
  containers:
  - name: memory-hog
    image: polinux/stress
    command: ["stress"]
    args: ["--vm", "1", "--vm-bytes", "512M"]
    resources:
      limits:
        memory: "128Mi"
EOF

# Wait for events to be processed
sleep 60
```

### Step 2: Verify Events Were Captured

```cypher
// Find the OOMKilled event
MATCH (e:Episodic)-[:ABOUT]->(r:Resource {name: 'oom-test'})
WHERE e.reason = 'OOMKilled'
RETURN e.eid AS oom_eid, e.severity, e.event_time
ORDER BY e.event_time DESC
LIMIT 1
```

**Expected:** severity = 'FATAL'

### Step 3: Find Downstream Effects

```cypher
// Find CrashLoopBackOff caused by OOMKilled
MATCH path = (oom:Episodic {reason: 'OOMKilled'})-[:POTENTIAL_CAUSE*1..2]->(effect:Episodic)
WHERE (oom)-[:ABOUT]->(:Resource {name: 'oom-test'})
RETURN
  effect.reason AS effect_reason,
  effect.severity AS effect_severity,
  length(path) AS causal_distance,
  [rel in relationships(path) | rel.confidence] AS confidence_scores
ORDER BY causal_distance
LIMIT 5
```

**Expected:**
- effect_reason includes 'CrashLoopBackOff'
- confidence_scores show high values (>0.85)

### Step 4: Check Incident Clustering

```cypher
// Find incident cluster for the resource
MATCH (i:Incident {resource_id: 'pod/oom-test'})<-[:PART_OF]-(e:Episodic)
RETURN
  i.event_count AS total_events,
  collect(e.reason) AS event_reasons
```

**Expected:** Multiple related events clustered together

### Step 5: Verify Confidence Score

```cypher
// Check confidence score for OOMKilled → CrashLoop
MATCH (oom:Episodic {reason: 'OOMKilled'})-[r:POTENTIAL_CAUSE]->(crash:Episodic)
WHERE (oom)-[:ABOUT]->(:Resource {name: 'oom-test'})
  AND crash.reason CONTAINS 'CrashLoop'
RETURN
  r.confidence AS confidence,
  r.domain_score AS domain_score,
  r.temporal_score AS temporal_score,
  r.distance_score AS distance_score
```

**Expected:**
- confidence ≈ 0.95
- domain_score = 0.95 (known K8s failure pattern)

### Step 6: Cleanup

```bash
kubectl delete pod oom-test -n observability
```

**Result:** ✅ Pass if complete causal chain is captured with high confidence

---

## Performance Testing

### Test 1: Index Performance

```cypher
// Test severity index performance
PROFILE
MATCH (e:Episodic)
WHERE e.severity = 'ERROR'
RETURN count(e)
```

Check execution plan - should show `NodeIndexSeek` using `epi_severity` index.

### Test 2: Temporal Query Performance

```cypher
// Test event_time index performance
PROFILE
MATCH (e:Episodic)
WHERE e.event_time >= datetime() - duration('PT1H')
RETURN count(e)
```

Should show `NodeIndexSeekByRange` using `epi_event_time` index.

### Test 3: RCA Query Performance

```cypher
// Test complex RCA query performance
PROFILE
MATCH path = (c:Episodic)-[r:POTENTIAL_CAUSE*1..3]->(e:Episodic)
WHERE c.reason = 'OOMKilled'
  AND e.event_time >= datetime() - duration('PT24H')
RETURN count(path)
```

Should complete in <1 second for typical dataset size.

---

## Test Summary Checklist

- [ ] Multi-format log parsing (JSON, glog, plain text)
- [ ] K8s event severity mapping (FATAL, ERROR, WARNING)
- [ ] RCA confidence scoring (0.40-0.95 range)
- [ ] Severity escalation (WARNING→ERROR→FATAL after 3 repeats)
- [ ] Incident clustering (2+ events in 5-minute window)
- [ ] Enhanced error patterns (40+ patterns detected)
- [ ] End-to-end RCA scenario (OOMKilled → CrashLoop)
- [ ] Performance (indexed queries <1 second)

---

## Troubleshooting Test Failures

### No Confidence Scores

**Cause:** Kafka instability or enhanced kg-builder not processing new events

**Solution:**
```bash
# Check kg-builder logs
kubectl logs -n observability -l app=kg-builder --tail=100 | grep LinkRCAWithScore

# Restart kg-builder to trigger reprocessing
kubectl rollout restart deployment/kg-builder -n observability
```

### No Escalated Events

**Cause:** No repeating events within 5-minute window

**Solution:** Generate test events as shown in Test 4.3

### No Incidents

**Cause:** No clusters of 2+ ERROR/FATAL events within 5 minutes

**Solution:** Check if feature flag is enabled:
```bash
kubectl exec -n observability -l app=kg-builder -- printenv | grep INCIDENT
```

---

## Expected Test Results Summary

| Test | Expected Result | Pass Criteria |
|------|----------------|---------------|
| Multi-format Parsing | JSON, glog, plain text logs parsed | Severity extracted correctly |
| K8s Severity Mapping | OOMKilled→FATAL, ImagePull→ERROR | 15+ mappings working |
| Confidence Scoring | 0.40-0.95 scores on RCA links | Formula verified |
| Severity Escalation | WARNING→ERROR after 3 repeats | escalated=true flag set |
| Incident Clustering | 2+ related events in Incident node | PART_OF relationships exist |
| Error Patterns | 40+ patterns across 10 categories | Diverse patterns detected |
| End-to-End RCA | OOM→Crash causal chain | Confidence >0.85 |
| Performance | Indexed queries <1 second | NodeIndexSeek used |
