#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEO4J_USER="neo4j"
NEO4J_PASS="anuragvishwa"
NEO4J_CONTAINER="kgroot_latest-neo4j-1"

echo "=========================================="
echo "Running Neo4j Test Queries"
echo "=========================================="
echo ""

queries=(
    "01-basic-stats.cypher:Basic Statistics"
    "02-crashloop-analysis.cypher:CrashLoop Analysis"
    "03-oom-analysis.cypher:OOM Analysis"
    "04-probe-failures.cypher:Probe Failures"
    "05-image-pull-errors.cypher:Image Pull Errors"
    "06-error-logs-analysis.cypher:Error Logs Analysis"
    "07-rca-analysis.cypher:Root Cause Analysis"
    "08-topology-analysis.cypher:Topology Analysis"
)

for entry in "${queries[@]}"; do
    IFS=':' read -r file title <<< "$entry"
    filepath="$SCRIPT_DIR/$file"

    if [ ! -f "$filepath" ]; then
        echo "⚠️  Skipping $title - file not found: $file"
        continue
    fi

    echo "=========================================="
    echo "📊 $title"
    echo "=========================================="

    # Read the cypher file and execute each query
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip comments and empty lines
        if [[ "$line" =~ ^// ]] || [[ -z "$line" ]]; then
            if [[ "$line" =~ ^// ]]; then
                echo "$line"
            fi
            continue
        fi

        # Accumulate query lines until we hit a semicolon
        if [[ -z "$query" ]]; then
            query="$line"
        else
            query="$query $line"
        fi

        # Execute when we find a semicolon
        if [[ "$line" =~ \;$ ]]; then
            echo ""
            docker exec "$NEO4J_CONTAINER" cypher-shell \
                -u "$NEO4J_USER" \
                -p "$NEO4J_PASS" \
                "$query" 2>&1 || echo "Error executing query"
            echo ""
            query=""
        fi
    done < "$filepath"

    echo ""
done

echo "=========================================="
echo "✅ All queries complete!"
echo "=========================================="
echo ""
echo "Access Neo4j Browser: http://localhost:7474"
echo "  Username: neo4j"
echo "  Password: anuragvishwa"
