# KG-RCA Platform v2.0.0 - Control Plane Architecture

## 🚀 Zero-Touch Multi-Tenant Operations

The KG-RCA platform now features **automatic cluster discovery** and **dynamic graph-builder spawning** through a centralized Control Plane. No more manual configuration or deployment of graph-builders per cluster!

---

## ✨ What's New in v2.0.0

### 🎯 Key Features

- ✅ **Zero-Touch Operations** - `helm install` automatically registers and spawns graph-builders
- ✅ **Auto-Discovery** - Control plane detects new clusters via Kafka registry topic
- ✅ **Self-Healing** - Crashed containers automatically restart
- ✅ **Heartbeat Monitoring** - Stale clusters detected and cleaned up (2min → stale, 5min → cleanup)
- ✅ **Multi-Cluster Support** - Single server handles unlimited Kubernetes clusters
- ✅ **Prometheus Metrics** - Complete observability of cluster lifecycle

### 📊 Architecture

```
┌────────────────────────────────────────────────────────┐
│ Kubernetes Clusters (af-7, af-8, ...)                 │
│ ┌────────────┐  ┌────────────┐                        │
│ │ State      │  │ Event      │ Send data + heartbeats │
│ │ Watcher    │  │ Exporter   │ every 30 seconds       │
│ └─────┬──────┘  └─────┬──────┘                        │
└───────┼─────────────────┼─────────────────────────────┘
        │                 │
        └────────┬────────┘
                 ▼
      ┌──────────────────┐
      │  Kafka Broker     │ - cluster.registry (compacted)
      │  (KRaft mode)     │ - cluster.heartbeat (1h retention)
      └────────┬──────────┘ - state.k8s.resource
               │             - events.normalized
               │
    ┌──────────┴──────────┐
    ▼                     ▼
┌─────────────┐   ┌────────────────────┐
│ Control     │   │ Graph Builders      │
│ Plane       │   │ (Auto-spawned)      │
│ Manager     │   │ - kg-builder-af-7   │
│             │   │ - kg-builder-af-8   │
│ • Registry  │   │ - ...               │
│ • Heartbeat │   │                     │
│ • Reconcile │   │ Each isolated by    │
│ • Spawn     │   │ client_id filter    │
│ • Cleanup   │   │                     │
└──────┬──────┘   └─────────┬───────────┘
       │                    │
       └──────────┬─────────┘
                  ▼
          ┌──────────────┐
          │   Neo4j DB   │ Single shared database
          │              │ with client_id isolation
          └──────────────┘
```

---

## 📋 System Components

### Core Services (Docker)

| Service | Port | Description |
|---------|------|-------------|
| **kg-kafka** | 9092 | Message broker (KRaft mode, no Zookeeper) |
| **kg-neo4j** | 7474, 7687 | Graph database |
| **kg-control-plane** | 9090 | Auto-discovery & spawning (NEW!) |
| **kg-alertmanager** | 9093 | Alert aggregation |
| **kg-alert-receiver** | 8080 | Alert processing |
| **kg-kafka-ui** | 7777 | Kafka web UI |
| **kg-graph-builder-{id}** | - | Auto-spawned per cluster |

### Client Components (Kubernetes)

| Component | Purpose |
|-----------|---------|
| **state-watcher** | Watches K8s resources, sends to Kafka + heartbeats |
| **event-exporter** | Exports K8s events to Kafka |
| **vector** (optional) | Log collection |

---

## 🚀 Quick Start

### Prerequisites

- **Server**: Ubuntu 20.04/22.04/24.04 LTS
- **Resources**: Minimum 4GB RAM, 2 vCPUs (Recommended: 8GB RAM, 4 vCPUs)
- **Disk**: 50GB+ SSD
- **Docker**: 24.0+ with Compose v2
- **Network**: Open port 9092 for Kafka

### 1. Deploy Infrastructure (Mini-Server)

```bash
# Clone repository
git clone https://github.com/anuragvishwa/kgroot-latest.git
cd kgroot-latest/mini-server-prod

# Start all services with control plane
docker compose -f docker-compose-control-plane.yml up -d

# Wait 60 seconds for services to be healthy
sleep 60

# Verify all services are running
docker ps | grep kg-

# Check control plane metrics
curl http://localhost:9090/metrics | grep kg_control_plane
```

### 2. Deploy Client Agents (Kubernetes Clusters)

```bash
# Add Helm repository
helm repo add anuragvishwa https://anuragvishwa.github.io/kgroot-latest/
helm repo update

# Install on each cluster (change client.id for each cluster)
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.0.2 \
  --namespace observability \
  --create-namespace \
  --set client.id="af-7" \
  --set client.kafka.brokers="YOUR_SERVER_IP:9092"

# Verify installation
kubectl get pods -n observability
```

### 3. Verify Auto-Spawn

```bash
# Watch control plane logs (should see cluster registration)
docker logs kg-control-plane --follow

# Expected output:
# 📝 Cluster registered: af-7 (name: production-us-east, version: 2.0.2)
# 🔧 Spawning graph-builder for cluster: af-7
# ✅ Spawned graph-builder-af-7 (container: abc123)

# Verify graph-builder was created
docker ps | grep graph-builder

# Check Neo4j data
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "MATCH (n:Resource {client_id: 'af-7'}) RETURN count(n);"
```

---

## 📚 Documentation

### Essential Guides

1. **[QUICK-START-V2.md](../QUICK-START-V2.md)** - Complete v2.0.0 deployment guide
2. **[docs/NEO4J-RCA-QUERIES.md](docs/NEO4J-RCA-QUERIES.md)** - 40+ RCA queries with examples
3. **[docs/MONITORING-GUIDE.md](docs/MONITORING-GUIDE.md)** - Monitoring, metrics, and alerts
4. **[docs/TROUBLESHOOTING-PLAYBOOK.md](docs/TROUBLESHOOTING-PLAYBOOK.md)** - Common issues and fixes

### Legacy Documentation (v1.x)

- **[docs/legacy/](docs/legacy/)** - Old manual deployment guides (v1.x)
- **[docs/legacy/QUICK-START-V1-LEGACY.md](docs/legacy/QUICK-START-V1-LEGACY.md)** - Legacy quick start

---

## 🎯 Control Plane Features

### Cluster Lifecycle Management

```bash
# View active clusters
curl -s http://localhost:9090/metrics | grep 'kg_control_plane_clusters_total{status="active"}'

# View metrics
curl http://localhost:9090/metrics

# Available metrics:
# - kg_control_plane_clusters_total{status="active|stale|dead"}
# - kg_control_plane_spawn_operations_total
# - kg_control_plane_cleanup_operations_total
```

### Automatic Cleanup

- **2 minutes** - No heartbeat → marked as **STALE** (graph-builder keeps running)
- **5 minutes** - No heartbeat → marked as **DEAD** → cleanup:
  - Stop and remove graph-builder container
  - Delete consumer group
  - Remove from control plane memory
  - (Neo4j data preserved for analysis)

### Heartbeat Monitoring

Clusters send heartbeats every 30 seconds to `cluster.heartbeat` topic:

```json
{
  "client_id": "af-7",
  "timestamp": "2025-10-23T14:00:00Z",
  "status": "healthy",
  "metrics": {
    "resources_sent": 1234,
    "uptime_seconds": 3600
  }
}
```

---

## 🔍 Monitoring & Observability

### Web UIs

| UI | URL | Credentials |
|----|-----|-------------|
| **Kafka UI** | http://SERVER_IP:7777 | None |
| **Neo4j Browser** | http://SERVER_IP:7474 | neo4j / Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA |
| **Control Plane Metrics** | http://SERVER_IP:9090/metrics | None |

### Health Check Script

```bash
#!/bin/bash
echo "=== KG-RCA Platform Status ==="
echo ""
echo "Containers:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep kg-
echo ""
echo "Active Clusters:"
curl -s http://localhost:9090/metrics | grep 'kg_control_plane_clusters_total{status="active"}'
echo ""
echo "Consumer Groups:"
docker exec kg-kafka kafka-consumer-groups \
  --bootstrap-server kg-kafka:29092 \
  --list | grep -E "control-plane|kg-builder"
```

---

## 🛠️ System Requirements

### Minimum (Testing)
- **CPU**: 2 vCPUs
- **RAM**: 4GB
- **Disk**: 50GB
- **Clusters**: 1-2

### Recommended (Production)
- **CPU**: 4 vCPUs
- **RAM**: 8GB
- **Disk**: 100GB SSD
- **Clusters**: 3-5

### High Scale
- **CPU**: 8+ vCPUs
- **RAM**: 16GB+
- **Disk**: 200GB+ NVMe
- **Clusters**: 10+

### AWS Instance Recommendations

| Instance | vCPUs | RAM | Use Case | Est. Cost/mo |
|----------|-------|-----|----------|--------------|
| t3.large | 2 | 8GB | Testing/Dev | $60 |
| t3.xlarge | 4 | 16GB | Production (5-10 clusters) | $121 |
| t3.2xlarge | 8 | 32GB | High scale (20+ clusters) | $242 |

---

## 🔐 Security & Network

### Firewall Rules (AWS Security Group)

**Inbound**:
- **Port 22** - SSH (your IP only)
- **Port 9092** - Kafka (from Kubernetes cluster IPs)
- **Port 7474** - Neo4j HTTP (optional, for browser access)
- **Port 7687** - Neo4j Bolt (optional)
- **Port 7777** - Kafka UI (optional, or use SSH tunnel)

**Outbound**: Allow all

### Network Ports

```bash
# Test Kafka connectivity from client cluster
kubectl run kafka-test --rm -it --image=busybox -- \
  nc -zv SERVER_IP 9092

# Test from control plane to Kafka
docker exec kg-control-plane nc -zv kg-kafka 29092
```

---

## 📊 Example Queries

### Neo4j Queries (Browser: http://SERVER_IP:7474)

```cypher
// Count resources by cluster
MATCH (n:Resource)
RETURN n.client_id AS Cluster, count(n) AS ResourceCount
ORDER BY ResourceCount DESC;

// List all pods in af-7
MATCH (n:Resource {client_id: 'af-7', kind: 'Pod'})
RETURN n.name AS Pod, n.ns AS Namespace, n.node AS Node
LIMIT 10;

// Find failed pods
MATCH (n:Resource {client_id: 'af-7', kind: 'Pod'})
WHERE n.status_json CONTAINS 'Failed' OR n.status_json CONTAINS 'CrashLoopBackOff'
RETURN n.name AS Pod, n.ns AS Namespace, n.status_json AS Status;
```

**See [docs/NEO4J-RCA-QUERIES.md](docs/NEO4J-RCA-QUERIES.md) for 40+ more queries!**

---

## 🐛 Troubleshooting

### Common Issues

**Problem**: Consumer groups show EMPTY status
```bash
# Restart control plane
docker restart kg-control-plane

# Watch logs
docker logs kg-control-plane --follow
```

**Problem**: Graph-builder not spawning
```bash
# Check control plane logs
docker logs kg-control-plane | grep spawn

# Manually register cluster
echo 'af-7:{"client_id":"af-7","cluster_name":"test","version":"2.0.2","registered_at":"2025-10-23T14:00:00Z","metadata":{}}' | \
docker exec -i kg-kafka kafka-console-producer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.registry \
  --property "parse.key=true" \
  --property "key.separator=:"
```

**Problem**: Kafka unhealthy
```bash
# Check Kafka logs
docker logs kg-kafka --tail 100

# Restart Kafka
docker restart kg-kafka
```

**See [docs/TROUBLESHOOTING-PLAYBOOK.md](docs/TROUBLESHOOTING-PLAYBOOK.md) for complete guide!**

---

## 🎓 Version History

### v2.0.0 (Current) - Control Plane Architecture
- ✅ Zero-touch cluster operations
- ✅ Auto-discovery via Kafka registry
- ✅ Dynamic graph-builder spawning
- ✅ Heartbeat-based cleanup
- ✅ Prometheus metrics

### v1.x (Legacy) - Manual Deployment
- ⚠️ Manual graph-builder deployment per cluster
- ⚠️ Static docker-compose configuration
- ⚠️ No auto-cleanup
- 📁 See [docs/legacy/](docs/legacy/) for v1.x docs

---

## 🚀 Next Steps

1. ✅ Deploy infrastructure on mini-server
2. ✅ Deploy client agents to Kubernetes clusters
3. ✅ Verify auto-spawn in control plane logs
4. ✅ Explore Neo4j queries for RCA
5. ✅ Set up monitoring dashboards (optional)
6. ✅ Test multi-cluster deployment

---

## 📞 Support

### Documentation
- **Quick Start**: [QUICK-START-V2.md](../QUICK-START-V2.md)
- **Queries**: [docs/NEO4J-RCA-QUERIES.md](docs/NEO4J-RCA-QUERIES.md)
- **Monitoring**: [docs/MONITORING-GUIDE.md](docs/MONITORING-GUIDE.md)
- **Troubleshooting**: [docs/TROUBLESHOOTING-PLAYBOOK.md](docs/TROUBLESHOOTING-PLAYBOOK.md)

### Health Check
```bash
curl http://SERVER_IP:9090/metrics | grep kg_control_plane
docker logs kg-control-plane --tail 50
docker ps | grep kg-
```

---

**🎉 Ready to deploy? → See [QUICK-START-V2.md](../QUICK-START-V2.md) for step-by-step instructions!**
