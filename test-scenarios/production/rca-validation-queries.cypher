// ============================================
// RCA Validation Queries
// Use these to validate your 19,928 POTENTIAL_CAUSE relationships
// ============================================

// 1. RCA Coverage Overview
MATCH ()-[r:POTENTIAL_CAUSE]->()
WITH count(r) as total_rca
MATCH (e:Episodic)
WITH total_rca, count(e) as total_events
RETURN
  total_events,
  total_rca,
  round(total_rca * 100.0 / total_events, 2) as rca_coverage_percent,
  CASE
    WHEN total_rca > 10000 THEN '✅ Excellent'
    WHEN total_rca > 1000 THEN '✅ Good'
    WHEN total_rca > 100 THEN '⚠️  Needs Improvement'
    ELSE '❌ Critical Issue'
  END as status;

// 2. Sample RCA Chains (Review for Accuracy)
MATCH (s:Episodic)-[r:POTENTIAL_CAUSE]->(c:Episodic)
RETURN
  s.event_time as symptom_time,
  s.reason as symptom,
  s.severity as symptom_severity,
  c.event_time as cause_time,
  c.reason as cause,
  c.severity as cause_severity,
  r.weight as confidence,
  duration.inSeconds(
    datetime(c.event_time),
    datetime(s.event_time)
  ).seconds as time_gap_seconds
ORDER BY s.event_time DESC
LIMIT 20;

// 3. Multi-Hop RCA Chains
MATCH path = (symptom:Episodic)-[:POTENTIAL_CAUSE*2..3]->(root:Episodic)
RETURN
  symptom.event_time as symptom_time,
  symptom.reason as symptom,
  [node IN nodes(path) | node.reason] as causality_chain,
  root.event_time as root_cause_time,
  root.reason as root_cause,
  length(path) as hops,
  duration.inMinutes(
    datetime(root.event_time),
    datetime(symptom.event_time)
  ).minutes as total_time_span_minutes
ORDER BY symptom_time DESC
LIMIT 10;

// 4. Most Common Root Causes
MATCH (symptom:Episodic)-[:POTENTIAL_CAUSE]->(cause:Episodic)
RETURN
  cause.reason as root_cause,
  cause.severity as severity,
  count(DISTINCT symptom) as symptoms_caused,
  collect(DISTINCT symptom.reason)[0..5] as example_symptoms
ORDER BY symptoms_caused DESC
LIMIT 15;

// 5. RCA by Severity Patterns
MATCH (s:Episodic)-[:POTENTIAL_CAUSE]->(c:Episodic)
RETURN
  s.severity as symptom_severity,
  c.severity as cause_severity,
  count(*) as occurrence_count,
  round(count(*) * 100.0 / sum(count(*)) OVER(), 2) as percentage
ORDER BY occurrence_count DESC;

// 6. RCA Time Distribution (How far back do causes go?)
MATCH (s:Episodic)-[:POTENTIAL_CAUSE]->(c:Episodic)
WITH
  duration.inMinutes(
    datetime(c.event_time),
    datetime(s.event_time)
  ).minutes as minutes_gap
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
  max(minutes_gap) as max_minutes
ORDER BY
  CASE time_bucket
    WHEN '< 1 min' THEN 1
    WHEN '1-5 min' THEN 2
    WHEN '5-15 min' THEN 3
    WHEN '15-60 min' THEN 4
    ELSE 5
  END;

// 7. Cross-Pod RCA (Events causing issues in other pods)
MATCH (s:Episodic)-[:ABOUT]->(pod1:Pod),
      (s)-[:POTENTIAL_CAUSE]->(c:Episodic)-[:ABOUT]->(pod2:Pod)
WHERE pod1.name <> pod2.name
RETURN
  pod1.name as symptom_pod,
  s.reason as symptom,
  pod2.name as cause_pod,
  c.reason as cause,
  count(*) as occurrences
ORDER BY occurrences DESC
LIMIT 10;

// 8. RCA for Specific Namespace (kg-testing)
MATCH (s:Episodic)-[:ABOUT]->(r1:Resource {ns: 'kg-testing'}),
      (s)-[:POTENTIAL_CAUSE]->(c:Episodic)-[:ABOUT]->(r2:Resource {ns: 'kg-testing'})
RETURN
  r1.name as affected_resource,
  s.reason as symptom,
  r2.name as cause_resource,
  c.reason as cause,
  count(*) as occurrences
ORDER BY occurrences DESC
LIMIT 15;

// 9. Orphaned Causes (Causes with no symptoms - may indicate cleanup needed)
MATCH (c:Episodic)
WHERE NOT exists((c)<-[:POTENTIAL_CAUSE]-())
  AND c.severity IN ['WARNING', 'ERROR', 'FATAL']
WITH count(c) as orphaned
MATCH (all:Episodic)
WHERE all.severity IN ['WARNING', 'ERROR', 'FATAL']
WITH orphaned, count(all) as total
RETURN
  orphaned,
  total,
  round(orphaned * 100.0 / total, 2) as orphaned_percentage,
  CASE
    WHEN orphaned_percentage < 30 THEN '✅ Good - Most events linked'
    WHEN orphaned_percentage < 60 THEN '⚠️  Moderate - Some events not linked'
    ELSE '❌ Poor - Many events not linked'
  END as rca_completeness;

// 10. Cascade Analysis (Symptoms that have multiple causes)
MATCH (s:Episodic)<-[:POTENTIAL_CAUSE]-(c:Episodic)
WITH s, collect(c.reason) as causes, count(c) as cause_count
WHERE cause_count > 1
RETURN
  s.event_time as symptom_time,
  s.reason as symptom,
  s.severity as severity,
  cause_count as number_of_causes,
  causes
ORDER BY cause_count DESC, symptom_time DESC
LIMIT 10;

// 11. RCA Quality Check (Are causes always before symptoms?)
MATCH (s:Episodic)-[:POTENTIAL_CAUSE]->(c:Episodic)
WHERE datetime(c.event_time) > datetime(s.event_time)
RETURN count(*) as invalid_rca_count;
// Should return 0 (causes should always precede symptoms)

// 12. RCA by Resource Type
MATCH (s:Episodic)-[:ABOUT]->(r:Resource),
      (s)-[:POTENTIAL_CAUSE]->(c:Episodic)
RETURN
  labels(r) as resource_type,
  count(DISTINCT s) as symptoms_with_rca,
  round(avg(size((s)-[:POTENTIAL_CAUSE]->())), 2) as avg_causes_per_symptom
ORDER BY symptoms_with_rca DESC;

// 13. Recent RCA Activity (Last hour)
MATCH (s:Episodic)-[:POTENTIAL_CAUSE]->(c:Episodic)
WHERE datetime(s.event_time) > datetime() - duration('PT1H')
RETURN
  count(*) as recent_rca_count,
  min(s.event_time) as earliest,
  max(s.event_time) as latest,
  count(DISTINCT c.reason) as unique_cause_types,
  count(DISTINCT s.reason) as unique_symptom_types;

// 14. RCA Confidence Distribution (if weight is used)
MATCH ()-[r:POTENTIAL_CAUSE]->()
WHERE r.weight IS NOT NULL
WITH r.weight as weight
WITH
  CASE
    WHEN weight > 0.8 THEN 'High Confidence (>0.8)'
    WHEN weight > 0.5 THEN 'Medium Confidence (0.5-0.8)'
    ELSE 'Low Confidence (<0.5)'
  END as confidence_bucket
RETURN
  confidence_bucket,
  count(*) as count
ORDER BY
  CASE confidence_bucket
    WHEN 'High Confidence (>0.8)' THEN 1
    WHEN 'Medium Confidence (0.5-0.8)' THEN 2
    ELSE 3
  END;

// 15. Production Readiness Check
MATCH ()-[r:POTENTIAL_CAUSE]->()
WITH count(r) as rca_count
MATCH (e:Episodic)
WHERE e.severity IN ['ERROR', 'FATAL']
WITH rca_count, count(e) as error_count
RETURN
  rca_count as total_rca_links,
  error_count as total_errors,
  round(rca_count * 100.0 / error_count, 2) as rca_coverage_percent,
  CASE
    WHEN rca_count > 10000 AND rca_coverage_percent > 50 THEN '✅ PRODUCTION READY'
    WHEN rca_count > 1000 AND rca_coverage_percent > 30 THEN '⚠️  STAGING READY'
    WHEN rca_count > 100 THEN '🔧 DEVELOPMENT READY'
    ELSE '❌ NOT READY - RCA needs work'
  END as readiness_status;
