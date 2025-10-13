# KGroot Client - Kubernetes Observability Collector

**Deploy to any Kubernetes cluster to send observability data to KGroot Server**

This client package deploys lightweight collectors that watch your Kubernetes cluster and send events, logs, and alerts to a KGroot server for knowledge graph-based root cause analysis.

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [What Gets Deployed](#what-gets-deployed)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Connecting to Mini-Server](#connecting-to-mini-server)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)
- [Uninstallation](#uninstallation)

---

## 🚀 Quick Start

### 1. Get Server Connection Info

From your KGroot server (mini-server), get the Kafka endpoint:

```bash
# SSH to mini-server
ssh mini-server "curl -s http://169.254.169.254/latest/meta-data/public-ipv4"
# Example output: 54.123.45.67
```

Your Kafka endpoint will be: `54.123.45.67:9092`

### 2. Install with Helm

```bash
# Add your cluster name and server endpoint
helm install kgroot-client ./helm-chart/kg-client \
  --set global.clusterName="my-cluster" \
  --set server.kafka.brokers="54.123.45.67:9092" \
  --create-namespace
```

### 3. Verify Deployment

```bash
# Check all components are running
kubectl get pods -n kgroot-client

# Expected output:
# NAME                           READY   STATUS    RESTARTS   AGE
# kg-client-event-exporter-xxx   1/1     Running   0          1m
# kg-client-vector-xxx           1/1     Running   0          1m
# kg-client-vector-yyy           1/1     Running   0          1m
```

### 4. Configure Prometheus Alertmanager (Optional)

To send alerts to KGroot:

```bash
# Get Vector webhook URL
kubectl get svc -n kgroot-client kg-client-vector

# Add to Alertmanager configuration:
# receivers:
#   - name: 'kgroot'
#     webhook_configs:
#       - url: 'http://kg-client-vector.kgroot-client.svc:9090/alerts'
```

---

## 📦 What Gets Deployed

This Helm chart deploys three components:

### 1. **Event Exporter** (Deployment - 1 replica)
- **What**: Watches Kubernetes events (pod crashes, scheduling issues, etc.)
- **Output**: `raw.k8s.events` topic
- **Resources**: 50m CPU, 64Mi RAM

### 2. **Vector** (DaemonSet - 1 per node)
- **What**: Collects pod logs from all nodes
- **Output**: `raw.k8s.logs` topic
- **Features**:
  - Filters by log level (ERROR, WARN, INFO)
  - Excludes system namespaces
  - Receives Prometheus alerts via webhook
- **Resources**: 100m CPU, 128Mi RAM per node

### 3. **RBAC** (ServiceAccount, ClusterRole, ClusterRoleBinding)
- **What**: Read-only permissions for events, pods, logs
- **Scope**: Cluster-wide (read-only)

---

## ✅ Prerequisites

### Client Side (Kubernetes Cluster)
- Kubernetes 1.20+
- Helm 3.0+
- kubectl configured
- Network access to KGroot server on port 9092

### Server Side (KGroot Mini-Server)
- Running Kafka on port 9092
- Port 9092 accessible from your cluster
- Topics created (auto-created if not exist)

### Network Requirements
```bash
# Test connectivity from your cluster
kubectl run test-kafka --rm -it --image=busybox --restart=Never -- \
  nc -zv YOUR_SERVER_IP 9092

# Should output: Connection successful
```

---

## 🔧 Installation

### Option 1: Quick Install (Default Settings)

```bash
cd client/helm-chart

helm install kgroot-client ./kg-client \
  --set global.clusterName="production" \
  --set server.kafka.brokers="54.123.45.67:9092"
```

### Option 2: Custom Values File

Create `my-values.yaml`:

```yaml
global:
  clusterName: "my-production-cluster"

server:
  kafka:
    brokers: "kafka.mycompany.com:9092"
    # For production with authentication:
    sasl:
      enabled: true
      mechanism: "PLAIN"
      username: "kgroot-client"
      password: "secure-password"

vector:
  logCollection:
    # Only collect ERROR and FATAL logs
    levels:
      - ERROR
      - FATAL
    # Exclude more namespaces
    excludeNamespaces:
      - kube-system
      - kube-public
      - monitoring
      - logging

eventExporter:
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
```

Install with custom values:

```bash
helm install kgroot-client ./kg-client -f my-values.yaml
```

### Option 3: Install in Custom Namespace

```bash
helm install kgroot-client ./kg-client \
  --set global.clusterName="staging" \
  --set server.kafka.brokers="54.123.45.67:9092" \
  --set namespace="observability" \
  --namespace observability \
  --create-namespace
```

---

## ⚙️ Configuration

### Key Configuration Options

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `global.clusterName` | Identifier for this cluster | `my-cluster` | **YES** |
| `server.kafka.brokers` | Kafka broker endpoint | `localhost:9092` | **YES** |
| `server.kafka.sasl.enabled` | Enable SASL auth | `false` | No |
| `vector.enabled` | Deploy log collector | `true` | No |
| `eventExporter.enabled` | Deploy event watcher | `true` | No |
| `vector.logCollection.levels` | Log levels to collect | `[ERROR,WARN,INFO]` | No |

### Full Configuration Reference

See [`helm-chart/kg-client/values.yaml`](helm-chart/kg-client/values.yaml) for all options.

---

## 🔌 Connecting to Mini-Server

### Step 1: Get Mini-Server Public IP

```bash
# If using AWS EC2
ssh mini-server "curl -s http://169.254.169.254/latest/meta-data/public-ipv4"

# Or check your cloud provider's console
# Example: 54.123.45.67
```

### Step 2: Verify Port 9092 is Accessible

```bash
# On mini-server, check Kafka is listening
ssh mini-server "docker exec kgroot-latest-kafka-1 \
  kafka-topics.sh --bootstrap-server localhost:9092 --list"

# Check security group/firewall allows port 9092 from your cluster
```

### Step 3: Test Connectivity from Cluster

```bash
# Run test pod
kubectl run kafka-test --rm -it --image=busybox --restart=Never -- \
  nc -zv 54.123.45.67 9092

# Should see: 54.123.45.67 (54.123.45.67:9092) open
```

### Step 4: Install Client

```bash
helm install kgroot-client ./helm-chart/kg-client \
  --set global.clusterName="prod-cluster" \
  --set server.kafka.brokers="54.123.45.67:9092"
```

### Step 5: Verify on Server

```bash
# On mini-server, check consumer groups
ssh mini-server "docker exec kgroot-latest-kafka-1 \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list"

# Should see: kg-builder, alerts-enricher

# Check messages are flowing
ssh mini-server "docker exec kgroot-latest-kafka-1 \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group kg-builder --describe"

# Look for LAG = 0 (messages being consumed)
```

---

## ✓ Verification

### 1. Check Pod Status

```bash
kubectl get pods -n kgroot-client
```

**Expected output:**
```
NAME                                        READY   STATUS    RESTARTS   AGE
kg-client-event-exporter-7d8f9c5b6d-abcde  1/1     Running   0          2m
kg-client-vector-xxxxx                      1/1     Running   0          2m
kg-client-vector-yyyyy                      1/1     Running   0          2m
```

### 2. Check Logs

```bash
# Event Exporter logs
kubectl logs -n kgroot-client deployment/kg-client-event-exporter

# Vector logs (pick any pod)
kubectl logs -n kgroot-client ds/kg-client-vector
```

### 3. Verify Data Flow on Server

```bash
# Check topics have messages
ssh mini-server "
docker exec kgroot-latest-kafka-1 kafka-run-class.sh kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic raw.k8s.events \
  --time -1
"

# Output shows message counts per partition:
# raw.k8s.events:0:123
# raw.k8s.events:1:456
# raw.k8s.events:2:789
```

### 4. Check Graph Builder is Processing

```bash
ssh mini-server "docker logs kgroot-latest-graph-builder-1 --tail 50"

# Should see log processing messages
```

### 5. Query Neo4j

```bash
# On mini-server or local machine
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (n) RETURN count(n) AS total_nodes"

# Should return growing number of nodes
```

---

## 🔍 Troubleshooting

### Issue: Pods Not Starting

```bash
# Check pod events
kubectl describe pod -n kgroot-client <pod-name>

# Common issues:
# - Image pull errors: Check image repository access
# - RBAC errors: Ensure RBAC is enabled (--set rbac.create=true)
```

### Issue: No Data Flowing to Server

**1. Check pod logs for errors:**
```bash
kubectl logs -n kgroot-client deployment/kg-client-event-exporter
kubectl logs -n kgroot-client ds/kg-client-vector
```

**2. Test Kafka connectivity:**
```bash
kubectl run kafka-test --rm -it --image=confluentinc/cp-kafka:7.0.0 --restart=Never -- \
  kafka-topics --bootstrap-server YOUR_SERVER_IP:9092 --list

# Should list topics: raw.k8s.events, raw.k8s.logs, etc.
```

**3. Check firewall/security groups:**
- Ensure server's security group allows inbound TCP 9092 from your cluster
- If using AWS, add your cluster's NAT gateway IPs

**4. Verify Kafka advertised listeners:**
```bash
ssh mini-server "docker exec kgroot-latest-kafka-1 env | grep KAFKA_ADVERTISED"

# Should show: KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092
# For external access, may need to add: PLAINTEXT_HOST://PUBLIC_IP:9092
```

### Issue: High CPU/Memory Usage

**Vector consuming too much:**
```bash
# Reduce log collection scope
helm upgrade kgroot-client ./kg-client \
  --reuse-values \
  --set vector.logCollection.levels="{ERROR,FATAL}" \
  --set vector.logCollection.excludeNamespaces="{kube-system,monitoring,logging}"
```

### Issue: Messages Not Being Consumed on Server

```bash
# Check consumer groups on server
ssh mini-server "docker exec kgroot-latest-kafka-1 \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list"

# Check graph-builder is running
ssh mini-server "docker ps | grep graph-builder"

# Check graph-builder logs
ssh mini-server "docker logs kgroot-latest-graph-builder-1 --tail 50"
```

### Debug Mode

Enable debug logging:

```bash
helm upgrade kgroot-client ./kg-client \
  --reuse-values \
  --set vector.logLevel=debug \
  --set eventExporter.logLevel=debug
```

---

## 🗑️ Uninstallation

### Remove Client from Cluster

```bash
# Uninstall Helm release
helm uninstall kgroot-client -n kgroot-client

# Remove namespace (if desired)
kubectl delete namespace kgroot-client
```

### Clean Up Server Side

```bash
# Optional: Delete topics on server
ssh mini-server "
docker exec kgroot-latest-kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --delete --topic raw.k8s.events

docker exec kgroot-latest-kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --delete --topic raw.k8s.logs
"
```

---

## 📚 Additional Resources

- **Server Setup**: See `/saas/server_mini/README.md`
- **Architecture**: See main `/README.md`
- **Query Library**: See `/production/neo4j-queries/QUERY_LIBRARY.md`
- **Validation**: See `/validation/README.md`

---

## 🐛 Getting Help

1. **Check Logs**: Always start with pod logs
2. **Network Test**: Verify connectivity to Kafka
3. **Server Health**: Check server components are running
4. **GitHub Issues**: Report bugs or ask questions

---

## 📝 Example End-to-End Test

```bash
# 1. Deploy client
helm install kgroot-client ./helm-chart/kg-client \
  --set global.clusterName="test" \
  --set server.kafka.brokers="54.123.45.67:9092"

# 2. Wait for pods
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=kg-client \
  -n kgroot-client \
  --timeout=120s

# 3. Generate test event
kubectl run test-pod --image=busybox --restart=Never -- /bin/sh -c "exit 1"

# 4. Check event was captured
kubectl logs -n kgroot-client deployment/kg-client-event-exporter | grep test-pod

# 5. Verify on server
ssh mini-server "
docker exec kgroot-latest-kafka-1 \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic raw.k8s.events \
  --from-beginning \
  --max-messages 1 | grep test-pod
"

# 6. Clean up
kubectl delete pod test-pod
```

---

**Status**: ✅ Ready for production use

**Version**: 1.0.0

**Last Updated**: 2025-10-11
