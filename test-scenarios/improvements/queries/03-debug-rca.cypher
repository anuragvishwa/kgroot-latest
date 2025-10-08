// ============================================
// Debug RCA - Find out why POTENTIAL_CAUSE is missing
// ============================================

// 1. Check if POTENTIAL_CAUSE relationship exists ANYWHERE
MATCH (s)-[r:POTENTIAL_CAUSE]->(t)
RETURN
  labels(s) as source_labels,
  s.event_time as source_time,
  s.reason as source_reason,
  labels(t) as target_labels,
  t.event_time as target_time,
  t.reason as target_reason,
  r.weight as weight
LIMIT 10;

// 2. Count all relationship types in the graph
MATCH ()-[r]->()
RETURN
  type(r) as relationship_type,
  count(*) as count
ORDER BY count DESC;

// 3. Find candidate pairs that SHOULD have POTENTIAL_CAUSE
// (Events on same pod, within 15 min, error before fatal)
MATCH (earlier:Episodic)-[:ABOUT]->(r:Resource)<-[:ABOUT]-(later:Episodic)
WHERE r.ns = 'kg-testing'
  AND earlier.event_id <> later.event_id
  AND datetime(earlier.event_time) < datetime(later.event_time)
  AND duration.inMinutes(
    datetime(earlier.event_time),
    datetime(later.event_time)
  ).minutes <= 15
  AND earlier.severity IN ['WARNING', 'ERROR']
  AND later.severity IN ['ERROR', 'FATAL']
WITH
  earlier,
  later,
  r,
  duration.inMinutes(
    datetime(earlier.event_time),
    datetime(later.event_time)
  ).minutes as gap_minutes
RETURN
  r.name as resource,
  earlier.event_time as earlier_time,
  earlier.reason as earlier_reason,
  earlier.severity as earlier_severity,
  later.event_time as later_time,
  later.reason as later_reason,
  later.severity as later_severity,
  gap_minutes,
  exists((earlier)-[:POTENTIAL_CAUSE]->(later)) as has_rca_link
ORDER BY later_time DESC
LIMIT 20;

// 4. Check graph-builder configuration in events
// Look for any events that mention RCA or causality
MATCH (e:Episodic)
WHERE r.ns = 'kg-testing'
  AND (e.message CONTAINS 'RCA' OR e.message CONTAINS 'cause')
RETURN
  e.event_time,
  e.reason,
  e.message
LIMIT 10;

// 5. Find all ERROR → FATAL sequences (prime candidates for RCA)
MATCH (err:Episodic)-[:ABOUT]->(r:Pod)
WHERE r.ns = 'kg-testing'
  AND err.severity = 'ERROR'
WITH r, collect(err) as errors
MATCH (fatal:Episodic)-[:ABOUT]->(r)
WHERE fatal.severity = 'FATAL'
  AND datetime(fatal.event_time) > datetime(errors[0].event_time)
RETURN
  r.name as pod,
  size(errors) as error_count_before_fatal,
  errors[0].event_time as first_error,
  fatal.event_time as fatal_time,
  fatal.reason as fatal_reason,
  exists((errors[0])-[:POTENTIAL_CAUSE]->(fatal)) as has_rca
LIMIT 10;

// 6. Check event properties (ensure required fields exist for RCA)
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
RETURN
  e.event_id as has_event_id,
  e.event_time as has_event_time,
  e.severity as has_severity,
  e.reason as has_reason,
  r.uid as has_resource_uid,
  labels(r) as resource_type
LIMIT 5;

// 7. Find the most recent events (check data freshness)
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
WITH max(datetime(e.event_time)) as latest
RETURN
  latest as latest_event_time,
  duration.inSeconds(latest, datetime()).seconds as seconds_ago,
  CASE
    WHEN duration.inSeconds(latest, datetime()).seconds < 120 THEN 'Data is fresh'
    ELSE 'Data may be stale'
  END as status;
