# KG RCA Mini Server - Complete Deployment Guide

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Server Provisioning](#server-provisioning)
3. [Initial Setup](#initial-setup)
4. [Configuration](#configuration)
5. [Deployment](#deployment)
6. [SSL Setup (Optional)](#ssl-setup-optional)
7. [Testing](#testing)
8. [Client Integration](#client-integration)
9. [Monitoring](#monitoring)
10. [Maintenance](#maintenance)

---

## Prerequisites

### What You Need

- **Server**: Ubuntu 20.04/22.04/24.04 LTS
- **Minimum Resources**: 4GB RAM, 2 vCPUs, 50GB disk
- **Recommended**: 8GB RAM, 4 vCPUs, 100GB SSD
- **Network**: Public IP address or domain name
- **Access**: SSH access with sudo privileges

### Your Local Machine

- Git installed
- SSH client
- Text editor

---

## Server Provisioning

### Option 1: AWS EC2

1. **Login to AWS Console**
   - Navigate to EC2 Dashboard
   - Click "Launch Instance"

2. **Configure Instance**
   ```
   Name: kg-rca-server
   OS: Ubuntu Server 22.04 LTS
   Instance Type: t3.large (or t3.xlarge for production)
   Key Pair: Create or select existing
   Storage: 100GB gp3 SSD
   ```

3. **Security Group Rules**
   ```
   SSH (22)         - Your IP only
   Kafka SSL (9093) - Anywhere (for clients)
   Neo4j (7474)     - Optional, Your IP only
   Neo4j (7687)     - Optional, Your IP only
   KG API (8080)    - Optional, Clients only
   Grafana (3000)   - Optional, Your IP only
   ```

4. **Launch and Note**
   - Save your key pair file (.pem)
   - Note the public IP address
   - Note the public DNS name

### Option 2: DigitalOcean

1. **Create Droplet**
   ```
   Image: Ubuntu 22.04 LTS
   Plan: 8GB RAM / 4 vCPUs ($48/mo)
   Region: Choose closest to your clients
   Authentication: SSH keys
   ```

2. **Configure Firewall**
   - Add rules similar to AWS above

### Option 3: Bare Metal / VPS

- Install Ubuntu 22.04 LTS
- Ensure you have root access
- Configure firewall (UFW)

---

## Initial Setup

### Step 1: Connect to Your Server

**For AWS:**
```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@YOUR_SERVER_IP
```

**For DigitalOcean or VPS:**
```bash
ssh root@YOUR_SERVER_IP
```

### Step 2: Update System

```bash
sudo apt update
sudo apt upgrade -y
```

### Step 3: Clone Repository

```bash
# If you have the code in GitHub
git clone https://github.com/your-org/kgroot_latest.git
cd kgroot_latest/mini-server-prod

# OR upload files manually
mkdir -p ~/kg-rca
cd ~/kg-rca
# Use scp or sftp to upload mini-server-prod folder
```

### Step 4: Run Setup Script

```bash
cd mini-server-prod
chmod +x scripts/*.sh
sudo ./scripts/setup-ubuntu.sh
```

**What this script does:**
- Installs Docker and Docker Compose
- Configures system optimizations
- Sets up firewall (optional)
- Configures user permissions

**Important:** If you added your user to the docker group, log out and back in:
```bash
exit
# SSH back in
ssh ubuntu@YOUR_SERVER_IP
```

### Step 5: Verify Docker Installation

```bash
docker --version
docker compose version
docker ps
```

Expected output:
```
Docker version 24.x.x
Docker Compose version v2.x.x
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```

---

## Configuration

### Step 1: Create Environment File

```bash
cd ~/kg-rca/mini-server-prod
cp .env.example .env
nano .env  # or use vim, vi, etc.
```

### Step 2: Configure Environment Variables

Edit `.env` file:

```bash
# ============================================================================
# REQUIRED SETTINGS
# ============================================================================

# Neo4j password (change this!)
NEO4J_PASSWORD=your_secure_password_here

# KG API key (generate with: openssl rand -hex 32)
KG_API_KEY=your_generated_api_key_here

# Grafana password
GRAFANA_PASSWORD=your_grafana_password

# ============================================================================
# SSL SETTINGS (if you'll use SSL)
# ============================================================================

# Your server's hostname or IP
KAFKA_ADVERTISED_HOST=YOUR_SERVER_IP_OR_HOSTNAME

# SSL passwords (if configuring SSL later)
KAFKA_SSL_KEYSTORE_PASSWORD=your_keystore_password
KAFKA_SSL_KEY_PASSWORD=your_key_password
KAFKA_SSL_TRUSTSTORE_PASSWORD=your_truststore_password

# ============================================================================
# OPTIONAL
# ============================================================================

# Logging level
LOG_LEVEL=info

# Grafana URL
GRAFANA_ROOT_URL=http://YOUR_SERVER_IP:3000
```

**Generate strong passwords:**
```bash
# Generate random passwords
openssl rand -hex 32

# Or use this for multiple passwords
for i in {1..3}; do openssl rand -hex 16; done
```

### Step 3: Save and Verify

```bash
# Save file (Ctrl+O, Enter, Ctrl+X in nano)

# Verify .env file
cat .env
```

---

## Deployment

### Step 1: Build and Start Services (Plaintext Kafka)

```bash
cd ~/kg-rca/mini-server-prod

# Start all services
docker compose up -d
```

### Step 2: Monitor Startup

```bash
# Watch logs
docker compose logs -f

# Or watch specific service
docker compose logs -f kafka
docker compose logs -f neo4j
docker compose logs -f graph-builder
```

**Wait for services to be healthy** (2-5 minutes). Press `Ctrl+C` to stop following logs.

### Step 3: Check Service Status

```bash
# Check running containers
docker compose ps

# Should see all services "Up" and "healthy"
```

Expected output:
```
NAME                 STATUS              PORTS
kg-alerts-enricher   Up
kg-grafana          Up (healthy)        0.0.0.0:3000->3000/tcp
kg-kafka            Up (healthy)        0.0.0.0:9092-9093->9092-9093/tcp
kg-kafka-ui         Up                  0.0.0.0:7777->8080/tcp
kg-neo4j            Up (healthy)        0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp
kg-api              Up (healthy)        0.0.0.0:8080->8080/tcp
kg-graph-builder    Up (healthy)        0.0.0.0:9090->9090/tcp
kg-prometheus       Up                  0.0.0.0:9091->9090/tcp
kg-zookeeper        Up                  0.0.0.0:2181->2181/tcp
```

### Step 4: Create Kafka Topics

```bash
./scripts/create-topics.sh
```

This creates all required topics:
- `raw.k8s.events`
- `raw.k8s.logs`
- `raw.prom.alerts`
- `events.normalized`
- `alerts.enriched`
- And more...

### Step 5: Run Health Checks

```bash
./scripts/test-services.sh
```

Expected: All services should show ✓ green checkmarks.

---

## SSL Setup (Optional)

### When Do You Need SSL?

- ✅ **Yes**: Clients connect over public internet
- ✅ **Yes**: Security compliance requirements
- ❌ **No**: All clients are on same VPC/private network
- ❌ **No**: Testing/development environment

### Step 1: Generate SSL Certificates

```bash
cd ~/kg-rca/mini-server-prod
./scripts/setup-ssl.sh
```

**Follow the prompts:**
1. Enter your server's public hostname or IP
2. Set strong passwords for keystores
3. Choose whether to generate client certificates

### Step 2: Verify SSL Files

```bash
ls -l ssl/
```

Should see:
```
ca-cert
kafka.keystore.jks
kafka.truststore.jks
```

### Step 3: Update .env File

The script automatically updates `.env`, verify:

```bash
grep KAFKA .env
```

Should show:
```
KAFKA_ADVERTISED_HOST=your-server-ip
KAFKA_SSL_KEYSTORE_PASSWORD=xxx
KAFKA_SSL_KEY_PASSWORD=xxx
KAFKA_SSL_TRUSTSTORE_PASSWORD=xxx
```

### Step 4: Deploy with SSL

```bash
# Stop services
docker compose down

# Start with SSL configuration
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d

# Wait for services to start
sleep 30

# Check logs
docker compose logs kafka | tail -20
```

### Step 5: Open SSL Port in Firewall

```bash
sudo ufw allow 9093/tcp
sudo ufw status
```

### Step 6: Test SSL Connection

```bash
# From another machine with kafka tools:
openssl s_client -connect YOUR_SERVER_IP:9093 -showcerts

# Should show SSL handshake success
```

---

## Testing

### Test 1: Service Access

```bash
# Kafka UI
curl http://localhost:7777

# Neo4j Browser
curl http://localhost:7474

# KG API
curl http://localhost:8080/healthz

# Prometheus
curl http://localhost:9091/-/healthy

# Grafana
curl http://localhost:3000/api/health
```

### Test 2: Kafka Topics

```bash
# List topics
docker exec kg-kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --list

# Describe a topic
docker exec kg-kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --describe --topic raw.k8s.events
```

### Test 3: Neo4j Connection

```bash
# Access Neo4j shell
docker exec -it kg-neo4j cypher-shell -u neo4j -p YOUR_NEO4J_PASSWORD

# In the shell, run:
RETURN "Connection successful" AS message;

# Exit with: :exit
```

### Test 4: Send Test Event

```bash
# Producer test event
echo '{"id":"test-1","timestamp":"2024-01-01T00:00:00Z","severity":"ERROR","message":"Test event","resource_type":"Pod","resource_name":"test-pod","namespace":"default"}' | \
docker exec -i kg-kafka kafka-console-producer.sh \
    --bootstrap-server localhost:9092 \
    --topic events.normalized

# Consume to verify
docker exec kg-kafka kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic events.normalized \
    --from-beginning \
    --max-messages 1 \
    --timeout-ms 5000
```

### Test 5: External Access

**From your local machine:**

```bash
# Replace YOUR_SERVER_IP with actual IP

# Kafka UI
open http://YOUR_SERVER_IP:7777

# Neo4j Browser
open http://YOUR_SERVER_IP:7474

# Grafana
open http://YOUR_SERVER_IP:3000
```

---

## Client Integration

### Step 1: Get Connection Details

**For Plaintext (internal/VPC):**
```
Kafka Broker: YOUR_SERVER_IP:9092
Protocol: PLAINTEXT
```

**For SSL (internet):**
```
Kafka Broker: YOUR_SERVER_IP:9093
Protocol: SSL
CA Certificate: ~/kg-rca/mini-server-prod/ssl/ca-cert
```

### Step 2: Copy CA Certificate (if using SSL)

**From server to local machine:**
```bash
# On your local machine
scp ubuntu@YOUR_SERVER_IP:~/kg-rca/mini-server-prod/ssl/ca-cert ./ca-cert
```

### Step 3: Deploy Client Agent (Helm)

**On your Kubernetes cluster:**

```bash
# Add values for Helm chart
cat > client-values.yaml <<EOF
client:
  id: "my-company-cluster-1"
  apiKey: "YOUR_KG_API_KEY"  # From .env file

  kafka:
    brokers: "YOUR_SERVER_IP:9093"
    protocol: SSL
    sasl:
      mechanism: PLAIN
      username: ""  # Not needed for SSL without SASL
      password: ""

    tls:
      enabled: true
      caCert: |
$(cat ca-cert | sed 's/^/        /')

# Enable components
eventExporter:
  enabled: true

logExporter:
  enabled: true

prometheusExporter:
  enabled: true
EOF

# Install Helm chart
helm install kg-rca-agent ./path/to/helm-chart \
    -f client-values.yaml \
    -n observability \
    --create-namespace
```

### Step 4: Verify Client Connection

```bash
# Check client pods
kubectl get pods -n observability

# Check logs
kubectl logs -n observability -l app=kg-rca-agent -f

# Should see: "Connected to Kafka" messages
```

### Step 5: Verify Data Flow

**Back on the server:**

```bash
# Check topic activity in Kafka UI
open http://YOUR_SERVER_IP:7777

# Or via CLI - check message count
docker exec kg-kafka kafka-run-class.sh \
    kafka.tools.GetOffsetShell \
    --broker-list localhost:9092 \
    --topic raw.k8s.events

# Should show increasing offsets
```

---

## Monitoring

### Access Monitoring Tools

1. **Kafka UI** - `http://YOUR_SERVER_IP:7777`
   - View topics, messages, consumer groups
   - Monitor lag, throughput

2. **Neo4j Browser** - `http://YOUR_SERVER_IP:7474`
   - Login: neo4j / YOUR_NEO4J_PASSWORD
   - Query graph data
   - Visualize relationships

3. **Grafana** - `http://YOUR_SERVER_IP:3000`
   - Login: admin / YOUR_GRAFANA_PASSWORD
   - View dashboards
   - Set up alerts

4. **Prometheus** - `http://YOUR_SERVER_IP:9091`
   - View metrics
   - Query with PromQL

### Key Metrics to Monitor

```bash
# Check Graph Builder metrics
curl http://localhost:9090/metrics | grep kg_

# Check container stats
docker stats

# Check system resources
htop
df -h
```

### Set Up Alerts (Optional)

Create Prometheus alerts in `config/prometheus.yml`:

```yaml
rule_files:
  - "alerts.yml"
```

---

## Maintenance

### Daily Operations

**View logs:**
```bash
docker compose logs -f --tail=100
```

**Restart a service:**
```bash
docker compose restart <service-name>
```

**Update configuration:**
```bash
# Edit config
nano config/prometheus.yml

# Reload (if supported)
docker compose restart prometheus
```

### Backups

**Manual backup:**
```bash
./scripts/backup.sh
```

**Automated backups (cron):**
```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * cd ~/kg-rca/mini-server-prod && ./scripts/backup.sh >> backup.log 2>&1
```

**Upload backups to S3:**
```bash
# Install AWS CLI
sudo apt install awscli -y

# Configure
aws configure

# Upload
aws s3 cp backups/kg-rca-backup-*.tar.gz s3://your-bucket/backups/
```

### Updates

**Update Docker images:**
```bash
docker compose pull
docker compose up -d
```

**Update application code:**
```bash
cd ~/kg-rca/mini-server-prod
git pull
docker compose build
docker compose up -d
```

### Scaling

**Increase resources:**

1. **Horizontal**: Add more servers and load balance
2. **Vertical**: Upgrade instance type (t3.large → t3.xlarge)

**Adjust memory limits:**

Edit [docker-compose.yml](docker-compose.yml):
```yaml
neo4j:
  environment:
    NEO4J_server_memory_heap_max__size: 8G  # Increase
```

### Troubleshooting

**Service won't start:**
```bash
docker compose logs <service-name>
docker inspect <container-name>
```

**Out of disk space:**
```bash
docker system prune -a
df -h
```

**Performance issues:**
```bash
docker stats
htop
```

See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for detailed solutions.

---

## Security Checklist

- [ ] Changed all default passwords
- [ ] Configured firewall (UFW)
- [ ] SSL/TLS enabled for external access
- [ ] SSH key-based authentication only
- [ ] Regular backups configured
- [ ] Monitoring alerts set up
- [ ] Sensitive data not in version control
- [ ] API keys secured
- [ ] Regular security updates scheduled

---

## Next Steps

1. ✅ Deploy and test the server
2. ✅ Install client agents on your clusters
3. ✅ Configure monitoring dashboards
4. ✅ Set up automated backups
5. ✅ Document your deployment
6. 📊 Start analyzing your incidents!

---

## Support

**Need help?**

1. Check [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
2. Review logs: `docker compose logs -f`
3. Run health check: `./scripts/test-services.sh`
4. Check GitHub issues

**Have questions?**

- Open an issue on GitHub
- Contact: support@lumniverse.com

---

**Congratulations! Your KG RCA server is ready! 🎉**
