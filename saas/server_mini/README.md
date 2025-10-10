# KG RCA Server - EC2 MVP Deployment

Simple single-server deployment on AWS EC2 (t3.large or t3.xlarge) for MVP.

## Overview

This deployment runs all components on a single EC2 instance using Docker Compose, suitable for:
- MVP/Pilot deployments
- Up to 5-10 clients
- Development/staging environments
- Cost-effective initial rollout

## Architecture

```
┌─────────────────────────────────────────────┐
│           AWS EC2 (t3.large/xlarge)         │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │      Docker Compose Stack            │  │
│  │                                      │  │
│  │  ├─ Kafka + Zookeeper               │  │
│  │  ├─ Neo4j                            │  │
│  │  ├─ Graph Builder                    │  │
│  │  ├─ Alerts Enricher                  │  │
│  │  ├─ KG API (port 8080)               │  │
│  │  ├─ Prometheus                       │  │
│  │  └─ Grafana                          │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │      Nginx (Reverse Proxy)           │  │
│  │  - SSL Termination                   │  │
│  │  - Client API endpoints              │  │
│  └──────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

## Recommended Instance Sizes

### t3.large (MVP - 5 clients)
- 2 vCPUs, 8 GB RAM
- Cost: ~$60/month
- Good for: Initial pilot, low volume

### t3.xlarge (Production MVP - 10 clients)
- 4 vCPUs, 16 GB RAM
- Cost: ~$120/month
- Good for: Small production deployment

### Storage
- 100 GB gp3 EBS volume (Neo4j data)
- Cost: ~$8/month

## Prerequisites

- AWS Account with EC2 access
- Domain name (e.g., `api.yourdomain.com`)
- SSL certificate (Let's Encrypt via Certbot)

## Quick Start

### 1. Launch EC2 Instance

```bash
# Use the provided Terraform or CloudFormation
cd terraform
terraform init
terraform apply -var="instance_type=t3.large" -var="domain=api.yourdomain.com"
```

Or manually via AWS Console:
- AMI: Ubuntu 22.04 LTS
- Instance Type: t3.large
- Storage: 100 GB gp3
- Security Groups: HTTP (80), HTTPS (443), SSH (22)

### 2. Setup Script (Automated)

SSH into the instance and run:

```bash
curl -sSL https://raw.githubusercontent.com/yourorg/kg-rca/main/saas/server_mini/setup.sh | bash
```

Or manually:

```bash
# Clone this repo
git clone https://github.com/yourorg/kg-rca.git
cd kg-rca/saas/server_mini

# Run setup
./setup.sh
```

### 3. Configure Environment

Edit `.env` file:

```bash
# Domain configuration
DOMAIN=api.yourdomain.com
EMAIL=admin@yourdomain.com

# Neo4j credentials
NEO4J_PASSWORD=<strong-password>

# Kafka configuration (default is fine)
KAFKA_RETENTION_HOURS=168

# Optional: Prometheus/Grafana admin password
GRAFANA_ADMIN_PASSWORD=<strong-password>
```

### 4. Start Services

```bash
# Start all services
docker-compose up -d

# Check health
./health-check.sh

# View logs
docker-compose logs -f
```

### 5. Setup SSL

```bash
# Install Certbot
sudo certbot --nginx -d api.yourdomain.com

# Auto-renewal is configured
```

## API Endpoints

After deployment, the following endpoints are available:

### Client API (port 443 - HTTPS)
- `POST /api/v1/client/register` - Register new client
- `POST /api/v1/events` - Ingest events (with API key auth)
- `GET /api/v1/rca/{incident_id}` - Get RCA for incident
- `GET /api/v1/health` - Health check

### Internal Monitoring (SSH tunnel only)
- Grafana: http://localhost:3000
- Neo4j Browser: http://localhost:7474
- Kafka UI: http://localhost:7777
- Prometheus: http://localhost:9091

## Client Onboarding

```bash
# Register new client
curl -X POST https://api.yourdomain.com/api/v1/client/register \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "acme-corp",
    "email": "admin@acme.com",
    "cluster_name": "prod-us-west-2"
  }'

# Response includes API key and Kafka credentials
```

## Monitoring & Operations

### Health Check
```bash
./health-check.sh
```

### Backup Neo4j Data
```bash
./backup.sh
```

### View Metrics
```bash
# SSH tunnel to Grafana
ssh -L 3000:localhost:3000 ubuntu@<ec2-ip>

# Open http://localhost:3000
```

### Scale Up
```bash
# Resize instance
aws ec2 modify-instance-attribute \
  --instance-id i-xxxxx \
  --instance-type t3.xlarge

# Restart instance
aws ec2 reboot-instances --instance-ids i-xxxxx
```

## Cost Estimation

### Monthly Costs (t3.large)
- EC2 Instance: $60
- EBS Storage (100GB): $8
- Data Transfer (100GB): $9
- **Total: ~$77/month**

### Monthly Costs (t3.xlarge)
- EC2 Instance: $120
- EBS Storage (100GB): $8
- Data Transfer (100GB): $9
- **Total: ~$137/month**

## Migration Path to K8s

When you outgrow single-server deployment:

1. **Backup data**: Use `./backup.sh`
2. **Setup EKS cluster**: Use `../server/` deployment
3. **Migrate data**: Restore Neo4j data to EKS
4. **Update DNS**: Point to ALB
5. **Decommission EC2**

## Troubleshooting

### Services not starting
```bash
# Check Docker logs
docker-compose logs -f

# Check disk space
df -h

# Check memory
free -h
```

### Out of memory
```bash
# Check Neo4j memory usage
docker stats

# Reduce Neo4j heap size in docker-compose.yml
# NEO4J_server_memory_heap_max__size: 3G
```

### Kafka issues
```bash
# Check Kafka topics
docker-compose exec kafka kafka-topics.sh --list --bootstrap-server localhost:9092

# Check consumer lag
docker-compose exec kafka kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups
```

## Security Considerations

1. **API Keys**: Use strong random keys for each client
2. **Neo4j Password**: Change default password
3. **Firewall**: Only expose ports 80/443/22
4. **SSH**: Use key-based authentication only
5. **Updates**: Regular security updates
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

## Support

- Documentation: `/docs`
- Issues: GitHub Issues
- Email: support@yourdomain.com
