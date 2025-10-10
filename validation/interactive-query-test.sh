#!/bin/bash

# Interactive Query Tester
# Allows testing custom queries against the knowledge graph

NEO4J_USER="neo4j"
NEO4J_PASS="anuragvishwa"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}Interactive Knowledge Graph Query Tester${NC}"
echo -e "${BLUE}==================================================${NC}\n"

# Function to run query
run_query() {
    local query="$1"
    echo -e "${YELLOW}Executing query...${NC}\n"
    docker exec kgroot_latest-neo4j-1 cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" "$query" --format plain 2>&1
    echo ""
}

# Menu
while true; do
    echo -e "${BLUE}Select a query to test:${NC}"
    echo ""
    echo "  1. Find recent ERROR/FATAL events"
    echo "  2. Root cause analysis for a specific event"
    echo "  3. Find cascading failures"
    echo "  4. Check system health"
    echo "  5. Find error-prone resources"
    echo "  6. Get topology for a resource"
    echo "  7. Find causal chains"
    echo "  8. Get incident timeline"
    echo "  9. Detect memory leaks (OOM events)"
    echo " 10. Check embedding coverage"
    echo " 11. Database statistics"
    echo " 12. Custom query (enter your own)"
    echo "  0. Exit"
    echo ""
    echo -n "Enter choice: "
    read choice

    case $choice in
        1)
            echo -e "\n${YELLOW}Query: Find recent ERROR/FATAL events${NC}\n"
            run_query "
            MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
            WHERE e.event_time >= datetime() - duration({hours: 24})
              AND e.severity IN ['ERROR', 'FATAL']
            RETURN e.eid, e.reason, e.severity, r.name, toString(e.event_time) AS time
            ORDER BY e.event_time DESC
            LIMIT 10
            "
            ;;
        2)
            echo ""
            echo -n "Enter event ID (or press Enter for sample): "
            read event_id
            if [ -z "$event_id" ]; then
                event_id=$(docker exec kgroot_latest-neo4j-1 cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" \
                    "MATCH (e:Episodic) RETURN e.eid LIMIT 1" --format plain 2>/dev/null | grep -v "^+" | grep -v "e.eid" | head -1 | xargs)
            fi
            echo -e "\n${YELLOW}Query: Root cause analysis for event $event_id${NC}\n"
            run_query "
            MATCH (e:Episodic {eid: '$event_id'})-[:ABOUT]->(r:Resource)
            OPTIONAL MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(e)
            WHERE pc.confidence >= 0.5
            RETURN
                e.eid AS effect_event,
                e.reason AS effect_reason,
                r.name AS effect_resource,
                cause.eid AS root_cause_event,
                cause.reason AS root_cause_reason,
                pc.confidence AS confidence
            ORDER BY pc.confidence DESC
            LIMIT 10
            "
            ;;
        3)
            echo -e "\n${YELLOW}Query: Find cascading failures (last 24h)${NC}\n"
            run_query "
            MATCH (trigger:Episodic)-[:ABOUT]->(r:Resource)
            WHERE trigger.event_time >= datetime() - duration({hours: 24})
              AND trigger.severity IN ['ERROR', 'FATAL']
            MATCH (trigger)-[:POTENTIAL_CAUSE]->(cascade:Episodic)-[:ABOUT]->(affected:Resource)
            WHERE cascade.event_time > trigger.event_time
              AND cascade.event_time <= trigger.event_time + duration({minutes: 15})
            WITH trigger, r,
                 count(DISTINCT cascade) AS cascade_count,
                 collect(DISTINCT affected.name)[0..5] AS affected_resources
            WHERE cascade_count >= 3
            RETURN
                trigger.eid AS trigger_event,
                trigger.reason AS trigger_reason,
                r.name AS trigger_resource,
                cascade_count,
                affected_resources
            ORDER BY cascade_count DESC
            LIMIT 10
            "
            ;;
        4)
            echo -e "\n${YELLOW}Query: System health dashboard${NC}\n"
            run_query "
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
            "
            ;;
        5)
            echo -e "\n${YELLOW}Query: Most error-prone resources (last 7 days)${NC}\n"
            run_query "
            MATCH (r:Resource)<-[:ABOUT]-(e:Episodic)
            WHERE e.event_time >= datetime() - duration({days: 7})
              AND e.severity IN ['ERROR', 'FATAL']
            WITH r,
                 count(e) AS error_count,
                 collect(DISTINCT e.reason)[0..5] AS error_types
            ORDER BY error_count DESC
            RETURN
                r.name AS resource_name,
                r.kind AS kind,
                r.ns AS namespace,
                error_count,
                error_types
            LIMIT 10
            "
            ;;
        6)
            echo ""
            echo -n "Enter resource UID (or press Enter for sample): "
            read resource_uid
            if [ -z "$resource_uid" ]; then
                resource_uid=$(docker exec kgroot_latest-neo4j-1 cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" \
                    "MATCH (r:Resource) RETURN r.uid LIMIT 1" --format plain 2>/dev/null | grep -v "^+" | grep -v "r.uid" | head -1 | xargs)
            fi
            echo -e "\n${YELLOW}Query: Topology for resource $resource_uid${NC}\n"
            run_query "
            MATCH (r:Resource {uid: '$resource_uid'})
            OPTIONAL MATCH (r)-[rel1:SELECTS|RUNS_ON|CONTROLS]->(related1:Resource)
            OPTIONAL MATCH (r)<-[rel2:SELECTS|RUNS_ON|CONTROLS]-(related2:Resource)
            RETURN
                r.rid AS resource,
                r.kind AS kind,
                r.name AS name,
                collect(DISTINCT type(rel1) + ' -> ' + related1.name) AS outgoing,
                collect(DISTINCT related2.name + ' -> ' + type(rel2)) AS incoming
            "
            ;;
        7)
            echo -e "\n${YELLOW}Query: Find causal chains (root → effect)${NC}\n"
            run_query "
            MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..3]->(effect:Episodic)
            WHERE NOT EXISTS { (:Episodic)-[:POTENTIAL_CAUSE]->(root) }
            WITH path,
                 [node IN nodes(path) | node.eid + ':' + node.reason] AS chain,
                 length(path) AS depth,
                 [rel IN relationships(path) | rel.confidence] AS confidences
            RETURN chain, depth, confidences
            ORDER BY depth DESC
            LIMIT 10
            "
            ;;
        8)
            echo -e "\n${YELLOW}Query: Get incident timelines${NC}\n"
            run_query "
            MATCH (inc:Incident)<-[:PART_OF]-(e:Episodic)-[:ABOUT]->(r:Resource)
            WITH inc,
                 count(e) AS event_count,
                 collect(DISTINCT e.reason)[0..5] AS reasons,
                 collect(DISTINCT r.name)[0..5] AS resources
            RETURN
                inc.resource_id AS incident_id,
                toString(inc.window_start) AS start_time,
                toString(inc.window_end) AS end_time,
                event_count,
                reasons,
                resources
            ORDER BY event_count DESC
            LIMIT 10
            "
            ;;
        9)
            echo -e "\n${YELLOW}Query: Detect memory leaks (OOM events)${NC}\n"
            run_query "
            MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
            WHERE e.reason IN ['OOMKilled', 'LOG_OOM_KILLED']
              AND e.event_time >= datetime() - duration({hours: 6})
            WITH r, count(e) AS oom_count
            WHERE oom_count >= 2
            RETURN
                r.rid AS resource_id,
                r.kind AS kind,
                r.name AS name,
                oom_count,
                'Memory leak suspected' AS diagnosis
            ORDER BY oom_count DESC
            LIMIT 10
            "
            ;;
        10)
            echo -e "\n${YELLOW}Query: Check embedding coverage${NC}\n"
            run_query "
            MATCH (e:Episodic)
            WITH count(e) AS total,
                 sum(CASE WHEN e.embedding IS NOT NULL THEN 1 ELSE 0 END) AS with_embedding,
                 sum(CASE WHEN e.embedding IS NULL THEN 1 ELSE 0 END) AS without_embedding
            RETURN
                total AS total_events,
                with_embedding,
                without_embedding,
                round(toFloat(with_embedding) / total * 100) / 100.0 AS coverage_pct
            "
            ;;
        11)
            echo -e "\n${YELLOW}Query: Database statistics${NC}\n"
            run_query "
            MATCH (n)
            WITH labels(n) AS labels, count(*) AS count
            UNWIND labels AS label
            WITH label, sum(count) AS total
            RETURN label AS node_type, total AS count
            ORDER BY total DESC
            "
            echo ""
            run_query "
            MATCH ()-[r]->()
            WITH type(r) AS rel_type, count(*) AS count
            RETURN rel_type, count
            ORDER BY count DESC
            "
            ;;
        12)
            echo ""
            echo "Enter your custom Cypher query (end with semicolon on a new line):"
            echo ""
            custom_query=""
            while IFS= read -r line; do
                if [[ "$line" == ";" ]]; then
                    break
                fi
                custom_query+="$line "
            done
            echo -e "\n${YELLOW}Executing custom query...${NC}\n"
            run_query "$custom_query"
            ;;
        0)
            echo -e "\n${GREEN}Goodbye!${NC}\n"
            exit 0
            ;;
        *)
            echo -e "\n${RED}Invalid choice. Please try again.${NC}\n"
            ;;
    esac

    echo -e "${BLUE}--------------------------------------------------${NC}\n"
done
