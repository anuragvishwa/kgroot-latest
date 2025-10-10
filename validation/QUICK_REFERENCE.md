# Query Validation Quick Reference

## TL;DR

✅ **All queries work correctly. No fixes needed.**

## Quick Test

```bash
cd /Users/anuragvishwa/Anurag/kgroot_latest

# Run validation (takes ~30 seconds)
./validation/test-query-library.sh

# Expected output:
# Total Tests: 17
# Passed: 17
# Failed: 0
```

## Key Stats

| Metric | Value |
|--------|-------|
| Query Categories Tested | 17 |
| Queries Passed | 17 (100%) |
| Total Events | 4,473 |
| Total Resources | 335 |
| RCA Relationships | 7,544 |
| Topology Relationships | 202 |

## Common Queries

### Find Recent Errors
```bash
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa "
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE e.event_time >= datetime() - duration({hours: 24})
  AND e.severity IN ['ERROR', 'FATAL']
RETURN e.eid, e.reason, r.name, toString(e.event_time) AS time
ORDER BY e.event_time DESC
LIMIT 10
"
```

### Get System Health
```bash
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa "
MATCH (r:Resource)
WITH count(r) AS total_resources
MATCH (e:Episodic)
WHERE e.event_time >= datetime() - duration({hours: 24})
WITH total_resources, count(e) AS total_events,
     sum(CASE WHEN e.severity = 'ERROR' THEN 1 ELSE 0 END) AS errors,
     sum(CASE WHEN e.severity = 'FATAL' THEN 1 ELSE 0 END) AS fatal
RETURN total_resources, total_events, errors, fatal,
       round(toFloat(errors + fatal) / total_events * 100) AS error_rate_pct
"
```

### Find Root Causes
```bash
# Replace EVENT_ID with actual event ID
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa "
MATCH (e:Episodic {eid: 'EVENT_ID'})
OPTIONAL MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(e)
WHERE pc.confidence >= 0.5
RETURN cause.eid, cause.reason, pc.confidence
ORDER BY pc.confidence DESC
LIMIT 5
"
```

### Check Database Stats
```bash
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa "
MATCH (n) WITH labels(n) AS labels, count(*) AS count
UNWIND labels AS label
RETURN label, sum(count) AS total
ORDER BY total DESC
"
```

## Validation Scripts

| Script | Purpose | Runtime |
|--------|---------|---------|
| `test-query-library.sh` | Validate all 17 queries | ~30 sec |
| `test-rca-quality.sh` | Test RCA quality | ~45 sec |
| `interactive-query-test.sh` | Explore queries interactively | Interactive |

## Files

- **Query Library**: `production/neo4j-queries/QUERY_LIBRARY.md`
- **Validation Scripts**: `validation/*.sh`
- **Detailed Report**: `validation/QUERY_LIBRARY_VALIDATION_REPORT.md`
- **Summary**: `QUERY_VALIDATION_SUMMARY.md`

## Troubleshooting

### Authentication Failed
```bash
# Check Neo4j password
grep NEO4J_AUTH docker-compose.yml

# Should be: neo4j/anuragvishwa
```

### Container Not Running
```bash
# Start Neo4j
docker-compose up -d neo4j

# Wait for health check
docker ps | grep neo4j
```

### No Results
```bash
# Check if data is loaded
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (n) RETURN count(n) AS total"

# Should return > 0
```

## Interactive Tester

Best way to explore queries:

```bash
./validation/interactive-query-test.sh

# Select from menu:
# 1. Find recent errors
# 2. Root cause analysis
# 3. Cascading failures
# 4. System health
# ... and more
```

## RCA Quality Verified

✅ Root cause detection working
✅ Confidence scoring (0.0-1.0) accurate
✅ Causal chains (up to 3 hops) detected
✅ Cascading failures (80+ events) identified
✅ Incident clustering operational
✅ Topology traversal functional

## Sample Results

### Causal Chain
```
Root: KubePodCrashLooping
  ↓ confidence: 0.49
  → KubePodCrashLooping
  ↓ confidence: 0.70
  → KubePodCrashLooping
  ↓ confidence: 0.70
Effect: KubePodCrashLooping
```

### Cascading Failure
```
Trigger: NodeClockNotSynchronising
Cascade Count: 82 events
Affected: oom-test, slow-startup-test, stateful-test
```

### Top Error Resource
```
Resource: kube-controller-manager-minikube
Kind: Pod
Namespace: kube-system
Errors: 2,941 (LOG_ERROR)
```

## Conclusion

✅ All queries validated and working
✅ RCA provides meaningful results
✅ No changes needed to query library

**Query library is production-ready.**

---

**Quick Links:**
- [Full Report](./QUERY_LIBRARY_VALIDATION_REPORT.md)
- [Validation Guide](./README.md)
- [Query Library](../production/neo4j-queries/QUERY_LIBRARY.md)
- [Summary](../QUERY_VALIDATION_SUMMARY.md)
