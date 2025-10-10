# Quick Start - EC2 Deployment (5 Minutes)

The fastest way to get KG RCA running on EC2.

## TL;DR

```bash
# 1. Launch EC2 (t3.large, Ubuntu 22.04, 100GB disk)
# 2. SSH to server
ssh ubuntu@<server-ip>

# 3. One-command setup
curl -sSL https://raw.githubusercontent.com/yourorg/kg-rca/main/saas/server_mini/setup.sh | bash

# 4. Configure
cd kg-rca
nano .env  # Set DOMAIN and EMAIL

# 5. Start
docker-compose up -d

# 6. Setup SSL
sudo certbot --nginx -d api.yourdomain.com

# Done! 🎉
```

## What You Get

- ✅ Full KG RCA stack running on single server
- ✅ Docker Compose orchestration
- ✅ Automatic SSL with Let's Encrypt
- ✅ Health monitoring
- ✅ Daily backups
- ✅ Auto-start on boot

## Components Deployed

```
┌─────────────────────────────────┐
│  EC2 Instance (t3.large)        │
│  ├─ Kafka + Zookeeper           │
│  ├─ Neo4j (Knowledge Graph)     │
│  ├─ Graph Builder               │
│  ├─ Alerts Enricher             │
│  ├─ KG API                      │
│  ├─ Prometheus + Grafana        │
│  └─ Nginx (SSL Termination)     │
└─────────────────────────────────┘
```

## Minimum Requirements

- **Instance:** t3.large (2 vCPU, 8GB RAM)
- **Storage:** 100 GB SSD
- **OS:** Ubuntu 22.04 LTS
- **Network:** Public IP, ports 22/80/443

## Terraform Deployment (Recommended)

```bash
cd saas/server_mini/terraform

# Create config
cat > terraform.tfvars <<EOF
domain       = "api.yourdomain.com"
ssh_key_name = "your-key"
instance_type = "t3.large"
EOF

# Deploy
terraform init
terraform apply

# Output shows IP and next steps
```

## Manual Steps After Deployment

### 1. Configure DNS
```
api.yourdomain.com -> <SERVER_IP>
```

### 2. Edit Environment
```bash
nano .env
# Set: DOMAIN, EMAIL
# Save: NEO4J_PASSWORD, GRAFANA_ADMIN_PASSWORD
```

### 3. Start Services
```bash
docker-compose up -d
./health-check.sh
```

### 4. Setup SSL
```bash
sudo certbot --nginx -d api.yourdomain.com
```

## Verify Deployment

```bash
# Health check
curl https://api.yourdomain.com/api/v1/health

# Expected response
{"status":"healthy","version":"1.0.0"}
```

## Access Monitoring (SSH Tunnel)

```bash
ssh -L 3000:localhost:3000 -L 7474:localhost:7474 ubuntu@<IP>
```

- **Grafana:** http://localhost:3000
- **Neo4j:** http://localhost:7474

## Cost

- **t3.large:** ~$77/month
- **t3.xlarge:** ~$137/month

## When to Scale

- 5 clients → t3.large
- 10 clients → t3.xlarge
- 20+ clients → Migrate to K8s (`../server/`)

## Troubleshooting

```bash
# Check services
docker-compose ps

# View logs
docker-compose logs -f

# Restart service
docker-compose restart <service-name>
```

## Next Steps

1. ✅ Server running
2. [Register first client](./DEPLOYMENT_GUIDE.md#client-onboarding)
3. [Deploy client agent](../client/README.md)
4. [Setup monitoring](./DEPLOYMENT_GUIDE.md#setup-grafana-dashboards)

## Full Documentation

See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) for complete instructions.
