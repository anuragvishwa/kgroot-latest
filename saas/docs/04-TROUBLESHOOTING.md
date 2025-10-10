# Troubleshooting Guide

**Version**: 1.0.0
**Last Updated**: 2025-01-09

---

## Table of Contents

1. [Diagnostic Tools](#diagnostic-tools)
2. [Server Issues](#server-issues)
3. [Client Issues](#client-issues)
4. [RCA Quality Issues](#rca-quality-issues)
5. [Performance Issues](#performance-issues)
6. [Network & Connectivity](#network--connectivity)
7. [Data Issues](#data-issues)
8. [Storage Issues](#storage-issues)
9. [Security Issues](#security-issues)
10. [Emergency Procedures](#emergency-procedures)

---

## Diagnostic Tools

### Essential Commands

```bash
# Quick health check
alias kg-health='kubectl get pods -n kg-rca-server && kubectl top nodes'

# View all logs
alias kg-logs='kubectl logs -n kg-rca-server --all-containers=true --tail=100'

# Describe problematic pod
alias kg-describe='kubectl describe pod -n kg-rca-server'

# Get events sorted by time
alias kg-events='kubectl get events -n kg-rca-server --sort-by=.lastTimestamp'

# Check resource usage
alias kg-top='kubectl top pods -n kg-rca-server --containers'
```

### Log Collection Script

```bash
#!/bin/bash
# collect-logs.sh - Collect diagnostic information

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="kg-diagnostics-$TIMESTAMP"
mkdir -p $OUTPUT_DIR

echo "Collecting diagnostics to $OUTPUT_DIR..."

# 1. Pod status
kubectl get pods -n kg-rca-server -o wide > $OUTPUT_DIR/pods.txt

# 2. Events
kubectl get events -n kg-rca-server --sort-by=.lastTimestamp > $OUTPUT_DIR/events.txt

# 3. Logs from all pods
for pod in $(kubectl get pods -n kg-rca-server -o name); do
  pod_name=$(basename $pod)
  echo "Collecting logs from $pod_name..."
  kubectl logs -n kg-rca-server $pod --tail=1000 > $OUTPUT_DIR/logs-$pod_name.txt 2>&1

  # Get previous logs if pod restarted
  kubectl logs -n kg-rca-server $pod --previous --tail=1000 > $OUTPUT_DIR/logs-$pod_name-previous.txt 2>&1 || true
done

# 4. Describe problematic pods
for pod in $(kubectl get pods -n kg-rca-server --field-selector=status.phase!=Running -o name); do
  pod_name=$(basename $pod)
  kubectl describe -n kg-rca-server $pod > $OUTPUT_DIR/describe-$pod_name.txt
done

# 5. Resource usage
kubectl top nodes > $OUTPUT_DIR/nodes-resources.txt
kubectl top pods -n kg-rca-server --containers > $OUTPUT_DIR/pods-resources.txt

# 6. Storage
kubectl get pvc -n kg-rca-server > $OUTPUT_DIR/storage.txt

# 7. Services and endpoints
kubectl get svc,ep -n kg-rca-server > $OUTPUT_DIR/services.txt

# 8. ConfigMaps and Secrets (names only)
kubectl get cm,secret -n kg-rca-server > $OUTPUT_DIR/config.txt

# 9. Neo4j cluster status
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  "CALL dbms.cluster.overview();" > $OUTPUT_DIR/neo4j-cluster.txt 2>&1 || true

# 10. Kafka broker status
kubectl exec -n kg-rca-server kafka-0 -- kafka-broker-api-versions.sh \
  --bootstrap-server kafka:9092 > $OUTPUT_DIR/kafka-brokers.txt 2>&1 || true

# 11. Consumer lag
kubectl exec -n kg-rca-server kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group kg-builder > $OUTPUT_DIR/consumer-lag.txt 2>&1 || true

# 12. Prometheus metrics snapshot
curl -s http://prometheus.kg-rca-server.svc.cluster.local:9090/api/v1/query?query=up > $OUTPUT_DIR/prometheus-up.txt

# Create tarball
tar czf kg-diagnostics-$TIMESTAMP.tar.gz $OUTPUT_DIR/
echo "Diagnostics collected: kg-diagnostics-$TIMESTAMP.tar.gz"
```

---

## Server Issues

### Issue: Pods Not Starting

**Symptoms**:
- Pods stuck in `Pending` state
- `kubectl get pods` shows `0/1 Running`

**Diagnosis**:
```bash
# Check pod status
kubectl describe pod <pod-name> -n kg-rca-server

# Common error messages:
# - "Insufficient cpu" or "Insufficient memory"
# - "No nodes available"
# - "PVC not bound"
# - "ImagePullBackOff"
```

**Solutions**:

**1. Insufficient Resources**:
```bash
# Check node capacity
kubectl describe nodes | grep -A 5 "Allocated resources"

# Solution: Add more nodes or reduce resource requests
# Scale up node pool (cloud-specific):
# AWS EKS:
eksctl scale nodegroup --cluster=kg-rca-server --name=standard-workers --nodes=10

# GKE:
gcloud container clusters resize kg-rca-server --num-nodes=10

# Temporary: Reduce resource requests
kubectl set resources deployment <deployment-name> -n kg-rca-server \
  --requests=cpu=500m,memory=1Gi
```

**2. PVC Not Bound**:
```bash
# Check PVC status
kubectl get pvc -n kg-rca-server

# If PVC is Pending, check storage class
kubectl get storageclass

# Solution: Create storage class or fix provisioner
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/aws-ebs
parameters:
  type: gp3
reclaimPolicy: Retain
EOF
```

**3. ImagePullBackOff**:
```bash
# Check image name and tag
kubectl get pod <pod-name> -n kg-rca-server -o yaml | grep image:

# Solution: Verify image exists or fix registry credentials
kubectl create secret docker-registry regcred \
  --docker-server=<registry> \
  --docker-username=<username> \
  --docker-password=<password> \
  -n kg-rca-server

# Update deployment to use secret
kubectl patch deployment <deployment-name> -n kg-rca-server -p \
  '{"spec":{"template":{"spec":{"imagePullSecrets":[{"name":"regcred"}]}}}}'
```

---

### Issue: Neo4j Cluster Not Forming

**Symptoms**:
- Neo4j pods restart frequently
- No leader elected
- "Unable to join cluster" errors in logs

**Diagnosis**:
```bash
# Check Neo4j logs
kubectl logs -n kg-rca-server neo4j-0 --tail=100

# Check cluster status
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  "CALL dbms.cluster.overview();" 2>&1

# Common error messages:
# - "Connection refused"
# - "Clock skew detected"
# - "Unable to connect to cluster member"
```

**Solutions**:

**1. Network Connectivity Issues**:
```bash
# Test pod-to-pod connectivity
kubectl exec -n kg-rca-server neo4j-0 -- nc -zv neo4j-1.neo4j.kg-rca-server.svc.cluster.local 7687

# Solution: Check NetworkPolicy
kubectl get networkpolicy -n kg-rca-server

# If blocking, temporarily disable for testing
kubectl delete networkpolicy --all -n kg-rca-server
```

**2. Clock Skew**:
```bash
# Check time on all nodes
for node in $(kubectl get nodes -o name); do
  echo "$node: $(kubectl debug $node -it --image=busybox -- date)"
done

# Solution: Enable NTP on all nodes (cloud-specific)
# AWS: NTP is usually enabled by default
# GKE: Managed automatically
```

**3. Split-Brain Scenario**:
```bash
# Multiple leaders detected
# Solution: Force cluster reset

# 1. Stop all Neo4j pods
kubectl scale statefulset neo4j -n kg-rca-server --replicas=0

# 2. Delete cluster state
kubectl exec -n kg-rca-server neo4j-0 -- rm -rf /data/cluster-state

# 3. Start pods one by one
kubectl scale statefulset neo4j -n kg-rca-server --replicas=1
# Wait for neo4j-0 to be ready
kubectl wait --for=condition=ready pod neo4j-0 -n kg-rca-server --timeout=300s

kubectl scale statefulset neo4j -n kg-rca-server --replicas=2
# Wait for neo4j-1 to join
kubectl wait --for=condition=ready pod neo4j-1 -n kg-rca-server --timeout=300s

kubectl scale statefulset neo4j -n kg-rca-server --replicas=3
```

---

### Issue: Kafka Brokers Down

**Symptoms**:
- Kafka pods not ready
- Producers/consumers unable to connect
- Under-replicated partitions

**Diagnosis**:
```bash
# Check broker status
kubectl get pods -n kg-rca-server -l app=kafka

# Check broker logs
kubectl logs -n kg-rca-server kafka-0 --tail=100

# Check Zookeeper connectivity
kubectl exec -n kg-rca-server kafka-0 -- zookeeper-shell.sh zookeeper:2181 ls /brokers/ids

# Common error messages:
# - "Zookeeper session expired"
# - "Unable to bind port 9092"
# - "Out of memory"
```

**Solutions**:

**1. Zookeeper Issues**:
```bash
# Check Zookeeper ensemble
kubectl exec -n kg-rca-server zookeeper-0 -- zkServer.sh status

# Expected output: Mode: leader (or follower)

# If Zookeeper is down, restart ensemble
kubectl rollout restart statefulset zookeeper -n kg-rca-server

# Wait for Zookeeper to be healthy
kubectl wait --for=condition=ready pod -l app=zookeeper -n kg-rca-server --timeout=300s

# Then restart Kafka
kubectl rollout restart statefulset kafka -n kg-rca-server
```

**2. Under-Replicated Partitions**:
```bash
# List under-replicated partitions
kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --under-replicated-partitions

# Solution: Reassign partitions
# 1. Generate reassignment JSON
kubectl exec -n kg-rca-server kafka-0 -- kafka-reassign-partitions.sh \
  --bootstrap-server kafka:9092 \
  --topics-to-move-json-file topics.json \
  --broker-list "0,1,2,3,4" \
  --generate

# 2. Execute reassignment
kubectl exec -n kg-rca-server kafka-0 -- kafka-reassign-partitions.sh \
  --bootstrap-server kafka:9092 \
  --reassignment-json-file reassignment.json \
  --execute

# 3. Verify
kubectl exec -n kg-rca-server kafka-0 -- kafka-reassign-partitions.sh \
  --bootstrap-server kafka:9092 \
  --reassignment-json-file reassignment.json \
  --verify
```

**3. Disk Full**:
```bash
# Check disk usage
kubectl exec -n kg-rca-server kafka-0 -- df -h /kafka

# If disk is full, delete old log segments
kubectl exec -n kg-rca-server kafka-0 -- kafka-log-dirs.sh \
  --bootstrap-server kafka:9092 \
  --describe

# Or increase retention (reduce data)
kubectl exec -n kg-rca-server kafka-0 -- kafka-configs.sh \
  --bootstrap-server kafka:9092 \
  --alter \
  --entity-type topics \
  --entity-name <topic-name> \
  --add-config retention.hours=24

# Or expand PVC
kubectl patch pvc kafka-data-kafka-0 -n kg-rca-server \
  -p '{"spec":{"resources":{"requests":{"storage":"2Ti"}}}}'
```

---

### Issue: Graph Builder Not Processing Messages

**Symptoms**:
- High Kafka consumer lag
- No new data in Neo4j
- Graph Builder pods healthy but idle

**Diagnosis**:
```bash
# Check Graph Builder logs
kubectl logs -n kg-rca-server deployment/graph-builder --tail=100

# Check consumer group lag
kubectl exec -n kg-rca-server kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group kg-builder

# Check Neo4j connectivity
kubectl exec -n kg-rca-server deployment/graph-builder -- \
  nc -zv neo4j.kg-rca-server.svc.cluster.local 7687

# Common issues:
# - Neo4j connection timeout
# - Message parsing errors
# - Database not found
```

**Solutions**:

**1. Neo4j Connection Issues**:
```bash
# Verify Neo4j is accessible
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  "RETURN 1;"

# Check Graph Builder Neo4j URI
kubectl exec -n kg-rca-server deployment/graph-builder -- env | grep NEO4J_URI

# Solution: Update environment variable
kubectl set env deployment/graph-builder -n kg-rca-server \
  NEO4J_URI="neo4j://neo4j.kg-rca-server.svc.cluster.local:7687"

# Restart pods
kubectl rollout restart deployment graph-builder -n kg-rca-server
```

**2. Message Parsing Errors**:
```bash
# Check logs for parsing errors
kubectl logs -n kg-rca-server deployment/graph-builder | grep -i error

# Example error: "Failed to parse JSON"
# Solution: Check message format in Kafka

# Consume a message
kubectl exec -n kg-rca-server kafka-0 -- kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic client-acme-abc123.events.normalized \
  --max-messages 1

# Validate JSON format
```

**3. Performance Bottleneck**:
```bash
# Check resource usage
kubectl top pods -n kg-rca-server -l app=graph-builder

# If CPU/memory is maxed out, scale up
kubectl scale deployment graph-builder -n kg-rca-server --replicas=20

# Or increase resources
kubectl set resources deployment graph-builder -n kg-rca-server \
  --requests=cpu=4000m,memory=8Gi \
  --limits=cpu=8000m,memory=16Gi
```

---

### Issue: API Not Responding

**Symptoms**:
- API requests timeout
- 502 Bad Gateway errors
- Ingress shows no backends

**Diagnosis**:
```bash
# Check API pods
kubectl get pods -n kg-rca-server -l app=kg-api

# Check API logs
kubectl logs -n kg-rca-server deployment/kg-api --tail=100

# Check service endpoints
kubectl get endpoints kg-api -n kg-rca-server

# Test internal connectivity
kubectl run test-pod --image=curlimages/curl --rm -it --restart=Never -- \
  curl http://kg-api.kg-rca-server.svc.cluster.local:8080/healthz
```

**Solutions**:

**1. No Healthy Backends**:
```bash
# Check pod readiness
kubectl describe pods -n kg-rca-server -l app=kg-api | grep -A 5 "Readiness"

# If failing readiness checks, check logs
kubectl logs -n kg-rca-server deployment/kg-api

# Common causes:
# - Neo4j not reachable
# - PostgreSQL not reachable

# Test connections from API pod
kubectl exec -n kg-rca-server deployment/kg-api -- \
  nc -zv neo4j.kg-rca-server.svc.cluster.local 7687

kubectl exec -n kg-rca-server deployment/kg-api -- \
  nc -zv postgresql.kg-rca-server.svc.cluster.local 5432
```

**2. Ingress Misconfiguration**:
```bash
# Check ingress
kubectl describe ingress kg-api -n kg-rca-server

# Common issues:
# - Wrong service name
# - Wrong service port
# - TLS certificate not ready

# Check certificate
kubectl describe certificate kg-api-tls -n kg-rca-server

# If certificate not ready, check cert-manager logs
kubectl logs -n cert-manager deployment/cert-manager
```

**3. Rate Limiting**:
```bash
# If getting 429 responses, rate limit is triggered
# Check rate limit annotations
kubectl get ingress kg-api -n kg-rca-server -o yaml | grep -A 3 annotations

# Temporarily disable rate limiting
kubectl annotate ingress kg-api -n kg-rca-server \
  nginx.ingress.kubernetes.io/rate-limit- \
  nginx.ingress.kubernetes.io/limit-rps-

# Or increase limits
kubectl annotate ingress kg-api -n kg-rca-server \
  nginx.ingress.kubernetes.io/rate-limit="1000" --overwrite
```

---

## Client Issues

### Issue: Agent Pods Not Starting

**Symptoms**:
- State Watcher, Vector, or Event Exporter pods not running
- Pods in `CrashLoopBackOff`

**Diagnosis**:
```bash
# Check pod status (on client cluster)
kubectl get pods -n kg-rca

# Check logs
kubectl logs -n kg-rca deployment/kg-rca-state-watcher --tail=100

# Common errors:
# - "Failed to connect to Kafka"
# - "Authentication failed"
# - "Invalid API key"
```

**Solutions**:

**1. Kafka Connection Issues**:
```bash
# Test Kafka connectivity from client cluster
kubectl run test-kafka -n kg-rca --image=confluentinc/cp-kafka:latest --rm -it --restart=Never -- \
  bash -c "echo test | kafka-console-producer.sh \
    --bootstrap-server kafka.kg-rca.yourcompany.com:9092 \
    --topic test-topic \
    --producer-property security.protocol=SASL_PLAINTEXT \
    --producer-property sasl.mechanism=SCRAM-SHA-512 \
    --producer-property sasl.jaas.config='org.apache.kafka.common.security.scram.ScramLoginModule required username=\"client-acme-abc123\" password=\"YOUR_PASSWORD\";'"

# If connection fails, check:
# - Firewall rules
# - Network policies
# - Kafka LoadBalancer IP/hostname
```

**2. Authentication Failures**:
```bash
# Verify credentials in secret
kubectl get secret kg-rca-credentials -n kg-rca -o yaml

# Expected fields:
# - kafka-username
# - kafka-password
# - api-key

# If credentials are wrong, update secret
kubectl create secret generic kg-rca-credentials -n kg-rca \
  --from-literal=kafka-username="client-acme-abc123" \
  --from-literal=kafka-password="CORRECT_PASSWORD" \
  --from-literal=api-key="CORRECT_API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart pods to pick up new credentials
kubectl rollout restart deployment -n kg-rca
```

**3. RBAC Permissions**:
```bash
# Check if service account has permissions
kubectl auth can-i list pods --as=system:serviceaccount:kg-rca:kg-rca-agent -n default

# If permission denied, create RBAC
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kg-rca-agent
rules:
- apiGroups: [""]
  resources: ["pods", "services", "endpoints", "nodes", "events"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kg-rca-agent
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: kg-rca-agent
subjects:
- kind: ServiceAccount
  name: kg-rca-agent
  namespace: kg-rca
EOF
```

---

### Issue: No Data Flowing to Server

**Symptoms**:
- Agents running but no data in server Neo4j
- Kafka topics empty
- Consumer lag is zero

**Diagnosis**:
```bash
# Check if messages are being produced (server-side)
kubectl exec -n kg-rca-server kafka-0 -- kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic client-acme-abc123.events.normalized \
  --from-beginning \
  --max-messages 5

# If no messages, check client logs
kubectl logs -n kg-rca deployment/kg-rca-state-watcher --tail=100 | grep -i "sent\|error"

# Check client metrics
kubectl exec -n kg-rca deployment/kg-rca-state-watcher -- \
  curl http://localhost:9090/metrics | grep kg_client_events_sent_total
```

**Solutions**:

**1. No Events in Cluster**:
```bash
# Create test event to trigger data flow
kubectl run test-pod --image=nginx --restart=Never -n default

# Wait 30 seconds, then check Kafka
kubectl exec -n kg-rca-server kafka-0 -- kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic client-acme-abc123.events.normalized \
  --from-beginning \
  --max-messages 1

# If still no messages, check State Watcher is watching correct namespaces
kubectl get deployment kg-rca-state-watcher -n kg-rca -o yaml | grep -A 5 "WATCH_NAMESPACES"
```

**2. Kafka ACL Issues**:
```bash
# Verify client has write permissions (server-side)
kubectl exec -n kg-rca-server kafka-0 -- kafka-acls.sh \
  --bootstrap-server kafka:9092 \
  --list \
  --principal User:client-acme-abc123

# If missing, add ACLs
kubectl exec -n kg-rca-server kafka-0 -- kafka-acls.sh \
  --bootstrap-server kafka:9092 \
  --add \
  --allow-principal User:client-acme-abc123 \
  --operation Write \
  --operation Describe \
  --topic "client-acme-abc123.*" \
  --resource-pattern-type prefixed
```

---

## RCA Quality Issues

### Issue: No RCA Links Being Created

**Symptoms**:
- Incidents exist in Neo4j
- No `POTENTIAL_CAUSE` edges
- RCA queries return empty results

**Diagnosis**:
```bash
# Check if incidents are being created
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (inc:Incident) RETURN count(inc), max(inc.timestamp);"

# Check Graph Builder logs for RCA computation
kubectl logs -n kg-rca-server deployment/graph-builder | grep -i "rca\|potential_cause"

# Check RCA configuration
kubectl exec -n kg-rca-server deployment/graph-builder -- env | grep RCA
```

**Solutions**:

**1. RCA Window Too Short**:
```bash
# Check if prior events exist in time window
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (inc:Incident)
   WITH inc ORDER BY inc.timestamp DESC LIMIT 1
   MATCH (prior:Episodic)
   WHERE prior.timestamp >= inc.timestamp - 900
     AND prior.timestamp < inc.timestamp
   RETURN count(prior), min(prior.timestamp), max(prior.timestamp);"

# If count is 0, increase RCA window
kubectl set env deployment/graph-builder -n kg-rca-server \
  RCA_WINDOW_MIN=30

# Restart to apply
kubectl rollout restart deployment graph-builder -n kg-rca-server
```

**2. Incidents Not Being Detected**:
```bash
# Check episodic severity distribution
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (e:Episodic) RETURN e.severity, count(*) ORDER BY count(*) DESC;"

# If no "error" or "critical" severity, incidents won't be created
# Check severity escalation is enabled
kubectl exec -n kg-rca-server deployment/graph-builder -- env | grep SEVERITY_ESCALATION

# Enable severity escalation
kubectl set env deployment/graph-builder -n kg-rca-server \
  SEVERITY_ESCALATION_ENABLED=true \
  SEVERITY_ESCALATION_THRESHOLD=3 \
  SEVERITY_ESCALATION_WINDOW_MIN=5
```

**3. Graph Builder Not Running RCA Algorithm**:
```bash
# Check Graph Builder is consuming incident-related messages
kubectl logs -n kg-rca-server deployment/graph-builder | grep -i "incident"

# Manually trigger RCA computation for testing
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (inc:Incident)
   WITH inc ORDER BY inc.timestamp DESC LIMIT 1
   MATCH (prior:Episodic)
   WHERE prior.timestamp >= inc.timestamp - 900
     AND prior.timestamp < inc.timestamp
   CREATE (prior)-[:POTENTIAL_CAUSE {
     confidence: 0.8,
     created_at: datetime()
   }]->(inc)
   RETURN count(*);"

# If manual creation works, issue is with Graph Builder
# Check for errors in logs
kubectl logs -n kg-rca-server deployment/graph-builder --tail=500 | grep -i error
```

---

### Issue: Low RCA Accuracy

**Symptoms**:
- A@3 accuracy < 85%
- MAR (Mean Average Rank) > 3
- High number of low-confidence links

**Diagnosis**:
```bash
# Query RCA quality metrics
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH ()-[r:POTENTIAL_CAUSE]->()
   RETURN
     avg(r.confidence) as avg_confidence,
     min(r.confidence) as min_confidence,
     max(r.confidence) as max_confidence,
     count(CASE WHEN r.confidence IS NULL THEN 1 END) as null_count,
     count(*) as total_links;"

# Check confidence score distribution
curl -s "http://prometheus.kg-rca-server.svc.cluster.local:9090/api/v1/query?query=kg_rca_confidence_score" | jq
```

**Solutions**:

**1. Improve Temporal Scoring**:
```bash
# Reduce RCA window to focus on more recent events
kubectl set env deployment/graph-builder -n kg-rca-server \
  RCA_WINDOW_MIN=10

# Adjust temporal weight
kubectl set env deployment/graph-builder -n kg-rca-server \
  RCA_TEMPORAL_WEIGHT=0.5
```

**2. Enable Incident Clustering**:
```bash
# Group related incidents to reduce false positives
kubectl set env deployment/graph-builder -n kg-rca-server \
  INCIDENT_CLUSTERING_ENABLED=true \
  INCIDENT_CLUSTERING_WINDOW_MIN=5
```

**3. Tune Confidence Thresholds**:
```bash
# Only create links above certain confidence threshold
kubectl set env deployment/graph-builder -n kg-rca-server \
  RCA_MIN_CONFIDENCE=0.3 \
  RCA_MAX_CAUSES=5

# This reduces low-quality links
```

---

## Performance Issues

### Issue: High Latency

**Symptoms**:
- API responses slow (P95 > 200ms)
- Message processing slow (P95 > 500ms)
- Graph queries timeout

**Diagnosis**:
```bash
# Check Prometheus for latency metrics
curl -s "http://prometheus.kg-rca-server.svc.cluster.local:9090/api/v1/query?query=histogram_quantile(0.95,kg_api_request_duration_seconds_bucket)" | jq

# Check resource utilization
kubectl top pods -n kg-rca-server

# Check Neo4j query performance
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  "CALL dbms.listQueries() YIELD query, elapsedTimeMillis
   WHERE elapsedTimeMillis > 1000
   RETURN query, elapsedTimeMillis
   ORDER BY elapsedTimeMillis DESC
   LIMIT 10;"
```

**Solutions**:

**1. Scale Up Components**:
```bash
# Scale KG API
kubectl scale deployment kg-api -n kg-rca-server --replicas=30

# Scale Graph Builder
kubectl scale deployment graph-builder -n kg-rca-server --replicas=20

# Increase Neo4j heap
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  "CALL dbms.setConfigValue('server.memory.heap.max_size', '128G');"
```

**2. Add Indexes**:
```bash
# Check missing indexes
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "SHOW INDEXES;"

# Add common query indexes
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "CREATE INDEX episodic_timestamp_severity IF NOT EXISTS
   FOR (e:Episodic) ON (e.timestamp, e.severity);

   CREATE INDEX resource_namespace_kind IF NOT EXISTS
   FOR (r:Resource) ON (r.namespace, r.kind);

   CREATE INDEX incident_timestamp IF NOT EXISTS
   FOR (i:Incident) ON (i.timestamp);"
```

**3. Optimize Queries**:
```bash
# Profile slow query
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "PROFILE
   MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
   WHERE r.namespace = 'production'
   RETURN e, r
   LIMIT 100;"

# Look for:
# - AllNodesScan (bad, needs index)
# - NodeByLabelScan (good with filter)
# - NodeIndexSeek (best)
```

---

### Issue: High Memory Usage

**Symptoms**:
- Pods being OOMKilled
- Memory usage consistently at limit
- Node memory pressure

**Diagnosis**:
```bash
# Check pod memory usage
kubectl top pods -n kg-rca-server --containers | sort -k4 -n -r | head -20

# Check which pods are OOMKilled
kubectl get events -n kg-rca-server | grep OOMKilled

# Check Neo4j heap usage
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  "CALL dbms.queryJmx('java.lang:type=Memory') YIELD attributes
   RETURN attributes.HeapMemoryUsage.value.used, attributes.HeapMemoryUsage.value.max;"
```

**Solutions**:

**1. Increase Memory Limits**:
```bash
# Increase Neo4j memory
kubectl set resources statefulset neo4j -n kg-rca-server \
  --limits=memory=128Gi \
  --requests=memory=64Gi

# Update Neo4j heap config
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  "CALL dbms.setConfigValue('server.memory.heap.max_size', '64G');
   CALL dbms.setConfigValue('server.memory.pagecache.size', '32G');"

# Restart pods
kubectl rollout restart statefulset neo4j -n kg-rca-server
```

**2. Optimize Kafka Memory**:
```bash
# Adjust Kafka heap
kubectl set env statefulset kafka -n kg-rca-server \
  KAFKA_HEAP_OPTS="-Xmx16G -Xms8G"

# Reduce buffer sizes if needed
kubectl set env statefulset kafka -n kg-rca-server \
  KAFKA_SOCKET_SEND_BUFFER_BYTES=102400 \
  KAFKA_SOCKET_RECEIVE_BUFFER_BYTES=102400
```

**3. Enable JVM Memory Tuning**:
```bash
# Enable G1GC for better memory management
kubectl set env deployment graph-builder -n kg-rca-server \
  JAVA_OPTS="-XX:+UseG1GC -XX:MaxGCPauseMillis=200 -Xmx4G"

kubectl set env deployment kg-api -n kg-rca-server \
  JAVA_OPTS="-XX:+UseG1GC -XX:MaxGCPauseMillis=100 -Xmx2G"
```

---

## Network & Connectivity

### Issue: Cannot Reach API from External

**Symptoms**:
- Curl to API domain fails
- DNS resolution works but connection refused
- 502 Bad Gateway

**Diagnosis**:
```bash
# Test DNS resolution
dig api.kg-rca.yourcompany.com +short

# Test connectivity
curl -v https://api.kg-rca.yourcompany.com/healthz

# Check from inside cluster
kubectl run test-pod --image=curlimages/curl --rm -it --restart=Never -- \
  curl -v http://kg-api.kg-rca-server.svc.cluster.local:8080/healthz

# Check ingress
kubectl get ingress kg-api -n kg-rca-server -o yaml
```

**Solutions**:

**1. LoadBalancer IP Not Assigned**:
```bash
# Check LoadBalancer service
kubectl get svc -n ingress-nginx nginx-ingress-controller

# If EXTERNAL-IP is <pending>, cloud provider issue
# Check cloud provider documentation

# Temporary workaround: Use NodePort
kubectl patch svc nginx-ingress-controller -n ingress-nginx -p \
  '{"spec":{"type":"NodePort"}}'

# Then access via node IP:nodePort
```

**2. Firewall Rules**:
```bash
# Check security groups/firewall rules allow port 443

# AWS:
aws ec2 describe-security-groups --group-ids <sg-id>

# GCP:
gcloud compute firewall-rules list --filter="name:kg-rca"

# Add firewall rule if missing (GCP example):
gcloud compute firewall-rules create allow-https \
  --allow tcp:443 \
  --source-ranges 0.0.0.0/0 \
  --target-tags kg-rca-server
```

**3. Certificate Issues**:
```bash
# Check certificate
kubectl describe certificate kg-api-tls -n kg-rca-server

# If not ready, check cert-manager
kubectl logs -n cert-manager deployment/cert-manager --tail=100

# Manual certificate request
kubectl delete certificate kg-api-tls -n kg-rca-server
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: kg-api-tls
  namespace: kg-rca-server
spec:
  secretName: kg-api-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
    - api.kg-rca.yourcompany.com
EOF
```

---

## Data Issues

### Issue: Missing Data in Neo4j

**Symptoms**:
- Client reports missing resources
- Graph has gaps
- Recent events not appearing

**Diagnosis**:
```bash
# Check data freshness
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (e:Episodic)
   RETURN max(e.timestamp) as latest_timestamp,
          datetime({epochSeconds: max(e.timestamp)}) as latest_time;"

# Compare with Kafka latest offset
kubectl exec -n kg-rca-server kafka-0 -- kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list kafka:9092 \
  --topic client-acme-abc123.events.normalized

# Check consumer lag
kubectl exec -n kg-rca-server kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group kg-builder | grep client-acme-abc123
```

**Solutions**:

**1. High Consumer Lag**:
```bash
# If lag > 10000, scale up Graph Builder
kubectl scale deployment graph-builder -n kg-rca-server --replicas=30

# Monitor lag reduction
watch kubectl exec -n kg-rca-server kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group kg-builder
```

**2. Reprocess Messages**:
```bash
# Reset consumer group to earlier offset
kubectl exec -n kg-rca-server kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --group kg-builder \
  --topic client-acme-abc123.events.normalized \
  --reset-offsets \
  --to-datetime 2025-01-09T10:00:00.000 \
  --execute

# Graph Builder will reprocess messages from that timestamp
```

---

### Issue: Duplicate Data

**Symptoms**:
- Same resource appears multiple times
- Duplicate episodic events

**Diagnosis**:
```bash
# Check for duplicate resources
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (r:Resource)
   WITH r.name as name, r.namespace as ns, r.kind as kind, count(*) as cnt
   WHERE cnt > 1
   RETURN name, ns, kind, cnt
   ORDER BY cnt DESC
   LIMIT 20;"
```

**Solutions**:

**1. Merge Duplicates**:
```bash
# Create unique constraint (prevents future duplicates)
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "CREATE CONSTRAINT resource_unique IF NOT EXISTS
   FOR (r:Resource) REQUIRE (r.name, r.namespace, r.kind, r.cluster) IS UNIQUE;"

# Merge existing duplicates
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (r1:Resource), (r2:Resource)
   WHERE id(r1) < id(r2)
     AND r1.name = r2.name
     AND r1.namespace = r2.namespace
     AND r1.kind = r2.kind
   CALL apoc.refactor.mergeNodes([r1, r2], {properties: 'combine'})
   YIELD node
   RETURN count(node);"
```

---

## Storage Issues

### Issue: Disk Space Running Out

**Symptoms**:
- Pods evicted
- `No space left on device` errors
- PVC usage > 90%

**Diagnosis**:
```bash
# Check PVC usage
kubectl get pvc -n kg-rca-server

# Check disk usage inside pods
kubectl exec -n kg-rca-server neo4j-0 -- df -h /data
kubectl exec -n kg-rca-server kafka-0 -- df -h /kafka

# Check which database is using most space
kubectl exec -n kg-rca-server neo4j-0 -- du -sh /data/databases/*
```

**Solutions**:

**1. Expand PVC**:
```bash
# Increase PVC size (requires storage class to support expansion)
kubectl patch pvc neo4j-data-neo4j-0 -n kg-rca-server \
  -p '{"spec":{"resources":{"requests":{"storage":"2Ti"}}}}'

# Verify expansion
kubectl get pvc neo4j-data-neo4j-0 -n kg-rca-server -w
```

**2. Clean Up Old Data**:
```bash
# Reduce Kafka retention
kubectl exec -n kg-rca-server kafka-0 -- kafka-configs.sh \
  --bootstrap-server kafka:9092 \
  --alter \
  --entity-type topics \
  --entity-name client-oldco.events.normalized \
  --add-config retention.hours=24

# Delete old Neo4j databases (for offboarded clients)
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p $PASSWORD \
  "DROP DATABASE client_oldco_xyz_kg;"
```

**3. Enable Compression**:
```bash
# Enable Kafka compression
kubectl exec -n kg-rca-server kafka-0 -- kafka-configs.sh \
  --bootstrap-server kafka:9092 \
  --alter \
  --entity-type brokers \
  --entity-name 0 \
  --add-config compression.type=gzip
```

---

## Security Issues

### Issue: Unauthorized API Access

**Symptoms**:
- 401 Unauthorized errors
- API key not working
- Client accessing wrong data

**Diagnosis**:
```bash
# Verify API key in database
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -c \
  "SELECT client_id, key_prefix, created_at, last_used_at
   FROM api_keys
   WHERE key_prefix = 'kg_client-acme-abc1';"

# Check API logs for auth failures
kubectl logs -n kg-rca-server deployment/kg-api | grep -i "401\|unauthorized"
```

**Solutions**:

**1. Rotate API Key**:
```bash
# Generate new API key
./generate-api-key.sh client-acme-abc123

# Invalidate old key
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -c \
  "DELETE FROM api_keys
   WHERE client_id = 'client-acme-abc123'
     AND key_prefix = 'kg_client-acme-abc1';"
```

**2. Fix Data Isolation**:
```bash
# Verify client can only access their own data
# Test query with wrong client_id should return empty

# Check API code ensures client_id from API key matches requested data
```

---

## Emergency Procedures

### Complete System Restart

```bash
#!/bin/bash
# emergency-restart.sh - Use only in extreme cases

echo "WARNING: This will restart all components"
read -p "Are you sure? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
  echo "Aborted"
  exit 1
fi

# 1. Stop all consumers
kubectl scale deployment graph-builder -n kg-rca-server --replicas=0

# 2. Restart Zookeeper
kubectl rollout restart statefulset zookeeper -n kg-rca-server
kubectl wait --for=condition=ready pod -l app=zookeeper -n kg-rca-server --timeout=300s

# 3. Restart Kafka
kubectl rollout restart statefulset kafka -n kg-rca-server
kubectl wait --for=condition=ready pod -l app=kafka -n kg-rca-server --timeout=300s

# 4. Restart Neo4j
kubectl rollout restart statefulset neo4j -n kg-rca-server
kubectl wait --for=condition=ready pod -l app=neo4j -n kg-rca-server --timeout=300s

# 5. Restart PostgreSQL
kubectl rollout restart statefulset postgresql -n kg-rca-server
kubectl wait --for=condition=ready pod -l app=postgresql -n kg-rca-server --timeout=300s

# 6. Restart consumers
kubectl scale deployment graph-builder -n kg-rca-server --replicas=5

# 7. Restart API
kubectl rollout restart deployment kg-api -n kg-rca-server

echo "System restart complete"
```

### Disaster Recovery

```bash
# In case of complete data loss, restore from backup
# See OPERATIONS.md for full procedure

# 1. Restore Neo4j databases
kubectl exec -n kg-rca-server neo4j-0 -- neo4j-admin database load \
  client_acme_abc123_kg \
  --from-path=/backups/restore.dump

# 2. Restore PostgreSQL
kubectl exec -n kg-rca-server postgresql-0 -- pg_restore \
  -U billing -d billing --clean /tmp/restore.dump

# 3. Reset Kafka consumer offsets to latest
kubectl exec -n kg-rca-server kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --group kg-builder \
  --reset-offsets \
  --to-latest \
  --all-topics \
  --execute
```

---

## Getting Help

If issues persist after trying these solutions:

1. **Collect Diagnostics**:
   ```bash
   ./collect-logs.sh
   ```

2. **Check Documentation**:
   - [Architecture Guide](00-ARCHITECTURE.md)
   - [Server Deployment](01-SERVER-DEPLOYMENT.md)
   - [Operations Guide](03-OPERATIONS.md)

3. **Contact Support**:
   - Email: support@kg-rca.yourcompany.com
   - Slack: #kg-rca-support
   - Include diagnostics tarball

4. **Emergency Escalation**:
   - Phone: +1-XXX-XXX-XXXX (24/7)
   - For P0/P1 incidents only

---

**Document Version**: 1.0.0
**Maintained By**: Platform Engineering Team
**Last Review**: 2025-01-09
