# KG-RCA Platform Troubleshooting Playbook

Complete troubleshooting guide for common issues in KG-RCA platform v2.0.0+.

---

## Table of Contents

1. [Control Plane Issues](#1-control-plane-issues)
2. [Kafka Issues](#2-kafka-issues)
3. [Neo4j Issues](#3-neo4j-issues)
4. [Client Cluster Issues](#4-client-cluster-issues)
5. [Data Flow Issues](#5-data-flow-issues)
6. [Network & Connectivity](#6-network--connectivity)
7. [Performance Issues](#7-performance-issues)
8. [Emergency Procedures](#8-emergency-procedures)

---

## 1. Control Plane Issues

### Issue 1.1: Control Plane Not Starting

**Symptoms:**
- Container exits immediately
- `docker ps` doesn't show `kg-control-plane`

**Diagnosis:**
```bash
# Check container logs
docker logs kg-control-plane --tail 100

# Check if ports are already in use
sudo lsof -i :9090

# Verify environment variables
docker inspect kg-control-plane | jq '.[0].Config.Env'
```

**Solutions:**

**A. Port Conflict:**
```bash
# Find process using port 9090
sudo lsof -i :9090

# Kill the process or change control plane port
docker stop kg-control-plane
docker rm kg-control-plane

# Edit docker-compose-control-plane.yml to use different port
# Then restart
docker compose -f docker-compose-control-plane.yml up -d
```

**B. Kafka Connection Failed:**
```bash
# Verify Kafka is running
docker ps | grep kg-kafka

# Test Kafka connectivity
docker exec kg-kafka kafka-broker-api-versions \
  --bootstrap-server kg-kafka:29092

# Check network
docker network inspect mini-server-prod_kg-network | grep kg-kafka
```

**C. Neo4j Connection Failed:**
```bash
# Verify Neo4j is running
docker ps | grep kg-neo4j

# Test Neo4j connection
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "RETURN 1 as test;"

# Check Neo4j logs
docker logs kg-neo4j --tail 50 | grep ERROR
```

**D. Docker Socket Permission:**
```bash
# Verify control plane can access Docker socket
docker exec kg-control-plane ls -la /var/run/docker.sock

# Fix permissions if needed
sudo chmod 666 /var/run/docker.sock

# Or add control plane to docker group (preferred)
docker exec kg-control-plane getent group docker
```

### Issue 1.2: Graph-Builder Not Auto-Spawning

**Symptoms:**
- Cluster registered but no graph-builder container
- Metrics show active cluster but spawn count is 0

**Diagnosis:**
```bash
# Check control plane logs
docker logs kg-control-plane | grep "spawning graph-builder"

# Verify cluster registration
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.registry \
  --from-beginning \
  --property print.key=true | grep "af-4"

# Check reconciliation loop
docker logs kg-control-plane | grep "reconciliation"
```

**Solutions:**

**A. Docker API Error:**
```bash
# Check Docker socket permissions
docker exec kg-control-plane ls -la /var/run/docker.sock

# Restart control plane with proper permissions
docker stop kg-control-plane
docker rm kg-control-plane
docker compose -f docker-compose-control-plane.yml up -d
```

**B. Image Pull Error:**
```bash
# Check if image exists
docker pull anuragvishwa/kg-graph-builder:1.0.20

# Check control plane logs for pull errors
docker logs kg-control-plane | grep "image pull"

# Manually spawn to test
docker run -d \
  --name kg-graph-builder-af-4 \
  --network mini-server-prod_kg-network \
  -e CLIENT_ID=af-4 \
  -e KAFKA_BROKERS=kg-kafka:29092 \
  -e NEO4J_URI=bolt://kg-neo4j:7687 \
  -e NEO4J_USER=neo4j \
  -e NEO4J_PASSWORD=Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  anuragvishwa/kg-graph-builder:1.0.20
```

**C. Network Issues:**
```bash
# Verify network exists
docker network ls | grep kg-network

# Check if control plane is on the network
docker network inspect mini-server-prod_kg-network | grep kg-control-plane

# Recreate network if needed
docker network create mini-server-prod_kg-network
```

### Issue 1.3: Stale Clusters Not Cleaning Up

**Symptoms:**
- Clusters marked as stale but not removed
- Graph-builder containers still running for dead clusters

**Diagnosis:**
```bash
# Check heartbeats
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.heartbeat \
  --from-beginning | tail -20

# Check control plane metrics
curl -s http://localhost:9090/metrics | grep stale

# Check cleanup logs
docker logs kg-control-plane | grep "cleanup"
```

**Solutions:**

**A. Heartbeat Timeout Too Long:**
```bash
# Adjust timeout in environment (edit docker-compose-control-plane.yml)
HEARTBEAT_TIMEOUT=2m  # Change to 1m
CLEANUP_TIMEOUT=5m     # Change to 3m

# Restart control plane
docker compose -f docker-compose-control-plane.yml up -d
```

**B. Reconciliation Loop Not Running:**
```bash
# Check if reconciliation is happening
docker logs kg-control-plane | grep "reconciliation started"

# Restart control plane
docker restart kg-control-plane

# Monitor logs
docker logs kg-control-plane --follow
```

**C. Manual Cleanup:**
```bash
# Stop stale graph-builder
docker stop kg-graph-builder-af-X
docker rm kg-graph-builder-af-X

# Manually trigger cleanup in Neo4j
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "MATCH (n:Resource {client_id: 'af-X'}) DETACH DELETE n;"
```

---

## 2. Kafka Issues

### Issue 2.1: Kafka Container Won't Start

**Symptoms:**
- `kg-kafka` exits immediately
- Error: "data directory not writable"

**Diagnosis:**
```bash
# Check Kafka logs
docker logs kg-kafka

# Check volume permissions
docker volume inspect mini-server-prod_kafka-data

# Check disk space
df -h
```

**Solutions:**

**A. Volume Permission Error:**
```bash
# Stop Kafka
docker stop kg-kafka
docker rm kg-kafka

# Remove old volume
docker volume rm mini-server-prod_kafka-data

# Restart (will create fresh volume)
docker compose -f docker-compose-control-plane.yml up -d kg-kafka
```

**B. Port Conflict:**
```bash
# Check if ports 9092/29092 are in use
sudo lsof -i :9092
sudo lsof -i :29092

# Change ports in docker-compose-control-plane.yml if needed
```

**C. Disk Space Full:**
```bash
# Check disk usage
df -h

# Clean up Docker
docker system prune -a --volumes

# Clean old Kafka segments
docker exec kg-kafka kafka-configs \
  --bootstrap-server kg-kafka:29092 \
  --entity-type topics \
  --entity-name state.k8s.resource \
  --alter \
  --add-config retention.ms=3600000
```

### Issue 2.2: Topics Not Created

**Symptoms:**
- `kafka-topics --list` shows empty or missing topics
- Consumer/producer errors about missing topics

**Diagnosis:**
```bash
# List topics
docker exec kg-kafka kafka-topics \
  --bootstrap-server kg-kafka:29092 \
  --list

# Check Kafka logs
docker logs kg-kafka | grep -i topic
```

**Solutions:**

**A. Manual Topic Creation:**
```bash
# Create cluster.registry topic
docker exec kg-kafka kafka-topics \
  --bootstrap-server kg-kafka:29092 \
  --create \
  --topic cluster.registry \
  --partitions 1 \
  --replication-factor 1 \
  --config cleanup.policy=compact

# Create cluster.heartbeat topic
docker exec kg-kafka kafka-topics \
  --bootstrap-server kg-kafka:29092 \
  --create \
  --topic cluster.heartbeat \
  --partitions 1 \
  --replication-factor 1 \
  --config retention.ms=3600000

# Create state.k8s.resource topic
docker exec kg-kafka kafka-topics \
  --bootstrap-server kg-kafka:29092 \
  --create \
  --topic state.k8s.resource \
  --partitions 3 \
  --replication-factor 1

# Create events.normalized topic
docker exec kg-kafka kafka-topics \
  --bootstrap-server kg-kafka:29092 \
  --create \
  --topic events.normalized \
  --partitions 3 \
  --replication-factor 1
```

**B. Auto-Create Enabled:**
```bash
# Enable auto topic creation (edit docker-compose-control-plane.yml)
KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"

# Restart Kafka
docker restart kg-kafka
```

### Issue 2.3: High Consumer Lag

**Symptoms:**
- Consumer group shows high lag
- Data not appearing in Neo4j quickly

**Diagnosis:**
```bash
# Check consumer lag
docker exec kg-kafka kafka-consumer-groups \
  --bootstrap-server kg-kafka:29092 \
  --group graph-builder-af-4 \
  --describe

# Check partition assignment
docker exec kg-kafka kafka-consumer-groups \
  --bootstrap-server kg-kafka:29092 \
  --group graph-builder-af-4 \
  --describe | grep "CURRENT-OFFSET"
```

**Solutions:**

**A. Scale Up Graph-Builder:**
```bash
# Increase partitions first
docker exec kg-kafka kafka-topics \
  --bootstrap-server kg-kafka:29092 \
  --alter \
  --topic state.k8s.resource \
  --partitions 6

# Note: Cannot auto-spawn multiple graph-builders per cluster yet
# This is a future enhancement
```

**B. Increase Consumer Throughput:**
```bash
# Edit graph-builder environment (in control plane spawn code)
# Increase batch size and fetch parameters
MAX_POLL_RECORDS=1000
FETCH_MIN_BYTES=1048576
```

**C. Reset Consumer Offset:**
```bash
# Only if data loss is acceptable
docker exec kg-kafka kafka-consumer-groups \
  --bootstrap-server kg-kafka:29092 \
  --group graph-builder-af-4 \
  --reset-offsets \
  --to-latest \
  --execute \
  --topic state.k8s.resource
```

---

## 3. Neo4j Issues

### Issue 3.1: Neo4j Connection Refused

**Symptoms:**
- Graph-builder logs show "connection refused"
- Cannot access Neo4j Browser

**Diagnosis:**
```bash
# Check if Neo4j is running
docker ps | grep kg-neo4j

# Check Neo4j logs
docker logs kg-neo4j --tail 100

# Test connection
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "RETURN 1;"
```

**Solutions:**

**A. Neo4j Still Starting:**
```bash
# Wait for Neo4j to be fully ready (can take 30-60s)
docker logs kg-neo4j --follow

# Look for "Started." message
# Then test again
```

**B. Wrong Credentials:**
```bash
# Check environment variables
docker inspect kg-neo4j | jq '.[0].Config.Env' | grep NEO4J

# Reset password if needed
docker exec -it kg-neo4j neo4j-admin set-initial-password Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA
```

**C. Port Not Exposed:**
```bash
# Check port mapping
docker port kg-neo4j

# Should show:
# 7474/tcp -> 0.0.0.0:7474
# 7687/tcp -> 0.0.0.0:7687

# Restart with correct ports if needed
docker stop kg-neo4j
docker rm kg-neo4j
docker compose -f docker-compose-control-plane.yml up -d kg-neo4j
```

### Issue 3.2: Neo4j Out of Memory

**Symptoms:**
- Neo4j container OOMKilled
- Neo4j logs show "OutOfMemoryError"
- Queries extremely slow

**Diagnosis:**
```bash
# Check container memory
docker stats kg-neo4j --no-stream

# Check Neo4j heap usage
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "CALL dbms.queryJmx('java.lang:type=Memory') YIELD attributes RETURN attributes.HeapMemoryUsage;"

# Count nodes
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "MATCH (n) RETURN count(n);"
```

**Solutions:**

**A. Increase Memory Limits:**
```bash
# Edit docker-compose-control-plane.yml
# Under kg-neo4j service:
environment:
  - NEO4J_server_memory_heap_initial__size=2G
  - NEO4J_server_memory_heap_max__size=4G
  - NEO4J_server_memory_pagecache_size=2G

deploy:
  resources:
    limits:
      memory: 8G

# Restart Neo4j
docker compose -f docker-compose-control-plane.yml up -d kg-neo4j
```

**B. Clean Old Data:**
```bash
# Delete old events (older than 7 days)
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "MATCH (e:Event) WHERE e.timestamp < datetime() - duration({days: 7}) DETACH DELETE e;"

# Delete old alerts
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "MATCH (a:Alert) WHERE a.status = 'resolved' AND a.ends_at < datetime() - duration({days: 7}) DETACH DELETE a;"
```

**C. Optimize Queries:**
```cypher
// Create indexes for common queries
CREATE INDEX resource_client_id IF NOT EXISTS FOR (n:Resource) ON (n.client_id);
CREATE INDEX resource_kind IF NOT EXISTS FOR (n:Resource) ON (n.kind);
CREATE INDEX resource_name IF NOT EXISTS FOR (n:Resource) ON (n.name);
CREATE INDEX event_timestamp IF NOT EXISTS FOR (n:Event) ON (n.timestamp);
CREATE INDEX alert_status IF NOT EXISTS FOR (n:Alert) ON (n.status);
```

### Issue 3.3: Slow Queries

**Symptoms:**
- Queries taking >10 seconds
- Browser timeouts
- High CPU usage

**Diagnosis:**
```cypher
// List long-running queries
CALL dbms.listQueries()
YIELD queryId, username, query, elapsedTimeMillis
WHERE elapsedTimeMillis > 5000
RETURN queryId, query, elapsedTimeMillis
ORDER BY elapsedTimeMillis DESC;

// Explain query plan
EXPLAIN MATCH (n:Resource {client_id: 'af-4'}) RETURN n;

// Profile query
PROFILE MATCH (n:Resource {client_id: 'af-4'}) RETURN count(n);
```

**Solutions:**

**A. Add Missing Indexes:**
```cypher
// Show existing indexes
SHOW INDEXES;

// Create composite index for common patterns
CREATE INDEX resource_client_kind IF NOT EXISTS
FOR (n:Resource) ON (n.client_id, n.kind);

// Create index on frequently filtered properties
CREATE INDEX resource_namespace IF NOT EXISTS
FOR (n:Resource) ON (n.namespace);
```

**B. Kill Long-Running Query:**
```cypher
// Find query ID
CALL dbms.listQueries()
YIELD queryId, query, elapsedTimeMillis
WHERE elapsedTimeMillis > 10000
RETURN queryId;

// Kill it
CALL dbms.killQuery('query-123');
```

**C. Optimize Query:**
```cypher
// Bad: Full graph scan
MATCH (n) WHERE n.client_id = 'af-4' RETURN n;

// Good: Use label and indexed property
MATCH (n:Resource {client_id: 'af-4'}) RETURN n;

// Bad: Unbounded traversal
MATCH (n)-[*]-(m) RETURN n, m;

// Good: Limit depth
MATCH (n)-[*1..3]-(m) RETURN n, m LIMIT 100;
```

---

## 4. Client Cluster Issues

### Issue 4.1: Helm Install Fails

**Symptoms:**
- `helm install` returns error
- Pods not created

**Diagnosis:**
```bash
# Check Helm release status
helm list -n kgroot -a

# Describe failed release
helm status kg-rca-agent -n kgroot

# Check for events
kubectl get events -n kgroot --sort-by='.lastTimestamp' | tail -20
```

**Solutions:**

**A. Invalid Values:**
```bash
# Validate values.yaml
helm lint client-light/helm-chart \
  --values client-light/helm-chart/values.yaml \
  --set client.id=af-4

# Dry-run to see rendered templates
helm install kg-rca-agent client-light/helm-chart \
  --namespace kgroot \
  --create-namespace \
  --set client.id=af-4 \
  --dry-run --debug
```

**B. Missing Client ID:**
```bash
# Ensure client.id is set
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --namespace kgroot \
  --create-namespace \
  --set client.id=af-4 \  # REQUIRED!
  --set client.kafka.brokers=98.90.147.12:9092
```

**C. Namespace Issues:**
```bash
# Create namespace first
kubectl create namespace kgroot

# Then install
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --namespace kgroot \
  --set client.id=af-4
```

### Issue 4.2: State-Watcher CrashLoopBackOff

**Symptoms:**
- `state-watcher` pod restarting repeatedly
- Logs show errors

**Diagnosis:**
```bash
# Check pod status
kubectl get pods -n kgroot -l app=kg-rca-agent-state-watcher

# View logs
kubectl logs -n kgroot -l app=kg-rca-agent-state-watcher --tail=100

# Describe pod
kubectl describe pod -n kgroot -l app=kg-rca-agent-state-watcher
```

**Solutions:**

**A. Kafka Connection Failed:**
```bash
# Test Kafka connectivity from pod
kubectl exec -n kgroot -it <state-watcher-pod> -- nc -zv 98.90.147.12 9092

# If fails, check firewall/security groups
# Verify broker address in values.yaml

# Update if needed
helm upgrade kg-rca-agent anuragvishwa/kg-rca-agent \
  --namespace kgroot \
  --set client.id=af-4 \
  --set client.kafka.brokers=CORRECT_IP:9092 \
  --reuse-values
```

**B. RBAC Permissions:**
```bash
# Check if ServiceAccount has permissions
kubectl auth can-i list pods --as=system:serviceaccount:kgroot:kg-rca-agent -n kgroot
kubectl auth can-i list nodes --as=system:serviceaccount:kgroot:kg-rca-agent

# If false, check ClusterRole
kubectl get clusterrole kg-rca-agent -o yaml

# Reinstall chart if RBAC is missing
helm uninstall kg-rca-agent -n kgroot
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --namespace kgroot \
  --set client.id=af-4
```

**C. Memory/CPU Limits:**
```bash
# Check resource limits
kubectl describe pod -n kgroot -l app=kg-rca-agent-state-watcher | grep -A 5 Limits

# Increase if OOMKilled
helm upgrade kg-rca-agent anuragvishwa/kg-rca-agent \
  --namespace kgroot \
  --set client.id=af-4 \
  --set stateWatcher.resources.limits.memory=512Mi \
  --reuse-values
```

### Issue 4.3: Registration Job Failed

**Symptoms:**
- Registration job shows "Error" or "Failed" status
- Cluster not appearing in control plane

**Diagnosis:**
```bash
# Check job status
kubectl get jobs -n kgroot | grep register

# View job logs
kubectl logs -n kgroot job/kg-rca-agent-register-cluster

# Check events
kubectl describe job -n kgroot kg-rca-agent-register-cluster
```

**Solutions:**

**A. Kafka Connection Failed:**
```bash
# Test from job pod
kubectl run kafka-test -n kgroot --rm -it --image=confluentinc/cp-kafka:7.5.0 -- \
  kafka-broker-api-versions --bootstrap-server 98.90.147.12:9092

# If fails, check network/firewall
```

**B. JSON Parsing Error:**
```bash
# Check registration job logs for parse errors
kubectl logs -n kgroot job/kg-rca-agent-register-cluster

# If "No key separator found", upgrade to chart v2.0.2+
helm repo update
helm upgrade kg-rca-agent anuragvishwa/kg-rca-agent \
  --namespace kgroot \
  --set client.id=af-4 \
  --reuse-values
```

**C. Manual Registration:**
```bash
# Manually register cluster
docker exec kg-kafka kafka-console-producer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.registry \
  --property "parse.key=true" \
  --property "key.separator=:" << EOF
af-4:{"client_id":"af-4","cluster_name":"af-4","version":"2.0.2","registered_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","metadata":{"namespace":"kgroot"}}
EOF
```

---

## 5. Data Flow Issues

### Issue 5.1: No Data in Neo4j

**Symptoms:**
- Neo4j database empty or has very few nodes
- Queries return 0 results

**Diagnosis:**
```bash
# Count resources in Neo4j
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "MATCH (n:Resource {client_id: 'af-4'}) RETURN count(n);"

# Check if messages in Kafka
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic state.k8s.resource \
  --max-messages 5 --timeout-ms 5000

# Check graph-builder status
docker ps | grep kg-graph-builder-af-4
docker logs kg-graph-builder-af-4 --tail 100
```

**Solutions:**

**A. State-Watcher Not Running:**
```bash
# Check state-watcher pod
kubectl get pods -n kgroot -l app=kg-rca-agent-state-watcher

# If not running, check logs and fix (see section 4.2)
```

**B. Graph-Builder Not Spawned:**
```bash
# Check if graph-builder exists
docker ps | grep kg-graph-builder-af-4

# If not, check control plane (see section 1.2)

# Manually spawn for testing
docker run -d \
  --name kg-graph-builder-af-4 \
  --network mini-server-prod_kg-network \
  -e CLIENT_ID=af-4 \
  -e KAFKA_BROKERS=kg-kafka:29092 \
  -e NEO4J_URI=bolt://kg-neo4j:7687 \
  -e NEO4J_USER=neo4j \
  -e NEO4J_PASSWORD=Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  anuragvishwa/kg-graph-builder:1.0.20
```

**C. Graph-Builder Errors:**
```bash
# Check graph-builder logs for errors
docker logs kg-graph-builder-af-4 | grep -i error

# Common errors:
# - Neo4j connection: Check Neo4j status
# - Kafka consumer: Check Kafka connectivity
# - Parse error: Check message format in Kafka

# Restart graph-builder
docker restart kg-graph-builder-af-4
```

### Issue 5.2: Events Not Appearing

**Symptoms:**
- No Event nodes in Neo4j
- Event-exporter logs show errors

**Diagnosis:**
```bash
# Check event-exporter pod
kubectl get pods -n kgroot -l app=kg-rca-agent-event-exporter

# View logs
kubectl logs -n kgroot -l app=kg-rca-agent-event-exporter --tail=100

# Check events in Kafka
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic events.normalized \
  --max-messages 5 --timeout-ms 5000

# Check events in Neo4j
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "MATCH (e:Event {client_id: 'af-4'}) RETURN count(e);"
```

**Solutions:**

**A. Event-Exporter Not Running:**
```bash
# Check pod status
kubectl get pods -n kgroot -l app=kg-rca-agent-event-exporter

# Check logs for errors
kubectl logs -n kgroot -l app=kg-rca-agent-event-exporter

# Restart if needed
kubectl delete pod -n kgroot -l app=kg-rca-agent-event-exporter
```

**B. Missing client_id:**
```bash
# Ensure chart version is v2.0.0+ with client_id injection
helm list -n kgroot

# If older version, upgrade
helm upgrade kg-rca-agent anuragvishwa/kg-rca-agent \
  --namespace kgroot \
  --set client.id=af-4 \
  --reuse-values
```

### Issue 5.3: Heartbeats Missing

**Symptoms:**
- Cluster marked as stale in control plane
- No heartbeat messages in Kafka

**Diagnosis:**
```bash
# Check heartbeat topic
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.heartbeat \
  --from-beginning | grep af-4

# Check state-watcher logs
kubectl logs -n kgroot -l app=kg-rca-agent-state-watcher | grep heartbeat

# Check control plane logs
docker logs kg-control-plane | grep "heartbeat.*af-4"
```

**Solutions:**

**A. State-Watcher Version Too Old:**
```bash
# Ensure state-watcher has heartbeat code (v1.0.3+)
kubectl describe pod -n kgroot -l app=kg-rca-agent-state-watcher | grep Image

# If older, upgrade chart
helm upgrade kg-rca-agent anuragvishwa/kg-rca-agent \
  --namespace kgroot \
  --set client.id=af-4 \
  --reuse-values
```

**B. Heartbeat Topic Missing:**
```bash
# Create topic manually
docker exec kg-kafka kafka-topics \
  --bootstrap-server kg-kafka:29092 \
  --create \
  --topic cluster.heartbeat \
  --partitions 1 \
  --replication-factor 1 \
  --config retention.ms=3600000

# Restart state-watcher
kubectl delete pod -n kgroot -l app=kg-rca-agent-state-watcher
```

**C. Manual Heartbeat Test:**
```bash
# Send test heartbeat
docker exec kg-kafka kafka-console-producer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.heartbeat << EOF
{"client_id":"af-4","timestamp":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","status":"healthy","metrics":{"resources_sent":0,"uptime_seconds":0}}
EOF

# Verify received
docker logs kg-control-plane | tail -20
```

---

## 6. Network & Connectivity

### Issue 6.1: Cannot Access Neo4j Browser

**Symptoms:**
- http://SERVER_IP:7474 times out or refuses connection

**Diagnosis:**
```bash
# Check if Neo4j port is exposed
docker port kg-neo4j | grep 7474

# Check if port is listening on host
sudo netstat -tulpn | grep 7474

# Test locally on server
curl http://localhost:7474

# Check firewall
sudo iptables -L -n | grep 7474
```

**Solutions:**

**A. Firewall Blocking:**
```bash
# Allow port 7474 (Ubuntu/Debian)
sudo ufw allow 7474/tcp
sudo ufw reload

# AWS Security Group: Add inbound rule for port 7474

# Test again
curl http://SERVER_IP:7474
```

**B. Docker Not Binding to 0.0.0.0:**
```bash
# Check port binding
docker port kg-neo4j

# Should show: 7474/tcp -> 0.0.0.0:7474
# If shows 127.0.0.1:7474, edit docker-compose-control-plane.yml

# Change:
ports:
  - "0.0.0.0:7474:7474"
  - "0.0.0.0:7687:7687"

# Restart
docker compose -f docker-compose-control-plane.yml up -d
```

### Issue 6.2: Kafka Not Reachable from Client Cluster

**Symptoms:**
- State-watcher/event-exporter logs show connection refused
- Kafka test fails from client cluster

**Diagnosis:**
```bash
# Test from client cluster pod
kubectl run kafka-test -n kgroot --rm -it --image=busybox -- \
  nc -zv 98.90.147.12 9092

# Test DNS resolution
kubectl run dns-test -n kgroot --rm -it --image=busybox -- \
  nslookup 98.90.147.12

# Check Kafka advertised listeners
docker logs kg-kafka | grep advertised
```

**Solutions:**

**A. Firewall Issue:**
```bash
# On server, allow port 9092
sudo ufw allow 9092/tcp

# AWS Security Group: Add inbound rule for 9092 from client cluster CIDR

# Test again from client cluster
```

**B. Wrong Broker Address:**
```bash
# Use external IP, not internal Docker IP
# Check current value
kubectl get configmap -n kgroot -o yaml | grep brokers

# Update if needed
helm upgrade kg-rca-agent anuragvishwa/kg-rca-agent \
  --namespace kgroot \
  --set client.id=af-4 \
  --set client.kafka.brokers=CORRECT_EXTERNAL_IP:9092 \
  --reuse-values
```

**C. Network Policy Blocking:**
```bash
# Check if network policies are blocking egress
kubectl get networkpolicies -n kgroot

# If blocking, add exception for Kafka IP
```

---

## 7. Performance Issues

### Issue 7.1: High Memory Usage

**Diagnosis:**
```bash
# Check memory usage
docker stats --no-stream

# Check which container is using most memory
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}" | sort -k2 -hr
```

**Solutions:**

**A. Neo4j Memory Tuning:** (see section 3.2)

**B. Kafka Memory Tuning:**
```bash
# Edit docker-compose-control-plane.yml
environment:
  KAFKA_HEAP_OPTS: "-Xmx1G -Xms1G"  # Reduce from 2G if needed

# Restart
docker compose -f docker-compose-control-plane.yml up -d kg-kafka
```

**C. Graph-Builder Memory Leak:**
```bash
# Restart graph-builder daily via cron
# Add to crontab:
0 3 * * * docker restart kg-graph-builder-af-4
```

### Issue 7.2: High CPU Usage

**Diagnosis:**
```bash
# Check CPU usage
docker stats --no-stream

# Check which process inside container
docker exec kg-control-plane top -b -n 1
```

**Solutions:**

**A. Control Plane Reconciliation Too Frequent:**
```bash
# Increase reconciliation interval (edit docker-compose)
RECONCILE_INTERVAL=60s  # Change from 30s

# Restart
docker compose -f docker-compose-control-plane.yml up -d
```

**B. Neo4j Query Load:**
```cypher
// Find expensive queries
CALL dbms.listQueries()
YIELD queryId, query, cpuTimeMillis
WHERE cpuTimeMillis > 1000
RETURN queryId, query, cpuTimeMillis
ORDER BY cpuTimeMillis DESC;

// Kill expensive query
CALL dbms.killQuery('query-123');
```

### Issue 7.3: Disk Space Running Out

**Diagnosis:**
```bash
# Check disk usage
df -h

# Check Docker disk usage
docker system df

# Check specific volumes
docker exec kg-kafka du -sh /var/lib/kafka/data
docker exec kg-neo4j du -sh /data
```

**Solutions:**

**A. Clean Old Docker Resources:**
```bash
# Remove old containers/images
docker system prune -a

# Remove unused volumes (CAUTION: Will delete data!)
docker volume prune
```

**B. Kafka Log Retention:**
```bash
# Reduce retention for high-volume topics
docker exec kg-kafka kafka-configs \
  --bootstrap-server kg-kafka:29092 \
  --entity-type topics \
  --entity-name state.k8s.resource \
  --alter \
  --add-config retention.ms=3600000  # 1 hour
```

**C. Neo4j Data Cleanup:**
```cypher
// Delete old events (older than 7 days)
MATCH (e:Event)
WHERE e.timestamp < datetime() - duration({days: 7})
WITH e LIMIT 10000
DETACH DELETE e;

// Run repeatedly until count = 0
```

---

## 8. Emergency Procedures

### Emergency 8.1: Complete System Restart

```bash
#!/bin/bash
# Use when system is in unknown state

echo "=== Emergency Restart Procedure ==="

# Stop all KG containers
echo "Stopping all containers..."
docker ps --format "{{.Names}}" | grep kg- | xargs -r docker stop

# Wait for graceful shutdown
sleep 10

# Remove containers (not volumes!)
docker ps -a --format "{{.Names}}" | grep kg- | xargs -r docker rm

# Start core infrastructure
echo "Starting core infrastructure..."
docker compose -f docker-compose-control-plane.yml up -d kg-kafka kg-neo4j

# Wait for Kafka and Neo4j to be ready
echo "Waiting for services to be ready..."
sleep 30

# Start control plane
echo "Starting control plane..."
docker compose -f docker-compose-control-plane.yml up -d kg-control-plane

# Wait for control plane
sleep 10

# Start remaining services
echo "Starting remaining services..."
docker compose -f docker-compose-control-plane.yml up -d

echo "=== Restart Complete ==="
echo "Run: docker ps | grep kg-"
echo "Check: curl http://localhost:9090/metrics | grep kg_control_plane"
```

### Emergency 8.2: Data Recovery

**Backup:**
```bash
# Backup Neo4j
docker exec kg-neo4j neo4j-admin database dump neo4j \
  --to-path=/backups --verbose

docker cp kg-neo4j:/backups/neo4j.dump \
  ./neo4j-backup-$(date +%Y%m%d-%H%M).dump

# Backup Kafka topics
docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.registry \
  --from-beginning \
  --timeout-ms 10000 > cluster-registry-backup.json
```

**Restore:**
```bash
# Restore Neo4j
docker cp neo4j-backup-20251023.dump kg-neo4j:/backups/

docker exec kg-neo4j neo4j-admin database load neo4j \
  --from-path=/backups/neo4j-backup-20251023.dump \
  --overwrite-destination=true

docker restart kg-neo4j
```

### Emergency 8.3: Rollback

```bash
# Rollback client cluster
helm rollback kg-rca-agent -n kgroot

# Rollback control plane
docker compose -f docker-compose-control-plane.yml down

# Edit docker-compose-control-plane.yml to use old image versions
# Then:
docker compose -f docker-compose-control-plane.yml up -d
```

---

## Quick Command Reference

```bash
# Health check
docker ps | grep kg- && curl -s http://localhost:9090/metrics | grep kg_control_plane

# View all logs
docker compose -f docker-compose-control-plane.yml logs --tail=50

# Restart everything
docker compose -f docker-compose-control-plane.yml restart

# Check data flow
docker exec kg-kafka kafka-console-consumer --bootstrap-server kg-kafka:29092 --topic state.k8s.resource --max-messages 1 --timeout-ms 5000

# Verify Neo4j data
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA "MATCH (n:Resource {client_id: 'af-4'}) RETURN count(n);"

# Check client cluster
kubectl get pods -n kgroot
```

---

## Getting Help

1. **Check logs first**: Most issues are explained in logs
2. **Run health check script**: See MONITORING-GUIDE.md
3. **Search this playbook**: Use Ctrl+F to find similar issues
4. **Check Neo4j query guide**: See NEO4J-RCA-QUERIES.md for debugging queries
5. **Community support**: GitHub Issues (when available)

---

**Document Version**: 1.0.0
**Last Updated**: 2025-10-23
**Platform Version**: v2.0.0
