# Installation Test Guide

Quick guide to test the KG RCA Agent installation on your Kubernetes cluster.

## Test Environment Setup

You'll need:
- A Kubernetes cluster (can be Minikube, kind, or real cluster)
- KG RCA Server running and accessible
- kubectl and Helm installed

## Option 1: Test on Minikube (Local)

```bash
# Start Minikube
minikube start --cpus=4 --memory=8192

# Verify cluster
kubectl cluster-info

# Set server IP (your mini-server)
SERVER_IP="3.93.235.47"

# Create test values
cat > test-values.yaml <<EOF
client:
  id: "test-minikube"
  kafka:
    bootstrapServers: "${SERVER_IP}:9092"

vector:
  enabled: true
eventExporter:
  enabled: true
stateWatcher:
  enabled: true
prometheusAgent:
  enabled: false
EOF

# Install
helm install kg-rca-agent helm-chart/kg-rca-agent \
  --values test-values.yaml \
  --namespace observability \
  --create-namespace

# Watch pods start
kubectl get pods -n observability -w
```

## Option 2: Test on Real Cluster

```bash
# Verify cluster access
kubectl get nodes

# Create values file with your server
cat > prod-test-values.yaml <<EOF
client:
  id: "test-prod-cluster"
  kafka:
    bootstrapServers: "3.93.235.47:9092"  # Replace with your server

# Optional: limit to specific namespaces for testing
monitoredNamespaces: ["default", "test"]
EOF

# Install
helm install kg-rca-agent helm-chart/kg-rca-agent \
  --values prod-test-values.yaml \
  --namespace observability \
  --create-namespace
```

## Verification Steps

### 1. Check Pod Status

```bash
kubectl get pods -n observability

# Expected output:
# NAME                                           READY   STATUS    RESTARTS   AGE
# kg-rca-agent-vector-xxxxx                     1/1     Running   0          1m
# kg-rca-agent-event-exporter-xxxxxxxxxx-xxxxx  1/1     Running   0          1m
# kg-rca-agent-state-watcher-xxxxxxxxxx-xxxxx   1/1     Running   0          1m
```

### 2. Check Vector Logs

```bash
kubectl logs -n observability -l app=vector --tail=50

# Should see:
# - "Successfully connected to Kafka"
# - "Sending logs to topic: events.normalized"
# - No error messages
```

### 3. Check Event Exporter

```bash
kubectl logs -n observability -l app=event-exporter --tail=50

# Should see:
# - "Watching Kubernetes events"
# - "Sent event to Kafka"
```

### 4. Check State Watcher

```bash
kubectl logs -n observability -l app=state-watcher --tail=50

# Should see:
# - "Watching resources: Pod, Deployment, Service..."
# - "Sent resource state to Kafka"
```

### 5. Generate Test Events

Create some activity in the cluster:

```bash
# Create a test pod that will crash
kubectl run test-crash --image=busybox --command -- /bin/sh -c "exit 1"

# Create a test deployment
kubectl create deployment test-nginx --image=nginx --replicas=2

# Wait a moment
sleep 10

# Check that events were captured
kubectl logs -n observability -l app=event-exporter --tail=20 | grep test
```

### 6. Verify Data on Server

SSH to your KG RCA Server:

```bash
# Check Kafka topics
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic events.normalized \
  --max-messages 5

# Check Neo4j for your cluster's data
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "MATCH (n:Pod) WHERE n.name CONTAINS 'test' RETURN n.name, n.namespace, n.uid LIMIT 10"

# Check KG API stats
curl -s http://localhost:8080/api/v1/graph/stats | python3 -m json.tool
```

## Troubleshooting

### Pods CrashLoopBackOff

```bash
kubectl describe pod -n observability <pod-name>
kubectl logs -n observability <pod-name> --previous
```

Common causes:
- Wrong Kafka bootstrap server address
- Network policy blocking egress
- Insufficient resources

### No Data Reaching Server

```bash
# Test network connectivity from Vector pod
kubectl exec -n observability -it \
  $(kubectl get pod -n observability -l app=vector -o name | head -1) \
  -- sh -c "nc -zv 3.93.235.47 9092"

# Check if Kafka topic exists on server
ssh your-server "docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list | grep normalized"
```

### ImagePullBackOff

If pods can't pull images:

```bash
# Check if images exist (they should be built on server)
docker images | grep -E "vector|event-exporter|state-watcher"

# If using private registry, create pull secret
kubectl create secret docker-registry regcred \
  --docker-server=your-registry.com \
  --docker-username=user \
  --docker-password=pass \
  --namespace=observability
```

## Cleanup

```bash
# Uninstall chart
helm uninstall kg-rca-agent --namespace observability

# Delete namespace
kubectl delete namespace observability

# Clean up test resources
kubectl delete pod test-crash
kubectl delete deployment test-nginx
```

## Success Criteria

✅ All 3 pods running (Vector, Event Exporter, State Watcher)
✅ No error logs in any pod
✅ Network connectivity to Kafka server confirmed
✅ Events appearing in Kafka topics on server
✅ Resources visible in Neo4j on server
✅ KG API showing non-zero counts

## Next Steps After Successful Test

1. Document your specific configuration
2. Create production values file with SSL
3. Deploy to production clusters
4. Set up monitoring alerts
5. Configure backup procedures
