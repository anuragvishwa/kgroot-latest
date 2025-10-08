# Test Scenarios Structure

```
test-scenarios/
│
├── 📖 Documentation
│   ├── README.md           # Complete guide with all details
│   ├── QUICK_START.md      # 5-minute quick start guide
│   └── STRUCTURE.md        # This file
│
├── 🐍 apps/                # Buggy Python applications
│   ├── crashloop.py        # Crashes immediately → CrashLoopBackOff
│   ├── oom-killer.py       # Allocates too much memory → OOMKilled
│   ├── slow-startup.py     # Takes 90s to start → Probe failures
│   ├── error-logger.py     # Logs errors continuously
│   ├── intermittent-fail.py # Random failures, eventual crash
│   ├── image-pull-fail.yaml # Pod with invalid image → ImagePullBackOff
│   └── Dockerfile          # Builds all apps into one image
│
├── ☸️  k8s/                 # Kubernetes manifests
│   ├── 00-namespace.yaml        # kg-testing namespace
│   ├── 01-crashloop.yaml        # CrashLoop deployment + service
│   ├── 02-oom-killer.yaml       # OOM deployment + service
│   ├── 03-slow-startup.yaml     # Slow startup with probes
│   ├── 04-error-logger.yaml     # Error logger (2 replicas)
│   ├── 05-intermittent-fail.yaml # Intermittent failures
│   └── 06-resource-quota.yaml   # ResourceQuota + LimitRange
│
├── 🛠️  scripts/            # Automation scripts
│   ├── build-and-deploy.sh # Build image + deploy everything
│   ├── cleanup.sh          # Delete all test resources
│   ├── watch-events.sh     # Watch K8s events live
│   └── check-kafka-topics.sh # Check Kafka message flow
│
└── 🔍 queries/             # Neo4j Cypher queries
    ├── 01-basic-stats.cypher         # Overview & counts
    ├── 02-crashloop-analysis.cypher  # CrashLoop detection
    ├── 03-oom-analysis.cypher        # OOM patterns
    ├── 04-probe-failures.cypher      # Health check issues
    ├── 05-image-pull-errors.cypher   # Image problems
    ├── 06-error-logs-analysis.cypher # Log analysis
    ├── 07-rca-analysis.cypher        # Root cause chains
    ├── 08-topology-analysis.cypher   # Resource relationships
    └── run-test-queries.sh           # Execute all queries
```

---

## File Counts

- **6 Python applications** (buggy test apps)
- **7 Kubernetes manifests** (namespace + 6 test scenarios)
- **4 Bash scripts** (deploy, cleanup, monitoring)
- **8 Cypher query files** (Neo4j analysis)
- **3 Documentation files** (README, quick start, structure)

**Total: 28 files**

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Kubernetes Cluster (kg-testing namespace)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ crashloop    │  │ oom-test     │  │ error-logger │     │
│  │ (crashes)    │  │ (OOM killed) │  │ (logs errors)│ ... │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Events & Logs
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  k8s-event-exporter + Vector (observability namespace)       │
│  • Captures K8s events                                       │
│  • Collects pod logs                                         │
│  • Normalizes & enriches data                                │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Normalized Events
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Kafka (Docker)                                              │
│  Topics: raw.k8s.events, events.normalized, logs.normalized  │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Stream Processing
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  graph-builder (Docker)                                      │
│  • Consumes from Kafka                                       │
│  • Builds knowledge graph                                    │
│  • Performs RCA                                              │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Graph Writes
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Neo4j (Docker)                                              │
│  Nodes: Resource, Episodic                                   │
│  Relationships: ABOUT, POTENTIAL_CAUSE, CONTROLS             │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Query
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  You! (via queries/run-test-queries.sh or Neo4j Browser)    │
└─────────────────────────────────────────────────────────────┘
```

---

## Test Scenario Matrix

| Scenario | Pod Name | Expected Event | Severity | Neo4j Query |
|----------|----------|----------------|----------|-------------|
| **Crash Loop** | crashloop-test | CrashLoopBackOff, BackOff | FATAL | 02-crashloop-analysis.cypher |
| **OOM Kill** | oom-test | OOMKilled | FATAL | 03-oom-analysis.cypher |
| **Slow Start** | slow-startup-test | Unhealthy, ProbeWarning | WARNING | 04-probe-failures.cypher |
| **Error Logs** | error-logger-test | LOG_ERROR (various) | ERROR | 06-error-logs-analysis.cypher |
| **Intermittent** | intermittent-fail-test | Random failures → Crash | ERROR → FATAL | 02-crashloop-analysis.cypher |
| **Image Pull** | image-pull-fail | ImagePullBackOff | ERROR | 05-image-pull-errors.cypher |

---

## Usage Patterns

### For Quick Testing (5 min)
```bash
scripts/build-and-deploy.sh
# Wait 2-3 minutes
queries/run-test-queries.sh
scripts/cleanup.sh
```

### For Deep Analysis (30 min)
```bash
scripts/build-and-deploy.sh
scripts/watch-events.sh  # Terminal 1
kubectl get pods -n kg-testing -w  # Terminal 2

# After 5-10 minutes
queries/run-test-queries.sh

# Open Neo4j Browser and explore graph visually
open http://localhost:7474

# Let it run for 30 minutes to see:
# - Severity escalation
# - RCA chains
# - Pattern detection

scripts/cleanup.sh
```

### For CI/CD Integration
```bash
# Deploy
scripts/build-and-deploy.sh

# Wait for events
sleep 180

# Validate with specific queries
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic)-[:ABOUT]->(:Resource {ns: 'kg-testing'}) RETURN count(e)"

# Should return > 0

# Cleanup
scripts/cleanup.sh
```

---

## Expected Timeline

| Time | What Happens |
|------|--------------|
| 0:00 | Deploy test scenarios |
| 0:10 | Pods start appearing |
| 0:20 | First CrashLoopBackOff events |
| 0:30 | OOM kills start |
| 1:00 | slow-startup becomes Ready |
| 1:30 | Events start appearing in Neo4j |
| 2:00 | RCA chains begin forming |
| 3:00 | Good time to run queries |
| 5:00+ | Patterns stabilize, severity escalation |

---

## Key Insights to Verify

After running test scenarios, you should be able to answer:

1. ✅ **Which pod is crashing most frequently?**
   - Query: `02-crashloop-analysis.cypher` → Count crash events per pod

2. ✅ **What caused the OOM kill?**
   - Query: `03-oom-analysis.cypher` → Find memory warnings before OOM

3. ✅ **Which errors are most common?**
   - Query: `06-error-logs-analysis.cypher` → Error patterns grouping

4. ✅ **What's the root cause of this symptom?**
   - Query: `07-rca-analysis.cypher` → POTENTIAL_CAUSE chains

5. ✅ **How are resources connected?**
   - Query: `08-topology-analysis.cypher` → Deployment → Pod hierarchy

6. ✅ **How long did slow-startup take to become ready?**
   - Query: `04-probe-failures.cypher` → Startup duration calculation

---

## Customization

### Add Your Own Test App

1. Create `apps/my-test.py`
2. Add to `apps/Dockerfile`
3. Create `k8s/09-my-test.yaml`
4. Add to `scripts/build-and-deploy.sh`
5. Create `queries/09-my-test-analysis.cypher`
6. Update `README.md`

### Modify Failure Behavior

Edit Python files in `apps/`:
- Change crash frequency
- Adjust memory allocation
- Modify log patterns
- Change failure rates

### Adjust Resource Limits

Edit `k8s/*.yaml` files:
- Memory limits (trigger OOM faster/slower)
- CPU limits
- Probe timing
- Replica counts

---

## Integration Points

This test suite validates:

- ✅ **K8s event collection** (k8s-event-exporter → Vector)
- ✅ **Log aggregation** (Vector DaemonSet → Kafka)
- ✅ **Event normalization** (Vector transforms)
- ✅ **Kafka throughput** (all topics)
- ✅ **Graph building** (graph-builder consumer)
- ✅ **Neo4j writes** (Resource & Episodic nodes)
- ✅ **RCA algorithm** (POTENTIAL_CAUSE relationships)
- ✅ **Severity mapping** (K8s events → severity levels)
- ✅ **Topology tracking** (CONTROLS relationships)
- ✅ **Query performance** (Cypher queries)

---

**For more details, see [README.md](README.md) or [QUICK_START.md](QUICK_START.md)**
