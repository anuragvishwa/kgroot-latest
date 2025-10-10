# KG RCA Deployment Options

Choose the right deployment strategy for your needs.

## Quick Decision Tree

```
Start Here
    ↓
Are you building an MVP or pilot? (< 10 clients, proving concept)
    ↓
   YES → EC2 (server_mini/)
    │     • 30 minutes setup
    │     • $77/month
    │     • Perfect for getting started
    │
   NO → Do you have 20+ clients or need 99.9% uptime?
    │        ↓
    │       YES → Kubernetes (server/)
    │        │     • Production-grade
    │        │     • Auto-scaling
    │        │     • High availability
    │        │
    │       NO → Still use EC2, plan K8s migration later
    │             • Start simple
    │             • Migrate when ready
```

## Side-by-Side Comparison

| Factor | EC2 (server_mini/) | Kubernetes (server/) |
|--------|-------------------|---------------------|
| **Setup Time** | ⚡ 30 minutes | ⏳ 2-3 hours |
| **Complexity** | 🟢 Simple | 🔴 Complex |
| **Monthly Cost** | 💰 $77 | 💰💰 $216+ |
| **Client Capacity** | 5-10 clients | 50-1000+ clients |
| **High Availability** | ❌ Single server | ✅ Multi-AZ |
| **Auto-Scaling** | ❌ Manual resize | ✅ Automatic |
| **Maintenance** | 🟢 Easy | 🟡 Moderate |
| **Monitoring** | Basic | Advanced |
| **Disaster Recovery** | Manual | Automated |
| **Team Size** | 1-2 engineers | 3+ engineers |
| **K8s Knowledge** | Not required | Required |
| **Learning Curve** | 📗 Low | 📕 High |

## Deployment Paths

### Path 1: Start Small → Scale Up (Recommended for Most)

```
Month 1-3: MVP on EC2
    ↓
    ├─ Validate product-market fit
    ├─ Onboard first 5-10 clients
    ├─ Learn operational patterns
    └─ $77/month cost
    ↓
Month 4-6: Growth Phase
    ↓
    ├─ 10-15 clients on EC2
    ├─ Vertical scaling (t3.xlarge)
    ├─ Plan K8s migration
    └─ $137/month cost
    ↓
Month 7+: Scale on Kubernetes
    ↓
    ├─ Migrate to K8s cluster
    ├─ 20-100+ clients
    ├─ High availability
    └─ $216-500/month cost
```

**Total Time to K8s**: 6-7 months
**Learning Benefit**: Operational experience before complexity
**Cost Savings**: $1,000+ in first 6 months

### Path 2: Production-First (For Established Companies)

```
Start: Kubernetes from Day 1
    ↓
    ├─ Already have K8s expertise
    ├─ Need HA from start
    ├─ Enterprise customers (SLAs)
    └─ Budget for $300+/month
    ↓
Result: Production-ready immediately
```

**Best For**:
- Companies with existing K8s infrastructure
- Enterprise sales requiring SLAs
- Large initial customer commitments
- DevOps team available

### Path 3: Dual Deployment (Dev/Prod Split)

```
Development: EC2 (server_mini/)
    ↓
    ├─ Test changes
    ├─ Staging environment
    ├─ Cost-effective
    └─ $77/month

Production: Kubernetes (server/)
    ↓
    ├─ Live customers
    ├─ High availability
    ├─ Auto-scaling
    └─ $216+/month
```

**Total Cost**: $293/month
**Benefits**: Safe testing, professional production

## Cost Analysis (12 Months)

### Scenario A: EC2 Only (Small Scale)
```
Months 1-12: EC2 (t3.large)
Cost: 12 × $77 = $924/year
Capacity: 5-10 clients
```

### Scenario B: EC2 → K8s Migration
```
Months 1-6:  EC2 (t3.large)   = $462
Months 7-12: K8s (small)      = $1,296
────────────────────────────────────
Total:                        = $1,758/year
Capacity: Scale from 5 to 50+ clients
```

### Scenario C: K8s from Start
```
Months 1-12: K8s (small cluster)
Cost: 12 × $216 = $2,592/year
Capacity: 50+ clients from day 1
```

**Savings with Path B**: $834 vs starting with K8s

## Technical Comparison

### Architecture

**EC2 (server_mini/):**
```
┌─────────────────────────────┐
│  Single EC2 Instance        │
│  ┌─────────────────────┐    │
│  │  Docker Compose     │    │
│  │  ├─ Kafka           │    │
│  │  ├─ Neo4j           │    │
│  │  ├─ Graph Builder   │    │
│  │  ├─ KG API          │    │
│  │  └─ Monitoring      │    │
│  └─────────────────────┘    │
└─────────────────────────────┘
```

**Kubernetes (server/):**
```
┌───────────────────────────────────────┐
│  EKS Cluster (Multi-AZ)               │
│  ┌────────┐  ┌────────┐  ┌────────┐  │
│  │ Node 1 │  │ Node 2 │  │ Node 3 │  │
│  ├────────┤  ├────────┤  ├────────┤  │
│  │ Pods   │  │ Pods   │  │ Pods   │  │
│  │ Auto-  │  │ Auto-  │  │ Auto-  │  │
│  │ scale  │  │ scale  │  │ scale  │  │
│  └────────┘  └────────┘  └────────┘  │
│  ┌────────────────────────────────┐  │
│  │  ALB (Load Balancer)           │  │
│  └────────────────────────────────┘  │
└───────────────────────────────────────┘
```

### Operations

**EC2 (server_mini/):**
```bash
# Start/stop services
docker-compose up -d
docker-compose stop

# Check health
./health-check.sh

# View logs
docker-compose logs -f

# Backup
./backup.sh

# Scale up
aws ec2 modify-instance-attribute --instance-type t3.xlarge
```

**Kubernetes (server/):**
```bash
# Deploy/update
helm upgrade kg-rca-server .

# Check health
kubectl get pods
kubectl get hpa

# View logs
kubectl logs -f deployment/graph-builder

# Backup
kubectl exec neo4j-0 -- neo4j-admin dump

# Scale up
kubectl scale deployment/graph-builder --replicas=5
```

## Migration Process

### When to Migrate from EC2 to K8s

Migrate when you hit **2 or more** of these triggers:

- [ ] **15+ active clients** (approaching capacity)
- [ ] **SLA requirements** > 99.5% uptime
- [ ] **Manual scaling** happening weekly
- [ ] **Revenue** > $10k MRR (can afford higher infrastructure cost)
- [ ] **Team growth** (dedicated DevOps engineer hired)
- [ ] **Multi-region** expansion planned
- [ ] **Enterprise customers** requiring compliance certifications

### Migration Steps

1. **Preparation** (Week 1)
   - [ ] Setup EKS cluster
   - [ ] Deploy K8s stack
   - [ ] Test with synthetic data

2. **Data Migration** (Week 2)
   - [ ] Backup EC2 Neo4j data
   - [ ] Restore to K8s Neo4j
   - [ ] Verify data integrity

3. **Client Migration** (Week 3-4)
   - [ ] Migrate clients one-by-one
   - [ ] Update Kafka endpoints
   - [ ] Verify RCA queries work

4. **Cutover** (Day 1)
   - [ ] Update DNS to K8s ALB
   - [ ] Monitor for 24 hours
   - [ ] Decommission EC2

**Total Time**: 3-4 weeks with testing

## Support & Documentation

### EC2 (server_mini/)
- [README](server_mini/README.md) - Overview
- [QUICK_START](server_mini/QUICK_START.md) - 5-minute setup
- [DEPLOYMENT_GUIDE](server_mini/DEPLOYMENT_GUIDE.md) - Complete guide
- [COMPARISON](server_mini/COMPARISON.md) - Detailed comparison

### Kubernetes (server/)
- [README](server/README.md) - Overview
- [Architecture](docs/00-ARCHITECTURE.md) - System design
- [Deployment](docs/01-SERVER-DEPLOYMENT.md) - K8s setup
- [Operations](docs/03-OPERATIONS.md) - Daily operations

## Recommendations by Company Stage

### Early Startup (Pre-Seed, Seed)
**Choose:** EC2 (server_mini/)
- Focus on product, not infrastructure
- Minimize burn rate
- Fast iteration
- Learn before committing to K8s

### Growth Startup (Series A)
**Choose:** EC2 → K8s migration
- Start simple
- Migrate at 15+ clients
- Invest in DevOps when revenue supports it

### Established Company (Series B+)
**Choose:** Kubernetes (server/)
- Enterprise requirements
- Existing K8s expertise
- Multi-region from day 1
- Professional operations

### Enterprise Internal Tool
**Choose:** Based on existing infrastructure
- Already have K8s? → Use it
- No K8s? → Start with EC2
- Integration > greenfield decisions

## Decision Matrix

Use this to choose:

|  | Use EC2 | Use K8s |
|---|---------|---------|
| **Budget** | < $200/month | > $300/month |
| **Clients** | < 15 | > 15 |
| **Team Size** | 1-3 engineers | 4+ engineers |
| **K8s Experience** | None | Yes |
| **SLA Required** | 99.5% OK | 99.9%+ |
| **Time to Deploy** | Days | Weeks |
| **Compliance** | Basic | Enterprise |

## Summary

### Choose EC2 (server_mini/) if:
- ✅ MVP/pilot phase
- ✅ Budget-conscious
- ✅ Small team
- ✅ < 15 clients
- ✅ Fast deployment needed
- ✅ No K8s expertise

### Choose Kubernetes (server/) if:
- ✅ Production at scale
- ✅ > 20 clients
- ✅ High availability critical
- ✅ Enterprise customers
- ✅ DevOps team available
- ✅ K8s expertise exists

### Pro Tip:
**Start with EC2, migrate to K8s when you've proven product-market fit and have 15+ clients.** This approach:
- Minimizes initial cost
- Reduces complexity while learning
- Provides clear migration trigger
- Saves $1,000+ in first 6 months

---

**Still not sure?** Default to EC2 for MVP. You can always migrate to K8s later, and you'll be glad you started simple.
