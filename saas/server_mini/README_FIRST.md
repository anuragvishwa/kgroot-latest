# 👋 Start Here!

Welcome to the KG RCA EC2 Single-Server Deployment!

## 🚀 Fastest Path to Running System

```bash
# 1. SSH to your EC2 instance (or launch one with Terraform)
ssh ubuntu@<your-ec2-ip>

# 2. Clone repository
git clone <your-repo>
cd kg-rca/saas/server_mini

# 3. Run automated setup
./setup.sh

# 4. Configure environment
nano .env
# Set: DOMAIN=api.yourdomain.com, EMAIL=your@email.com

# 5. Start everything
docker-compose up -d

# 6. Setup SSL
sudo certbot --nginx -d api.yourdomain.com

# 7. Verify
./health-check.sh

# Done! 🎉
```

**Time**: ~30 minutes total

## 📚 Documentation

Not sure where to start? Follow this order:

1. **[INDEX.md](INDEX.md)** ← Complete navigation guide
2. **[QUICK_START.md](QUICK_START.md)** ← 5-minute version
3. **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** ← Full step-by-step
4. **[COMPARISON.md](COMPARISON.md)** ← EC2 vs K8s decision

## 🤔 Common Questions

### Should I use EC2 or Kubernetes?

**Use EC2 (this deployment) if:**
- ✅ MVP/pilot phase
- ✅ < 15 clients
- ✅ Budget < $200/month
- ✅ Want to deploy in 30 minutes

**Use Kubernetes if:**
- ✅ Production scale (20+ clients)
- ✅ Need 99.9%+ uptime
- ✅ Have K8s expertise
- ✅ Budget > $300/month

See [COMPARISON.md](COMPARISON.md) for detailed analysis.

### What will this cost?

- **t3.large**: ~$77/month (5-10 clients)
- **t3.xlarge**: ~$137/month (10-15 clients)

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for breakdown.

### Can I migrate to Kubernetes later?

Yes! Easy migration path documented in [COMPARISON.md](COMPARISON.md).

## 🎯 What You Get

This deploys the complete KG RCA stack on a single EC2 instance:

- ✅ Kafka + Zookeeper (event streaming)
- ✅ Neo4j (knowledge graph database)
- ✅ Graph Builder (RCA engine)
- ✅ Alerts Enricher (alert processing)
- ✅ KG API (REST API for clients)
- ✅ Prometheus + Grafana (monitoring)
- ✅ Nginx with SSL (secure access)
- ✅ Health checks & backups

## 🆘 Need Help?

1. **Quick questions**: See [QUICK_START.md](QUICK_START.md)
2. **Deployment issues**: See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Troubleshooting
3. **Decisions**: See [COMPARISON.md](COMPARISON.md)
4. **Navigation**: See [INDEX.md](INDEX.md)

## 📁 What's in This Folder?

```
server_mini/
├── README_FIRST.md          ← You are here!
├── INDEX.md                 ← Complete navigation guide
├── QUICK_START.md           ← 5-minute deployment
├── DEPLOYMENT_GUIDE.md      ← Detailed instructions
├── COMPARISON.md            ← EC2 vs K8s comparison
├── docker-compose.yml       ← Complete stack definition
├── setup.sh                 ← Automated setup script
├── terraform/               ← Infrastructure as code
└── config/                  ← Service configurations
```

## ✅ Pre-flight Checklist

Before deploying:

- [ ] AWS account with EC2 access
- [ ] Domain name (e.g., api.yourdomain.com)
- [ ] SSH key pair in AWS
- [ ] Basic Docker knowledge (helpful but not required)

## 🚀 Ready to Deploy?

### Option 1: Terraform (Recommended)
```bash
cd terraform
terraform init
terraform apply
# Follow output for next steps
```

### Option 2: Manual
```bash
# Launch EC2 via AWS Console
# SSH to instance
./setup.sh
# Follow prompts
```

**Next Step**: See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for complete instructions.

---

**Questions?** Start with [INDEX.md](INDEX.md) for navigation help.

**Ready to go?** Jump to [QUICK_START.md](QUICK_START.md) for fastest path.

**Want details?** Read [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for everything.
