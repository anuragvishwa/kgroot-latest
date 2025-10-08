#!/bin/bash
# Cleanup old episodic events from Neo4j (data retention)

RETENTION_DAYS=${1:-7}

echo "🧹 Cleaning up episodic events older than $RETENTION_DAYS days..."

# Count events before deletion
BEFORE=$(docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic) RETURN count(e) as total" --format plain 2>/dev/null | tail -1)

echo "Events before cleanup: $BEFORE"

# Delete old events
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa <<EOF
MATCH (e:Episodic)
WHERE e.eventTime < datetime() - duration('P${RETENTION_DAYS}D')
WITH e LIMIT 10000
DETACH DELETE e
RETURN count(e) as deleted
EOF

# Count events after deletion
AFTER=$(docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic) RETURN count(e) as total" --format plain 2>/dev/null | tail -1)

echo ""
echo "Events after cleanup: $AFTER"
echo "Deleted: $((BEFORE - AFTER)) events"
echo ""
echo "✅ Cleanup complete!"
echo ""
echo "Note: Run this script regularly (e.g., daily cron job)"
echo "Example cron: 0 2 * * * /path/to/cleanup-old-events.sh 7"
