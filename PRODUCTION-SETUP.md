# Production Server Setup Guide

## Current Configuration

**Server**: AWS EC2 (Elastic IP: 98.90.147.12)
**Domain**: kafka.lumniverse.com → 98.90.147.12
**Status**: ✓ Configured and Running

## 1. Port Strategy

### Ports to EXPOSE (AWS Security Group)

#### Port 9092 - Kafka (REQUIRED for clients)
```
Type: Custom TCP
Port: 9092
Source: 0.0.0.0/0 (or restrict to specific client IP ranges)
Description: Kafka broker - external client access
```

#### Port 22 - SSH (REQUIRED for admin)
```
Type: SSH
Port: 22
Source: Your-IP/32
Description: SSH access for server administration
```

### Ports to KEEP CLOSED (Use SSH Tunnel)

Access these via SSH tunnel only - DO NOT expose to internet:

```bash
# From your local machine:
ssh -L 7474:localhost:7474 \
    -L 7687:localhost:7687 \
    -L 8080:localhost:8080 \
    -L 7777:localhost:7777 \
    -L 3000:localhost:3000 \
    mini-server
```

Then access:
- **Neo4j Browser**: http://localhost:7474 (graph visualization)
- **Neo4j Bolt**: bolt://localhost:7687 (direct queries)
- **KG API**: http://localhost:8080 (REST API for queries)
- **Kafka UI**: http://localhost:7777 (Kafka monitoring)
- **Grafana**: http://localhost:3000 (metrics dashboard)

## 2. Kafka Configuration

### Current Setup
```yaml
Advertised Listener: kafka.lumniverse.com:9092
Internal Services: kafka:9092 (Docker network)
External Clients: kafka.lumniverse.com:9092
```

### Client Connection String
```bash
--set server.kafka.brokers="kafka.lumniverse.com:9092"
```

## 3. DNS Configuration (Namecheap)

Your current DNS is correctly configured:

```
Type: A Record
Host: kafka
Value: 98.90.147.12
Result: kafka.lumniverse.com → 98.90.147.12
TTL: Automatic
```

**No changes needed!**

## 4. SSL/TLS Certificate

### Current Setup: Plaintext (No SSL)

This is **fine for initial setup and testing**. You can add SSL later if needed.

### When to Add SSL:
- Exposing to public internet
- Client compliance requirements
- Handling sensitive data

### How to Add SSL (Future):
```bash
# 1. Install certbot
sudo yum install certbot -y

# 2. Temporarily open port 80 in security group

# 3. Generate certificate
sudo certbot certonly --standalone -d kafka.lumniverse.com

# 4. Configure Kafka SSL (requires additional Kafka config)
# - Update KAFKA_ADVERTISED_LISTENERS to use SSL://
# - Add SSL_KEYSTORE_LOCATION and SSL_KEYSTORE_PASSWORD
# - Provide SSL certificates to clients
```

**For now, skip this step.**

## 5. Client Deployment (Helm Chart)

### Installation Command
```bash
helm install my-client-name saas/client/helm-chart/kg-rca-agent \
  --set client.id=unique-client-id-123 \
  --set client.apiKey=secure-api-key-456 \
  --set server.kafka.brokers="kafka.lumniverse.com:9092"
```

### Test Connection from Client Cluster
```bash
# 1. Test DNS resolution
nslookup kafka.lumniverse.com
# Expected: 98.90.147.12

# 2. Test port connectivity
telnet kafka.lumniverse.com 9092
# OR
nc -zv kafka.lumniverse.com 9092
# Expected: Connection successful

# 3. Deploy test client
helm install test-client saas/client/helm-chart/kg-rca-agent \
  --set client.id=test-client-123 \
  --set client.apiKey=test-api-key \
  --set server.kafka.brokers="kafka.lumniverse.com:9092"

# 4. Check client logs
kubectl logs -l app=kg-rca-agent --tail=50
```

## 6. Graph Visualization for Clients

You have 3 options for clients to view their knowledge graph:

### Option 1: SSH Tunnel Access (Most Secure)
**Best for**: Technical clients, your own access

```bash
# Give client SSH credentials
ssh -L 7474:localhost:7474 user@kafka.lumniverse.com

# Then browse: http://localhost:7474
# Neo4j credentials: neo4j / anuragvishwa
```

**Pros**: Most secure, no additional ports exposed
**Cons**: Requires SSH access, technical knowledge

### Option 2: Direct Neo4j Exposure (Less Secure)
**Best for**: Internal clients, trusted networks

```
Open port 7474 in AWS Security Group
Clients access: http://kafka.lumniverse.com:7474
```

**Pros**: Easy for clients
**Cons**: Exposes database UI to internet, requires Neo4j authentication

### Option 3: Custom Dashboard (Recommended for Production)
**Best for**: External clients, production SaaS

Build a web UI that:
1. Queries KG API (port 8080 - internal)
2. Displays graph with custom branding
3. Provides client-specific authentication
4. Deployed on separate domain (e.g., dashboard.lumniverse.com)

**Pros**: Professional, secure, branded experience
**Cons**: Requires development effort

**Recommendation**:
- Use Option 1 for your own access
- Use Option 3 for production clients
- Use Option 2 only for internal/testing

## 7. Monitoring Your Server

### SSH Tunnel for Monitoring
```bash
ssh -L 7777:localhost:7777 -L 3000:localhost:3000 mini-server
```

### Kafka UI (Port 7777)
**URL**: http://localhost:7777 (after SSH tunnel)

View:
- Topics and messages
- Consumer groups and lag
- Broker health
- Topic configurations

### Grafana (Port 3000)
**URL**: http://localhost:3000 (after SSH tunnel)
**Credentials**: admin / admin

View:
- System metrics
- Kafka metrics
- Neo4j performance
- Custom dashboards

### Docker Status
```bash
ssh mini-server "docker ps"
ssh mini-server "docker-compose -f docker-compose-fixed.yml ps"
ssh mini-server "docker stats --no-stream"
```

### Service Logs
```bash
# Kafka
ssh mini-server "docker logs kgroot-latest-kafka-1 --tail 50"

# Graph Builder
ssh mini-server "docker logs kgroot-latest-graph-builder-1 --tail 50"

# KG API
ssh mini-server "docker logs kgroot-latest-kg-api-1 --tail 50"

# Alerts Enricher
ssh mini-server "docker logs kgroot-latest-alerts-enricher-1 --tail 50"
```

## 8. AWS Security Group Summary

### Required Configuration

```
Inbound Rules:
┌────────────┬─────────┬──────────────────┬─────────────────────────────┐
│ Type       │ Port    │ Source           │ Description                 │
├────────────┼─────────┼──────────────────┼─────────────────────────────┤
│ SSH        │ 22      │ Your-IP/32       │ Admin access                │
│ Custom TCP │ 9092    │ 0.0.0.0/0        │ Kafka - client connections  │
└────────────┴─────────┴──────────────────┴─────────────────────────────┘

Outbound Rules:
┌────────────┬─────────┬──────────────────┬─────────────────────────────┐
│ Type       │ Port    │ Destination      │ Description                 │
├────────────┼─────────┼──────────────────┼─────────────────────────────┤
│ All        │ All     │ 0.0.0.0/0        │ Allow all outbound          │
└────────────┴─────────┴──────────────────┴─────────────────────────────┘
```

### Ports NOT to Expose
- 7474 (Neo4j Browser)
- 7687 (Neo4j Bolt)
- 8080 (KG API)
- 7777 (Kafka UI)
- 3000 (Grafana)
- 9090 (Graph Builder Metrics)
- 9091 (Prometheus)

**Access these via SSH tunnel only.**

## 9. Client Onboarding Checklist

When adding a new client:

- [ ] Generate unique client ID (e.g., `client-acme-prod-001`)
- [ ] Generate secure API key (store securely)
- [ ] Provide Helm installation command:
  ```bash
  helm install acme-rca-agent saas/client/helm-chart/kg-rca-agent \
    --set client.id=client-acme-prod-001 \
    --set client.apiKey=<secure-key> \
    --set server.kafka.brokers="kafka.lumniverse.com:9092"
  ```
- [ ] Verify client connectivity:
  ```bash
  kubectl logs -l app=kg-rca-agent --tail=100
  ```
- [ ] Check data flow on server:
  ```bash
  ssh mini-server "docker exec kgroot-latest-kafka-1 kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 --describe --group <client-id>"
  ```
- [ ] Provide graph access (choose option from section 6)
- [ ] Document client-specific configuration

## 10. Troubleshooting

### Client Cannot Connect to Kafka

**Check DNS resolution:**
```bash
nslookup kafka.lumniverse.com
# Should return: 98.90.147.12
```

**Check port connectivity:**
```bash
telnet kafka.lumniverse.com 9092
# OR
nc -zv kafka.lumniverse.com 9092
```

**Verify AWS Security Group:**
- Port 9092 must be open
- Source must include client IP range

**Check Kafka advertised listener:**
```bash
ssh mini-server "docker exec kgroot-latest-kafka-1 sh -c 'env | grep ADVERTISED'"
# Should show: KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka.lumniverse.com:9092
```

### Data Not Flowing

**Check Kafka topics have data:**
```bash
ssh mini-server "docker exec kgroot-latest-kafka-1 kafka-topics.sh \
  --bootstrap-server localhost:9092 --describe"
```

**Check consumer lag:**
```bash
ssh mini-server "docker exec kgroot-latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --all-groups"
```

**Check service logs:**
```bash
ssh mini-server "docker logs kgroot-latest-graph-builder-1 --tail 100"
```

### Neo4j Graph Not Updating

**Check Neo4j is running:**
```bash
ssh mini-server "docker ps | grep neo4j"
```

**Check graph-builder logs:**
```bash
ssh mini-server "docker logs kgroot-latest-graph-builder-1 --tail 50"
```

**Test Neo4j connection via SSH tunnel:**
```bash
ssh -L 7474:localhost:7474 mini-server
# Browse: http://localhost:7474
# Credentials: neo4j / anuragvishwa
```

**Run test query:**
```cypher
MATCH (n) RETURN count(n) as node_count
```

## 11. Backup and Maintenance

### Regular Backups

**Neo4j data:**
```bash
ssh mini-server "docker exec kgroot-latest-neo4j-1 neo4j-admin database dump neo4j --to-stdout > /home/ec2-user/backup/neo4j-$(date +%Y%m%d).dump"
```

**Kafka topics (optional):**
```bash
# Use Kafka MirrorMaker or Kafka Connect for replication
# Or snapshot topics using kafka-dump (custom tooling)
```

### Disk Space Monitoring
```bash
ssh mini-server "df -h"
ssh mini-server "docker system df"
```

### Log Rotation
```bash
# Configure Docker log rotation in /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

## 12. Scaling Considerations

### Current Limitations
- Single Kafka broker (no replication)
- Single Neo4j instance
- All services on one EC2 instance

### When to Scale
- **Multiple brokers**: When clients > 10 or message volume > 1M/day
- **Neo4j cluster**: When graph size > 10M nodes
- **Separate instances**: When CPU/memory > 80% sustained

### Future Architecture
```
├── Load Balancer (ALB)
├── Kafka Cluster (3+ brokers)
├── Neo4j Cluster (3+ instances)
├── Separate processing tier (graph-builder, alerts-enricher)
└── Monitoring cluster (Prometheus, Grafana)
```

## Summary

✓ **Kafka advertised listener**: kafka.lumniverse.com:9092
✓ **DNS configured**: kafka.lumniverse.com → 98.90.147.12
✓ **AWS Security Group**: Open port 9092, SSH tunnel for others
✓ **No SSL required**: Plaintext is fine for now
✓ **Client connection**: `--set server.kafka.brokers="kafka.lumniverse.com:9092"`
✓ **Graph access**: SSH tunnel to port 7474 (or build custom dashboard)

**Next Steps:**
1. Configure AWS Security Group (open port 9092)
2. Deploy test client using Helm chart
3. Verify data flow end-to-end
4. Set up monitoring via SSH tunnel
5. Document client onboarding process
