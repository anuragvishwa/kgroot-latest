## # Test Scenarios Improvements

This folder contains improvements and recommendations based on initial test results.

## 📊 What's in This Folder

```
improvements/
├── docs/
│   └── ANALYSIS.md           # Detailed analysis of current state & gaps
├── queries/
│   ├── 01-fixed-basic-stats.cypher
│   ├── 02-correlation-based-rca.cypher  # Works without POTENTIAL_CAUSE
│   └── 03-debug-rca.cypher              # Debug why RCA isn't working
├── scenarios/
│   ├── failed-scheduling.yaml           # FailedScheduling events
│   ├── failed-mount.yaml                # FailedMount, ConfigMap/PVC errors
│   ├── invalid-container-config.yaml    # Container startup errors
│   ├── network-errors.yaml              # Network connectivity issues
│   └── resource-pressure.yaml           # CPU throttling, disk pressure
└── scripts/
    ├── deploy-additional-scenarios.sh
    └── test-improved-queries.sh
```

---

## 🔍 Key Findings

### Critical Issue: RCA Not Working ❌

**All POTENTIAL_CAUSE queries return empty results.**

This is the primary blocker for MVP launch. The RCA (Root Cause Analysis) algorithm in graph-builder is either:
1. Not running
2. Not creating relationships
3. Has incorrect configuration

**Action Required**: Debug graph-builder RCA logic immediately.

### What's Working ✅

- Data pipeline (133 events, 44 resources captured)
- Event detection (6 event types: BackOff, Unhealthy, Killing, Failed, etc.)
- Topology tracking (CONTROLS, SELECTS relationships)
- Log severity parsing (ERROR, FATAL, WARNING)

### Current Coverage: 6/18 event types (33%)

**For MVP, we need at least 10 event types (50-60% coverage).**

---

## 🚀 Quick Start

### 1. Deploy Additional Test Scenarios

```bash
cd improvements/scripts
chmod +x *.sh
./deploy-additional-scenarios.sh
```

This adds 5 more critical K8s error types:
- FailedScheduling
- FailedMount
- Invalid container config
- Network errors
- Resource pressure

### 2. Test Improved Queries

```bash
./test-improved-queries.sh
```

These queries work **without POTENTIAL_CAUSE** by using time-based correlation instead.

### 3. Debug RCA

```cypher
// In Neo4j Browser (http://localhost:7474)

// Check if RCA relationships exist
MATCH ()-[r:POTENTIAL_CAUSE]->()
RETURN count(r) as rca_count;

// If 0, RCA is broken
```

---

## 📈 MVP Requirements

### Current State:

| Feature | Status | Notes |
|---------|--------|-------|
| Data Collection | ✅ Working | 133 events captured |
| Event Types | ⚠️ Partial | 6/18 types (need 10+) |
| RCA (POTENTIAL_CAUSE) | ❌ Broken | Zero relationships |
| Topology | ✅ Working | CONTROLS, SELECTS, RUNS_ON |
| Queries | ⚠️ Partial | 1 query failed, RCA queries empty |

### MVP Score: **3/6 (50%)**

**Blocker: RCA must work for MVP.**

---

## 🔧 How to Fix RCA

### Step 1: Check if RCA is Running

```bash
# Check graph-builder logs for RCA activity
docker logs kgroot_latest-graph-builder-1 | grep -i "rca\|potential\|cause"

# Check environment variables
docker exec kgroot_latest-graph-builder-1 env | grep RCA
```

Expected env vars:
- `RCA_WINDOW_MIN=15` (default)
- `SEVERITY_ESCALATION_ENABLED=true` (optional)

### Step 2: Verify RCA Logic

Check [kg/rca.go](../../kg/rca.go) or graph-builder source:

```go
// RCA should create POTENTIAL_CAUSE when:
// 1. Both events are on same resource (or related)
// 2. Earlier event has lower/equal severity
// 3. Within time window (15 min default)
// 4. Time ordering: earlier → later
```

### Step 3: Test with Simple Case

Create a simple test case:
1. ERROR log
2. Wait 30 seconds
3. FATAL crash

This should create `ERROR_LOG -[:POTENTIAL_CAUSE]-> FATAL_CRASH`

### Step 4: Check Neo4j Constraints

```cypher
// Ensure Episodic nodes have unique IDs
SHOW CONSTRAINTS;

// If no constraints, graph-builder may be creating duplicates
```

---

## 📊 Improved Queries

### Correlation-Based RCA (Fallback)

Instead of relying on POTENTIAL_CAUSE, use **time proximity** and **resource relationships**:

```cypher
// Find events that happened close in time on same pod
MATCH (e1:Episodic)-[:ABOUT]->(r:Pod)<-[:ABOUT]-(e2:Episodic)
WHERE r.ns = 'kg-testing'
  AND datetime(e1.event_time) < datetime(e2.event_time)
  AND duration.inSeconds(
    datetime(e1.event_time),
    datetime(e2.event_time)
  ).seconds < 300  // 5 minutes
  AND e1.severity IN ['ERROR', 'WARNING']
  AND e2.severity IN ['ERROR', 'FATAL']
RETURN
  e1.reason as earlier_event,
  e2.reason as later_event,
  r.name as pod,
  duration.inSeconds(
    datetime(e1.event_time),
    datetime(e2.event_time)
  ).seconds as time_gap
ORDER BY e2.event_time DESC
LIMIT 20;
```

See [02-correlation-based-rca.cypher](queries/02-correlation-based-rca.cypher) for more.

---

## 🎯 Additional Test Scenarios

### FailedScheduling

Triggers when pods can't be scheduled:
- Invalid node selector
- Insufficient resources
- Taints/tolerations mismatch

**Expected Events**: `FailedScheduling` (WARNING or ERROR)

### FailedMount

Triggers when volumes can't be mounted:
- Non-existent ConfigMap
- Non-existent PVC
- Non-existent Secret

**Expected Events**: `FailedMount`, `FailedAttachVolume` (ERROR)

### Invalid Container Config

Triggers when container fails to start:
- Invalid command
- Invalid working directory
- Missing binary

**Expected Events**: `Error`, `BackOff` (ERROR/FATAL)

### Network Errors

Application tries to connect to non-existent services:

**Expected**: ERROR logs with network timeout messages

### Resource Pressure

CPU throttling, disk pressure:

**Expected**: `Throttled`, `DiskPressure` warnings (may require node-level monitoring)

---

## 📚 Documentation

See [docs/ANALYSIS.md](docs/ANALYSIS.md) for:
- Detailed gap analysis
- MVP requirements
- Current vs ideal coverage
- Recommended improvements
- Timeline to MVP

---

## ✅ Success Criteria

### Before MVP Launch:

- [ ] RCA creates 50+ POTENTIAL_CAUSE links
- [ ] 10+ K8s event types detected
- [ ] All 8 query categories return results
- [ ] Zero consumer lag in Kafka
- [ ] <2s latency from event → Neo4j
- [ ] Documentation complete

### How to Validate:

```cypher
// 1. Check RCA coverage
MATCH ()-[r:POTENTIAL_CAUSE]->()
RETURN count(r);
// Target: 50+

// 2. Check event type diversity
MATCH (e:Episodic)
RETURN DISTINCT e.reason, count(*) as count
ORDER BY count DESC;
// Target: 10+ distinct reasons

// 3. Check data freshness
MATCH (e:Episodic)
RETURN max(e.event_time) as latest;
// Target: < 2 minutes ago
```

---

## 🚨 Action Items

### P0 - Blocker (Do First)

1. **Debug RCA** - Find out why POTENTIAL_CAUSE isn't being created
2. **Trigger OOMKilled** - Lower memory limit on oom-test pod

### P1 - High Priority (MVP Required)

3. **Deploy Additional Scenarios** - Get to 10+ event types
4. **Fix Broken Queries** - Remove incompatible Neo4j syntax

### P2 - Medium Priority (Post-MVP)

5. **Add More Resources** - Test with StatefulSets, DaemonSets, Jobs
6. **Severity Escalation** - Test with repeated failures
7. **Cross-Pod Impact** - Test cascading failures

---

## 💡 Pro Tips

### Generate More RCA Candidates

```bash
# Scale up error-logger to generate more events
kubectl scale deployment error-logger-test -n kg-testing --replicas=5

# Restart crashloop pod to get fresh crash sequence
kubectl delete pod -n kg-testing -l app=crashloop-test

# Force OOM kill
kubectl patch deployment oom-test -n kg-testing -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"app","resources":{"limits":{"memory":"24Mi"}}}]}}}}'
```

### Monitor RCA in Real-time

```bash
# Watch for POTENTIAL_CAUSE creation
watch -n 5 'docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r);"'
```

---

**For detailed analysis, see [docs/ANALYSIS.md](docs/ANALYSIS.md)**
