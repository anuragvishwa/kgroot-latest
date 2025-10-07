#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "  RCA System Validation"
echo "========================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

function check() {
    local name="$1"
    local query="$2"

    echo -n "Checking: $name... "

    # Run cypher query via kubectl exec into Neo4j
    result=$(kubectl exec -n observability neo4j-0 -- \
        cypher-shell -u neo4j -p anuragvishwa "$query" 2>/dev/null || echo "ERROR")

    if echo "$result" | grep -q "ERROR"; then
        echo -e "${RED}FAIL${NC}"
        echo "  Query: $query"
        echo "  Error: $result"
        ((FAIL++))
        return 1
    elif [ -z "$result" ] || echo "$result" | grep -q "0 rows"; then
        echo -e "${YELLOW}WARN (no data)${NC}"
        ((WARN++))
        return 0
    else
        echo -e "${GREEN}PASS${NC}"
        ((PASS++))
        return 0
    fi
}

echo "1. Schema Validation"
echo "--------------------"

check "Resource nodes exist" \
    "MATCH (r:Resource) RETURN count(r) AS cnt LIMIT 1;"

check "Episodic nodes exist" \
    "MATCH (e:Episodic) RETURN count(e) AS cnt LIMIT 1;"

check "ABOUT relationships exist" \
    "MATCH ()-[r:ABOUT]->() RETURN count(r) AS cnt LIMIT 1;"

check "POTENTIAL_CAUSE relationships exist" \
    "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r) AS cnt LIMIT 1;"

echo ""
echo "2. Data Quality"
echo "---------------"

check "Resources have kind" \
    "MATCH (r:Resource) WHERE r.kind IS NOT NULL RETURN count(r) LIMIT 1;"

check "Episodic events have timestamps" \
    "MATCH (e:Episodic) WHERE e.event_time IS NOT NULL RETURN count(e) LIMIT 1;"

check "Pods have namespace" \
    "MATCH (p:Resource:Pod) WHERE p.ns IS NOT NULL RETURN count(p) LIMIT 1;"

echo ""
echo "3. Topology Validation"
echo "----------------------"

check "SELECTS relationships (Service→Pod)" \
    "MATCH (:Resource:Service)-[r:SELECTS]->(:Resource:Pod) RETURN count(r) LIMIT 1;"

check "RUNS_ON relationships (Pod→Node)" \
    "MATCH (:Resource:Pod)-[r:RUNS_ON]->(:Resource:Node) RETURN count(r) LIMIT 1;"

check "CONTROLS relationships (Deployment→Pod)" \
    "MATCH (:Resource:Deployment)-[r:CONTROLS]->() RETURN count(r) LIMIT 1;"

echo ""
echo "4. RCA Functionality"
echo "--------------------"

check "Events linked to resources" \
    "MATCH (e:Episodic)-[:ABOUT]->(r:Resource) RETURN count(*) LIMIT 1;"

check "Causal links created" \
    "MATCH ()-[pc:POTENTIAL_CAUSE]->() WHERE pc.hops IS NOT NULL RETURN count(pc) LIMIT 1;"

check "Recent events (last hour)" \
    "MATCH (e:Episodic) WHERE e.event_time > datetime() - duration({hours: 1}) RETURN count(e) LIMIT 1;"

echo ""
echo "5. Test Scenario Validation (if tests deployed)"
echo "------------------------------------------------"

check "ImagePullBackOff events captured" \
    "MATCH (e:Episodic) WHERE e.reason CONTAINS 'Pull' OR e.reason CONTAINS 'BackOff' RETURN count(e) LIMIT 1;"

check "CrashLoop events captured" \
    "MATCH (e:Episodic) WHERE e.reason CONTAINS 'BackOff' OR e.reason CONTAINS 'CrashLoop' RETURN count(e) LIMIT 1;"

check "Log-based events captured" \
    "MATCH (e:Episodic {etype: 'k8s.log'}) WHERE e.severity IN ['ERROR', 'FATAL'] RETURN count(e) LIMIT 1;"

echo ""
echo "6. Graph Statistics"
echo "-------------------"

echo -n "Total Resource nodes: "
kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH (r:Resource) RETURN count(r) AS cnt;" 2>/dev/null | tail -1 || echo "N/A"

echo -n "Total Episodic nodes: "
kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH (e:Episodic) RETURN count(e) AS cnt;" 2>/dev/null | tail -1 || echo "N/A"

echo -n "Total POTENTIAL_CAUSE links: "
kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r) AS cnt;" 2>/dev/null | tail -1 || echo "N/A"

echo -n "Pod count: "
kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH (p:Resource:Pod) RETURN count(p) AS cnt;" 2>/dev/null | tail -1 || echo "N/A"

echo -n "Service count: "
kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH (s:Resource:Service) RETURN count(s) AS cnt;" 2>/dev/null | tail -1 || echo "N/A"

echo ""
echo "========================================"
echo "  Results: ${GREEN}${PASS} passed${NC}, ${YELLOW}${WARN} warnings${NC}, ${RED}${FAIL} failed${NC}"
echo "========================================"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "❌ Some checks failed. Review logs:"
    echo "  kubectl logs -n observability -l app=kg-builder --tail=100"
    echo "  kubectl logs -n observability -l app=vector --tail=100"
    echo "  kubectl logs -n observability -l app=state-watcher --tail=100"
    exit 1
elif [ $WARN -gt 3 ]; then
    echo ""
    echo "⚠️  Several warnings. System may need more time to collect data."
    echo "   Wait 5-10 minutes and run again, or deploy test scenarios:"
    echo "   kubectl apply -f test/01-imagepull-failure.yaml"
    exit 0
else
    echo ""
    echo "✅ All checks passed! RCA system is working correctly."
    exit 0
fi
