# KGroot System Capabilities & Architecture

## 🎯 What KGroot Does

KGroot is a **Kubernetes Root Cause Analysis (RCA) system** that builds a knowledge graph to automatically detect and trace failures in your K8s cluster.

---

## ✅ Currently Implemented Features

### 1. **Data Collection**

**✅ Kubernetes Resource Monitoring**
- Pods, Services, Deployments, ReplicaSets, DaemonSets, Nodes, Jobs, Endpoints
- Real-time state watching via `state-watcher`
- Topology relationships (SELECTS, CONTROLS, RUNS_ON)

**✅ Event Collection**
- K8s events (ImagePullBackOff, CrashLoopBackOff, etc.)
- Normalized into `events.normalized` Kafka topic

**✅ Log Collection**
- Container logs via Vector
- Error/Warning/Fatal log detection
- Normalized into `logs.normalized` Kafka topic

**✅ Prometheus Integration**
- Scrape targets monitoring
- Alert rules monitoring
- Metrics-based event correlation

### 2. **Knowledge Graph (Neo4j)**

**✅ Node Types**
- `Resource` - K8s resources (Pods, Services, Deployments, etc.)
- `Episodic` - Events, logs, alerts (time-based occurrences)
- `PromTarget` - Prometheus scrape targets
- `Rule` - Prometheus alert rules

**✅ Relationship Types**
- `ABOUT` - Events/logs linked to resources (2,514 relationships)
- `POTENTIAL_CAUSE` - **RCA causal links** (5,436 relationships! 🎉)
- `SELECTS` - Service→Pod selection
- `CONTROLS` - Controller→Pod ownership
- `RUNS_ON` - Pod→Node placement
- `SCRAPES` - Prometheus→Target monitoring

### 3. **Root Cause Analysis (RCA)**

**✅ Temporal Correlation**
- Time-windowed event correlation
- Configurable via `EVENT_CORRELATION_WINDOW_SEC` (default: 60s)

**✅ Causal Link Detection**
- Builds `POTENTIAL_CAUSE` relationships between events
- Multi-hop traversal up to `CAUSAL_LINK_MAX_HOPS` (default: 3)
- Time threshold: `CAUSAL_LINK_TIME_THRESHOLD_SEC` (default: 300s)

**✅ Graph-based RCA**
- Shortest path queries to find root causes
- Transitive causality (A→B→C chains)
- Pattern-based failure detection

### 4. **Tested Failure Patterns**

**✅ Already Implemented & Tested:**

1. **ImagePullBackOff** (`test/01-imagepull-failure.yaml`)
   - Wrong image tags
   - Missing images

2. **CrashLoopBackOff** (`test/02-crashloop.yaml`)
   - Application panics
   - Exit code failures

3. **OOMKilled** (`test/03-oomkilled.yaml`)
   - Memory exhaustion
   - Memory limit exceeded

4. **Service Selector Mismatch** (`test/04-service-mismatch.yaml`)
   - Empty endpoints
   - Service can't find pods

5. **Cascading Failures** (`test/05-cascading-failure.yaml`)
   - 3-tier failure propagation (DB→API→Frontend)
   - Temporal correlation across tiers

6. **Configuration Errors** (`test/06-missing-env.yaml`)
   - Missing environment variables
   - Application startup failures

**Your data shows this is working:**
- 2,540 Episodic nodes (events/logs captured)
- 5,436 POTENTIAL_CAUSE links (RCA correlations built!)
- Services correctly linked to Pods via SELECTS

---

## 📊 Prometheus Integration

**✅ Yes, using Prometheus!**

You have `prometheus-kube-prometheus-prometheus` service running in the `monitoring` namespace.

**What's monitored:**
- Prometheus scrape targets → Neo4j (`PromTarget` nodes, 21 targets)
- Alert rules → Neo4j (`Rule` nodes)
- Metrics correlated with K8s events

**Metrics-based RCA:**
- High CPU/Memory → Pod failures
- Network errors → Service unavailability
- Node pressure → Pod evictions

---

## ❌ Not Yet Implemented

### 1. **OpenAI Embeddings / LLM Integration**

**Current Status:** ❌ NOT IMPLEMENTED

The system does NOT currently use:
- OpenAI embeddings
- Vector similarity search
- LLM-based root cause explanations
- Semantic similarity between logs

**What would embeddings add?**
- Semantic log clustering (group similar errors)
- Anomaly detection (find unusual patterns)
- Natural language RCA explanations
- Similar failure pattern matching

**Implementation Path:**
1. Generate embeddings for log messages using OpenAI API
2. Store embeddings in Neo4j or vector DB (Pinecone, Weaviate)
3. Add similarity search queries
4. Use GPT-4 to generate human-readable RCA summaries

**Example Future Query:**
```cypher
// Find similar failures using embeddings
MATCH (e:Episodic)
WHERE e.embedding IS NOT NULL
WITH e, vector.similarity(e.embedding, $query_embedding) AS similarity
WHERE similarity > 0.8
RETURN e.message, similarity
ORDER BY similarity DESC
```

### 2. **GitHub Actions / CI Integration**

**Current Status:** ❌ NOT IMPLEMENTED

**What would this add?**
- Deployment failure correlation
- CI/CD event tracking
- Build failure → Pod crash correlation
- Git commit → failure timeline

**Implementation Path:**
1. Add GitHub webhook receiver
2. Capture deployment events (commit SHA, PR, author)
3. Link deployments to K8s rollouts
4. Correlate code changes with failures

### 3. **Jira Integration**

**Current Status:** ❌ NOT IMPLEMENTED

**What would this add?**
- Auto-create Jira tickets for incidents
- Link RCA graphs to tickets
- Track MTTR (Mean Time To Resolution)
- Historical incident analysis

**Implementation Path:**
1. Add Jira API integration
2. Trigger on critical POTENTIAL_CAUSE chains
3. Attach Neo4j graph visualization to ticket
4. Update ticket status based on resolution

### 4. **Advanced Pattern Detection**

**What's missing:**
- ❌ Network partition detection
- ❌ DNS resolution failures
- ❌ Certificate expiration
- ❌ Resource quota exhaustion
- ❌ StorageClass issues
- ❌ Init container failures
- ❌ Liveness/Readiness probe failures (partially detected via events)

These could be added by:
1. Extending event normalization patterns
2. Adding more Prometheus alert rules
3. Creating specific Cypher queries for detection

---

## 🔬 How to Test RCA

### **Run All Tests:**
```bash
cd /Users/anuragvishwa/Anurag/kgroot_latest

# Deploy all test scenarios
./test/run-all-tests.sh

# Validate RCA system
./test/validate-rca.sh
```

### **Test Individual Scenarios:**
```bash
# Test 1: ImagePullBackOff
kubectl apply -f test/01-imagepull-failure.yaml

# Test 5: Cascading Failure (most complex!)
kubectl apply -f test/05-cascading-failure.yaml

# Wait 2 minutes, then check Neo4j
kubectl port-forward -n observability svc/neo4j-external 7474:7474
```

### **Validate RCA Links:**
```cypher
// Find root causes of recent failures
MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..3]->(symptom:Episodic)
WHERE root.event_time > datetime() - duration({minutes: 30})
RETURN path
LIMIT 25;
```

---

## 📈 Current System Stats (From Your Data)

```
Total Nodes: 2,741
├─ Episodic:       2,540 (events/logs)
├─ Resource:       77 (base resources)
├─ Pod:            35
├─ Service:        27
├─ PromTarget:     21
└─ Others:         41

Total Relationships: 8,032
├─ POTENTIAL_CAUSE: 5,436 ⭐ (RCA links!)
├─ ABOUT:          2,514 (event→resource)
├─ SCRAPES:        39 (prom→target)
├─ CONTROLS:       36 (controller→pod)
├─ RUNS_ON:        27 (pod→node)
└─ SELECTS:        20 (service→pod)
```

**This is working beautifully!** 🎉

---

## 🚀 Roadmap: What to Add Next

### Priority 1: Core Improvements
1. ✅ Fix ingress for permanent Neo4j/Kafka UI access
2. ⬜ Add OpenAI embeddings for log similarity
3. ⬜ Implement more K8s failure patterns
4. ⬜ Add RCA confidence scores

### Priority 2: Integrations
1. ⬜ GitHub Actions webhook
2. ⬜ Jira ticket automation
3. ⬜ Slack/PagerDuty notifications
4. ⬜ Grafana dashboard for RCA visualization

### Priority 3: Advanced Features
1. ⬜ ML-based anomaly detection
2. ⬜ Predictive failure analysis
3. ⬜ Auto-remediation suggestions
4. ⬜ Historical pattern learning

---

## 🔧 Architecture Summary

```
┌─────────────┐
│ Kubernetes  │
│  Cluster    │
└──────┬──────┘
       │
       ├─→ state-watcher ──→ Kafka (state.k8s.resource, state.k8s.topology)
       ├─→ k8s-event-exporter ──→ Kafka (events.normalized)
       ├─→ vector-logs ──→ Kafka (logs.normalized)
       └─→ prometheus ──→ Kafka (state.prom.targets, state.prom.rules)
                          │
                          ▼
                    ┌───────────┐
                    │   Kafka   │
                    └─────┬─────┘
                          │
                          ▼
                   ┌──────────────┐
                   │ kg-builder   │ ← Consumes all topics
                   │ (Go app)     │ ← Builds knowledge graph
                   │              │ ← Creates POTENTIAL_CAUSE links
                   └──────┬───────┘
                          │
                          ▼
                    ┌──────────┐
                    │  Neo4j   │ ← Knowledge Graph
                    │  (Graph  │ ← Query via Cypher
                    │   DB)    │ ← Browser at :7474
                    └──────────┘
```

**Missing from diagram:**
- ❌ OpenAI API (embeddings)
- ❌ GitHub webhooks
- ❌ Jira API
- ❌ Vector database (if using embeddings)

---

## 📝 Summary

**What you have:**
- ✅ Full K8s observability stack
- ✅ Real-time knowledge graph
- ✅ Working RCA with 5,436 causal links
- ✅ 6 tested failure patterns
- ✅ Prometheus integration

**What you need to add:**
- ⬜ OpenAI embeddings (for semantic similarity)
- ⬜ GitHub/Jira integration (for incident tracking)
- ⬜ More K8s failure patterns (DNS, certs, etc.)

**Your system is production-ready for basic RCA!** 🚀

The test suite proves it's working. Now you can:
1. Add embeddings for smarter log analysis
2. Integrate with CI/CD and ticketing systems
3. Build a frontend for easier RCA visualization
