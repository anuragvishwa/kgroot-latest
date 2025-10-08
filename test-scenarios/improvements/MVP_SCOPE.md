# MVP Scope & Recommendations

## 📊 Executive Summary

Based on test results from the initial deployment, the Knowledge Graph system shows **strong data pipeline performance** but has a **critical blocker for MVP**: **RCA (Root Cause Analysis) is not creating POTENTIAL_CAUSE relationships**.

**Current MVP Readiness: 50% (3/6 core features)**

---

## ✅ What's Working

### 1. Data Pipeline (100% ✅)
- ✅ K8s events flowing: k8s-event-exporter → Vector → Kafka → Neo4j
- ✅ Pod logs flowing: Vector DaemonSet → Kafka → Neo4j
- ✅ State tracking: Resources & topology updating correctly
- ✅ Zero consumer lag: graph-builder keeping up with Kafka

**Verdict**: Production-ready

### 2. Event Detection (60% ⚠️)
- ✅ 6 event types captured (BackOff, Unhealthy, Killing, Failed, etc.)
- ✅ Severity mapping working (ERROR, FATAL, WARNING)
- ✅ Log parsing working (JSON, glog, plain text)
- ❌ Only 6/18 critical event types (33% coverage)

**Verdict**: Needs more scenarios for MVP (target: 10+ types)

### 3. Topology Tracking (100% ✅)
- ✅ Deployment → ReplicaSet → Pod hierarchy
- ✅ Service → Pod selections
- ✅ Pod → Node placement
- ✅ CONTROLS, SELECTS, RUNS_ON relationships

**Verdict**: Production-ready

### 4. RCA (0% ❌ - BLOCKER)
- ❌ **Zero POTENTIAL_CAUSE relationships created**
- ❌ All RCA queries return empty
- ❌ Root cause analysis not functional

**Verdict**: Critical blocker for MVP launch

### 5. Query Interface (75% ⚠️)
- ✅ 7/8 query categories working
- ❌ 1 query failed (Neo4j syntax incompatibility)
- ❌ All RCA-dependent queries return empty

**Verdict**: Needs fixes for MVP

### 6. Observability (80% ✅)
- ✅ Kafka UI showing message flow
- ✅ Neo4j Browser for graph exploration
- ✅ Consumer group metrics available
- ⚠️ No RCA metrics (can't measure what doesn't exist)

**Verdict**: Good enough for MVP

---

## 🎯 MVP Requirements

### Minimum Viable Product Must Have:

| Feature | Required | Current | Status |
|---------|----------|---------|--------|
| **Data Collection** | 100% | 100% | ✅ Ready |
| **Event Types** | 10+ | 6 | ⚠️ Need 4 more |
| **RCA Links** | 50+ | 0 | ❌ Blocker |
| **Topology** | Basic | Full | ✅ Ready |
| **Queries** | 8 working | 7 working | ⚠️ Need fixes |
| **Zero Data Loss** | Yes | Yes | ✅ Ready |

**MVP Blockers:**
1. 🔴 **P0**: RCA must work (0% → 100%)
2. 🟡 **P1**: Add 4+ event types (33% → 60%+ coverage)
3. 🟡 **P1**: Fix broken queries

---

## 🔧 RCA Investigation Plan

### Why is POTENTIAL_CAUSE Missing?

**Hypothesis 1: RCA Not Running**
```bash
# Check if RCA code is executing
docker logs kgroot_latest-graph-builder-1 | grep -i "rca\|potential\|cause"

# Check environment
docker exec kgroot_latest-graph-builder-1 env | grep RCA_WINDOW
```

**Expected**: `RCA_WINDOW_MIN=15` (from docker-compose.yml line 132)

**Hypothesis 2: Time Window Too Short**
- Current: 15 minutes
- Test events may be too spaced out
- **Test**: Create events 1 minute apart

**Hypothesis 3: Same Resource Requirement**
- RCA may only link events on exact same resource
- **Test**: Check if ERROR log + FATAL crash on same pod creates link

**Hypothesis 4: Code Bug**
- RCA logic may have a bug
- **Test**: Read `kg/rca.go` or graph-builder source code

### Debugging Steps:

```bash
# 1. Check graph-builder is running
docker ps | grep graph-builder

# 2. Check logs for errors
docker logs kgroot_latest-graph-builder-1 --tail=100

# 3. Check if RCA code path is reached
docker logs kgroot_latest-graph-builder-1 | grep "Processing.*RCA"

# 4. Test manual RCA query
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e1:Episodic)-[:ABOUT]->(r:Pod)<-[:ABOUT]-(e2:Episodic)
   WHERE datetime(e1.event_time) < datetime(e2.event_time)
   AND duration.inMinutes(datetime(e1.event_time), datetime(e2.event_time)).minutes < 15
   RETURN e1.reason, e2.reason, r.name LIMIT 5;"
```

### Expected RCA Patterns:

```
ERROR log → CrashLoopBackOff (same pod, <15 min)
Unhealthy → Killing (liveness probe failure)
FailedScheduling → NodeNotReady (node issues)
Memory warning logs → OOMKilled (resource exhaustion)
```

---

## 📈 K8s Event Coverage

### Current Coverage: 6 Types (33%)

| Event Type | Severity | Status | Priority |
|------------|----------|--------|----------|
| BackOff | WARNING | ✅ Covered | P0 |
| Unhealthy | WARNING/ERROR | ✅ Covered | P0 |
| Killing | NORMAL | ✅ Covered | P0 |
| Failed | WARNING | ✅ Covered | P0 |
| SandboxChanged | NORMAL | ✅ Covered | P2 |
| Scheduled | NORMAL | ✅ Covered | P2 |

### MVP Target: 10+ Types (60%)

Additional scenarios to add:

| Event Type | Scenario | Priority | Covered |
|------------|----------|----------|---------|
| **OOMKilled** | Lower memory limit | P0 | ⚠️ Not triggered yet |
| **FailedScheduling** | Invalid node selector | P0 | ✅ Ready to deploy |
| **FailedMount** | Missing ConfigMap/PVC | P1 | ✅ Ready to deploy |
| **ImagePullBackOff** | Invalid image | P0 | ✅ Covered (partially) |
| **NodeNotReady** | Node simulation | P1 | ❌ Complex (post-MVP) |
| **Evicted** | Resource pressure | P1 | ✅ Ready to deploy |
| **FailedKillPod** | Termination issues | P2 | ❌ Not needed for MVP |
| **NetworkNotReady** | CNI issues | P2 | ❌ Not needed for MVP |

**Action**: Deploy scenarios from `improvements/scenarios/` to reach 10+ types.

---

## 🚀 Path to MVP

### Timeline: 3-4 Days

#### Day 1: Fix RCA (Critical Path)
- [ ] Debug why POTENTIAL_CAUSE isn't created (4 hours)
- [ ] Fix RCA logic or configuration (2 hours)
- [ ] Validate RCA with simple test case (1 hour)
- [ ] Create 50+ RCA links in test environment (1 hour)

**Deliverable**: RCA working with 50+ POTENTIAL_CAUSE links

#### Day 2: Expand Coverage
- [ ] Deploy additional scenarios (1 hour)
  - FailedScheduling
  - FailedMount
  - Resource pressure
- [ ] Trigger OOMKilled event (30 min)
- [ ] Fix broken queries (1 hour)
- [ ] Validate 10+ event types detected (30 min)

**Deliverable**: 10+ event types, all queries working

#### Day 3: Validation & Testing
- [ ] Run full test suite (2 hours)
- [ ] Verify all MVP criteria met (1 hour)
- [ ] Load testing (scale to 100+ events/min) (2 hours)
- [ ] Fix any issues found (2 hours)

**Deliverable**: Stable system under load

#### Day 4: Documentation & Sign-off
- [ ] Update documentation (2 hours)
- [ ] Create demo video/screenshots (2 hours)
- [ ] MVP sign-off review (2 hours)

**Deliverable**: MVP launch-ready

---

## ✅ MVP Launch Checklist

### Core Functionality
- [ ] **RCA Working**: 50+ POTENTIAL_CAUSE relationships
- [ ] **Event Coverage**: 10+ distinct K8s event types
- [ ] **Topology**: Deployment → Pod hierarchy tracked
- [ ] **Queries**: All 8 categories return results
- [ ] **No Data Loss**: Consumer lag = 0

### Performance
- [ ] **Latency**: <2s from K8s event → Neo4j
- [ ] **Throughput**: Handle 100+ events/min
- [ ] **Stability**: No crashes over 24-hour test

### Observability
- [ ] **Kafka UI**: Accessible and showing data
- [ ] **Neo4j Browser**: Accessible and showing graph
- [ ] **Metrics**: graph-builder Prometheus metrics available
- [ ] **Logs**: All components logging correctly

### Documentation
- [ ] **Architecture**: Diagrams and explanation
- [ ] **Deployment**: Step-by-step guide
- [ ] **Queries**: Example Cypher queries documented
- [ ] **Troubleshooting**: Common issues and fixes

---

## 💡 Post-MVP Enhancements

### Phase 2 (After MVP Launch)

1. **Expand K8s Coverage** (30+ event types)
   - StatefulSet events
   - DaemonSet events
   - Job/CronJob events
   - HPA scaling events

2. **Advanced RCA**
   - Multi-hop causality (3+ levels)
   - Cross-namespace impact
   - Weighted causality scores
   - ML-based anomaly detection

3. **Better Observability**
   - Grafana dashboards
   - Alert rules
   - RCA metrics
   - Performance dashboards

4. **More Integrations**
   - Slack/PagerDuty alerts
   - Jira ticket creation
   - Webhook notifications
   - REST API for queries

---

## 📊 Success Metrics

### MVP Launch Criteria:

```cypher
// 1. RCA Coverage
MATCH ()-[r:POTENTIAL_CAUSE]->()
RETURN count(r) as rca_links;
// ✅ Target: 50+

// 2. Event Type Diversity
MATCH (e:Episodic)
RETURN DISTINCT e.reason as event_type, count(*) as count
ORDER BY count DESC;
// ✅ Target: 10+ distinct types

// 3. Data Freshness
MATCH (e:Episodic)
RETURN max(e.event_time) as latest;
// ✅ Target: < 2 minutes ago

// 4. Resource Coverage
MATCH (r:Resource)
WHERE r.ns = 'kg-testing'
RETURN labels(r) as type, count(*) as count;
// ✅ Target: 40+ resources

// 5. Topology Completeness
MATCH ()-[r:CONTROLS|SELECTS|RUNS_ON]->()
RETURN type(r) as rel, count(*) as count;
// ✅ Target: 50+ topology links
```

---

## 🎯 Recommendation for MVP

### Scope Decision:

**Option A: Fix RCA + Basic Coverage (Recommended)**
- Fix RCA (mandatory)
- Add 4 scenarios → 10 event types
- Timeline: 3-4 days
- **Risk: Low** (RCA may take longer to debug)

**Option B: Launch without RCA (Not Recommended)**
- Use correlation-based queries instead
- MVP becomes "event aggregator" not "RCA system"
- Timeline: 1-2 days
- **Risk: High** (loses key differentiation)

**Option C: Delay MVP (Safest)**
- Fully debug RCA
- Add all 18 critical event types
- Complete performance testing
- Timeline: 1-2 weeks
- **Risk: Very Low** (but delays launch)

### **Recommendation: Option A**

RCA is the killer feature. Without it, this is just another log aggregator. Fix RCA first, then expand coverage. Launch when both work reliably.

---

## 📞 Support

For questions or issues:
- Check [improvements/README.md](README.md)
- Check [improvements/docs/ANALYSIS.md](docs/ANALYSIS.md)
- Review graph-builder logs
- Test with improved queries in `improvements/queries/`

---

**Bottom Line: The system has a solid foundation. Fix RCA (P0 blocker), add 4 scenarios (P1), and you're MVP-ready in 3-4 days.**
