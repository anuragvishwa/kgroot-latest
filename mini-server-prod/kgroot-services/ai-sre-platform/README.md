# AI SRE Platform - Multi-Agent Root Cause Analysis System

> **Production-ready, Kafka-first, multi-agent AI SRE platform for automated incident investigation**

Built on top of KGroot causality analysis with lightweight, modular agent architecture.

---

## 🎯 Vision

Build a **true AI SRE** that acts as an "agentic interface to production" by:

- Understanding infrastructure topology and codebase
- Integrating with observability tools (Datadog, Grafana, Argo, etc.)
- Capturing institutional knowledge from Slack, docs, and runbooks
- Reasoning across production environments to deliver high-confidence RCA
- Learning from past incidents to improve over time

**Not just ChatGPT + logs. Real autonomous investigation.**

---

## 📊 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        INGESTION LAYER (Kafka-First)                     │
│                                                                           │
│   Sources → Kafka Topics (Multi-tenant) → Stream Processing → Storage    │
│                                                                           │
│   • K8s Events          • Datadog Metrics        • Argo Logs            │
│   • GitHub CI/CD        • Slack Incidents        • Prometheus           │
│                                                                           │
│   All data flows through Kafka with canonical event envelope            │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                    DATA PLANE (Always Available)                         │
│                                                                           │
│   • Neo4j (Causality + Topology + Vectors)                              │
│   • OpenSearch (Logs + Metrics + Full-text)                             │
│   • Redis (Session cache + Rate limiting)                               │
│   • PostgreSQL (Service→Repo mapping)                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                    CONTROL PLANE (AI Orchestration)                      │
│                                                                           │
│   ┌────────────────────────────────────────────────────────────┐        │
│   │            AI SRE Orchestrator (FastAPI)                    │        │
│   │  • Rule-based routing (cheap, deterministic)               │        │
│   │  • LLM planning (only for ambiguous cases)                 │        │
│   │  • Agent coordination & memory management                  │        │
│   └────────────────────────────────────────────────────────────┘        │
│                                                                           │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│   │Tool Registry │  │Agent Registry│  │Memory Manager│                 │
│   │(Plugin-based)│  │(Dynamic Load)│  │(Context/LTM) │                 │
│   └──────────────┘  └──────────────┘  └──────────────┘                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     SPECIALIST AGENTS (Modular)                          │
│                                                                           │
│   GraphAgent     MetricsAgent    LogsAgent     CodeAgent   ContextAgent │
│   (Neo4j RCA)    (Datadog/Prom)  (Argo/ES)     (GitHub)    (Slack/Docs)│
│                                                                           │
│   Each agent has access to specific tools from Tool Registry            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Key Design Principles

### 1. **Kafka-First Ingestion**
- All data sources → Kafka topics (with tenant isolation)
- Canonical event envelope for consistency
- Exactly-once delivery with idempotency keys
- Data plane never blocked by control plane failures

### 2. **Plugin-Based Tool Registry**
- Tools self-register via Python entry points
- Add new integrations without touching core code
- Each tool: metadata, schema, cost tracking, rate limits

### 3. **Modular Agent Framework**
- Agents composed of tools (GraphAgent, MetricsAgent, etc.)
- Dynamic loading based on configuration
- Parallel execution where possible
- Unified result schema for easy synthesis

### 4. **Cheap Rules → Smart LLM**
- Rule engine handles 60-80% of cases deterministically
- LLM planning only for ambiguous scenarios
- Massive cost savings + more predictable behavior

### 5. **Multi-Tenant Security**
- Per-tenant Kafka topics: `k8s-events-{tenant_id}`
- Client ID isolation in Neo4j, OpenSearch
- Per-tenant API credentials and budgets
- Secret management via Vault/AWS Parameter Store

### 6. **Observability & Cost Control**
- Every tool call tracked: latency, cost, success rate
- Per-tenant budgets and circuit breakers
- Audit trail for all agent decisions
- Prometheus metrics for monitoring

---

## 📁 Project Structure

```
ai-sre-platform/
├── README.md                          # This file
├── ARCHITECTURE.md                    # Detailed architecture
├── IMPLEMENTATION_ROADMAP.md          # Phase-by-phase guide
├── CANONICAL_EVENT_ENVELOPE.md        # Event schema standard
│
├── docs/
│   ├── TOOL_DEVELOPMENT_GUIDE.md     # How to add new tools
│   ├── AGENT_DEVELOPMENT_GUIDE.md    # How to add new agents
│   ├── KAFKA_INTEGRATION.md          # Kafka patterns
│   ├── SECURITY.md                   # Security best practices
│   └── RUNBOOK.md                    # Operations guide
│
├── architecture/
│   ├── diagrams/                     # Architecture diagrams
│   ├── adr/                          # Architecture Decision Records
│   └── patterns/                     # Common patterns
│
├── config/
│   ├── schemas/
│   │   ├── event_envelope.avro       # Canonical envelope
│   │   └── agent_result.json         # Agent result schema
│   ├── tools/
│   │   ├── tools.yaml                # Tool configurations
│   │   └── credentials.yaml.example  # Credential template
│   └── agents/
│       └── agents.yaml               # Agent configurations
│
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── tool_registry.py          # Tool plugin system
│   │   ├── agent_registry.py         # Agent management
│   │   ├── memory_manager.py         # Incident memory
│   │   ├── router.py                 # Rule-based routing
│   │   └── schemas.py                # Pydantic models
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── orchestrator.py           # Main orchestrator
│   │   ├── planner.py                # LLM-based planning
│   │   ├── synthesizer.py            # Result synthesis
│   │   └── budgets.py                # Cost/rate limiting
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                   # Base agent class
│   │   ├── graph_agent.py            # Neo4j causality
│   │   ├── metrics_agent.py          # Datadog/Prometheus
│   │   ├── logs_agent.py             # Argo/OpenSearch
│   │   ├── code_agent.py             # GitHub integration
│   │   └── context_agent.py          # Slack/docs search
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py                   # Base tool class
│   │   ├── graph_tools.py            # Neo4j tools
│   │   ├── metrics_tools.py          # Datadog/Prom tools
│   │   ├── logs_tools.py             # Log search tools
│   │   ├── code_tools.py             # GitHub tools
│   │   └── context_tools.py          # Slack/doc tools
│   │
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── kafka_consumer.py         # Multi-tenant consumer
│   │   ├── processors/               # Per-source processors
│   │   │   ├── k8s_processor.py
│   │   │   ├── datadog_processor.py
│   │   │   ├── argo_processor.py
│   │   │   └── cicd_processor.py
│   │   └── envelope.py               # Envelope validation
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI app
│   │   ├── routes/
│   │   │   ├── investigate.py        # POST /investigate
│   │   │   ├── incidents.py          # Incident CRUD
│   │   │   └── health.py             # Health checks
│   │   └── middleware.py             # Auth, logging
│   │
│   └── utils/
│       ├── __init__.py
│       ├── secrets.py                # Secret management
│       ├── circuit_breaker.py        # Circuit breakers
│       └── observability.py          # Metrics/tracing
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── scripts/
│   ├── setup_kafka_topics.sh         # Create topics
│   ├── load_test_data.py             # Load sample data
│   └── deploy.sh                     # Deployment script
│
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml            # Local dev stack
│   └── docker-compose.prod.yml       # Production stack
│
├── helm/                             # Kubernetes deployment
│   └── ai-sre-platform/
│
├── pyproject.toml                    # Python deps + entry points
├── requirements.txt
└── .env.example                      # Environment variables
```

---

## 🚀 Quick Start

### Prerequisites

```bash
# Required services
- Kafka cluster (or local docker-compose)
- Neo4j 5.x (with vector index support)
- OpenSearch/Elasticsearch
- Redis
- PostgreSQL (optional, for service mapping)

# Python 3.11+
- pip install -r requirements.txt
```

### Local Development Setup

```bash
# 1. Clone and enter directory
cd mini-server-prod/kgroot-services/ai-sre-platform

# 2. Start infrastructure (Kafka, Neo4j, OpenSearch, Redis)
docker-compose up -d

# 3. Create Kafka topics
./scripts/setup_kafka_topics.sh

# 4. Set environment variables
cp .env.example .env
# Edit .env with your credentials

# 5. Initialize Neo4j indexes (from existing scripts)
# Run your existing CREATE-INDEXES.cypher

# 6. Start API server
uvicorn src.api.main:app --reload --port 8000

# 7. Start Kafka consumers (in separate terminals)
python -m src.ingestion.kafka_consumer --group k8s-events
python -m src.ingestion.kafka_consumer --group datadog-metrics

# 8. Test the system
curl -X POST http://localhost:8000/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Why did nginx pods fail?",
    "tenant_id": "acme-01",
    "time_window": {
      "start": "2025-10-30T07:00:00Z",
      "end": "2025-10-30T08:00:00Z"
    }
  }'
```

---

## 📋 Implementation Phases

> **See [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md) for detailed steps**

### Phase 1: Foundation (Week 1-2)
- ✅ Canonical event envelope
- ✅ Tool registry framework
- ✅ Agent base classes
- ✅ Basic orchestrator
- ✅ GraphAgent (wrap existing Neo4j RCA)

### Phase 2: Ingestion Layer (Week 3-4)
- ✅ Kafka topic setup
- ✅ Multi-tenant consumers
- ✅ Event processors (K8s, Datadog, Argo)
- ✅ Schema validation
- ✅ Dead-letter queues

### Phase 3: Core Agents (Week 5-8)
- ✅ MetricsAgent (Datadog/Prometheus)
- ✅ LogsAgent (Argo/OpenSearch)
- ✅ CodeAgent (GitHub integration)
- ✅ ContextAgent (Slack/docs)

### Phase 4: Intelligence Layer (Week 9-10)
- ✅ Rule-based router
- ✅ LLM planner (GPT-4o)
- ✅ Result synthesizer
- ✅ Incident memory & learning

### Phase 5: Production Hardening (Week 11-12)
- ✅ Circuit breakers
- ✅ Per-tenant budgets
- ✅ Observability (Prometheus, Grafana)
- ✅ Security (Vault integration)
- ✅ Load testing

### Phase 6: Advanced Features (Week 13+)
- ✅ Vector similarity for past incidents
- ✅ Automated runbook generation
- ✅ Proactive anomaly detection
- ✅ Human-in-the-loop approvals

---

## 🔑 Key Concepts

### Canonical Event Envelope

Every event from any source is normalized to:

```json
{
  "tenant_id": "acme-01",
  "source": "k8s.events",
  "event_type": "PodOOMKilled",
  "ts": "2025-10-30T07:41:03Z",
  "correlation_ids": {
    "trace_id": "abc123",
    "commit": "def456",
    "workflow": "argo-deploy-789"
  },
  "entity": {
    "cluster": "prod-us-west",
    "namespace": "payments",
    "service": "nginx-api",
    "pod": "nginx-api-7d8f-xyz"
  },
  "severity": "error",
  "payload": { "...raw vendor fields..." },
  "ingest_id": "uuid-for-deduplication",
  "schema_version": "v1"
}
```

### Incident Scope

Every investigation operates on a well-defined scope:

```json
{
  "tenant_id": "acme-01",
  "service": "nginx-api",
  "time_window": {
    "start": "2025-10-30T07:00:00Z",
    "end": "2025-10-30T08:00:00Z"
  },
  "pivot_event_id": "evt-123",
  "correlation_ids": ["trace-abc", "commit-def"]
}
```

### Unified Agent Result

Every agent returns:

```json
{
  "agent": "MetricsAgent",
  "findings": [
    {
      "kind": "anomaly.cpu",
      "detail": { "service": "nginx-api", "spike_factor": 3.2 },
      "confidence": 0.82
    }
  ],
  "artifacts": [
    { "type": "timeseries", "ref": "es://metrics/cpu-spike-123" }
  ],
  "cost": {
    "llm_usd": 0.002,
    "api_usd": 0.001
  },
  "latency_ms": 640
}
```

---

## 🛠️ Tool Development

Adding a new tool is simple:

```python
# src/tools/my_new_tool.py
from src.core.tool_registry import BaseTool, ToolMetadata, tool_registry

class MyNewTool(BaseTool):
    def __init__(self, api_client):
        self.client = api_client
        tool_registry.register(self)  # Auto-register

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="my_new_tool",
            description="Does something useful",
            category="metrics",
            rate_limit_per_min=60
        )

    async def execute(self, params: dict) -> dict:
        # Your logic here
        result = await self.client.query(params)
        return {"success": True, "data": result}

    def get_schema(self) -> dict:
        # JSON schema for LLM function calling
        return {...}
```

Enable in config:

```yaml
# config/tools/tools.yaml
tools:
  my_new_tool:
    enabled: true
    api_key: ${MY_TOOL_API_KEY}
```

**That's it!** The tool is now available to all agents.

---

## 📊 Observability

### Metrics (Prometheus)

```
# Tool calls
kgroot_tool_calls_total{tenant, tool, status}
kgroot_tool_latency_seconds{tenant, tool}
kgroot_tool_cost_usd{tenant, tool}

# Agent execution
kgroot_agent_executions_total{tenant, agent, status}
kgroot_agent_latency_seconds{tenant, agent}

# Orchestrator
kgroot_investigations_total{tenant, status}
kgroot_investigation_confidence{tenant}
```

### Tracing

OpenTelemetry traces for every investigation:
- Span per agent execution
- Span per tool call
- Span per LLM invocation

### Audit Trail

Every decision logged to `audit-orchestrator` Kafka topic:
```json
{
  "timestamp": "2025-10-30T07:45:00Z",
  "tenant_id": "acme-01",
  "incident_id": "inc-123",
  "event_type": "plan_created",
  "details": {
    "agents_selected": ["GraphAgent", "MetricsAgent"],
    "reasoning": "OOMKilled detected, need causality + metrics"
  }
}
```

---

## 🔒 Security

- **Secrets**: Vault/AWS Parameter Store (never in code/config)
- **Multi-tenancy**: Strict isolation via tenant_id in all queries
- **API Auth**: JWT tokens with tenant claims
- **Secret Redaction**: Automatic PII/secret scrubbing in logs
- **Rate Limiting**: Per-tenant and per-tool rate limits
- **Circuit Breakers**: Prevent cascade failures

---

## 💰 Cost Control

### Per-Tenant Budgets

```yaml
budgets:
  acme-01:
    max_llm_usd_per_day: 50.0
    max_agent_concurrency: 5
    max_investigations_per_hour: 100
```

### Tool-Level Tracking

Every tool call tracked:
- API cost (Datadog, OpenAI, etc.)
- Compute cost (estimate)
- Total per incident
- Daily/monthly rollups

---

## 🧪 Testing Strategy

```bash
# Unit tests
pytest tests/unit/

# Integration tests (requires docker-compose)
pytest tests/integration/

# End-to-end tests
pytest tests/e2e/

# Load testing
locust -f tests/load/locustfile.py
```

---

## 📚 Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) - Deep dive into architecture
- [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md) - Step-by-step guide
- [CANONICAL_EVENT_ENVELOPE.md](./CANONICAL_EVENT_ENVELOPE.md) - Event schema
- [docs/TOOL_DEVELOPMENT_GUIDE.md](./docs/TOOL_DEVELOPMENT_GUIDE.md) - Adding tools
- [docs/AGENT_DEVELOPMENT_GUIDE.md](./docs/AGENT_DEVELOPMENT_GUIDE.md) - Adding agents
- [docs/KAFKA_INTEGRATION.md](./docs/KAFKA_INTEGRATION.md) - Kafka patterns
- [docs/RUNBOOK.md](./docs/RUNBOOK.md) - Operations guide

---

## 🎯 Success Metrics

### Technical Metrics
- **MTTR Reduction**: 40-60% faster incident resolution
- **False Positive Rate**: <10% (vs 60% in naive approaches)
- **Confidence Score**: >0.85 for root causes
- **Agent Latency**: p95 < 5 seconds per agent
- **Cost per Investigation**: <$0.50

### Business Metrics
- **On-call Load**: 30-50% reduction in pages
- **Toil Reduction**: 70% of investigations automated
- **Knowledge Capture**: 100% of incidents stored for learning
- **Onboarding Time**: 6 months → 2 weeks (via AI SRE training)

---

## 🤝 Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for:
- Code style guide
- PR process
- Testing requirements
- ADR process

---

## 📄 License

Internal use only - Proprietary

---

## 🚦 Current Status

**Phase**: Design & Architecture ✅
**Next**: Phase 1 Implementation (Foundation)

---

## 📞 Support

- Slack: `#ai-sre-platform`
- Email: `sre-team@company.com`
- Docs: `https://docs.company.com/ai-sre`

---

**Let's build a true AI SRE! 🚀**