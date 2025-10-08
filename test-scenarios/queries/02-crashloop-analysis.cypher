// ============================================
// CrashLoop Analysis
// ============================================

// 1. Find CrashLoopBackOff events
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND (e.reason CONTAINS 'CrashLoop'
       OR e.reason CONTAINS 'BackOff'
       OR e.message CONTAINS 'CrashLoopBackOff')
RETURN
  e.event_time as time,
  e.reason as reason,
  e.severity as severity,
  r.name as pod,
  e.message as message
ORDER BY time DESC
LIMIT 20;

// 2. Find ERROR logs from crashloop app
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND r.name CONTAINS 'crashloop'
  AND e.severity IN ['ERROR', 'FATAL']
RETURN
  e.event_time as time,
  e.severity as severity,
  e.message as message
ORDER BY time DESC
LIMIT 20;

// 3. Count crash events per pod
MATCH (e:Episodic)-[:ABOUT]->(r:Pod)
WHERE r.ns = 'kg-testing'
  AND (e.reason CONTAINS 'Crash' OR e.reason CONTAINS 'BackOff')
RETURN
  r.name as pod,
  count(e) as crash_count,
  min(e.event_time) as first_crash,
  max(e.event_time) as last_crash
ORDER BY crash_count DESC;

// 4. Find root cause analysis for crashloop
MATCH path = (symptom:Episodic)-[:POTENTIAL_CAUSE*1..3]->(root:Episodic)
WHERE symptom.severity IN ['ERROR', 'FATAL']
  AND exists((symptom)-[:ABOUT]->(:Resource {ns: 'kg-testing'}))
  AND root.reason CONTAINS 'Crash'
RETURN
  symptom.event_time as symptom_time,
  symptom.reason as symptom,
  root.reason as root_cause,
  length(path) as causality_depth
ORDER BY symptom_time DESC
LIMIT 10;
