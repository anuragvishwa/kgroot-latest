// ============================================
// Probe Failures (Readiness/Liveness)
// ============================================

// 1. Find readiness probe failures
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND (e.reason CONTAINS 'Unhealthy'
       OR e.message CONTAINS 'readiness probe'
       OR e.message CONTAINS 'liveness probe')
RETURN
  e.event_time as time,
  e.reason as reason,
  e.severity as severity,
  r.name as pod,
  e.message as message
ORDER BY time DESC
LIMIT 20;

// 2. Slow startup detection (multiple probe failures)
MATCH (e:Episodic)-[:ABOUT]->(r:Pod)
WHERE r.ns = 'kg-testing'
  AND r.name CONTAINS 'slow-startup'
  AND e.message CONTAINS 'probe'
RETURN
  r.name as pod,
  count(e) as probe_failure_count,
  min(e.event_time) as first_failure,
  max(e.event_time) as last_failure,
  duration.inSeconds(
    datetime(min(e.event_time)),
    datetime(max(e.event_time))
  ).seconds as startup_duration_seconds
ORDER BY probe_failure_count DESC;

// 3. Pods with probe failures by severity
MATCH (e:Episodic)-[:ABOUT]->(r:Pod)
WHERE r.ns = 'kg-testing'
  AND (e.message CONTAINS 'probe' OR e.reason CONTAINS 'Unhealthy')
RETURN
  r.name as pod,
  e.severity as severity,
  count(*) as count
ORDER BY pod, severity;
