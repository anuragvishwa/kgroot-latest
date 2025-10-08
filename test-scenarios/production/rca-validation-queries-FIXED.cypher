// ============================================
// RCA Validation Queries - FIXED VERSION
// Correct variable naming: CAUSE -> SYMPTOM
// ============================================

// IMPORTANT: Relationship Semantics
// (cause)-[:POTENTIAL_CAUSE]->(symptom)
// The arrow points FROM cause TO symptom/effect

// 1. RCA Coverage Overview
MATCH (cause)-[r:POTENTIAL_CAUSE]->(symptom)
WITH count(r) as total_rca
MATCH (e:Episodic)
WITH total_rca, count(e) as total_events
RETURN
  total_events,
  total_rca,
  round(total_rca * 100.0 / total_events, 2) as rca_per_event_ratio,
  CASE
    WHEN total_rca > 20000 THEN '✅ Excellent (20k+ links)'
    WHEN total_rca > 10000 THEN '✅ Good (10k+ links)'
    WHEN total_rca > 1000 THEN '⚠️  Adequate (1k+ links)'
    ELSE '❌ Insufficient (< 1k links)'
  END as status;

// 2. Sample RCA Chains (CORRECT ORDER)
MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(symptom:Episodic)
WITH
  cause, symptom, r,
  duration.inSeconds(
    datetime(cause.event_time),
    datetime(symptom.event_time)
  ).seconds as time_gap
WHERE time_gap > 0  // Filter out incorrect links (cause should be before symptom)
RETURN
  cause.event_time as cause_time,
  cause.reason as cause_event,
  cause.severity as cause_severity,
  symptom.event_time as symptom_time,
  symptom.reason as symptom_event,
  symptom.severity as symptom_severity,
  time_gap as seconds_between_cause_and_symptom,
  r.confidence as confidence_score
ORDER BY symptom_time DESC
LIMIT 20;

// 3. Verify Time Ordering (Data Quality Check)
MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(symptom:Episodic)
WITH
  duration.inSeconds(
    datetime(cause.event_time),
    datetime(symptom.event_time)
  ).seconds as time_gap
WITH
  CASE
    WHEN time_gap > 0 THEN 'Correct (cause before symptom)'
    WHEN time_gap = 0 THEN 'Same time (acceptable)'
    ELSE 'Incorrect (cause after symptom!)'
  END as ordering,
  count(*) as count
RETURN
  ordering,
  count,
  round(count * 100.0 / sum(count) OVER(), 2) as percentage
ORDER BY count DESC;

// Expected: >95% "Correct (cause before symptom)"

// 4. Most Common Root Causes
MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(symptom:Episodic)
RETURN
  cause.reason as root_cause_type,
  cause.severity as severity,
  count(DISTINCT symptom) as symptoms_caused,
  collect(DISTINCT symptom.reason)[0..5] as example_symptoms
ORDER BY symptoms_caused DESC
LIMIT 15;

// 5. RCA Chain Depth (Multi-hop Analysis)
MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*2..5]->(leaf:Episodic)
RETURN
  length(path) as chain_depth,
  count(*) as chain_count,
  collect(DISTINCT root.reason)[0..3] as root_causes,
  collect(DISTINCT leaf.reason)[0..3] as final_symptoms
ORDER BY chain_depth;

// 6. Prometheus Alerts as Root Causes
MATCH (alert:Episodic {etype: 'prom.alert'})-[:POTENTIAL_CAUSE]->(symptom:Episodic)
RETURN
  alert.reason as alert_name,
  alert.severity as alert_severity,
  count(DISTINCT symptom) as k8s_symptoms_caused,
  collect(DISTINCT symptom.reason)[0..5] as symptom_types
ORDER BY k8s_symptoms_caused DESC
LIMIT 10;

// 7. Cross-Pod RCA (One Pod's Issues Causing Another's)
MATCH (cause:Episodic)-[:ABOUT]->(pod1:Pod),
      (cause)-[:POTENTIAL_CAUSE]->(symptom:Episodic)-[:ABOUT]->(pod2:Pod)
WHERE pod1.name <> pod2.name
  AND pod1.ns = 'kg-testing' AND pod2.ns = 'kg-testing'
RETURN
  pod1.name as problem_pod,
  cause.reason as problem_type,
  pod2.name as affected_pod,
  symptom.reason as symptom_type,
  count(*) as occurrences
ORDER BY occurrences DESC
LIMIT 10;

// 8. RCA Time Distribution
MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(symptom:Episodic)
WITH
  duration.inMinutes(
    datetime(cause.event_time),
    datetime(symptom.event_time)
  ).minutes as minutes_gap
WHERE minutes_gap >= 0  // Only valid RCA (cause before symptom)
WITH
  CASE
    WHEN minutes_gap < 1 THEN '< 1 min'
    WHEN minutes_gap < 5 THEN '1-5 min'
    WHEN minutes_gap < 15 THEN '5-15 min'
    WHEN minutes_gap < 60 THEN '15-60 min'
    ELSE '> 1 hour'
  END as time_bucket,
  minutes_gap
RETURN
  time_bucket,
  count(*) as rca_count,
  round(avg(minutes_gap), 2) as avg_minutes,
  min(minutes_gap) as min_minutes,
  max(minutes_gap) as max_minutes,
  round(count(*) * 100.0 / sum(count(*)) OVER(), 2) as percentage
ORDER BY
  CASE time_bucket
    WHEN '< 1 min' THEN 1
    WHEN '1-5 min' THEN 2
    WHEN '5-15 min' THEN 3
    WHEN '15-60 min' THEN 4
    ELSE 5
  END;

// Expected: Most RCA links within 5-15 min window

// 9. RCA by Severity Pattern
MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(symptom:Episodic)
RETURN
  cause.severity as cause_severity,
  symptom.severity as symptom_severity,
  count(*) as occurrence_count,
  round(count(*) * 100.0 / sum(count(*)) OVER(), 2) as percentage
ORDER BY occurrence_count DESC
LIMIT 10;

// Common patterns:
// ERROR -> ERROR
// WARNING -> ERROR
// WARNING -> FATAL
// ERROR -> FATAL

// 10. Confidence Score Distribution
MATCH ()-[r:POTENTIAL_CAUSE]->()
WHERE r.confidence IS NOT NULL
WITH r.confidence as confidence
WITH
  CASE
    WHEN confidence >= 0.8 THEN 'High (≥0.8)'
    WHEN confidence >= 0.6 THEN 'Medium (0.6-0.8)'
    WHEN confidence >= 0.4 THEN 'Low (0.4-0.6)'
    ELSE 'Very Low (<0.4)'
  END as confidence_bucket
RETURN
  confidence_bucket,
  count(*) as count,
  round(count(*) * 100.0 / sum(count(*)) OVER(), 2) as percentage
ORDER BY
  CASE confidence_bucket
    WHEN 'High (≥0.8)' THEN 1
    WHEN 'Medium (0.6-0.8)' THEN 2
    WHEN 'Low (0.4-0.6)' THEN 3
    ELSE 4
  END;

// 11. Example RCA Chains (for manual review)
MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*2..3]->(leaf:Episodic)
WHERE root.severity IN ['WARNING', 'ERROR']
  AND leaf.severity IN ['ERROR', 'FATAL']
WITH
  [node IN nodes(path) | node.reason + ' (' + node.event_time + ')'] as chain,
  length(path) as depth,
  leaf.event_time as final_time
RETURN
  chain as causality_chain,
  depth
ORDER BY final_time DESC
LIMIT 10;

// 12. RCA for kg-testing Namespace
MATCH (cause:Episodic)-[:ABOUT]->(r1:Resource {ns: 'kg-testing'}),
      (cause)-[:POTENTIAL_CAUSE]->(symptom:Episodic)-[:ABOUT]->(r2:Resource {ns: 'kg-testing'})
RETURN
  r1.name as cause_resource,
  cause.reason as cause_type,
  r2.name as symptom_resource,
  symptom.reason as symptom_type,
  count(*) as occurrences
ORDER BY occurrences DESC
LIMIT 15;

// 13. Orphaned Events (No causes identified)
MATCH (symptom:Episodic)
WHERE NOT exists((symptom)<-[:POTENTIAL_CAUSE]-())
  AND symptom.severity IN ['ERROR', 'FATAL']
WITH count(symptom) as orphaned
MATCH (all_errors:Episodic)
WHERE all_errors.severity IN ['ERROR', 'FATAL']
WITH orphaned, count(all_errors) as total_errors
RETURN
  orphaned as errors_without_causes,
  total_errors,
  orphaned - total_errors as errors_with_causes,
  round((total_errors - orphaned) * 100.0 / total_errors, 2) as rca_coverage_percent,
  CASE
    WHEN orphaned * 100.0 / total_errors < 30 THEN '✅ Excellent (<30% orphaned)'
    WHEN orphaned * 100.0 / total_errors < 50 THEN '⚠️  Good (<50% orphaned)'
    WHEN orphaned * 100.0 / total_errors < 70 THEN '⚠️  Fair (<70% orphaned)'
    ELSE '❌ Poor (>70% orphaned)'
  END as quality_rating;

// 14. Top Incident Patterns (Most Common Cause->Symptom Pairs)
MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(symptom:Episodic)
RETURN
  cause.reason as cause,
  symptom.reason as symptom,
  count(*) as frequency,
  collect(DISTINCT cause.severity)[0] as cause_severity,
  collect(DISTINCT symptom.severity)[0] as symptom_severity
ORDER BY frequency DESC
LIMIT 20;

// 15. Production Readiness Summary
WITH
  // Count total RCA links
  size([(c)-[r:POTENTIAL_CAUSE]->(s) | r]) as rca_count,
  // Count events
  size([(e:Episodic) | e]) as event_count,
  // Count error events
  size([(e:Episodic) WHERE e.severity IN ['ERROR', 'FATAL'] | e]) as error_count,
  // Count distinct event types
  size([(e:Episodic) | e.reason]) as event_type_count,
  // Count resources
  size([(r:Resource) | r]) as resource_count
RETURN
  rca_count as total_rca_links,
  event_count as total_events,
  error_count as error_events,
  event_type_count as event_types_captured,
  resource_count as resources_tracked,
  round(rca_count * 100.0 / error_count, 2) as rca_per_error_ratio,
  CASE
    WHEN rca_count > 20000 AND event_type_count > 30 AND rca_count * 100.0 / error_count > 500
      THEN '✅ PRODUCTION READY - Excellent Coverage'
    WHEN rca_count > 10000 AND event_type_count > 20
      THEN '✅ PRODUCTION READY - Good Coverage'
    WHEN rca_count > 1000 AND event_type_count > 10
      THEN '⚠️  STAGING READY - Adequate Coverage'
    ELSE '❌ NOT READY - Insufficient Coverage'
  END as readiness_status;
