# KG RCA Server - EC2 Deployment Guide

Complete step-by-step guide for deploying KG RCA on a single EC2 instance.

## Overview

This guide walks you through deploying the entire KG RCA stack on a single AWS EC2 instance using Docker Compose. Perfect for MVP/pilot deployments with 5-10 clients.

**What you'll deploy:**
- Kafka + Zookeeper (event streaming)
- Neo4j (knowledge graph database)
- Graph Builder (KG construction)
- Alerts Enricher (alert processing)
- KG API (REST API for clients)
- Prometheus + Grafana (monitoring)
- Nginx (reverse proxy with SSL)

**Time estimate:** 30-45 minutes

## Prerequisites

✅ **Required:**
- AWS Account with EC2 access
- Domain name (e.g., `api.yourdomain.com`)
- SSH key pair in AWS
- AWS CLI installed and configured (for Terraform)

✅ **Recommended:**
- Basic Docker knowledge
- Familiarity with Linux/Ubuntu

## Option A: Automated Deployment (Terraform)

### Step 1: Configure Terraform

```bash
cd saas/server_mini/terraform

# Copy example variables
cat > terraform.tfvars <<EOF
aws_region       = "us-east-1"
instance_type    = "t3.large"
domain           = "api.yourdomain.com"
ssh_key_name     = "your-ssh-key-name"
allowed_ssh_cidr = ["YOUR.IP.ADDRESS/32"]  # Your IP only
EOF
```

### Step 2: Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Review plan
terraform plan

# Deploy (takes 2-3 minutes)
terraform apply
```

**Output will show:**
- Public IP address
- SSH command
- DNS configuration needed
- Next steps

### Step 3: Configure DNS

Create an A record in your DNS provider:
```
api.yourdomain.com -> <PUBLIC_IP_FROM_TERRAFORM>
```

Wait for DNS propagation (use `dig api.yourdomain.com` to check)

### Step 4: SSH and Setup

```bash
# SSH to server
ssh ubuntu@<PUBLIC_IP>

# Clone your repository
git clone <your-repo-url>
cd kg-rca/saas/server_mini

# Run setup script
./setup.sh
```

### Step 5: Configure Environment

```bash
# Edit .env file
nano .env
```

Set these values:
```bash
DOMAIN=api.yourdomain.com
EMAIL=admin@yourdomain.com
NEO4J_PASSWORD=<keep-generated-password>
GRAFANA_ADMIN_PASSWORD=<keep-generated-password>
```

**⚠️ IMPORTANT:** Save the auto-generated passwords somewhere secure!

### Step 6: Start Services

```bash
# Start all services
docker-compose up -d

# Watch logs (Ctrl+C to exit)
docker-compose logs -f

# Wait for all services to be healthy (2-3 minutes)
watch docker-compose ps
```

### Step 7: Setup SSL Certificate

```bash
# Request certificate from Let's Encrypt
sudo certbot --nginx -d api.yourdomain.com

# Follow prompts:
# - Enter email
# - Agree to terms
# - Choose to redirect HTTP to HTTPS (recommended)
```

### Step 8: Verify Deployment

```bash
# Run health check
./health-check.sh

# Test API endpoint
curl https://api.yourdomain.com/api/v1/health
```

**Expected output:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-10T12:00:00Z"
}
```

---

## Option B: Manual Deployment (AWS Console)

### Step 1: Launch EC2 Instance

1. Go to AWS EC2 Console
2. Click "Launch Instance"
3. Configure:
   - **Name:** kg-rca-server
   - **AMI:** Ubuntu Server 22.04 LTS
   - **Instance Type:** t3.large
   - **Key Pair:** Select your SSH key
   - **Storage:** 30 GB root + 100 GB data volume (gp3)
   - **Security Group:**
     - SSH (22) from your IP
     - HTTP (80) from anywhere
     - HTTPS (443) from anywhere

4. Launch instance

### Step 2: Configure DNS

Create an A record:
```
api.yourdomain.com -> <ELASTIC_IP>
```

### Step 3: SSH and Run Setup

```bash
# Connect to instance
ssh -i your-key.pem ubuntu@<INSTANCE_IP>

# Download setup script
curl -O https://raw.githubusercontent.com/yourorg/kg-rca/main/saas/server_mini/setup.sh
chmod +x setup.sh

# Run setup
./setup.sh
```

Continue from **Step 5** in Option A above.

---

## Post-Deployment Configuration

### Access Monitoring Tools

Use SSH tunneling to access internal services:

```bash
# Create tunnels
ssh -L 3000:localhost:3000 \
    -L 7474:localhost:7474 \
    -L 7777:localhost:7777 \
    ubuntu@<SERVER_IP>
```

Then open in browser:
- **Grafana:** http://localhost:3000 (admin / <GRAFANA_PASSWORD>)
- **Neo4j Browser:** http://localhost:7474 (neo4j / <NEO4J_PASSWORD>)
- **Kafka UI:** http://localhost:7777

### Setup Grafana Dashboards

1. Open Grafana (http://localhost:3000)
2. Add Neo4j data source:
   - URL: `bolt://neo4j:7687`
   - Username: `neo4j`
   - Password: `<NEO4J_PASSWORD>`
3. Import dashboards from `config/grafana/dashboards/`

### Configure Backups

```bash
# Create daily backup cron job
crontab -e

# Add this line (backup at 2 AM daily)
0 2 * * * /home/ubuntu/kg-rca/backup.sh
```

### Setup Monitoring Alerts

```bash
# Install AWS CloudWatch agent (optional)
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb

# Configure basic metrics
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-config-wizard
```

---

## Client Onboarding

### Register First Client

```bash
# Test client registration
curl -X POST https://api.yourdomain.com/api/v1/client/register \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "test-client",
    "email": "test@example.com",
    "cluster_name": "test-cluster"
  }'
```

Response:
```json
{
  "client_id": "test-client",
  "api_key": "kg_xxx...",
  "kafka": {
    "brokers": ["kafka.yourdomain.com:9092"],
    "username": "test-client",
    "password": "xxx..."
  }
}
```

**Save these credentials!** The API key and Kafka credentials are shown only once.

### Deploy Client Agent

Use the credentials from above to deploy the client agent (Helm chart):

```bash
# On client's Kubernetes cluster
helm install kg-rca-agent ./client/helm-chart/kg-rca-agent \
  --set client.id=test-client \
  --set client.apiKey=kg_xxx... \
  --set client.kafka.sasl.username=test-client \
  --set client.kafka.sasl.password=xxx...
```

---

## Operations

### Daily Checks

```bash
# Check service health
./health-check.sh

# Check disk space
df -h

# Check memory
free -h

# Check Docker stats
docker stats --no-stream
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f graph-builder

# Last 100 lines
docker-compose logs --tail=100 kg-api
```

### Restart Services

```bash
# Restart single service
docker-compose restart graph-builder

# Restart all
docker-compose restart

# Full restart (recreate containers)
docker-compose down
docker-compose up -d
```

### Update Services

```bash
# Pull latest images
docker-compose pull

# Recreate containers with new images
docker-compose up -d

# Check status
docker-compose ps
```

### Backup and Restore

**Backup:**
```bash
# Manual backup
./backup.sh

# Backups stored in ./backups/
ls -lh backups/
```

**Restore:**
```bash
# Stop Neo4j
docker-compose stop neo4j

# Restore dump
docker-compose run --rm neo4j \
  neo4j-admin database load neo4j \
  --from-path=/backups/neo4j_20240110_020000.dump.gz

# Start Neo4j
docker-compose start neo4j
```

---

## Scaling

### When to Scale Up

Consider scaling when:
- CPU usage > 70% sustained
- Memory usage > 80%
- More than 10 active clients
- Query response time > 2 seconds

### Vertical Scaling (Resize Instance)

```bash
# Stop services
docker-compose down

# Resize instance (via AWS Console or CLI)
aws ec2 modify-instance-attribute \
  --instance-id i-xxxxx \
  --instance-type t3.xlarge

aws ec2 start-instances --instance-ids i-xxxxx

# SSH back and start services
docker-compose up -d
```

### Horizontal Scaling (Migrate to K8s)

When you need multi-server deployment:

1. **Backup data:** `./backup.sh`
2. **Setup EKS:** Follow `../server/README.md`
3. **Migrate Neo4j data:** Restore backup to EKS
4. **Update DNS:** Point to ALB
5. **Decommission EC2**

---

## Troubleshooting

### Services Won't Start

```bash
# Check logs
docker-compose logs

# Check disk space
df -h

# Check memory
free -h

# Restart Docker
sudo systemctl restart docker
docker-compose up -d
```

### Neo4j Out of Memory

Edit `docker-compose.yml`:
```yaml
environment:
  NEO4J_server_memory_heap_max__size: 3G  # Reduce from 4G
```

Then restart:
```bash
docker-compose up -d neo4j
```

### Kafka Consumer Lag

```bash
# Check consumer groups
docker-compose exec kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --all-groups

# If lag is high, check graph-builder logs
docker-compose logs -f graph-builder
```

### SSL Certificate Issues

```bash
# Check certificate expiry
sudo certbot certificates

# Renew manually
sudo certbot renew

# Check Nginx config
sudo nginx -t
```

### Can't Connect to API

```bash
# Check Nginx is running
docker-compose ps nginx

# Check Nginx logs
docker-compose logs nginx

# Test locally
curl http://localhost:8080/api/v1/health
```

---

## Security Checklist

- [ ] Changed default Neo4j password
- [ ] Changed default Grafana password
- [ ] Setup firewall (only 22/80/443)
- [ ] SSH key-based auth only (disable password)
- [ ] SSL certificate installed
- [ ] Regular backups configured
- [ ] CloudWatch monitoring setup
- [ ] Security updates enabled
- [ ] API rate limiting configured
- [ ] Log rotation enabled

---

## Cost Optimization

### Cost Breakdown (t3.large)

| Item | Monthly Cost |
|------|--------------|
| t3.large instance | $60 |
| 100 GB gp3 storage | $8 |
| Data transfer (100GB) | $9 |
| **Total** | **$77** |

### Cost Saving Tips

1. **Use Reserved Instances:** Save 30-40% with 1-year commitment
2. **Stop during off-hours:** If not 24/7, schedule stop/start
3. **Optimize storage:** Delete old Kafka logs and Neo4j snapshots
4. **Use Spot Instances:** For dev/staging (not recommended for production)

### Scaling Costs

| Instance Type | vCPU | RAM | Monthly Cost | Clients |
|--------------|------|-----|--------------|---------|
| t3.large | 2 | 8 GB | $60 | 5 |
| t3.xlarge | 4 | 16 GB | $120 | 10 |
| t3.2xlarge | 8 | 32 GB | $240 | 20+ |

---

## Support

- **Documentation:** See `README.md` and `../docs/`
- **Issues:** GitHub Issues
- **Emergency:** Check `docker-compose logs` first

## Next Steps

1. ✅ Server deployed and running
2. ⏭️ Register your first client
3. ⏭️ Deploy client agent in their cluster
4. ⏭️ Verify events flowing through Kafka
5. ⏭️ Test RCA query
6. ⏭️ Setup monitoring dashboards
7. ⏭️ Configure backups

**Congratulations!** Your KG RCA MVP server is now live! 🎉
