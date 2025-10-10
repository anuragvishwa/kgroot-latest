#!/bin/bash

# RCA Quality Validation Script
# Tests if queries provide meaningful root cause analysis

NEO4J_USER="neo4j"
NEO4J_PASS="anuragvishwa"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}RCA Quality Validation${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Function to run query and format results
run_rca_query() {
    local query="$1"
    docker exec kgroot_latest-neo4j-1 cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" "$query" --format plain 2>&1
}

echo -e "${YELLOW}Test 1: Find Recent ERROR/FATAL Events${NC}\n"
RECENT_ERRORS=$(run_rca_query "
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE e.event_time >= datetime() - duration({hours: 24})
  AND e.severity IN ['ERROR', 'FATAL']
RETURN e.eid, e.reason, e.severity, r.name, toString(e.event_time) AS time
ORDER BY e.event_time DESC
LIMIT 5
")
echo "$RECENT_ERRORS"
echo ""

# Get first error event ID for detailed analysis
ERROR_EID=$(echo "$RECENT_ERRORS" | grep -v "^+" | grep -v "e.eid" | head -1 | awk '{print $1}' | tr -d '"')

if [ -z "$ERROR_EID" ]; then
    echo -e "${YELLOW}No recent ERROR/FATAL events found. Checking all events...${NC}\n"

    ALL_EVENTS=$(run_rca_query "
    MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
    RETURN e.eid, e.reason, e.severity, r.name, toString(e.event_time) AS time
    ORDER BY e.event_time DESC
    LIMIT 5
    ")
    echo "$ALL_EVENTS"
    ERROR_EID=$(echo "$ALL_EVENTS" | grep -v "^+" | grep -v "e.eid" | head -1 | awk '{print $1}' | tr -d '"')
fi

echo -e "\n${YELLOW}Test 2: Check POTENTIAL_CAUSE Relationships for Event: $ERROR_EID${NC}\n"

RCA_RESULT=$(run_rca_query "
MATCH (e:Episodic {eid: '$ERROR_EID'})-[:ABOUT]->(r:Resource)
OPTIONAL MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(e)
OPTIONAL MATCH (cause)-[:ABOUT]->(cause_resource:Resource)
RETURN
    e.reason AS effect_reason,
    r.name AS effect_resource,
    toString(e.event_time) AS effect_time,
    cause.reason AS cause_reason,
    cause_resource.name AS cause_resource,
    toString(cause.event_time) AS cause_time,
    pc.confidence AS confidence
ORDER BY pc.confidence DESC
LIMIT 5
")

echo "$RCA_RESULT"
echo ""

echo -e "${YELLOW}Test 3: Check POTENTIAL_CAUSE Relationships${NC}\n"
PC_COUNT=$(run_rca_query "
MATCH ()-[r:POTENTIAL_CAUSE]->()
RETURN count(r) AS potential_cause_count
")
echo "$PC_COUNT"
echo ""

echo -e "${YELLOW}Test 4: Find Causal Chains (Root → Intermediate → Effect)${NC}\n"
CAUSAL_CHAINS=$(run_rca_query "
MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..3]->(effect:Episodic)
WHERE NOT EXISTS { (:Episodic)-[:POTENTIAL_CAUSE]->(root) }
WITH path,
     [node IN nodes(path) | node.eid + ':' + node.reason] AS chain,
     length(path) AS depth,
     [rel IN relationships(path) | rel.confidence] AS confidences
RETURN chain, depth, confidences
ORDER BY depth DESC
LIMIT 5
")
echo "$CAUSAL_CHAINS"
echo ""

echo -e "${YELLOW}Test 5: Cascading Failure Detection${NC}\n"
CASCADING=$(run_rca_query "
MATCH (trigger:Episodic)-[:ABOUT]->(r:Resource)
WHERE trigger.event_time >= datetime() - duration({hours: 24})
  AND trigger.severity IN ['ERROR', 'FATAL']
MATCH (trigger)-[:POTENTIAL_CAUSE]->(cascade:Episodic)-[:ABOUT]->(affected:Resource)
WHERE cascade.event_time > trigger.event_time
  AND cascade.event_time <= trigger.event_time + duration({minutes: 15})
WITH trigger, r,
     count(DISTINCT cascade) AS cascade_count,
     collect(DISTINCT affected.name)[0..3] AS affected_resources
WHERE cascade_count >= 2
RETURN
    trigger.eid AS trigger_event,
    trigger.reason AS trigger_reason,
    r.name AS trigger_resource,
    cascade_count,
    affected_resources
ORDER BY cascade_count DESC
LIMIT 5
")
echo "$CASCADING"
echo ""

echo -e "${YELLOW}Test 6: Resource Blast Radius${NC}\n"
BLAST_RADIUS=$(run_rca_query "
MATCH (r:Resource)
WHERE EXISTS { (r)<-[:ABOUT]-(:Episodic) }
WITH r LIMIT 1

MATCH path = (r)-[:SELECTS|RUNS_ON|CONTROLS*1..2]-(affected:Resource)
OPTIONAL MATCH (affected)<-[:ABOUT]-(e:Episodic)
WHERE e.event_time >= datetime() - duration({hours: 24})
  AND e.severity IN ['ERROR', 'FATAL']
WITH DISTINCT r, affected, count(e) AS error_count, length(path) AS distance
RETURN
    r.name AS origin,
    affected.name AS affected_resource,
    affected.kind AS kind,
    distance,
    error_count,
    CASE
        WHEN error_count > 10 THEN 'critical'
        WHEN error_count > 5 THEN 'high'
        WHEN error_count > 0 THEN 'medium'
        ELSE 'low'
    END AS impact
ORDER BY distance, error_count DESC
LIMIT 10
")
echo "$BLAST_RADIUS"
echo ""

echo -e "${YELLOW}Test 7: Incident Clustering${NC}\n"
INCIDENTS=$(run_rca_query "
MATCH (inc:Incident)<-[:PART_OF]-(e:Episodic)-[:ABOUT]->(r:Resource)
WITH inc,
     count(e) AS event_count,
     collect(DISTINCT e.reason)[0..3] AS reasons,
     collect(DISTINCT r.name)[0..3] AS resources
RETURN
    inc.resource_id AS incident_id,
    toString(inc.window_start) AS start_time,
    toString(inc.window_end) AS end_time,
    event_count,
    reasons,
    resources
ORDER BY event_count DESC
LIMIT 5
")
echo "$INCIDENTS"
echo ""

echo -e "${YELLOW}Test 8: System Health Dashboard${NC}\n"
HEALTH=$(run_rca_query "
MATCH (r:Resource)
WITH count(r) AS total_resources,
     count(DISTINCT r.kind) AS resource_types,
     count(DISTINCT r.ns) AS namespaces

MATCH (e:Episodic)
WHERE e.event_time >= datetime() - duration({hours: 24})
WITH total_resources, resource_types, namespaces,
     count(e) AS total_events,
     sum(CASE WHEN e.severity = 'ERROR' THEN 1 ELSE 0 END) AS errors,
     sum(CASE WHEN e.severity = 'FATAL' THEN 1 ELSE 0 END) AS fatal

RETURN
    total_resources,
    resource_types,
    namespaces,
    total_events AS events_24h,
    errors AS errors_24h,
    fatal AS fatal_24h,
    round(toFloat(errors + fatal) / total_events * 100) / 100.0 AS error_rate,
    round((1.0 - toFloat(errors + fatal) / total_events) * 100) / 100.0 AS health_score
")
echo "$HEALTH"
echo ""

echo -e "${YELLOW}Test 9: Most Error-Prone Resources${NC}\n"
ERROR_PRONE=$(run_rca_query "
MATCH (r:Resource)<-[:ABOUT]-(e:Episodic)
WHERE e.event_time >= datetime() - duration({days: 7})
  AND e.severity IN ['ERROR', 'FATAL']
WITH r,
     count(e) AS error_count,
     collect(DISTINCT e.reason)[0..3] AS error_types
ORDER BY error_count DESC
RETURN
    r.name AS resource_name,
    r.kind AS kind,
    r.ns AS namespace,
    error_count,
    error_types
LIMIT 5
")
echo "$ERROR_PRONE"
echo ""

echo -e "${YELLOW}Test 10: Topology Validation${NC}\n"
TOPOLOGY=$(run_rca_query "
MATCH ()-[r:SELECTS|RUNS_ON|CONTROLS]->()
WITH type(r) AS rel_type, count(*) AS count
RETURN rel_type, count
ORDER BY count DESC
")
echo "$TOPOLOGY"
echo ""

echo -e "\n${BLUE}==================================================${NC}"
echo -e "${BLUE}VALIDATION SUMMARY${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Check if we have meaningful data
HAS_EVENTS=$(run_rca_query "MATCH (e:Episodic) RETURN count(e) > 0 AS has_events" | grep -v "^+" | grep -v "has_events" | grep "true")
HAS_RESOURCES=$(run_rca_query "MATCH (r:Resource) RETURN count(r) > 0 AS has_resources" | grep -v "^+" | grep -v "has_resources" | grep "true")
HAS_TOPOLOGY=$(run_rca_query "MATCH ()-[r:SELECTS|RUNS_ON|CONTROLS]->() RETURN count(r) > 0 AS has_topology" | grep -v "^+" | grep -v "has_topology" | grep "true")
HAS_RCA=$(run_rca_query "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r) > 0 AS has_rca" | grep -v "^+" | grep -v "has_rca" | grep "true")

echo -e "Events in DB: ${GREEN}$([ ! -z "$HAS_EVENTS" ] && echo "✓ Yes" || echo "✗ No")${NC}"
echo -e "Resources in DB: ${GREEN}$([ ! -z "$HAS_RESOURCES" ] && echo "✓ Yes" || echo "✗ No")${NC}"
echo -e "Topology Relationships: ${GREEN}$([ ! -z "$HAS_TOPOLOGY" ] && echo "✓ Yes" || echo "✗ No")${NC}"
echo -e "RCA Relationships: ${GREEN}$([ ! -z "$HAS_RCA" ] && echo "✓ Yes" || echo "✗ No")${NC}"

if [ ! -z "$HAS_EVENTS" ] && [ ! -z "$HAS_RESOURCES" ] && [ ! -z "$HAS_TOPOLOGY" ] && [ ! -z "$HAS_RCA" ]; then
    echo -e "\n${GREEN}✓ Knowledge graph is properly populated and RCA queries work!${NC}"
    exit 0
else
    echo -e "\n${YELLOW}⚠ Knowledge graph may be missing some data${NC}"
    exit 1
fi
