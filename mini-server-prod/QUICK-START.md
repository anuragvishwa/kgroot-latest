# Quick Start Guide - 15 Minutes to Production

This guide gets you from zero to a running KG RCA server in 15 minutes.

## Prerequisites

- Ubuntu server with 8GB RAM, 4 vCPUs
- SSH access with sudo
- This repository on the server

## Step 1: Initial Setup (5 minutes)

SSH to your server and run:

```bash
# Update system and install Docker
sudo apt update && sudo apt upgrade -y
cd ~/kg-rca/mini-server-prod
chmod +x scripts/*.sh
sudo ./scripts/setup-ubuntu.sh
```

**Log out and back in** if you were added to the docker group.

## Step 2: Configure Environment (2 minutes)

```bash
cd ~/kg-rca/mini-server-prod

# Copy and edit environment file
cp .env.example .env
nano .env
```

**Required changes:**
- `NEO4J_PASSWORD`: Set a strong password
- `KG_API_KEY`: Generate with `openssl rand -hex 32`
- `GRAFANA_PASSWORD`: Set a password

Save and exit (Ctrl+O, Enter, Ctrl+X).

## Step 3: Deploy Services (5 minutes)

```bash
# Start all services
docker compose up -d

# Wait for services to be healthy
sleep 60

# Create Kafka topics
./scripts/create-topics.sh
```

## Step 4: Verify Deployment (2 minutes)

```bash
# Run health checks
./scripts/test-services.sh

# Check services are running
docker compose ps
```

Expected: All services showing "Up" and "healthy".

## Step 5: Access Services (1 minute)

Replace `YOUR_SERVER_IP` with your actual IP:

- **Kafka UI**: http://YOUR_SERVER_IP:7777
- **Neo4j**: http://YOUR_SERVER_IP:7474 (user: neo4j, password: YOUR_NEO4J_PASSWORD)
- **Grafana**: http://YOUR_SERVER_IP:3000 (user: admin, password: YOUR_GRAFANA_PASSWORD)

## Next Steps

### Enable SSL (Recommended for Production)

```bash
# Generate SSL certificates
./scripts/setup-ssl.sh

# Redeploy with SSL
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d

# Open firewall
sudo ufw allow 9093/tcp
```

### Deploy Client Agents

Update your Helm values:

```yaml
client:
  id: "your-cluster-id"
  apiKey: "YOUR_KG_API_KEY"  # From .env

  kafka:
    brokers: "YOUR_SERVER_IP:9093"
    protocol: SSL
    tls:
      enabled: true
      caCert: |
        # Copy from ssl/ca-cert on server
```

Deploy:

```bash
helm install kg-rca-agent ./helm-chart -f values.yaml -n observability
```

### Set Up Automated Backups

```bash
# Test backup
./scripts/backup.sh

# Schedule daily backups
crontab -e

# Add:
0 2 * * * cd /home/ubuntu/kg-rca/mini-server-prod && ./scripts/backup.sh
```

## Troubleshooting

### Services not starting?

```bash
# Check logs
docker compose logs -f

# Check specific service
docker compose logs <service-name>
```

### Port not accessible?

```bash
# Check firewall
sudo ufw status

# Open port
sudo ufw allow <port>/tcp
```

### Need help?

- Full guide: [STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md)
- Troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Commands Cheat Sheet

```bash
# View logs
docker compose logs -f

# Restart service
docker compose restart <service>

# Stop all services
docker compose down

# Start all services
docker compose up -d

# Check health
./scripts/test-services.sh

# Backup
./scripts/backup.sh

# Update services
docker compose pull
docker compose up -d
```

---

**Congratulations! Your KG RCA server is running!** 🎉

Next: Deploy client agents to start collecting data.
