# Topic Architecture Analysis: alerts.normalized vs events.normalized

## Question
Do we need `alerts.normalized` if `events.normalized` already exists?

## Current Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Prometheus/Alertmanager    │    Kubernetes Events                  │
│           ↓                  │            ↓                          │
│    Vector Webhook            │    event-exporter                     │
│           ↓                  │            ↓                          │
├─────────────────────────────────────────────────────────────────────┤
│                         RAW TOPICS                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   raw.prom.alerts           │    raw.k8s.events                     │
│   (raw Alertmanager         │    (raw K8s events)                   │
│    payloads)                │                                        │
│           ↓                  │            ↓                          │
│    Vector transform          │    event-exporter transform           │
│    (normalize)               │    (normalize)                        │
│           ↓                  │            ↓                          │
├─────────────────────────────────────────────────────────────────────┤
│                    UNIFIED NORMALIZED TOPIC                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                    events.normalized                                 │
│              (Both alert + event types)                              │
│                                                                      │
│  • K8s events: etype = "k8s.event"                                  │
│  • Prometheus alerts: etype = "prom.alert"                          │
│                                                                      │
│                         ↓                                            │
│                  alerts-enricher                                     │
│           (filters: etype == 'prom.alert')                          │
│                         ↓                                            │
├─────────────────────────────────────────────────────────────────────┤
│                      OUTPUT TOPIC                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                   alerts.enriched                                    │
│           (enriched with K8s context)                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Topic Analysis

### ✅ **events.normalized** (EXISTS & IN USE)
- **Purpose**: Unified topic for ALL normalized events
- **Producers**:
  - Vector (normalized Prometheus alerts with `etype: "prom.alert"`)
  - event-exporter (normalized K8s events)
- **Consumers**:
  - alerts-enricher (filters on `etype === 'prom.alert'`)
- **Content**: Mixed event types, distinguished by `etype` field
- **Data**: ✅ Active (172 messages in consumer group offset)

### ❌ **alerts.normalized** (DOES NOT EXIST)
- **Current Status**: Topic does not exist and has 0 messages
- **Not referenced** in any configuration
- **Not produced** by any component
- **Not consumed** by any component

### ✅ **alerts.enriched** (OUTPUT TOPIC)
- **Purpose**: Final enriched alerts with K8s context
- **Producer**: alerts-enricher
- **Consumers**: Downstream systems (UI, notifications, etc.)

## Code Evidence

### alerts-enricher (index.ts:82-85)
```typescript
// Only enrich Prometheus alerts
if (event.etype !== 'prom.alert') {
  return null;
}
```

The enricher **filters `events.normalized`** for `prom.alert` events only.

### Current Configuration
```yaml
INPUT_TOPIC: events.normalized        # Single unified input
OUTPUT_TOPIC: alerts.enriched          # Enriched output
STATE_RESOURCE_TOPIC: state.k8s.resource
STATE_TOPOLOGY_TOPIC: state.k8s.topology
```

## Answer: No, `alerts.normalized` is NOT needed

### Reasons:

1. **Already Unified**: `events.normalized` serves as the single source of truth for ALL normalized events (both K8s events and Prometheus alerts)

2. **Type Discrimination**: Events are distinguished by the `etype` field:
   - `etype: "prom.alert"` → Prometheus alerts
   - `etype: "k8s.event"` → Kubernetes events (implied)

3. **Efficient Filtering**: The enricher uses `etype === 'prom.alert'` to process only alert events from the unified stream

4. **Simpler Architecture**:
   - ✅ One normalized topic instead of two
   - ✅ Easier to correlate events and alerts
   - ✅ Single consumer subscription
   - ✅ Reduced operational complexity

5. **Current Implementation**: The system is ALREADY working this way - there is no `alerts.normalized` topic

## Benefits of Current Unified Approach

### 🎯 **Simplified Data Flow**
```
Multiple Sources → Raw Topics → Single Normalized Topic → Enricher → Output
```

### 🎯 **Event Correlation**
Having both events and alerts in the same topic makes it easier to:
- Correlate K8s events with Prometheus alerts
- Analyze event sequences
- Build timelines

### 🎯 **Resource Efficiency**
- Single consumer group
- Single Kafka topic to manage
- Reduced broker load

### 🎯 **Flexibility**
Future consumers can:
- Subscribe to `events.normalized` once
- Filter by `etype` for specific event types
- Process all events together for correlation

## If You DID Want Separate Topics

If there were specific reasons to separate (e.g., different retention policies, compliance), you could:

```yaml
# Option A: Separate normalized topics
events.normalized    # K8s events only
alerts.normalized    # Prometheus alerts only

# Option B: Keep unified, add filtered views
events.normalized    # All events (current approach) ✅
  ├─ alerts.enricher filters on etype='prom.alert'
  └─ event.processor filters on etype='k8s.event'
```

**But there's no current need for this complexity.**

## Recommendation

✅ **Keep the current architecture**: Use `events.normalized` as the unified topic for all normalized events.

### Configuration Summary
```
Raw Layer:
  - raw.prom.alerts      (Prometheus alerts)
  - raw.k8s.events       (K8s events)
  - raw.k8s.logs         (K8s logs)

Normalized Layer:
  - events.normalized    (All events - unified)
  - logs.normalized      (All logs)

Output Layer:
  - alerts.enriched      (Enriched Prometheus alerts)
```

### Notes for Helm Chart
The `values.yaml` should clarify that:
- `alertReceiver.env.KAFKA_TOPIC` (default: `alerts.raw`) - NOT USED
- The alert receiver uses `INPUT_TOPIC` → `events.normalized`
- There is NO `alerts.normalized` topic

Consider updating the ConfigMap template to remove confusing references:
- Line 35: `$topicAlertsRaw` is labeled "alerts.raw" but this is misleading
- Should document that alerts flow through `events.normalized`

## What About `raw.events`?

### Status: **ORPHANED TOPIC** ⚠️

The `raw.events` topic **exists but is not used** in the current architecture.

### Historical Context

In the **old architecture** (see [k8s/vector-configmap.yaml](../k8s/vector-configmap.yaml)):

```toml
# Old Vector config had a unified raw.events sink
[sinks.raw_events]
type              = "kafka"
inputs            = ["raw_prom_enrich", "raw_k8s_enrich"]  # Combined!
bootstrap_servers = "${KAFKA_BOOTSTRAP}"
topic             = "raw.events"
key_field         = "kafka_key"
```

**Purpose**: Combine ALL raw events (K8s + Prometheus) into a single topic with stable Kafka keys.

### Current Architecture

The **new client-light Helm chart** uses **separate raw topics**:

```
✅ raw.prom.alerts    (Prometheus alerts only)
✅ raw.k8s.events     (K8s events only)
✅ raw.k8s.logs       (K8s logs only)
```

**No `raw.events` sink is configured** in the Vector DaemonSet template.

### Why the Change?

#### Old Approach (Combined `raw.events`)
```
Alertmanager → Vector → raw.events (combined) → ?
K8s Events → Vector → raw.events (combined) → ?
```
- ❌ Mixed event types in one topic
- ❌ Harder to set different retention policies
- ❌ Consumers must filter by `etype`

#### New Approach (Separate Raw Topics)
```
Alertmanager → Vector → raw.prom.alerts → Archive/Audit
K8s Events → event-exporter → raw.k8s.events → Archive/Audit
```
- ✅ Type-specific raw topics
- ✅ Independent retention policies (alerts: 30d, events: 14d)
- ✅ Clearer data lineage
- ✅ Easier to archive/replay specific types

### Recommendation: Delete `raw.events` Topic

Since the topic:
- ❌ Has **0 messages**
- ❌ Has **no producers**
- ❌ Has **no consumers**
- ❌ Is **not referenced** in any current configuration
- ❌ Was only used in the old architecture

**Action**: Delete the orphaned topic:

```bash
ssh mini-server "cd /home/ubuntu/kgroot-latest/mini-server-prod && \
  docker exec kg-kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --delete \
    --topic raw.events"
```

Or update the topic creation script to remove it:
- [mini-server-prod/scripts/create-topics.sh:51](../mini-server-prod/scripts/create-topics.sh#L51)

## Conclusion

**No, `alerts.normalized` is not needed.** The current unified architecture using `events.normalized` for both K8s events and Prometheus alerts is:
- ✅ Simpler
- ✅ More efficient
- ✅ Already implemented and working
- ✅ Easier to maintain
- ✅ Better for event correlation

**Yes, `raw.events` should be removed.** It's an orphaned topic from the old architecture:
- ⚠️ Topic exists but unused
- ⚠️ No producers or consumers
- ⚠️ Replaced by type-specific raw topics

Keep the current design! 🎉