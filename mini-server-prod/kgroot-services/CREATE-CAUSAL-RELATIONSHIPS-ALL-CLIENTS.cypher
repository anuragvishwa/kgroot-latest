// ============================================================================
// CREATE CAUSAL RELATIONSHIPS FOR ALL CLIENTS (BATCH)
// ============================================================================
// This script creates POTENTIAL_CAUSE relationships for ALL clients
// Each client's causal graph is completely isolated
// ============================================================================

// Get all unique client_ids from Episodic events
MATCH (e:Episodic)
WHERE e.client_id IS NOT NULL
  AND e.event_time > datetime() - duration({hours: 24})
WITH DISTINCT e.client_id as client_id
ORDER BY client_id

WITH collect(client_id) as all_clients
UNWIND all_clients as cid

// For each client, create causal relationships
CALL {
  WITH cid

  MATCH (e1:Episodic)
  WHERE e1.client_id = cid
    AND e1.event_time > datetime() - duration({hours: 24})

  MATCH (e2:Episodic)
  WHERE e2.client_id = cid
    AND e1.client_id = e2.client_id

  // Adaptive time window
  WITH e1, e2, cid,
       CASE
         WHEN e1.reason IN ['OOMKilled', 'Killing', 'Error'] THEN 2
         WHEN e1.reason CONTAINS 'ImagePull' THEN 5
         WHEN e1.reason IN ['FailedScheduling', 'FailedMount'] THEN 15
         ELSE 10
       END as adaptive_window_minutes

  WHERE e2.event_time > e1.event_time
    AND e2.event_time < e1.event_time + duration({minutes: adaptive_window_minutes})

  // Get resources and topology
  OPTIONAL MATCH (e1)-[:ABOUT]->(r1:Resource {client_id: cid})
  OPTIONAL MATCH (e2)-[:ABOUT]->(r2:Resource {client_id: cid})
  OPTIONAL MATCH topology_path = (r1)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r2)
  WHERE ALL(rel IN relationships(topology_path) WHERE rel.client_id = cid)

  WITH e1, e2, r1, r2, topology_path, cid,
       duration.between(e1.event_time, e2.event_time).seconds as time_diff_seconds

  // Domain knowledge patterns
  WITH e1, e2, r1, r2, topology_path, time_diff_seconds, cid,
       CASE
         WHEN e1.reason = 'OOMKilled' AND e2.reason IN ['BackOff', 'Failed', 'Killing'] THEN 0.95
         WHEN e1.reason = 'OOMKilled' AND e2.reason = 'Evicted' THEN 0.90
         WHEN e1.reason = 'MemoryPressure' AND e2.reason IN ['OOMKilled', 'Evicted'] THEN 0.88
         WHEN e1.reason = 'DiskPressure' AND e2.reason IN ['Evicted', 'Failed'] THEN 0.85
         WHEN e1.reason = 'PIDPressure' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.82
         WHEN e1.reason CONTAINS 'ImagePull' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.90
         WHEN e1.reason = 'ImagePullBackOff' AND e2.reason = 'Failed' THEN 0.92
         WHEN e1.reason = 'ErrImagePull' AND e2.reason = 'ImagePullBackOff' THEN 0.93
         WHEN e1.reason = 'InvalidImageName' AND e2.reason CONTAINS 'ImagePull' THEN 0.88
         WHEN e1.reason = 'RegistryUnavailable' AND e2.reason CONTAINS 'ImagePull' THEN 0.87
         WHEN e1.reason = 'Unhealthy' AND e2.reason IN ['Killing', 'Failed', 'BackOff'] THEN 0.88
         WHEN e1.reason = 'ProbeWarning' AND e2.reason = 'Unhealthy' THEN 0.85
         WHEN e1.reason = 'LivenessProbe' AND e2.reason IN ['Killing', 'BackOff'] THEN 0.87
         WHEN e1.reason = 'ReadinessProbe' AND e2.reason = 'Unhealthy' THEN 0.83
         WHEN e1.reason = 'FailedScheduling' AND e2.reason IN ['Pending', 'Failed'] THEN 0.90
         WHEN e1.reason = 'Unschedulable' AND e2.reason = 'FailedScheduling' THEN 0.88
         WHEN e1.reason = 'NodeAffinity' AND e2.reason IN ['FailedScheduling', 'Pending'] THEN 0.86
         WHEN e1.reason = 'Taints' AND e2.reason IN ['FailedScheduling', 'Pending'] THEN 0.85
         WHEN e1.reason = 'InsufficientResources' AND e2.reason = 'FailedScheduling' THEN 0.89
         WHEN e1.reason = 'FailedMount' AND e2.reason IN ['Failed', 'ContainerCreating'] THEN 0.88
         WHEN e1.reason = 'VolumeFailure' AND e2.reason IN ['FailedMount', 'Failed'] THEN 0.87
         WHEN e1.reason = 'FailedAttachVolume' AND e2.reason = 'FailedMount' THEN 0.90
         WHEN e1.reason = 'VolumeNotFound' AND e2.reason IN ['FailedMount', 'Failed'] THEN 0.86
         WHEN e1.reason = 'NetworkNotReady' AND e2.reason IN ['Failed', 'Pending'] THEN 0.85
         WHEN e1.reason = 'FailedCreatePodSandBox' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.87
         WHEN e1.reason = 'CNIFailed' AND e2.reason = 'NetworkNotReady' THEN 0.88
         WHEN e1.reason = 'IPAllocationFailed' AND e2.reason IN ['Failed', 'Pending'] THEN 0.86
         WHEN e1.reason = 'DNSConfigForming' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.82
         WHEN e1.reason = 'Error' AND e2.reason IN ['BackOff', 'Failed', 'CrashLoopBackOff'] THEN 0.87
         WHEN e1.reason = 'Completed' AND e2.reason = 'BackOff' THEN 0.75
         WHEN e1.reason = 'CrashLoopBackOff' AND e2.reason = 'Failed' THEN 0.85
         WHEN e1.reason CONTAINS 'Exit' AND e2.reason IN ['BackOff', 'Failed'] THEN 0.80
         WHEN e1.reason = 'FailedCreate' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.84
         WHEN e1.reason = 'Forbidden' AND e2.reason IN ['Failed', 'FailedCreate'] THEN 0.88
         WHEN e1.reason = 'Unauthorized' AND e2.reason IN ['Failed', 'Forbidden'] THEN 0.87
         WHEN e1.reason = 'InvalidConfiguration' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.86
         WHEN e1.reason = 'ConfigMapNotFound' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.85
         ELSE 0.30
       END as domain_score

  // Temporal score
  WITH e1, e2, r1, r2, topology_path, time_diff_seconds, domain_score, cid,
       CASE
         WHEN time_diff_seconds <= 0 THEN 0.0
         WHEN time_diff_seconds >= 300 THEN 0.1
         ELSE 1.0 - (toFloat(time_diff_seconds) / 300.0) * 0.9
       END as temporal_score

  // Distance score with topology
  WITH e1, e2, time_diff_seconds, domain_score, temporal_score, topology_path, r1, r2, cid,
       CASE
         WHEN r1.name = r2.name AND r1.name IS NOT NULL THEN 0.95
         WHEN topology_path IS NOT NULL AND length(topology_path) = 1 THEN 0.85
         WHEN topology_path IS NOT NULL AND length(topology_path) = 2 THEN 0.70
         WHEN topology_path IS NOT NULL AND length(topology_path) = 3 THEN 0.55
         WHEN r1.ns = r2.ns AND r1.kind = r2.kind AND r1.ns IS NOT NULL THEN 0.40
         ELSE 0.20
       END as distance_score

  // Overall confidence
  WITH e1, e2, temporal_score, distance_score, domain_score, time_diff_seconds, cid,
       (0.4 * temporal_score + 0.3 * distance_score + 0.3 * domain_score) as confidence

  WHERE confidence > 0.3

  // Top-M filtering
  WITH e2, e1, confidence, temporal_score, distance_score, domain_score, time_diff_seconds, cid
  ORDER BY e2.eid, confidence DESC

  WITH e2, cid, collect({
    e1_id: e1.eid,
    confidence: confidence,
    temporal_score: temporal_score,
    distance_score: distance_score,
    domain_score: domain_score,
    time_diff_seconds: time_diff_seconds
  })[0..5] as top_causes

  UNWIND top_causes as cause

  MATCH (e1:Episodic {eid: cause.e1_id, client_id: cid})

  MERGE (e1)-[pc:POTENTIAL_CAUSE]->(e2)
  ON CREATE SET
    pc.client_id = cid,
    pc.confidence = round(cause.confidence * 1000.0) / 1000.0,
    pc.temporal_score = round(cause.temporal_score * 1000.0) / 1000.0,
    pc.distance_score = round(cause.distance_score * 1000.0) / 1000.0,
    pc.domain_score = round(cause.domain_score * 1000.0) / 1000.0,
    pc.time_gap_seconds = cause.time_diff_seconds,
    pc.created_at = datetime(),
    pc.version = 'enhanced_v1_batch'
  ON MATCH SET
    pc.confidence = round(cause.confidence * 1000.0) / 1000.0,
    pc.temporal_score = round(cause.temporal_score * 1000.0) / 1000.0,
    pc.distance_score = round(cause.distance_score * 1000.0) / 1000.0,
    pc.domain_score = round(cause.domain_score * 1000.0) / 1000.0,
    pc.time_gap_seconds = cause.time_diff_seconds,
    pc.updated_at = datetime()

  RETURN count(*) as rels_created
}

RETURN
  cid as client_id,
  rels_created as causal_relationships_created
ORDER BY client_id;


// ============================================================================
// Verification per client
// ============================================================================

MATCH (e:Episodic)
WHERE e.client_id IS NOT NULL
WITH DISTINCT e.client_id as client_id

CALL {
  WITH client_id
  MATCH (e1:Episodic {client_id: client_id})-[pc:POTENTIAL_CAUSE {client_id: client_id}]->(e2:Episodic {client_id: client_id})
  RETURN
    count(pc) as total_rels,
    round(avg(pc.confidence) * 1000.0) / 1000.0 as avg_conf,
    count(CASE WHEN pc.distance_score IN [0.85, 0.70, 0.55] THEN 1 END) as topology_enhanced
}

RETURN
  client_id,
  total_rels,
  avg_conf,
  topology_enhanced
ORDER BY client_id;


// ============================================================================
// CRITICAL: Check cross-tenant violations
// ============================================================================

MATCH (e1:Episodic)-[pc:POTENTIAL_CAUSE]->(e2:Episodic)
WHERE e1.client_id <> e2.client_id
   OR e1.client_id <> pc.client_id
   OR e2.client_id <> pc.client_id
RETURN
  count(*) as cross_tenant_violations,
  'MUST be 0!' as warning,
  collect({
    from_client: e1.client_id,
    to_client: e2.client_id,
    rel_client: pc.client_id
  })[0..10] as sample_violations;
