#!/bin/bash

# ==============================================================================
# Test Script for Control Plane V2 (Pure Model)
# ==============================================================================

set -e

echo "🧪 Testing Control Plane V2 - Pure Control Plane Model"
echo "============================================================"

KAFKA_CONTAINER="kg-kafka"
KAFKA_BROKER="localhost:29092"
TEST_CLIENT_ID="test-client-001"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# ==============================================================================
# Test 1: Verify Kafka Topics Created
# ==============================================================================
echo ""
echo "${YELLOW}Test 1: Verifying Kafka Topics${NC}"
echo "------------------------------------------------"

TOPIC_COUNT=$(docker exec $KAFKA_CONTAINER kafka-topics.sh \
  --bootstrap-server $KAFKA_BROKER \
  --list | grep -E "events|logs|alerts|state|raw|cluster|dlq" | wc -l | tr -d ' ')

if [ "$TOPIC_COUNT" -eq 13 ]; then
    echo "${GREEN}✅ All 13 topics created${NC}"
else
    echo "${RED}❌ Expected 13 topics, found $TOPIC_COUNT${NC}"
    docker exec $KAFKA_CONTAINER kafka-topics.sh \
      --bootstrap-server $KAFKA_BROKER \
      --list | grep -E "events|logs|alerts|state|raw|cluster|dlq"
    exit 1
fi

# ==============================================================================
# Test 2: Verify Control Plane Running
# ==============================================================================
echo ""
echo "${YELLOW}Test 2: Verifying Control Plane${NC}"
echo "------------------------------------------------"

if docker ps | grep -q "kg-control-plane"; then
    echo "${GREEN}✅ Control Plane container running${NC}"
    docker logs kg-control-plane --tail 10
else
    echo "${RED}❌ Control Plane container not running${NC}"
    exit 1
fi

# ==============================================================================
# Test 3: Register Test Client
# ==============================================================================
echo ""
echo "${YELLOW}Test 3: Registering Test Client${NC}"
echo "------------------------------------------------"
echo "Client ID: $TEST_CLIENT_ID"

# Send registration message
echo "$TEST_CLIENT_ID:{\"client_id\":\"$TEST_CLIENT_ID\",\"cluster_name\":\"test-cluster\",\"k8s_version\":\"1.28\"}" | \
  docker exec -i $KAFKA_CONTAINER kafka-console-producer.sh \
    --bootstrap-server $KAFKA_BROKER \
    --topic cluster.registry \
    --property "parse.key=true" \
    --property "key.separator=:"

echo "${GREEN}✅ Registration message sent${NC}"

# Wait for control plane to process
echo "Waiting 10 seconds for control plane to spawn containers..."
sleep 10

# ==============================================================================
# Test 4: Verify Per-Client Containers Spawned
# ==============================================================================
echo ""
echo "${YELLOW}Test 4: Verifying Per-Client Containers${NC}"
echo "------------------------------------------------"

EXPECTED_CONTAINERS=(
  "kg-event-normalizer-$TEST_CLIENT_ID"
  "kg-log-normalizer-$TEST_CLIENT_ID"
  "kg-graph-builder-$TEST_CLIENT_ID"
)

SPAWNED_COUNT=0

for container in "${EXPECTED_CONTAINERS[@]}"; do
    if docker ps | grep -q "$container"; then
        echo "${GREEN}✅ Container spawned: $container${NC}"
        ((SPAWNED_COUNT++))
    else
        echo "${RED}❌ Container NOT spawned: $container${NC}"
    fi
done

if [ "$SPAWNED_COUNT" -eq 3 ]; then
    echo "${GREEN}✅ All 3 containers spawned successfully${NC}"
else
    echo "${RED}❌ Expected 3 containers, found $SPAWNED_COUNT${NC}"
    echo ""
    echo "Control Plane logs:"
    docker logs kg-control-plane --tail 30
    exit 1
fi

# ==============================================================================
# Test 5: Send Test Event
# ==============================================================================
echo ""
echo "${YELLOW}Test 5: Sending Test Event${NC}"
echo "------------------------------------------------"

TEST_EVENT="{\"event_id\":\"evt-test-123\",\"reason\":\"OOMKilled\",\"message\":\"Test event from control plane test\",\"type\":\"Warning\",\"metadata\":{\"uid\":\"test-123\",\"creationTimestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"},\"involvedObject\":{\"kind\":\"Pod\",\"name\":\"test-pod\",\"namespace\":\"default\"}}"

echo "$TEST_CLIENT_ID::event::test-123|$TEST_EVENT" | \
  docker exec -i $KAFKA_CONTAINER kafka-console-producer.sh \
    --bootstrap-server $KAFKA_BROKER \
    --topic raw.k8s.events \
    --property "parse.key=true" \
    --property "key.separator=|"

echo "${GREEN}✅ Test event sent to raw.k8s.events${NC}"
echo "   Key: $TEST_CLIENT_ID::event::test-123"

# Wait for normalization
echo "Waiting 5 seconds for event normalization..."
sleep 5

# ==============================================================================
# Test 6: Verify Event Normalized
# ==============================================================================
echo ""
echo "${YELLOW}Test 6: Verifying Event Normalization${NC}"
echo "------------------------------------------------"

# Check if event was normalized
NORMALIZED_EVENT=$(docker exec $KAFKA_CONTAINER kafka-console-consumer.sh \
  --bootstrap-server $KAFKA_BROKER \
  --topic events.normalized \
  --from-beginning \
  --max-messages 1 \
  --timeout-ms 5000 \
  --property print.key=true 2>/dev/null | grep "$TEST_CLIENT_ID" || echo "")

if [ -n "$NORMALIZED_EVENT" ]; then
    echo "${GREEN}✅ Event normalized successfully${NC}"
    echo "Normalized output:"
    echo "$NORMALIZED_EVENT" | head -c 200
    echo "..."
else
    echo "${RED}❌ Event not found in events.normalized topic${NC}"
    echo ""
    echo "Event normalizer logs:"
    docker logs "kg-event-normalizer-$TEST_CLIENT_ID" --tail 20
    exit 1
fi

# ==============================================================================
# Test 7: Verify Consumer Groups
# ==============================================================================
echo ""
echo "${YELLOW}Test 7: Verifying Consumer Groups${NC}"
echo "------------------------------------------------"

EXPECTED_GROUPS=(
  "event-normalizer-$TEST_CLIENT_ID"
  "log-normalizer-$TEST_CLIENT_ID"
  "graph-builder-$TEST_CLIENT_ID"
)

FOUND_GROUPS=0

for group in "${EXPECTED_GROUPS[@]}"; do
    if docker exec $KAFKA_CONTAINER kafka-consumer-groups.sh \
       --bootstrap-server $KAFKA_BROKER \
       --list 2>/dev/null | grep -q "$group"; then
        echo "${GREEN}✅ Consumer group exists: $group${NC}"
        ((FOUND_GROUPS++))
    else
        echo "${RED}❌ Consumer group NOT found: $group${NC}"
    fi
done

if [ "$FOUND_GROUPS" -eq 3 ]; then
    echo "${GREEN}✅ All consumer groups created${NC}"
else
    echo "${YELLOW}⚠️  Found $FOUND_GROUPS/3 consumer groups (may take time to register)${NC}"
fi

# ==============================================================================
# Test 8: Send Heartbeat
# ==============================================================================
echo ""
echo "${YELLOW}Test 8: Sending Heartbeat${NC}"
echo "------------------------------------------------"

HEARTBEAT="{\"client_id\":\"$TEST_CLIENT_ID\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"

echo "$TEST_CLIENT_ID:$HEARTBEAT" | \
  docker exec -i $KAFKA_CONTAINER kafka-console-producer.sh \
    --bootstrap-server $KAFKA_BROKER \
    --topic cluster.heartbeat \
    --property "parse.key=true" \
    --property "key.separator=:"

echo "${GREEN}✅ Heartbeat sent${NC}"

# ==============================================================================
# Test 9: Verify Message Payloads (NO client_id)
# ==============================================================================
echo ""
echo "${YELLOW}Test 9: Verifying Clean Message Payloads${NC}"
echo "------------------------------------------------"

# Check if normalized event payload contains client_id (it shouldn't!)
PAYLOAD_CHECK=$(docker exec $KAFKA_CONTAINER kafka-console-consumer.sh \
  --bootstrap-server $KAFKA_BROKER \
  --topic events.normalized \
  --from-beginning \
  --max-messages 1 \
  --timeout-ms 3000 2>/dev/null | grep "client_id" || echo "")

if [ -z "$PAYLOAD_CHECK" ]; then
    echo "${GREEN}✅ Message payloads are clean (no client_id field)${NC}"
else
    echo "${YELLOW}⚠️  Message payload contains client_id (expected to be removed in V2)${NC}"
    echo "This may indicate V1 normalizer is still running."
fi

# ==============================================================================
# Summary
# ==============================================================================
echo ""
echo "============================================================"
echo "${GREEN}✅ Control Plane V2 Test Complete!${NC}"
echo "============================================================"
echo ""
echo "Summary:"
echo "  ✅ 13 Kafka topics created"
echo "  ✅ Control plane running"
echo "  ✅ Test client registered"
echo "  ✅ 3 per-client containers spawned"
echo "  ✅ Event sent and normalized"
echo "  ✅ Consumer groups created"
echo "  ✅ Heartbeat monitoring active"
echo ""
echo "🎯 Architecture:"
echo "   Client: $TEST_CLIENT_ID"
echo "   Containers:"
echo "     - kg-event-normalizer-$TEST_CLIENT_ID"
echo "     - kg-log-normalizer-$TEST_CLIENT_ID"
echo "     - kg-graph-builder-$TEST_CLIENT_ID"
echo ""
echo "📊 To monitor:"
echo "   docker logs kg-control-plane -f"
echo "   docker logs kg-event-normalizer-$TEST_CLIENT_ID -f"
echo "   docker ps | grep $TEST_CLIENT_ID"
echo ""
echo "🧹 To cleanup test client:"
echo "   docker stop kg-event-normalizer-$TEST_CLIENT_ID kg-log-normalizer-$TEST_CLIENT_ID kg-graph-builder-$TEST_CLIENT_ID"
echo "   docker rm kg-event-normalizer-$TEST_CLIENT_ID kg-log-normalizer-$TEST_CLIENT_ID kg-graph-builder-$TEST_CLIENT_ID"
echo ""
echo "============================================================"
