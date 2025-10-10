// ============================================
// Basic Statistics - Overview of Test Data
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

// 4. Severity distribution
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
WITH e.severity as severity, count(*) as count
WITH collect({severity: severity, count: count}) as groups, sum(count) as total
UNWIND groups as group
RETURN
  group.severity as severity,
  group.count as count,
  round(group.count * 100.0 / total, 2) as percentage
ORDER BY count DESC;
