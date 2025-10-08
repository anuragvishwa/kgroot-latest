#!/bin/bash
# Backup Neo4j database

BACKUP_DIR="./backups/neo4j"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="neo4j-${TIMESTAMP}.dump"

mkdir -p $BACKUP_DIR

echo "🗄️  Backing up Neo4j database..."
echo "Backup file: $BACKUP_FILE"

# Create dump inside container
docker exec kgroot_latest-neo4j-1 neo4j-admin database dump neo4j \
  --to-path=/tmp/backup.dump 2>&1 | grep -v "^$"

if [ $? -eq 0 ]; then
  # Copy dump to host
  docker cp kgroot_latest-neo4j-1:/tmp/backup.dump \
    $BACKUP_DIR/$BACKUP_FILE

  if [ $? -eq 0 ]; then
    echo "✅ Backup complete!"
    echo ""
    echo "Backup location: $BACKUP_DIR/$BACKUP_FILE"
    ls -lh $BACKUP_DIR/$BACKUP_FILE
    echo ""
    echo "To restore:"
    echo "  1. Stop graph-builder: docker compose stop graph-builder"
    echo "  2. docker exec kgroot_latest-neo4j-1 neo4j-admin database load neo4j --from-path=/tmp/backup.dump --overwrite-destination=true"
    echo "  3. Restart: docker compose restart neo4j graph-builder"

    # Cleanup old backups (keep last 7 days)
    echo ""
    echo "🧹 Cleaning up old backups (keeping last 7 days)..."
    find $BACKUP_DIR -name "neo4j-*.dump" -mtime +7 -delete 2>/dev/null
    echo "Remaining backups:"
    ls -lht $BACKUP_DIR/ | head -10
  else
    echo "❌ Failed to copy backup from container"
    exit 1
  fi
else
  echo "❌ Failed to create Neo4j dump"
  exit 1
fi
