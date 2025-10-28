# Quick Start Guide - Control Plane V2

## 🚀 Start Server (5 minutes)

```bash
cd ~/kgroot_latest/mini-server-prod

# Start all services
./START-SERVER.sh

# Test control plane
./TEST-CONTROL-PLANE-V2.sh
```

**Expected result:**
- ✅ 13 Kafka topics created
- ✅ Control plane running
- ✅ Test client registered
- ✅ 3 per-client containers spawned automatically

---

## 🔍 Monitor Control Plane

```bash
# Watch control plane activity
docker logs kg-control-plane -f

# Expected output:
# 📋 New client registered: test-client-001
# 🚀 Spawning containers for client: test-client-001
#    ✅ Spawned event normalizer: kg-event-normalizer-test-client-001
#    ✅ Spawned log normalizer: kg-log-normalizer-test-client-001
#    ✅ Spawned graph builder: kg-graph-builder-test-client-001
```

---

## 📊 Check Spawned Containers

```bash
# List all client containers
docker ps | grep "kg-event-normalizer\|kg-log-normalizer\|kg-graph-builder"

# Expected output:
# kg-event-normalizer-test-client-001
# kg-log-normalizer-test-client-001
# kg-graph-builder-test-client-001
```

---

## 🧪 Manual Testing

### Register a New Client

```bash
# Send registration message
docker exec kg-kafka kafka-console-producer.sh \
  --bootstrap-server localhost:29092 \
  --topic cluster.registry \
  --property "parse.key=true" \
  --property "key.separator=:"

# Input (paste this):
my-client-001:{"client_id":"my-client-001","cluster_name":"production","k8s_version":"1.28"}

# Press Ctrl+D to exit

# Wait 10 seconds, then check:
docker ps | grep my-client-001

# Should see 3 containers spawned!
```

### Send Test Event

```bash
# Send event with client-specific key
docker exec kg-kafka kafka-console-producer.sh \
  --bootstrap-server localhost:29092 \
  --topic raw.k8s.events \
  --property "parse.key=true" \
  --property "key.separator=|"

# Input (paste this):
my-client-001::event::test123|{"event_id":"evt-123","reason":"OOMKilled","message":"Test OOM event","type":"Warning","metadata":{"uid":"test123","creationTimestamp":"2025-01-20T10:00:00Z"},"involvedObject":{"kind":"Pod","name":"test-pod","namespace":"default"}}

# Press Ctrl+D to exit

# Check if normalized:
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:29092 \
  --topic events.normalized \
  --from-beginning \
  --max-messages 1 \
  --property print.key=true

# Should see:
# my-client-001::evt-123    {"event_id":"evt-123",...}
# (Note: NO client_id in payload!)
```

### Send Heartbeat

```bash
# Send heartbeat to keep client alive
docker exec kg-kafka kafka-console-producer.sh \
  --bootstrap-server localhost:29092 \
  --topic cluster.heartbeat \
  --property "parse.key=true" \
  --property "key.separator=:"

# Input:
my-client-001:{"client_id":"my-client-001","timestamp":"2025-01-20T10:00:00Z"}

# Press Ctrl+D
```

---

## 🧹 Cleanup Test Client

```bash
# Stop sending heartbeats and wait 2 minutes
# Control plane will automatically cleanup

# Or manually stop containers:
docker stop kg-event-normalizer-my-client-001 \
           kg-log-normalizer-my-client-001 \
           kg-graph-builder-my-client-001

docker rm kg-event-normalizer-my-client-001 \
         kg-log-normalizer-my-client-001 \
         kg-graph-builder-my-client-001
```

---

## 📋 Verify Clean Architecture

### Check Message Payloads (NO client_id)

```bash
# Check raw events
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:29092 \
  --topic raw.k8s.events \
  --from-beginning \
  --max-messages 1

# Should see: {"event_id":"evt-123",...}  ← NO "client_id" field

# Check normalized events
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:29092 \
  --topic events.normalized \
  --from-beginning \
  --max-messages 1

# Should see: {"event_id":"evt-123",...}  ← Still NO "client_id" field
```

### Check Consumer Groups

```bash
# List consumer groups (should see one per client)
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:29092 \
  --list | grep "my-client-001"

# Expected:
# event-normalizer-my-client-001
# log-normalizer-my-client-001
# graph-builder-my-client-001

# Check consumer lag
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:29092 \
  --describe --group event-normalizer-my-client-001
```

---

## 🎯 Key Differences from V1

| V1 (Old) | V2 (New) |
|----------|----------|
| client_id in EVERY message | client_id ONLY in Kafka key |
| Single normalizer for all clients | Per-client normalizers |
| Manual container management | Automatic spawning/cleanup |
| Filter messages in code | Kafka routing by consumer group |

---

## 🐛 Troubleshooting

### Containers not spawning

```bash
# Check control plane logs
docker logs kg-control-plane --tail 50

# Check if Docker socket mounted correctly
docker exec kg-control-plane ls -la /var/run/docker.sock
```

### Events not normalizing

```bash
# Check if normalizer container is running
docker ps | grep kg-event-normalizer-{client-id}

# Check normalizer logs
docker logs kg-event-normalizer-{client-id} --tail 50

# Check if event has correct key format
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:29092 \
  --topic raw.k8s.events \
  --from-beginning \
  --property print.key=true \
  --max-messages 5

# Key format must be: {client-id}::{entity-type}::{entity-id}
```

### Stale client not cleaned up

```bash
# Check last heartbeat
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:29092 \
  --topic cluster.heartbeat \
  --from-beginning | grep "{client-id}"

# Check control plane threshold
docker logs kg-control-plane | grep "stale"

# Default: 2 minutes no heartbeat → cleanup triggered
```

---

## 📚 Full Documentation

- **[CONTROL-PLANE-ARCHITECTURE.md](./CONTROL-PLANE-ARCHITECTURE.md)** - Complete architecture
- **[REFACTORING-SUMMARY.md](./REFACTORING-SUMMARY.md)** - V1 → V2 changes
- **[13-TOPIC-ARCHITECTURE.md](./13-TOPIC-ARCHITECTURE.md)** - Overall system

---

**🎉 Control Plane V2 is ready! Automatic multi-client management with clean architecture.**
