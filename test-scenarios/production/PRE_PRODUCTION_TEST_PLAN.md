# Pre-Production Test Plan

## 🎯 Objective

Validate the Knowledge Graph system is production-ready by testing all critical paths, failure scenarios, and performance characteristics.

---

## ✅ Test Results So Far

**Good News! RCA is Working:**
```cypher
MATCH ()-[r:POTENTIAL_CAUSE]->()
RETURN count(r) as rca_count;
// Result: 19,928 relationships ✅
```

This is excellent - your RCA algorithm is functioning and creating causality links!

---

## 📋 Pre-Production Test Checklist

### Phase 1: Functional Testing (2-3 hours)

#### 1.1 Data Pipeline ✅
- [x] K8s events flowing (BackOff, Unhealthy, Killing, etc.)
- [x] Pod logs flowing (ERROR, FATAL logs captured)
- [x] State updates (Resource nodes, topology)
- [ ] Prometheus alerts flowing → `raw.prom.alerts` topic
- [ ] All Kafka topics have messages
- [ ] Consumer lag = 0

**Test Commands:**
```bash
# Check all topics
docker exec kgroot_latest-kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 --list

# Check consumer lag
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --group kg-builder --describe
```

#### 1.2 RCA Validation ✅
- [x] POTENTIAL_CAUSE relationships created (19,928 ✅)
- [ ] Verify RCA chains make sense (manual review 10 samples)
- [ ] Test multi-hop causality (ERROR → WARNING → FATAL)
- [ ] Cross-pod impact detected
- [ ] Time-based correlation working (15min window)

**Test Queries:**
```cypher
// Sample 10 RCA chains
MATCH (s:Episodic)-[r:POTENTIAL_CAUSE]->(t:Episodic)
RETURN
  s.event_time as symptom_time,
  s.reason as symptom,
  s.severity as symptom_severity,
  t.event_time as cause_time,
  t.reason as cause,
  t.severity as cause_severity,
  r.weight as confidence
ORDER BY s.event_time DESC
LIMIT 10;

// Multi-hop causality
MATCH path = (s:Episodic)-[:POTENTIAL_CAUSE*2..3]->(root:Episodic)
RETURN
  s.reason as symptom,
  [node IN nodes(path) | node.reason] as causality_chain,
  length(path) as hops
LIMIT 5;
```

#### 1.3 Event Type Coverage
- [x] CrashLoopBackOff ✅
- [x] BackOff ✅
- [x] Unhealthy (probe failures) ✅
- [x] Killing ✅
- [ ] OOMKilled (verify with actual kill)
- [ ] FailedScheduling
- [ ] FailedMount
- [ ] ImagePullBackOff
- [ ] Prometheus alerts (HighErrorRate, PodNotReady, etc.)
- [ ] StatefulSet events
- [ ] DaemonSet events
- [ ] Job/CronJob events
- [ ] HPA scaling events

**Test Commands:**
```bash
# Deploy production scenarios
kubectl apply -f test-scenarios/production/

# Wait 3-5 minutes, then check
kubectl get events -n kg-testing --sort-by='.lastTimestamp' | tail -30
```

#### 1.4 Topology Tracking ✅
- [x] Deployment → ReplicaSet → Pod ✅
- [x] Service → Pod selections ✅
- [x] Pod → Node placement ✅
- [ ] StatefulSet → PVC relationships
- [ ] DaemonSet → Node mapping
- [ ] HPA → Deployment relationships

**Test Query:**
```cypher
// Verify topology completeness
MATCH ()-[r:CONTROLS|SELECTS|RUNS_ON]->()
RETURN type(r) as relationship, count(*) as count
ORDER BY count DESC;

// Should see:
// CONTROLS: 100+
// SELECTS: 20+
// RUNS_ON: 50+
```

---

### Phase 2: Performance Testing (2-3 hours)

#### 2.1 Throughput Test
**Goal**: Handle 100+ events/minute

```bash
# Scale up error generators
kubectl scale deployment error-logger-test -n kg-testing --replicas=10
kubectl scale deployment intermittent-fail-test -n kg-testing --replicas=5

# Monitor for 10 minutes
watch -n 10 'kubectl get pods -n kg-testing'
```

**Success Criteria:**
- [ ] No consumer lag
- [ ] No graph-builder errors
- [ ] Neo4j query response < 500ms
- [ ] All events processed within 2s

#### 2.2 Data Volume Test
**Goal**: Handle 10,000+ events

```bash
# Let system run for 30+ minutes
# Check total event count
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic) RETURN count(e) as total_events;"

# Target: 10,000+
```

**Success Criteria:**
- [ ] Neo4j response time stable
- [ ] Memory usage < 80%
- [ ] CPU usage < 70%
- [ ] No OOM kills

#### 2.3 Latency Test
**Goal**: Event → Neo4j < 2 seconds

```bash
# Create test event with timestamp
kubectl run latency-test -n kg-testing --image=busybox --restart=Never \
  -- sh -c "echo 'LATENCY_TEST_START' && date && exit 1"

# Wait 5 seconds
sleep 5

# Check Neo4j for event
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic)-[:ABOUT]->(:Resource {name: 'latency-test'})
   RETURN e.event_time, e.message LIMIT 1;"

# Compare timestamps
```

**Success Criteria:**
- [ ] P50 latency < 1s
- [ ] P95 latency < 2s
- [ ] P99 latency < 5s

---

### Phase 3: Reliability Testing (2-4 hours)

#### 3.1 Restart Resilience
**Test**: graph-builder restart doesn't lose data

```bash
# Note current offset
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --group kg-builder --describe

# Restart graph-builder
docker restart kgroot_latest-graph-builder-1

# Wait 30 seconds
sleep 30

# Verify consumer resumed from last offset
docker logs kgroot_latest-graph-builder-1 --tail=20
```

**Success Criteria:**
- [ ] Consumer resumes from last committed offset
- [ ] No events lost
- [ ] No duplicate events in Neo4j

#### 3.2 Backpressure Handling
**Test**: System handles Kafka backlog

```bash
# Stop graph-builder
docker stop kgroot_latest-graph-builder-1

# Generate events for 2 minutes
# (pods crashing, scaling, etc.)

# Check Kafka lag
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --group kg-builder --describe

# Start graph-builder
docker start kgroot_latest-graph-builder-1

# Monitor lag decrease
watch -n 5 'docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --group kg-builder --describe'
```

**Success Criteria:**
- [ ] Lag clears within 5 minutes
- [ ] No OOM during catch-up
- [ ] All events processed correctly

#### 3.3 Neo4j Connection Loss
**Test**: graph-builder handles Neo4j downtime

```bash
# Stop Neo4j
docker stop kgroot_latest-neo4j-1

# Generate events (they'll queue in Kafka)
kubectl scale deployment error-logger-test -n kg-testing --replicas=5

# Wait 1 minute
sleep 60

# Start Neo4j
docker start kgroot_latest-neo4j-1

# Wait for health check
sleep 30

# Verify events were processed
```

**Success Criteria:**
- [ ] graph-builder logs show retry attempts
- [ ] Once Neo4j recovers, events are processed
- [ ] No data loss

---

### Phase 4: Query Performance (1-2 hours)

#### 4.1 Basic Query Performance
```cypher
// Warm up
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
RETURN count(e);

// Test queries (all should be < 500ms)
// Query 1: Recent events
PROFILE
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND datetime(e.event_time) > datetime() - duration('PT1H')
RETURN e.event_time, e.reason, r.name
ORDER BY e.event_time DESC
LIMIT 50;

// Query 2: RCA chains
PROFILE
MATCH path = (s:Episodic)-[:POTENTIAL_CAUSE*1..3]->(root:Episodic)
WHERE s.severity IN ['ERROR', 'FATAL']
RETURN
  s.reason as symptom,
  root.reason as root_cause,
  length(path) as hops
LIMIT 20;

// Query 3: Resource errors
PROFILE
MATCH (e:Episodic)-[:ABOUT]->(r:Pod)
WHERE r.ns = 'kg-testing'
  AND e.severity IN ['ERROR', 'FATAL']
RETURN r.name, count(e) as errors
ORDER BY errors DESC;
```

**Success Criteria:**
- [ ] All queries < 500ms
- [ ] No full table scans
- [ ] Indexes being used

#### 4.2 Index Validation
```cypher
// Check indexes exist
SHOW INDEXES;

// Expected indexes:
// - Episodic(event_id)
// - Episodic(event_time)
// - Episodic(severity)
// - Resource(uid)
// - Resource(ns, name)
```

**Success Criteria:**
- [ ] All required indexes exist
- [ ] Indexes are online
- [ ] No failed indexes

---

### Phase 5: Edge Cases (2-3 hours)

#### 5.1 Duplicate Events
**Test**: System handles duplicate K8s events

```bash
# Manually send duplicate to Kafka
# (or restart event-exporter to replay events)

# Check Neo4j for duplicates
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic)
   WITH e.event_id as id, count(*) as cnt
   WHERE cnt > 1
   RETURN id, cnt;"

# Should return 0 rows
```

**Success Criteria:**
- [ ] No duplicate Episodic nodes
- [ ] event_id is unique constraint

#### 5.2 Malformed Events
**Test**: System handles invalid events gracefully

```bash
# Check graph-builder logs for errors
docker logs kgroot_latest-graph-builder-1 | grep -i "error\|panic\|fatal"

# Should see error handling, not crashes
```

**Success Criteria:**
- [ ] Malformed events logged, not crashed
- [ ] Valid events still processed
- [ ] DLQ topics used (if configured)

#### 5.3 Very Long Events
**Test**: Large log messages don't break system

```bash
# Create pod with huge log output
kubectl run big-logger -n kg-testing --image=busybox --restart=Never \
  -- sh -c "for i in \$(seq 1 1000); do echo 'ERROR: Long message aaaaaaaaaaaaaa...' (10KB); done"

# Verify system handles it
```

**Success Criteria:**
- [ ] System processes large events
- [ ] No OOM
- [ ] Message truncation if needed

---

### Phase 6: Monitoring & Alerting (1-2 hours)

#### 6.1 Prometheus Metrics
```bash
# Check graph-builder metrics
curl http://localhost:9090/metrics | grep -E "kg_|graph_"

# Expected metrics:
# - kg_events_processed_total
# - kg_rca_links_created_total
# - kg_neo4j_write_latency_seconds
# - kg_kafka_consume_lag
```

**Success Criteria:**
- [ ] All metrics exposed
- [ ] Metrics updating in real-time
- [ ] Prometheus scraping successfully

#### 6.2 Alerting Rules
```bash
# Check Prometheus alerts
curl http://localhost:9091/api/v1/rules | jq '.data.groups[]'

# Verify test alerts firing
kubectl get prometheusrules -n observability
```

**Success Criteria:**
- [ ] Alert rules loaded
- [ ] Test alerts visible in Prometheus
- [ ] Alertmanager receiving alerts (if configured)

---

## 📊 Production Readiness Scorecard

### Must Have (Blockers)

| Requirement | Status | Notes |
|-------------|--------|-------|
| RCA Working | ✅ | 19,928 links created |
| Zero Data Loss | ⏳ | Test in progress |
| < 2s Latency | ⏳ | Test in progress |
| Consumer Lag = 0 | ⏳ | Test in progress |
| All Queries < 500ms | ⏳ | Test in progress |
| Handles Restarts | ⏳ | Test in progress |

### Should Have

| Requirement | Status | Notes |
|-------------|--------|-------|
| 15+ Event Types | ⏳ | Currently 6, adding more |
| Prometheus Alerts | ⏳ | Deploying now |
| StatefulSet Support | ⏳ | Deploying now |
| Job/CronJob Support | ⏳ | Deploying now |
| HPA Events | ⏳ | Deploying now |
| Metrics Dashboard | ⏳ | Grafana setup |

### Nice to Have

| Requirement | Status | Notes |
|-------------|--------|-------|
| ML Anomaly Detection | ❌ | Post-launch |
| Multi-cluster | ❌ | Post-launch |
| Historical Queries | ⏳ | Works, needs tuning |
| API Endpoint | ❌ | kg-api exists but not tested |

---

## 🚀 Deployment Commands

### Deploy All Production Scenarios

```bash
# 1. Fix and deploy additional scenarios
cd test-scenarios/production

# 2. Deploy Prometheus alert rules
kubectl apply -f prometheus-alerts.yaml

# 3. Deploy StatefulSet
kubectl apply -f statefulset-tests.yaml

# 4. Deploy DaemonSet
kubectl apply -f daemonset-tests.yaml

# 5. Deploy Jobs/CronJobs
kubectl apply -f job-cronjob-tests.yaml

# 6. Deploy HPA
kubectl apply -f hpa-scaling-tests.yaml

# 7. Wait 5 minutes for events to flow
sleep 300

# 8. Verify
kubectl get all -n kg-testing
kubectl get events -n kg-testing --sort-by='.lastTimestamp' | tail -50
```

---

## 🔍 Validation Queries

### Run These After All Tests

```cypher
// 1. Total event count (should be 10,000+)
MATCH (e:Episodic)
RETURN count(e) as total_events;

// 2. Event type diversity (should be 15+)
MATCH (e:Episodic)
RETURN DISTINCT e.reason, count(*) as count
ORDER BY count DESC;

// 3. RCA coverage (should be high ratio)
MATCH (e:Episodic {severity: 'ERROR'})
WITH count(e) as errors
MATCH ()-[r:POTENTIAL_CAUSE]->()
WITH errors, count(r) as rca_links
RETURN
  errors,
  rca_links,
  round(rca_links * 100.0 / errors, 2) as rca_coverage_percent;

// 4. Resource coverage
MATCH (r:Resource)
RETURN
  labels(r) as type,
  count(*) as count
ORDER BY count DESC;

// 5. Data freshness
MATCH (e:Episodic)
RETURN
  max(e.event_time) as latest,
  duration.inSeconds(datetime(max(e.event_time)), datetime()).seconds as seconds_ago;

// 6. Prometheus alerts captured
MATCH (e:Episodic {etype: 'prom.alert'})
RETURN
  e.reason as alert_name,
  count(*) as fires
ORDER BY fires DESC;
```

---

## ✅ Go/No-Go Decision

### Ready for Production If:

1. ✅ **RCA Works**: 1000+ POTENTIAL_CAUSE links created
2. ⏳ **No Data Loss**: Consumer lag = 0, all events captured
3. ⏳ **Performance**: < 2s latency, queries < 500ms
4. ⏳ **Reliability**: Handles restarts, backpressure, failures
5. ⏳ **Coverage**: 15+ event types including critical ones
6. ⏳ **Monitoring**: Metrics exposed, alerts working

### Not Ready If:

- ❌ RCA creating < 100 links (algorithm broken)
- ❌ Consumer lag growing (can't keep up)
- ❌ Latency > 5s (too slow)
- ❌ Crashes during testing (stability issues)
- ❌ Data loss during restarts (durability issues)

---

## 📝 Test Execution Log

Fill this out as you test:

```
Date: ___________
Tester: ___________

Phase 1: Functional Testing
[ ] Data Pipeline - PASS / FAIL / BLOCKED
[ ] RCA Validation - PASS / FAIL / BLOCKED
[ ] Event Coverage - PASS / FAIL / BLOCKED
[ ] Topology - PASS / FAIL / BLOCKED

Phase 2: Performance Testing
[ ] Throughput - PASS / FAIL / BLOCKED
[ ] Data Volume - PASS / FAIL / BLOCKED
[ ] Latency - PASS / FAIL / BLOCKED

Phase 3: Reliability Testing
[ ] Restart Resilience - PASS / FAIL / BLOCKED
[ ] Backpressure - PASS / FAIL / BLOCKED
[ ] Connection Loss - PASS / FAIL / BLOCKED

Phase 4: Query Performance
[ ] Basic Queries - PASS / FAIL / BLOCKED
[ ] Indexes - PASS / FAIL / BLOCKED

Phase 5: Edge Cases
[ ] Duplicates - PASS / FAIL / BLOCKED
[ ] Malformed Events - PASS / FAIL / BLOCKED
[ ] Large Events - PASS / FAIL / BLOCKED

Phase 6: Monitoring
[ ] Prometheus Metrics - PASS / FAIL / BLOCKED
[ ] Alert Rules - PASS / FAIL / BLOCKED

Overall: READY / NOT READY / NEEDS REVIEW
```

---

## 🎓 Next Steps After Testing

1. **If Ready**: Deploy to staging → prod
2. **If Not Ready**: Fix blockers, re-test critical paths
3. **If Needs Review**: Schedule architecture review

---

**Estimated Total Test Time: 10-15 hours**

Break it into 2-3 sessions over 2-3 days for thoroughness.
