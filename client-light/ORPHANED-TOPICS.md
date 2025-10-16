# Orphaned Kafka Topics

## Summary

~~The following topics existed in Kafka but were **not used** by the current architecture:~~

| Topic | Status | Action Taken | Date |
|-------|--------|--------------|------|
| `raw.events` | ✅ DELETED | Removed from Kafka and topic creation scripts | 2025-10-16 |
| `alerts.normalized` | ✅ DELETED | Removed from Kafka and topic creation scripts | 2025-10-16 |

**Both orphaned topics have been successfully cleaned up!**

## Details

### 1. `raw.events`

**Created**: In topic creation scripts ([mini-server-prod/scripts/create-topics.sh:51](../mini-server-prod/scripts/create-topics.sh#L51))

**Original Purpose**: In the old architecture, this was a unified topic combining raw Prometheus alerts and K8s events.

**Current Status**:
- ❌ **0 messages**
- ❌ **No producers** (Vector webhook no longer writes to it)
- ❌ **No consumers**
- ❌ **Not referenced** in current Helm charts

**Replaced By**:
- `raw.prom.alerts` - Prometheus/Alertmanager alerts
- `raw.k8s.events` - Kubernetes events

**Why Separated?**
- ✅ Different retention policies (alerts: 30d, events: 14d)
- ✅ Type-specific processing
- ✅ Clearer data lineage
- ✅ Easier to archive/replay specific types

**Migration**: Architecture changed from combined to type-specific raw topics.

### 2. `alerts.normalized`

**Created**: In topic creation scripts ([mini-server-prod/scripts/create-topics.sh:55](../mini-server-prod/scripts/create-topics.sh#L55))

**Original Intent**: Unknown - possibly planned for normalized Prometheus alerts only.

**Current Status**:
- ❌ **0 messages**
- ❌ **No producers**
- ❌ **No consumers**
- ❌ **Not referenced** in current codebase

**Replaced By**:
- `events.normalized` - Unified normalized topic for both K8s events AND Prometheus alerts
  - K8s events have `etype: "k8s.event"`
  - Prometheus alerts have `etype: "prom.alert"`

**Why Unified?**
- ✅ Simpler architecture (one topic vs two)
- ✅ Easier event correlation
- ✅ Single consumer subscription
- ✅ alerts-enricher filters by `etype === 'prom.alert'`

## Cleanup Actions

### Option 1: Delete the Topics (Recommended)

```bash
# Connect to mini-server
ssh mini-server

# Delete raw.events
docker exec kg-kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --delete \
  --topic raw.events

# Delete alerts.normalized
docker exec kg-kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --delete \
  --topic alerts.normalized
```

### Option 2: Update Topic Creation Scripts

Remove these lines from:

**[mini-server-prod/scripts/create-topics.sh](../mini-server-prod/scripts/create-topics.sh)**:
```bash
# Line 51 - Remove:
"raw.events:3:2592000000:Raw generic events (30 days)"

# Line 55 - Remove:
"alerts.normalized:3:2592000000:Normalized alerts (30 days)"
```

**Also update**:
- [scripts/kafka-init.sh:38](../scripts/kafka-init.sh#L38)
- [k8s/kafka.yaml:49](../k8s/kafka.yaml#L49)
- [saas/server_mini/scripts/kafka-init.sh:9](../saas/server_mini/scripts/kafka-init.sh#L9)
- [saas/server_mini/setup.sh:233](../saas/server_mini/setup.sh#L233)

## Current Correct Architecture

### Raw Layer (Type-Specific)
```
✅ raw.prom.alerts    - Prometheus/Alertmanager alerts (30d retention)
✅ raw.k8s.events     - Kubernetes events (14d retention)
✅ raw.k8s.logs       - Kubernetes logs (3d retention)
```

### Normalized Layer (Unified)
```
✅ events.normalized  - All events (K8s + Prom alerts) (14d retention)
✅ logs.normalized    - All logs (3d retention)
```

### Output/State Layer
```
✅ alerts.enriched       - Enriched Prometheus alerts (30d retention)
✅ state.k8s.resource    - K8s resource state (30d retention)
✅ state.k8s.topology    - K8s topology state (30d retention)
✅ state.prom.targets    - Prometheus targets state (30d retention)
✅ state.prom.rules      - Prometheus rules state (30d retention)
```

### DLQ Layer
```
✅ dlq.raw        - Dead letter queue for raw processing (7d retention)
✅ dlq.normalized - Dead letter queue for normalization (7d retention)
```

## Verification

After cleanup, verify topics:

```bash
# List all topics
ssh mini-server "docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list"

# Expected topics (no raw.events or alerts.normalized):
# - raw.prom.alerts
# - raw.k8s.events
# - raw.k8s.logs
# - events.normalized
# - logs.normalized
# - alerts.enriched
# - state.k8s.resource
# - state.k8s.topology
# - state.prom.targets
# - state.prom.rules
# - dlq.raw
# - dlq.normalized
```

## Impact Assessment

**Deleting these topics has ZERO impact** because:
- ✅ No producers write to them
- ✅ No consumers read from them
- ✅ They contain no data (0 messages)
- ✅ All functionality is handled by replacement topics

## References

- [TOPIC-ARCHITECTURE-ANALYSIS.md](./TOPIC-ARCHITECTURE-ANALYSIS.md) - Full architecture analysis
- [ALERTMANAGER-FIX.md](./ALERTMANAGER-FIX.md) - Recent fixes to alert flow