# Resource Usage & Consumer Cleanup Guide

## Overview

This guide covers graph-builder resource consumption, Kafka consumer management, and cleanup procedures for multi-tenant deployments.

---

## Graph-Builder Resource Usage

### Current Metrics (per instance)

Based on production measurements:

```
CONTAINER          CPU %     MEM USAGE / LIMIT     NET I/O
kg-graph-builder   1.69%     9.488MiB / 7.638GiB   21.7MB / 29.3MB
```

**Resource Consumption:**
- **CPU**: ~1.7% (very low - efficient Go application)
- **Memory**: ~9.5 MB (minimal footprint)
- **Network**: 21.7 MB received, 29.3 MB sent (18 minutes runtime)

### Scaling Considerations

**Per Graph-Builder Instance:**
- CPU: < 2% (single core)
- Memory: ~10-20 MB baseline + data processing
- Network: Depends on message volume

**For 10 Clusters (10 graph-builder instances):**
- Total CPU: ~17-20% (less than 1 full core)
- Total Memory: ~100-200 MB
- Very cost-effective for multi-tenant deployments

**Resource Limits (Recommended):**
```yaml
# docker-compose.yml
kg-graph-builder-af-10:
  image: anuragvishwa/kg-graph-builder:1.0.20
  deploy:
    resources:
      limits:
        cpus: '0.5'      # Half a CPU core
        memory: 256M     # 256 MB memory
      reservations:
        cpus: '0.1'      # Reserve 10% of a core
        memory: 64M      # Reserve 64 MB
```

---

## Graph-Builders are Kafka Consumers

### What is a Kafka Consumer?

Graph-builders are **Kafka consumer applications** that:
1. Connect to Kafka brokers
2. Join a consumer group (e.g., `kg-builder-af-10`)
3. Subscribe to multiple topics
4. Read messages continuously
5. Process and store data in Neo4j

### Consumer Group Details

**Active Consumer Group: `kg-builder-af-10`**

| Topic | Partitions | Messages Consumed | Lag | Status |
|-------|------------|-------------------|-----|--------|
| events.normalized | 3 | 4,517 | 0 | ✅ Caught up |
| logs.normalized | 3 | 801,993 | 4 | ✅ Nearly caught up |
| state.k8s.resource | 3 | 270,892 | 12 | ✅ Nearly caught up |
| state.k8s.topology | 3 | 225,412 | 26 | ✅ Active processing |
| state.prom.targets | 3 | 55,312 | 0 | ✅ Caught up |
| state.prom.rules | 3 | 0 | 0 | ✅ No messages |
| graph.commands | 3 | 0 | 0 | ✅ No messages |

**Key Metrics:**
- **Total Messages Processed**: ~1.3 million
- **Current Lag**: 42 messages (negligible)
- **Consumer Status**: STABLE ✅
- **Processing Rate**: Real-time (lag < 50)

### Consumer Properties

```go
// Each graph-builder creates a consumer group
KAFKA_GROUP: kg-builder-af-10  // Unique per cluster
CLIENT_ID: af-10                // Tenant identifier

// Consumer subscribes to all relevant topics
Topics: [
  "state.k8s.resource",
  "state.k8s.topology",
  "events.normalized",
  "logs.normalized",
  "state.prom.targets",
  "state.prom.rules",
  "graph.commands"
]
```

---

## Consumer Cleanup

### Why Consumer Groups Accumulate

When you:
1. Restart graph-builder with different `KAFKA_GROUP`
2. Test with different `CLIENT_ID` values
3. Redeploy with new configurations

**Result:** Old consumer groups remain in Kafka metadata, even though no consumer is active.

### Identifying Unused Consumers

**Before Cleanup:**
```
kg-builder-af-10        ← Active (STABLE)
kg-builder-af-4         ← Unused (EMPTY)
kg-builder-af-5         ← Unused (EMPTY)
kg-builder-af-6         ← Unused (EMPTY)
kg-builder-af-7         ← Unused (EMPTY)
kg-builder              ← Unused (EMPTY)
alerts-enricher-a1-v2   ← Old version (EMPTY)
alerts-enricher-a2-v2   ← Old version (EMPTY)
... (14 old enricher groups)
```

**Indicators of Unused Consumers:**
- State: `EMPTY` (no active members)
- Lag: Large numbers (not being consumed)
- Group name doesn't match current deployment

### Cleanup Commands

#### 1. List All Consumer Groups
```bash
ssh mini-server 'docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list'
```

#### 2. Check Consumer Group Status
```bash
# Check specific group
ssh mini-server 'docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group kg-builder-af-10'
```

#### 3. Delete Unused Consumer Groups

**Delete Single Group:**
```bash
ssh mini-server 'docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --delete \
  --group kg-builder-af-4'
```

**Bulk Delete (Bash Loop):**
```bash
# Delete all old kg-builder groups
for group in kg-builder kg-builder-af-4 kg-builder-af-5 kg-builder-af-6 kg-builder-af-7; do
  ssh mini-server "docker exec kg-kafka kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --delete \
    --group $group"
done

# Delete all old alerts-enricher groups
for i in 1 2 3 4 5 6 7; do
  ssh mini-server "docker exec kg-kafka kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --delete \
    --group alerts-enricher-af-${i}-v2"
done
```

#### 4. Verify Cleanup
```bash
ssh mini-server 'docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list'

# Should only show active consumers:
# kg-builder-af-10
```

### Cleanup Script

Create `cleanup-consumers.sh`:

```bash
#!/bin/bash
# cleanup-consumers.sh - Clean up unused Kafka consumer groups

KAFKA_HOST="mini-server"
KAFKA_CONTAINER="kg-kafka"
BOOTSTRAP_SERVER="localhost:9092"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Fetching all consumer groups..."
GROUPS=$(ssh $KAFKA_HOST "docker exec $KAFKA_CONTAINER kafka-consumer-groups.sh \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --list" 2>/dev/null)

echo "📋 Current consumer groups:"
echo "$GROUPS"
echo ""

# Active groups to keep
KEEP_GROUPS=("kg-builder-af-10")

echo "🗑️  Consumer groups to delete:"
TO_DELETE=()
while IFS= read -r group; do
  # Check if group should be kept
  KEEP=0
  for keep_group in "${KEEP_GROUPS[@]}"; do
    if [ "$group" == "$keep_group" ]; then
      KEEP=1
      break
    fi
  done

  if [ $KEEP -eq 0 ]; then
    echo "  - $group"
    TO_DELETE+=("$group")
  fi
done <<< "$GROUPS"

if [ ${#TO_DELETE[@]} -eq 0 ]; then
  echo -e "${GREEN}✅ No consumer groups to delete!${NC}"
  exit 0
fi

echo ""
read -p "Delete ${#TO_DELETE[@]} consumer groups? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
  for group in "${TO_DELETE[@]}"; do
    echo -n "Deleting $group... "
    RESULT=$(ssh $KAFKA_HOST "docker exec $KAFKA_CONTAINER kafka-consumer-groups.sh \
      --bootstrap-server $BOOTSTRAP_SERVER \
      --delete \
      --group $group" 2>&1)

    if echo "$RESULT" | grep -q "successful"; then
      echo -e "${GREEN}✅${NC}"
    else
      echo -e "${RED}❌${NC}"
      echo "$RESULT"
    fi
  done

  echo ""
  echo -e "${GREEN}🎉 Cleanup complete!${NC}"
  echo ""
  echo "Remaining consumer groups:"
  ssh $KAFKA_HOST "docker exec $KAFKA_CONTAINER kafka-consumer-groups.sh \
    --bootstrap-server $BOOTSTRAP_SERVER \
    --list"
else
  echo "Cleanup cancelled."
fi
```

**Usage:**
```bash
chmod +x cleanup-consumers.sh
./cleanup-consumers.sh
```

---

## Multi-Tenant Consumer Management

### Best Practices

#### 1. **Consistent Consumer Group Naming**

Use the pattern: `{service}-{client-id}`

```yaml
# Good ✅
kg-graph-builder-af-10:
  environment:
    CLIENT_ID: "af-10"
    KAFKA_GROUP: "kg-builder-af-10"  # Matches client_id

kg-graph-builder-af-11:
  environment:
    CLIENT_ID: "af-11"
    KAFKA_GROUP: "kg-builder-af-11"  # Matches client_id
```

```yaml
# Bad ❌
kg-graph-builder-af-10:
  environment:
    CLIENT_ID: "af-10"
    KAFKA_GROUP: "kg-builder"  # Generic - will conflict!
```

#### 2. **One Consumer Group Per Cluster**

Each graph-builder should have its own consumer group:

```
Cluster af-10 → Consumer Group: kg-builder-af-10
Cluster af-11 → Consumer Group: kg-builder-af-11
Cluster af-12 → Consumer Group: kg-builder-af-12
```

**Why?**
- Independent offset tracking per cluster
- No interference between clusters
- Can pause/restart individual graph-builders
- Clear monitoring per cluster

#### 3. **Consumer Group Lifecycle**

**When to Create:**
- New cluster deployed
- New tenant onboarded

**When to Delete:**
- Cluster decommissioned
- Tenant offboarded
- Testing/development completed

**Never Delete:**
- Active consumer groups (STATE = STABLE)
- Groups with recent activity

### Monitoring Consumer Health

#### Check Consumer Lag

```bash
# Get lag for specific consumer
ssh mini-server 'docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group kg-builder-af-10'
```

**Healthy Consumer:**
- Lag: < 1000 (ideally < 100)
- State: STABLE
- Current offset close to log-end-offset

**Unhealthy Consumer:**
- Lag: Growing over time
- State: EMPTY (no active members)
- Current offset far behind log-end-offset

#### Monitor Processing Rate

```bash
# Check multiple times to see if lag is decreasing
ssh mini-server 'docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group kg-builder-af-10' > before.txt

# Wait 30 seconds
sleep 30

ssh mini-server 'docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group kg-builder-af-10' > after.txt

# Compare
diff before.txt after.txt
```

---

## Resource Optimization

### Scaling Guidelines

**Single Graph-Builder:**
- Handles: 1 Kubernetes cluster
- CPU: < 2%
- Memory: ~10-20 MB
- Messages: 1-2 million/day

**10 Graph-Builders (10 clusters):**
- Total CPU: ~20%
- Total Memory: ~100-200 MB
- Messages: 10-20 million/day
- Cost: Very low (< 1 full CPU core)

**100 Graph-Builders (100 clusters):**
- Total CPU: ~200% (2 cores)
- Total Memory: ~1-2 GB
- Messages: 100-200 million/day
- Cost: Still very reasonable

### Optimization Tips

#### 1. **Vertical Scaling (Resource Limits)**

```yaml
# High-volume cluster
kg-graph-builder-af-10:
  deploy:
    resources:
      limits:
        cpus: '1.0'      # Full CPU core
        memory: 512M     # 512 MB memory
```

#### 2. **Horizontal Scaling (Multiple Consumers)**

Kafka partitions allow parallel processing:

```yaml
# Topic has 6 partitions
# Can run 2 graph-builders in same consumer group
kg-graph-builder-af-10-1:
  environment:
    KAFKA_GROUP: "kg-builder-af-10"  # Same group

kg-graph-builder-af-10-2:
  environment:
    KAFKA_GROUP: "kg-builder-af-10"  # Same group
```

**Result:** Each consumer processes 3 partitions (6 ÷ 2 = 3)

#### 3. **Topic Configuration**

```bash
# Increase partitions for high-volume topics
ssh mini-server 'docker exec kg-kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --topic events.normalized \
  --partitions 6'
```

More partitions = More parallelization = Better throughput

---

## Troubleshooting

### Consumer Group Stuck

**Symptom:** Lag increasing, consumer shows EMPTY

**Solution:**
```bash
# 1. Check if graph-builder is running
docker ps | grep graph-builder

# 2. Check logs for errors
docker logs kg-graph-builder --tail=50

# 3. Restart graph-builder
docker restart kg-graph-builder

# 4. If still stuck, reset offsets to latest
ssh mini-server 'docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group kg-builder-af-10 \
  --reset-offsets \
  --to-latest \
  --all-topics \
  --execute'
```

### High Memory Usage

**Symptom:** Graph-builder using > 500 MB memory

**Possible Causes:**
1. Large batch sizes
2. Memory leak
3. Too many concurrent messages

**Solution:**
```bash
# Restart graph-builder
docker restart kg-graph-builder

# Monitor memory over time
watch -n 5 'docker stats kg-graph-builder --no-stream'
```

### Consumer Lag Growing

**Symptom:** Lag increasing faster than consumption

**Solutions:**

1. **Scale horizontally** (add more consumer instances)
2. **Increase partitions** (better parallelization)
3. **Optimize Neo4j** (slow writes causing bottleneck)
4. **Check network** (slow Kafka connection)

---

## Summary

### Resource Usage (Actual Production Data)

**Single Graph-Builder Instance:**
- CPU: 1.7% (very efficient)
- Memory: 9.5 MB (minimal footprint)
- Network: ~50 MB total (18 minutes)
- Messages: 1.3 million processed
- Lag: < 50 (real-time)

### Consumer Management

**Active Consumers:**
- ✅ `kg-builder-af-10` - Cluster af-10 (STABLE)

**Cleanup Results:**
- ❌ Deleted 20 unused consumer groups
- 💾 Freed Kafka metadata space
- 🧹 Clean, organized consumer list

### Multi-Tenant Efficiency

**10 Clusters:**
- 10 graph-builders × 1.7% CPU = 17% CPU
- 10 graph-builders × 10 MB = 100 MB memory
- **Total: < 1 full CPU core for 10 clusters!**

**Very cost-effective for SaaS deployments!** 🚀

---

## Related Documentation

- [MULTI-TENANT-ARCHITECTURE.md](MULTI-TENANT-ARCHITECTURE.md) - Multi-tenant design
- [INSTALLATION.md](INSTALLATION.md) - Installation guide
- [cleanup-consumers.sh](cleanup-consumers.sh) - Automated cleanup script

---

## License

Apache 2.0