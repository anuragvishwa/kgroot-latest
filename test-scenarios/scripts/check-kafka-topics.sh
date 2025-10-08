#!/bin/bash

echo "=========================================="
echo "Checking Kafka Topics for Test Events"
echo "=========================================="
echo ""

TOPICS=(
    "raw.k8s.events"
    "events.normalized"
    "logs.normalized"
    "raw.k8s.logs"
)

for topic in "${TOPICS[@]}"; do
    echo "=== Topic: $topic ==="

    # Try to get latest message
    echo "Latest message (if any):"
    docker exec kgroot_latest-kafka-1 kafka-console-consumer.sh \
        --bootstrap-server localhost:9092 \
        --topic "$topic" \
        --max-messages 1 \
        --timeout-ms 3000 \
        2>&1 | grep -v "WARN\|ERROR" | head -5 || echo "No recent messages"

    echo ""
done

echo "=========================================="
echo "Consumer Group Status"
echo "=========================================="
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --group kg-builder \
    --describe 2>/dev/null | head -20

echo ""
echo "For Kafka UI, visit: http://localhost:7777"
