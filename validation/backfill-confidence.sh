#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# BACKFILL CONFIDENCE SCORES FOR EXISTING RCA LINKS
# This script updates all existing POTENTIAL_CAUSE relationships with
# confidence scores calculated using the same algorithm as LinkRCAWithScore
# ═══════════════════════════════════════════════════════════════════════════

set -e

NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASS="${NEO4J_PASS:-password}"

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  CONFIDENCE SCORE BACKFILL"
echo "  $(date)"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# Check if cypher-shell is available
if ! command -v cypher-shell &> /dev/null; then
    echo "❌ ERROR: cypher-shell not found"
    echo "   Please install Neo4j client tools or use Neo4j Browser at http://localhost:7474"
    echo "   Then run the queries in validation/backfill-confidence.cypher manually"
    exit 1
fi

echo "[1/4] Checking links needing backfill..."
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" \
    "MATCH (c:Episodic)-[pc:POTENTIAL_CAUSE]->(e:Episodic)
     WHERE pc.confidence IS NULL
     RETURN count(pc) as links_needing_backfill;"

echo ""
echo "[2/4] Starting backfill (this may take several minutes)..."
echo "⏳ Processing in batches of 10,000..."

# Run the backfill using apoc.periodic.iterate
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" <<'EOF'
CALL apoc.periodic.iterate(
  "MATCH (c:Episodic)-[pc:POTENTIAL_CAUSE]->(e:Episodic)
   WHERE pc.confidence IS NULL
   RETURN c, pc, e",

  "MATCH (c)-[:ABOUT]->(u:Resource)
   MATCH (e)-[:ABOUT]->(r:Resource)
   OPTIONAL MATCH p = shortestPath((u)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r))

   WITH c, pc, e, p, u, r
   WHERE p IS NOT NULL

   WITH c, pc, e, p,
        1.0 - (duration.between(c.event_time, e.event_time).milliseconds / (60000.0 * 15)) AS temporal_score,
        1.0 / (length(p) + 1.0) AS distance_score

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
EOF

echo ""
echo "[3/4] Verifying backfill completion..."
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" \
    "MATCH ()-[r:POTENTIAL_CAUSE]->()
     WITH
       count(CASE WHEN r.confidence IS NULL THEN 1 END) as null_count,
       count(CASE WHEN r.confidence IS NOT NULL THEN 1 END) as with_confidence,
       count(*) as total
     RETURN
       total as \`Total Links\`,
       with_confidence as \`With Confidence\`,
       null_count as \`Still NULL\`,
       round(with_confidence * 100.0 / total, 2) as \`Coverage %\`;"

echo ""
echo "[4/4] Confidence distribution after backfill..."
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" \
    "MATCH ()-[r:POTENTIAL_CAUSE]->()
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
       confidence_range as \`Confidence Range\`,
       count(*) as \`Count\`,
       round(count(*) * 100.0 / sum(count(*)), 2) as \`%\`
     ORDER BY confidence_range;"

echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "✅ Backfill completed at $(date)"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "1. Restart kg service to use updated LinkRCAWithScore"
echo "2. Re-run validation: ./validation/run-validation.sh"
echo "3. Check Prometheus metrics at http://localhost:9090"
