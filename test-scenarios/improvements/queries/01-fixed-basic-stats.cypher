// ============================================
// Basic Statistics - FIXED VERSION
// ============================================

// 1. Count all events in kg-testing namespace
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
RETURN
  e.etype as event_type,
  e.severity as severity,
  count(*) as count
ORDER BY count DESC;

// 2. Count resources in test namespace
MATCH (r:Resource)
WHERE r.ns = 'kg-testing'
RETURN
  labels(r) as resource_types,
  count(*) as count
ORDER BY count DESC;

// 3. Event timeline (last 30 minutes)
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND datetime(e.event_time) > datetime() - duration('PT30M')
RETURN
  datetime(e.event_time) as time,
  e.etype as type,
  e.severity as severity,
  e.reason as reason,
  r.name as resource
ORDER BY time DESC
LIMIT 50;

// 4. Severity distribution (FIXED - removed OVER clause)
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
WITH e.severity as severity, count(*) as count
WITH severity, count, sum(count) as total
RETURN
  severity,
  count,
  round(count * 100.0 / total, 2) as percentage
ORDER BY count DESC;

// 5. Events per hour (trend analysis)
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND datetime(e.event_time) > datetime() - duration('PT2H')
WITH
  datetime(e.event_time).hour as hour,
  count(*) as events
RETURN hour, events
ORDER BY hour;

// 6. Most problematic resources (by error count)
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND e.severity IN ['ERROR', 'FATAL']
RETURN
  r.name as resource,
  labels(r) as type,
  count(e) as error_count
ORDER BY error_count DESC
LIMIT 10;
