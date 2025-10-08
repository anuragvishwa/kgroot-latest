// ============================================
// OOM (Out of Memory) Analysis
// ============================================

// 1. Find OOMKilled events
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND (e.reason = 'OOMKilled'
       OR e.message CONTAINS 'OOM'
       OR e.message CONTAINS 'out of memory')
RETURN
  e.event_time as time,
  e.reason as reason,
  e.severity as severity,
  r.name as pod,
  e.message as message
ORDER BY time DESC
LIMIT 20;

// 2. Memory-related warnings before OOM
MATCH (warning:Episodic)-[:ABOUT]->(r:Pod),
      (oom:Episodic)-[:ABOUT]->(r)
WHERE r.ns = 'kg-testing'
  AND r.name CONTAINS 'oom'
  AND warning.severity = 'WARNING'
  AND (warning.message CONTAINS 'memory'
       OR warning.message CONTAINS 'Allocating')
  AND datetime(warning.event_time) < datetime(oom.event_time)
  AND oom.reason = 'OOMKilled'
RETURN
  warning.event_time as warning_time,
  warning.message as warning,
  oom.event_time as oom_time,
  r.name as pod
ORDER BY warning_time DESC
LIMIT 10;

// 3. OOM kill frequency per pod
MATCH (e:Episodic)-[:ABOUT]->(r:Pod)
WHERE r.ns = 'kg-testing'
  AND e.reason = 'OOMKilled'
RETURN
  r.name as pod,
  count(e) as oom_count,
  min(e.event_time) as first_oom,
  max(e.event_time) as last_oom,
  duration.between(
    datetime(min(e.event_time)),
    datetime(max(e.event_time))
  ) as time_span
ORDER BY oom_count DESC;
