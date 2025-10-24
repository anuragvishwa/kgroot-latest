# KG RCA Mini Server - Deployment Checklist

Use this checklist to ensure you complete all steps for a successful deployment.

## Pre-Deployment

### Server Provisioning
- [ ] Ubuntu server provisioned (20.04/22.04/24.04 LTS)
- [ ] Minimum 8GB RAM, 4 vCPUs, 100GB disk
- [ ] Public IP address assigned
- [ ] SSH access configured
- [ ] DNS name configured (optional)

### Network Configuration
- [ ] Firewall rules configured in cloud provider
- [ ] Port 22 (SSH) open to your IP
- [ ] Port 9093 (Kafka SSL) open to client IPs
- [ ] Other ports restricted or closed

### Local Preparation
- [ ] SSH key pair generated
- [ ] Git repository cloned locally
- [ ] AWS CLI installed (if using S3)

## Initial Server Setup

### System Setup
- [ ] Connected to server via SSH
- [ ] System packages updated (`sudo apt update && upgrade`)
- [ ] Setup script executed (`sudo ./scripts/setup-ubuntu.sh`)
- [ ] Docker installed and running
- [ ] Docker Compose installed
- [ ] User added to docker group (if applicable)
- [ ] UFW firewall configured (optional)

### Repository Setup
- [ ] Code repository cloned or files uploaded
- [ ] Navigated to `mini-server-prod` directory
- [ ] Scripts have execute permissions (`chmod +x scripts/*.sh`)

## Configuration

### Environment Configuration
- [ ] `.env` file created from `.env.example`
- [ ] Neo4j password set (strong password)
- [ ] Grafana password set (strong password)
- [ ] KG API key generated and set
- [ ] Server hostname/IP set (for SSL)
- [ ] All passwords documented securely

### File Verification
- [ ] `docker-compose.yml` reviewed
- [ ] Configuration files in `config/` reviewed
- [ ] Service ports verified
- [ ] Volume mounts verified

## Deployment

### Service Deployment
- [ ] Services started (`docker compose up -d`)
- [ ] Waited for services to be healthy (2-5 minutes)
- [ ] All containers running (`docker compose ps`)
- [ ] No restart loops observed

### Kafka Topics
- [ ] Topics created (`./scripts/create-topics.sh`)
- [ ] Topic list verified
- [ ] Topic configurations verified

### Health Checks
- [ ] Health check script executed (`./scripts/test-services.sh`)
- [ ] All services reporting healthy
- [ ] Ports accessible
- [ ] HTTP endpoints responding

## SSL Setup (Optional but Recommended)

### Certificate Generation
- [ ] SSL script executed (`./scripts/setup-ssl.sh`)
- [ ] Certificates generated in `ssl/` directory
- [ ] `.env` file updated with SSL settings
- [ ] Passwords documented

### SSL Deployment
- [ ] Services restarted with SSL config
- [ ] `docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d`
- [ ] Port 9093 accessible
- [ ] SSL connection tested from external client

### Certificate Distribution
- [ ] CA certificate copied (`ssl/ca-cert`)
- [ ] CA certificate provided to client teams
- [ ] Client certificates generated (if mutual TLS)

## Testing

### Service Tests
- [ ] Kafka UI accessible (`http://SERVER:7777`)
- [ ] Neo4j Browser accessible (`http://SERVER:7474`)
- [ ] Grafana accessible (`http://SERVER:3000`)
- [ ] KG API health check (`curl http://SERVER:8080/healthz`)
- [ ] Prometheus accessible (`http://SERVER:9091`)

### Data Flow Tests
- [ ] Test event sent to Kafka
- [ ] Event consumed by Graph Builder
- [ ] Data visible in Neo4j
- [ ] No errors in logs

### Integration Tests
- [ ] Client agent deployed to test cluster
- [ ] Events flowing from client to server
- [ ] Data appearing in Neo4j
- [ ] RCA query tested via API

## Monitoring Setup

### Dashboard Configuration
- [ ] Grafana login successful
- [ ] Prometheus datasource configured
- [ ] Neo4j datasource configured
- [ ] Dashboards imported or created
- [ ] Dashboards displaying data

### Alert Configuration
- [ ] Alert rules created in Prometheus
- [ ] Grafana notification channels configured
- [ ] Test alerts sent and received
- [ ] Alert thresholds tuned

## Backup Setup

### Backup Configuration
- [ ] Backup script tested (`./scripts/backup.sh`)
- [ ] Backup created successfully
- [ ] Backup size reasonable
- [ ] Backup contents verified

### Automated Backups
- [ ] Cron job created for daily backups
- [ ] Cron job tested
- [ ] Backup rotation configured
- [ ] Old backups cleaned up

### Cloud Backup (Optional)
- [ ] AWS CLI / gsutil installed
- [ ] Cloud storage bucket created
- [ ] Backup uploaded to cloud
- [ ] Versioning enabled
- [ ] Lifecycle policy configured

## Security Hardening

### Access Control
- [ ] Root login disabled
- [ ] Password authentication disabled
- [ ] SSH keys only
- [ ] Fail2Ban installed and configured
- [ ] Unnecessary services disabled

### Network Security
- [ ] UFW firewall active
- [ ] Only necessary ports open
- [ ] Cloud firewall rules configured
- [ ] Rate limiting configured (if applicable)

### Application Security
- [ ] Default passwords changed
- [ ] Strong passwords used
- [ ] API authentication enabled
- [ ] Secrets not in version control
- [ ] `.env` file secured (600 permissions)

### Monitoring
- [ ] SSH login alerts configured
- [ ] Failed login monitoring active
- [ ] Security logs reviewed
- [ ] Vulnerability scanning scheduled

## Documentation

### Internal Documentation
- [ ] Server IP/hostname documented
- [ ] Credentials stored securely
- [ ] Network diagram created
- [ ] Deployment notes documented
- [ ] Runbook created

### Client Documentation
- [ ] Connection details provided
- [ ] SSL certificate provided (if needed)
- [ ] API documentation shared
- [ ] Example configurations provided
- [ ] Support contacts shared

## Client Integration

### Client Deployment
- [ ] Helm chart values configured
- [ ] Client agents deployed
- [ ] Pods running successfully
- [ ] Logs showing successful connection

### Data Verification
- [ ] Events appearing in Kafka UI
- [ ] Events processed by Graph Builder
- [ ] Nodes created in Neo4j
- [ ] RCA queries returning results

### Performance Testing
- [ ] Event throughput measured
- [ ] Latency measured
- [ ] Resource usage monitored
- [ ] Bottlenecks identified

## Post-Deployment

### Monitoring
- [ ] Services monitored for 24 hours
- [ ] No critical errors
- [ ] Performance acceptable
- [ ] Alerts working

### Optimization
- [ ] Resource usage optimized
- [ ] Slow queries identified and fixed
- [ ] Memory settings tuned
- [ ] Connection pools sized

### Maintenance Planning
- [ ] Update schedule defined
- [ ] Backup schedule confirmed
- [ ] On-call rotation established
- [ ] Escalation procedures defined

## Sign-Off

### Technical Sign-Off
- [ ] All services operational
- [ ] All tests passed
- [ ] No critical issues
- [ ] Performance meets requirements

Signed: _________________ Date: _________

### Product/Business Sign-Off
- [ ] Meets business requirements
- [ ] Documentation complete
- [ ] Team trained
- [ ] Ready for production

Signed: _________________ Date: _________

---

## Quick Reference

### Essential Commands

```bash
# Check service status
docker compose ps

# View logs
docker compose logs -f

# Restart service
docker compose restart <service>

# Run health check
./scripts/test-services.sh

# Create backup
./scripts/backup.sh

# Update services
docker compose pull && docker compose up -d
```

### Essential URLs

- Kafka UI: http://SERVER:7777
- Neo4j: http://SERVER:7474
- Grafana: http://SERVER:3000
- KG API: http://SERVER:8080
- Prometheus: http://SERVER:9091

### Emergency Contacts

- Primary: _________________
- Secondary: _________________
- On-Call: _________________

---

## Notes

Add any deployment-specific notes here:

_____________________________________________________________________

_____________________________________________________________________

_____________________________________________________________________
