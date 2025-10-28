#!/bin/bash

# ============================================================================
# KG RCA Mini Server - Kafka Topics Creation
# ============================================================================
# This script creates all required Kafka topics
# Run after Kafka is up and healthy
# ============================================================================

# Note: Not using 'set -e' to allow continuing after warnings

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}KG RCA - Kafka Topics Creation${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""

# ============================================================================
# Configuration
# ============================================================================
KAFKA_CONTAINER="kg-kafka"
BOOTSTRAP_SERVER="localhost:9092"

# ============================================================================
# Check if Kafka is running
# ============================================================================
echo -e "${YELLOW}Checking Kafka status...${NC}"

if ! docker ps | grep -q $KAFKA_CONTAINER; then
    echo -e "${RED}Error: Kafka container is not running${NC}"
    echo "Start services first: docker compose up -d"
    exit 1
fi

echo -e "${GREEN}✓ Kafka is running${NC}"
echo ""

# ============================================================================
# Topic definitions
# Format: TOPIC_NAME:PARTITIONS:RETENTION_MS:DESCRIPTION
# ============================================================================
TOPICS=(
    "raw.k8s.events:3:1209600000:Raw Kubernetes events (14 days)"
    "raw.k8s.logs:6:259200000:Raw Kubernetes logs (3 days)"
    "raw.prom.alerts:3:2592000000:Raw Prometheus alerts (30 days)"
    "events.normalized:3:1209600000:Normalized events (14 days)"
    "logs.normalized:6:259200000:Normalized logs (3 days)"
    "alerts.enriched:3:2592000000:Enriched alerts (30 days)"
    "state.k8s.resource:3:2592000000:Kubernetes resource state (30 days)"
    "state.k8s.topology:3:2592000000:Kubernetes topology state (30 days)"
    "state.prom.targets:3:2592000000:Prometheus targets state (30 days)"
    "state.prom.rules:3:2592000000:Prometheus rules state (30 days)"
    "dlq.raw:3:604800000:Dead letter queue - raw processing (7 days)"
    "dlq.normalized:3:604800000:Dead letter queue - normalization (7 days)"
)

# ============================================================================
# Function to create topic
# ============================================================================
create_topic() {
    local topic_name=$1
    local partitions=$2
    local retention_ms=$3
    local description=$4

    echo -e "${YELLOW}Creating topic: $topic_name${NC}"
    echo "  Partitions: $partitions"
    echo "  Retention: $retention_ms ms ($((retention_ms / 1000 / 60 / 60 / 24)) days)"
    echo "  Description: $description"

    # Check if topic already exists
    if docker exec $KAFKA_CONTAINER kafka-topics.sh \
        --bootstrap-server $BOOTSTRAP_SERVER \
        --list | grep -q "^${topic_name}$"; then
        echo -e "${YELLOW}  Topic already exists, skipping...${NC}"
        return 0
    fi

    # Create topic
    docker exec $KAFKA_CONTAINER kafka-topics.sh \
        --bootstrap-server $BOOTSTRAP_SERVER \
        --create \
        --topic "$topic_name" \
        --partitions "$partitions" \
        --replication-factor 1 \
        --config compression.type=gzip \
        --config retention.ms="$retention_ms" \
        --config segment.bytes=1073741824 \
        --config min.insync.replicas=1

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}  ✓ Topic created successfully${NC}"
    else
        echo -e "${RED}  ✗ Failed to create topic${NC}"
        return 1
    fi
}

# ============================================================================
# Create all topics
# ============================================================================
echo -e "${YELLOW}Creating topics...${NC}"
echo ""

SUCCESS_COUNT=0
FAILED_COUNT=0

for topic_def in "${TOPICS[@]}"; do
    IFS=':' read -r name partitions retention description <<< "$topic_def"

    if create_topic "$name" "$partitions" "$retention" "$description"; then
        ((SUCCESS_COUNT++))
    else
        ((FAILED_COUNT++))
    fi
    echo ""
done

# ============================================================================
# List all topics
# ============================================================================
echo -e "${YELLOW}Listing all topics:${NC}"
docker exec $KAFKA_CONTAINER kafka-topics.sh \
    --bootstrap-server $BOOTSTRAP_SERVER \
    --list | sort

echo ""

# ============================================================================
# Show topic details
# ============================================================================
echo -e "${YELLOW}Topic details:${NC}"
docker exec $KAFKA_CONTAINER kafka-topics.sh \
    --bootstrap-server $BOOTSTRAP_SERVER \
    --describe

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}Topic Creation Complete${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo -e "Topics created: ${GREEN}$SUCCESS_COUNT${NC}"
if [ $FAILED_COUNT -gt 0 ]; then
    echo -e "Topics failed: ${RED}$FAILED_COUNT${NC}"
fi
echo ""
echo "Next steps:"
echo "1. Verify topics are created: docker exec $KAFKA_CONTAINER kafka-topics.sh --bootstrap-server $BOOTSTRAP_SERVER --list"
echo "2. Check Kafka UI: http://your-server:7777"
echo "3. Deploy client agents to start sending data"
echo ""
