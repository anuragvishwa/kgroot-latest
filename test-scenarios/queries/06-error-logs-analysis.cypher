// ============================================
// Error Logs Analysis
// ============================================

// 1. All ERROR and FATAL logs from test namespace
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND e.severity IN ['ERROR', 'FATAL']
  AND e.etype = 'k8s.log'
RETURN
  e.event_time as time,
  e.severity as severity,
  r.name as pod,
  e.message as message
ORDER BY time DESC
LIMIT 50;

// 2. Error patterns (grouping similar errors)
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND e.severity = 'ERROR'
  AND e.etype = 'k8s.log'
WITH
  CASE
    WHEN e.message CONTAINS 'Database' THEN 'Database Errors'
    WHEN e.message CONTAINS 'timeout' THEN 'Timeout Errors'
    WHEN e.message CONTAINS 'HTTP' THEN 'HTTP Errors'
    WHEN e.message CONTAINS 'exception' OR e.message CONTAINS 'Exception' THEN 'Exceptions'
    WHEN e.message CONTAINS 'Failed' OR e.message CONTAINS 'failed' THEN 'Operation Failures'
    ELSE 'Other'
  END as error_category,
  count(*) as count
RETURN
  error_category,
  count
ORDER BY count DESC;

// 3. Most verbose pods (logging most errors)
MATCH (e:Episodic)-[:ABOUT]->(r:Pod)
WHERE r.ns = 'kg-testing'
  AND e.severity IN ['ERROR', 'FATAL', 'WARNING']
RETURN
  r.name as pod,
  e.severity as severity,
  count(*) as log_count
ORDER BY pod, severity;

// 4. Find exception traces
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND (e.message CONTAINS 'Traceback'
       OR e.message CONTAINS 'traceback'
       OR e.message CONTAINS 'ZeroDivisionError')
RETURN
  e.event_time as time,
  r.name as pod,
  e.message as exception
ORDER BY time DESC
LIMIT 10;
