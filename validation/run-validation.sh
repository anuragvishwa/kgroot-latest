#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════
# RCA VALIDATION SCRIPT
# Purpose: Run all validation checks (A@K, MAR, Confidence, SLA)
# ═══════════════════════════════════════════════════════════════════════════

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  RCA VALIDATION SUITE"
echo "  $(date)"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# Configuration
NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASS="${NEO4J_PASS:-anuragvishwa}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
KG_API_URL="${KG_API_URL:-http://localhost:8080}"

# ───────────────────────────────────────────────────────────────────────────
# 1. CHECK NEO4J CONNECTIVITY
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[1/5] Checking Neo4j connectivity...${NC}"
if cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" \
   "RETURN 1 as connected" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ Neo4j connected${NC}"
else
  echo -e "${RED}✗ Neo4j connection failed${NC}"
  echo "  Make sure Neo4j is running at $NEO4J_URI"
  exit 1
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 2. RUN NEO4J QUALITY QUERIES
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[2/5] Running Neo4j quality checks...${NC}"

# Query 1: Confidence Coverage
echo -e "${YELLOW}Query 1: Confidence Score Coverage${NC}"
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" \
  "MATCH ()-[r:POTENTIAL_CAUSE]->()
   WITH
     count(CASE WHEN r.confidence IS NULL THEN 1 END) as null_confidence,
     count(CASE WHEN r.confidence IS NOT NULL THEN 1 END) as with_confidence,
     count(*) as total
   RETURN
     total as \`Total RCA Links\`,
     with_confidence as \`Links with Confidence\`,
     null_confidence as \`Links with NULL\`,
     round(with_confidence * 100.0 / total, 2) as \`% with Confidence\`"
echo ""

# Query 4: Temporal Correctness (using milliseconds, allowing simultaneous events)
echo -e "${YELLOW}Query 4: Temporal Correctness Validation${NC}"
INVALID_COUNT=$(cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" --format plain \
  "MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(symptom:Episodic)
   WITH duration.between(datetime(cause.event_time), datetime(symptom.event_time)).milliseconds as time_gap_ms
   WHERE time_gap_ms < 0
   RETURN count(*) as invalid_links" | tail -1)

if [ "$INVALID_COUNT" = "0" ]; then
  echo -e "${GREEN}✓ PASS: All RCA links are temporally correct (cause before or simultaneous with symptom)${NC}"
else
  echo -e "${RED}✗ FAIL: Found $INVALID_COUNT invalid RCA links (cause after symptom)${NC}"
fi
echo ""

# Query 7: Known Pattern Confidence (FIXED for actual data)
echo -e "${YELLOW}Query 7: Known Pattern Confidence${NC}"
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" \
  "MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(symptom:Episodic)
   WHERE r.confidence IS NOT NULL
     AND (
       (cause.reason = 'KubePodCrashLooping' AND symptom.reason = 'KubePodNotReady') OR
       (cause.reason = 'NodeClockNotSynchronising' AND symptom.reason = 'PrometheusMissingRuleEvaluations') OR
       (cause.reason = 'KubePodNotReady' AND symptom.reason = 'KubePodCrashLooping')
     )
   WITH
     cause.reason + ' → ' + symptom.reason as pattern,
     avg(r.confidence) as avg_confidence,
     count(*) as occurrences
   RETURN pattern as \`Pattern\`, occurrences as \`Count\`, round(avg_confidence, 3) as \`Avg Confidence\`"
echo ""

# Query 10: Recent Quality
echo -e "${YELLOW}Query 10: Recent RCA Quality (Last 1 Hour)${NC}"
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" \
  "MATCH ()-[r:POTENTIAL_CAUSE]->()
   WHERE datetime(r.created_at) > datetime() - duration('PT1H')
   WITH
     count(*) as total_links,
     count(CASE WHEN r.confidence IS NOT NULL THEN 1 END) as links_with_conf,
     avg(r.confidence) as avg_conf
   RETURN
     total_links as \`Links (1h)\`,
     links_with_conf as \`Scored\`,
     round(links_with_conf * 100.0 / total_links, 2) as \`% Scored\`,
     round(avg_conf, 3) as \`Avg Confidence\`"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 3. CHECK PROMETHEUS METRICS
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[3/5] Checking Prometheus metrics...${NC}"

check_metric() {
  local metric=$1
  local description=$2

  if curl -s "$PROMETHEUS_URL/api/v1/query?query=$metric" > /dev/null 2>&1; then
    VALUE=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=$metric" | \
            jq -r '.data.result[0].value[1] // "N/A"' 2>/dev/null || echo "N/A")
    echo "  $description: $VALUE"
  else
    echo "  $description: ${RED}Not available${NC}"
  fi
}

# Check key RCA metrics
check_metric "kg_rca_links_created_total" "Total RCA Links Created"
check_metric "kg_rca_null_confidence_total" "NULL Confidence (Fallback Used)"
check_metric "kg_rca_accuracy_at_k{k=\"3\"}" "A@3 Accuracy"
check_metric "kg_rca_mean_average_rank" "Mean Average Rank (MAR)"
echo ""

# Check SLA metrics
echo -e "${YELLOW}SLA Metrics:${NC}"
check_metric "kg_sla_violations_total{operation=\"rca_compute\",severity=\"critical\"}" "RCA Compute SLA Violations (Critical)"
check_metric "kg_sla_violations_total{operation=\"message_processing\",severity=\"warning\"}" "Message Processing SLA Warnings"
check_metric "rate(kg_rca_compute_time_seconds_sum[5m])" "RCA Compute Time (5m rate)"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 4. RUN A@K AND MAR CALCULATION
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[4/5] Computing A@K and MAR metrics...${NC}"

# Check if validation API exists
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$KG_API_URL/api/v1/rca/validate" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
  echo "Using validation API..."
  curl -s "$KG_API_URL/api/v1/rca/validate" | jq '.'
else
  echo -e "${YELLOW}Note: Validation API not available (HTTP $HTTP_CODE). Use cypher queries for manual A@K calculation.${NC}"
  echo "See validation/rca-quality-queries.cypher Query #6"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 5. SUMMARY AND RECOMMENDATIONS
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[5/5] Generating summary...${NC}"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  VALIDATION SUMMARY"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# Get key stats for summary
TOTAL_LINKS=$(cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" --format plain \
  "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(*) as total" | tail -1)

SCORED_PERCENT=$(cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASS" --format plain \
  "MATCH ()-[r:POTENTIAL_CAUSE]->()
   WITH count(CASE WHEN r.confidence IS NOT NULL THEN 1 END) * 100.0 / count(*) as pct
   RETURN round(pct, 2)" | tail -1)

echo "📊 RCA Statistics:"
echo "   Total RCA Links: $TOTAL_LINKS"
echo "   Confidence Coverage: $SCORED_PERCENT%"
echo ""

# Pass/Fail criteria
echo "✅ Pass Criteria:"
echo "   1. Confidence Coverage > 95%: $([ "${SCORED_PERCENT%.*}" -ge 95 ] && echo -e "${GREEN}PASS${NC}" || echo -e "${RED}FAIL${NC}")"
echo "   2. Zero Invalid Temporal Links: $([ "$INVALID_COUNT" = "0" ] && echo -e "${GREEN}PASS${NC}" || echo -e "${RED}FAIL${NC}")"
echo "   3. Known Pattern Confidence > 0.85: ${YELLOW}See Query 7 above${NC}"
echo ""

echo "📈 Monitoring URLs:"
echo "   Neo4j Browser: http://localhost:7474"
echo "   Prometheus: $PROMETHEUS_URL"
echo "   Grafana: http://localhost:3000 (if configured)"
echo ""

echo "📁 Full Query Set:"
echo "   validation/rca-quality-queries.cypher (10 detailed queries)"
echo ""

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  Validation completed at $(date)"
echo "═══════════════════════════════════════════════════════════════════════════"
