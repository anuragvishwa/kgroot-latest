# Test Neo4j Queries - Verification Guide

This guide helps you verify that your Neo4j queries are working correctly.

---

## ✅ Verify Query is Working

### Step 1: Check if ANY events exist (last 30 minutes)

```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 30})
  AND e.client_id = 'ab-01'
RETURN count(e) as total_events,
       count(CASE WHEN e.etype = 'k8s.event' THEN 1 END) as k8s_events,
       count(CASE WHEN e.etype = 'k8s.log' THEN 1 END) as k8s_logs
```

**Expected Output (if system is working):**
```
| total_events | k8s_events | k8s_logs |
|--------------|------------|----------|
| 150-500      | 50-200     | 100-300  |
```

**If you get 0 for everything:**
- ⚠️ Events are not being ingested
- Check graph-builder service
- Verify Kafka is producing events

---

### Step 2: Check severity distribution (last 30 minutes)

```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 30})
  AND e.client_id = 'ab-01'
  AND e.etype = 'k8s.event'
RETURN e.severity, count(*) as count
ORDER BY count DESC
```

**Expected Output (healthy system):**
```
| severity | count |
|----------|-------|
| INFO     | 180   |
| ""       | 20    |  (empty severity is normal for some events)
```

**If you see WARNING/ERROR:**
```
| severity | count |
|----------|-------|
| INFO     | 150   |
| WARNING  | 15    |
| ERROR    | 5     |
| ""       | 10    |
```
Then the main RCA query should return results!

---

### Step 3: Check all unique severities (ever recorded)

```cypher
MATCH (e:Episodic {client_id: 'ab-01', etype: 'k8s.event'})
RETURN DISTINCT e.severity as severity, count(*) as count
ORDER BY count DESC
```

**This tells you what severity values actually exist in your database.**

---

### Step 4: Check reason field distribution (last 30 minutes)

```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 30})
  AND e.client_id = 'ab-01'
  AND e.etype = 'k8s.event'
RETURN e.reason, count(*) as count
ORDER BY count DESC
LIMIT 20
```

**Expected Output (healthy system):**
```
| reason           | count |
|------------------|-------|
| Started          | 25    |
| Pulled           | 20    |
| Created          | 20    |
| Scheduled        | 18    |
| SuccessfulCreate | 15    |
| Completed        | 12    |
```

**If you see failure reasons:**
```
| reason             | count |
|--------------------|-------|
| Started            | 25    |
| BackOff            | 8     |  ← Failure!
| OOMKilled          | 3     |  ← Failure!
| FailedScheduling   | 2     |  ← Failure!
```

---

## 🔍 Test Different Time Windows

### Last 1 hour
```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({hours: 1})
  AND e.client_id = 'ab-01'
  AND (
    (e.etype = 'k8s.event' AND e.severity <> 'INFO' AND e.severity <> '')
    OR
    (e.etype = 'k8s.log' AND e.reason IN ['LOG_ERROR', 'LOG_WARNING', 'LOG_FATAL'])
  )
RETURN e.etype, e.reason, e.message, e.severity, e.event_time
ORDER BY e.event_time DESC
LIMIT 20
```

### Last 24 hours
```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({days: 1})
  AND e.client_id = 'ab-01'
  AND (
    (e.etype = 'k8s.event' AND e.severity <> 'INFO' AND e.severity <> '')
    OR
    (e.etype = 'k8s.log' AND e.reason IN ['LOG_ERROR', 'LOG_WARNING', 'LOG_FATAL'])
  )
RETURN e.etype, e.reason, e.message, e.severity, e.event_time
ORDER BY e.event_time DESC
LIMIT 50
```

### Last 7 days
```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({days: 7})
  AND e.client_id = 'ab-01'
  AND (
    (e.etype = 'k8s.event' AND e.severity <> 'INFO' AND e.severity <> '')
    OR
    (e.etype = 'k8s.log' AND e.reason IN ['LOG_ERROR', 'LOG_WARNING', 'LOG_FATAL'])
  )
RETURN e.etype, e.reason, e.severity, count(*) as count,
       min(e.event_time) as first_seen,
       max(e.event_time) as last_seen
GROUP BY e.etype, e.reason, e.severity
ORDER BY count DESC
```

---

## 🧪 Test with Pattern Matching (Backup Query)

If Option A returns 0 results, try **Option B (pattern matching)**:

```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 30})
  AND e.client_id = 'ab-01'
  AND (
    // Pattern match: Any reason containing failure keywords
    (e.etype = 'k8s.event' AND (
      toLower(e.reason) CONTAINS 'fail' OR
      toLower(e.reason) CONTAINS 'error' OR
      toLower(e.reason) CONTAINS 'kill' OR
      toLower(e.reason) CONTAINS 'crash' OR
      toLower(e.reason) CONTAINS 'backoff' OR
      toLower(e.reason) CONTAINS 'evict' OR
      toLower(e.reason) CONTAINS 'unhealthy'
    ))
    OR
    // Include ERROR/WARNING logs
    (e.etype = 'k8s.log' AND e.reason IN ['LOG_ERROR', 'LOG_WARNING', 'LOG_FATAL'])
  )
RETURN e.etype, e.reason, e.message, e.severity, e.event_time
ORDER BY e.event_time DESC
LIMIT 20
```

**This catches events even if severity field is missing or wrong.**

---

## 📊 Find Historical Failures

### Count failures by reason (last 7 days)
```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({days: 7})
  AND e.client_id = 'ab-01'
  AND e.etype = 'k8s.event'
  AND (
    toLower(e.reason) CONTAINS 'fail' OR
    toLower(e.reason) CONTAINS 'error' OR
    toLower(e.reason) CONTAINS 'kill' OR
    toLower(e.reason) CONTAINS 'crash' OR
    toLower(e.reason) CONTAINS 'backoff' OR
    toLower(e.reason) CONTAINS 'evict'
  )
RETURN e.reason, e.severity, count(*) as count
ORDER BY count DESC
```

### Find all ERROR severity events (ever)
```cypher
MATCH (e:Episodic {client_id: 'ab-01', etype: 'k8s.event', severity: 'ERROR'})
RETURN e.reason, e.message, e.event_time
ORDER BY e.event_time DESC
LIMIT 20
```

### Find all WARNING severity events (ever)
```cypher
MATCH (e:Episodic {client_id: 'ab-01', etype: 'k8s.event', severity: 'WARNING'})
RETURN e.reason, e.message, e.event_time
ORDER BY e.event_time DESC
LIMIT 20
```

---

## 🎯 Simulate a Failure (for testing)

To verify RCA queries work, you can simulate failures:

### 1. Create a pod with insufficient memory
```bash
kubectl run oom-test --image=polinux/stress --restart=Never -- stress --vm 1 --vm-bytes 2G --vm-hang 1
```

Wait 30 seconds, then run the main RCA query. You should see `OOMKilled` events!

### 2. Create a pod with wrong image
```bash
kubectl run image-fail --image=nonexistent/image:v999
```

You should see `ImagePullBackOff` or `ErrImagePull` events.

### 3. Create a pod that crashes
```bash
kubectl run crash-test --image=busybox --restart=Always -- sh -c "exit 1"
```

You should see `CrashLoopBackOff` and `BackOff` events.

### Clean up test pods
```bash
kubectl delete pod oom-test image-fail crash-test --ignore-not-found
```

---

## ✅ Verification Checklist

Run these checks in order:

- [ ] **Step 1**: Verify events exist (should return 150-500 events)
- [ ] **Step 2**: Check severity distribution (mostly INFO is good)
- [ ] **Step 3**: Check unique severities (see what exists)
- [ ] **Step 4**: Check reason distribution (see failure reasons)
- [ ] **Step 5**: Try different time windows (1h, 24h, 7d)
- [ ] **Step 6**: Try pattern matching query (backup method)
- [ ] **Step 7**: Search historical failures (last 7 days)
- [ ] **Step 8**: (Optional) Simulate failure for testing

---

## 🤔 Interpretation Guide

### ✅ 0 Results = **HEALTHY SYSTEM**
```
Your system has NO failures in the specified time window.
This is GOOD! No action needed.
```

**To verify the query is working:**
1. Increase time window to 24 hours or 7 days
2. Check if any historical failures exist
3. Run simulation tests to generate failures

### ⚠️ Many Results = **ISSUES DETECTED**
```
The query found failures. Time to investigate!
```

**Next steps:**
1. Group by reason to identify patterns
2. Use RCA Query 1 (comprehensive) to get causal relationships
3. Check blast radius with topology queries

### ❌ 0 Events in Step 1 = **INGESTION PROBLEM**
```
No events are being recorded at all.
```

**Troubleshooting:**
1. Check graph-builder service: `kubectl get pods -n observability`
2. Check Kafka: `kubectl exec -it kafka-0 -- kafka-topics.sh --list --bootstrap-server localhost:9092`
3. Check event-watcher: Verify it's sending to Kafka

---

## 🚀 Next Steps After Verification

### If 0 Results (Healthy System):
1. ✅ Your RCA system is ready for production
2. ✅ Queries are configured correctly
3. ✅ Wait for real failures, or run simulation tests

### If Results Found (Failures Detected):
1. 📊 Run comprehensive RCA query (Query 1)
2. 🔍 Check pattern matching (Query 4-6)
3. 💥 Analyze blast radius (Query 10-11)
4. 🤖 Use LLM analyzer for recommendations

### If No Events at All:
1. ⚠️ Fix data ingestion pipeline
2. 🔧 Check graph-builder service
3. 📡 Verify Kafka connectivity
4. 🔄 Restart services if needed

---

## 📝 Common Questions

**Q: I get 0 results for 30 minutes but results for 24 hours. Is this normal?**
A: Yes! This means your system WAS having issues in the past 24 hours but is currently healthy. This is actually good - it means issues were resolved.

**Q: Should I be worried about 0 results?**
A: No! 0 results means no failures. This is the ideal state. The queries are working correctly.

**Q: How do I know if the query itself is broken?**
A: Run Step 1 (count all events). If you get 150-500 events, the query works. If you get 0, check data ingestion.

**Q: What if I want to test the RCA system?**
A: Use the simulation tests in the "Simulate a Failure" section to generate test failures.

**Q: How often should I run these queries?**
A:
- Monitoring: Every 1-5 minutes (automated)
- Investigation: On-demand when issues occur
- Testing: Weekly to verify system health

---

## 📚 Related Documentation

- Full query reference: [NEO4J-QUERIES-REFERENCE.md](NEO4J-QUERIES-REFERENCE.md)
- RCA implementation: [rca_api_neo4j.py](rca_api_neo4j.py)
- Pattern matching: [pattern_matcher.py](core/pattern_matcher.py)
- Blast radius: [root_cause_ranker.py](core/root_cause_ranker.py)
