# Kafka Consumer Group Management

## TL;DR: ✅ **Fully Automatic - No Manual Steps Needed**

Consumer groups are **created automatically by Kafka** when the graph-builder connects. You don't need to create them manually.

---

## How It Works

### 1. Graph Builder Starts

When you deploy a graph-builder with `CLIENT_ID=prod-us-east-1`:

```yaml
environment:
  CLIENT_ID: prod-us-east-1
  KAFKA_GROUP: kg-builder
```

### 2. Consumer Group Name Auto-Generated

The graph-builder code automatically appends the client ID:

```go
// From graph-builder.go:1334-1337
clientID := getenv("CLIENT_ID", "")
group := getenv("KAFKA_GROUP", "kg-builder")
if clientID != "" {
    group = fmt.Sprintf("%s-%s", group, clientID)
    // group becomes: "kg-builder-prod-us-east-1"
}
```

### 3. Kafka Auto-Creates Consumer Group

When `sarama.NewConsumerGroup(brokers, group, cfg)` is called (line 1374):

```go
cg, err := sarama.NewConsumerGroup(brokers, group, cfg)
// Kafka automatically creates "kg-builder-prod-us-east-1" if it doesn't exist
```

### 4. Consumer Starts Reading

The consumer group is now active and reading from topics:
- `logs.normalized`
- `events.normalized`
- `state.k8s.resource`
- `state.k8s.topology`
- etc.

---

## Example Flow

```
┌─────────────────────────────────────────────────────────────┐
│ docker-compose.yml                                          │
│                                                             │
│ graph-builder-prod-us-east-1:                              │
│   environment:                                              │
│     CLIENT_ID: prod-us-east-1                              │
│     KAFKA_GROUP: kg-builder                                │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ Container starts
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ Graph Builder (Go code)                                     │
│                                                             │
│ 1. Read CLIENT_ID = "prod-us-east-1"                       │
│ 2. Read KAFKA_GROUP = "kg-builder"                         │
│ 3. Combine: group = "kg-builder-prod-us-east-1"           │
│ 4. Connect to Kafka with this group name                   │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ First connection
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ Kafka Broker                                                │
│                                                             │
│ 1. Receives connection from "kg-builder-prod-us-east-1"   │
│ 2. Checks if consumer group exists                         │
│ 3. Not found? CREATE IT AUTOMATICALLY ✅                   │
│ 4. Assign partitions to consumer                           │
│ 5. Start delivering messages                               │
└─────────────────────────────────────────────────────────────┘
                  │
                  ▼
         Messages flowing! 🎉
```

---

## Verification

### Check Consumer Groups (After Deploy)

```bash
# List all consumer groups
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list

# Expected output:
# kg-builder-prod-us-east-1
# kg-builder-staging-eu-west-1
# alerts-enricher
```

### Check Consumer Group Details

```bash
# View details of a specific consumer group
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group kg-builder-prod-us-east-1 \
  --describe

# Example output:
# GROUP                        TOPIC              PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
# kg-builder-prod-us-east-1   logs.normalized    0          1523            1523            0
# kg-builder-prod-us-east-1   events.normalized  0          89              89              0
# kg-builder-prod-us-east-1   state.k8s.resource 0          2341            2341            0
```

### Check Graph Builder Logs

```bash
# View startup logs
docker logs kg-graph-builder-prod-us-east-1 | grep "multi-tenant"

# Expected output:
# multi-tenant mode enabled: client_id=prod-us-east-1, consumer_group=kg-builder-prod-us-east-1
# consuming topics: [state.k8s.resource state.k8s.topology events.normalized logs.normalized ...]
```

---

## Multiple Clients Example

When you deploy 3 graph-builders:

```yaml
# Client A
graph-builder-prod-us-east-1:
  environment:
    CLIENT_ID: prod-us-east-1
    KAFKA_GROUP: kg-builder

# Client B
graph-builder-staging-eu-west-1:
  environment:
    CLIENT_ID: staging-eu-west-1
    KAFKA_GROUP: kg-builder

# Client C
graph-builder-dev-asia-1:
  environment:
    CLIENT_ID: dev-asia-1
    KAFKA_GROUP: kg-builder
```

Kafka automatically creates **3 consumer groups**:
1. `kg-builder-prod-us-east-1`
2. `kg-builder-staging-eu-west-1`
3. `kg-builder-dev-asia-1`

Each reads **all messages** from the topics but filters by `client_id` in the message body.

---

## What About Single-Tenant Mode?

If `CLIENT_ID` is empty (single-tenant):

```yaml
graph-builder:
  environment:
    CLIENT_ID: ""  # Empty
    KAFKA_GROUP: kg-builder
```

Consumer group name is just: `kg-builder`
- Processes ALL messages regardless of client_id

---

## Consumer Group Lifecycle

### Creation
- ✅ **Automatic** when first consumer connects
- No manual intervention needed

### Updates
- ✅ **Automatic** when consumers join/leave
- Kafka rebalances partitions automatically

### Deletion
- ⚠️ **Manual or Auto** (depends on Kafka config)
- By default: Kafka keeps consumer groups for 7 days after last consumer disconnects
- Can be deleted manually if needed

### Manual Deletion (Optional)

If you want to remove an old consumer group:

```bash
# Delete consumer group (only works if no consumers are active)
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group kg-builder-old-client \
  --delete
```

**When to delete manually:**
- Client is permanently retired
- Want to reset offsets (start from beginning)
- Clean up after testing

---

## Consumer Group vs Client ID

Two different concepts that both use "client_id":

| Concept | What It Is | Where Used | Purpose |
|---------|------------|------------|---------|
| **Kafka Consumer Group** | `kg-builder-prod-us-east-1` | Kafka broker | Track which messages this consumer has read |
| **Message client_id Field** | `"client_id": "prod-us-east-1"` | Message body | Identify which client sent this message |
| **Kafka Client ID** | `kg-builder-prod-us-east-1` | Kafka connection metadata | For monitoring/debugging connections |

### Flow:

```
1. Graph builder connects with:
   - Consumer Group: "kg-builder-prod-us-east-1"
   - Kafka Client ID: "kg-builder-prod-us-east-1"

2. Reads message:
   {
     "client_id": "prod-us-east-1",  ← Checks this field
     "pod_name": "nginx-abc",
     ...
   }

3. If message.client_id matches env.CLIENT_ID:
   → Process the message
   Else:
   → Skip the message
```

---

## Offset Management

Consumer groups track **offsets** (which messages have been read):

### Automatic Offset Commits

```go
// Kafka automatically commits offsets periodically
// You don't need to do anything
```

### Reset Offsets (If Needed)

If you want a consumer to re-process old messages:

```bash
# Reset to earliest (re-process all messages)
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group kg-builder-prod-us-east-1 \
  --reset-offsets \
  --to-earliest \
  --topic logs.normalized \
  --execute

# Reset to specific timestamp
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group kg-builder-prod-us-east-1 \
  --reset-offsets \
  --to-datetime 2025-01-15T00:00:00.000 \
  --all-topics \
  --execute
```

**Note:** Consumer must be stopped before resetting offsets.

---

## Troubleshooting

### Consumer Group Not Created

**Symptom:** No consumer group appears in Kafka

**Possible Causes:**
1. Graph builder failed to start
2. Kafka connection issues
3. Wrong Kafka broker address

**Check:**
```bash
# Check container status
docker ps | grep graph-builder

# Check logs for errors
docker logs kg-graph-builder-prod-us-east-1

# Look for connection errors
docker logs kg-graph-builder-prod-us-east-1 | grep -i "kafka\|error\|fail"
```

### Consumer Group Stuck/No Progress

**Symptom:** LAG keeps increasing

**Check:**
```bash
# Check consumer lag
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group kg-builder-prod-us-east-1 \
  --describe

# If LAG is increasing, check:
# 1. Is consumer running?
docker ps | grep graph-builder-prod-us-east-1

# 2. Any errors in logs?
docker logs kg-graph-builder-prod-us-east-1 --tail 100

# 3. Is Neo4j responding?
docker logs kg-neo4j --tail 50
```

### Wrong Consumer Group Name

**Symptom:** Consumer uses wrong group name

**Check environment:**
```bash
# Inspect container environment
docker inspect kg-graph-builder-prod-us-east-1 | jq '.[0].Config.Env' | grep -E "CLIENT_ID|KAFKA_GROUP"

# Expected:
# "CLIENT_ID=prod-us-east-1"
# "KAFKA_GROUP=kg-builder"
```

---

## Best Practices

### ✅ DO

- Let Kafka auto-create consumer groups
- Use meaningful CLIENT_ID values (e.g., `prod-us-east-1` not `client-a`)
- Monitor consumer lag regularly
- Check logs when deploying new clients

### ❌ DON'T

- Manually pre-create consumer groups (unnecessary)
- Share consumer groups between different clients
- Delete consumer groups while consumers are running
- Use the same CLIENT_ID for multiple graph-builders

---

## Summary

| Question | Answer |
|----------|--------|
| **Do I need to create consumer groups manually?** | ❌ No - automatic |
| **When are consumer groups created?** | ✅ When graph-builder first connects |
| **What if I add a new client?** | ✅ New consumer group created automatically |
| **What if I remove a client?** | ⚠️ Consumer group stays for 7 days, then auto-deleted |
| **Can I pre-create consumer groups?** | ⚠️ You can, but unnecessary |
| **Do I need to manage offsets?** | ❌ No - automatic (unless resetting) |

## Conclusion

**Everything is automatic!** 🎉

Just deploy your graph-builders with proper `CLIENT_ID` values, and Kafka handles all the consumer group management for you.

No manual steps required.

---

## See Also

- [MULTI-TENANT-SETUP.md](./MULTI-TENANT-SETUP.md) - Multi-tenant architecture
- [DYNAMIC-CLIENT-DISCOVERY.md](./DYNAMIC-CLIENT-DISCOVERY.md) - Auto-discovery
- [SERVICES-EXPLAINED.md](./SERVICES-EXPLAINED.md) - What each service does
