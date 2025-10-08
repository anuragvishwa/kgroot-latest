#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUERIES_DIR="$SCRIPT_DIR/../queries"
NEO4J_USER="neo4j"
NEO4J_PASS="anuragvishwa"
NEO4J_CONTAINER="kgroot_latest-neo4j-1"

echo "=========================================="
echo "Testing Improved Queries"
echo "=========================================="
echo ""

echo "1. Fixed Basic Stats"
echo "----------------------------------------"
docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" \
  "$(cat $QUERIES_DIR/01-fixed-basic-stats.cypher | grep -v '^//' | grep -v '^$' | head -20)"

echo ""
echo "2. Correlation-Based RCA (No POTENTIAL_CAUSE needed)"
echo "----------------------------------------"
echo "Finding events that happened close in time..."
docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" \
  "$(cat $QUERIES_DIR/02-correlation-based-rca.cypher | sed -n '/^MATCH.*e1:Episodic.*e2:Episodic/,/^LIMIT 20;/p')"

echo ""
echo "3. Debug RCA"
echo "----------------------------------------"
echo "Checking if POTENTIAL_CAUSE relationships exist..."
docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" \
  "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r) as rca_count;"

echo ""
echo "Counting all relationship types..."
docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASS" \
  "MATCH ()-[r]->() RETURN type(r) as rel_type, count(*) as count ORDER BY count DESC LIMIT 10;"

echo ""
echo "=========================================="
echo "✅ Query Testing Complete"
echo "=========================================="
echo ""
echo "For full query results, use Neo4j Browser:"
echo "  http://localhost:7474"
echo "  Username: neo4j"
echo "  Password: anuragvishwa"
echo ""
echo "Copy queries from: improvements/queries/"
