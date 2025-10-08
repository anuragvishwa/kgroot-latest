// ============================================
// Image Pull Errors
// ============================================

// 1. Find ImagePullBackOff events
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND (e.reason CONTAINS 'ImagePull'
       OR e.reason = 'ErrImagePull'
       OR e.reason = 'ImagePullBackOff')
RETURN
  e.event_time as time,
  e.reason as reason,
  e.severity as severity,
  r.name as pod,
  e.message as message
ORDER BY time DESC
LIMIT 20;

// 2. Identify problematic images
MATCH (e:Episodic)-[:ABOUT]->(r:Pod)
WHERE r.ns = 'kg-testing'
  AND e.reason IN ['ErrImagePull', 'ImagePullBackOff']
WITH r.name as pod, e.message as message
WHERE message CONTAINS 'image'
RETURN
  pod,
  message
LIMIT 10;

// 3. Timeline of image pull attempts
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND r.name = 'image-pull-fail'
RETURN
  datetime(e.event_time) as time,
  e.reason as reason,
  e.severity as severity
ORDER BY time DESC
LIMIT 30;
