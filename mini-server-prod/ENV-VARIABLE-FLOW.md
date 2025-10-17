# Environment Variable Flow

## Complete Flow: Who Sets What?

You asked: **"Who sets the environment variables?"**

Answer: **You do, in the docker-compose.yml files!** Here's the complete flow:

---

## The Complete Chain

```
1. You write docker-compose.yml
   ↓
2. Docker reads docker-compose.yml
   ↓
3. Docker sets environment variables in container
   ↓
4. Go code reads environment variables
   ↓
5. Consumer group name is auto-generated
   ↓
6. Kafka auto-creates consumer group
```

---

## Detailed Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│ Step 1: YOU write docker-compose.yml                            │
│                                                                  │
│  graph-builder-prod-us-east-1:                                  │
│    environment:                                                  │
│      CLIENT_ID: prod-us-east-1          ← YOU SET THIS         │
│      KAFKA_GROUP: kg-builder            ← YOU SET THIS         │
│      KAFKA_BROKERS: kafka:9092          ← YOU SET THIS         │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         │ docker compose up
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 2: Docker reads docker-compose.yml                         │
│                                                                  │
│  Docker Compose parses YAML and creates container               │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         │ Container starts
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 3: Docker sets ENV vars in container                       │
│                                                                  │
│  Inside container (kg-graph-builder-prod-us-east-1):            │
│  $ env | grep CLIENT                                            │
│  CLIENT_ID=prod-us-east-1              ← DOCKER SET THIS       │
│  KAFKA_GROUP=kg-builder                ← DOCKER SET THIS       │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         │ Go program starts
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 4: Go code reads ENV vars (graph-builder.go:1333)          │
│                                                                  │
│  clientID := getenv("CLIENT_ID", "")   ← READS FROM OS.GETENV  │
│  // clientID = "prod-us-east-1"                                 │
│                                                                  │
│  group := getenv("KAFKA_GROUP", "kg-builder")                   │
│  // group = "kg-builder"                                        │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         │ String concatenation
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 5: Go code auto-generates consumer group name              │
│                                                                  │
│  if clientID != "" {                                            │
│      group = fmt.Sprintf("%s-%s", group, clientID)             │
│  }                                                              │
│  // group = "kg-builder-prod-us-east-1"  ← AUTO-GENERATED      │
│                                                                  │
│  log: "multi-tenant mode enabled:                              │
│        client_id=prod-us-east-1,                               │
│        consumer_group=kg-builder-prod-us-east-1"               │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         │ Connect to Kafka
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 6: Kafka receives connection request                       │
│                                                                  │
│  Consumer requests to join group: "kg-builder-prod-us-east-1"  │
│                                                                  │
│  Kafka checks: Does this consumer group exist?                  │
│  → No? CREATE IT AUTOMATICALLY  ← KAFKA AUTO-CREATES           │
│  → Yes? Add consumer to existing group                          │
│                                                                  │
│  Consumer group "kg-builder-prod-us-east-1" is now active ✅   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Code References

### 1. Docker-Compose Sets ENV (Line 35)

From [compose/docker-compose.multi-client.yml:35](../compose/docker-compose.multi-client.yml#L35):
```yaml
environment:
  CLIENT_ID: client-a        # ← YOU WRITE THIS
  KAFKA_GROUP: kg-builder    # ← YOU WRITE THIS
```

### 2. Go Code Reads ENV (Line 1333)

From [kg/graph-builder.go:1333-1337](../../kg/graph-builder.go#L1333-L1337):
```go
clientID := getenv("CLIENT_ID", "")
group := getenv("KAFKA_GROUP", "kg-builder")
if clientID != "" {
    group = fmt.Sprintf("%s-%s", group, clientID)
    log.Printf("multi-tenant mode enabled: client_id=%s, consumer_group=%s", clientID, group)
}
```

### 3. Go Code Creates Kafka Consumer (Line 1374)

From [kg/graph-builder.go:1374](../../kg/graph-builder.go#L1374):
```go
cg, err := sarama.NewConsumerGroup(brokers, group, cfg)
// ↑ This tells Kafka: "I want to join group 'kg-builder-prod-us-east-1'"
// Kafka auto-creates the group if it doesn't exist
```

---

## Three Ways to Set CLIENT_ID

### Method 1: Hardcoded in docker-compose.yml (Static)

```yaml
# compose/docker-compose.multi-client.yml
graph-builder-client-a:
  environment:
    CLIENT_ID: client-a      # ← Hardcoded
```

**Pros:** Simple, explicit
**Cons:** Must manually update for new clients

---

### Method 2: Reference .env file (Semi-Dynamic)

```yaml
# compose/docker-compose.yml
graph-builder:
  environment:
    CLIENT_ID: ${CLIENT_A_ID}  # ← Reads from .env file
```

```bash
# .env file
CLIENT_A_ID=prod-us-east-1
```

**Pros:** Centralized config
**Cons:** Still manual updates

---

### Method 3: Auto-Generated (Dynamic - Recommended)

```bash
# Run discovery script
./generate-multi-client-compose.sh

# This creates compose/docker-compose.multi-client.generated.yml with:
```

```yaml
graph-builder-prod-us-east-1:
  environment:
    CLIENT_ID: prod-us-east-1  # ← Auto-discovered from Kafka messages
```

**Pros:** Fully automatic, matches reality
**Cons:** Requires messages to exist first

---

## What You Control vs What's Automatic

| Layer | Who Sets It | How | Automatic? |
|-------|------------|-----|-----------|
| **CLIENT_ID in compose** | ✍️ You | Write in YAML or run script | Manual or scripted |
| **KAFKA_GROUP in compose** | ✍️ You | Write in YAML | Manual |
| **ENV vars in container** | 🐳 Docker | Reads from compose file | ✅ Automatic |
| **Consumer group name** | 🔧 Go code | Concatenates CLIENT_ID | ✅ Automatic |
| **Consumer group creation** | 📊 Kafka | First consumer connects | ✅ Automatic |

---

## Example: Adding a New Client

### Manual Approach

**Step 1:** You edit `docker-compose.multi-client.yml`:
```yaml
graph-builder-new-client:
  environment:
    CLIENT_ID: new-client-123   # ← YOU TYPE THIS
    KAFKA_GROUP: kg-builder
```

**Step 2:** Deploy:
```bash
docker compose -f compose/docker-compose.yml -f compose/docker-compose.multi-client.yml up -d
```

**Step 3:** Docker sets ENV → Go reads ENV → Consumer group auto-created

---

### Automatic Approach (Using Discovery Script)

**Step 1:** Client starts sending messages with `client_id: new-client-123`

**Step 2:** Run discovery script:
```bash
./generate-multi-client-compose.sh
```

**Step 3:** Script automatically writes:
```yaml
graph-builder-new-client-123:
  environment:
    CLIENT_ID: new-client-123   # ← SCRIPT WRITES THIS
    KAFKA_GROUP: kg-builder
```

**Step 4:** Deploy:
```bash
docker compose -f compose/docker-compose.yml -f compose/docker-compose.multi-client.generated.yml up -d
```

**Step 5:** Docker sets ENV → Go reads ENV → Consumer group auto-created

---

## Verification Commands

### Check ENV vars in running container

```bash
# Method 1: docker inspect
docker inspect kg-graph-builder-prod-us-east-1 | jq '.[0].Config.Env' | grep -E "CLIENT_ID|KAFKA_GROUP"

# Expected output:
# "CLIENT_ID=prod-us-east-1"
# "KAFKA_GROUP=kg-builder"

# Method 2: docker exec
docker exec kg-graph-builder-prod-us-east-1 env | grep -E "CLIENT_ID|KAFKA_GROUP"

# Expected output:
# CLIENT_ID=prod-us-east-1
# KAFKA_GROUP=kg-builder
```

### Check what consumer group was created

```bash
# Check graph-builder logs
docker logs kg-graph-builder-prod-us-east-1 | grep "multi-tenant"

# Expected output:
# multi-tenant mode enabled: client_id=prod-us-east-1, consumer_group=kg-builder-prod-us-east-1

# Check Kafka
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list | grep kg-builder

# Expected output:
# kg-builder-prod-us-east-1
```

---

## Common Mistakes

### ❌ Mistake 1: Forgetting to Set CLIENT_ID

```yaml
graph-builder:
  environment:
    KAFKA_GROUP: kg-builder
    # CLIENT_ID: ???  ← MISSING!
```

**Result:** Consumer group name = `kg-builder` (no client suffix)
**Problem:** Processes ALL messages, no filtering

---

### ❌ Mistake 2: Wrong CLIENT_ID Value

```yaml
# Docker compose
CLIENT_ID: prod-us-east-1

# But messages in Kafka have:
{"client_id": "production-us-east-1", ...}
```

**Result:** Graph-builder reads messages but filters them all out
**Problem:** No data processed, consumer group has 0 lag but no work done

---

### ❌ Mistake 3: Duplicate CLIENT_ID

```yaml
graph-builder-1:
  environment:
    CLIENT_ID: prod-us-east-1

graph-builder-2:
  environment:
    CLIENT_ID: prod-us-east-1  # ← DUPLICATE!
```

**Result:** Both join consumer group `kg-builder-prod-us-east-1`
**Problem:** Kafka splits partitions between them, inefficient

---

## Summary

### Who Sets Environment Variables?

1. **You write** the docker-compose.yml (manually or with script)
2. **Docker reads** the YAML and sets ENV in container
3. **Go code reads** the ENV using `os.Getenv()`
4. **Go code generates** consumer group name
5. **Kafka auto-creates** the consumer group

### What's Manual vs Automatic?

| Task | Who Does It | How |
|------|------------|-----|
| Write CLIENT_ID in YAML | 👤 You | Manual edit or script |
| Set ENV in container | 🐳 Docker | Automatic |
| Read ENV in Go | 🔧 Go code | Automatic |
| Generate consumer group name | 🔧 Go code | Automatic |
| Create consumer group | 📊 Kafka | Automatic |

### Key Takeaway

**You only need to set `CLIENT_ID` in docker-compose.yml.**

Everything else (consumer group naming, Kafka group creation) happens automatically!

---

## See Also

- [CONSUMER-GROUP-MANAGEMENT.md](./CONSUMER-GROUP-MANAGEMENT.md) - Consumer group lifecycle
- [DYNAMIC-CLIENT-DISCOVERY.md](./DYNAMIC-CLIENT-DISCOVERY.md) - Auto-generate configs
- [compose/README.md](./compose/README.md) - Docker compose usage
