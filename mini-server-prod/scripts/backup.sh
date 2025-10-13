#!/bin/bash

# ============================================================================
# KG RCA Mini Server - Backup Script
# ============================================================================
# This script backs up Neo4j data and Kafka topics
# Recommended: Run daily via cron
# ============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}KG RCA Mini Server - Backup${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""

# ============================================================================
# Configuration
# ============================================================================
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="kg-rca-backup-$TIMESTAMP"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

# Retention (days)
RETENTION_DAYS=${RETENTION_DAYS:-7}

# ============================================================================
# Create backup directory
# ============================================================================
echo -e "${YELLOW}[1/4] Preparing backup directory...${NC}"
mkdir -p "$BACKUP_PATH"
echo "Backup location: $BACKUP_PATH"
echo ""

# ============================================================================
# Backup Neo4j
# ============================================================================
echo -e "${YELLOW}[2/4] Backing up Neo4j database...${NC}"

# Stop Neo4j for consistent backup (or use online backup if Enterprise)
echo "Creating Neo4j backup..."

# Option 1: Offline backup (recommended for consistency)
# Uncomment if you want to stop Neo4j during backup
# docker compose stop neo4j

# Copy Neo4j data
docker run --rm \
    --volumes-from kg-neo4j \
    -v "$BACKUP_PATH:/backup" \
    ubuntu \
    tar czf /backup/neo4j-data.tar.gz /data

echo -e "${GREEN}✓ Neo4j backup complete${NC}"

# Restart Neo4j if it was stopped
# docker compose start neo4j

echo ""

# ============================================================================
# Backup Kafka topics metadata
# ============================================================================
echo -e "${YELLOW}[3/4] Backing up Kafka metadata...${NC}"

# List all topics
docker exec kg-kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --describe > "$BACKUP_PATH/kafka-topics.txt"

# Get topic configurations
docker exec kg-kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --list | while read topic; do
    echo "Topic: $topic" >> "$BACKUP_PATH/kafka-configs.txt"
    docker exec kg-kafka kafka-configs.sh \
        --bootstrap-server localhost:9092 \
        --entity-type topics \
        --entity-name "$topic" \
        --describe >> "$BACKUP_PATH/kafka-configs.txt"
    echo "" >> "$BACKUP_PATH/kafka-configs.txt"
done

echo -e "${GREEN}✓ Kafka metadata backup complete${NC}"
echo ""

# ============================================================================
# Backup configurations
# ============================================================================
echo -e "${YELLOW}[4/4] Backing up configuration files...${NC}"

# Copy docker-compose files
cp docker-compose*.yml "$BACKUP_PATH/" 2>/dev/null || true

# Copy .env (without sensitive data)
if [ -f .env ]; then
    grep -v -E 'PASSWORD|KEY|SECRET' .env > "$BACKUP_PATH/env.txt" 2>/dev/null || true
fi

# Copy config directory
if [ -d config ]; then
    cp -r config "$BACKUP_PATH/"
fi

echo -e "${GREEN}✓ Configuration backup complete${NC}"
echo ""

# ============================================================================
# Create backup manifest
# ============================================================================
cat > "$BACKUP_PATH/manifest.txt" <<EOF
KG RCA Backup Manifest
======================

Backup Date: $(date)
Backup Name: $BACKUP_NAME
Hostname: $(hostname)
Docker Version: $(docker --version)

Contents:
---------
- neo4j-data.tar.gz: Neo4j database dump
- kafka-topics.txt: Kafka topics description
- kafka-configs.txt: Kafka topic configurations
- docker-compose*.yml: Service configurations
- env.txt: Environment variables (sanitized)
- config/: Application configurations

Restore Instructions:
--------------------
1. Extract Neo4j data: tar xzf neo4j-data.tar.gz
2. Stop services: docker compose down
3. Copy Neo4j data to volume location
4. Recreate Kafka topics using kafka-topics.txt
5. Start services: docker compose up -d

EOF

# ============================================================================
# Compress backup
# ============================================================================
echo -e "${YELLOW}Compressing backup...${NC}"
cd "$BACKUP_DIR"
tar czf "${BACKUP_NAME}.tar.gz" "$BACKUP_NAME"
rm -rf "$BACKUP_NAME"
cd - > /dev/null

BACKUP_SIZE=$(du -h "$BACKUP_DIR/${BACKUP_NAME}.tar.gz" | cut -f1)
echo -e "${GREEN}✓ Backup compressed: $BACKUP_SIZE${NC}"
echo ""

# ============================================================================
# Clean old backups
# ============================================================================
echo -e "${YELLOW}Cleaning old backups (older than $RETENTION_DAYS days)...${NC}"

find "$BACKUP_DIR" -name "kg-rca-backup-*.tar.gz" -type f -mtime +$RETENTION_DAYS -delete

REMAINING_BACKUPS=$(find "$BACKUP_DIR" -name "kg-rca-backup-*.tar.gz" -type f | wc -l)
echo -e "${GREEN}✓ Cleanup complete ($REMAINING_BACKUPS backups remaining)${NC}"
echo ""

# ============================================================================
# Summary
# ============================================================================
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}Backup Complete${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Backup file: $BACKUP_DIR/${BACKUP_NAME}.tar.gz"
echo "Backup size: $BACKUP_SIZE"
echo "Retention: $RETENTION_DAYS days"
echo "Remaining backups: $REMAINING_BACKUPS"
echo ""
echo "To restore this backup:"
echo "  tar xzf $BACKUP_DIR/${BACKUP_NAME}.tar.gz"
echo "  cd ${BACKUP_NAME}"
echo "  cat manifest.txt  # Read restore instructions"
echo ""
echo -e "${YELLOW}Recommendation: Copy backup to remote storage (S3, etc.)${NC}"
echo ""

# ============================================================================
# Optional: Upload to S3 (uncomment to enable)
# ============================================================================
# if command -v aws &> /dev/null; then
#     echo -e "${YELLOW}Uploading to S3...${NC}"
#     S3_BUCKET="your-backup-bucket"
#     aws s3 cp "$BACKUP_DIR/${BACKUP_NAME}.tar.gz" "s3://$S3_BUCKET/kg-rca-backups/"
#     echo -e "${GREEN}✓ Backup uploaded to S3${NC}"
# fi
