#!/bin/bash

# Query Library Validation Script
# Tests all queries from production/neo4j-queries/QUERY_LIBRARY.md

NEO4J_URL="bolt://localhost:7687"
NEO4J_USER="neo4j"
NEO4J_PASS="anuragvishwa"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}Knowledge Graph Query Library Validation${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Helper function to run query and check result
run_query_test() {
    local test_name="$1"
    local query="$2"
    local description="$3"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo -e "${BLUE}Test $TOTAL_TESTS: $test_name${NC}"
    echo -e "Description: $description"

    # Run query using cypher-shell
    result=$(docker exec kgroot_latest-neo4j-1 cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" "$query" 2>&1)
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ Query executed successfully${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))

        # Count results
        result_count=$(echo "$result" | grep -v "^+" | grep -v "^|" | grep -v "rows available" | wc -l | xargs)
        echo -e "  Results: $result_count rows\n"
        return 0
    else
        echo -e "${RED}✗ Query failed${NC}"
        echo -e "${RED}Error: $result${NC}\n"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi
}

# Get sample event IDs and resource UIDs for parameterized queries
echo -e "${YELLOW}Fetching sample data for parameterized queries...${NC}\n"

SAMPLE_EVENT=$(docker exec kgroot_latest-neo4j-1 cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" \
    "MATCH (e:Episodic) RETURN e.eid LIMIT 1" --format plain 2>/dev/null | grep -v "^+" | grep -v "e.eid" | head -1 | xargs)

SAMPLE_RESOURCE=$(docker exec kgroot_latest-neo4j-1 cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" \
    "MATCH (r:Resource) RETURN r.uid LIMIT 1" --format plain 2>/dev/null | grep -v "^+" | grep -v "r.uid" | head -1 | xargs)

SAMPLE_RESOURCE_RID=$(docker exec kgroot_latest-neo4j-1 cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" \
    "MATCH (r:Resource) RETURN r.rid LIMIT 1" --format plain 2>/dev/null | grep -v "^+" | grep -v "r.rid" | head -1 | xargs)

echo -e "Sample Event ID: ${GREEN}$SAMPLE_EVENT${NC}"
echo -e "Sample Resource UID: ${GREEN}$SAMPLE_RESOURCE${NC}"
echo -e "Sample Resource RID: ${GREEN}$SAMPLE_RESOURCE_RID${NC}\n"

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}1. RCA & CAUSALITY QUERIES${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Test 1.1: Root Causes with Confidence Scoring (simplified)
run_query_test \
    "Find Root Causes with Confidence" \
    "MATCH (e:Episodic {eid: '$SAMPLE_EVENT'})-[:ABOUT]->(r:Resource)
     MATCH (c:Episodic)-[:ABOUT]->(u:Resource)
     WHERE c.event_time <= e.event_time
       AND c.event_time >= e.event_time - duration({minutes: 15})
       AND u <> r
     OPTIONAL MATCH p = shortestPath((u)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r))
     WHERE p IS NOT NULL
     WITH e, c, p,
          1.0 - (duration.between(c.event_time, e.event_time).milliseconds / 900000.0) AS temporal_score,
          1.0 / (length(p) + 1.0) AS distance_score
     WITH e, c, p,
          (temporal_score * 0.5 + distance_score * 0.5) AS confidence
     WHERE confidence >= 0.3
     RETURN c.eid, c.reason, confidence, length(p) AS hops
     ORDER BY confidence DESC
     LIMIT 5" \
    "Find root causes for an event with confidence scores"

# Test 1.2: Complete Causal Chain
run_query_test \
    "Causal Chain Analysis" \
    "MATCH (effect:Episodic {eid: '$SAMPLE_EVENT'})
     MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..3]->(effect)
     WHERE NOT EXISTS { (:Episodic)-[:POTENTIAL_CAUSE]->(root) }
     WITH path, [node IN nodes(path) | node.eid] AS event_chain,
          length(path) AS chain_length
     RETURN event_chain, chain_length
     ORDER BY chain_length ASC
     LIMIT 3" \
    "Find complete causal chains from root cause to effect"

# Test 1.3: Cascading Failures
run_query_test \
    "Detect Cascading Failures" \
    "MATCH (trigger:Episodic)-[:ABOUT]->(r:Resource)
     WHERE trigger.event_time >= datetime() - duration({hours: 24})
       AND trigger.severity IN ['ERROR', 'FATAL']
     MATCH (trigger)-[:POTENTIAL_CAUSE]->(cascade:Episodic)
     WHERE cascade.event_time > trigger.event_time
       AND cascade.event_time <= trigger.event_time + duration({minutes: 15})
     WITH trigger, r, count(DISTINCT cascade) AS cascade_count
     WHERE cascade_count >= 2
     RETURN trigger.eid, trigger.reason, r.rid, cascade_count
     ORDER BY cascade_count DESC
     LIMIT 5" \
    "Detect cascading failure patterns"

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}2. VECTOR EMBEDDING QUERIES${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Test 2.1: Check embeddings exist
run_query_test \
    "Check Vector Embeddings" \
    "MATCH (e:Episodic)
     WHERE e.embedding IS NOT NULL
     RETURN count(e) AS events_with_embeddings" \
    "Count events with embeddings"

# Test 2.2: Find events without embeddings
run_query_test \
    "Find Events Without Embeddings" \
    "MATCH (e:Episodic)
     WHERE e.embedding IS NULL
       AND e.event_time >= datetime() - duration({days: 7})
     RETURN count(e) AS events_without_embeddings" \
    "Count events needing embeddings"

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}3. RESOURCE & TOPOLOGY QUERIES${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Test 3.1: Complete Resource Topology
run_query_test \
    "Get Resource Topology" \
    "MATCH (r:Resource {uid: '$SAMPLE_RESOURCE'})
     OPTIONAL MATCH (r)-[rel1]->(related1:Resource)
     OPTIONAL MATCH (r)<-[rel2]-(related2:Resource)
     WITH r,
          count(DISTINCT rel1) AS outgoing_count,
          count(DISTINCT rel2) AS incoming_count
     RETURN r.rid, r.kind, r.name, outgoing_count, incoming_count" \
    "Get complete topology for a resource"

# Test 3.2: Blast Radius
run_query_test \
    "Calculate Blast Radius" \
    "MATCH (failed:Resource {uid: '$SAMPLE_RESOURCE'})
     MATCH path = (failed)-[:SELECTS|RUNS_ON|CONTROLS*1..2]-(affected:Resource)
     OPTIONAL MATCH (affected)<-[:ABOUT]-(e:Episodic)
     WHERE e.event_time >= datetime() - duration({hours: 24})
       AND e.severity IN ['ERROR', 'FATAL']
     WITH DISTINCT affected, count(e) AS error_count, length(path) AS distance
     RETURN affected.rid, affected.kind, distance, error_count
     ORDER BY distance, error_count DESC
     LIMIT 10" \
    "Calculate blast radius for a resource"

# Test 3.3: Orphaned Resources
run_query_test \
    "Find Orphaned Resources" \
    "MATCH (r:Resource)
     WHERE NOT EXISTS { (r)-[:SELECTS|RUNS_ON|CONTROLS]-() }
       AND r.updated_at < datetime() - duration({hours: 24})
     RETURN count(r) AS orphaned_count" \
    "Find resources with no relationships"

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}4. INCIDENT ANALYSIS QUERIES${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Test 4.1: Get Incidents
run_query_test \
    "Get All Incidents" \
    "MATCH (inc:Incident)
     RETURN count(inc) AS total_incidents" \
    "Count total incidents"

# Test 4.2: Incident Timeline
run_query_test \
    "Get Incident Timeline" \
    "MATCH (inc:Incident)
     MATCH (e:Episodic)-[:PART_OF]->(inc)
     WITH inc, count(e) AS event_count
     RETURN inc.resource_id, event_count
     ORDER BY event_count DESC
     LIMIT 5" \
    "Get timeline for incidents"

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}5. ANOMALY DETECTION QUERIES${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Test 5.1: Error Spike Detection
run_query_test \
    "Detect Error Spikes" \
    "WITH datetime() - duration({minutes: 15}) AS recent_window,
          datetime() - duration({hours: 24}) AS baseline_window
     MATCH (recent:Episodic)
     WHERE recent.event_time >= recent_window
       AND recent.severity IN ['ERROR', 'FATAL']
     WITH count(recent) AS recent_count, baseline_window
     MATCH (historical:Episodic)
     WHERE historical.event_time >= baseline_window
       AND historical.severity IN ['ERROR', 'FATAL']
     WITH recent_count, count(historical) / 96.0 AS baseline_avg
     WITH recent_count, baseline_avg,
          recent_count / CASE WHEN baseline_avg > 0 THEN baseline_avg ELSE 1 END AS spike_ratio
     RETURN recent_count, baseline_avg, spike_ratio" \
    "Compare current error rate to historical average"

# Test 5.2: Memory Leak Detection
run_query_test \
    "Detect Memory Leak Patterns" \
    "MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
     WHERE e.reason IN ['OOMKilled', 'LOG_OOM_KILLED']
       AND e.event_time >= datetime() - duration({hours: 6})
     WITH r, count(e) AS oom_count
     WHERE oom_count >= 2
     RETURN r.rid, r.kind, r.name, oom_count
     ORDER BY oom_count DESC
     LIMIT 5" \
    "Find resources with increasing OOM events"

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}6. PERFORMANCE & HEALTH QUERIES${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Test 6.1: System Health Dashboard
run_query_test \
    "System Health Dashboard" \
    "MATCH (r:Resource)
     WITH count(r) AS total_resources,
          count(DISTINCT r.kind) AS resource_types,
          count(DISTINCT r.ns) AS namespaces
     MATCH (e:Episodic)
     WHERE e.event_time >= datetime() - duration({hours: 24})
     WITH total_resources, resource_types, namespaces,
          count(e) AS total_events_24h,
          sum(CASE WHEN e.severity = 'ERROR' THEN 1 ELSE 0 END) AS errors_24h,
          sum(CASE WHEN e.severity = 'FATAL' THEN 1 ELSE 0 END) AS fatal_24h
     RETURN {
         resources: total_resources,
         resource_types: resource_types,
         namespaces: namespaces,
         events_24h: total_events_24h,
         errors_24h: errors_24h,
         fatal_24h: fatal_24h
     } AS dashboard" \
    "Complete system health overview"

# Test 6.2: Resource Health Scores
run_query_test \
    "Calculate Resource Health Scores" \
    "MATCH (r:Resource)
     WHERE r.kind IN ['Pod', 'Service', 'Deployment']
     OPTIONAL MATCH (r)<-[:ABOUT]-(e:Episodic)
     WHERE e.event_time >= datetime() - duration({hours: 24})
     WITH r,
          count(e) AS total_events,
          sum(CASE WHEN e.severity = 'ERROR' THEN 1 ELSE 0 END) AS errors,
          sum(CASE WHEN e.severity = 'FATAL' THEN 1 ELSE 0 END) AS fatal
     WITH r, total_events, errors, fatal,
          1.0 - (toFloat(errors) * 0.5 + toFloat(fatal) * 1.0) / CASE WHEN total_events > 0 THEN total_events ELSE 1 END AS health_score
     WHERE health_score < 0.8
     RETURN r.rid, r.kind, r.name, total_events, errors, fatal, health_score
     ORDER BY health_score ASC
     LIMIT 10" \
    "Calculate health scores for all resources"

# Test 6.3: Top Error-Prone Resources
run_query_test \
    "Find Error-Prone Resources" \
    "MATCH (r:Resource)<-[:ABOUT]-(e:Episodic)
     WHERE e.event_time >= datetime() - duration({days: 7})
       AND e.severity IN ['ERROR', 'FATAL']
     WITH r, count(e) AS error_count
     ORDER BY error_count DESC
     RETURN r.rid, r.kind, r.name, error_count
     LIMIT 10" \
    "Find resources with most errors"

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}7. MAINTENANCE QUERIES${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Test 7.1: Database Statistics
run_query_test \
    "Get Database Statistics" \
    "MATCH (n)
     WITH labels(n) AS labels, count(*) AS count
     UNWIND labels AS label
     WITH label, sum(count) AS total
     RETURN label AS node_type, total AS count
     ORDER BY total DESC" \
    "Get node counts by type"

# Test 7.2: Relationship Statistics
run_query_test \
    "Get Relationship Statistics" \
    "MATCH ()-[r]->()
     WITH type(r) AS rel_type, count(*) AS count
     RETURN rel_type, count
     ORDER BY count DESC" \
    "Get relationship counts by type"

echo -e "\n${BLUE}==================================================${NC}"
echo -e "${BLUE}TEST SUMMARY${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "Total Tests: ${YELLOW}$TOTAL_TESTS${NC}"
echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed: ${RED}$FAILED_TESTS${NC}"

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "\n${GREEN}✓ All queries validated successfully!${NC}"
    exit 0
else
    echo -e "\n${RED}✗ Some queries failed validation${NC}"
    exit 1
fi
