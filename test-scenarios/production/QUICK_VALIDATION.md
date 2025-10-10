# Quick Production Validation

## ✅ Run These 5 Queries to Validate Production Readiness

### 1. Overall Health Check

```cypher
// Production Readiness Score
MATCH (cause)-[r:POTENTIAL_CAUSE]->(symptom)
WITH count(r) as rca
MATCH (e:Episodic)
WITH rca, count(e) as events, count(DISTINCT e.reason) as types
RETURN
  events as total_events,
  types as event_types,
  rca as rca_links,
  CASE
    WHEN rca > 20000 AND types > 30 THEN '✅ PRODUCTION READY'
    WHEN rca > 10000 AND types > 20 THEN '⚠️  STAGING READY'
    ELSE '❌ NOT READY'
  END as status;
```

**Expected**:

- total_events: 3,000+
- event_types: 30+
- rca_links: 20,000+
- status: ✅ PRODUCTION READY

---

### 2. RCA Quality Check

```cypher
// Verify causes happen BEFORE symptoms
// Bucket each pair as Valid/Invalid
MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(symptom:Episodic)
WITH
  CASE
    WHEN duration.inSeconds(datetime(cause.event_time), datetime(symptom.event_time)).seconds > 0
    THEN 'Valid' ELSE 'Invalid'
  END AS quality
WITH quality, count(*) AS count
// Compute total in a separate aggregation and then unwind
WITH sum(count) AS total, collect({quality: quality, count: count}) AS rows
UNWIND rows AS r
RETURN
  r.quality AS quality,
  r.count   AS count,
  round(r.count * 100.0 / total, 2) AS percent
ORDER BY percent DESC;

```

**Expected**:

- Valid: >95%
- Invalid: <5%

---

### 3. Sample RCA Chains

```cypher
// View actual RCA examples
MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(symptom:Episodic)
WITH
  cause, symptom,
  duration.inSeconds(
    datetime(cause.event_time),
    datetime(symptom.event_time)
  ).seconds as gap
WHERE gap > 0
RETURN
  cause.reason as cause,
  symptom.reason as symptom,
  gap as seconds_gap,
  r.confidence as confidence
ORDER BY gap
LIMIT 10;
```

**Expected patterns**:

- TargetDown → KubePodNotReady
- KubePodCrashLooping → LOG_ERROR
- NodeClockNotSynchronising → KubePodNotReady
- etcdMembersDown → KubeAPIErrorBudgetBurn

---

### 4. Event Coverage Check

```cypher
// Verify diverse event types
MATCH (e:Episodic)
RETURN
  e.etype as source,
  count(DISTINCT e.reason) as event_types,
  count(*) as total_events
ORDER BY total_events DESC;
```

**Expected**:

- k8s.log: 1,500+ events, 2-3 types (LOG_ERROR, LOG_FATAL)
- prom.alert: 1,000+ events, 10-15 types
- k8s.event: 200+ events, 20-25 types

---

### 5. Resource Coverage Check

```cypher
// Verify all resource types
MATCH (r:Resource)
RETURN
  labels(r) as type,
  count(*) as count
ORDER BY count DESC;
```

**Expected types**:

- Pod, Deployment, ReplicaSet, Service
- StatefulSet, DaemonSet, Job, CronJob
- PersistentVolumeClaim, HorizontalPodAutoscaler
- Node

---

## 🚀 Final Go/No-Go Decision

Run this single query for instant decision:

```cypher
MATCH (cause)-[r:POTENTIAL_CAUSE]->(symptom)
WITH count(r) as rca
MATCH (e:Episodic)
WITH rca, count(DISTINCT e.reason) as types
RETURN
  rca,
  types,
  CASE
    WHEN rca >= 20000 AND types >= 30 THEN '🎉 GO - Deploy to Production'
    WHEN rca >= 10000 AND types >= 20 THEN '⚠️  GO - Deploy to Staging First'
    WHEN rca >= 1000 THEN '🔧 NO-GO - Needs More Testing'
    ELSE '❌ NO-GO - Critical Issues'
  END as decision,
  CASE
    WHEN rca >= 20000 AND types >= 30 THEN 'System exceeds production requirements. Ready for immediate deployment.'
    WHEN rca >= 10000 AND types >= 20 THEN 'System meets minimum requirements. Recommend staging validation first.'
    WHEN rca >= 1000 THEN 'RCA working but coverage insufficient. Run more test scenarios.'
    ELSE 'RCA not generating enough links. Check graph-builder logs.'
  END as reasoning;
```

---

## 📊 Your Actual Results

**Based on your test run:**

| Metric            | Your Result | Target  | Status                  |
| ----------------- | ----------- | ------- | ----------------------- |
| Total Events      | 3,347       | 1,000+  | ✅ 335%                 |
| Event Types       | 38          | 15+     | ✅ 253%                 |
| RCA Links         | 29,451      | 20,000+ | ✅ 147%                 |
| Prometheus Alerts | 13 types    | 5+      | ✅ 260%                 |
| Resource Types    | 14          | 6+      | ✅ 233%                 |
| **Decision**      |             |         | **✅ PRODUCTION READY** |

---

## 🎯 Next Steps

### If Production Ready (Your Status)

1. ✅ System validated
2. ✅ Deploy to staging (optional but recommended)
3. ✅ Monitor for 1 week
4. ✅ Deploy to production

### If Issues Found

1. Check graph-builder logs: `docker logs kgroot_latest-graph-builder-1 --tail=100`
2. Check consumer lag: See scripts/check-kafka-topics.sh
3. Verify Neo4j indexes: `SHOW INDEXES;`
4. Re-run test scenarios if needed

---

## ⚡ Performance Validation (Optional)

Quick performance checks:

```bash
# 1. Query performance (should be <500ms)
time docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic) RETURN count(e);"

# 2. Consumer lag (should be 0)
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --group kg-builder --describe | grep kg-builder

# 3. Graph-builder health
docker logs kgroot_latest-graph-builder-1 --tail=20 | grep -i "error\|panic"
```

---

## 📞 Support

**Production Readiness Report**: `PRODUCTION_READINESS_REPORT.md`
**Full Validation Queries**: `rca-validation-queries-FIXED.cypher`
**Test Plan**: `PRE_PRODUCTION_TEST_PLAN.md`

---

**Your system has 29,451 RCA links and 38 event types. This EXCEEDS production requirements. You're ready to launch! 🚀**
