// ============================================================================
// CREATE POTENTIAL_CAUSE RELATIONSHIPS IN NEO4J
// ============================================================================
// This script creates causal relationships between events with confidence scores
// Run this in Neo4j Browser or via cypher-shell
// ============================================================================

// Step 1: Check current state (should be 0)
// ----------------------------------------------------------------------------
MATCH ()-[pc:POTENTIAL_CAUSE]->()
RETURN count(pc) as existing_relationships;

// If you got 0, continue to Step 2
// If you got > 0, skip to Step 3 to verify what exists

// ============================================================================
// Step 2: Create POTENTIAL_CAUSE relationships
// ============================================================================

// This creates relationships for events in last 24 hours
// Adjust the time window as needed: hours: 24, hours: 48, days: 7, etc.

MATCH (e1:Episodic {client_id: 'ab-01'})
WHERE e1.event_time > datetime() - duration({hours: 24})

MATCH (e2:Episodic {client_id: 'ab-01'})
WHERE e2.event_time > e1.event_time
  AND e2.event_time < e1.event_time + duration({minutes: 10})

// Get resources
OPTIONAL MATCH (e1)-[:ABOUT]->(r1:Resource)
OPTIONAL MATCH (e2)-[:ABOUT]->(r2:Resource)

// Calculate time difference in seconds
WITH e1, e2, r1, r2,
     duration.between(e1.event_time, e2.event_time).seconds as time_diff_seconds

// Calculate domain score (Kubernetes causality rules)
WITH e1, e2, r1, r2, time_diff_seconds,
     CASE
       // High confidence: OOMKilled patterns
       WHEN e1.reason = 'OOMKilled' AND e2.reason IN ['BackOff', 'Failed', 'Killing'] THEN 0.95

       // High confidence: Image pull failures
       WHEN e1.reason CONTAINS 'ImagePull' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.90
       WHEN e1.reason = 'Failed' AND e1.message CONTAINS 'pull' AND e2.reason = 'BackOff' THEN 0.90

       // High confidence: Unhealthy -> restart patterns
       WHEN e1.reason = 'Unhealthy' AND e2.reason IN ['BackOff', 'Failed', 'Killing'] THEN 0.80

       // Medium-high: Generic failure patterns
       WHEN e1.reason = 'Failed' AND e2.reason = 'BackOff' THEN 0.85
       WHEN e1.reason IN ['FailedMount', 'FailedScheduling'] AND e2.reason IN ['BackOff', 'Failed'] THEN 0.80

       // Medium: Same pod, different reasons
       WHEN r1.name = r2.name AND r1.name IS NOT NULL THEN 0.65

       // Low-medium: Same namespace, same kind
       WHEN r1.ns = r2.ns AND r1.kind = r2.kind AND r1.ns IS NOT NULL THEN 0.50

       // Low: Same namespace
       WHEN r1.ns = r2.ns AND r1.ns IS NOT NULL THEN 0.40

       ELSE 0.30
     END as domain_score

// Calculate temporal score (closer in time = higher score)
// Using linear decay: 1.0 at t=0, 0.0 at t=300s (5 minutes)
WITH e1, e2, r1, r2, time_diff_seconds, domain_score,
     CASE
       WHEN time_diff_seconds <= 0 THEN 0.0
       WHEN time_diff_seconds >= 300 THEN 0.1  // Min score for events within window
       ELSE 1.0 - (toFloat(time_diff_seconds) / 300.0) * 0.9  // Linear decay
     END as temporal_score

// Calculate distance score (graph proximity)
WITH e1, e2, time_diff_seconds, domain_score, temporal_score,
     CASE
       WHEN r1.name = r2.name AND r1.name IS NOT NULL THEN 0.95  // Same pod (very close)
       WHEN r1.ns = r2.ns AND r1.kind = r2.kind AND r1.ns IS NOT NULL THEN 0.60  // Same namespace/kind
       WHEN r1.ns = r2.ns AND r1.ns IS NOT NULL THEN 0.40  // Same namespace
       ELSE 0.20  // Different namespace (far)
     END as distance_score

// Calculate overall confidence (weighted combination)
// Formula: 40% temporal + 30% distance + 30% domain
WITH e1, e2, temporal_score, distance_score, domain_score,
     (0.4 * temporal_score + 0.3 * distance_score + 0.3 * domain_score) as confidence

// Only create relationships above minimum threshold
WHERE confidence > 0.3

// Create the POTENTIAL_CAUSE relationship
MERGE (e1)-[pc:POTENTIAL_CAUSE]->(e2)
SET pc.confidence = round(confidence * 1000.0) / 1000.0,
    pc.temporal_score = round(temporal_score * 1000.0) / 1000.0,
    pc.distance_score = round(distance_score * 1000.0) / 1000.0,
    pc.domain_score = round(domain_score * 1000.0) / 1000.0,
    pc.time_gap_seconds = time_diff_seconds,
    pc.created_at = datetime(),
    pc.created_by = 'manual_script'

RETURN count(*) as total_relationships_created;


// ============================================================================
// Step 3: Verify what was created
// ============================================================================

// Count total relationships
MATCH ()-[pc:POTENTIAL_CAUSE]->()
RETURN count(pc) as total_relationships,
       avg(pc.confidence) as avg_confidence,
       min(pc.confidence) as min_confidence,
       max(pc.confidence) as max_confidence;


// View top confidence relationships
MATCH (e1:Episodic)-[pc:POTENTIAL_CAUSE]->(e2:Episodic)
WHERE e1.client_id = 'ab-01'
RETURN
  e1.reason as cause_reason,
  e2.reason as effect_reason,
  pc.confidence as confidence,
  pc.temporal_score as temporal,
  pc.distance_score as distance,
  pc.domain_score as domain,
  pc.time_gap_seconds as time_gap_seconds,
  e1.event_time as cause_time,
  e2.event_time as effect_time
ORDER BY pc.confidence DESC
LIMIT 20;


// View specific pattern: BackOff events and their causes
MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(effect:Episodic {reason: 'BackOff'})
WHERE cause.client_id = 'ab-01'
RETURN cause.reason, effect.reason, pc.confidence, pc.domain_score
ORDER BY pc.confidence DESC
LIMIT 10;


// ============================================================================
// Step 4: Test your RCA query
// ============================================================================

// This should now return confidence scores instead of nulls
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 60})
  AND e.client_id = 'ab-01'
  AND e.severity = 'WARNING'

OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource)
OPTIONAL MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(e)

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
    time_gap: pc.time_gap_seconds
  }) as root_causes
ORDER BY e.event_time DESC
LIMIT 10;


// ============================================================================
// Optional: Delete all POTENTIAL_CAUSE relationships (if you need to start over)
// ============================================================================

// CAUTION: This deletes ALL causal relationships!
// Uncomment to run:
// MATCH ()-[pc:POTENTIAL_CAUSE]->()
// DELETE pc
// RETURN count(*) as deleted_relationships;
