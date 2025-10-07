# KGroot RCA Improvements for Maximum Accuracy

Based on the paper **"KGroot: Enhancing Root Cause Analysis through Knowledge Graphs and LLM"** (arXiv:2402.13264v1), this document outlines improvements to achieve maximum RCA accuracy for Kubernetes bug/error detection.

## Paper Summary

**KGroot** achieves **93.5% top-3 accuracy (A@3)** in root cause analysis by:

1. **Fault Event Knowledge Graph (FEKG)**: Historical knowledge graph built from past failures
2. **Fault Propagation Graph (FPG)**: Real-time graph constructed during online failures
3. **Graph Convolutional Networks (GCN)**: Computes similarity between FPG and FEKG
4. **Event-driven RCA**: Discovers causal relationships from event sequences

## Current Implementation Status

### ✅ What We Have

1. **Real-time Event Ingestion**
   - Prometheus alerts (via Vector)
   - Kubernetes events (via state-watcher)
   - Pod logs with severity filtering (via Vector DaemonSet)
   - Resource state changes (Pods, Services, Deployments, etc.)
   - Topology relationships (SELECTS, RUNS_ON, CONTROLS)

2. **Knowledge Graph Construction** (graph-builder.go)
   - Resource nodes with labels by kind (Pod, Service, Deployment, etc.)
   - Episodic nodes for events/alerts/logs
   - Relationship discovery (ABOUT, POTENTIAL_CAUSE)
   - Temporal windowing for causal links (15-minute default)
   - High-signal log filtering to reduce graph bloat

3. **Enrichment Pipeline** (alerts-enricher)
   - Enriches alerts with resource state
   - Adds topology context
   - Produces enriched alerts for downstream analysis

### 🚧 What's Missing for Maximum Accuracy

#### 1. Historical FEKG Construction

**Problem**: We don't have historical failure patterns to compare against.

**Solution**:
- Create periodic graph snapshots (enabled via `ENABLE_TEMPORAL_SNAPSHOTS=true`)
- Store fault event subgraphs for each resolved incident
- Build FEKG templates from successful RCA resolutions

**Implementation**:
```cypher
// Store historical incident patterns
MATCH (e:Episodic)-[:POTENTIAL_CAUSE*1..3]-(root:Episodic)
WHERE e.severity IN ['CRITICAL', 'ERROR']
  AND root.severity IN ['WARNING', 'ERROR']
  AND e.resolved_at IS NOT NULL
CREATE (fekg:FEKG {
  incident_id: e.incident_id,
  root_cause: root.reason,
  pattern: [path signatures],
  timestamp: e.resolved_at
})
```

#### 2. Graph Convolutional Network (GCN) Similarity

**Problem**: We use simple shortest-path and time-window heuristics, not ML-based similarity.

**Solution**:
- Implement GCN service for graph embedding and similarity computation
- Compare runtime FPG against historical FEKG patterns
- Rank root cause candidates by GCN similarity scores

**Implementation** (requires separate ML service):
```python
# gcn-service/model.py
import torch
import torch_geometric as pyg

class GCNSimilarity(torch.nn.Module):
    def __init__(self, input_dim, hidden_dim):
        super().__init__()
        self.conv1 = pyg.nn.GCNConv(input_dim, hidden_dim)
        self.conv2 = pyg.nn.GCNConv(hidden_dim, hidden_dim)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        x = self.conv2(x, edge_index)
        return pyg.nn.global_mean_pool(x)

    def similarity(self, fpg_embedding, fekg_embedding):
        return torch.cosine_similarity(fpg_embedding, fekg_embedding)
```

#### 3. Event Sequence Analysis

**Problem**: We create episodic nodes but don't analyze event sequences deeply.

**Solution**:
- Implement temporal pattern mining
- Discover frequent fault sequences (e.g., "ImagePullBackOff → CrashLoopBackOff → PodEvicted")
- Use sequence similarity for better root cause ranking

**Cypher Query**:
```cypher
// Find common fault sequences in last 30 days
MATCH path = (e1:Episodic)-[:POTENTIAL_CAUSE]->(e2:Episodic)-[:POTENTIAL_CAUSE]->(e3:Episodic)
WHERE e3.event_time > datetime() - duration({days: 30})
  AND e1.severity IN ['ERROR', 'CRITICAL']
RETURN [e1.reason, e2.reason, e3.reason] AS sequence, count(*) AS frequency
ORDER BY frequency DESC
LIMIT 20
```

#### 4. Multi-level Fault Propagation

**Problem**: We only link events within a time window, not multi-hop dependencies.

**Solution**:
- Track cascading failures across service boundaries
- Link alerts to their upstream/downstream services
- Build fault propagation chains (Pod → Service → Deployment → Namespace)

**Enhanced LinkRCA** (graph-builder.go):
```go
func (g *Graph) LinkRCAEnhanced(ctx context.Context, eid string, windowMin int) error {
    // Level 1: Direct resource dependencies (current implementation)
    // Level 2: Service-level propagation
    cy := `
    MATCH (e:Episodic {eid:$eid})-[:ABOUT]->(pod:Resource:Pod)
    MATCH (pod)<-[:SELECTS]-(svc:Resource:Service)
    MATCH (svc)<-[:CONTROLS]-(deploy:Resource:Deployment)
    WITH e, collect(DISTINCT pod) + collect(DISTINCT svc) + collect(DISTINCT deploy) AS affected
    UNWIND affected AS r
    MATCH (c:Episodic)-[:ABOUT]->(upstream:Resource)
    WHERE c.event_time <= e.event_time
      AND c.event_time >= e.event_time - duration({minutes:$mins})
    OPTIONAL MATCH p = shortestPath((upstream)-[*1..5]-(r))
    WHERE p IS NOT NULL
    MERGE (c)-[pc:POTENTIAL_CAUSE]->(e)
    ON CREATE SET pc.hops = length(p), pc.level = 'multi-hop'
    `
    // ...
}
```

#### 5. Metric-based Anomaly Correlation

**Problem**: We ingest Prometheus targets/rules but don't correlate metric anomalies with events.

**Solution**:
- Query Prometheus for metric values around event time
- Detect anomalies (CPU spike, memory leak, network errors)
- Create METRIC_ANOMALY nodes linked to events

**Example**:
```go
// In handleEvent or handleLog
func (h *handler) correlateMetrics(ctx context.Context, ev EventNormalized) error {
    // Query Prometheus for pod metrics around event time
    query := fmt.Sprintf(`rate(container_cpu_usage_seconds_total{pod="%s"}[5m])`, ev.Subject.Name)
    // If anomaly detected, create METRIC_ANOMALY node
    // Link to episodic event
}
```

## Recommended Deployment Strategy

### Phase 1: Current Setup (MVP) ✅
**Goal**: Basic RCA with real-time event correlation
**Accuracy**: ~60-70% (estimated)

- ✅ Deploy Kafka, Vector, state-watcher, alerts-enricher
- ✅ Deploy Neo4j and kg-builder
- ✅ Ingest events, logs, alerts, resources, topology
- ✅ Basic causal link discovery (time + topology)

### Phase 2: Historical Knowledge (+15-20% accuracy)
**Goal**: Learn from past incidents
**Accuracy**: ~75-85% (estimated)

- Create incident management workflow
- Tag resolved incidents with root causes
- Build FEKG templates from successful RCAs
- Store fault patterns in Neo4j

**Implementation**:
```bash
# Add to .env
ENABLE_FEKG_HISTORICAL=true
FEKG_RETENTION_DAYS=90
```

### Phase 3: ML-based Similarity (+8-13% accuracy)
**Goal**: Match KGroot paper performance
**Accuracy**: ~90-95% (KGroot achieves 93.5%)

- Deploy GCN service for graph embeddings
- Train on historical FEKGs
- Use cosine similarity for root cause ranking
- Integrate LLM for natural language explanation

**Implementation**:
```bash
# Add to .env
ENABLE_GCN_SIMILARITY=true
GCN_SERVICE_URL=http://gcn-service.observability.svc:8080
```

### Phase 4: Advanced Features (ongoing improvement)
- Multi-cluster RCA
- Cross-service distributed tracing integration
- Automated remediation suggestions
- Continuous learning from feedback

## Configuration for Maximum Accuracy

Update `.env` with these settings:

```bash
# RCA Configuration
RCA_WINDOW_MIN=15                    # Causal link time window
CAUSAL_LINK_MAX_HOPS=3               # Max graph distance for causality
CAUSAL_LINK_TIME_THRESHOLD_SEC=300   # 5-minute threshold

# Event Correlation
EVENT_CORRELATION_WINDOW_SEC=60      # Deduplicate events within 1 minute
EVENT_DEDUPLICATION_ENABLED=true     # Reduce noise

# Graph Pruning
PRUNE_OLD_EVENTS_DAYS=30             # Keep recent events only
PRUNE_RESOLVED_INCIDENTS_DAYS=7      # Keep resolved incidents for learning

# Feature Flags
ENABLE_LOG_FILTERING=true            # Only high-signal logs (ERROR/FATAL)
ENABLE_FPG_REALTIME=true             # Real-time fault propagation graphs
ENABLE_FEKG_HISTORICAL=true          # Historical fault pattern learning
ENABLE_TEMPORAL_SNAPSHOTS=true       # Periodic graph snapshots
SNAPSHOT_INTERVAL_MIN=60             # Hourly snapshots

# Future: GCN Integration
ENABLE_GCN_SIMILARITY=false          # Set to true when GCN service ready
GCN_SERVICE_URL=http://gcn-service.observability.svc:8080
```

## Neo4j Queries for RCA

### Find Root Causes for an Event
```cypher
// Given an error event, find potential root causes ranked by strength
MATCH (error:Episodic {eid: $event_id})
MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(error)
WITH cause, pc, error
ORDER BY pc.hops ASC, cause.event_time DESC
RETURN cause.reason AS root_cause,
       cause.severity AS severity,
       cause.message AS description,
       pc.hops AS distance,
       duration.between(cause.event_time, error.event_time) AS time_lag
LIMIT 10
```

### Find Common Fault Patterns
```cypher
// Discover frequent failure sequences
MATCH path = (e1:Episodic)-[:POTENTIAL_CAUSE]->(e2:Episodic)-[:POTENTIAL_CAUSE]->(e3:Episodic)
WHERE e3.event_time > datetime() - duration({days: 30})
  AND e1.severity IN ['ERROR', 'CRITICAL']
WITH [e1.reason, e2.reason, e3.reason] AS sequence
RETURN sequence, count(*) AS occurrences
ORDER BY occurrences DESC
LIMIT 20
```

### Analyze Service Impact
```cypher
// Find which services are affected by a pod failure
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource:Pod)
WHERE e.severity = 'ERROR'
  AND e.event_time > datetime() - duration({hours: 1})
MATCH (pod)<-[:SELECTS]-(svc:Resource:Service)
OPTIONAL MATCH (svc)<-[:CONTROLS]-(deploy:Resource:Deployment)
RETURN pod.name AS failed_pod,
       collect(DISTINCT svc.name) AS affected_services,
       collect(DISTINCT deploy.name) AS deployments,
       count(e) AS error_count
ORDER BY error_count DESC
```

## Next Steps for Maximum Accuracy

1. **Deploy Current Setup** (Phase 1): Use existing code with unified `.env`
2. **Collect Training Data** (2-4 weeks): Let the system run and collect events
3. **Manual RCA Tagging**: Resolve incidents manually and tag root causes
4. **Build FEKG Templates**: Create historical knowledge base
5. **Implement GCN Service** (optional): For ML-based similarity
6. **Validate & Iterate**: Compare RCA predictions vs. actual root causes

## Estimated Accuracy Timeline

| Phase | Accuracy | Timeframe | Effort |
|-------|----------|-----------|--------|
| Phase 1 (Current) | 60-70% | Immediate | Low |
| Phase 2 (Historical) | 75-85% | 2-4 weeks | Medium |
| Phase 3 (GCN/ML) | 90-95% | 2-3 months | High |
| Phase 4 (Advanced) | 95%+ | 6+ months | Very High |

**Recommendation for MVP**: Start with Phase 1, collect data for 2-4 weeks, then move to Phase 2. GCN/ML (Phase 3) can wait until you have sufficient historical data (~100+ resolved incidents).
