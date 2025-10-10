# Operations Guide

**Version**: 1.0.0
**Last Updated**: 2025-01-09

---

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Monitoring & Dashboards](#monitoring--dashboards)
3. [Scaling Procedures](#scaling-procedures)
4. [Backup & Restore](#backup--restore)
5. [Client Management](#client-management)
6. [Performance Tuning](#performance-tuning)
7. [Cost Optimization](#cost-optimization)
8. [Incident Response](#incident-response)
9. [Maintenance Windows](#maintenance-windows)
10. [Capacity Planning](#capacity-planning)

---

## Daily Operations

### Morning Health Check

```bash
#!/bin/bash
# daily-health-check.sh - Run every morning

echo "=== KG RCA Server Health Check ==="
echo "Date: $(date)"
echo ""

# 1. Check all pods are running
echo "1. Pod Health:"
kubectl get pods -n kg-rca-server | grep -v Running | grep -v Completed
UNHEALTHY_PODS=$(kubectl get pods -n kg-rca-server | grep -v Running | grep -v Completed | wc -l)
if [ $UNHEALTHY_PODS -gt 1 ]; then  # > 1 because of header line
  echo "⚠️  WARNING: $((UNHEALTHY_PODS-1)) unhealthy pods detected"
else
  echo "✅ All pods healthy"
fi
echo ""

# 2. Check Neo4j cluster
echo "2. Neo4j Cluster:"
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  "CALL dbms.cluster.overview() YIELD role RETURN role;" 2>/dev/null | grep LEADER
if [ $? -eq 0 ]; then
  echo "✅ Neo4j cluster has leader"
else
  echo "❌ ERROR: No Neo4j leader found"
fi
echo ""

# 3. Check Kafka brokers
echo "3. Kafka Brokers:"
KAFKA_BROKERS=$(kubectl exec -n kg-rca-server kafka-0 -- kafka-broker-api-versions.sh \
  --bootstrap-server kafka:9092 2>/dev/null | grep "id:" | wc -l)
echo "   Active brokers: $KAFKA_BROKERS/5"
if [ $KAFKA_BROKERS -eq 5 ]; then
  echo "✅ All Kafka brokers online"
else
  echo "⚠️  WARNING: Only $KAFKA_BROKERS/5 brokers online"
fi
echo ""

# 4. Check consumer lag
echo "4. Consumer Lag:"
MAX_LAG=$(kubectl exec -n kg-rca-server kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group kg-builder 2>/dev/null | awk '{print $5}' | grep -v LAG | sort -n | tail -1)
echo "   Max lag: $MAX_LAG messages"
if [ $MAX_LAG -lt 1000 ]; then
  echo "✅ Consumer lag acceptable (<1000)"
elif [ $MAX_LAG -lt 10000 ]; then
  echo "⚠️  WARNING: Consumer lag elevated ($MAX_LAG)"
else
  echo "❌ ERROR: Consumer lag critical ($MAX_LAG)"
fi
echo ""

# 5. Check disk usage
echo "5. Disk Usage:"
kubectl exec -n kg-rca-server neo4j-0 -- df -h /data | tail -1
kubectl exec -n kg-rca-server kafka-0 -- df -h /kafka | tail -1
echo ""

# 6. Query Prometheus for key metrics
echo "6. Key Metrics (last hour):"
curl -s "http://prometheus:9090/api/v1/query?query=kg_rca_accuracy_at_k{k=\"3\"}" | \
  jq -r '.data.result[0].value[1]' | xargs printf "   RCA Accuracy (A@3): %.2f%%\n"

curl -s "http://prometheus:9090/api/v1/query?query=rate(kg_messages_processed_total{status=\"success\"}[1h])" | \
  jq -r '.data.result[0].value[1]' | xargs printf "   Message rate: %.0f msg/sec\n"

echo ""
echo "=== Health Check Complete ==="
```

### Client Activity Summary

```bash
#!/bin/bash
# client-activity-summary.sh - Weekly report

echo "=== Client Activity Summary ==="
echo "Week ending: $(date)"
echo ""

# Query PostgreSQL for all active clients
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -t -c \
  "SELECT id, name, plan FROM clients WHERE status = 'active' ORDER BY created_at;" | \
while IFS='|' read -r client_id name plan; do
  client_id=$(echo $client_id | xargs)
  name=$(echo $name | xargs)
  plan=$(echo $plan | xargs)

  echo "Client: $name ($client_id)"
  echo "  Plan: $plan"

  # Get event count
  EVENTS=$(kubectl exec -n kg-rca-server kafka-0 -- kafka-run-class kafka.tools.GetOffsetShell \
    --broker-list kafka:9092 \
    --topic "${client_id}.events.normalized" 2>/dev/null | awk -F: '{sum+=$3} END {print sum}')
  echo "  Total events: $EVENTS"

  # Get resource count from Neo4j
  DB_NAME="client_${client_id//-/_}_kg"
  RESOURCES=$(kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
    -d $DB_NAME "MATCH (r:Resource) RETURN count(r);" 2>/dev/null | tail -2 | head -1 | xargs)
  echo "  Resources: $RESOURCES"

  # Get RCA links
  RCA_LINKS=$(kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
    -d $DB_NAME "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r);" 2>/dev/null | tail -2 | head -1 | xargs)
  echo "  RCA links: $RCA_LINKS"

  echo ""
done
```

---

## Monitoring & Dashboards

### Accessing Grafana

```bash
# Port-forward Grafana
kubectl port-forward -n kg-rca-server svc/grafana 3000:3000

# Or access via ingress
# URL: https://grafana.kg-rca.yourcompany.com
# User: admin
# Password: [from secrets]
```

### Key Dashboards

#### 1. Server Overview Dashboard

**Panels**:
- Total active clients
- Messages processed (rate)
- RCA accuracy (A@3)
- System resource utilization
- Error rate

**Alerts**:
- CPU usage > 80%
- Memory usage > 85%
- Disk usage > 90%
- Pod restarts > 5 in 1 hour

#### 2. Per-Client Dashboard

**Panels**:
- Events ingested (time series)
- RCA queries executed
- Storage usage
- API call rate
- Kafka lag per topic

**Variables**:
- `$client_id` (dropdown)

**Sample Queries**:
```promql
# Events per second per client
rate(kg_messages_processed_total{client_id="$client_id"}[5m])

# Storage usage per client
kg_client_storage_bytes{client_id="$client_id"} / 1024 / 1024 / 1024

# API calls per minute
rate(kg_api_calls_total{client_id="$client_id"}[1m]) * 60
```

#### 3. RCA Quality Dashboard

**Panels**:
- A@1, A@3, A@5, A@10 accuracy (gauges)
- Mean Average Rank (MAR) trend
- Confidence score distribution (histogram)
- Null confidence link count
- RCA compute time (P50, P95, P99)

**Sample Queries**:
```promql
# RCA Accuracy at K=3
kg_rca_accuracy_at_k{k="3"}

# Mean Average Rank
kg_rca_mean_average_rank

# RCA compute time P95
histogram_quantile(0.95, kg_rca_compute_time_seconds_bucket)
```

#### 4. Performance Dashboard

**Panels**:
- Message processing latency (P50, P95, P99)
- Neo4j query duration
- API latency
- Kafka consumer lag
- End-to-end latency

**Sample Queries**:
```promql
# Message processing P95
histogram_quantile(0.95, kg_message_processing_duration_seconds_bucket)

# Consumer lag by topic
kg_kafka_consumer_lag

# API P95 latency
histogram_quantile(0.95, kg_api_request_duration_seconds_bucket)
```

### Setting Up Alerts

```yaml
# alerting-rules.yaml
groups:
  - name: server-critical
    interval: 30s
    rules:
      - alert: Neo4jDown
        expr: neo4j_up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Neo4j instance {{ $labels.instance }} is down"
          description: "Neo4j has been down for more than 2 minutes"

      - alert: KafkaBrokerDown
        expr: kafka_broker_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Kafka broker {{ $labels.broker }} is down"

      - alert: HighConsumerLag
        expr: kg_kafka_consumer_lag > 10000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High consumer lag on {{ $labels.topic }}"
          description: "Lag: {{ $value }} messages"

      - alert: LowRCAAccuracy
        expr: kg_rca_accuracy_at_k{k="3"} < 0.85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "RCA accuracy below threshold"
          description: "A@3 accuracy: {{ $value }}"

      - alert: DiskSpaceHigh
        expr: (kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes) > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Disk usage high on {{ $labels.persistentvolumeclaim }}"
          description: "{{ $value | humanizePercentage }} used"

      - alert: PodRestartingFrequently
        expr: rate(kube_pod_container_status_restarts_total[1h]) > 5
        labels:
          severity: warning
        annotations:
          summary: "Pod {{ $labels.pod }} restarting frequently"

# Apply rules
kubectl create configmap prometheus-rules \
  --from-file=alerting-rules.yaml \
  -n kg-rca-server
```

---

## Scaling Procedures

### Horizontal Scaling

#### Scale Graph Builder

```bash
# Check current replicas
kubectl get deployment graph-builder -n kg-rca-server

# Scale up (manual)
kubectl scale deployment graph-builder -n kg-rca-server --replicas=20

# Verify scaling
kubectl get pods -n kg-rca-server -l app=graph-builder

# Auto-scaling is enabled by default (5-50 replicas)
# Check HPA status
kubectl get hpa graph-builder -n kg-rca-server

# Expected output:
# NAME            REFERENCE                  TARGETS         MINPODS   MAXPODS   REPLICAS   AGE
# graph-builder   Deployment/graph-builder   45%/70%         5         50        8          10d
```

#### Scale KG API

```bash
# Scale up manually
kubectl scale deployment kg-api -n kg-rca-server --replicas=30

# Auto-scaling is enabled (10-100 replicas)
kubectl get hpa kg-api -n kg-rca-server
```

#### Scale Kafka

```bash
# Scale Kafka brokers (requires careful coordination)
# 1. Scale StatefulSet
kubectl scale statefulset kafka -n kg-rca-server --replicas=7

# 2. Wait for new brokers to be ready
kubectl wait --for=condition=ready pod kafka-5 kafka-6 -n kg-rca-server --timeout=300s

# 3. Rebalance partitions
cat > reassignment.json <<EOF
{
  "version": 1,
  "partitions": [
    // Partition reassignment config
  ]
}
EOF

kubectl exec -n kg-rca-server kafka-0 -- kafka-reassign-partitions.sh \
  --bootstrap-server kafka:9092 \
  --reassignment-json-file /tmp/reassignment.json \
  --execute
```

### Vertical Scaling

#### Increase Neo4j Resources

```bash
# Edit StatefulSet
kubectl edit statefulset neo4j -n kg-rca-server

# Update resources:
# spec:
#   template:
#     spec:
#       containers:
#       - name: neo4j
#         resources:
#           requests:
#             cpu: 16000m
#             memory: 128Gi
#           limits:
#             cpu: 32000m
#             memory: 256Gi

# Also update config for heap size
# env:
# - name: NEO4J_server_memory_heap_max__size
#   value: "64G"

# Rolling restart (one pod at a time)
kubectl rollout restart statefulset neo4j -n kg-rca-server

# Monitor rolling update
kubectl rollout status statefulset neo4j -n kg-rca-server
```

#### Expand Storage

```bash
# Increase PVC size (requires storage class to support expansion)
kubectl patch pvc neo4j-data-neo4j-0 -n kg-rca-server \
  -p '{"spec":{"resources":{"requests":{"storage":"1Ti"}}}}'

# Verify expansion
kubectl get pvc neo4j-data-neo4j-0 -n kg-rca-server

# Repeat for all Neo4j pods
kubectl patch pvc neo4j-data-neo4j-1 -n kg-rca-server \
  -p '{"spec":{"resources":{"requests":{"storage":"1Ti"}}}}'
kubectl patch pvc neo4j-data-neo4j-2 -n kg-rca-server \
  -p '{"spec":{"resources":{"requests":{"storage":"1Ti"}}}}'
```

---

## Backup & Restore

### Automated Backups

#### Neo4j Backup CronJob

```yaml
# neo4j-backup-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: neo4j-backup
  namespace: kg-rca-server
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: neo4j:5.20
            command:
            - /bin/bash
            - -c
            - |
              # List all databases
              DATABASES=$(cypher-shell -u neo4j -p $NEO4J_PASSWORD \
                "SHOW DATABASES YIELD name WHERE name STARTS WITH 'client_' RETURN name;" | \
                tail -n +2 | head -n -1)

              # Backup each database
              for DB in $DATABASES; do
                echo "Backing up database: $DB"
                neo4j-admin database dump $DB --to-path=/backups/$DB-$(date +%Y%m%d).dump
              done

              # Upload to S3
              aws s3 sync /backups s3://kg-rca-backups/neo4j/$(date +%Y%m%d)/

              # Cleanup old local backups (keep last 7 days)
              find /backups -name "*.dump" -mtime +7 -delete
            env:
            - name: NEO4J_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: neo4j-auth
                  key: password
            volumeMounts:
            - name: backups
              mountPath: /backups
          volumes:
          - name: backups
            emptyDir: {}
          restartPolicy: OnFailure
```

#### PostgreSQL Backup

```bash
# Create backup CronJob
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgresql-backup
  namespace: kg-rca-server
spec:
  schedule: "0 3 * * *"  # Daily at 3 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:16
            command:
            - /bin/bash
            - -c
            - |
              pg_dump -h postgresql -U billing -d billing -F c -f /backups/billing-$(date +%Y%m%d).dump
              aws s3 cp /backups/billing-$(date +%Y%m%d).dump s3://kg-rca-backups/postgresql/
            env:
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgresql-auth
                  key: password
            volumeMounts:
            - name: backups
              mountPath: /backups
          volumes:
          - name: backups
            emptyDir: {}
          restartPolicy: OnFailure
EOF
```

### Manual Backup

```bash
# Backup single Neo4j database
kubectl exec -n kg-rca-server neo4j-0 -- neo4j-admin database dump \
  client_acme_abc123_kg \
  --to-path=/backups/client_acme_abc123_kg-manual.dump

# Copy to local machine
kubectl cp kg-rca-server/neo4j-0:/backups/client_acme_abc123_kg-manual.dump \
  ./client_acme_abc123_kg-manual.dump

# Backup PostgreSQL
kubectl exec -n kg-rca-server postgresql-0 -- pg_dump -U billing -F c -f /tmp/billing-backup.dump
kubectl cp kg-rca-server/postgresql-0:/tmp/billing-backup.dump ./billing-backup.dump
```

### Restore Procedures

#### Restore Neo4j Database

```bash
# Upload backup file to pod
kubectl cp ./client_acme_abc123_kg-backup.dump \
  kg-rca-server/neo4j-0:/backups/restore.dump

# Stop database (if running)
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  "STOP DATABASE client_acme_abc123_kg;"

# Restore from dump
kubectl exec -n kg-rca-server neo4j-0 -- neo4j-admin database load \
  client_acme_abc123_kg \
  --from-path=/backups/restore.dump \
  --overwrite-destination=true

# Start database
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  "START DATABASE client_acme_abc123_kg;"

# Verify
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (n) RETURN count(n) LIMIT 1;"
```

#### Restore PostgreSQL

```bash
# Upload backup
kubectl cp ./billing-backup.dump kg-rca-server/postgresql-0:/tmp/restore.dump

# Restore
kubectl exec -n kg-rca-server postgresql-0 -- pg_restore \
  -U billing \
  -d billing \
  --clean \
  --if-exists \
  /tmp/restore.dump

# Verify
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -c "SELECT count(*) FROM clients;"
```

---

## Client Management

### Add New Client

```bash
# See CLIENT_ONBOARDING.md for full procedure
# Quick reference:

# 1. Create client record
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -c \
  "INSERT INTO clients (id, name, email, plan, status, created_at, updated_at) \
   VALUES ('client-newco-xyz789', 'NewCo Inc', 'admin@newco.com', 'basic', 'active', NOW(), NOW());"

# 2. Generate API key
./generate-api-key.sh client-newco-xyz789

# 3. Create Kafka credentials
KAFKA_PASSWORD=$(openssl rand -base64 32)
kubectl exec -n kg-rca-server kafka-0 -- kafka-configs.sh \
  --bootstrap-server kafka:9092 \
  --alter \
  --add-config "SCRAM-SHA-512=[password=$KAFKA_PASSWORD]" \
  --entity-type users \
  --entity-name client-newco-xyz789

# 4. Create Neo4j database
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  "CREATE DATABASE client_newco_xyz789_kg;"

# 5. Create Kafka topics and ACLs
# (See onboarding doc for full commands)
```

### Upgrade Client Plan

```bash
# Update client plan
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -c \
  "UPDATE clients SET plan = 'pro', updated_at = NOW() WHERE id = 'client-acme-abc123';"

# Update rate limits (if using separate rate limiting service)
# Update billing in Stripe
```

### Suspend Client

```bash
# Suspend client (stop data ingestion but keep data)
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -c \
  "UPDATE clients SET status = 'suspended', updated_at = NOW() WHERE id = 'client-acme-abc123';"

# Revoke Kafka ACLs
kubectl exec -n kg-rca-server kafka-0 -- kafka-acls.sh \
  --bootstrap-server kafka:9092 \
  --remove \
  --allow-principal User:client-acme-abc123 \
  --operation All \
  --topic "*" \
  --force

# API requests will return 403 Forbidden
```

### Delete Client

```bash
# See CLIENT_ONBOARDING.md for full offboarding procedure

# 1. Export data (if requested)
kubectl exec -n kg-rca-server neo4j-0 -- neo4j-admin database dump \
  client_acme_abc123_kg \
  --to-path=/backups/client_acme_abc123_kg-final.dump

# 2. Delete Neo4j database
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  "DROP DATABASE client_acme_abc123_kg;"

# 3. Delete Kafka topics
for topic in $(kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
  --bootstrap-server kafka:9092 --list | grep "client-acme-abc123"); do
  kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
    --bootstrap-server kafka:9092 \
    --delete \
    --topic "$topic"
done

# 4. Update client status
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -c \
  "UPDATE clients SET status = 'deleted', updated_at = NOW() WHERE id = 'client-acme-abc123';"
```

---

## Performance Tuning

### Neo4j Tuning

```yaml
# Adjust Neo4j configuration based on workload
neo4j:
  config:
    # Memory settings (adjust based on available RAM)
    server.memory.heap.max_size: "64G"
    server.memory.heap.initial_size: "32G"
    server.memory.pagecache.size: "32G"

    # Transaction settings
    db.memory.transaction.total_max: "32G"
    db.memory.transaction.max: "16G"

    # Query cache
    dbms.query.cache_size: "2000"

    # Checkpoint settings (for write-heavy workloads)
    db.checkpoint.interval.time: "15m"
    db.checkpoint.interval.tx: "100000"

    # Bolt connections
    dbms.connector.bolt.thread_pool_max_size: "800"
```

### Kafka Tuning

```yaml
# Kafka broker configuration
kafka:
  config:
    # Message batching (for high throughput)
    batch.size: "32768"
    linger.ms: "10"

    # Compression
    compression.type: "gzip"

    # Replication
    default.replication.factor: "3"
    min.insync.replicas: "2"

    # Retention (adjust based on data volume)
    log.retention.hours: "168"  # 7 days
    log.retention.bytes: "1099511627776"  # 1TB per topic

    # Segment size
    log.segment.bytes: "1073741824"  # 1GB

    # Network threads
    num.network.threads: "8"
    num.io.threads: "16"
```

### Graph Builder Tuning

```bash
# Adjust batch size for message processing
kubectl set env deployment/graph-builder -n kg-rca-server \
  KAFKA_CONSUMER_BATCH_SIZE=100 \
  KAFKA_CONSUMER_BATCH_TIMEOUT_MS=1000

# Adjust RCA window
kubectl set env deployment/graph-builder -n kg-rca-server \
  RCA_WINDOW_MIN=15 \
  RCA_MAX_CAUSES=10

# Tune resource limits
kubectl set resources deployment graph-builder -n kg-rca-server \
  --requests=cpu=2000m,memory=4Gi \
  --limits=cpu=4000m,memory=8Gi
```

---

## Cost Optimization

### Resource Right-Sizing

```bash
# Analyze actual resource usage over 7 days
kubectl top pods -n kg-rca-server --containers | tee resource-usage.txt

# Identify over-provisioned pods
# Example: If Graph Builder is using 1CPU but requested 2CPU, reduce:
kubectl set resources deployment graph-builder -n kg-rca-server \
  --requests=cpu=1000m,memory=2Gi \
  --limits=cpu=2000m,memory=4Gi
```

### Storage Optimization

```bash
# Review storage usage per client
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  "SHOW DATABASES YIELD name, sizeOnDisk ORDER BY sizeOnDisk DESC;"

# Expected output:
# name                      | sizeOnDisk
# --------------------------|------------
# client_bigco_kg           | 50 GB
# client_medco_kg           | 10 GB
# client_smallco_kg         | 1 GB

# Compress old data or reduce retention
# For Kafka, reduce retention for low-value clients
kubectl exec -n kg-rca-server kafka-0 -- kafka-configs.sh \
  --bootstrap-server kafka:9092 \
  --alter \
  --entity-type topics \
  --entity-name client-smallco.logs.normalized \
  --add-config retention.hours=24
```

### Auto-Scaling Optimization

```bash
# Review HPA metrics
kubectl get hpa -n kg-rca-server

# Adjust scale-down behavior to reduce pod churn
kubectl patch hpa graph-builder -n kg-rca-server -p \
  '{"spec":{"behavior":{"scaleDown":{"stabilizationWindowSeconds":600}}}}'
```

---

## Incident Response

### Severity Levels

| Severity | Description | Response Time | Example |
|----------|-------------|---------------|---------|
| **P0 - Critical** | Service down for all clients | < 15 minutes | Neo4j cluster down |
| **P1 - High** | Service degraded for all clients | < 1 hour | High Kafka lag |
| **P2 - Medium** | Service down for 1 client | < 4 hours | Single client Neo4j DB corrupt |
| **P3 - Low** | Minor issue, workaround available | < 24 hours | Dashboard not loading |

### Incident Response Procedure

```bash
# 1. ACKNOWLEDGE
# - Post in #incidents Slack channel
# - Create incident ticket

# 2. ASSESS
# - Check monitoring dashboards
# - Review recent changes (deployments, config changes)
# - Collect logs

# 3. MITIGATE
# - Apply immediate fix or workaround
# - Scale resources if needed
# - Communicate with affected clients

# 4. RESOLVE
# - Implement permanent fix
# - Verify fix with monitoring
# - Update documentation

# 5. POST-MORTEM
# - Write incident report
# - Identify root cause
# - Create prevention tasks
```

### Common Incident Scenarios

**Scenario 1: Neo4j Cluster Split-Brain**

```bash
# Symptoms: Multiple leaders, data inconsistency
# 1. Check cluster status
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  "CALL dbms.cluster.overview();"

# 2. Identify correct leader (most recent transactions)
# 3. Force re-election if needed
kubectl exec -n kg-rca-server neo4j-1 -- cypher-shell -u neo4j -p $PASSWORD \
  "CALL dbms.cluster.role.observer();"

# 4. Restart followers to rejoin cluster
kubectl delete pod neo4j-1 neo4j-2 -n kg-rca-server
```

**Scenario 2: Kafka Broker Failure**

```bash
# Symptoms: Increased lag, producer errors
# 1. Check broker status
kubectl get pods -n kg-rca-server -l app=kafka

# 2. Check under-replicated partitions
kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --under-replicated-partitions

# 3. Restart failed broker
kubectl delete pod kafka-3 -n kg-rca-server

# 4. Monitor partition reassignment
kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --describe
```

---

## Maintenance Windows

### Scheduled Maintenance

```bash
# Announce maintenance window
# - Email all clients 7 days in advance
# - Post on status page
# - Slack notification 24 hours before

# Example maintenance script
#!/bin/bash
# monthly-maintenance.sh

echo "Starting monthly maintenance - $(date)"

# 1. Put system in maintenance mode (return 503 for API)
kubectl scale deployment kg-api -n kg-rca-server --replicas=0
kubectl apply -f maintenance-page.yaml

# 2. Update Helm chart
helm upgrade kg-rca-server . \
  --namespace kg-rca-server \
  --values production-values.yaml

# 3. Run database maintenance
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  "CALL apoc.maintenance.compact();"

# 4. Vacuum PostgreSQL
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -c "VACUUM ANALYZE;"

# 5. Clean up old Kafka data
kubectl exec -n kg-rca-server kafka-0 -- kafka-log-dirs.sh \
  --bootstrap-server kafka:9092 \
  --describe

# 6. Restore API service
kubectl scale deployment kg-api -n kg-rca-server --replicas=10

echo "Maintenance complete - $(date)"
```

---

## Capacity Planning

### Current Capacity Assessment

```bash
# Analyze current usage
echo "=== Capacity Report ==="
echo "Date: $(date)"
echo ""

# Client count
TOTAL_CLIENTS=$(kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -t -c \
  "SELECT count(*) FROM clients WHERE status = 'active';" | xargs)
echo "Active clients: $TOTAL_CLIENTS"

# Total events per day
TOTAL_EVENTS=$(kubectl exec -n kg-rca-server kafka-0 -- kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list kafka:9092 --topic "*events.normalized" | \
  awk -F: '{sum+=$3} END {print sum}')
echo "Total events stored: $TOTAL_EVENTS"

# Storage usage
NEO4J_STORAGE=$(kubectl exec -n kg-rca-server neo4j-0 -- df -h /data | tail -1 | awk '{print $3}')
KAFKA_STORAGE=$(kubectl exec -n kg-rca-server kafka-0 -- df -h /kafka | tail -1 | awk '{print $3}')
echo "Neo4j storage used: $NEO4J_STORAGE"
echo "Kafka storage used: $KAFKA_STORAGE"

# Resource utilization
kubectl top nodes
kubectl top pods -n kg-rca-server
```

### Growth Projections

```bash
# Calculate when capacity limits will be reached
# Example: If adding 10 clients per month
CURRENT_CLIENTS=50
GROWTH_RATE=10  # clients per month
MAX_CLIENTS=200  # based on current infrastructure

MONTHS_UNTIL_FULL=$(( (MAX_CLIENTS - CURRENT_CLIENTS) / GROWTH_RATE ))
echo "Estimated capacity exhaustion: $MONTHS_UNTIL_FULL months"

# Plan infrastructure scaling 3 months before capacity
SCALE_UP_MONTH=$(( MONTHS_UNTIL_FULL - 3 ))
echo "Plan infrastructure scaling in: $SCALE_UP_MONTH months"
```

---

## Operations Checklist

**Daily**:
- [ ] Run health check script
- [ ] Review Grafana dashboards
- [ ] Check for critical alerts
- [ ] Review error logs

**Weekly**:
- [ ] Generate client activity summary
- [ ] Review resource utilization
- [ ] Check backup success
- [ ] Review incident tickets

**Monthly**:
- [ ] Capacity planning review
- [ ] Performance tuning
- [ ] Update client billing
- [ ] Run maintenance window
- [ ] Review and update documentation

**Quarterly**:
- [ ] Disaster recovery test
- [ ] Security audit
- [ ] Cost optimization review
- [ ] Client satisfaction survey
- [ ] Infrastructure upgrade planning

---

**Document Version**: 1.0.0
**Maintained By**: Platform Engineering Team
**Last Review**: 2025-01-09
