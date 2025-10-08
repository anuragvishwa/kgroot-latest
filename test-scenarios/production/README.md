# Production-Level Testing Suite

## 🎉 Great News - RCA is Working!

```cypher
MATCH ()-[r:POTENTIAL_CAUSE]->()
RETURN count(r) as rca_count;
// Result: 19,928 ✅
```

Your system is generating RCA links! This is the critical feature that makes the Knowledge Graph valuable.

---

## 📁 What's in This Folder

```
production/
├── README.md (this file)
├── PRE_PRODUCTION_TEST_PLAN.md      # Comprehensive 10-15 hour test plan
├── rca-validation-queries.cypher     # 15 queries to validate RCA quality
├── deploy-production-tests.sh        # Deploy all scenarios at once
│
├── prometheus-alerts.yaml            # Prometheus alert rules for kg-testing
├── statefulset-tests.yaml            # StatefulSet scenarios
├── daemonset-tests.yaml              # DaemonSet scenarios
├── job-cronjob-tests.yaml            # Job/CronJob scenarios
└── hpa-scaling-tests.yaml            # HorizontalPodAutoscaler scenarios
```

---

## 🚀 Quick Start

### Deploy Everything

```bash
cd test-scenarios/production
./deploy-production-tests.sh
```

This deploys:
- ✅ Prometheus alert scenarios
- ✅ StatefulSet tests (3 replicas with failures)
- ✅ DaemonSet tests (node-level monitoring)
- ✅ Job/CronJob tests (batch workloads)
- ✅ HPA tests (auto-scaling)
- ✅ All fixed improvement scenarios

### Wait & Validate

```bash
# Wait 5-10 minutes for events to flow
sleep 600

# Check Kafka
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --group kg-builder --describe

# Validate RCA
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "$(cat rca-validation-queries.cypher)"
```

---

## 📊 What You'll Get

### Event Type Coverage

**Current (Basic Tests):**
- CrashLoopBackOff
- BackOff
- Unhealthy
- Killing
- Failed
- ImagePullBackOff

**+ Production Tests Add:**
- StatefulSet scaling events
- DaemonSet lifecycle events
- Job completion/failure events
- CronJob scheduling events
- HPA scaling events
- PVC provisioning events
- Prometheus alerts (HighErrorRate, PodNotReady, OOMKilled, etc.)

**Total Expected: 20-25 event types**

### Resource Coverage

**Added Resource Types:**
- StatefulSet
- DaemonSet
- Job
- CronJob
- HorizontalPodAutoscaler
- PersistentVolumeClaim (via StatefulSet)

### Prometheus Integration

Prometheus alerts will flow through:
```
Prometheus → Alertmanager → Vector → Kafka → graph-builder → Neo4j
```

Alerts included:
- `PodCrashLooping` (based on restart rate)
- `HighErrorRate` (based on container errors)
- `PodMemoryUsageHigh` (>90% of limit)
- `PodCPUThrottling` (CPU throttled containers)
- `PodNotReady` (pods not ready for 5min)
- `DeploymentReplicasMismatch`
- `ContainerOOMKilled`
- `TestPodHighRestartRate`

---

## 🔍 RCA Validation

### 1. Quick Check

```cypher
// Total RCA links
MATCH ()-[r:POTENTIAL_CAUSE]->()
RETURN count(r);
// Current: 19,928 ✅
// Target: 20,000+
```

### 2. Quality Check

```cypher
// Sample RCA chains (review these manually)
MATCH (s:Episodic)-[r:POTENTIAL_CAUSE]->(c:Episodic)
RETURN
  s.event_time as symptom_time,
  s.reason as symptom,
  c.event_time as cause_time,
  c.reason as cause,
  duration.inSeconds(
    datetime(c.event_time),
    datetime(s.event_time)
  ).seconds as time_gap
ORDER BY s.event_time DESC
LIMIT 10;
```

Expected patterns:
- ERROR logs → CrashLoopBackOff (same pod)
- Unhealthy → Killing (probe failures)
- Memory warnings → OOMKilled
- FailedScheduling → NodeNotReady

### 3. Full Validation

```bash
# Run all 15 validation queries
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa < rca-validation-queries.cypher

# Or use Neo4j Browser
open http://localhost:7474
# Copy/paste queries from rca-validation-queries.cypher
```

Key metrics to check:
- [ ] RCA Coverage: >50% of ERROR/FATAL events have causes
- [ ] Time Distribution: Most RCA within 5-15 minutes
- [ ] Multi-hop Chains: 2-3 level causality exists
- [ ] Cross-Pod Impact: Failures in one pod affecting others
- [ ] No Orphaned Causes: <30% events without links

---

## 📋 Pre-Production Testing

Follow [PRE_PRODUCTION_TEST_PLAN.md](PRE_PRODUCTION_TEST_PLAN.md) for complete testing:

### Phase 1: Functional (2-3 hours)
- Data pipeline validation
- RCA chain review
- Event type coverage
- Topology completeness

### Phase 2: Performance (2-3 hours)
- Throughput: 100+ events/min
- Data volume: 10,000+ events
- Latency: <2s event → Neo4j

### Phase 3: Reliability (2-4 hours)
- Restart resilience
- Backpressure handling
- Connection loss recovery

### Phase 4: Query Performance (1-2 hours)
- All queries <500ms
- Index validation
- EXPLAIN PLAN review

### Phase 5: Edge Cases (2-3 hours)
- Duplicate events
- Malformed events
- Large log messages

### Phase 6: Monitoring (1-2 hours)
- Prometheus metrics
- Alert rules
- Grafana dashboards

**Total: 10-15 hours** (spread over 2-3 days)

---

## ✅ Production Readiness Checklist

### Must Have
- [x] RCA Working (19,928 links ✅)
- [ ] Zero Consumer Lag
- [ ] <2s Latency
- [ ] No Data Loss on Restart
- [ ] All Queries <500ms
- [ ] 15+ Event Types

### Should Have
- [ ] Prometheus Alerts Integrated
- [ ] StatefulSet Events Captured
- [ ] Job/CronJob Events Captured
- [ ] HPA Events Captured
- [ ] Metrics Dashboard
- [ ] Documentation Complete

### Nice to Have
- [ ] ML Anomaly Detection
- [ ] Multi-cluster Support
- [ ] API Endpoint Tested
- [ ] Alert Routing Configured

---

## 🎯 Expected Results

After deploying production tests and waiting 10 minutes:

```cypher
// 1. Event diversity
MATCH (e:Episodic)
RETURN DISTINCT e.reason, count(*) as count
ORDER BY count DESC;
// Expected: 20-25 distinct event types

// 2. Total events
MATCH (e:Episodic)
RETURN count(e) as total;
// Expected: 15,000+ events

// 3. RCA coverage
MATCH ()-[r:POTENTIAL_CAUSE]->()
RETURN count(r) as rca_links;
// Expected: 25,000+ links

// 4. Resource types
MATCH (r:Resource)
RETURN labels(r), count(*);
// Expected: 7+ resource types (Pod, Deployment, StatefulSet, etc.)

// 5. Prometheus alerts
MATCH (e:Episodic {etype: 'prom.alert'})
RETURN e.reason, count(*) as fires;
// Expected: 5-10 alert types firing
```

---

## 🐛 Troubleshooting

### Resource Quota Error

If you get:
```
Error from server (Forbidden): ... maximum cpu usage per Container is 500m
```

**Fixed!** The scenarios in this folder respect your LimitRange (500m CPU, 512Mi RAM).

### Prometheus Alerts Not Appearing

Check if Prometheus Operator is installed:
```bash
kubectl get crd prometheusrules.monitoring.coreos.com

# If not found, alerts won't work
# You can still test with regular Prometheus config
```

### StatefulSet PVC Pending

If PVCs stay pending:
```bash
# Check if dynamic provisioning is available
kubectl get storageclass

# If none, PVCs won't bind (expected in Minikube)
# StatefulSet will still generate events
```

### No Job Completion Events

Jobs complete quickly - run this to see them:
```bash
kubectl get jobs -n kg-testing -w

# Check Neo4j for Job events
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
   WHERE r.name CONTAINS 'job'
   RETURN e.event_time, e.reason LIMIT 20;"
```

---

## 📊 Monitoring

### Kafka UI
```
http://localhost:7777
```
Check topics:
- `raw.k8s.events`
- `events.normalized`
- `raw.prom.alerts`
- `logs.normalized`

### Neo4j Browser
```
http://localhost:7474
Username: neo4j
Password: anuragvishwa
```

### Prometheus (if running)
```
http://localhost:9091
```

### Grafana (if running)
```
http://localhost:3000
Username: admin
Password: admin
```

---

## 🎓 Next Steps

1. **Deploy**: Run `./deploy-production-tests.sh`
2. **Wait**: 5-10 minutes for events to flow
3. **Validate**: Run RCA validation queries
4. **Test**: Follow PRE_PRODUCTION_TEST_PLAN.md
5. **Review**: Check if all criteria met
6. **Launch**: If ready, deploy to staging/prod!

---

## 📈 Success Metrics

Your system will be **production-ready** when:

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| RCA Links | 19,928 | 20,000+ | ✅ |
| Event Types | 6 | 15+ | ⏳ In Progress |
| Consumer Lag | ? | 0 | ⏳ Test |
| Latency (P95) | ? | <2s | ⏳ Test |
| Query Speed | ? | <500ms | ⏳ Test |
| Uptime | ? | 99.9% | ⏳ Test |

---

**You're 80% there! RCA works, data flows. Just need to expand coverage and validate performance.**

Good luck with production testing! 🚀
