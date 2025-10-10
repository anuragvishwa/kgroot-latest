# KG RCA SaaS Platform Documentation

**Version**: 1.0.0
**Last Updated**: 2025-01-09
**Total Pages**: 6,122 lines of comprehensive documentation

---

## Quick Start

New to KG RCA? Start here:

1. **First Time Setup** - Read [00-ARCHITECTURE.md](00-ARCHITECTURE.md) to understand the system
2. **Deploy Server** - Follow [01-SERVER-DEPLOYMENT.md](01-SERVER-DEPLOYMENT.md) to set up your infrastructure
3. **Onboard Client** - Use [02-CLIENT-ONBOARDING.md](02-CLIENT-ONBOARDING.md) to add your first customer
4. **Daily Operations** - Reference [03-OPERATIONS.md](03-OPERATIONS.md) for day-to-day tasks
5. **Troubleshooting** - Consult [04-TROUBLESHOOTING.md](04-TROUBLESHOOTING.md) when issues arise

**Estimated Setup Time**: 1-2 hours for complete deployment

---

## Documentation Structure

### [00-ARCHITECTURE.md](00-ARCHITECTURE.md) (1,540 lines)

**Complete system architecture and design documentation**

Topics covered:
- Multi-tenant architecture (database-per-client, topic-per-client)
- Component descriptions (Neo4j, Kafka, Graph Builder, KG API, etc.)
- Data flow diagrams and processing pipeline
- Security architecture (TLS, SASL, API keys, network policies)
- Scalability design (horizontal and vertical scaling)
- High availability setup (3-node Neo4j, 5-broker Kafka)
- Network architecture and service types
- Storage architecture and capacity planning
- Monitoring and observability stack

**When to read**:
- Before deployment to understand the system
- During architecture reviews
- When planning infrastructure scaling
- For security audits

**Key sections**:
- Multi-Tenant Architecture (pages 1-4)
- Component Descriptions (pages 5-10)
- Data Flow (pages 11-14)
- Security Architecture (pages 15-18)
- Scalability Design (pages 19-22)

---

### [01-SERVER-DEPLOYMENT.md](01-SERVER-DEPLOYMENT.md) (1,132 lines)

**Step-by-step guide for deploying the server infrastructure**

Topics covered:
- Prerequisites (Kubernetes cluster, Helm, domain, Stripe)
- Pre-deployment checklist
- Installation steps with commands
- Configuration examples (production-values.yaml)
- Post-deployment verification
- DNS configuration
- SSL/TLS setup with cert-manager
- Monitoring setup with Grafana
- Backup configuration
- Common troubleshooting scenarios

**When to read**:
- First time setting up the server
- When upgrading infrastructure
- For disaster recovery procedures
- Before maintenance windows

**Key sections**:
- Prerequisites (pages 1-3)
- Installation Steps (pages 4-8)
- Post-Deployment Verification (pages 9-12)
- DNS & TLS Setup (pages 13-15)

**Expected Duration**: 30-45 minutes

---

### [02-CLIENT-ONBOARDING.md](02-CLIENT-ONBOARDING.md) (1,058 lines)

**Complete guide for onboarding new clients to the platform**

Topics covered:
- Server-side setup (creating client records, generating credentials)
- Neo4j database creation
- Kafka topic and ACL configuration
- Client installation package generation
- Client-side installation steps
- Verification procedures
- Testing data flow
- Client offboarding process

**When to read**:
- Adding a new client
- Troubleshooting client connectivity
- Upgrading or suspending client accounts
- Offboarding clients

**Key sections**:
- Server-Side Setup (pages 1-5)
- Client-Side Installation (pages 6-8)
- Verification (pages 9-11)
- Testing Data Flow (pages 12-14)

**Expected Duration**: 20-30 minutes per client

---

### [03-OPERATIONS.md](03-OPERATIONS.md) (1,022 lines)

**Day-to-day operations guide for running the platform**

Topics covered:
- Daily health checks and monitoring
- Grafana dashboards and alerts
- Scaling procedures (horizontal and vertical)
- Backup and restore procedures
- Client management (add, upgrade, suspend, delete)
- Performance tuning (Neo4j, Kafka, Graph Builder)
- Cost optimization strategies
- Incident response procedures
- Maintenance windows
- Capacity planning

**When to read**:
- Daily operations
- Performance issues
- Scaling decisions
- Cost optimization
- Incident response

**Key sections**:
- Daily Operations (pages 1-3)
- Monitoring & Dashboards (pages 4-7)
- Scaling Procedures (pages 8-11)
- Backup & Restore (pages 12-15)
- Client Management (pages 16-18)

**Operational Checklists**:
- Daily checklist
- Weekly checklist
- Monthly checklist
- Quarterly checklist

---

### [04-TROUBLESHOOTING.md](04-TROUBLESHOOTING.md) (1,370 lines)

**Comprehensive troubleshooting guide for common and complex issues**

Topics covered:
- Diagnostic tools and log collection
- Server issues (pods not starting, Neo4j cluster, Kafka brokers)
- Client issues (agents not connecting, no data flow)
- RCA quality issues (no links, low accuracy)
- Performance issues (high latency, memory usage)
- Network and connectivity problems
- Data issues (missing data, duplicates)
- Storage issues (disk space)
- Security issues (unauthorized access)
- Emergency procedures

**When to read**:
- When things go wrong
- During incidents
- For performance debugging
- After monitoring alerts

**Key sections**:
- Diagnostic Tools (pages 1-2)
- Server Issues (pages 3-10)
- Client Issues (pages 11-13)
- RCA Quality Issues (pages 14-16)
- Performance Issues (pages 17-20)
- Emergency Procedures (pages 21-22)

**Issue Coverage**:
- 30+ common issues with solutions
- 100+ diagnostic commands
- Emergency recovery procedures

---

## How to Use This Documentation

### For First-Time Users

```
1. Read: 00-ARCHITECTURE.md (30 minutes)
   └─> Understand the multi-tenant design

2. Follow: 01-SERVER-DEPLOYMENT.md (45 minutes)
   └─> Deploy your infrastructure

3. Execute: 02-CLIENT-ONBOARDING.md (30 minutes)
   └─> Onboard your first client

4. Bookmark: 03-OPERATIONS.md & 04-TROUBLESHOOTING.md
   └─> For daily reference
```

### For Operators

**Morning Routine**:
```bash
# Run daily health check
./daily-health-check.sh  # See 03-OPERATIONS.md

# Review Grafana dashboards
open https://grafana.kg-rca.yourcompany.com

# Check for alerts
kubectl get events -n kg-rca-server --sort-by=.lastTimestamp | head -20
```

**Issue Response**:
```
1. Check: 04-TROUBLESHOOTING.md for your specific issue
2. Run: Diagnostic commands from the guide
3. Apply: Suggested solutions
4. Escalate: If issue persists (contact info in each doc)
```

### For Developers

**Code Changes**:
- Review [00-ARCHITECTURE.md](00-ARCHITECTURE.md) for component interactions
- Test changes using procedures in [02-CLIENT-ONBOARDING.md](02-CLIENT-ONBOARDING.md)
- Update documentation if changing architecture

**Performance Tuning**:
- Reference [03-OPERATIONS.md](03-OPERATIONS.md) Performance Tuning section
- Measure impact with Prometheus metrics
- Document changes in this README

---

## Common Tasks Quick Reference

### Deploy Server
```bash
# See: 01-SERVER-DEPLOYMENT.md, Step 4
helm install kg-rca-server ./kg-rca-server \
  --namespace kg-rca-server \
  --create-namespace \
  --values production-values.yaml
```

### Onboard Client
```bash
# See: 02-CLIENT-ONBOARDING.md, Steps 1-7
./generate-api-key.sh client-newco-xyz
kubectl exec neo4j-0 -- cypher-shell "CREATE DATABASE client_newco_xyz_kg;"
# ... (full steps in documentation)
```

### Scale Components
```bash
# See: 03-OPERATIONS.md, Scaling Procedures
kubectl scale deployment graph-builder -n kg-rca-server --replicas=20
kubectl scale deployment kg-api -n kg-rca-server --replicas=30
```

### Backup Database
```bash
# See: 03-OPERATIONS.md, Backup & Restore
kubectl exec neo4j-0 -- neo4j-admin database dump client_abc_kg \
  --to-path=/backups/client_abc_kg.dump
```

### Check System Health
```bash
# See: 03-OPERATIONS.md, Daily Operations
kubectl get pods -n kg-rca-server | grep -v Running
kubectl top pods -n kg-rca-server
```

### Troubleshoot High Lag
```bash
# See: 04-TROUBLESHOOTING.md, Performance Issues
kubectl exec kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe --group kg-builder
```

---

## Document Conventions

### Command Blocks

All commands are provided with:
- **Description**: What the command does
- **Expected output**: What success looks like
- **Common errors**: What might go wrong

Example:
```bash
# Description: Check pod status
kubectl get pods -n kg-rca-server

# Expected output:
# NAME                     READY   STATUS    RESTARTS   AGE
# neo4j-0                  1/1     Running   0          5m

# Common errors:
# - Pods in Pending state: See 04-TROUBLESHOOTING.md, Issue 1
```

### Placeholders

Replace these placeholders with your values:
- `<pod-name>` - Actual pod name (e.g., `neo4j-0`)
- `YOUR_PASSWORD` - Your actual password
- `client-acme-abc123` - Your client ID
- `yourcompany.com` - Your domain

### Severity Indicators

- **Critical** - Immediate action required
- **Warning** - Should be addressed soon
- **Info** - For reference

---

## Documentation Statistics

| Document | Lines | Pages | Word Count | Estimated Read Time |
|----------|-------|-------|------------|---------------------|
| 00-ARCHITECTURE.md | 1,540 | 31 | ~12,000 | 30 minutes |
| 01-SERVER-DEPLOYMENT.md | 1,132 | 23 | ~9,000 | 25 minutes |
| 02-CLIENT-ONBOARDING.md | 1,058 | 21 | ~8,500 | 20 minutes |
| 03-OPERATIONS.md | 1,022 | 20 | ~8,000 | 20 minutes |
| 04-TROUBLESHOOTING.md | 1,370 | 27 | ~11,000 | 30 minutes |
| **Total** | **6,122** | **122** | **~48,500** | **~2 hours** |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0.0 | 2025-01-09 | Initial comprehensive documentation | Platform Team |

---

## Contributing to Documentation

If you find errors or want to improve the documentation:

1. **Small fixes**: Edit the relevant .md file directly
2. **Large changes**: Create a branch and submit for review
3. **New sections**: Follow the existing structure and conventions
4. **Always test**: Verify all commands before documenting

**Documentation Standards**:
- Use clear, concise language
- Include working code examples
- Show expected outputs
- Document common errors
- Update version history

---

## Support

### Getting Help

1. **Search this documentation** - Use Ctrl+F or grep
2. **Check Grafana dashboards** - Visual system status
3. **Review logs** - Use diagnostic scripts
4. **Contact support** - For unresolved issues

### Support Channels

- **Email**: support@kg-rca.yourcompany.com
- **Slack**: #kg-rca-support
- **Emergency**: +1-XXX-XXX-XXXX (24/7 for P0/P1)

### Before Contacting Support

Please have ready:
- Diagnostic logs (`./collect-logs.sh`)
- Error messages
- Steps to reproduce
- Recent changes to system

---

## Feedback

Help us improve this documentation:
- Report errors: docs-feedback@kg-rca.yourcompany.com
- Suggest improvements: Submit issue or PR
- Request new sections: Slack #kg-rca-docs

---

## License

Copyright © 2025 KG RCA Platform
Internal documentation - Confidential

---

**Ready to get started?** Begin with [00-ARCHITECTURE.md](00-ARCHITECTURE.md) to understand the system architecture.

For quick deployment, jump to [01-SERVER-DEPLOYMENT.md](01-SERVER-DEPLOYMENT.md).

**Questions?** Contact the Platform Engineering Team.

---

*Last updated: 2025-01-09*
*Next review: 2025-02-09*
