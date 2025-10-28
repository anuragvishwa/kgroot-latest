# KG-RCA Platform Monitoring Guide

Complete monitoring, metrics, and observability guide for the KG-RCA platform v2.0.0+.

---

## Table of Contents

1. [System Health Monitoring](#1-system-health-monitoring)
2. [Control Plane Metrics](#2-control-plane-metrics)
3. [Kafka Monitoring](#3-kafka-monitoring)
4. [Neo4j Monitoring](#4-neo4j-monitoring)
5. [Client Cluster Health](#5-client-cluster-health)
6. [Alerting Setup](#6-alerting-setup)
7. [Log Aggregation](#7-log-aggregation)
8. [Dashboard Examples](#8-dashboard-examples)

---

## 1. System Health Monitoring

### 1.1 Quick Health Check Script

```bash
#!/bin/bash
# save as: check-health.sh

echo "=== KG-RCA Platform Health Check ==="
echo ""

# Check all containers
echo "1. Container Status:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep kg-

echo ""
echo "2. Control Plane Metrics:"
curl -s http://localhost:9090/metrics | grep kg_control_plane

echo ""
echo "3. Kafka Topics:"
docker exec kg-kafka kafka-topics --bootstrap-server kg-kafka:29092 --list

echo ""
echo "4. Neo4j Status:"
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "CALL dbms.components() YIELD name, versions, edition RETURN name, versions[0] as version, edition;"

echo ""
echo "5. Active Clusters:"
curl -s http://localhost:9090/metrics | grep 'kg_control_plane_clusters_total{status="active"}'

echo ""
echo "=== Health Check Complete ==="
```

**Usage**:
```bash
chmod +x check-health.sh
./check-health.sh
```

### 1.2 Docker Container Health

```bash
# Check container health status
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Health}}"

# View container logs (last 100 lines)
docker logs kg-control-plane --tail 100 --follow

# Check container resource usage
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Restart unhealthy container
docker restart kg-control-plane
```

### 1.3 Disk Space Monitoring

```bash
# Check Docker volumes
docker system df -v

# Check Kafka data volume
docker exec kg-kafka df -h /var/lib/kafka/data

# Check Neo4j data volume
docker exec kg-neo4j df -h /data

# Clean up old containers/images
docker system prune -a --volumes --force
```

---

## 2. Control Plane Metrics

### 2.1 Prometheus Metrics Endpoint

**URL**: http://localhost:9090/metrics

### Available Metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `kg_control_plane_clusters_total{status="active"}` | Gauge | Number of active clusters |
| `kg_control_plane_clusters_total{status="stale"}` | Gauge | Number of stale clusters (no heartbeat >2min) |
| `kg_control_plane_clusters_total{status="dead"}` | Gauge | Number of dead clusters |
| `kg_control_plane_spawn_operations_total` | Counter | Total graph-builder spawns |
| `kg_control_plane_cleanup_operations_total` | Counter | Total cleanup operations |

### 2.2 Query Metrics with curl

```bash
# Active clusters count
curl -s http://localhost:9090/metrics | grep 'kg_control_plane_clusters_total{status="active"}'

# Spawn operations
curl -s http://localhost:9090/metrics | grep 'kg_control_plane_spawn_operations_total'

# All control plane metrics
curl -s http://localhost:9090/metrics | grep kg_control_plane
```

### 2.3 Control Plane Logs

```bash
# Real-time logs
docker logs kg-control-plane --follow

# Last 200 lines
docker logs kg-control-plane --tail 200

# Logs from specific time
docker logs kg-control-plane --since 30m

# Search for specific events
docker logs kg-control-plane 2>&1 | grep "cluster registered"
docker logs kg-control-plane 2>&1 | grep "spawned graph-builder"
docker logs kg-control-plane 2>&1 | grep ERROR
```

### 2.4 Heartbeat Monitoring

```bash
# Check recent heartbeats
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.heartbeat \
  --from-beginning \
  --max-messages 10 | jq .

# Monitor live heartbeats
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.heartbeat \
  --from-beginning | jq '{client_id, status, timestamp, uptime: .metrics.uptime_seconds}'
```

---

## 3. Kafka Monitoring

### 3.1 Kafka UI

**URL**: http://localhost:7777

**Features**:
- Topic browser
- Consumer group monitoring
- Message inspection
- Broker health
- Configuration management

### 3.2 Topic Monitoring

```bash
# List all topics
docker exec kg-kafka kafka-topics \
  --bootstrap-server kg-kafka:29092 \
  --list

# Describe specific topic
docker exec kg-kafka kafka-topics \
  --bootstrap-server kg-kafka:29092 \
  --describe \
  --topic cluster.registry

# Check topic offsets
docker exec kg-kafka kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list kg-kafka:29092 \
  --topic state.k8s.resource
```

### 3.3 Consumer Group Monitoring

```bash
# List consumer groups
docker exec kg-kafka kafka-consumer-groups \
  --bootstrap-server kg-kafka:29092 \
  --list

# Check consumer group lag
docker exec kg-kafka kafka-consumer-groups \
  --bootstrap-server kg-kafka:29092 \
  --group graph-builder-af-4 \
  --describe

# Reset consumer group offset (if needed)
docker exec kg-kafka kafka-consumer-groups \
  --bootstrap-server kg-kafka:29092 \
  --group graph-builder-af-4 \
  --topic state.k8s.resource \
  --reset-offsets \
  --to-earliest \
  --execute
```

### 3.4 Message Inspection

```bash
# Sample messages from state topic
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic state.k8s.resource \
  --max-messages 5 \
  --property print.key=true \
  --property key.separator="|||" | jq .

# Sample events
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic events.normalized \
  --max-messages 5 | jq '{client_id, type, reason, timestamp}'

# Check cluster registry
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.registry \
  --from-beginning \
  --property print.key=true | jq .
```

### 3.5 Kafka Performance Metrics

```bash
# Check Kafka JMX metrics (requires JMX exporter)
docker exec kg-kafka kafka-run-class kafka.tools.JmxTool \
  --object-name kafka.server:type=BrokerTopicMetrics,name=MessagesInPerSec \
  --reporting-interval 1000
```

---

## 4. Neo4j Monitoring

### 4.1 Neo4j Browser

**URL**: http://localhost:7474
**Username**: neo4j
**Password**: Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA

### 4.2 Database Metrics

```cypher
// Database info
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions[0] as version, edition;

// Node count by label
CALL db.labels() YIELD label
CALL apoc.cypher.run('MATCH (n:' + label + ') RETURN count(n) as count', {})
YIELD value
RETURN label, value.count as count
ORDER BY count DESC;

// Relationship count by type
CALL db.relationshipTypes() YIELD relationshipType
CALL apoc.cypher.run(
  'MATCH ()-[r:' + relationshipType + ']->() RETURN count(r) as count',
  {}
)
YIELD value
RETURN relationshipType, value.count as count
ORDER BY count DESC;

// Database size
CALL apoc.monitor.store()
YIELD logSize, stringStoreSize, arrayStoreSize, relStoreSize,
      propStoreSize, totalStoreSize
RETURN logSize, stringStoreSize, arrayStoreSize, relStoreSize,
       propStoreSize, totalStoreSize;
```

### 4.3 Query Performance

```cypher
// List running queries
CALL dbms.listQueries()
YIELD queryId, username, query, elapsedTimeMillis, status
WHERE elapsedTimeMillis > 1000
RETURN queryId, username, query, elapsedTimeMillis, status
ORDER BY elapsedTimeMillis DESC;

// Kill long-running query
CALL dbms.killQuery('query-123');

// Query plan analysis
PROFILE MATCH (n:Resource {client_id: 'af-4'}) RETURN count(n);
```

### 4.4 Neo4j Logs

```bash
# View Neo4j logs
docker logs kg-neo4j --tail 100

# Check for errors
docker logs kg-neo4j 2>&1 | grep ERROR

# Query log (if enabled)
docker exec kg-neo4j cat /logs/query.log
```

### 4.5 Backup and Restore

```bash
# Create backup
docker exec kg-neo4j neo4j-admin database dump neo4j \
  --to-path=/backups \
  --verbose

# Copy backup to host
docker cp kg-neo4j:/backups/neo4j.dump ./neo4j-backup-$(date +%Y%m%d).dump

# Restore from backup
docker exec kg-neo4j neo4j-admin database load neo4j \
  --from-path=/backups/neo4j.dump \
  --overwrite-destination=true
```

---

## 5. Client Cluster Health

### 5.1 Check Client Pods

```bash
# List all KG-RCA pods in client cluster
kubectl get pods -n kgroot -l app.kubernetes.io/name=kg-rca-agent

# Check state-watcher logs
kubectl logs -n kgroot -l app=kg-rca-agent-state-watcher --tail=100 --follow

# Check event-exporter logs
kubectl logs -n kgroot -l app=kg-rca-agent-event-exporter --tail=100 --follow

# Check vector logs (if deployed)
kubectl logs -n kgroot -l app=vector-agent --tail=100 --follow
```

### 5.2 Registration Status

```bash
# Check if cluster is registered
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.registry \
  --from-beginning \
  --property print.key=true | grep "af-4"

# Verify graph-builder is running
docker ps | grep "kg-graph-builder-af-4"

# Check graph-builder logs
docker logs kg-graph-builder-af-4 --tail 100
```

### 5.3 Data Flow Verification

```bash
# Check if state-watcher is sending data
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic state.k8s.resource \
  --max-messages 3 --timeout-ms 5000 | jq '{client_id, kind, name, namespace}'

# Check if events are flowing
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic events.normalized \
  --max-messages 3 --timeout-ms 5000 | jq '{client_id, type, reason}'

# Verify data in Neo4j
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "MATCH (n:Resource {client_id: 'af-4'}) RETURN count(n) as count;"
```

---

## 6. Alerting Setup

### 6.1 AlertManager Configuration

Location: `/Users/anuragvishwa/Anurag/kgroot_latest/mini-server-prod/alertmanager.yml`

```yaml
route:
  receiver: 'kg-alert-receiver'
  group_by: ['alertname', 'cluster', 'namespace']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h

receivers:
  - name: 'kg-alert-receiver'
    webhook_configs:
      - url: 'http://kg-alert-receiver:8080/webhook'
        send_resolved: true
```

### 6.2 Test Alert

```bash
# Send test alert to AlertManager
curl -X POST http://localhost:9093/api/v1/alerts \
  -H 'Content-Type: application/json' \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning",
      "client_id": "af-4",
      "namespace": "kgroot"
    },
    "annotations": {
      "summary": "Test alert from monitoring guide",
      "description": "This is a test alert"
    }
  }]'

# Check if alert was received
docker logs kg-alert-receiver --tail 50 | grep TestAlert
```

### 6.3 Alert Queries in Neo4j

```cypher
// Count active alerts by severity
MATCH (a:Alert)
WHERE a.status = 'firing'
RETURN a.severity as Severity,
       count(a) as Count
ORDER BY
  CASE Severity
    WHEN 'critical' THEN 1
    WHEN 'warning' THEN 2
    ELSE 3
  END;

// Recent alerts with details
MATCH (a:Alert)
WHERE a.created_at > datetime() - duration({hours: 24})
RETURN a.alert_name as Alert,
       a.severity as Severity,
       a.status as Status,
       a.summary as Summary,
       a.starts_at as StartedAt
ORDER BY a.starts_at DESC
LIMIT 20;
```

---

## 7. Log Aggregation

### 7.1 Centralized Logging with Vector (Client-Side)

Check Vector DaemonSet logs:
```bash
kubectl logs -n kgroot -l app=vector-agent --tail=100 --follow
```

### 7.2 Server-Side Log Collection

```bash
# Collect all container logs
for container in kg-control-plane kg-kafka kg-neo4j kg-alert-receiver; do
  echo "=== $container ==="
  docker logs $container --tail 50 2>&1
  echo ""
done > /tmp/kg-logs-$(date +%Y%m%d-%H%M).txt

# Compress logs
tar -czf kg-logs-$(date +%Y%m%d-%H%M).tar.gz /tmp/kg-logs-*.txt
```

### 7.3 Log Rotation

```bash
# Configure Docker log rotation (edit daemon.json)
sudo cat << EOF > /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF

sudo systemctl restart docker
```

---

## 8. Dashboard Examples

### 8.1 Grafana Dashboard (JSON)

Save as: `grafana-dashboard.json`

```json
{
  "dashboard": {
    "title": "KG-RCA Platform",
    "panels": [
      {
        "title": "Active Clusters",
        "targets": [{
          "expr": "kg_control_plane_clusters_total{status=\"active\"}"
        }],
        "type": "stat"
      },
      {
        "title": "Spawn Operations",
        "targets": [{
          "expr": "rate(kg_control_plane_spawn_operations_total[5m])"
        }],
        "type": "graph"
      },
      {
        "title": "Kafka Message Rate",
        "targets": [{
          "expr": "rate(kafka_server_brokertopicmetrics_messagesin_total[1m])"
        }],
        "type": "graph"
      }
    ]
  }
}
```

### 8.2 Terminal Dashboard Script

```bash
#!/bin/bash
# save as: dashboard.sh

while true; do
  clear
  echo "╔════════════════════════════════════════════════════════════╗"
  echo "║          KG-RCA Platform Dashboard                        ║"
  echo "╚════════════════════════════════════════════════════════════╝"
  echo ""

  echo "📊 System Health:"
  docker ps --format "  {{.Names}}: {{.Status}}" | grep kg- | head -7

  echo ""
  echo "📈 Control Plane Metrics:"
  curl -s http://localhost:9090/metrics | grep kg_control_plane | sed 's/^/  /'

  echo ""
  echo "💾 Resource Usage:"
  docker stats --no-stream --format "  {{.Name}}: CPU {{.CPUPerc}}, MEM {{.MemUsage}}" | grep kg-

  echo ""
  echo "Press Ctrl+C to exit"
  sleep 5
done
```

### 8.3 Prometheus Scrape Config

Add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'kg-control-plane'
    static_configs:
      - targets: ['kg-control-plane:9090']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

---

## Quick Command Reference

```bash
# Health check
./check-health.sh

# View control plane metrics
curl -s http://localhost:9090/metrics | grep kg_control_plane

# Check Kafka topics
docker exec kg-kafka kafka-topics --bootstrap-server kg-kafka:29092 --list

# Monitor heartbeats
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.heartbeat --from-beginning | jq .

# Neo4j quick query
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "MATCH (n:Resource {client_id: 'af-4'}) RETURN n.kind, count(n) ORDER BY count(n) DESC;"

# Check client cluster
kubectl get pods -n kgroot -l app.kubernetes.io/name=kg-rca-agent

# View logs
docker logs kg-control-plane --tail 100 --follow

# Restart service
docker restart kg-control-plane
```

---

## Monitoring Best Practices

1. **Set up automated health checks** - Run check-health.sh via cron every 5 minutes
2. **Monitor disk space** - Alert when >80% full
3. **Track consumer lag** - Alert if lag > 10000 messages
4. **Watch heartbeat gaps** - Alert if no heartbeat for >3 minutes
5. **Neo4j query performance** - Profile slow queries (>5s)
6. **Regular backups** - Daily Neo4j backups, weekly Kafka topic exports
7. **Log retention** - Keep logs for 30 days minimum
8. **Capacity planning** - Monitor growth trends monthly

---

**Document Version**: 1.0.0
**Last Updated**: 2025-10-23
**Platform Version**: v2.0.0
