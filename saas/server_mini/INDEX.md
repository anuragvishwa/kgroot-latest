# Server Mini - Complete Documentation Index

Quick navigation for the EC2 single-server deployment.

## 📚 Documentation

### Getting Started (Read These First)

1. **[QUICK_START.md](QUICK_START.md)** - 5-minute deployment guide
   - TL;DR version
   - Essential commands only
   - Fast path to running system

2. **[README.md](README.md)** - Overview and architecture
   - What you're deploying
   - Component descriptions
   - API endpoints
   - Basic operations

3. **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Complete step-by-step instructions
   - Prerequisites
   - Two deployment options (Terraform + Manual)
   - Post-deployment configuration
   - Client onboarding
   - Operations procedures
   - Troubleshooting
   - Security checklist

### Decision Making

4. **[COMPARISON.md](COMPARISON.md)** - EC2 vs K8s detailed comparison
   - When to use each
   - Cost analysis
   - Scalability comparison
   - Migration triggers
   - Decision matrix

5. **[SUMMARY.md](SUMMARY.md)** - What was created and why
   - Files overview
   - Key features
   - Use cases
   - Success criteria

6. **[../DEPLOYMENT_OPTIONS.md](../DEPLOYMENT_OPTIONS.md)** - High-level deployment strategy
   - Decision tree
   - Deployment paths
   - Recommendations by company stage

## 📁 Files

### Configuration Files

- **[docker-compose.yml](docker-compose.yml)** - Complete stack definition
  - All services configured
  - Health checks
  - Volumes
  - Networking

- **[.env.example](.env.example)** - Environment template
  - Domain configuration
  - Passwords
  - Kafka settings

### Scripts

- **[setup.sh](setup.sh)** - Automated setup script
  - Installs Docker
  - Creates directories
  - Generates configs
  - Sets up systemd service

- **[scripts/kafka-init.sh](scripts/kafka-init.sh)** - Kafka topic creation
  - Creates all required topics
  - Sets retention policies
  - Configures compression

### Infrastructure as Code

- **[terraform/main.tf](terraform/main.tf)** - EC2 infrastructure
  - Instance configuration
  - Security groups
  - EBS volumes
  - Elastic IP

- **[terraform/variables.tf](terraform/variables.tf)** - Configurable parameters
  - Instance type
  - Domain name
  - SSH key
  - AWS region

- **[terraform/outputs.tf](terraform/outputs.tf)** - Deployment information
  - Public IP
  - SSH command
  - Next steps guide

- **[terraform/user-data.sh](terraform/user-data.sh)** - Bootstrap script
  - System updates
  - Docker installation
  - Volume mounting

### Service Configurations

- **[config/prometheus/prometheus.yml](config/prometheus/prometheus.yml)** - Metrics collection
  - Scrape configs
  - Targets

- **[config/nginx/nginx.conf](config/nginx/nginx.conf)** - Reverse proxy
  - SSL termination
  - HTTP → HTTPS redirect
  - Proxy settings

## 🚀 Quick Navigation by Task

### I want to...

#### Deploy the Server
1. Read [QUICK_START.md](QUICK_START.md) for fastest path
2. Or [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed instructions
3. Use Terraform: `cd terraform && terraform apply`
4. Or run: `./setup.sh`

#### Understand the Architecture
1. Read [README.md](README.md) - Architecture section
2. Check [../DEPLOYMENT_OPTIONS.md](../DEPLOYMENT_OPTIONS.md) for context

#### Decide Between EC2 and K8s
1. Read [COMPARISON.md](COMPARISON.md)
2. Check [../DEPLOYMENT_OPTIONS.md](../DEPLOYMENT_OPTIONS.md)
3. Use the decision matrix

#### Configure the Environment
1. Copy [.env.example](.env.example) to `.env`
2. Edit domain and email
3. Save the auto-generated passwords

#### Start Services
```bash
docker-compose up -d
./health-check.sh
```

#### Monitor Services
```bash
# SSH tunnel
ssh -L 3000:localhost:3000 -L 7474:localhost:7474 ubuntu@<IP>

# Open in browser
# Grafana: http://localhost:3000
# Neo4j: http://localhost:7474
```

#### Troubleshoot Issues
1. Check [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Troubleshooting section
2. Run `docker-compose logs -f`
3. Check `./health-check.sh`

#### Backup Data
```bash
./backup.sh
```

#### Scale Up
1. Read [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Scaling section
2. Resize instance via AWS
3. Or migrate to K8s ([COMPARISON.md](COMPARISON.md))

#### Onboard a Client
1. Read [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Client Onboarding section
2. Register via API
3. Deploy client agent with provided credentials

#### Migrate to Kubernetes
1. Read [COMPARISON.md](COMPARISON.md) - Migration section
2. Check [../DEPLOYMENT_OPTIONS.md](../DEPLOYMENT_OPTIONS.md) - Migration process
3. See [../server/](../server/) for K8s deployment

## 📋 Cheat Sheet

### Common Commands

```bash
# Check health
./health-check.sh

# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs (all)
docker-compose logs -f

# View logs (specific service)
docker-compose logs -f graph-builder

# Restart service
docker-compose restart <service-name>

# Backup
./backup.sh

# Update services
docker-compose pull
docker-compose up -d

# Check disk space
df -h

# Check memory
free -h

# Check service status
docker-compose ps
```

### Quick Troubleshooting

```bash
# Service won't start
docker-compose logs <service-name>

# Out of memory
free -h
docker stats

# Out of disk
df -h
docker system prune -a

# SSL certificate issues
sudo certbot certificates
sudo certbot renew

# Kafka issues
docker-compose exec kafka kafka-topics.sh --list --bootstrap-server localhost:9092
```

## 🎯 Documentation Matrix

|  | Quick | Detailed | Decision |
|---|-------|----------|----------|
| **Setup** | [QUICK_START](QUICK_START.md) | [DEPLOYMENT_GUIDE](DEPLOYMENT_GUIDE.md) | [DEPLOYMENT_OPTIONS](../DEPLOYMENT_OPTIONS.md) |
| **Architecture** | [README](README.md) | [DEPLOYMENT_GUIDE](DEPLOYMENT_GUIDE.md) | - |
| **Operations** | [README](README.md) | [DEPLOYMENT_GUIDE](DEPLOYMENT_GUIDE.md) | - |
| **Scaling** | [README](README.md) | [COMPARISON](COMPARISON.md) | [DEPLOYMENT_OPTIONS](../DEPLOYMENT_OPTIONS.md) |
| **Migration** | [COMPARISON](COMPARISON.md) | [DEPLOYMENT_OPTIONS](../DEPLOYMENT_OPTIONS.md) | [COMPARISON](COMPARISON.md) |

## 🔗 External References

### AWS Documentation
- [EC2 User Guide](https://docs.aws.amazon.com/ec2/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)

### Service Documentation
- [Docker Compose](https://docs.docker.com/compose/)
- [Neo4j](https://neo4j.com/docs/)
- [Kafka](https://kafka.apache.org/documentation/)
- [Nginx](https://nginx.org/en/docs/)
- [Let's Encrypt](https://letsencrypt.org/docs/)

## 📞 Support

### Self-Service
1. Check this INDEX for relevant documentation
2. Read the troubleshooting section in [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
3. Review logs: `docker-compose logs`

### Need Help?
- **Quick Questions**: See [QUICK_START.md](QUICK_START.md)
- **Deployment Issues**: See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **Architecture Questions**: See [README.md](README.md)
- **Decision Help**: See [COMPARISON.md](COMPARISON.md) or [DEPLOYMENT_OPTIONS.md](../DEPLOYMENT_OPTIONS.md)

## 🎓 Learning Path

### New to Docker?
1. Install Docker Desktop
2. Read [docker-compose.yml](docker-compose.yml) to understand services
3. Try locally first: `docker-compose up`

### New to AWS?
1. Read [terraform/main.tf](terraform/main.tf) to understand infrastructure
2. Start with AWS Console (manual deployment)
3. Graduate to Terraform when comfortable

### New to SaaS?
1. Read [README.md](README.md) for architecture
2. Understand multi-tenancy model
3. Review client onboarding flow in [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

## ✅ Documentation Completeness

This deployment package includes:

- [x] Quick start guide (5 minutes)
- [x] Detailed deployment guide (step-by-step)
- [x] Architecture overview
- [x] Decision framework (EC2 vs K8s)
- [x] Infrastructure as code (Terraform)
- [x] Automated setup script
- [x] Configuration templates
- [x] Operations procedures
- [x] Troubleshooting guide
- [x] Security checklist
- [x] Migration path
- [x] Cost analysis
- [x] Cheat sheet
- [x] This index document

**Documentation Status**: ✅ Complete

## 📈 What's Next?

After deployment:
1. ✅ Server running → Read [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Operations
2. ✅ First client → See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Client Onboarding
3. ✅ 10+ clients → Consider [COMPARISON.md](COMPARISON.md) - Migration to K8s
4. ✅ Enterprise customers → See [../server/](../server/) for K8s deployment

---

**Last Updated**: 2025-01-10
**Version**: 1.0.0
**Status**: Production Ready
