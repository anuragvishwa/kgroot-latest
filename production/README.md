# 🚀 Production Deployment - Knowledge Graph RCA System

## 🎯 Two Deployment Models

### 1. **SaaS Multi-Tenant** (Serve Multiple Clients) 💰
Deploy YOUR server infrastructure and onboard multiple paying clients.

### 2. **Single-Tenant** (Traditional Deployment)
Deploy entire stack in one cluster for a single organization.

---

## Quick Links

### SaaS Multi-Tenant (Recommended)
| Resource | Description |
|----------|-------------|
| [🏢 SaaS Architecture](prod-docs/saas/SAAS_ARCHITECTURE.md) | Multi-tenant design, data isolation |
| [🖥️ Server Deployment](prod-docs/saas/SERVER_DEPLOYMENT.md) | Deploy YOUR infrastructure |
| [👥 Client Onboarding](prod-docs/saas/CLIENT_ONBOARDING.md) | Onboard new clients |
| [💰 Billing Setup](prod-docs/saas/BILLING_SETUP.md) | Usage-based billing with Stripe |

### Single-Tenant / Universal
| Resource | Description |
|----------|-------------|
| [📖 Complete System Overview](prod-docs/COMPLETE_SYSTEM_OVERVIEW.md) | Architecture, features, data flow |
| [⚙️ Deployment Guide](prod-docs/PRODUCTION_DEPLOYMENT_GUIDE.md) | Helm installation instructions |
| [🔌 API Reference](api-docs/API_REFERENCE.md) | Complete API documentation (50+ endpoints) |
| [📊 Query Library](neo4j-queries/QUERY_LIBRARY.md) | Neo4j Cypher queries (50+ examples) |
| [🔍 Vector Search](vector-search/) | Semantic search implementation |
| [📦 Server Helm Chart](helm-chart/server/kg-rca-server/) | YOUR SaaS infrastructure |
| [📦 Client Helm Chart](helm-chart/client/kg-rca-agent/) | Lightweight client agents |
| [📦 Single Helm Chart](helm-chart/kg-rca-system/) | All-in-one deployment |

---

## What's Inside?

### 1. 🔍 Vector Search (Semantic Queries)

Ask natural language questions like:
- **"What bug is caused by what"**
- **"Show me memory leak incidents"**
- **"Find connection timeout errors"**

**Location**: `vector-search/`
- `embeddings.go` - Go service for vector search
- `embedding-service/` - Python service (sentence-transformers)
  - Flask API for generating embeddings
  - 384-dimensional vectors
  - Pre-trained on K8s patterns

**Example**:
```bash
curl -X POST http://localhost:8080/api/v1/search/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "memory leak causing pod crashes",
    "top_k": 10,
    "min_similarity": 0.6
  }'
```

---

### 2. 📦 Helm Chart (Single-Command Deployment)

Deploy the entire system with one command!

**Location**: `helm-chart/kg-rca-system/`

**What gets deployed**:
- Neo4j (knowledge graph)
- Kafka + Zookeeper (streaming)
- Graph Builder (RCA engine)
- KG API (REST endpoints)
- Embedding Service (vector search)
- State Watcher (K8s monitoring)
- Vector (log collection)
- K8s Event Exporter
- Prometheus + Grafana
- Cleanup CronJob

**Install**:
```bash
cd helm-chart
helm install kg-rca ./kg-rca-system \
  --namespace observability \
  --create-namespace
```

**Custom configuration**:
```bash
helm install kg-rca ./kg-rca-system \
  --namespace observability \
  --values my-values.yaml
```

---

### 3. 🔌 API Documentation

Complete API reference for building clients and integrations.

**Location**: `api-docs/API_REFERENCE.md`

**API Categories**:
1. **RCA & Analysis APIs** - Root cause analysis with confidence scoring
2. **Vector Search APIs** - Semantic search, causal search
3. **Graph Query APIs** - Topology, event history, timelines
4. **Incident Management APIs** - List, update, resolve incidents
5. **Resource APIs** - Get resource details, health scores
6. **Metrics & Health APIs** - System statistics, monitoring
7. **Admin & Maintenance APIs** - Cleanup, reindexing

**Example endpoints**:
```bash
# Semantic search
POST /api/v1/search/semantic

# RCA analysis
POST /api/v1/rca

# List incidents
GET /api/v1/incidents

# Get resource health
GET /api/v1/resources/{uid}/health

# System statistics
GET /api/v1/stats
```

---

### 4. 📊 Neo4j Query Library

50+ production-ready Cypher queries.

**Location**: `neo4j-queries/QUERY_LIBRARY.md`

**Query Categories**:
1. **RCA & Causality** - Find root causes with confidence scoring
2. **Vector Embeddings** - Semantic similarity search
3. **Resource & Topology** - Get topology, blast radius
4. **Incident Analysis** - Cluster events, timelines
5. **Anomaly Detection** - Detect spikes, leaks, cascades
6. **Performance & Health** - Health scores, dashboards
7. **Maintenance** - Cleanup, indexing

**Example**:
```cypher
// Find root causes with confidence scoring
MATCH (e:Episodic {eid: $event_id})-[:ABOUT]->(r:Resource)
MATCH (c:Episodic)-[:POTENTIAL_CAUSE]->(e)
RETURN c.eid, c.reason,
       (temporal_score * 0.3 + distance_score * 0.3 + domain_score * 0.4) AS confidence
ORDER BY confidence DESC
```

---

### 5. 📖 Production Documentation

Complete guides for deployment and operations.

**Location**: `prod-docs/`

**Documents**:
- `COMPLETE_SYSTEM_OVERVIEW.md` - Architecture, features, use cases
- `PRODUCTION_DEPLOYMENT_GUIDE.md` - Step-by-step installation
- `USE_CASES.md` - Common scenarios and examples

---

## 🎯 Key Features

### ✅ Universal Semantic Search
- Ask questions in natural language
- Vector embeddings (384 dimensions)
- Sentence-transformers model
- Cosine similarity matching

### ✅ Intelligent RCA
- Confidence scoring (temporal + distance + domain)
- K8s-specific failure patterns
- Causal chain analysis
- Blast radius calculation

### ✅ Real-Time Updates
- <1 second latency from K8s to graph
- Automatic sync via state-watcher
- Kafka buffering (7-day retention)
- Incremental update API

### ✅ Single-Command Deployment
- One Helm chart for everything
- Configurable via values.yaml
- Supports HA, auto-scaling
- Air-gapped installation support

### ✅ Production Monitoring
- Prometheus metrics (20+ metrics)
- Grafana dashboards (13 panels)
- Health checks, circuit breakers
- Anomaly detection

---

## 🚀 Quick Start

### Option 1: SaaS Multi-Tenant (Recommended for serving clients)

**For YOU (SaaS Provider)**:
```bash
# 1. Deploy YOUR server infrastructure
cd production/helm-chart/server
helm install kg-rca-server ./kg-rca-server \
  --namespace kg-rca-server \
  --create-namespace \
  --values production-values.yaml

# 2. Onboard first client
curl -X POST https://api.kg-rca.your-company.com/admin/clients \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"name": "Acme Corp", "plan": "pro"}'

# 3. Client installs lightweight agents
# (See CLIENT_ONBOARDING.md)
```

**For CLIENTS**:
```bash
# Install lightweight agents in your cluster
cd production/helm-chart/client
helm install kg-rca-agent ./kg-rca-agent \
  --namespace kg-rca \
  --create-namespace \
  --values acme-corp-values.yaml
```

📖 **See**: [prod-docs/saas/](prod-docs/saas/) for complete SaaS setup

---

### Option 2: Single-Tenant (Traditional single-cluster deployment)

```bash
# 1. Install Helm chart
cd production/helm-chart
helm install kg-rca ./kg-rca-system \
  --namespace observability \
  --create-namespace

# 2. Wait for pods
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/instance=kg-rca \
  -n observability --timeout=10m

# 3. Test API
kubectl port-forward svc/kg-rca-kg-api 8080:8080 -n observability
curl http://localhost:8080/healthz

# 4. Try semantic search
curl -X POST http://localhost:8080/api/v1/search/semantic \
  -H "Content-Type: application/json" \
  -d '{"query": "pod crashes", "top_k": 5}' | jq .
```

---

### Option 3: Production Single-Tenant Setup

```bash
# 1. Create custom values
cat > values-prod.yaml <<EOF
neo4j:
  auth:
    password: <STRONG-PASSWORD>
  resources:
    requests: {cpu: 2000m, memory: 8Gi}

kafka:
  replicaCount: 3

graphBuilder:
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10

kgApi:
  ingress:
    enabled: true
    hosts:
      - host: kg-api.your-domain.com
EOF

# 2. Install
helm install kg-rca ./kg-rca-system \
  --namespace observability \
  --values values-prod.yaml \
  --wait
```

---

## 📚 Documentation Structure

```
production/
│
├── README.md                      # ← You are here
│
├── helm-chart/                    # K8s deployments
│   ├── server/                    # 🆕 YOUR SaaS infrastructure
│   │   └── kg-rca-server/
│   │       ├── values.yaml        # Neo4j, Kafka, Graph Builder, API
│   │       └── templates/
│   ├── client/                    # 🆕 Lightweight client agents
│   │   └── kg-rca-agent/
│   │       ├── values.yaml        # State watcher, Vector, Events
│   │       └── templates/
│   └── kg-rca-system/             # Single-tenant (all-in-one)
│
├── vector-search/                 # Semantic search
│   ├── embeddings.go              # Go implementation
│   └── embedding-service/         # Python service
│       ├── main.py
│       ├── Dockerfile
│       └── requirements.txt
│
├── api-docs/                      # API documentation
│   └── API_REFERENCE.md           # 50+ endpoints
│
├── neo4j-queries/                 # Query examples
│   └── QUERY_LIBRARY.md           # 50+ Cypher queries
│
├── billing-service/               # 🆕 Usage-based billing
│   ├── metrics.go                 # Track usage
│   ├── stripe.go                  # Stripe integration
│   └── schema.sql                 # PostgreSQL schema
│
└── prod-docs/                     # Guides
    ├── saas/                      # 🆕 SaaS multi-tenant docs
    │   ├── SAAS_ARCHITECTURE.md   # Multi-tenant design
    │   ├── SERVER_DEPLOYMENT.md   # Deploy YOUR infrastructure
    │   ├── CLIENT_ONBOARDING.md   # Onboard clients
    │   └── BILLING_SETUP.md       # Usage-based billing
    │
    ├── COMPLETE_SYSTEM_OVERVIEW.md    # Architecture
    ├── PRODUCTION_DEPLOYMENT_GUIDE.md # Installation
    └── USE_CASES.md                   # Examples
```

---

## 🔍 Example Use Cases

### 1. Semantic Search

```bash
# "What caused the memory leak?"
curl -X POST http://localhost:8080/api/v1/search/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "memory leak causing crashes",
    "top_k": 10,
    "filters": {
      "severity": ["ERROR", "FATAL"],
      "namespace": ["production"]
    }
  }' | jq .
```

### 2. Root Cause Analysis

```bash
# Get RCA for specific event
curl -X POST http://localhost:8080/api/v1/rca \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt-abc123",
    "min_confidence": 0.7,
    "include_blast_radius": true
  }' | jq .
```

### 3. Causal Chain Analysis

```bash
# "What caused what"
curl -X POST http://localhost:8080/api/v1/search/causal \
  -H "Content-Type: application/json" \
  -d '{
    "query": "pod eviction service outage",
    "max_chain_length": 5
  }' | jq .
```

### 4. List Active Incidents

```bash
# Get open incidents
curl http://localhost:8080/api/v1/incidents?status=open | jq .
```

---

## 🛠️ Building APIs (For Clients)

### Python SDK Example

```python
from kg_rca_client import KGRCAClient

client = KGRCAClient(
    base_url="http://kg-api.your-domain.com/api/v1",
    api_key="your-api-key"
)

# Semantic search
results = client.search.semantic(
    query="memory leak crashes",
    top_k=10
)

# RCA analysis
analysis = client.rca.analyze(
    event_id="evt-123",
    min_confidence=0.7
)

# List incidents
incidents = client.incidents.list(
    status="open",
    severity=["FATAL"]
)
```

### JavaScript/TypeScript SDK Example

```typescript
import { KGRCAClient } from '@kg-rca/client';

const client = new KGRCAClient({
  baseURL: 'http://kg-api.your-domain.com/api/v1',
  apiKey: 'your-api-key'
});

// Semantic search
const results = await client.search.semantic({
  query: 'connection timeout',
  topK: 10
});

// RCA
const analysis = await client.rca.analyze({
  eventId: 'evt-123'
});
```

---

## 📊 System Requirements

### Minimal (Development)
- **CPU**: 8 cores
- **Memory**: 16GB RAM
- **Storage**: 50GB
- **Kubernetes**: v1.24+

### Recommended (Production)
- **CPU**: 24 cores
- **Memory**: 64GB RAM
- **Storage**: 200GB SSD
- **Kubernetes**: v1.24+
- **Nodes**: 3+ worker nodes

### Large (Enterprise)
- **CPU**: 64 cores
- **Memory**: 256GB RAM
- **Storage**: 500GB SSD
- **Kubernetes**: v1.24+
- **Nodes**: 5+ worker nodes

---

## 🔧 Configuration

### values.yaml Structure

```yaml
global:
  namespace: observability
  imageRegistry: your-registry.com

neo4j:
  auth: {password: changeme}
  resources: {requests: {cpu: 2000m, memory: 8Gi}}
  persistence: {enabled: true, size: 50Gi}

kafka:
  replicaCount: 3
  config: {numPartitions: 6, replicationFactor: 3}

graphBuilder:
  replicaCount: 3
  autoscaling: {enabled: true, minReplicas: 3, maxReplicas: 10}

kgApi:
  replicaCount: 3
  ingress: {enabled: true, hosts: [...]}

embeddingService:
  replicaCount: 2
  resources: {requests: {cpu: 1000m, memory: 2Gi}}

prometheus:
  enabled: true
  retention: 30d

grafana:
  enabled: true
  service: {type: LoadBalancer}
```

---

## 🎓 Next Steps

After installation:

1. ✅ Read [Complete System Overview](prod-docs/COMPLETE_SYSTEM_OVERVIEW.md)
2. ✅ Follow [Deployment Guide](prod-docs/PRODUCTION_DEPLOYMENT_GUIDE.md)
3. ✅ Explore [API Reference](api-docs/API_REFERENCE.md)
4. ✅ Try [Query Examples](neo4j-queries/QUERY_LIBRARY.md)
5. ✅ Set up monitoring dashboards
6. ✅ Test semantic search
7. ✅ Configure webhooks
8. ✅ Train team on RCA queries

---

## 📞 Support

- **Documentation**: See `prod-docs/` directory
- **API Reference**: See `api-docs/API_REFERENCE.md`
- **Query Examples**: See `neo4j-queries/QUERY_LIBRARY.md`
- **Issues**: File issues in GitHub repository

---

## 🎉 Summary

You now have everything needed for production deployment:

### Core Features
✅ **Vector search** for semantic queries ("What bug is caused by what")
✅ **Intelligent RCA** with confidence scoring
✅ **Complete APIs** (50+ endpoints documented)
✅ **Query library** (50+ Neo4j examples)
✅ **Production monitoring** (Prometheus, Grafana)
✅ **Auto-scaling support**
✅ **HA configuration**

### 🆕 SaaS Multi-Tenant Features
✅ **Multi-tenant architecture** - Serve multiple clients from YOUR server
✅ **Data isolation** - Database-per-client (Neo4j), topic-per-client (Kafka)
✅ **Usage-based billing** - Stripe integration, track events/queries/storage
✅ **Lightweight clients** - Agents send data to YOUR server
✅ **API authentication** - API keys per client
✅ **Rate limiting** - Kong API Gateway with per-client limits
✅ **Client onboarding** - 30-minute onboarding process
✅ **Revenue tracking** - Billing dashboards, invoice generation

### Deployment Options

**Option 1: SaaS Multi-Tenant** (Recommended for serving clients) 💰
```bash
# Deploy YOUR server
cd production/helm-chart/server
helm install kg-rca-server ./kg-rca-server \
  --namespace kg-rca-server \
  --values production-values.yaml

# See: prod-docs/saas/
```

**Option 2: Single-Tenant** (Traditional deployment)
```bash
# Deploy entire stack in one cluster
cd production/helm-chart
helm install kg-rca ./kg-rca-system \
  --namespace observability
```

### Pricing Model (SaaS)

| Plan | Price | Events/Day | RCA Queries | Storage |
|------|-------|------------|-------------|---------|
| **Free** | $0 | 10K | 100 | 1 GB |
| **Basic** | $99/mo | 100K | 1K | 10 GB |
| **Pro** | $499/mo | 1M | 10K | 100 GB |
| **Enterprise** | Custom | Unlimited | Unlimited | Custom |

**Revenue Potential**: $100K-$1M+/month with 100+ clients

---

### Next Steps

**For SaaS Providers**:
1. ✅ Read [SaaS Architecture](prod-docs/saas/SAAS_ARCHITECTURE.md)
2. ✅ Deploy [YOUR Server](prod-docs/saas/SERVER_DEPLOYMENT.md)
3. ✅ Setup [Billing](prod-docs/saas/BILLING_SETUP.md)
4. ✅ Onboard [First Client](prod-docs/saas/CLIENT_ONBOARDING.md)

**For Single-Tenant**:
1. ✅ Read [Complete System Overview](prod-docs/COMPLETE_SYSTEM_OVERVIEW.md)
2. ✅ Follow [Deployment Guide](prod-docs/PRODUCTION_DEPLOYMENT_GUIDE.md)
3. ✅ Explore [API Reference](api-docs/API_REFERENCE.md)
4. ✅ Try [Query Examples](neo4j-queries/QUERY_LIBRARY.md)

For detailed instructions, see [Production Deployment Guide](prod-docs/PRODUCTION_DEPLOYMENT_GUIDE.md) or [SaaS Architecture](prod-docs/saas/SAAS_ARCHITECTURE.md).
