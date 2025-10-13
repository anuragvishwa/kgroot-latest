# KG RCA Mini Server - Production Deployment Guide

## Overview

This folder contains everything you need to deploy the KG RCA platform on an **Ubuntu server** for production use.

**Target Environment**: Ubuntu 20.04/22.04/24.04 LTS on AWS EC2, DigitalOcean, or bare metal

## What's Included

### 📁 Directory Structure

```
mini-server-prod/
├── README.md                           # This file - start here
├── STEP-BY-STEP-GUIDE.md              # Complete deployment walkthrough
├── docker-compose.yml                  # Main orchestration file
├── docker-compose.ssl.yml              # SSL-enabled version (optional)
├── .env.example                        # Environment variables template
├── config/                             # Service configurations
│   ├── prometheus.yml                  # Prometheus config
│   ├── grafana/
│   │   ├── datasources/               # Grafana data sources
│   │   └── dashboards/                # Grafana dashboards
│   └── kafka/
│       └── server.properties          # Kafka configuration
├── scripts/                            # Automation scripts
│   ├── setup-ubuntu.sh                # Initial Ubuntu setup
│   ├── install-docker.sh              # Docker installation
│   ├── setup-ssl.sh                   # SSL certificate setup
│   ├── create-topics.sh               # Kafka topic creation
│   ├── test-services.sh               # Service health checks
│   └── backup.sh                      # Data backup script
├── ssl/                                # SSL certificates (you'll generate)
│   └── .gitkeep
└── docs/
    ├── ARCHITECTURE.md                # System architecture
    ├── TROUBLESHOOTING.md             # Common issues & fixes
    ├── MONITORING.md                  # How to monitor the system
    ├── BACKUP-RESTORE.md              # Backup & restore procedures
    └── SECURITY.md                    # Security best practices
```

## Quick Start

### Prerequisites

- Ubuntu server (20.04, 22.04, or 24.04 LTS)
- Minimum 4GB RAM, 2 vCPUs
- Recommended: 8GB RAM, 4 vCPUs
- 50GB disk space
- Root or sudo access

### Installation Steps (Summary)

1. **Clone this repository** to your server
2. **Run setup script**: `./scripts/setup-ubuntu.sh`
3. **Configure environment**: Copy and edit `.env.example` to `.env`
4. **Start services**: `docker compose up -d`
5. **Verify deployment**: `./scripts/test-services.sh`

👉 **For detailed instructions, see [STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md)**

## Services Deployed

| Service | Port | Description |
|---------|------|-------------|
| **Kafka** | 9092 | Message broker (internal) |
| **Kafka** | 9093 | Message broker (SSL - external) |
| **Zookeeper** | 2181 | Kafka coordination |
| **Neo4j** | 7474, 7687 | Graph database |
| **Graph Builder** | 9090 | Core KG processing |
| **KG API** | 8080 | REST API |
| **Alerts Enricher** | - | Alert processing |
| **Prometheus** | 9091 | Metrics collection |
| **Grafana** | 3000 | Metrics visualization |
| **Kafka UI** | 7777 | Kafka management |

## System Requirements

### Minimum (Testing/Development)
- **CPU**: 2 vCPUs
- **RAM**: 4GB
- **Disk**: 50GB
- **Network**: 1 Gbps

### Recommended (Production)
- **CPU**: 4 vCPUs
- **RAM**: 8GB
- **Disk**: 100GB (SSD)
- **Network**: 1 Gbps
- **Bandwidth**: 1TB/month

### Optimal (High Load)
- **CPU**: 8 vCPUs
- **RAM**: 16GB
- **Disk**: 200GB (NVMe SSD)
- **Network**: 10 Gbps
- **Bandwidth**: Unlimited

## AWS EC2 Instance Types

| Instance Type | vCPUs | RAM | Use Case | Monthly Cost* |
|---------------|-------|-----|----------|--------------|
| **t3.medium** | 2 | 4GB | Testing/Dev | ~$30 |
| **t3.large** | 2 | 8GB | Small production | ~$60 |
| **t3.xlarge** | 4 | 16GB | Medium production | ~$121 |
| **t3.2xlarge** | 8 | 32GB | Large production | ~$242 |

*Approximate costs for us-east-1 region

## Network Ports to Open

### Internal (Docker Network Only)
- 2181 (Zookeeper)
- 9092 (Kafka internal)

### External (Open in Firewall)
- **22** - SSH (your IP only)
- **9093** - Kafka SSL (client connections)
- **7474, 7687** - Neo4j (if remote access needed)
- **8080** - KG API (if remote access needed)
- **3000** - Grafana (optional, can use SSH tunnel)
- **9091** - Prometheus (optional, can use SSH tunnel)
- **7777** - Kafka UI (optional, can use SSH tunnel)

## Documentation

### Essential Guides
1. **[STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md)** - Complete deployment walkthrough
2. **[TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - Problem solving
3. **[MONITORING.md](docs/MONITORING.md)** - System monitoring

### Additional Resources
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design
- **[SECURITY.md](docs/SECURITY.md)** - Security hardening
- **[BACKUP-RESTORE.md](docs/BACKUP-RESTORE.md)** - Data management

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Ubuntu Server                            │
│                   (t3.large or higher)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Client Pods (K8s) ──[SSL:9093]──> Kafka                       │
│         │                            │                          │
│         │                            ├──> raw.k8s.events        │
│         │                            ├──> raw.k8s.logs          │
│         │                            └──> raw.prom.alerts       │
│         │                                  │                    │
│         │                            ┌─────▼─────┐             │
│         │                            │   Alerts  │             │
│         │                            │ Enricher  │             │
│         │                            └─────┬─────┘             │
│         │                                  │                    │
│         │                            events.normalized          │
│         │                                  │                    │
│         │                            ┌─────▼─────┐             │
│         │                            │   Graph   │             │
│         │                            │  Builder  │             │
│         │                            └─────┬─────┘             │
│         │                                  │                    │
│         │                            ┌─────▼─────┐             │
│         │                            │   Neo4j   │             │
│         │                            │ (Graph DB)│             │
│         │                            └─────┬─────┘             │
│         │                                  │                    │
│         └────────[HTTP:8080]───────> KG API (RCA queries)      │
│                                                                 │
│  Monitoring:                                                    │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│  │ Prometheus │  │  Grafana   │  │  Kafka UI  │               │
│  └────────────┘  └────────────┘  └────────────┘               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Support & Next Steps

### Getting Started
1. Read the **[STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md)**
2. Provision your Ubuntu server
3. Run the setup scripts
4. Deploy client agents using the Helm chart

### Need Help?
- Check **[TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** for common issues
- Review logs: `docker compose logs -f [service-name]`
- Check service health: `./scripts/test-services.sh`

### Production Readiness Checklist
- [ ] SSL certificates configured
- [ ] Firewall rules configured
- [ ] Backups automated
- [ ] Monitoring dashboards configured
- [ ] Alerting configured
- [ ] Documentation reviewed
- [ ] Client agents tested
- [ ] Performance tested

---

**Ready to deploy?** → Go to [STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md)
