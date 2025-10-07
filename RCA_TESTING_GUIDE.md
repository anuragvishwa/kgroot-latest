# RCA Testing Guide - Intentional Failure Scenarios

This guide introduces intentional bugs/failures to test if the RCA system correctly identifies root causes.

## Test Scenarios Overview

| Test # | Scenario | Expected Root Cause | RCA Difficulty |
|--------|----------|---------------------|----------------|
| 1 | ImagePullBackOff | Wrong image tag | Easy |
| 2 | CrashLoopBackOff | Application panic | Easy |
| 3 | OOMKilled | Memory leak | Medium |
| 4 | Service Unavailable | Selector mismatch | Medium |
| 5 | Cascading Failure | Database down → API crash → Frontend error | Hard |
| 6 | Config-induced Crash | Missing environment variable | Easy |
| 7 | Readiness Probe Failure | Slow startup | Medium |
| 8 | Resource Quota Exceeded | Too many replicas | Medium |
| 9 | Network Connectivity | DNS resolution failure | Hard |
| 10 | Deployment Rollout Stuck | Invalid health check | Medium |

## Prerequisites

```bash
# Ensure all services are running
kubectl get pods -n observability

# Expected:
# - kafka-0
# - neo4j-0
# - kg-builder-*
# - vector-*
# - state-watcher-*
# - alerts-enricher-*

# Check Neo4j is accessible
kubectl port-forward -n observability svc/neo4j-external 7474:7474 &
# Open http://localhost:7474 (neo4j/anuragvishwa)
```

## Test 1: ImagePullBackOff (Wrong Image Tag)

### Deploy Buggy App

```yaml
# test/01-imagepull-failure.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-imagepull
  namespace: default
  labels:
    test: rca-imagepull
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-imagepull
  template:
    metadata:
      labels:
        app: test-imagepull
    spec:
      containers:
        - name: app
          image: nginx:this-tag-does-not-exist-12345  # ← Intentional error
          ports:
            - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: test-imagepull
  namespace: default
spec:
  selector:
    app: test-imagepull
  ports:
    - port: 80
      targetPort: 80
```

### Expected Behavior

1. Pod stuck in `ImagePullBackOff`
2. K8s events: `Failed to pull image`, `Back-off pulling image`
3. Vector captures events → `events.normalized`
4. kg-builder creates:
   - `Episodic` node with reason: `FailedPull` or `BackOff`
   - `Resource` node for pod
   - `ABOUT` relationship

### Verification Queries

```cypher
// 1. Find the ImagePullBackOff event
MATCH (e:Episodic)
WHERE e.reason CONTAINS 'Pull' OR e.reason CONTAINS 'BackOff'
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN e.eid, e.reason, e.message, e.severity, e.event_time
ORDER BY e.event_time DESC
LIMIT 10

// 2. Find affected pod
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource)
WHERE e.reason CONTAINS 'Pull'
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN pod.name, pod.ns, pod.image, e.message

// 3. Check if service is affected
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource:Pod)
WHERE e.reason CONTAINS 'Pull'
MATCH (pod)<-[:SELECTS]-(svc:Resource:Service)
RETURN svc.name, svc.ns, collect(pod.name) AS affected_pods

// Expected: Should find event with reason like "Failed", "BackOff", "ErrImagePull"
```

### Cleanup

```bash
kubectl delete -f test/01-imagepull-failure.yaml
```

---

## Test 2: CrashLoopBackOff (Application Panic)

### Deploy Buggy App

```yaml
# test/02-crashloop.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-crashloop
  namespace: default
  labels:
    test: rca-crashloop
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-crashloop
  template:
    metadata:
      labels:
        app: test-crashloop
    spec:
      containers:
        - name: app
          image: busybox
          command: ["sh", "-c", "echo 'Starting...'; sleep 2; echo 'ERROR: Fatal panic!'; exit 1"]  # ← Crashes immediately
---
apiVersion: v1
kind: Service
metadata:
  name: test-crashloop
  namespace: default
spec:
  selector:
    app: test-crashloop
  ports:
    - port: 80
```

### Expected Behavior

1. Container starts, exits with code 1
2. K8s events: `Back-off restarting failed container`
3. Logs: "ERROR: Fatal panic!"
4. Vector logs capture ERROR level log
5. kg-builder creates:
   - Multiple `Episodic` nodes (one per crash/restart)
   - Log-based episodic with `LOG_ERROR` or `LOG_FATAL`
   - Pod resource node

### Verification Queries

```cypher
// 1. Find crash events
MATCH (e:Episodic)
WHERE (e.reason CONTAINS 'BackOff' OR e.reason CONTAINS 'CrashLoop')
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN e.eid, e.reason, e.message, e.event_time
ORDER BY e.event_time DESC

// 2. Find log-based errors from the same pod
MATCH (e:Episodic {etype: 'k8s.log'})-[:ABOUT]->(pod:Resource)
WHERE e.severity = 'ERROR'
  AND pod.name CONTAINS 'test-crashloop'
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN e.reason, e.message, e.event_time

// 3. Find potential root cause chain
MATCH (crash:Episodic)-[:ABOUT]->(pod:Resource)
WHERE crash.reason CONTAINS 'BackOff'
  AND pod.name CONTAINS 'test-crashloop'
WITH crash, pod
MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(crash)
RETURN cause.reason AS root_cause,
       cause.message AS root_message,
       crash.reason AS symptom,
       pc.hops AS distance,
       duration.between(cause.event_time, crash.event_time) AS time_lag
ORDER BY time_lag

// Expected: Should find log ERROR as potential cause of CrashLoop
```

### Cleanup

```bash
kubectl delete -f test/02-crashloop.yaml
```

---

## Test 3: OOMKilled (Memory Exhaustion)

### Deploy Memory Hog

```yaml
# test/03-oomkilled.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-oom
  namespace: default
  labels:
    test: rca-oom
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-oom
  template:
    metadata:
      labels:
        app: test-oom
    spec:
      containers:
        - name: memory-hog
          image: polinux/stress
          command: ["stress", "--vm", "1", "--vm-bytes", "512M", "--vm-hang", "0"]
          resources:
            limits:
              memory: "128Mi"  # ← Much smaller than what app requests
            requests:
              memory: "64Mi"
```

### Expected Behavior

1. Container exceeds memory limit
2. Kernel OOM killer terminates container (exit code 137)
3. K8s events: `OOMKilled`
4. Pod restarts repeatedly

### Verification Queries

```cypher
// 1. Find OOMKilled events
MATCH (e:Episodic)
WHERE e.reason CONTAINS 'OOM' OR e.message CONTAINS 'OOMKilled'
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN e.eid, e.reason, e.message, e.event_time

// 2. Check pod status
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource)
WHERE e.reason CONTAINS 'OOM'
RETURN pod.name, pod.status_json

// 3. Find if there were warning signs (memory alerts)
MATCH (oom:Episodic)-[:ABOUT]->(pod:Resource)
WHERE oom.reason CONTAINS 'OOM'
WITH oom, pod
MATCH (alert:Episodic)-[:ABOUT]->(pod)
WHERE alert.etype = 'prom.alert'
  AND alert.event_time < oom.event_time
  AND alert.event_time > oom.event_time - duration({minutes: 15})
RETURN alert.reason AS warning_alert,
       alert.event_time AS alert_time,
       oom.event_time AS oom_time,
       duration.between(alert.event_time, oom.event_time) AS lead_time

// Expected: Find OOMKilled event, possibly with memory pressure alerts before
```

### Cleanup

```bash
kubectl delete -f test/03-oomkilled.yaml
```

---

## Test 4: Service Unavailable (Selector Mismatch)

### Deploy Misconfigured Service

```yaml
# test/04-service-mismatch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-backend
  namespace: default
  labels:
    test: rca-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: backend
      version: v1
  template:
    metadata:
      labels:
        app: backend
        version: v1  # ← Correct label
    spec:
      containers:
        - name: app
          image: nginx
          ports:
            - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: test-backend
  namespace: default
spec:
  selector:
    app: backend
    version: v2  # ← WRONG! Should be v1
  ports:
    - port: 80
      targetPort: 80
```

### Expected Behavior

1. Pods are running and healthy
2. Service has zero endpoints (selector mismatch)
3. Requests to service fail

### Verification Queries

```cypher
// 1. Find service with no endpoints
MATCH (svc:Resource:Service {name: 'test-backend'})
OPTIONAL MATCH (svc)-[:SELECTS]->(pod:Resource:Pod)
WITH svc, count(pod) AS pod_count
WHERE pod_count = 0
RETURN svc.name, svc.ns, svc.labels_json, pod_count

// 2. Find pods that SHOULD be selected but aren't
MATCH (pod:Resource:Pod)
WHERE pod.labels_kv CONTAINS 'app=backend'
  AND pod.ns = 'default'
WITH pod
MATCH (svc:Resource:Service {name: 'test-backend'})
WHERE NOT exists((svc)-[:SELECTS]->(pod))
RETURN svc.name AS service,
       pod.name AS orphaned_pod,
       svc.labels_json AS svc_selector,
       pod.labels_json AS pod_labels

// 3. Check for connection errors in logs
MATCH (e:Episodic {etype: 'k8s.log'})
WHERE e.message CONTAINS 'connection refused'
   OR e.message CONTAINS 'no endpoints'
   OR e.message CONTAINS 'service unavailable'
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN e.reason, e.message, e.event_time

// Expected: Find service with 0 pods selected, pods that match but not selected
```

### Cleanup

```bash
kubectl delete -f test/04-service-mismatch.yaml
```

---

## Test 5: Cascading Failure (Database → API → Frontend)

### Deploy 3-Tier App with Broken Database

```yaml
# test/05-cascading-failure.yaml
# Database (intentionally fails)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-db
  namespace: default
  labels:
    test: rca-cascade
    tier: database
spec:
  replicas: 1
  selector:
    matchLabels:
      app: db
  template:
    metadata:
      labels:
        app: db
        tier: database
    spec:
      containers:
        - name: db
          image: busybox
          command: ["sh", "-c", "echo 'DB ERROR: Cannot bind to port'; exit 1"]
---
apiVersion: v1
kind: Service
metadata:
  name: test-db
  namespace: default
spec:
  selector:
    app: db
  ports:
    - port: 5432

---
# API (tries to connect to DB)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-api
  namespace: default
  labels:
    test: rca-cascade
    tier: api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
        tier: api
    spec:
      containers:
        - name: api
          image: busybox
          command:
            - sh
            - -c
            - |
              echo "API starting..."
              sleep 5
              echo "ERROR: Failed to connect to database test-db:5432 - connection refused"
              sleep 5
              echo "FATAL: Database connection pool exhausted"
              exit 1
---
apiVersion: v1
kind: Service
metadata:
  name: test-api
  namespace: default
spec:
  selector:
    app: api
  ports:
    - port: 8080

---
# Frontend (tries to call API)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-frontend
  namespace: default
  labels:
    test: rca-cascade
    tier: frontend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
        tier: frontend
    spec:
      containers:
        - name: frontend
          image: busybox
          command:
            - sh
            - -c
            - |
              echo "Frontend starting..."
              sleep 10
              echo "WARNING: API call to test-api:8080 timed out after 30s"
              echo "ERROR: Cannot render page - upstream service unavailable"
              exit 1
---
apiVersion: v1
kind: Service
metadata:
  name: test-frontend
  namespace: default
spec:
  selector:
    app: frontend
  ports:
    - port: 80
```

### Expected Behavior

1. **Database** crashes immediately
2. **API** crashes trying to connect to DB
3. **Frontend** crashes when API is unavailable
4. Cascading failure chain: DB → API → Frontend

### Verification Queries

```cypher
// 1. Find all failures in the test
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource)
WHERE pod.name CONTAINS 'test-db'
   OR pod.name CONTAINS 'test-api'
   OR pod.name CONTAINS 'test-frontend'
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN pod.name AS component,
       e.reason AS failure_reason,
       e.severity AS severity,
       e.event_time AS time
ORDER BY e.event_time ASC

// 2. Find the root cause (earliest failure)
MATCH (e:Episodic)-[:ABOUT]->(pod:Resource)
WHERE (pod.name CONTAINS 'test-db' OR pod.name CONTAINS 'test-api' OR pod.name CONTAINS 'test-frontend')
  AND e.severity IN ['ERROR', 'CRITICAL']
  AND e.event_time > datetime() - duration({minutes: 30})
WITH e, pod
ORDER BY e.event_time ASC
LIMIT 1
RETURN pod.name AS root_component, e.reason AS root_cause, e.message

// 3. Build the causal chain
MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..3]->(symptom:Episodic)
WHERE root.event_time > datetime() - duration({minutes: 30})
  AND symptom.event_time > datetime() - duration({minutes: 30})
WITH path, nodes(path) AS event_chain
UNWIND event_chain AS evt
MATCH (evt)-[:ABOUT]->(res:Resource)
WHERE res.name CONTAINS 'test-'
RETURN [evt IN event_chain | evt.reason] AS causal_chain,
       [res IN [n IN event_chain | (n)-[:ABOUT]->(r) | r] | res.name][0..10] AS affected_resources,
       length(path) AS chain_length
ORDER BY chain_length DESC
LIMIT 5

// 4. Visualize the dependency graph
MATCH (db:Resource {name: 'test-db'})<-[:SELECTS]-(dbsvc:Resource:Service)
MATCH (api:Resource {name: 'test-api'})<-[:SELECTS]-(apisvc:Resource:Service)
MATCH (fe:Resource {name: 'test-frontend'})<-[:SELECTS]-(fesvc:Resource:Service)
OPTIONAL MATCH (db_pod:Resource:Pod)-[:RUNS_ON]->(node:Resource:Node)
WHERE db_pod.labels_kv CONTAINS 'app=db'
RETURN db, dbsvc, api, apisvc, fe, fesvc, db_pod, node

// Expected:
// - DB failure happens first
// - API failure shortly after (POTENTIAL_CAUSE link)
// - Frontend failure last (POTENTIAL_CAUSE link)
// - Clear causal chain visible
```

### Cleanup

```bash
kubectl delete -f test/05-cascading-failure.yaml
```

---

## Test 6: Missing Environment Variable

### Deploy App Expecting Config

```yaml
# test/06-missing-env.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-missing-env
  namespace: default
  labels:
    test: rca-config
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-config
  template:
    metadata:
      labels:
        app: test-config
    spec:
      containers:
        - name: app
          image: busybox
          command:
            - sh
            - -c
            - |
              echo "App starting..."
              if [ -z "$DATABASE_URL" ]; then
                echo "FATAL: Required environment variable DATABASE_URL is not set"
                exit 1
              fi
              echo "Running normally..."
              sleep 3600
          # ← DATABASE_URL not provided!
```

### Expected Behavior

1. Container starts
2. Logs show: "FATAL: Required environment variable DATABASE_URL is not set"
3. Container exits immediately
4. CrashLoopBackOff

### Verification Queries

```cypher
// 1. Find the fatal log
MATCH (e:Episodic {etype: 'k8s.log'})
WHERE e.severity = 'FATAL'
  AND e.message CONTAINS 'environment variable'
  AND e.event_time > datetime() - duration({minutes: 30})
RETURN e.reason, e.message, e.event_time

// 2. Link log to crash
MATCH (log:Episodic {etype: 'k8s.log'})-[:ABOUT]->(pod:Resource)
WHERE log.severity = 'FATAL'
  AND log.message CONTAINS 'environment variable'
WITH log, pod
MATCH (crash:Episodic)-[:ABOUT]->(pod)
WHERE crash.reason CONTAINS 'BackOff'
  AND crash.event_time > log.event_time
  AND crash.event_time < log.event_time + duration({minutes: 5})
RETURN pod.name,
       log.message AS root_cause,
       crash.reason AS symptom,
       duration.between(log.event_time, crash.event_time) AS delay

// 3. Check if POTENTIAL_CAUSE link was created
MATCH (log:Episodic)-[pc:POTENTIAL_CAUSE]->(crash:Episodic)
WHERE log.etype = 'k8s.log'
  AND log.message CONTAINS 'environment variable'
RETURN log.message, crash.reason, pc.hops

// Expected: Fatal log should be linked as potential cause of CrashLoop
```

### Cleanup

```bash
kubectl delete -f test/06-missing-env.yaml
```

---

## Comprehensive Validation Script

Save this as `test/validate-rca.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "  RCA System Validation"
echo "========================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

function check() {
    local name="$1"
    local query="$2"

    echo -n "Checking: $name... "

    # Run cypher query via kubectl exec into Neo4j
    result=$(kubectl exec -n observability neo4j-0 -- \
        cypher-shell -u neo4j -p anuragvishwa "$query" 2>/dev/null || echo "ERROR")

    if echo "$result" | grep -q "ERROR"; then
        echo -e "${RED}FAIL${NC}"
        ((FAIL++))
        return 1
    elif [ -z "$result" ] || echo "$result" | grep -q "0 rows"; then
        echo -e "${YELLOW}WARN (no data)${NC}"
        return 0
    else
        echo -e "${GREEN}PASS${NC}"
        ((PASS++))
        return 0
    fi
}

echo "1. Schema Validation"
echo "--------------------"

check "Resource nodes exist" \
    "MATCH (r:Resource) RETURN count(r) AS cnt LIMIT 1;"

check "Episodic nodes exist" \
    "MATCH (e:Episodic) RETURN count(e) AS cnt LIMIT 1;"

check "ABOUT relationships exist" \
    "MATCH ()-[r:ABOUT]->() RETURN count(r) AS cnt LIMIT 1;"

check "POTENTIAL_CAUSE relationships exist" \
    "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r) AS cnt LIMIT 1;"

echo ""
echo "2. Data Quality"
echo "---------------"

check "Resources have kind" \
    "MATCH (r:Resource) WHERE r.kind IS NOT NULL RETURN count(r) LIMIT 1;"

check "Episodic events have timestamps" \
    "MATCH (e:Episodic) WHERE e.event_time IS NOT NULL RETURN count(e) LIMIT 1;"

check "Pods have namespace" \
    "MATCH (p:Resource:Pod) WHERE p.ns IS NOT NULL RETURN count(p) LIMIT 1;"

echo ""
echo "3. Topology Validation"
echo "----------------------"

check "SELECTS relationships (Service→Pod)" \
    "MATCH (:Resource:Service)-[r:SELECTS]->(:Resource:Pod) RETURN count(r) LIMIT 1;"

check "RUNS_ON relationships (Pod→Node)" \
    "MATCH (:Resource:Pod)-[r:RUNS_ON]->(:Resource:Node) RETURN count(r) LIMIT 1;"

check "CONTROLS relationships (Deployment→Pod)" \
    "MATCH (:Resource:Deployment)-[r:CONTROLS]->() RETURN count(r) LIMIT 1;"

echo ""
echo "4. RCA Functionality"
echo "--------------------"

check "Events linked to resources" \
    "MATCH (e:Episodic)-[:ABOUT]->(r:Resource) RETURN count(*) LIMIT 1;"

check "Causal links created" \
    "MATCH ()-[pc:POTENTIAL_CAUSE]->() WHERE pc.hops IS NOT NULL RETURN count(pc) LIMIT 1;"

check "Recent events (last hour)" \
    "MATCH (e:Episodic) WHERE e.event_time > datetime() - duration({hours: 1}) RETURN count(e) LIMIT 1;"

echo ""
echo "========================================"
echo "  Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}"
echo "========================================"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "Some checks failed. Review logs:"
    echo "  kubectl logs -n observability -l app=kg-builder --tail=100"
    echo "  kubectl logs -n observability -l app=vector --tail=100"
    exit 1
fi
```

Make it executable:
```bash
chmod +x test/validate-rca.sh
```

---

## End-to-End Test Workflow

### 1. Deploy Test Scenarios

```bash
# Create test directory
mkdir -p test

# Deploy all tests (one at a time for clarity)
kubectl apply -f test/01-imagepull-failure.yaml
sleep 60  # Wait for events to propagate

kubectl apply -f test/02-crashloop.yaml
sleep 60

kubectl apply -f test/05-cascading-failure.yaml
sleep 120  # Longer wait for cascade

# Check pods are in expected failed states
kubectl get pods -l test=rca-imagepull
kubectl get pods -l test=rca-crashloop
kubectl get pods -l test=rca-cascade
```

### 2. Verify Events in Kafka

```bash
# Check events.normalized topic
kubectl exec -n observability kafka-0 -- \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic events.normalized --from-beginning --max-messages 10

# Check logs.normalized topic
kubectl exec -n observability kafka-0 -- \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic logs.normalized --from-beginning --max-messages 10
```

### 3. Run Validation Script

```bash
./test/validate-rca.sh
```

### 4. Manual Neo4j Verification

```bash
# Port-forward Neo4j
kubectl port-forward -n observability svc/neo4j-external 7474:7474

# Open browser: http://localhost:7474
# Run queries from each test scenario above
```

### 5. Cleanup

```bash
# Remove all test deployments
kubectl delete deployment -l test=rca-imagepull
kubectl delete deployment -l test=rca-crashloop
kubectl delete deployment -l test=rca-cascade
kubectl delete deployment -l test=rca-service
kubectl delete deployment -l test=rca-oom
kubectl delete deployment -l test=rca-config

kubectl delete service test-imagepull test-crashloop test-backend test-db test-api test-frontend
```

---

## Success Criteria

Your RCA system is working correctly if:

✅ **Events are captured**
- All K8s events appear in Neo4j as `Episodic` nodes
- Logs (ERROR/FATAL) appear as `Episodic` nodes
- Events linked to correct resources via `ABOUT`

✅ **Topology is correct**
- Pods linked to Services via `SELECTS`
- Pods linked to Deployments via `CONTROLS`
- Pods linked to Nodes via `RUNS_ON`

✅ **Causal links work**
- `POTENTIAL_CAUSE` relationships created
- Earlier events linked to later events
- Distance (hops) calculated correctly

✅ **Root cause identification**
- Queries can find root cause of failures
- Cascading failures show correct chain
- Time ordering is preserved

✅ **No data loss**
- All test events appear in graph
- Timestamps are correct
- No duplicate events (or deduplication working)

## Next Steps

After validating RCA works:

1. **Tune RCA parameters** in `.env`:
   ```bash
   RCA_WINDOW_MIN=30  # Expand time window if needed
   CAUSAL_LINK_MAX_HOPS=5  # Increase for deeper chains
   ```

2. **Add custom failure patterns** specific to your apps

3. **Integrate with alerting** (send Neo4j RCA results to Slack/PagerDuty)

4. **Build RCA dashboard** (Grafana + Neo4j plugin)

5. **Prepare for Phase 2** (Historical FEKG learning)
