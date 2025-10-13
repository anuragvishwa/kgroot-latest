# 🚀 START HERE - Complete Mini Server Production Setup

**You now have everything you need to deploy KG RCA on Ubuntu!**

## 📁 What You Have

```
mini-server-prod/
├── README.md                           ⭐ Overview and introduction
├── QUICK-START.md                      ⭐ Get running in 15 minutes
├── STEP-BY-STEP-GUIDE.md              ⭐ Detailed deployment walkthrough
├── DEPLOYMENT-CHECKLIST.md             ✓  Checklist for deployment
├── docker-compose.yml                  🐳 Main service definitions
├── docker-compose.ssl.yml              🔒 SSL configuration overlay
├── .env.example                        ⚙️  Environment variables template
│
├── scripts/                            🔧 Automation scripts
│   ├── setup-ubuntu.sh                 ⭐ Initial server setup
│   ├── setup-ssl.sh                    🔒 Generate SSL certificates
│   ├── create-topics.sh                📊 Create Kafka topics
│   ├── test-services.sh                ✓  Health check all services
│   └── backup.sh                       💾 Backup data
│
├── config/                             ⚙️  Service configurations
│   ├── prometheus.yml                  📈 Metrics collection
│   └── grafana/
│       ├── datasources/                📊 Grafana data sources
│       └── dashboards/                 📊 Dashboard configs
│
├── ssl/                                🔒 SSL certificates (generated)
│   └── .gitkeep
│
└── docs/                               📚 Comprehensive documentation
    ├── ARCHITECTURE.md                 🏗️  System architecture
    ├── TROUBLESHOOTING.md              🔍 Problem solving
    ├── MONITORING.md                   📊 Monitoring guide
    ├── SECURITY.md                     🔒 Security best practices
    └── BACKUP-RESTORE.md               💾 Backup and recovery
```

## 🎯 Your Next Steps

### For First-Time Deployment

1. **Read this** → [QUICK-START.md](QUICK-START.md) (15 minutes)
2. **Or detailed** → [STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md) (complete guide)
3. **Use checklist** → [DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md) (track progress)

### Choose Your Path

#### 🏃 Fast Track (15 minutes)
Perfect for testing, development, or quick POC.

```bash
cd mini-server-prod
sudo ./scripts/setup-ubuntu.sh
cp .env.example .env
nano .env  # Set passwords
docker compose up -d
./scripts/create-topics.sh
./scripts/test-services.sh
```

→ Follow [QUICK-START.md](QUICK-START.md)

#### 🚶 Production Track (2 hours)
Complete production deployment with SSL, monitoring, backups.

1. Server provisioning
2. Initial setup
3. SSL configuration
4. Service deployment
5. Client integration
6. Monitoring setup
7. Backup automation

→ Follow [STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md)

## 📖 Documentation Map

### Essential Reading (Start Here)
- [README.md](README.md) - What this is and what you need
- [QUICK-START.md](QUICK-START.md) - Get running fast
- [STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md) - Complete deployment guide

### Reference Documentation
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - How everything works
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - Fix common issues
- [MONITORING.md](docs/MONITORING.md) - Monitor your system
- [SECURITY.md](docs/SECURITY.md) - Secure your deployment
- [BACKUP-RESTORE.md](docs/BACKUP-RESTORE.md) - Protect your data

### Operational Guides
- [DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md) - Track deployment progress
- Scripts in `scripts/` directory - Automation tools

## 🎓 Learning Path

### Beginner (I'm new to this)
1. Read [README.md](README.md)
2. Follow [QUICK-START.md](QUICK-START.md) on a test server
3. Explore Kafka UI and Neo4j Browser
4. Deploy a test client

### Intermediate (I know Docker/Kubernetes)
1. Skim [README.md](README.md)
2. Review [ARCHITECTURE.md](docs/ARCHITECTURE.md)
3. Follow [STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md)
4. Configure SSL
5. Set up monitoring

### Advanced (I want production-ready)
1. Read [ARCHITECTURE.md](docs/ARCHITECTURE.md)
2. Review [SECURITY.md](docs/SECURITY.md)
3. Follow [STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md)
4. Configure SSL with mutual TLS
5. Set up monitoring and alerting
6. Configure automated backups
7. Perform disaster recovery test
8. Use [DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md)

## 🛠️ Quick Commands Reference

### Deployment
```bash
# Initial setup
sudo ./scripts/setup-ubuntu.sh

# Deploy services
docker compose up -d

# Deploy with SSL
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d

# Create topics
./scripts/create-topics.sh
```

### Operations
```bash
# Health check
./scripts/test-services.sh

# View logs
docker compose logs -f

# Restart service
docker compose restart <service>

# Backup
./scripts/backup.sh

# Update
docker compose pull && docker compose up -d
```

### Monitoring
```bash
# Check services
docker compose ps

# Check resources
docker stats

# Check specific service
docker logs <container-name> -f
```

## 🔑 Key Configuration Files

### Must Edit Before Deployment

**`.env`** (Copy from `.env.example`)
- NEO4J_PASSWORD
- KG_API_KEY
- GRAFANA_PASSWORD
- KAFKA_ADVERTISED_HOST (for SSL)

### May Edit for Customization

**`docker-compose.yml`**
- Memory limits
- Port mappings
- Volume locations

**`config/prometheus.yml`**
- Scrape intervals
- Add custom targets

## 🌟 Services You'll Deploy

| Service | Port | What It Does |
|---------|------|--------------|
| **Kafka** | 9092, 9093 | Message broker for events |
| **Zookeeper** | 2181 | Kafka coordination |
| **Neo4j** | 7474, 7687 | Graph database |
| **Graph Builder** | 9090 | Processes events into graph |
| **KG API** | 8080 | REST API for RCA |
| **Alerts Enricher** | - | Enriches events with context |
| **Prometheus** | 9091 | Metrics collection |
| **Grafana** | 3000 | Dashboards |
| **Kafka UI** | 7777 | Kafka management |

## 🎯 Success Criteria

Your deployment is successful when:

✓ All services showing "Up (healthy)"
```bash
docker compose ps
```

✓ Health check passes
```bash
./scripts/test-services.sh
```

✓ All Kafka topics created
```bash
docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list
```

✓ Web UIs accessible
- Kafka UI: http://SERVER:7777
- Neo4j: http://SERVER:7474
- Grafana: http://SERVER:3000

✓ Client agents can connect and send data

## 🆘 Getting Help

### Self-Service
1. Check [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
2. View logs: `docker compose logs -f`
3. Run health check: `./scripts/test-services.sh`

### Common Issues
- **Port not accessible?** Check firewall: `sudo ufw status`
- **Service not starting?** Check logs: `docker logs <container>`
- **Out of memory?** Check: `docker stats`
- **SSL not working?** Verify certificates: `ls -la ssl/`

### Documentation Index
- Setup issues → [STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md)
- Service errors → [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- Performance → [MONITORING.md](docs/MONITORING.md)
- Security → [SECURITY.md](docs/SECURITY.md)
- Backups → [BACKUP-RESTORE.md](docs/BACKUP-RESTORE.md)

## 📝 Before You Start Checklist

- [ ] I have Ubuntu server (20.04/22.04/24.04)
- [ ] Server has 8GB RAM, 4 vCPUs minimum
- [ ] I have SSH access with sudo
- [ ] I have this repository on the server
- [ ] I have 30 minutes for deployment
- [ ] I have passwords ready for Neo4j and Grafana

**Ready?** → Go to [QUICK-START.md](QUICK-START.md) or [STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md)

## 🎉 What You're Building

```
┌──────────────────────────────────────────────────────────┐
│               Your Client Clusters (K8s)                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Cluster1 │  │ Cluster2 │  │ Cluster3 │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
└───────┼─────────────┼─────────────┼──────────────────────┘
        │             │             │
        │ Events/Logs │             │ SSL (9093)
        └─────────────┴─────────────┘
                      │
┌─────────────────────┼─────────────────────────────────────┐
│            Your KG RCA Server (Ubuntu)                    │
│                     │                                     │
│              ┌──────▼────────┐                            │
│              │     Kafka     │                            │
│              └──┬────┬────┬──┘                            │
│                 │    │    │                               │
│      ┌──────────┘    │    └──────────┐                   │
│      │               │               │                   │
│ ┌────▼─────┐   ┌────▼─────┐   ┌─────▼────┐              │
│ │ Enricher │   │ Builder  │   │ KG API   │              │
│ └──────────┘   └────┬─────┘   └─────┬────┘              │
│                     │               │                   │
│               ┌─────▼─────────┐    │                   │
│               │    Neo4j      │◄───┘                   │
│               │ (Graph DB)    │                         │
│               └───────────────┘                         │
│                                                          │
│  📊 Grafana  📈 Prometheus  🔍 Kafka UI                 │
└──────────────────────────────────────────────────────────┘
```

A complete Root Cause Analysis platform that:
- Collects events, logs, and alerts from your K8s clusters
- Builds a knowledge graph of relationships
- Automatically identifies root causes
- Provides APIs for querying and analysis

## 💡 Tips for Success

1. **Start simple**: Use [QUICK-START.md](QUICK-START.md) first
2. **Test locally**: Try on a test server before production
3. **Use checklist**: [DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md) ensures nothing is missed
4. **Read logs**: When in doubt, check `docker compose logs -f`
5. **Monitor**: Set up Grafana dashboards from day one
6. **Backup early**: Run `./scripts/backup.sh` right away
7. **Document**: Keep notes on what you change

## 🚀 Ready to Deploy?

**Choose your starting point:**

- 🏃 **Quick**: [QUICK-START.md](QUICK-START.md) - 15 minutes
- 🚶 **Complete**: [STEP-BY-STEP-GUIDE.md](STEP-BY-STEP-GUIDE.md) - 2 hours
- ✓ **Checklist**: [DEPLOYMENT-CHECKLIST.md](DEPLOYMENT-CHECKLIST.md) - Track progress

**Have questions?**
- Check [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) first
- Review the appropriate doc from the list above
- All scripts have `--help` (most of them 😊)

---

**Good luck with your deployment! 🎉**

*Everything you need is in this folder. Follow the guides, use the scripts, and you'll have a production-ready RCA platform in no time.*
