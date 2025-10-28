# Installation Test Guide

Quick guide to test the KG RCA Agent installation on your Kubernetes cluster.

## Pre-Flight: Test Server Connectivity FIRST

**Before installing anything**, verify you can reach the KG RCA Server:

```bash
# Set your server IP (use the Elastic IP!)
SERVER_IP="98.90.147.12"

# Test 1: Basic ping (may timeout on AWS - that's OK!)
ping -c 3 $SERVER_IP
# Note: AWS often blocks ICMP, so timeout is normal

# Test 2: Check Kafka port (9092) - THIS IS THE CRITICAL TEST
nc -zv $SERVER_IP 9092
# Expected: "succeeded!" or "open"

# Test 3: Check if port is open (alternative method)
timeout 5 bash -c "</dev/tcp/$SERVER_IP/9092" && echo "✅ Kafka port 9092 is reachable" || echo "❌ Cannot connect to Kafka port 9092"

# Test 4: Check KG API port (if exposed)
curl -s http://$SERVER_IP:8080/api/v1/graph/stats || echo "API not accessible (may be normal if not exposed)"

# Test 5: From inside your Kubernetes cluster
kubectl run test-connectivity --image=busybox --rm -it --restart=Never -- \
  sh -c "nc -zv $SERVER_IP 9092 && echo 'SUCCESS' || echo 'FAILED'"
```

### Expected Results

✅ **Good to proceed:**

- Ping succeeds (shows server is online)
- Port 9092 shows "succeeded" or "open"
- Kubernetes pod can reach the server

❌ **Don't proceed yet - troubleshoot first:**

- Connection timeout
- Connection refused
- "No route to host"

### Common Connectivity Issues

**Issue: Connection timeout**

```bash
# Check if AWS security group allows your IP
# Go to AWS Console → EC2 → Security Groups
# The server's security group should allow:
# - Port 9092 (Kafka) from your cluster's egress IPs
# - Port 22 (SSH) from your IP for management
```

**Issue: Connection refused**

```bash
# Check if Kafka is actually running on server
ssh -i your-key.pem ec2-user@$SERVER_IP "docker ps | grep kafka"

# Check if Kafka is listening on correct interface
ssh -i your-key.pem ec2-user@$SERVER_IP "docker exec kg-kafka ss -tlnp | grep 9092"
```

**Issue: From Kubernetes pod but not from local machine**

- This is normal if your cluster has different egress IPs
- Ensure server security group allows cluster's NAT gateway IPs

---

## Test Environment Setup

You'll need:

- A Kubernetes cluster (can be Minikube, kind, or real cluster)
- KG RCA Server running and accessible
- kubectl and Helm installed
- **✅ Server connectivity verified** (see above)

## Option 1: Test on Minikube (Local)

```bash
# Start Minikube
minikube start --cpus=4 --memory=8192

# Verify cluster
kubectl cluster-info

# Set server IP (your mini-server)
SERVER_IP="98.90.147.12"

# Create test values
cat > test-values.yaml <<EOF
client:
  id: "test-minikube"
  kafka:
    brokers: "${SERVER_IP}:9092"
stateWatcher:
  prometheusUrl: "http://kube-prometheus-stack-prometheus.monitoring.svc:9090"  # Update if service name differs

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
    brokers: "98.90.147.12:9092"  # Replace with your server
stateWatcher:
  prometheusUrl: "http://kube-prometheus-stack-prometheus.monitoring.svc:9090"

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
# kg-rca-agent-alert-receiver-xxxxxxxxxx-xxxxx  1/1     Running   0          1m
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
# - "prom targets" log lines confirming `/api/v1/targets` sync
```

### 5. Check Alert Receiver

```bash
kubectl logs -n observability -l component=alert-receiver --tail=50
```

Expected:
- Starts consumer group `alerts-enricher-<client-id>`
- Prints `Connected to Kafka` and `Subscribed to topics`

> **Next:** Add the Alertmanager webhook URL  
> Grab the service name:
> ```bash
> kubectl get svc -n observability -l component=alert-webhook
> ```
> Then configure Alertmanager:
> `http://<service>.<namespace>.svc:9090/alerts`

### 6. Generate Test Events

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

#
# Alertmanager Integration (optional)
#

To forward Prometheus alerts to Kafka via the client’s alert-receiver, add a webhook receiver in Alertmanager.

- Service URL (in-cluster):
  - `http://kg-rca-agent-kg-rca-agent-alert-receiver.observability.svc:8080/alerts`

Example (kube-prometheus-stack values):

```yaml
alertmanager:
  config:
    route:
      receiver: kg-rca-agent
    receivers:
      - name: kg-rca-agent
        webhook_configs:
          - url: "http://kg-rca-agent-kg-rca-agent-alert-receiver.observability.svc:8080/alerts"
```

Quick test without changing Alertmanager (sends a sample alert):

```bash
kubectl -n observability run curl-tmp --rm -it \
  --image=curlimages/curl:8.5.0 --restart=Never -- \
  curl -sS -X POST \
  -H 'Content-Type: application/json' \
  -d '[{"status":"firing","labels":{"alertname":"TestAlert","severity":"warning"},"annotations":{"summary":"test"},"startsAt":"2025-01-01T00:00:00Z"}]' \
  http://kg-rca-agent-kg-rca-agent-alert-receiver.observability.svc:8080/alerts

# Then verify on the server
ssh mini-server 'docker exec -it kg-kafka sh -lc \
  "/opt/kafka/bin/kafka-run-class.sh kafka.tools.GetOffsetShell --broker-list localhost:9092 --topic alerts.raw --time -1"'
```

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
  -- sh -c "nc -zv 98.90.147.12 9092"

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
