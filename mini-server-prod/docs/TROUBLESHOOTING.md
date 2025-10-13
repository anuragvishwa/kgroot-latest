# Troubleshooting Guide

## Common Issues and Solutions

### Table of Contents
1. [Docker Issues](#docker-issues)
2. [Kafka Issues](#kafka-issues)
3. [Neo4j Issues](#neo4j-issues)
4. [Service Connection Issues](#service-connection-issues)
5. [Performance Issues](#performance-issues)
6. [SSL/TLS Issues](#ssltls-issues)
7. [Client Integration Issues](#client-integration-issues)

---

## Docker Issues

### Issue: Permission Denied

**Symptom:**
```
Got permission denied while trying to connect to the Docker daemon socket
```

**Solution:**
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in, or run:
newgrp docker

# Verify
docker ps
```

### Issue: Docker Compose Command Not Found

**Symptom:**
```
docker-compose: command not found
```

**Solution:**
```bash
# Use Docker Compose V2 (plugin)
docker compose version

# If not installed, run setup script again
sudo ./scripts/setup-ubuntu.sh
```

### Issue: Container Keeps Restarting

**Symptom:**
```bash
docker ps
# Shows container constantly restarting
```

**Solution:**
```bash
# Check logs
docker logs <container-name>

# Check for common issues:
# 1. Port already in use
sudo lsof -i :PORT_NUMBER
sudo kill -9 PID

# 2. Memory issues
free -h
docker stats

# 3. Configuration errors
docker inspect <container-name>
```

### Issue: Out of Disk Space

**Symptom:**
```
No space left on device
```

**Solution:**
```bash
# Check disk usage
df -h

# Clean Docker resources
docker system prune -a --volumes
# WARNING: This removes unused containers, networks, images, and volumes

# Or selectively:
docker container prune  # Remove stopped containers
docker image prune -a   # Remove unused images
docker volume prune     # Remove unused volumes
```

---

## Kafka Issues

### Issue: Kafka Not Starting

**Symptom:**
```
kafka container is unhealthy or keeps restarting
```

**Solution:**
```bash
# Check logs
docker logs kg-kafka

# Common causes:

# 1. Zookeeper not ready
docker logs kg-zookeeper
# Wait for: "binding to port 0.0.0.0/0.0.0.0:2181"

# 2. Port conflict
sudo lsof -i :9092
sudo lsof -i :9093

# 3. Memory issues
docker stats kg-kafka
# Adjust KAFKA_HEAP_OPTS in docker-compose.yml if needed

# 4. Volume permissions
docker volume inspect mini-server-prod_kafka-data
```

### Issue: Cannot Create Topics

**Symptom:**
```
Error while executing topic command: Topic already exists
# OR
Error while executing topic command: Connection to node -1 failed
```

**Solution:**
```bash
# Check Kafka is healthy
docker exec kg-kafka kafka-broker-api-versions.sh \
    --bootstrap-server localhost:9092

# List existing topics
docker exec kg-kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --list

# Delete and recreate topic (data loss!)
docker exec kg-kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --delete --topic TOPIC_NAME

# Then recreate
./scripts/create-topics.sh
```

### Issue: Clients Cannot Connect

**Symptom:**
```
Connection to node -1 could not be established
```

**Solution:**
```bash
# 1. Check advertised listeners
docker exec kg-kafka env | grep ADVERTISED

# 2. Verify port is open
sudo ufw status
sudo ufw allow 9092/tcp
sudo ufw allow 9093/tcp

# 3. Test from client machine
telnet YOUR_SERVER_IP 9093

# 4. Check firewall (cloud provider)
# AWS: Check Security Group
# DigitalOcean: Check Firewall rules

# 5. Verify hostname resolution
nslookup YOUR_HOSTNAME
```

### Issue: Messages Not Being Consumed

**Symptom:**
```
Consumer lag increasing, messages not processed
```

**Solution:**
```bash
# Check consumer groups
docker exec kg-kafka kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --list

# Check lag for specific group
docker exec kg-kafka kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --group CONSUMER_GROUP \
    --describe

# Check if consumers are running
docker ps | grep -E "enricher|builder"
docker logs kg-alerts-enricher
docker logs kg-graph-builder

# Reset consumer group (data loss!)
docker exec kg-kafka kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --group CONSUMER_GROUP \
    --reset-offsets --to-earliest --execute --all-topics
```

---

## Neo4j Issues

### Issue: Neo4j Not Starting

**Symptom:**
```
neo4j container unhealthy
```

**Solution:**
```bash
# Check logs
docker logs kg-neo4j

# Common causes:

# 1. Memory issues
docker stats kg-neo4j
# Reduce heap size in docker-compose.yml:
#   NEO4J_server_memory_heap_max__size: 2G

# 2. Database corruption
docker exec kg-neo4j neo4j-admin check-consistency

# 3. Port conflict
sudo lsof -i :7474
sudo lsof -i :7687

# 4. Volume permissions
docker volume inspect mini-server-prod_neo4j-data
```

### Issue: Cannot Connect to Neo4j

**Symptom:**
```
Unable to connect to neo4j://neo4j:7687
```

**Solution:**
```bash
# 1. Check if Neo4j is healthy
docker exec kg-neo4j neo4j status

# 2. Verify credentials
docker exec -it kg-neo4j cypher-shell -u neo4j -p YOUR_PASSWORD

# 3. Check from application
docker exec kg-api env | grep NEO4J
# Ensure NEO4J_PASS matches .env

# 4. Test connectivity from container
docker exec kg-graph-builder nc -zv neo4j 7687
```

### Issue: Slow Queries

**Symptom:**
```
Neo4j queries taking too long
```

**Solution:**
```bash
# 1. Check memory usage
docker stats kg-neo4j

# 2. Create indexes
docker exec -it kg-neo4j cypher-shell -u neo4j -p YOUR_PASSWORD
# In cypher-shell:
CREATE INDEX resource_id FOR (r:Resource) ON (r.id);
CREATE INDEX event_timestamp FOR (e:Event) ON (e.timestamp);

# 3. Analyze slow queries
# In cypher-shell:
CALL dbms.listQueries();

# 4. Check page cache
# In cypher-shell:
CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Page cache') YIELD attributes;

# 5. Increase memory in docker-compose.yml
```

### Issue: Database Full

**Symptom:**
```
No space left on device
```

**Solution:**
```bash
# Check database size
docker exec kg-neo4j du -sh /data

# Option 1: Clear old data
docker exec -it kg-neo4j cypher-shell -u neo4j -p YOUR_PASSWORD
# Delete old events:
MATCH (e:Event) WHERE e.timestamp < datetime() - duration('P30D') DELETE e;

# Option 2: Backup and restore
./scripts/backup.sh
docker compose down
docker volume rm mini-server-prod_neo4j-data
docker compose up -d

# Option 3: Increase disk size (cloud provider)
```

---

## Service Connection Issues

### Issue: Graph Builder Not Processing Events

**Symptom:**
```
Events in Kafka but not in Neo4j
```

**Solution:**
```bash
# 1. Check Graph Builder logs
docker logs kg-graph-builder -f

# 2. Verify Kafka connectivity
docker exec kg-graph-builder nc -zv kafka 9092

# 3. Verify Neo4j connectivity
docker exec kg-graph-builder nc -zv neo4j 7687

# 4. Check environment variables
docker exec kg-graph-builder env | grep -E "KAFKA|NEO4J"

# 5. Restart the service
docker compose restart graph-builder

# 6. Check for errors in consumer group
docker exec kg-kafka kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --group kg-builder \
    --describe
```

### Issue: KG API Returns 500 Error

**Symptom:**
```
curl http://localhost:8080/api/v1/rca/123 returns 500
```

**Solution:**
```bash
# 1. Check API logs
docker logs kg-api -f

# 2. Test Neo4j connection
docker exec kg-api nc -zv neo4j 7687

# 3. Verify data exists
docker exec -it kg-neo4j cypher-shell -u neo4j -p YOUR_PASSWORD
MATCH (n) RETURN count(n);

# 4. Check API configuration
docker exec kg-api env | grep NEO4J

# 5. Restart API
docker compose restart kg-api
```

### Issue: Alerts Not Being Enriched

**Symptom:**
```
Events in raw topic but not enriched
```

**Solution:**
```bash
# 1. Check enricher logs
docker logs kg-alerts-enricher -f

# 2. Verify input/output topics exist
docker exec kg-kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --list | grep -E "events.normalized|alerts.enriched"

# 3. Check environment variables
docker exec kg-alerts-enricher env | grep TOPIC

# 4. Send test message
echo '{"id":"test","timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","severity":"ERROR","message":"Test"}' | \
docker exec -i kg-kafka kafka-console-producer.sh \
    --bootstrap-server localhost:9092 \
    --topic events.normalized

# 5. Check if enricher consumed it
docker exec kg-kafka kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --group alerts-enricher \
    --describe
```

---

## Performance Issues

### Issue: High Memory Usage

**Symptom:**
```
docker stats shows high memory usage
```

**Solution:**
```bash
# 1. Check current usage
docker stats --no-stream

# 2. Reduce Neo4j heap
# Edit docker-compose.yml:
NEO4J_server_memory_heap_max__size: 2G  # Reduce

# 3. Reduce Kafka heap
KAFKA_HEAP_OPTS: "-Xmx1G -Xms512M"  # Reduce

# 4. Add swap space (temporary fix)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 5. Upgrade server instance type
```

### Issue: High CPU Usage

**Symptom:**
```
top shows 100% CPU usage
```

**Solution:**
```bash
# 1. Identify culprit
docker stats --no-stream

# 2. Check for infinite loops
docker logs kg-graph-builder --tail 100
docker logs kg-alerts-enricher --tail 100

# 3. Reduce concurrent processing
# Edit service code to reduce parallelism

# 4. Add resource limits in docker-compose.yml:
services:
  graph-builder:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

# 5. Upgrade server CPU
```

### Issue: Slow Kafka Throughput

**Symptom:**
```
Messages processed slowly
```

**Solution:**
```bash
# 1. Check Kafka performance
docker exec kg-kafka kafka-run-class.sh \
    kafka.tools.GetOffsetShell \
    --broker-list localhost:9092 \
    --time -1

# 2. Increase partitions
docker exec kg-kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --alter --topic events.normalized \
    --partitions 6

# 3. Adjust batch settings in producer configs

# 4. Use compression
# Already enabled: compression.type=gzip

# 5. Increase broker memory
# Edit KAFKA_HEAP_OPTS in docker-compose.yml
```

---

## SSL/TLS Issues

### Issue: SSL Certificate Invalid

**Symptom:**
```
SSL handshake failed
```

**Solution:**
```bash
# 1. Verify certificate
openssl x509 -in ssl/ca-cert -text -noout

# 2. Check SAN (Subject Alternative Name)
# Should include your hostname/IP

# 3. Regenerate certificates
rm -rf ssl/*.jks ssl/ca-*
./scripts/setup-ssl.sh

# 4. Verify hostname matches
grep KAFKA_ADVERTISED_HOST .env
```

### Issue: Clients Cannot Verify Certificate

**Symptom:**
```
certificate verify failed
```

**Solution:**
```bash
# 1. Ensure client has CA certificate
ls -l ssl/ca-cert

# 2. Copy to client
scp ssl/ca-cert client-machine:/path/to/ca-cert

# 3. Configure client to use CA cert
# In Helm values:
client:
  kafka:
    tls:
      caCert: |
        -----BEGIN CERTIFICATE-----
        ...
        -----END CERTIFICATE-----

# 4. Test manually
openssl s_client -connect YOUR_SERVER:9093 \
    -CAfile ssl/ca-cert
```

### Issue: Mixed Plaintext and SSL

**Symptom:**
```
Some clients can connect, others cannot
```

**Solution:**
```bash
# 1. Check listener configuration
docker exec kg-kafka env | grep LISTENERS

# Both should be available:
# PLAINTEXT://kafka:9092 (internal)
# SSL://YOUR_HOST:9093 (external)

# 2. Internal services use plaintext
docker exec kg-graph-builder env | grep KAFKA_BROKERS
# Should be: kafka:9092

# 3. External clients use SSL
# Should be: YOUR_HOST:9093

# 4. Restart Kafka if changed
docker compose -f docker-compose.yml -f docker-compose.ssl.yml restart kafka
```

---

## Client Integration Issues

### Issue: Client Pods Not Starting

**Symptom:**
```
kubectl get pods -n observability
# Shows CrashLoopBackOff
```

**Solution:**
```bash
# 1. Check pod logs
kubectl logs -n observability POD_NAME

# 2. Check Helm values
helm get values kg-rca-agent -n observability

# 3. Common issues:
# - Wrong broker address
# - Missing CA certificate
# - Wrong API key

# 4. Update values and upgrade
helm upgrade kg-rca-agent ./helm-chart \
    -f updated-values.yaml \
    -n observability
```

### Issue: Client Cannot Reach Kafka

**Symptom:**
```
Failed to connect to Kafka: Connection refused
```

**Solution:**
```bash
# 1. Test connectivity from cluster
kubectl run -it --rm debug --image=busybox --restart=Never -- sh
# In pod:
telnet YOUR_SERVER_IP 9093

# 2. Check firewall
sudo ufw status | grep 9093

# 3. Check cloud security group/firewall

# 4. Verify advertised host
docker exec kg-kafka env | grep ADVERTISED

# 5. Check DNS resolution
kubectl run -it --rm debug --image=busybox --restart=Never -- sh
# In pod:
nslookup YOUR_HOSTNAME
```

### Issue: Authentication Failed

**Symptom:**
```
Not authorized to access topics
```

**Solution:**
```bash
# 1. This setup doesn't use SASL
# Remove SASL config from client:
kafka:
  sasl:
    enabled: false  # or remove entirely

# 2. For SSL-only:
kafka:
  protocol: SSL
  tls:
    enabled: true
    caCert: <YOUR_CA_CERT>

# 3. No username/password needed
```

### Issue: No Data Appearing in Neo4j

**Symptom:**
```
Client sending data but nothing in graph
```

**Solution:**
```bash
# 1. Check Kafka UI for messages
open http://YOUR_SERVER_IP:7777

# 2. Verify topics have data
docker exec kg-kafka kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic events.normalized \
    --max-messages 1 \
    --from-beginning

# 3. Check Graph Builder logs
docker logs kg-graph-builder -f

# 4. Check Neo4j
docker exec -it kg-neo4j cypher-shell -u neo4j -p PASSWORD
MATCH (n) RETURN labels(n), count(n);

# 5. Verify topic names match
# Client should send to: raw.k8s.events, raw.k8s.logs, etc.
```

---

## Getting More Help

### Diagnostic Commands

```bash
# Full system status
./scripts/test-services.sh

# All logs
docker compose logs -f --tail=100

# System resources
htop
df -h
free -h

# Network connections
sudo netstat -tulpn | grep -E "9092|9093|7474|7687|8080"

# Docker info
docker info
docker compose config
```

### Collecting Debug Information

```bash
# Create debug bundle
mkdir debug-$(date +%Y%m%d)
cd debug-$(date +%Y%m%d)

# Collect logs
docker compose logs > docker-compose.log

# Collect configs
cp ../.env env.txt
cp ../docker-compose*.yml .

# System info
docker ps -a > containers.txt
docker stats --no-stream > stats.txt
df -h > disk.txt
free -h > memory.txt

# Tar it up
cd ..
tar czf debug-$(date +%Y%m%d).tar.gz debug-$(date +%Y%m%d)/
```

### Contact Support

If issues persist:

1. Create debug bundle (above)
2. Open GitHub issue with:
   - Problem description
   - Steps to reproduce
   - Expected vs actual behavior
   - Debug bundle
3. Email: support@lumniverse.com

---

**Most issues are resolved by:**
- Checking logs: `docker compose logs -f`
- Verifying configuration: `docker compose config`
- Restarting services: `docker compose restart`
- Running health checks: `./scripts/test-services.sh`
