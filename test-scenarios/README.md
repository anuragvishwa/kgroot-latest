# Knowledge Graph Testing Scenarios

This directory contains intentionally buggy applications and deployment scripts designed to test and validate the Knowledge Graph (KG) system's ability to detect, correlate, and perform root cause analysis on various Kubernetes failure scenarios.

## 📁 Directory Structure

```
test-scenarios/
├── apps/              # Buggy test applications
│   ├── crashloop.py
│   ├── oom-killer.py
│   ├── slow-startup.py
│   ├── error-logger.py
│   ├── intermittent-fail.py
│   ├── image-pull-fail.yaml
│   └── Dockerfile
├── k8s/               # Kubernetes manifests
│   ├── 00-namespace.yaml
│   ├── 01-crashloop.yaml
│   ├── 02-oom-killer.yaml
│   ├── 03-slow-startup.yaml
│   ├── 04-error-logger.yaml
│   ├── 05-intermittent-fail.yaml
│   └── 06-resource-quota.yaml
├── scripts/           # Deployment and utility scripts
│   ├── build-and-deploy.sh
│   ├── cleanup.sh
│   ├── watch-events.sh
│   └── check-kafka-topics.sh
└── queries/           # Neo4j Cypher queries for analysis
    ├── 01-basic-stats.cypher
    ├── 02-crashloop-analysis.cypher
    ├── 03-oom-analysis.cypher
    ├── 04-probe-failures.cypher
    ├── 05-image-pull-errors.cypher
    ├── 06-error-logs-analysis.cypher
    ├── 07-rca-analysis.cypher
    ├── 08-topology-analysis.cypher
    └── run-test-queries.sh
```

## 🚀 Quick Start

### Prerequisites

- Docker and Minikube running
- Knowledge Graph system deployed (Kafka, Neo4j, Vector, graph-builder)
- `kubectl` configured for your Minikube cluster

### Deploy Test Scenarios

```bash
cd test-scenarios/scripts
./build-and-deploy.sh
```

This will:
1. Build a Docker image with all test applications
2. Load it into Minikube
3. Create the `kg-testing` namespace
4. Deploy all buggy applications
5. Apply resource quotas and limits

### Monitor in Real-time

**Watch Kubernetes events:**
```bash
./watch-events.sh
```

**Watch pod status:**
```bash
kubectl get pods -n kg-testing -w
```

**Check specific pod logs:**
```bash
kubectl logs -n kg-testing <pod-name> -f
```

### Wait for Data Collection

**Wait 2-3 minutes** for events and logs to flow through the pipeline:
- K8s events → Vector → Kafka → graph-builder → Neo4j
- Pod logs → Vector → Kafka → graph-builder → Neo4j

### Run Analysis Queries

```bash
cd queries
./run-test-queries.sh
```

This will run all test queries and display results in your terminal.

**Or use Neo4j Browser:**
- Open http://localhost:7474
- Login: `neo4j` / `anuragvishwa`
- Copy/paste queries from `queries/*.cypher` files

### Cleanup

```bash
cd scripts
./cleanup.sh
```

This deletes the `kg-testing` namespace and all test resources.

---

## 🐛 Test Scenarios

### 1. CrashLoop Test (`crashloop-test`)

**What it does:**
- Starts up, logs INFO messages
- Crashes immediately with ERROR and FATAL logs
- Kubernetes restarts it repeatedly → `CrashLoopBackOff`

**Expected KG behavior:**
- Captures k8s.event with reason=`BackOff` or `CrashLoopBackOff`
- Captures ERROR/FATAL logs from the pod
- Links events to Pod resource via `ABOUT` relationship
- May establish POTENTIAL_CAUSE from logs to CrashLoop event

**Neo4j query:**
```bash
cd queries
cat 02-crashloop-analysis.cypher
```

---

### 2. OOM Killer Test (`oom-test`)

**What it does:**
- Allocates memory in 10MB chunks
- Exceeds pod memory limit (64Mi)
- Gets killed by Kubernetes → `OOMKilled`

**Expected KG behavior:**
- k8s.event with reason=`OOMKilled`
- Severity=`FATAL` (per Vector config)
- May capture warning logs about memory allocation before OOM
- Establishes causality chain: memory warnings → OOMKilled event

**Neo4j query:**
```bash
cd queries
cat 03-oom-analysis.cypher
```

---

### 3. Slow Startup Test (`slow-startup-test`)

**What it does:**
- Takes 90 seconds to initialize
- Readiness probe fails repeatedly during startup
- Eventually becomes Ready

**Expected KG behavior:**
- Multiple k8s.event with reason=`Unhealthy` or `ProbeWarning`
- Severity=`WARNING` (readiness probe failures)
- Events linked to Pod
- Timeline shows multiple probe failures, then success

**Neo4j query:**
```bash
cd queries
cat 04-probe-failures.cypher
```

---

### 4. Error Logger Test (`error-logger-test`)

**What it does:**
- Continuously logs ERROR, WARNING, FATAL messages
- Periodically generates Python exceptions with tracebacks
- Runs successfully but generates lots of log noise

**Expected KG behavior:**
- k8s.log events with severity=ERROR/WARNING/FATAL
- Log messages contain: database timeouts, HTTP errors, exceptions
- Demonstrates log-level severity detection (JSON, glog, plain text)
- Shows error pattern grouping

**Neo4j query:**
```bash
cd queries
cat 06-error-logs-analysis.cypher
```

---

### 5. Intermittent Failure Test (`intermittent-fail-test`)

**What it does:**
- Randomly succeeds/fails operations (30% failure rate)
- After 3 consecutive failures, crashes
- Demonstrates real-world flaky behavior

**Expected KG behavior:**
- Mixed INFO and ERROR logs
- Eventually crashes → CrashLoopBackOff
- RCA can trace crash back to repeated operation failures
- Shows temporal correlation between errors and crash

---

### 6. Image Pull Fail Test (`image-pull-fail`)

**What it does:**
- References a non-existent Docker image
- Kubernetes repeatedly tries to pull the image
- Results in `ImagePullBackOff`

**Expected KG behavior:**
- k8s.event with reason=`ErrImagePull` or `ImagePullBackOff`
- Severity=`ERROR` (per Vector config)
- Message contains image name/registry details
- Demonstrates image-related failure detection

**Neo4j query:**
```bash
cd queries
cat 05-image-pull-errors.cypher
```

---

## 📊 Neo4j Queries

### Query Categories

| Query File | Purpose | Key Metrics |
|------------|---------|-------------|
| `01-basic-stats.cypher` | Overview of test data | Event counts, severity distribution, timeline |
| `02-crashloop-analysis.cypher` | CrashLoop detection | Crash frequency, error logs, timing |
| `03-oom-analysis.cypher` | OOM kill patterns | OOM events, memory warnings, causality |
| `04-probe-failures.cypher` | Health check issues | Probe failures, startup duration |
| `05-image-pull-errors.cypher` | Image problems | ImagePullBackOff events, image names |
| `06-error-logs-analysis.cypher` | Log error patterns | Error grouping, exception traces |
| `07-rca-analysis.cypher` | Root cause analysis | POTENTIAL_CAUSE chains, impact radius |
| `08-topology-analysis.cypher` | Resource relationships | Deployment→Pod hierarchy, cross-pod impact |

### Example Queries

**1. Find all errors in test namespace:**
```cypher
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
  AND e.severity IN ['ERROR', 'FATAL']
RETURN e.event_time, e.reason, e.severity, r.name
ORDER BY e.event_time DESC
LIMIT 20;
```

**2. Root cause analysis:**
```cypher
MATCH path = (symptom:Episodic)-[:POTENTIAL_CAUSE*1..3]->(root:Episodic)
WHERE exists((symptom)-[:ABOUT]->(:Resource {ns: 'kg-testing'}))
  AND symptom.severity IN ['ERROR', 'FATAL']
RETURN symptom.reason, root.reason as root_cause, length(path)
ORDER BY symptom.event_time DESC
LIMIT 10;
```

**3. Most problematic pods:**
```cypher
MATCH (e:Episodic)-[:ABOUT]->(r:Pod)
WHERE r.ns = 'kg-testing'
  AND e.severity IN ['ERROR', 'FATAL']
RETURN r.name, count(e) as error_count
ORDER BY error_count DESC;
```

---

## 🔍 Validation Checklist

Use this checklist to verify the KG system is working correctly:

### Data Ingestion
- [ ] Events appear in Kafka topics (`raw.k8s.events`, `events.normalized`)
- [ ] Logs appear in Kafka topics (`raw.k8s.logs`, `logs.normalized`)
- [ ] State updates in Kafka (`state.k8s.resource`, `state.k8s.topology`)
- [ ] Consumer group `kg-builder` shows zero lag

### Neo4j Graph
- [ ] Resources created for test namespace (Pods, Deployments, Services)
- [ ] Episodic events created (k8s.event, k8s.log types)
- [ ] ABOUT relationships link events to resources
- [ ] POTENTIAL_CAUSE relationships exist for errors
- [ ] Topology relationships (CONTROLS, RUNS_ON) created

### Event Detection
- [ ] CrashLoopBackOff events detected
- [ ] OOMKilled events detected with FATAL severity
- [ ] ImagePullBackOff events detected
- [ ] Probe failure events detected
- [ ] ERROR/FATAL logs captured and parsed

### Root Cause Analysis
- [ ] POTENTIAL_CAUSE chains exist (symptom → root)
- [ ] Temporal correlation works (events within RCA window)
- [ ] Multiple causes linked to single symptom
- [ ] Cross-pod impact detected

### Severity Mapping
- [ ] CrashLoopBackOff → FATAL
- [ ] OOMKilled → FATAL
- [ ] ImagePullBackOff → ERROR
- [ ] Probe failures → WARNING (readiness) or ERROR (liveness)
- [ ] Log levels correctly parsed (JSON, glog, plain text)

---

## 📈 Monitoring Tools

### Kafka UI
```
http://localhost:7777
```
View topics, messages, consumer groups, and lag.

### Neo4j Browser
```
http://localhost:7474
Username: neo4j
Password: anuragvishwa
```
Run Cypher queries and visualize graph.

### Grafana (if deployed)
```
http://localhost:3000
Username: admin
Password: admin
```
View KG metrics dashboards.

### Prometheus (if deployed)
```
http://localhost:9091
```
View raw metrics from graph-builder.

---

## 🛠️ Troubleshooting

### No events in Kafka

**Check Vector deployment:**
```bash
kubectl logs -n observability vector-<pod-name>
```

**Check k8s-event-exporter:**
```bash
kubectl logs -n observability k8s-event-exporter-<pod-name>
```

**Verify connectivity:**
```bash
kubectl exec -n observability vector-<pod-name> -- \
  nc -zv kafka-external.observability.svc 29092
```

### No data in Neo4j

**Check graph-builder logs:**
```bash
docker logs kgroot_latest-graph-builder-1 --tail=50
```

**Check Kafka consumer lag:**
```bash
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group kg-builder \
  --describe
```

### Test pods not starting

**Check image load:**
```bash
minikube image ls | grep kg-test-apps
```

**Check pod events:**
```bash
kubectl describe pod -n kg-testing <pod-name>
```

**Check namespace quota:**
```bash
kubectl describe resourcequota -n kg-testing
```

---

## 🎯 Testing Tips

### Generate More Events

**Scale up replicas:**
```bash
kubectl scale deployment -n kg-testing error-logger-test --replicas=5
```

**Restart pods manually:**
```bash
kubectl delete pod -n kg-testing --all
```

**Create custom test pods:**
```bash
kubectl run my-test -n kg-testing --image=kg-test-apps:latest \
  --restart=Never -- python3 /app/crashloop.py
```

### Simulate Prod Scenarios

**Network failures:**
```bash
kubectl run network-test -n kg-testing --image=busybox \
  -- sh -c "while true; do wget -O- http://nonexistent:80; sleep 10; done"
```

**Resource exhaustion:**
Deploy more pods than quota allows to trigger FailedScheduling events.

**Long-running failures:**
Let scenarios run for 30+ minutes to see RCA window and severity escalation.

---

## 📚 Related Documentation

- **Production Setup:** `../production/README.md`
- **Architecture:** `../docs/ARCHITECTURE.md`
- **RCA Algorithm:** `../docs/RCA_ALGORITHM.md`
- **Vector Config:** `../k8s/vector-configmap.yaml`
- **Graph Builder:** `../kg/README.md`

---

## ✅ Success Criteria

The KG system passes testing if:

1. **All test scenarios generate expected events** (CrashLoop, OOM, probe failures, etc.)
2. **Events flow through entire pipeline** (K8s → Vector → Kafka → graph-builder → Neo4j)
3. **Graph structure is correct** (Resources, Episodic events, relationships)
4. **RCA works** (POTENTIAL_CAUSE links exist and make sense)
5. **Queries return relevant results** (all 8 query categories work)
6. **No data loss** (consumer lag stays at 0, no errors in logs)

---

## 🤝 Contributing

When adding new test scenarios:

1. Create Python app in `apps/`
2. Add to `apps/Dockerfile` if needed
3. Create K8s manifest in `k8s/`
4. Add to `scripts/build-and-deploy.sh`
5. Create corresponding Neo4j queries in `queries/`
6. Update this README

---

**Happy Testing! 🚀**
