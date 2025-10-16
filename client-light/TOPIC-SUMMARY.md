# Kafka Topics Summary - Complete Architecture

## Visual Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA SOURCES                                      │
└─────────────────────────────────────────────────────────────────────────────┘
              │                    │                    │
              │                    │                    │
    ┌─────────▼─────────┐  ┌──────▼──────┐  ┌─────────▼──────────┐
    │  Alertmanager     │  │   K8s API   │  │  Container Logs    │
    │   (Prometheus)    │  │   Events    │  │   (DaemonSet)      │
    └─────────┬─────────┘  └──────┬──────┘  └─────────┬──────────┘
              │                    │                    │
              │                    │                    │
    ┌─────────▼─────────┐  ┌──────▼──────┐  ┌─────────▼──────────┐
    │  Vector Webhook   │  │event-exporter│  │      Vector        │
    │   (port 9090)     │  │              │  │   (DaemonSet)      │
    └─────────┬─────────┘  └──────┬──────┘  └─────────┬──────────┘
              │                    │                    │
              │                    │                    │
┌─────────────▼────────────────────▼────────────────────▼─────────────────────┐
│                          RAW LAYER (Type-Specific)                          │
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━┓  ┏━━━━━━━━━━━━━━━━┓  ┏━━━━━━━━━━━━━━━━━━┓          │
│  ┃ raw.prom.alerts  ┃  ┃ raw.k8s.events ┃  ┃  raw.k8s.logs    ┃          │
│  ┃   (30d, 3p)      ┃  ┃   (14d, 3p)    ┃  ┃    (3d, 6p)      ┃          │
│  ┗━━━━━━━┳━━━━━━━━━━┛  ┗━━━━━━━┳━━━━━━━━┛  ┗━━━━━━━┳━━━━━━━━━━┛          │
│          │                      │                    │                      │
│          │ (normalize)          │ (normalize)        │ (normalize)          │
│          │                      │                    │                      │
└──────────┼──────────────────────┼────────────────────┼──────────────────────┘
           │                      │                    │
           │                      │                    │
┌──────────▼──────────────────────▼────────────────────▼──────────────────────┐
│                      NORMALIZED LAYER (Unified by Type)                     │
│                                                                              │
│       ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓       ┏━━━━━━━━━━━━━━━━━━━┓       │
│       ┃     events.normalized         ┃       ┃  logs.normalized  ┃       │
│       ┃     (14d, 3p)                 ┃       ┃     (3d, 6p)      ┃       │
│       ┃                               ┃       ┗━━━━━━━━━━━━━━━━━━━┛       │
│       ┃ • K8s events                  ┃                                     │
│       ┃   (etype: "k8s.event")        ┃                                     │
│       ┃                               ┃                                     │
│       ┃ • Prom alerts                 ┃                                     │
│       ┃   (etype: "prom.alert")       ┃                                     │
│       ┗━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┛                                     │
│                     │                                                        │
│                     │ (filter: etype='prom.alert')                          │
│                     │                                                        │
└─────────────────────┼────────────────────────────────────────────────────────┘
                      │
                      │
         ┌────────────▼────────────┐
         │   alerts-enricher       │
         │  (enrich with K8s       │
         │   resource context)     │
         └────────────┬────────────┘
                      │
┌─────────────────────▼────────────────────────────────────────────────────────┐
│                         OUTPUT/STATE LAYER                                   │
│                                                                               │
│  ┏━━━━━━━━━━━━━━━━━━┓  ┏━━━━━━━━━━━━━━━━━━━┓  ┏━━━━━━━━━━━━━━━━━━━━┓      │
│  ┃ alerts.enriched  ┃  ┃ state.k8s.resource ┃  ┃ state.k8s.topology ┃      │
│  ┃   (30d, 3p)      ┃  ┃     (30d, 3p)      ┃  ┃     (30d, 3p)      ┃      │
│  ┗━━━━━━━━━━━━━━━━━━┛  ┗━━━━━━━━━━━━━━━━━━━┛  ┗━━━━━━━━━━━━━━━━━━━━┛      │
│                                                                               │
│  ┏━━━━━━━━━━━━━━━━━━┓  ┏━━━━━━━━━━━━━━━━━━━┓                               │
│  ┃state.prom.targets┃  ┃ state.prom.rules   ┃                               │
│  ┃   (30d, 3p)      ┃  ┃     (30d, 3p)      ┃                               │
│  ┗━━━━━━━━━━━━━━━━━━┛  ┗━━━━━━━━━━━━━━━━━━━┛                               │
└───────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          DLQ LAYER (Error Handling)                         │
│                                                                              │
│         ┏━━━━━━━━━━━━━━┓              ┏━━━━━━━━━━━━━━━━━━┓                 │
│         ┃   dlq.raw    ┃              ┃  dlq.normalized  ┃                 │
│         ┃   (7d, 3p)   ┃              ┃     (7d, 3p)     ┃                 │
│         ┗━━━━━━━━━━━━━━┛              ┗━━━━━━━━━━━━━━━━━━┛                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    ✅ ORPHANED TOPICS CLEANED UP                            │
│                                                                              │
│         ┌──────────────────┐          ┌────────────────────────┐           │
│         │   raw.events     │          │  alerts.normalized     │           │
│         │    DELETED ✓     │          │      DELETED ✓         │           │
│         │  (2025-10-16)    │          │    (2025-10-16)        │           │
│         └──────────────────┘          └────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────────┘

Legend: (retention, partitions)
```

## Topic Inventory

### ✅ Active Topics (12)

#### Raw Layer (3)
| Topic | Retention | Partitions | Size | Purpose |
|-------|-----------|------------|------|---------|
| `raw.prom.alerts` | 30d | 3 | Active | Raw Alertmanager payloads |
| `raw.k8s.events` | 14d | 3 | Active | Raw Kubernetes events |
| `raw.k8s.logs` | 3d | 6 | Active | Raw container logs |

#### Normalized Layer (2)
| Topic | Retention | Partitions | Size | Purpose |
|-------|-----------|------------|------|---------|
| `events.normalized` | 14d | 3 | Active | All normalized events (K8s + Prom) |
| `logs.normalized` | 3d | 6 | Active | All normalized logs |

#### Output/State Layer (5)
| Topic | Retention | Partitions | Size | Purpose |
|-------|-----------|------------|------|---------|
| `alerts.enriched` | 30d | 3 | Active | Enriched Prometheus alerts with K8s context |
| `state.k8s.resource` | 30d | 3 | Active | Kubernetes resource state (compacted) |
| `state.k8s.topology` | 30d | 3 | Active | Kubernetes topology/relationships (compacted) |
| `state.prom.targets` | 30d | 3 | Active | Prometheus scrape targets |
| `state.prom.rules` | 30d | 3 | Active | Prometheus alerting rules |

#### DLQ Layer (2)
| Topic | Retention | Partitions | Size | Purpose |
|-------|-----------|------------|------|---------|
| `dlq.raw` | 7d | 3 | Active | Failed raw message processing |
| `dlq.normalized` | 7d | 3 | Active | Failed normalization |

### ✅ Orphaned Topics - CLEANED UP (2025-10-16)

| Topic | Previous Status | Action Taken |
|-------|-----------------|--------------|
| `raw.events` | Unused (0 messages) | ✅ Deleted from Kafka + removed from scripts |
| `alerts.normalized` | Unused (0 messages) | ✅ Deleted from Kafka + removed from scripts |

**Cleanup complete!** See [ORPHANED-TOPICS.md](./ORPHANED-TOPICS.md) for details.

## Data Flow Patterns

### Pattern 1: Alert Processing
```
Alertmanager
  → Vector Webhook
  → raw.prom.alerts (archive)
  → events.normalized (unified stream, etype="prom.alert")
  → alerts-enricher (filters + enriches)
  → alerts.enriched (final output)
```

### Pattern 2: K8s Event Processing
```
K8s API
  → event-exporter
  → raw.k8s.events (archive)
  → events.normalized (unified stream, etype="k8s.event")
  → (downstream consumers can filter by etype)
```

### Pattern 3: Log Processing
```
Container Logs
  → Vector DaemonSet
  → raw.k8s.logs (archive)
  → logs.normalized (enriched with K8s metadata)
  → (log aggregation/analysis)
```

### Pattern 4: State Management
```
K8s Resources
  → state-watcher
  → state.k8s.resource (compacted topic, latest state only)
  → (consumed by alerts-enricher for context)

K8s Resources
  → state-watcher
  → state.k8s.topology (compacted topic, relationships)
  → (consumed by alerts-enricher for correlation)
```

## Key Architecture Decisions

### ✅ Unified Normalized Layer
**Decision**: Use `events.normalized` for both K8s events and Prometheus alerts

**Rationale**:
- Simpler architecture (1 topic vs 2)
- Easier event correlation
- Type discrimination via `etype` field
- Single consumer subscription

**Trade-off**: Consumers must filter by `etype` if they only want specific event types

### ✅ Separate Raw Layer
**Decision**: Use type-specific raw topics (`raw.prom.alerts`, `raw.k8s.events`)

**Rationale**:
- Different retention policies per type
- Clearer data lineage
- Easier to archive/replay specific types
- Independent scaling

**Trade-off**: More topics to manage (but worth it for operational flexibility)

### ✅ Compacted State Topics
**Decision**: Use Kafka compaction for state topics

**Rationale**:
- Only latest state matters
- Automatic cleanup of old versions
- Efficient state rebuilding on restart

**Implementation**:
- `state.k8s.resource` - keyed by `kind:namespace:name`
- `state.k8s.topology` - keyed by relationship ID

## Consumer Groups

### Active Consumer Groups

```bash
# Check consumer groups
ssh mini-server "docker exec kg-kafka \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list"
```

**Known Groups**:
- `alerts-enricher-minikube-test-v2` - Consumes:
  - `events.normalized` (filters for etype='prom.alert')
  - `state.k8s.resource` (for enrichment context)
  - `state.k8s.topology` (for enrichment context)

## Monitoring Commands

```bash
# List all topics
ssh mini-server "docker exec kg-kafka \
  kafka-topics.sh --bootstrap-server localhost:9092 --list"

# Check topic details
ssh mini-server "docker exec kg-kafka \
  kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic events.normalized"

# Check consumer group lag
ssh mini-server "docker exec kg-kafka \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group alerts-enricher-minikube-test-v2"

# Sample messages from a topic
ssh mini-server "docker exec kg-kafka \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic events.normalized --from-beginning --max-messages 1"
```

## References

- [TOPIC-ARCHITECTURE-ANALYSIS.md](./TOPIC-ARCHITECTURE-ANALYSIS.md) - Detailed architectural analysis
- [ORPHANED-TOPICS.md](./ORPHANED-TOPICS.md) - Topics to clean up
- [ALERTMANAGER-FIX.md](./ALERTMANAGER-FIX.md) - Recent alert flow fixes