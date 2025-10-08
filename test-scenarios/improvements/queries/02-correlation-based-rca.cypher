// ============================================
// Correlation-Based RCA (No POTENTIAL_CAUSE needed)
// Uses time proximity and resource relationships
// ============================================

// 1. Find events that happened close in time on same pod
// This simulates causality without POTENTIAL_CAUSE
MATCH (e1:Episodic)-[:ABOUT]->(r:Pod)<-[:ABOUT]-(e2:Episodic)
WHERE r.ns = 'kg-testing'
  AND e1.event_id <> e2.event_id
  AND datetime(e1.event_time) < datetime(e2.event_time)
  AND duration.inSeconds(
    datetime(e1.event_time),
    datetime(e2.event_time)
  ).seconds < 300  // 5 minutes
  AND e1.severity IN ['ERROR', 'WARNING']
  AND e2.severity IN ['ERROR', 'FATAL']
RETURN
  e1.event_time as earlier_event_time,
  e1.reason as earlier_reason,
  e1.severity as earlier_severity,
  e2.event_time as later_event_time,
  e2.reason as later_reason,
  e2.severity as later_severity,
  r.name as pod,
  duration.inSeconds(
    datetime(e1.event_time),
    datetime(e2.event_time)
  ).seconds as time_gap_seconds
ORDER BY later_event_time DESC
LIMIT 20;

// 2. Error logs followed by crashes (likely causality)
MATCH (log:Episodic)-[:ABOUT]->(r:Pod)<-[:ABOUT]-(crash:Episodic)
WHERE r.ns = 'kg-testing'
  AND log.etype = 'k8s.log'
  AND log.severity IN ['ERROR', 'FATAL']
  AND crash.etype = 'k8s.event'
  AND crash.reason IN ['BackOff', 'CrashLoopBackOff', 'Error']
  AND datetime(log.event_time) < datetime(crash.event_time)
  AND duration.inSeconds(
    datetime(log.event_time),
    datetime(crash.event_time)
  ).seconds < 60  // Within 1 minute
RETURN
  r.name as pod,
  log.event_time as error_log_time,
  log.message as error_message,
  crash.event_time as crash_time,
  crash.reason as crash_reason,
  duration.inSeconds(
    datetime(log.event_time),
    datetime(crash.event_time)
  ).seconds as seconds_before_crash
ORDER BY crash_time DESC
LIMIT 10;

// 3. Probe failures followed by kills
MATCH (probe:Episodic)-[:ABOUT]->(r:Pod)<-[:ABOUT]-(kill:Episodic)
WHERE r.ns = 'kg-testing'
  AND probe.reason IN ['Unhealthy', 'ProbeWarning']
  AND kill.reason IN ['Killing', 'Killed']
  AND datetime(probe.event_time) < datetime(kill.event_time)
  AND duration.inSeconds(
    datetime(probe.event_time),
    datetime(kill.event_time)
  ).seconds < 120
RETURN
  r.name as pod,
  probe.event_time as probe_failure_time,
  probe.message as probe_message,
  kill.event_time as kill_time,
  duration.inSeconds(
    datetime(probe.event_time),
    datetime(kill.event_time)
  ).seconds as time_to_kill
ORDER BY kill_time DESC;

// 4. Timeline of events for a specific problematic pod
// Replace 'error-logger-test-797d67866b-mr7w8' with your pod name
MATCH (e:Episodic)-[:ABOUT]->(r:Pod)
WHERE r.name CONTAINS 'crashloop'  // or 'oom' or 'error-logger'
  AND r.ns = 'kg-testing'
RETURN
  datetime(e.event_time) as time,
  e.severity as severity,
  e.reason as reason,
  e.etype as type,
  CASE
    WHEN length(e.message) > 100 THEN substring(e.message, 0, 100) + '...'
    ELSE e.message
  END as message
ORDER BY time ASC;

// 5. Cascading errors (multiple errors within short time)
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND e.severity IN ['ERROR', 'FATAL']
WITH
  r.name as resource,
  datetime(e.event_time) as time,
  e.reason as reason
ORDER BY resource, time
WITH resource, collect({time: time, reason: reason}) as events
WHERE size(events) >= 3
RETURN
  resource,
  size(events) as error_count,
  events[0].time as first_error,
  events[-1].time as last_error,
  [event IN events | event.reason] as error_sequence
ORDER BY error_count DESC;

// 6. Check if POTENTIAL_CAUSE exists at all
MATCH ()-[r:POTENTIAL_CAUSE]->()
RETURN
  count(r) as potential_cause_count,
  CASE
    WHEN count(r) = 0 THEN 'RCA NOT WORKING - Using correlation fallback'
    ELSE 'RCA is working'
  END as status;

// 7. Find repeated failures (same error happening multiple times)
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND e.severity IN ['ERROR', 'FATAL']
WITH
  r.name as resource,
  e.reason as reason,
  count(*) as occurrences,
  min(e.event_time) as first_seen,
  max(e.event_time) as last_seen
WHERE occurrences >= 3
RETURN
  resource,
  reason,
  occurrences,
  first_seen,
  last_seen,
  duration.inMinutes(
    datetime(first_seen),
    datetime(last_seen)
  ).minutes as duration_minutes
ORDER BY occurrences DESC;
