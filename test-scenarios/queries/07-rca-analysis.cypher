// ============================================
// Root Cause Analysis (RCA)
// ============================================

// 1. Find all root causes for test namespace errors
MATCH path = (symptom:Episodic)-[:POTENTIAL_CAUSE*1..3]->(root:Episodic)
WHERE exists((symptom)-[:ABOUT]->(:Resource {ns: 'kg-testing'}))
  AND symptom.severity IN ['ERROR', 'FATAL']
RETURN
  symptom.event_time as symptom_time,
  symptom.reason as symptom,
  symptom.severity as symptom_severity,
  root.event_time as root_time,
  root.reason as root_cause,
  length(path) as causality_chain_length
ORDER BY symptom_time DESC
LIMIT 20;

// 2. Most common root causes
MATCH (symptom:Episodic)-[:POTENTIAL_CAUSE]->(root:Episodic)
WHERE exists((symptom)-[:ABOUT]->(:Resource {ns: 'kg-testing'}))
RETURN
  root.reason as root_cause,
  root.severity as severity,
  count(DISTINCT symptom) as affected_events,
  count(DISTINCT root) as root_event_count
ORDER BY affected_events DESC
LIMIT 10;

// 3. Cascading failures (events with multiple causes)
MATCH (symptom:Episodic)-[:POTENTIAL_CAUSE]->(cause:Episodic)
WHERE exists((symptom)-[:ABOUT]->(:Resource {ns: 'kg-testing'}))
WITH symptom, collect(cause.reason) as causes, count(cause) as cause_count
WHERE cause_count > 1
RETURN
  symptom.event_time as time,
  symptom.reason as symptom,
  cause_count,
  causes
ORDER BY cause_count DESC, time DESC
LIMIT 10;

// 4. Impact radius (how many events stem from one root cause)
MATCH path = (symptom:Episodic)-[:POTENTIAL_CAUSE*1..3]->(root:Episodic)
WHERE exists((root)-[:ABOUT]->(:Resource {ns: 'kg-testing'}))
WITH root, count(DISTINCT symptom) as impact_count
WHERE impact_count > 3
RETURN
  root.event_time as root_time,
  root.reason as root_cause,
  root.severity as severity,
  impact_count as events_affected
ORDER BY impact_count DESC
LIMIT 10;

// 5. Cross-pod impact (errors affecting multiple pods)
MATCH (e1:Episodic)-[:ABOUT]->(r1:Pod),
      (e2:Episodic)-[:ABOUT]->(r2:Pod)
WHERE r1.ns = 'kg-testing' AND r2.ns = 'kg-testing'
  AND r1.name <> r2.name
  AND e1.severity IN ['ERROR', 'FATAL']
  AND e2.severity IN ['ERROR', 'FATAL']
  AND abs(duration.inSeconds(
    datetime(e1.event_time),
    datetime(e2.event_time)
  ).seconds) < 10
RETURN
  e1.event_time as time1,
  r1.name as pod1,
  e1.reason as reason1,
  r2.name as pod2,
  e2.reason as reason2
ORDER BY time1 DESC
LIMIT 10;
