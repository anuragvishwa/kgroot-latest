# Troubleshooting Guide

## Quick Fix Steps

### 1. Minikube Cluster Issues

**Symptom:** `Unable to connect to the server: TLS handshake timeout`

**Fix:**
```bash
# Restart Minikube
minikube stop
minikube start

# Wait for cluster to be ready
kubectl get nodes

# Check all pods
kubectl get pods -A
```

### 2. Neo4j Not Running

**Symptom:** `Neo4j not running. Deploy Neo4j first.`

**Fix:**
```bash
# Deploy Neo4j
kubectl apply -f k8s/neo4j.yaml

# Wait for Neo4j to be ready (takes ~60-90 seconds)
kubectl wait --for=condition=ready pod -l app=neo4j -n observability --timeout=180s

# Check Neo4j logs
kubectl logs -n observability neo4j-0 --tail=30

# Look for: "Bolt enabled" and "Started"
```

**Common Neo4j Issues:**

**(A) Config Validation Error:**
```
Failed to read config: Unrecognized setting
```
Fix: Already applied in k8s/neo4j.yaml (strict validation disabled)

**(B) Container Crashes:**
```bash
# Check logs
kubectl logs -n observability neo4j-0

# If APOC plugin issues, the fix is already in neo4j.yaml:
# NEO4J_server_config_strict__validation_enabled: "false"

# Delete and recreate
kubectl delete statefulset neo4j -n observability
kubectl apply -f k8s/neo4j.yaml
```

### 3. kg-builder ImagePullBackOff

**Symptom:** `ErrImagePull` or `ImagePullBackOff` on kg-builder pod

**Fix:**
```bash
# Build the image
cd kg
go mod download
go mod tidy

# Build Docker image
docker build -t anuragvishwa/kg-builder:latest .

# Load into Minikube
minikube image load anuragvishwa/kg-builder:latest

# Verify image is loaded
minikube image ls | grep kg-builder

# Delete old pod to force recreation
kubectl delete pod -n observability -l app=kg-builder

# Check new pod
kubectl get pods -n observability -l app=kg-builder
```

### 4. No Messages in Kafka Topics

**Symptom:** Topics exist but have 0 messages

**Fix:**
```bash
# Check if Vector is running
kubectl logs -n observability -l app=vector --tail=30

# Check if state-watcher is running
kubectl logs -n observability -l app=state-watcher --tail=30

# Common issue: Services not started yet
# Wait 2-3 minutes after deployment

# Generate test events
kubectl apply -f test/05-cascading-failure.yaml

# Wait 60 seconds
sleep 60

# Check messages
kubectl exec -n observability kafka-0 -- \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic events.normalized --from-beginning --max-messages 5
```

### 5. Empty Knowledge Graph (No Nodes in Neo4j)

**Symptom:** Neo4j running but no nodes when querying

**Fix:**
```bash
# Check kg-builder is running
kubectl get pods -n observability -l app=kg-builder

# Check kg-builder logs for errors
kubectl logs -n observability -l app=kg-builder --tail=50

# Common issues:

# (A) kg-builder can't connect to Kafka
# Look for: "kafka: client has run out of available brokers"
# Fix: Check KAFKA_BROKERS in ConfigMap
kubectl get configmap kgroot-env -n observability -o yaml | grep KAFKA

# (B) kg-builder can't connect to Neo4j
# Look for: "neo4j: connection refused"
# Fix: Check NEO4J_URI
kubectl get configmap kgroot-env -n observability -o yaml | grep NEO4J

# Should be: neo4j://neo4j.observability.svc:7687

# (C) Schema not created
# Look for: "ensure schema" in logs
# Fix: Manually trigger schema creation
kubectl exec -n observability kafka-0 -- \
  kafka-console-producer.sh --bootstrap-server localhost:9092 \
  --topic graph.commands \
  --property "parse.key=true" \
  --property "key.separator=|"

# Type: cmd|{"op":"ENSURE_SCHEMA"}
# Press Ctrl+D

# (D) No events to process
# Generate test events
kubectl apply -f test/02-crashloop.yaml
sleep 60
```

### 6. Consumer Groups Not Working

**Symptom:** Consumer lag is increasing or consumer group doesn't exist

**Fix:**
```bash
# List all consumer groups
kubectl exec -n observability kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list

# Expected groups:
# - kg-builder
# - alerts-enricher-alerts

# Check specific group
kubectl exec -n observability kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group kg-builder --describe

# If group doesn't exist:
# 1. Check if kg-builder pod is running
# 2. Check kg-builder logs
# 3. Wait 1-2 minutes for consumer to register
```

### 7. vector-logs CrashLoopBackOff

**Symptom:** vector-logs DaemonSet pods crashing

**Fix:**
```bash
# Check logs
kubectl logs -n observability -l app=vector-logs --tail=50

# Common issues:

# (A) Can't access node logs
# Vector needs hostPath volumes
# Check vector-configmap.yaml has correct volume mounts

# (B) Kafka connection issues
# Check KAFKA_BOOTSTRAP env var

# (C) Permissions
# Vector needs proper RBAC
kubectl get clusterrolebinding vector-logs

# If missing, reapply
kubectl apply -f k8s/vector-configmap.yaml
```

## Verification Checklist

Run this after fixing issues:

```bash
# 1. All pods running?
kubectl get pods -n observability

# Expected Running pods:
# - kafka-0
# - neo4j-0
# - kg-builder-*
# - vector-*
# - vector-logs-* (DaemonSet)
# - state-watcher-*
# - alerts-enricher-*

# 2. Kafka topics exist?
kubectl exec -n observability kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list

# Expected: 15+ topics

# 3. Neo4j accessible?
kubectl exec -n observability neo4j-0 -- \
  cypher-shell -u neo4j -p anuragvishwa "RETURN 1 AS test;"

# Expected: "test" "1"

# 4. Knowledge graph has data?
kubectl exec -n observability neo4j-0 -- \
  cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (n) RETURN count(n) AS total;"

# Expected: total > 0

# 5. Consumers active?
kubectl exec -n observability kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list

# Expected: kg-builder, alerts-enricher-alerts

# 6. Run full verification
./VERIFY_DEPLOYMENT.sh
```

## Complete Redeployment

If nothing works, start fresh:

```bash
# 1. Delete everything
kubectl delete namespace observability

# Wait for deletion
kubectl get namespace observability
# (should show "No resources found")

# 2. Redeploy
./deploy-all.sh

# 3. Wait 5-10 minutes

# 4. Verify
./VERIFY_DEPLOYMENT.sh
```

## Getting Help

### Check Logs

```bash
# kg-builder (graph construction)
kubectl logs -n observability -l app=kg-builder -f

# Vector (event ingestion)
kubectl logs -n observability -l app=vector -f

# state-watcher (K8s resources)
kubectl logs -n observability -l app=state-watcher -f

# Neo4j (database)
kubectl logs -n observability neo4j-0 -f

# Kafka (message broker)
kubectl logs -n observability kafka-0 -f
```

### Check Configuration

```bash
# View ConfigMap
kubectl get configmap kgroot-env -n observability -o yaml

# Important values:
# - KAFKA_BROKERS: kafka.observability.svc:9092
# - NEO4J_URI: neo4j://neo4j.observability.svc:7687
# - NEO4J_USER: neo4j
# - NEO4J_PASS: anuragvishwa
```

### Test Components Individually

```bash
# Test Kafka
kubectl exec -n observability kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list

# Test Neo4j
kubectl port-forward -n observability svc/neo4j-external 7474:7474
# Open http://localhost:7474

# Test Vector
kubectl exec -n observability -it $(kubectl get pod -n observability -l app=vector -o name) -- sh
# Inside container: curl http://localhost:8686/health
```

## Common Error Messages

| Error | Meaning | Fix |
|-------|---------|-----|
| `connection refused` | Service not reachable | Check service name, wait for pod to be ready |
| `ImagePullBackOff` | Can't pull Docker image | Build and load image into minikube |
| `CrashLoopBackOff` | Container keeps crashing | Check logs for errors |
| `Pending` | Pod can't be scheduled | Check PVC, resources, node capacity |
| `UnknownTopicOrPartition` | Kafka topic doesn't exist | Create topics with kafka-init or manually |
| `No available brokers` | Can't connect to Kafka | Check KAFKA_BROKERS config, Kafka pod status |
| `Neo4j connection failed` | Can't connect to Neo4j | Check NEO4J_URI, Neo4j pod status |
| `Schema validation failed` | Neo4j config error | Fixed in neo4j.yaml (strict validation disabled) |

## Still Having Issues?

1. **Check all files are up to date:**
   ```bash
   cd /Users/anuragvishwa/Anurag/kgroot_latest
   git status
   ```

2. **Ensure Minikube has enough resources:**
   ```bash
   minikube config set memory 8192
   minikube config set cpus 4
   minikube delete
   minikube start
   ```

3. **Run the verification script:**
   ```bash
   ./VERIFY_DEPLOYMENT.sh
   ```

4. **Check documentation:**
   - `README.md` - Full documentation
   - `QUICK_START.md` - Getting started guide
   - `RCA_TESTING_GUIDE.md` - Testing guide
