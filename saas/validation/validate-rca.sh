#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════
# KG RCA QUALITY VALIDATION
# Validates RCA link quality for a specific client
# ═══════════════════════════════════════════════════════════════════════════

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
CLIENT_ID="${CLIENT_ID:-}"
SERVER_NAMESPACE="${SERVER_NAMESPACE:-kg-rca-server}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-changeme}"

if [ -z "$CLIENT_ID" ]; then
  echo "Usage: $0 --client-id <client-id>"
  echo "   or: CLIENT_ID=<client-id> $0"
  exit 1
fi

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  KG RCA QUALITY VALIDATION"
echo "  Client ID: $CLIENT_ID"
echo "  $(date)"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 1. CONNECT TO NEO4J
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[1/5] Connecting to Neo4j...${NC}"

NEO4J_POD=$(kubectl get pods -n "$SERVER_NAMESPACE" -l app=neo4j --field-selector=status.phase=Running -o name 2>/dev/null | head -1)
if [ -z "$NEO4J_POD" ]; then
  echo -e "${RED}✗ Neo4j pod not found${NC}"
  exit 1
fi

# Test connection
if kubectl exec -n "$SERVER_NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
  echo -e "${GREEN}✓ Connected to Neo4j${NC}"
else
  echo -e "${RED}✗ Cannot connect to Neo4j${NC}"
  exit 1
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 2. CHECK DATA INGESTION
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[2/5] Checking data ingestion for client...${NC}"

# Count events for this client
EVENT_COUNT=$(kubectl exec -n "$SERVER_NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain \
  "MATCH (e:Episodic) WHERE e.client_id = '$CLIENT_ID' RETURN count(e) as count" 2>/dev/null | tail -1 || echo "0")

echo "  Events: $EVENT_COUNT"

if [ "$EVENT_COUNT" -eq 0 ]; then
  echo -e "${YELLOW}⚠ No events found for this client${NC}"
  echo "  Check if client agents are running and connected"
else
  echo -e "${GREEN}✓ Events are being ingested${NC}"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 3. CHECK RCA LINKS
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[3/5] Checking RCA links...${NC}"

# Count RCA links for this client
RCA_COUNT=$(kubectl exec -n "$SERVER_NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain \
  "MATCH (c:Episodic)-[r:POTENTIAL_CAUSE]->(s:Episodic)
   WHERE c.client_id = '$CLIENT_ID' AND s.client_id = '$CLIENT_ID'
   RETURN count(r) as count" 2>/dev/null | tail -1 || echo "0")

echo "  RCA Links: $RCA_COUNT"

if [ "$RCA_COUNT" -eq 0 ]; then
  echo -e "${YELLOW}⚠ No RCA links found${NC}"
  if [ "$EVENT_COUNT" -gt 0 ]; then
    echo "  Events exist but no RCA links - check Graph Builder"
  fi
else
  echo -e "${GREEN}✓ RCA links are being created${NC}"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 4. CHECK RCA QUALITY
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[4/5] Analyzing RCA quality...${NC}"

if [ "$RCA_COUNT" -gt 0 ]; then
  # Confidence coverage
  WITH_CONFIDENCE=$(kubectl exec -n "$SERVER_NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain \
    "MATCH (c:Episodic)-[r:POTENTIAL_CAUSE]->(s:Episodic)
     WHERE c.client_id = '$CLIENT_ID' AND s.client_id = '$CLIENT_ID'
       AND r.confidence IS NOT NULL
     RETURN count(r) as count" 2>/dev/null | tail -1 || echo "0")

  CONFIDENCE_PCT=$(awk "BEGIN {printf \"%.1f\", ($WITH_CONFIDENCE * 100.0 / $RCA_COUNT)}")
  echo "  Confidence Coverage: $CONFIDENCE_PCT% ($WITH_CONFIDENCE/$RCA_COUNT)"

  if (( $(echo "$CONFIDENCE_PCT >= 95.0" | bc -l) )); then
    echo -e "  ${GREEN}✓ Excellent confidence coverage${NC}"
  elif (( $(echo "$CONFIDENCE_PCT >= 80.0" | bc -l) )); then
    echo -e "  ${YELLOW}⚠ Good confidence coverage${NC}"
  else
    echo -e "  ${RED}✗ Low confidence coverage${NC}"
  fi

  # Average confidence
  AVG_CONFIDENCE=$(kubectl exec -n "$SERVER_NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain \
    "MATCH (c:Episodic)-[r:POTENTIAL_CAUSE]->(s:Episodic)
     WHERE c.client_id = '$CLIENT_ID' AND s.client_id = '$CLIENT_ID'
       AND r.confidence IS NOT NULL
     RETURN round(avg(r.confidence), 3) as avg_conf" 2>/dev/null | tail -1 || echo "0")

  echo "  Average Confidence: $AVG_CONFIDENCE"

  # Temporal correctness
  INVALID=$(kubectl exec -n "$SERVER_NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain \
    "MATCH (c:Episodic)-[r:POTENTIAL_CAUSE]->(s:Episodic)
     WHERE c.client_id = '$CLIENT_ID' AND s.client_id = '$CLIENT_ID'
     WITH duration.between(datetime(c.event_time), datetime(s.event_time)).milliseconds as gap
     WHERE gap < 0
     RETURN count(*) as invalid" 2>/dev/null | tail -1 || echo "0")

  if [ "$INVALID" -eq 0 ]; then
    echo -e "  ${GREEN}✓ All RCA links temporally correct${NC}"
  else
    echo -e "  ${RED}✗ Found $INVALID invalid temporal links${NC}"
  fi
else
  echo "  Skipping quality checks (no RCA links)"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 5. CHECK RECENT ACTIVITY
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[5/5] Checking recent activity (last 1 hour)...${NC}"

RECENT_EVENTS=$(kubectl exec -n "$SERVER_NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain \
  "MATCH (e:Episodic)
   WHERE e.client_id = '$CLIENT_ID'
     AND datetime(e.event_time) > datetime() - duration('PT1H')
   RETURN count(e) as count" 2>/dev/null | tail -1 || echo "0")

RECENT_RCA=$(kubectl exec -n "$SERVER_NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain \
  "MATCH (c:Episodic)-[r:POTENTIAL_CAUSE]->(s:Episodic)
   WHERE c.client_id = '$CLIENT_ID' AND s.client_id = '$CLIENT_ID'
     AND datetime(r.created_at) > datetime() - duration('PT1H')
   RETURN count(r) as count" 2>/dev/null | tail -1 || echo "0")

echo "  Recent Events (1h): $RECENT_EVENTS"
echo "  Recent RCA Links (1h): $RECENT_RCA"

if [ "$RECENT_EVENTS" -gt 0 ]; then
  echo -e "${GREEN}✓ Active data ingestion${NC}"
else
  echo -e "${YELLOW}⚠ No recent events${NC}"
fi

if [ "$RECENT_RCA" -gt 0 ]; then
  echo -e "${GREEN}✓ Active RCA generation${NC}"
else
  echo -e "${YELLOW}⚠ No recent RCA links${NC}"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# SUMMARY
# ───────────────────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  VALIDATION SUMMARY"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

echo "Client: $CLIENT_ID"
echo "Total Events: $EVENT_COUNT"
echo "Total RCA Links: $RCA_COUNT"

if [ "$RCA_COUNT" -gt 0 ]; then
  echo "Confidence Coverage: $CONFIDENCE_PCT%"
  echo "Average Confidence: $AVG_CONFIDENCE"
fi

echo ""

# Determine overall status
if [ "$EVENT_COUNT" -gt 0 ] && [ "$RCA_COUNT" -gt 0 ] && (( $(echo "$CONFIDENCE_PCT >= 80.0" | bc -l) )); then
  echo -e "${GREEN}✅ RCA system operational and healthy${NC}"
  exit 0
elif [ "$EVENT_COUNT" -gt 0 ] && [ "$RCA_COUNT" -eq 0 ]; then
  echo -e "${YELLOW}⚠️  Events ingested but no RCA links${NC}"
  echo "Wait 15 minutes or check Graph Builder logs"
  exit 1
elif [ "$EVENT_COUNT" -eq 0 ]; then
  echo -e "${RED}❌ No data ingestion detected${NC}"
  echo "Check client agents and connectivity"
  exit 1
else
  echo -e "${YELLOW}⚠️  System needs attention${NC}"
  exit 1
fi
