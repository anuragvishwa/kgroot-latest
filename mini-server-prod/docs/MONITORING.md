# Monitoring Guide

## Overview

This guide covers how to monitor the KG RCA platform, interpret metrics, set up alerts, and troubleshoot performance issues.

## Access Monitoring Tools

### Grafana (Primary Dashboard)
- **URL**: `http://YOUR_SERVER_IP:3000`
- **Login**: admin / YOUR_GRAFANA_PASSWORD
- **Purpose**: Visualize all metrics, create dashboards

### Prometheus (Metrics Database)
- **URL**: `http://YOUR_SERVER_IP:9091`
- **Purpose**: Query raw metrics, test PromQL queries

### Kafka UI (Kafka Monitoring)
- **URL**: `http://YOUR_SERVER_IP:7777`
- **Purpose**: Monitor Kafka topics, consumer groups, messages

### Neo4j Browser (Graph Database)
- **URL**: `http://YOUR_SERVER_IP:7474`
- **Login**: neo4j / YOUR_NEO4J_PASSWORD
- **Purpose**: Query graph data, visualize relationships

## Key Metrics to Monitor

### 1. System Metrics

#### CPU Usage
```bash
# View container CPU
docker stats --no-stream

# View system CPU
top
htop
```

**Thresholds:**
- **Normal**: < 60%
- **Warning**: 60-80%
- **Critical**: > 80%

#### Memory Usage
```bash
# View container memory
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"

# View system memory
free -h
```

**Thresholds:**
- **Normal**: < 70%
- **Warning**: 70-85%
- **Critical**: > 85%

#### Disk Usage
```bash
# View disk space
df -h

# View Docker volumes
docker system df -v
```

**Thresholds:**
- **Normal**: < 70%
- **Warning**: 70-85%
- **Critical**: > 85%

### 2. Kafka Metrics

#### Message Rate
```promql
# Prometheus query
rate(kafka_server_brokertopicmetrics_messagesinpersec[5m])
```

**Access via Kafka UI:**
- Navigate to Topics
- View message rate per topic

#### Consumer Lag
```bash
# Check consumer group lag
docker exec kg-kafka kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --group CONSUMER_GROUP \
    --describe
```

**Interpretation:**
- **LAG < 1000**: Healthy, consumers keeping up
- **LAG 1000-10000**: Warning, consumers falling behind
- **LAG > 10000**: Critical, investigate immediately

**Common causes of lag:**
- Slow consumer processing
- Consumer crashes
- Insufficient partitions
- Network issues

#### Topic Sizes
```bash
# View topic sizes
for topic in $(docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list); do
    echo "Topic: $topic"
    docker exec kg-kafka kafka-log-dirs.sh \
        --bootstrap-server localhost:9092 \
        --describe --topic-list "$topic" | grep "partition"
done
```

### 3. Neo4j Metrics

#### Query Performance
```bash
# Access Neo4j browser
open http://YOUR_SERVER_IP:7474

# Run query:
CALL dbms.listQueries()
YIELD queryId, query, elapsedTimeMillis, activeLockCount
WHERE elapsedTimeMillis > 1000
RETURN queryId, query, elapsedTimeMillis
ORDER BY elapsedTimeMillis DESC
```

**Thresholds:**
- **Fast**: < 100ms
- **Acceptable**: 100-1000ms
- **Slow**: > 1000ms

#### Database Size
```bash
# Check database size
docker exec kg-neo4j du -sh /data

# Query node counts
docker exec -it kg-neo4j cypher-shell -u neo4j -p YOUR_PASSWORD <<EOF
MATCH (n)
RETURN labels(n)[0] as Label, count(n) as Count
ORDER BY Count DESC;
EOF
```

#### Transaction Rate
```cypher
// In Neo4j Browser
CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Transactions')
YIELD attributes
RETURN attributes.NumberOfOpenTransactions,
       attributes.PeakNumberOfConcurrentTransactions;
```

### 4. Graph Builder Metrics

#### Events Processed
```promql
# Prometheus query
rate(kg_events_processed_total[5m])
```

#### Processing Latency
```promql
# Prometheus query
histogram_quantile(0.95, rate(kg_event_processing_duration_seconds_bucket[5m]))
```

#### Error Rate
```promql
# Prometheus query
rate(kg_processing_errors_total[5m])
```

**View in logs:**
```bash
docker logs kg-graph-builder -f | grep -i error
```

### 5. KG API Metrics

#### Request Rate
```promql
# Prometheus query
rate(http_requests_total[5m])
```

#### Latency
```promql
# Prometheus query (p95)
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

#### Error Rate
```promql
# Prometheus query
rate(http_requests_total{status=~"5.."}[5m])
```

**Test API directly:**
```bash
# Health check
curl http://localhost:8080/healthz

# Measure latency
time curl http://localhost:8080/api/v1/graph/stats
```

## Grafana Dashboards

### System Overview Dashboard

Create dashboard with:

1. **System Panel**
   - CPU usage (all containers)
   - Memory usage (all containers)
   - Disk usage

2. **Kafka Panel**
   - Message rate per topic
   - Consumer lag
   - Broker health

3. **Neo4j Panel**
   - Query rate
   - Transaction rate
   - Database size

4. **Application Panel**
   - Events processed/sec
   - RCA queries/sec
   - Error rates

### Sample Dashboard JSON

```json
{
  "dashboard": {
    "title": "KG RCA Overview",
    "panels": [
      {
        "title": "Events Processed",
        "targets": [
          {
            "expr": "rate(kg_events_processed_total[5m])"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Consumer Lag",
        "targets": [
          {
            "expr": "kafka_consumer_lag"
          }
        ],
        "type": "graph"
      }
    ]
  }
}
```

## Setting Up Alerts

### Prometheus Alerting Rules

Create `/config/alerts.yml`:

```yaml
groups:
  - name: kg_rca_alerts
    interval: 30s
    rules:
      # High consumer lag
      - alert: HighConsumerLag
        expr: kafka_consumer_lag > 10000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High consumer lag for {{ $labels.group }}"
          description: "Consumer group {{ $labels.group }} has lag of {{ $value }}"

      # High memory usage
      - alert: HighMemoryUsage
        expr: (container_memory_usage_bytes / container_spec_memory_limit_bytes) > 0.85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage for {{ $labels.name }}"
          description: "Container {{ $labels.name }} is using {{ $value | humanizePercentage }} of memory"

      # Disk space low
      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.15
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Low disk space on {{ $labels.instance }}"
          description: "Only {{ $value | humanizePercentage }} disk space remaining"

      # Service down
      - alert: ServiceDown
        expr: up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.job }} is down"
          description: "{{ $labels.job }} has been down for more than 2 minutes"

      # High error rate
      - alert: HighErrorRate
        expr: rate(kg_processing_errors_total[5m]) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate in {{ $labels.service }}"
          description: "Error rate is {{ $value }} errors/sec"
```

### Enable Alerts in Prometheus

Edit `docker-compose.yml`:

```yaml
prometheus:
  volumes:
    - ./config/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    - ./config/alerts.yml:/etc/prometheus/alerts.yml:ro
```

Update `config/prometheus.yml`:

```yaml
rule_files:
  - "alerts.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093  # If you deploy AlertManager
```

### Grafana Alerts

1. **Open Grafana** → Alerting → Alert rules
2. **Create alert rule**:
   - Name: High Consumer Lag
   - Query: `kafka_consumer_lag`
   - Condition: `WHEN last() OF query(A, 5m, now) IS ABOVE 10000`
   - Evaluate every: 1m
   - For: 5m

3. **Configure notification channel**:
   - Email
   - Slack
   - PagerDuty
   - Webhook

## Log Monitoring

### View Real-time Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f graph-builder

# Filter for errors
docker compose logs -f | grep -i error

# Follow last 100 lines
docker compose logs -f --tail=100
```

### Log Patterns to Watch

#### Normal Operation
```
[INFO] Connected to Kafka
[INFO] Processing event: event-123
[INFO] Created node: Pod/my-app-xyz
[INFO] Updated relationship: RUNS_ON
```

#### Warning Signs
```
[WARN] High consumer lag detected: 5000
[WARN] Slow query detected: 2.5s
[WARN] Retry attempt 3/5
```

#### Critical Issues
```
[ERROR] Failed to connect to Neo4j
[ERROR] Kafka consumer crashed
[ERROR] Out of memory
[FATAL] Service shutting down
```

### Log Aggregation (Optional)

**Deploy ELK Stack:**

```yaml
# Add to docker-compose.yml
elasticsearch:
  image: elasticsearch:8.11.0
  ports:
    - "9200:9200"

logstash:
  image: logstash:8.11.0
  volumes:
    - ./config/logstash.conf:/usr/share/logstash/pipeline/logstash.conf

kibana:
  image: kibana:8.11.0
  ports:
    - "5601:5601"
```

**Or use external service:**
- Datadog
- New Relic
- Splunk
- CloudWatch (AWS)

## Health Checks

### Manual Health Check Script

```bash
#!/bin/bash
# health-check.sh

echo "=== KG RCA Health Check ==="
echo

# Check services
for service in zookeeper kafka neo4j graph-builder kg-api; do
    echo -n "Checking $service... "
    if docker ps | grep -q "kg-$service"; then
        echo "✓ Running"
    else
        echo "✗ Down"
    fi
done

echo
echo "=== Metrics ==="

# Consumer lag
echo "Consumer lag:"
docker exec kg-kafka kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --group kg-builder \
    --describe | grep -E "TOPIC|kg"

echo
# Neo4j node count
echo "Neo4j node count:"
docker exec -it kg-neo4j cypher-shell -u neo4j -p YOUR_PASSWORD \
    "MATCH (n) RETURN count(n) as total;" --format plain

echo
# System resources
echo "System resources:"
free -h | grep Mem
df -h / | grep -v Filesystem
```

### Automated Health Monitoring

**Create systemd service for monitoring:**

```bash
# /etc/systemd/system/kg-monitor.service
[Unit]
Description=KG RCA Health Monitor
After=docker.service

[Service]
Type=oneshot
ExecStart=/home/ubuntu/kg-rca/mini-server-prod/scripts/health-check.sh
StandardOutput=journal

[Install]
WantedBy=multi-user.target
```

**Create timer:**

```bash
# /etc/systemd/system/kg-monitor.timer
[Unit]
Description=Run KG RCA Health Check every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
```

**Enable:**
```bash
sudo systemctl enable kg-monitor.timer
sudo systemctl start kg-monitor.timer
```

## Performance Tuning

### Identify Bottlenecks

```bash
# CPU bound?
docker stats --no-stream | sort -k3 -h -r

# Memory bound?
docker stats --no-stream | sort -k7 -h -r

# I/O bound?
iostat -x 1 5

# Network bound?
iftop
```

### Optimization Strategies

#### 1. Kafka Optimization

```yaml
# docker-compose.yml
kafka:
  environment:
    # Increase heap
    KAFKA_HEAP_OPTS: "-Xmx4G -Xms2G"

    # Increase threads
    KAFKA_CFG_NUM_NETWORK_THREADS: 8
    KAFKA_CFG_NUM_IO_THREADS: 8

    # Batch settings
    KAFKA_CFG_BATCH_SIZE: 16384
    KAFKA_CFG_LINGER_MS: 10
```

#### 2. Neo4j Optimization

```yaml
# docker-compose.yml
neo4j:
  environment:
    # Increase heap
    NEO4J_server_memory_heap_max__size: 8G

    # Increase page cache
    NEO4J_server_memory_pagecache_size: 4G

    # Tune checkpoints
    NEO4J_dbms_checkpoint_interval_time: 30m
```

#### 3. Application Optimization

```yaml
# docker-compose.yml
graph-builder:
  environment:
    # Batch processing
    BATCH_SIZE: 100
    BATCH_TIMEOUT: 5s

    # Parallel processing
    WORKER_THREADS: 4
```

## Troubleshooting Performance Issues

### Issue: High CPU Usage

```bash
# Identify process
docker stats --no-stream | sort -k3 -r

# Check what it's doing
docker logs <container> -f

# If Neo4j: check for long-running queries
docker exec -it kg-neo4j cypher-shell -u neo4j -p PASSWORD
CALL dbms.listQueries() YIELD query, elapsedTimeMillis;

# Kill slow query
CALL dbms.killQuery('query-id');
```

### Issue: High Memory Usage

```bash
# Check current usage
docker stats --no-stream | sort -k7 -r

# Check for memory leaks in logs
docker logs graph-builder | grep -i "memory\|heap\|oom"

# Restart service to free memory
docker compose restart graph-builder
```

### Issue: Slow Queries

```bash
# Profile Neo4j query
docker exec -it kg-neo4j cypher-shell -u neo4j -p PASSWORD
PROFILE MATCH (n) RETURN n LIMIT 10;

# Add index
CREATE INDEX resource_id FOR (r:Resource) ON (r.id);

# View all indexes
SHOW INDEXES;
```

## Best Practices

1. **Monitor Regularly**: Check dashboards daily
2. **Set Up Alerts**: Don't wait for issues to be reported
3. **Baseline Metrics**: Know what "normal" looks like
4. **Log Rotation**: Prevent disk fill-up
5. **Capacity Planning**: Monitor trends, plan upgrades
6. **Document Issues**: Keep runbook of past issues
7. **Test Alerts**: Ensure notifications work
8. **Review Metrics**: Weekly review of trends

## Additional Resources

- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Neo4j Performance Tuning](https://neo4j.com/docs/operations-manual/current/performance/)
- [Kafka Monitoring](https://kafka.apache.org/documentation/#monitoring)
