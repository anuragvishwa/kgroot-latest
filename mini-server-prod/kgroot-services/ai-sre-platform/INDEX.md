# AI SRE Platform - Documentation Index

> **Central navigation** for all platform documentation

---

## 🎯 Start Here

### For Everyone
- **[README.md](./README.md)** - Project overview, architecture, quick start

### For New Developers
- **[GETTING_STARTED.md](./GETTING_STARTED.md)** - Local setup, development workflow

### For Architects
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - Detailed architecture, design principles

---

## 📋 Core Documentation

### Design & Architecture

| Document | Purpose | Audience | Time to Read |
|----------|---------|----------|--------------|
| [README.md](./README.md) | System overview, vision, quick start | Everyone | 15 min |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Detailed architecture, components, flows | Architects, Senior Devs | 30 min |
| [CANONICAL_EVENT_ENVELOPE.md](./CANONICAL_EVENT_ENVELOPE.md) | Event schema standard | All Devs | 15 min |
| [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md) | Phase-by-phase implementation plan | All Devs, PMs | 20 min |
| [GETTING_STARTED.md](./GETTING_STARTED.md) | Local setup, development guide | New Devs | 10 min |

### Implementation Guides (Coming Soon)

- [ ] `docs/TOOL_DEVELOPMENT_GUIDE.md` - How to add new tools
- [ ] `docs/AGENT_DEVELOPMENT_GUIDE.md` - How to add new agents
- [ ] `docs/KAFKA_INTEGRATION.md` - Kafka patterns and best practices
- [ ] `docs/SECURITY.md` - Security guidelines
- [ ] `docs/RUNBOOK.md` - Operations guide

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  INGESTION LAYER                         │
│   K8s → Kafka → Stream Processing → Storage             │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│                    DATA PLANE                            │
│   Neo4j • OpenSearch • Redis • PostgreSQL               │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│                  CONTROL PLANE                           │
│   Orchestrator → Agents → Tools                         │
└─────────────────────────────────────────────────────────┘
```

**See**: [ARCHITECTURE.md](./ARCHITECTURE.md) for full details

---

## 🚀 Implementation Status

### Phase 1: Foundation (Week 1-2) - 🟡 In Progress

| Task | Status | Owner | Docs |
|------|--------|-------|------|
| Core schemas | 🟡 In Progress | TBD | [Roadmap §1.1](./IMPLEMENTATION_ROADMAP.md#11-core-infrastructure-week-1-days-1-2) |
| Tool registry | 🟡 In Progress | TBD | [Roadmap §1.1](./IMPLEMENTATION_ROADMAP.md#11-core-infrastructure-week-1-days-1-2) |
| Agent base | ⚪ Not Started | TBD | [Roadmap §1.2](./IMPLEMENTATION_ROADMAP.md#12-agent-base-classes-week-1-days-3-4) |
| GraphAgent | ⚪ Not Started | TBD | [Roadmap §1.3](./IMPLEMENTATION_ROADMAP.md#13-graphagent---wrap-existing-neo4j-rca-week-1-day-5---week-2-day-1) |
| Orchestrator | ⚪ Not Started | TBD | [Roadmap §1.4](./IMPLEMENTATION_ROADMAP.md#14-simple-orchestrator-week-2-days-2-4) |

### Phase 2: Kafka Ingestion (Week 3-4) - ⚪ Not Started

### Phase 3: Additional Agents (Week 5-8) - ⚪ Not Started

### Phase 4: Intelligence Layer (Week 9-10) - ⚪ Not Started

### Phase 5: Production Hardening (Week 11-12) - ⚪ Not Started

**See**: [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md) for detailed plan

---

## 📚 Key Concepts

### Canonical Event Envelope

Every event from any source is normalized to a standard format:

```json
{
  "tenant_id": "acme-01",
  "source": "k8s.events",
  "event_type": "PodOOMKilled",
  "ts": "2025-10-30T07:41:03Z",
  "entity": {
    "service": "nginx-api",
    "namespace": "payments"
  },
  "severity": "error",
  "payload": {...}
}
```

**See**: [CANONICAL_EVENT_ENVELOPE.md](./CANONICAL_EVENT_ENVELOPE.md)

### Tool Registry (Plugin System)

Tools self-register via Python entry points:

```python
class MyTool(BaseTool):
    def __init__(self):
        tool_registry.register(self)  # Auto-registers
```

**Benefits**:
- Add new integrations without changing core code
- `pip install ai-sre-plugin-splunk` → tool available
- Each tool: metadata, schema, cost tracking

### Agent Architecture

Agents = LLM + Tools + Domain Expertise

```python
class GraphAgent(BaseAgent):
    capability = AgentCapability(
        name="GraphAgent",
        tools=["neo4j_find_root_causes", "neo4j_get_causal_chain"],
        expertise="Kubernetes event causality"
    )

    async def investigate(self, query, scope):
        # Use tools to investigate
        root_causes = await self.call_tool("neo4j_find_root_causes", {...})
        return findings
```

---

## 🔑 Success Criteria

### Technical Metrics

| Metric | Current (Manual) | Target (AI SRE) | Status |
|--------|------------------|-----------------|--------|
| **MTTR** | 30-120 min | <5 min | 🎯 TBD |
| **False Positive Rate** | N/A | <10% | 🎯 TBD |
| **Root Cause Confidence** | N/A | >0.85 | 🎯 TBD |
| **Investigation Latency** | N/A | <30s (p95) | 🎯 TBD |
| **Cost per Investigation** | ~$50 (human time) | <$0.50 | 🎯 TBD |

### Business Metrics

- **On-call Load**: 30-50% reduction in pages
- **Toil Reduction**: 70% of investigations automated
- **Knowledge Capture**: 100% of incidents stored for learning
- **Onboarding Time**: 6 months → 2 weeks

---

## 🛠️ Development Tools

### Required
- Python 3.11+
- Docker & Docker Compose
- Neo4j 5.x
- Kafka (Confluent Platform or AWS MSK)
- Redis
- Git

### Recommended
- VS Code with Python extension
- Postman (API testing)
- Neo4j Browser
- Kafka Tool (GUI for Kafka)

---

## 📞 Getting Help

### Internal Resources
- **Slack**: `#ai-sre-platform`
- **Project Board**: [Link to Jira/GitHub Projects]
- **Team Lead**: [Name]
- **Tech Lead**: [Name]

### External Resources
- [Neo4j Documentation](https://neo4j.com/docs/)
- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [OpenAI API](https://platform.openai.com/docs/)

---

## 🎯 Quick Links

### For New Team Members
1. Read [README.md](./README.md)
2. Read [CANONICAL_EVENT_ENVELOPE.md](./CANONICAL_EVENT_ENVELOPE.md)
3. Follow [GETTING_STARTED.md](./GETTING_STARTED.md) setup
4. Pick a task from [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md)

### For Existing Team
- Check current sprint tasks: [Project Board]
- Review PRs: [GitHub PRs]
- See blockers: [Slack #ai-sre-platform]

### For Stakeholders
- Project overview: [README.md](./README.md)
- Implementation timeline: [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md)
- Architecture decisions: [architecture/adr/](./architecture/adr/)

---

## 📅 Milestones

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| **Phase 1 Complete** (Foundation) | Week 2 | 🟡 In Progress |
| **Phase 2 Complete** (Kafka) | Week 4 | ⚪ Not Started |
| **Phase 3 Complete** (Agents) | Week 8 | ⚪ Not Started |
| **MVP Demo** | Week 10 | ⚪ Not Started |
| **Production Pilot** | Week 12 | ⚪ Not Started |
| **General Availability** | Week 16 | ⚪ Not Started |

---

## 🔄 Document Updates

| Date | Document | Change |
|------|----------|--------|
| 2025-10-30 | All | Initial creation |

---

## 📝 Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) (coming soon) for:
- Code style guide
- PR process
- Testing requirements
- Documentation standards

---

**Questions?** Ask in `#ai-sre-platform` Slack channel or email the team.

---

**Let's build an AI SRE that actually works! 🚀**