// ============================================================================
// ENHANCED CAUSAL RELATIONSHIP CREATION (Non-ML KGroot Improvements)
// ============================================================================
// Improvements over basic version:
// 1. Service topology integration (uses SELECTS/RUNS_ON/CONTROLS)
// 2. 30+ domain knowledge patterns (vs 5 in basic version)
// 3. Alarm event ranking (Equation 3 from paper)
// 4. Adaptive time windows per failure type
// 5. Top-M relationships per event (reduces false positives)
// ============================================================================

// ============================================================================
// STEP 1: Create enhanced POTENTIAL_CAUSE relationships
// ============================================================================

MATCH (e1:Episodic {client_id: 'ab-01'})
WHERE e1.event_time > datetime() - duration({hours: 24})

MATCH (e2:Episodic {client_id: 'ab-01'})

// Adaptive time window based on failure type
WITH e1, e2,
     CASE
       WHEN e1.reason IN ['OOMKilled', 'Killing', 'Error'] THEN 2      // Fast propagation
       WHEN e1.reason CONTAINS 'ImagePull' THEN 5                       // Medium propagation
       WHEN e1.reason IN ['FailedScheduling', 'FailedMount'] THEN 15   // Slow propagation
       ELSE 10                                                           // Default
     END as adaptive_window_minutes

WHERE e2.event_time > e1.event_time
  AND e2.event_time < e1.event_time + duration({minutes: adaptive_window_minutes})

// Get resources
OPTIONAL MATCH (e1)-[:ABOUT]->(r1:Resource)
OPTIONAL MATCH (e2)-[:ABOUT]->(r2:Resource)

// Get service topology path (NEW!)
OPTIONAL MATCH topology_path = (r1)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r2)

// Calculate time difference
WITH e1, e2, r1, r2, topology_path,
     duration.between(e1.event_time, e2.event_time).seconds as time_diff_seconds

// ===== ENHANCED DOMAIN SCORE (30+ patterns) =====
WITH e1, e2, r1, r2, topology_path, time_diff_seconds,
     CASE
       // ===== Resource Exhaustion (5 patterns) =====
       WHEN e1.reason = 'OOMKilled' AND e2.reason IN ['BackOff', 'Failed', 'Killing'] THEN 0.95
       WHEN e1.reason = 'Evicted' AND e2.reason IN ['Pending', 'BackOff'] THEN 0.92
       WHEN e1.message CONTAINS 'disk pressure' AND e2.reason = 'Evicted' THEN 0.90
       WHEN e1.message CONTAINS 'memory pressure' AND e2.reason = 'OOMKilled' THEN 0.88
       WHEN e1.reason CONTAINS 'ResourceExhausted' AND e2.reason = 'Failed' THEN 0.85

       // ===== Image/Registry (5 patterns) =====
       WHEN e1.reason CONTAINS 'ImagePull' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.90
       WHEN e1.reason = 'ErrImagePull' AND e2.reason = 'ImagePullBackOff' THEN 0.95
       WHEN e1.message CONTAINS 'manifest unknown' AND e2.reason = 'Failed' THEN 0.88
       WHEN e1.message CONTAINS 'pull access denied' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.87
       WHEN e1.message CONTAINS 'image not found' AND e2.reason = 'ErrImagePull' THEN 0.90

       // ===== Health Checks (4 patterns) =====
       WHEN e1.reason = 'Unhealthy' AND e2.reason IN ['BackOff', 'Failed', 'Killing'] THEN 0.80
       WHEN e1.message CONTAINS 'Liveness probe failed' AND e2.reason = 'Killing' THEN 0.92
       WHEN e1.message CONTAINS 'Readiness probe failed' AND e2.reason = 'Unhealthy' THEN 0.85
       WHEN e1.message CONTAINS 'probe timeout' AND e2.reason IN ['Unhealthy', 'Failed'] THEN 0.78

       // ===== Scheduling (5 patterns) =====
       WHEN e1.reason = 'FailedScheduling' AND e2.reason IN ['Pending', 'Failed'] THEN 0.88
       WHEN e1.message CONTAINS 'Insufficient cpu' AND e2.reason = 'FailedScheduling' THEN 0.90
       WHEN e1.message CONTAINS 'Insufficient memory' AND e2.reason = 'FailedScheduling' THEN 0.90
       WHEN e1.message CONTAINS 'node affinity' AND e2.reason IN ['FailedScheduling', 'Pending'] THEN 0.75
       WHEN e1.message CONTAINS 'no nodes available' AND e2.reason = 'FailedScheduling' THEN 0.85

       // ===== Volume/Mount (4 patterns) =====
       WHEN e1.reason = 'FailedMount' AND e2.reason IN ['BackOff', 'Failed'] THEN 0.85
       WHEN e1.message CONTAINS 'Volume not found' AND e2.reason = 'FailedMount' THEN 0.90
       WHEN e1.message CONTAINS 'MountVolume.SetUp failed' AND e2.reason = 'BackOff' THEN 0.87
       WHEN e1.message CONTAINS 'volume already attached' AND e2.reason = 'FailedMount' THEN 0.82

       // ===== Network (5 patterns) =====
       WHEN e1.reason = 'NetworkNotReady' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.78
       WHEN e1.message CONTAINS 'dial tcp' AND e2.reason = 'Unhealthy' THEN 0.75
       WHEN e1.message CONTAINS 'connection refused' AND e2.reason IN ['BackOff', 'Unhealthy'] THEN 0.82
       WHEN e1.message CONTAINS 'timeout' AND e2.reason IN ['Failed', 'Unhealthy'] THEN 0.70
       WHEN e1.message CONTAINS 'dns' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.73

       // ===== Crash/Exit (4 patterns) =====
       WHEN e1.reason = 'Killing' AND e2.reason = 'BackOff' THEN 0.90
       WHEN e1.message CONTAINS 'exit status' AND e2.reason = 'BackOff' THEN 0.85
       WHEN e1.message CONTAINS 'CrashLoopBackOff' AND e2.reason = 'Failed' THEN 0.88
       WHEN e1.message CONTAINS 'signal: killed' AND e2.reason IN ['BackOff', 'Failed'] THEN 0.83

       // ===== Config/RBAC (5 patterns) =====
       WHEN e1.message CONTAINS 'configmap' AND e2.reason = 'BackOff' THEN 0.70
       WHEN e1.message CONTAINS 'secret' AND e2.reason IN ['BackOff', 'Failed'] THEN 0.72
       WHEN e1.message CONTAINS 'forbidden' AND e2.reason = 'Failed' THEN 0.82
       WHEN e1.message CONTAINS 'unauthorized' AND e2.reason = 'BackOff' THEN 0.80
       WHEN e1.message CONTAINS 'permission denied' AND e2.reason = 'Failed' THEN 0.85

       // ===== Cascading Failures (3 patterns) =====
       WHEN e1.reason = 'ServiceDown' AND e2.reason IN ['HighLatency', 'ErrorRateHigh'] THEN 0.75
       WHEN e1.reason = 'PodRestart' AND e2.reason = 'ServiceDown' THEN 0.80
       WHEN e1.reason IN ['Failed', 'BackOff'] AND e2.reason = 'ServiceDown' THEN 0.70

       // ===== Generic Failures (2 patterns) =====
       WHEN e1.reason = 'Failed' AND e2.reason = 'BackOff' THEN 0.85
       WHEN r1.name = r2.name AND r1.name IS NOT NULL THEN 0.65

       ELSE 0.30
     END as domain_score

// ===== TEMPORAL SCORE (same as before) =====
WITH e1, e2, r1, r2, topology_path, time_diff_seconds, domain_score,
     CASE
       WHEN time_diff_seconds <= 0 THEN 0.0
       WHEN time_diff_seconds >= 300 THEN 0.1
       ELSE 1.0 - (toFloat(time_diff_seconds) / 300.0) * 0.9
     END as temporal_score

// ===== ENHANCED DISTANCE SCORE (with topology!) =====
WITH e1, e2, time_diff_seconds, domain_score, temporal_score, topology_path, r1, r2,
     CASE
       WHEN r1.name = r2.name AND r1.name IS NOT NULL THEN 0.95              // Same resource
       WHEN topology_path IS NOT NULL AND length(topology_path) = 1 THEN 0.85 // Direct dependency
       WHEN topology_path IS NOT NULL AND length(topology_path) = 2 THEN 0.70 // 2-hop dependency
       WHEN topology_path IS NOT NULL AND length(topology_path) = 3 THEN 0.55 // 3-hop dependency
       WHEN r1.ns = r2.ns AND r1.kind = r2.kind AND r1.ns IS NOT NULL THEN 0.40  // Same type/ns
       ELSE 0.20                                                               // Unrelated
     END as distance_score

// ===== OVERALL CONFIDENCE =====
WITH e1, e2, temporal_score, distance_score, domain_score, time_diff_seconds,
     (0.4 * temporal_score + 0.3 * distance_score + 0.3 * domain_score) as confidence

WHERE confidence > 0.3

// ===== TOP-M RELATIONSHIPS (M=5 from paper) =====
// Only keep top 5 causes per event to reduce false positives
WITH e2, e1, confidence, temporal_score, distance_score, domain_score, time_diff_seconds
ORDER BY e2.eid, confidence DESC

WITH e2, collect({
  e1_id: e1.eid,
  confidence: confidence,
  temporal_score: temporal_score,
  distance_score: distance_score,
  domain_score: domain_score,
  time_diff_seconds: time_diff_seconds
})[0..5] as top_causes  // Keep only top 5

UNWIND top_causes as cause

// Match the cause event by ID
MATCH (e1:Episodic {eid: cause.e1_id})

// Create the relationship
MERGE (e1)-[pc:POTENTIAL_CAUSE]->(e2)
SET pc.confidence = round(cause.confidence * 1000.0) / 1000.0,
    pc.temporal_score = round(cause.temporal_score * 1000.0) / 1000.0,
    pc.distance_score = round(cause.distance_score * 1000.0) / 1000.0,
    pc.domain_score = round(cause.domain_score * 1000.0) / 1000.0,
    pc.time_gap_seconds = cause.time_diff_seconds,
    pc.created_at = datetime(),
    pc.version = 'enhanced_v1'

RETURN count(*) as total_relationships_created;


// ============================================================================
// STEP 2: Detect alarm events (high-severity, user-facing)
// ============================================================================

// Mark critical events as alarms
MATCH (e:Episodic {client_id: 'ab-01'})
WHERE e.event_time > datetime() - duration({hours: 1})
  AND e.severity = 'WARNING'
  AND e.reason IN ['BackOff', 'Failed', 'Unhealthy', 'ServiceDown']

SET e:AlarmEvent

RETURN count(e) as alarm_events_detected;


// ============================================================================
// STEP 3: Rank root causes using KGroot Equation 3
// ============================================================================

// Find root causes for alarms with time+distance ranking
MATCH (alarm:AlarmEvent)
WHERE alarm.client_id = 'ab-01'
  AND alarm.event_time > datetime() - duration({hours: 1})

MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..5]->(alarm)
WHERE NOT ()-[:POTENTIAL_CAUSE]->(root)  // True root (no upstream causes)

WITH root, alarm, path,
     length(path) as hops,
     duration.between(root.event_time, alarm.event_time).seconds as time_gap,
     [rel in relationships(path) | rel.confidence] as path_confidences

// Calculate average path confidence
WITH root, alarm, hops, time_gap,
     reduce(sum = 0.0, c IN path_confidences | sum + c) / size(path_confidences) as avg_path_confidence

// Calculate normalized scores (0-1 range, lower is better)
// Temporal score: normalized time gap (earlier = better = lower score)
// Distance score: normalized hops (closer = better = lower score)
WITH root, alarm, hops, time_gap, avg_path_confidence,
     toFloat(time_gap) / 3600.0 as temporal_score_normalized,  // Normalize by 1 hour
     toFloat(hops) / 5.0 as distance_score_normalized           // Normalize by max 5 hops

// Final ranking (Wt=0.6, Wd=0.4 from paper)
// Lower score = better (closer to alarm)
WITH root, alarm, hops, time_gap, avg_path_confidence,
     (0.6 * temporal_score_normalized + 0.4 * distance_score_normalized) as final_rank

RETURN
  alarm.reason as alarm_type,
  alarm.event_time as alarm_time,
  root.reason as root_cause,
  root.message as root_cause_message,
  root.event_time as root_cause_time,
  final_rank,
  avg_path_confidence as path_confidence,
  hops,
  time_gap as propagation_time_seconds
ORDER BY alarm.eid, final_rank ASC
LIMIT 20;


// ============================================================================
// STEP 4: Verify what was created
// ============================================================================

MATCH ()-[pc:POTENTIAL_CAUSE {version: 'enhanced_v1'}]->()
RETURN
  count(pc) as total_relationships,
  avg(pc.confidence) as avg_confidence,
  avg(pc.temporal_score) as avg_temporal,
  avg(pc.distance_score) as avg_distance,
  avg(pc.domain_score) as avg_domain,
  max(pc.confidence) as max_confidence,
  min(pc.confidence) as min_confidence;


// ============================================================================
// STEP 5: Compare with topology-enhanced relationships
// ============================================================================

// Count relationships that used topology
MATCH ()-[pc:POTENTIAL_CAUSE {version: 'enhanced_v1'}]->()
WHERE pc.distance_score IN [0.85, 0.70, 0.55]  // These scores indicate topology usage
RETURN count(pc) as topology_enhanced_relationships;


// ============================================================================
// STEP 6: Test RCA query with enhanced relationships
// ============================================================================

MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 60})
  AND e.client_id = 'ab-01'
  AND e.severity = 'WARNING'

OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource)
OPTIONAL MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE {version: 'enhanced_v1'}]->(e)

RETURN
  e.reason as failure_reason,
  e.message as failure_message,
  e.event_time as when_failed,
  r.name as resource_name,
  collect({
    cause_reason: cause.reason,
    cause_message: cause.message,
    cause_time: cause.event_time,
    confidence: pc.confidence,
    temporal_score: pc.temporal_score,
    distance_score: pc.distance_score,
    domain_score: pc.domain_score,
    time_gap: pc.time_gap_seconds,
    topology_used: pc.distance_score IN [0.85, 0.70, 0.55]
  }) as root_causes
ORDER BY e.event_time DESC
LIMIT 10;


// ============================================================================
// OPTIONAL: Clean up old basic relationships (if you want fresh start)
// ============================================================================

// CAUTION: Uncomment only if you want to delete old relationships
// MATCH ()-[pc:POTENTIAL_CAUSE]->()
// WHERE pc.version IS NULL OR pc.version <> 'enhanced_v1'
// DELETE pc
// RETURN count(*) as deleted_old_relationships;
