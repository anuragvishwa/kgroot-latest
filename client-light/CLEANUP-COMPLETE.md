# Kafka Topics Cleanup - Complete ✅

**Date**: 2025-10-16
**Status**: Successfully completed

## Summary

Removed 2 orphaned Kafka topics that were not used in the current architecture.

## Actions Taken

### 1. Deleted Topics from Kafka

```bash
# Deleted raw.events
ssh mini-server "docker exec kg-kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 --delete --topic raw.events"

# Deleted alerts.normalized
ssh mini-server "docker exec kg-kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 --delete --topic alerts.normalized"
```

### 2. Updated Topic Creation Scripts

**Files Modified**:
- [mini-server-prod/scripts/create-topics.sh](../mini-server-prod/scripts/create-topics.sh)
  - Removed `raw.events` definition (line 51)
  - Removed `alerts.normalized` definition (line 55)
  - Added missing `state.prom.targets` and `state.prom.rules`

- [scripts/kafka-init.sh](../scripts/kafka-init.sh)
  - Removed `raw.events` (line 38)
  - Removed `alerts.normalized` (line 41)

### 3. Verification

**Before Cleanup** (15 topics):
```
__consumer_offsets
alerts.enriched
alerts.normalized      ← DELETED
dlq.normalized
dlq.raw
events.normalized
graph.commands
logs.normalized
raw.events             ← DELETED
raw.k8s.events
raw.k8s.logs
raw.prom.alerts
state.k8s.resource
state.k8s.topology
state.prom.rules
state.prom.targets
```

**After Cleanup** (13 topics):
```
__consumer_offsets
alerts.enriched
dlq.normalized
dlq.raw
events.normalized
graph.commands
logs.normalized
raw.k8s.events
raw.k8s.logs
raw.prom.alerts
state.k8s.resource
state.k8s.topology
state.prom.rules
state.prom.targets
```

## Why These Topics Were Removed

### `raw.events` ❌
- **Reason**: Replaced by type-specific topics
- **Old use**: Combined raw events (Prometheus + K8s)
- **New approach**: Separate topics for better retention policies
  - `raw.prom.alerts` (30d retention)
  - `raw.k8s.events` (14d retention)

### `alerts.normalized` ❌
- **Reason**: Never implemented; unified approach used instead
- **Current approach**: `events.normalized` handles both:
  - K8s events (`etype: "k8s.event"`)
  - Prometheus alerts (`etype: "prom.alert"`)
- **Benefits**: Simpler architecture, easier event correlation

## Current Clean Architecture

### Layer 1: Raw Topics (Type-Specific)
```
✅ raw.prom.alerts    (30d, 3p) - Prometheus alerts
✅ raw.k8s.events     (14d, 3p) - Kubernetes events
✅ raw.k8s.logs       (3d, 6p)  - Container logs
```

### Layer 2: Normalized Topics (Unified by Type)
```
✅ events.normalized  (14d, 3p) - All events (K8s + Prom)
✅ logs.normalized    (3d, 6p)  - All logs
```

### Layer 3: Output/State Topics
```
✅ alerts.enriched       (30d, 3p) - Enriched alerts
✅ state.k8s.resource    (30d, 3p) - Resource state
✅ state.k8s.topology    (30d, 3p) - Topology state
✅ state.prom.targets    (30d, 3p) - Prom targets
✅ state.prom.rules      (30d, 3p) - Prom rules
✅ graph.commands        (365d, 3p) - Graph commands
```

### Layer 4: Dead Letter Queues
```
✅ dlq.raw            (7d, 3p) - Failed raw processing
✅ dlq.normalized     (7d, 3p) - Failed normalization
```

## Impact Assessment

**Zero impact** because:
- ✅ Both topics had 0 messages
- ✅ No producers were writing to them
- ✅ No consumers were reading from them
- ✅ Not referenced in any current configuration
- ✅ All functionality handled by replacement topics

## Documentation Updated

- ✅ [TOPIC-ARCHITECTURE-ANALYSIS.md](./TOPIC-ARCHITECTURE-ANALYSIS.md)
- ✅ [TOPIC-SUMMARY.md](./TOPIC-SUMMARY.md)
- ✅ [ORPHANED-TOPICS.md](./ORPHANED-TOPICS.md)
- ✅ [ALERTMANAGER-FIX.md](./ALERTMANAGER-FIX.md)

## Monitoring

To verify topics after cleanup:

```bash
# List all topics (should show 13 + __consumer_offsets)
ssh mini-server "docker exec kg-kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 --list"

# Check no orphaned topics exist
ssh mini-server "docker exec kg-kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 --list" | grep -E "raw.events|alerts.normalized"
# Expected: No output
```

## Next Steps

No action required! The architecture is now clean and optimized:

1. ✅ All active topics are being used
2. ✅ No orphaned topics remaining
3. ✅ Topic creation scripts updated
4. ✅ Documentation reflects current state
5. ✅ Alertmanager properly configured (from earlier fix)

## References

- [Previous Issue: raw.prom.alerts not receiving data](./ALERTMANAGER-FIX.md) - Fixed by configuring Alertmanager webhook
- [Architecture Analysis](./TOPIC-ARCHITECTURE-ANALYSIS.md) - Full topic architecture
- [Topic Summary](./TOPIC-SUMMARY.md) - Visual overview