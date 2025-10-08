#!/bin/bash
# Production cleanup script for Neo4j episodic events
# Removes events older than retention period to prevent graph bloat

set -e

# Configuration
RETENTION_DAYS=${1:-7}
NEO4J_CONTAINER=${NEO4J_CONTAINER:-kgroot_latest-neo4j-1}
NEO4J_USER=${NEO4J_USER:-neo4j}
NEO4J_PASS=${NEO4J_PASS:-anuragvishwa}
DRY_RUN=${DRY_RUN:-false}
BATCH_SIZE=1000

echo "🧹 Neo4j Cleanup - Retention: ${RETENTION_DAYS} days"
echo "=================================================="

# Get current stats
echo "📊 Current Database Stats:"
docker exec ${NEO4J_CONTAINER} cypher-shell -u ${NEO4J_USER} -p ${NEO4J_PASS} \
  "MATCH (e:Episodic) WITH count(e) as events MATCH (inc:Incident) WITH events, count(inc) as incidents MATCH (r:Resource) RETURN events, incidents, count(r) as resources" \
  --format plain

# Count old events
echo -e "\n📊 Counting events to delete..."
OLD_COUNT=$(docker exec ${NEO4J_CONTAINER} cypher-shell -u ${NEO4J_USER} -p ${NEO4J_PASS} \
  "MATCH (e:Episodic) WHERE e.event_time < datetime() - duration('P${RETENTION_DAYS}D') RETURN count(e) as count" \
  --format plain | tail -n 1 | tr -d '"')

echo "Found ${OLD_COUNT} events older than ${RETENTION_DAYS} days"

if [ "$OLD_COUNT" = "0" ] || [ -z "$OLD_COUNT" ]; then
  echo "✅ No old events to clean up"
  exit 0
fi

if [ "$DRY_RUN" = "true" ]; then
  echo "🏃 DRY RUN MODE - Would delete ${OLD_COUNT} events"
  exit 0
fi

# Delete old events in batches
echo -e "\n🗑️  Deleting old events in batches of ${BATCH_SIZE}..."
DELETED_TOTAL=0

while true; do
  DELETED=$(docker exec ${NEO4J_CONTAINER} cypher-shell -u ${NEO4J_USER} -p ${NEO4J_PASS} \
    "MATCH (e:Episodic) WHERE e.event_time < datetime() - duration('P${RETENTION_DAYS}D') WITH e LIMIT ${BATCH_SIZE} DETACH DELETE e RETURN count(e) as deleted" \
    --format plain | tail -n 1 | tr -d '"')

  if [ -z "$DELETED" ] || [ "$DELETED" = "0" ]; then
    break
  fi

  DELETED_TOTAL=$((DELETED_TOTAL + DELETED))
  echo "  Deleted batch: ${DELETED} events (total: ${DELETED_TOTAL})"

  if [ "$DELETED" -lt "$BATCH_SIZE" ]; then
    break
  fi

  sleep 1
done

# Clean up orphaned incidents
echo -e "\n🧹 Cleaning orphaned incidents..."
ORPHANED=$(docker exec ${NEO4J_CONTAINER} cypher-shell -u ${NEO4J_USER} -p ${NEO4J_PASS} \
  "MATCH (inc:Incident) WHERE NOT EXISTS { MATCH (inc)<-[:PART_OF]-() } DELETE inc RETURN count(inc) as deleted" \
  --format plain | tail -n 1 | tr -d '"')

echo "  Deleted ${ORPHANED} orphaned incidents"

# Final stats
echo -e "\n📈 Final Database Stats:"
docker exec ${NEO4J_CONTAINER} cypher-shell -u ${NEO4J_USER} -p ${NEO4J_PASS} \
  "MATCH (e:Episodic) WITH count(e) as events MATCH (inc:Incident) WITH events, count(inc) as incidents MATCH (r:Resource) RETURN events, incidents, count(r) as resources" \
  --format plain

echo -e "\n✅ Cleanup complete!"
echo "Total events deleted: ${DELETED_TOTAL}"
echo "Orphaned incidents deleted: ${ORPHANED}"
echo ""
echo "💡 Schedule this script as a cron job:"
echo "   0 2 * * * /path/to/cleanup-old-events.sh 7"
