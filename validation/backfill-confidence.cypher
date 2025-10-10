// ═══════════════════════════════════════════════════════════════════════════
// BACKFILL CONFIDENCE SCORES FOR EXISTING RCA LINKS
// Purpose: Update all NULL confidence RCA links with calculated scores
// ═══════════════════════════════════════════════════════════════════════════

// Step 1: Count links needing backfill
MATCH (c:Episodic)-[pc:POTENTIAL_CAUSE]->(e:Episodic)
WHERE pc.confidence IS NULL
RETURN count(pc) as links_needing_backfill;

// Step 2: Backfill confidence scores (process in batches)
// WARNING: This may take several minutes for 100K+ links
// Recommendation: Run in batches of 10,000

CALL apoc.periodic.iterate(
  "MATCH (c:Episodic)-[pc:POTENTIAL_CAUSE]->(e:Episodic)
   WHERE pc.confidence IS NULL
   RETURN c, pc, e",

  "// Get topology path for distance score
   MATCH (c)-[:ABOUT]->(u:Resource)
   MATCH (e)-[:ABOUT]->(r:Resource)
   OPTIONAL MATCH p = shortestPath((u)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r))

   WITH c, pc, e, p, u, r
   WHERE p IS NOT NULL

   // Calculate temporal score
   WITH c, pc, e, p,
        1.0 - (duration.between(c.event_time, e.event_time).milliseconds / (60000.0 * 15)) AS temporal_score,
        1.0 / (length(p) + 1.0) AS distance_score

   // Calculate domain score (same heuristics as LinkRCAWithScore)
   WITH c, pc, e, temporal_score, distance_score,
        CASE
          WHEN c.reason CONTAINS 'OOMKilled' AND e.reason CONTAINS 'CrashLoop' THEN 0.95
          WHEN c.reason CONTAINS 'ImagePull' AND e.reason CONTAINS 'FailedScheduling' THEN 0.90
          WHEN c.reason CONTAINS 'NodeNotReady' AND e.reason CONTAINS 'Evicted' THEN 0.90
          WHEN c.message =~ '(?i).*(connection refused|timeout).*' AND e.severity = 'ERROR' THEN 0.70
          WHEN c.message =~ '(?i).*(database|deadlock).*' AND e.message =~ '(?i).*(api|service).*' THEN 0.65
          WHEN c.severity = 'ERROR' AND e.severity = 'ERROR' THEN 0.50
          ELSE 0.40
        END AS domain_score

   // Calculate final confidence
   WITH pc, temporal_score, distance_score, domain_score,
        (temporal_score * 0.3 + distance_score * 0.3 + domain_score * 0.4) AS confidence

   SET pc.confidence = confidence,
       pc.temporal_score = temporal_score,
       pc.distance_score = distance_score,
       pc.domain_score = domain_score,
       pc.backfilled = true,
       pc.updated_at = datetime()",

  {batchSize: 10000, parallel: false, retries: 3}
);

// Step 3: Verify backfill completion
MATCH ()-[r:POTENTIAL_CAUSE]->()
WITH
  count(CASE WHEN r.confidence IS NULL THEN 1 END) as null_count,
  count(CASE WHEN r.confidence IS NOT NULL THEN 1 END) as with_confidence,
  count(*) as total
RETURN
  total as `Total Links`,
  with_confidence as `With Confidence`,
  null_count as `Still NULL`,
  round(with_confidence * 100.0 / total, 2) as `Coverage %`;

// Step 4: Show confidence distribution
MATCH ()-[r:POTENTIAL_CAUSE]->()
WHERE r.confidence IS NOT NULL
WITH
  CASE
    WHEN r.confidence >= 0.9 THEN '0.90-1.00 (High)'
    WHEN r.confidence >= 0.7 THEN '0.70-0.89 (Medium-High)'
    WHEN r.confidence >= 0.5 THEN '0.50-0.69 (Medium)'
    WHEN r.confidence >= 0.3 THEN '0.30-0.49 (Low-Medium)'
    ELSE '0.00-0.29 (Low)'
  END as confidence_range
RETURN
  confidence_range as `Confidence Range`,
  count(*) as `Count`,
  round(count(*) * 100.0 / sum(count(*)), 2) as `%`
ORDER BY confidence_range;

// Expected: After backfill, 100% coverage with most links in 0.50-0.89 range
