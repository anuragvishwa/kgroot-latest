# Implementation Roadmap - AI SRE Platform

> **Timeline**: 12-16 weeks to production-ready
> **Approach**: Incremental delivery - each phase delivers working features
> **Team Size**: 2-3 engineers recommended

---

## Overview

This roadmap takes you from **design** → **MVP** → **production-ready** → **advanced features**.

Each phase:
- ✅ Delivers working, testable features
- ✅ Builds on previous phases
- ✅ Can be demoed to stakeholders
- ✅ Has clear success criteria

---

## Phase 0: Preparation (Week 0)

### Goals
- Set up development environment
- Review existing codebase
- Align team on architecture

### Tasks

#### 0.1: Environment Setup
```bash
# Install dependencies
brew install kafka confluent-platform
brew install neo4j
brew install redis
brew install postgresql

# Or use Docker
docker-compose -f docker/docker-compose.yml up -d
```

#### 0.2: Review Existing Code
- [ ] Review existing [rca_orchestrator.py](../rca_orchestrator.py)
- [ ] Review existing [rca.py](../rca-api/src/api/rca.py)
- [ ] Review Neo4j queries in [COMPLETE-RCA-SYSTEM-GUIDE.md](../COMPLETE-RCA-SYSTEM-GUIDE.md)
- [ ] Test current causality builder endpoint

#### 0.3: Architecture Alignment
- [ ] Team reviews [README.md](./README.md)
- [ ] Team reviews [CANONICAL_EVENT_ENVELOPE.md](./CANONICAL_EVENT_ENVELOPE.md)
- [ ] Create ADR (Architecture Decision Record) for key decisions
- [ ] Set up project board (Jira/GitHub Projects)

### Deliverables
- ✅ Local dev environment running
- ✅ Team aligned on architecture
- ✅ Project board created

### Success Criteria
- All team members can run existing RCA API locally
- Team understands canonical event envelope concept

---

## Phase 1: Foundation (Week 1-2)

### Goals
- Build core abstractions (Tool Registry, Agent Base)
- Wrap existing Neo4j RCA as GraphAgent
- Create simple orchestrator

### Tasks

#### 1.1: Core Infrastructure (Week 1, Days 1-2)

**Create base classes**:

```python
# src/core/schemas.py - Pydantic models
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime

class IncidentScope(BaseModel):
    tenant_id: str
    service: Optional[str] = None
    time_window: Dict[str, datetime]
    pivot_event_id: Optional[str] = None
    correlation_ids: Dict[str, str] = {}

class AgentFinding(BaseModel):
    kind: str
    detail: Dict[str, Any]
    confidence: float

class AgentResult(BaseModel):
    agent: str
    findings: List[AgentFinding]
    artifacts: List[Dict[str, Any]] = []
    cost: Dict[str, float] = {"llm_usd": 0.0, "api_usd": 0.0}
    latency_ms: int

class InvestigationResult(BaseModel):
    incident_id: str
    tenant_id: str
    query: str
    scope: IncidentScope
    agent_results: Dict[str, AgentResult]
    synthesis: Dict[str, Any]
    confidence: float
    total_cost_usd: float
    total_latency_ms: int
```

```python
# src/core/tool_registry.py - Tool plugin system
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class ToolMetadata(BaseModel):
    name: str
    description: str
    category: str  # graph, metrics, logs, code, context
    requires_auth: bool = False
    rate_limit_per_min: int = 60
    cost_per_call: float = 0.0

class BaseTool(ABC):
    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        pass

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Return JSON schema for LLM function calling"""
        pass

class ToolRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, tool: BaseTool):
        self._tools[tool.metadata.name] = tool
        logger.info(f"Registered tool: {tool.metadata.name}")

    def get_tool(self, name: str) -> BaseTool:
        return self._tools.get(name)

    def get_tools_by_category(self, category: str) -> List[BaseTool]:
        return [t for t in self._tools.values()
                if t.metadata.category == category]

    def get_all_schemas(self) -> List[Dict]:
        return [t.get_schema() for t in self._tools.values()]

# Global singleton
tool_registry = ToolRegistry()
```

**Checklist**:
- [ ] Create `src/core/schemas.py`
- [ ] Create `src/core/tool_registry.py`
- [ ] Write unit tests for tool registry
- [ ] Test tool registration and retrieval

#### 1.2: Agent Base Classes (Week 1, Days 3-4)

```python
# src/agents/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from pydantic import BaseModel
from src.core.tool_registry import BaseTool
import logging

logger = logging.getLogger(__name__)

class AgentCapability(BaseModel):
    name: str
    description: str
    tools: List[str]
    expertise: str

class BaseAgent(ABC):
    def __init__(self, llm_client, tools: List[BaseTool]):
        self.llm = llm_client
        self.tools = {t.metadata.name: t for t in tools}
        logger.info(f"Initialized {self.capability.name} with {len(tools)} tools")

    @property
    @abstractmethod
    def capability(self) -> AgentCapability:
        pass

    @abstractmethod
    async def investigate(self, query: str, scope: Dict) -> Dict[str, Any]:
        """Main investigation method"""
        pass

    async def _call_tool(self, tool_name: str, params: Dict) -> Dict[str, Any]:
        """Helper to call a tool with error handling"""
        tool = self.tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name} not available to {self.capability.name}")

        try:
            result = await tool.execute(params)
            return result
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {"success": False, "error": str(e)}
```

**Checklist**:
- [ ] Create `src/agents/base.py`
- [ ] Write unit tests
- [ ] Document agent lifecycle

#### 1.3: GraphAgent - Wrap Existing Neo4j RCA (Week 1, Day 5 - Week 2, Day 1)

```python
# src/tools/graph_tools.py
from src.core.tool_registry import BaseTool, ToolMetadata, tool_registry
from typing import Dict, Any

class Neo4jRootCauseTool(BaseTool):
    def __init__(self, neo4j_service):
        self.neo4j = neo4j_service
        tool_registry.register(self)

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="neo4j_find_root_causes",
            description="Find root causes from Neo4j causality graph",
            category="graph",
            requires_auth=False
        )

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        client_id = params['client_id']
        time_range_hours = params.get('time_range_hours', 24)

        # Call existing Neo4j service
        root_causes = self.neo4j.find_root_causes(
            client_id=client_id,
            time_range_hours=time_range_hours,
            limit=10
        )

        return {
            "tool": self.metadata.name,
            "success": True,
            "data": root_causes,
            "count": len(root_causes)
        }

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_id": {"type": "string"},
                        "time_range_hours": {"type": "integer", "default": 24}
                    },
                    "required": ["client_id"]
                }
            }
        }

# Similarly: Neo4jCausalChainTool, Neo4jBlastRadiusTool, etc.
```

```python
# src/agents/graph_agent.py
from src.agents.base import BaseAgent, AgentCapability
from src.core.schemas import AgentResult, AgentFinding
import time

class GraphAgent(BaseAgent):
    @property
    def capability(self) -> AgentCapability:
        return AgentCapability(
            name="GraphAgent",
            description="Analyzes Neo4j causality graphs and topology",
            tools=[
                "neo4j_find_root_causes",
                "neo4j_get_causal_chain",
                "neo4j_blast_radius"
            ],
            expertise="Kubernetes event causality, topology-aware RCA"
        )

    async def investigate(self, query: str, scope: Dict) -> AgentResult:
        start_time = time.time()
        findings = []

        # Step 1: Find root causes
        root_result = await self._call_tool("neo4j_find_root_causes", {
            "client_id": scope['tenant_id'],
            "time_range_hours": 24
        })

        if root_result['success'] and root_result['count'] > 0:
            for rc in root_result['data'][:3]:
                findings.append(AgentFinding(
                    kind="root_cause",
                    detail=rc,
                    confidence=rc.get('confidence', 0.8)
                ))

            # Step 2: Get causal chains
            for rc in root_result['data'][:1]:
                chain_result = await self._call_tool("neo4j_get_causal_chain", {
                    "event_id": rc['event_id'],
                    "client_id": scope['tenant_id']
                })
                if chain_result['success']:
                    findings.append(AgentFinding(
                        kind="causal_chain",
                        detail=chain_result['data'],
                        confidence=0.9
                    ))

        latency_ms = int((time.time() - start_time) * 1000)

        return AgentResult(
            agent=self.capability.name,
            findings=findings,
            cost={"llm_usd": 0.0, "api_usd": 0.0},
            latency_ms=latency_ms
        )
```

**Checklist**:
- [ ] Create graph tools (wrap existing Neo4j service)
- [ ] Create GraphAgent
- [ ] Write integration tests
- [ ] Test with real Neo4j data

#### 1.4: Simple Orchestrator (Week 2, Days 2-4)

```python
# src/orchestrator/orchestrator.py
from src.core.tool_registry import tool_registry
from src.core.schemas import IncidentScope, InvestigationResult
from src.agents.graph_agent import GraphAgent
from typing import Dict, Any
import time
import uuid

class SimpleOrchestrator:
    def __init__(self, neo4j_service):
        # Initialize tools
        from src.tools.graph_tools import (
            Neo4jRootCauseTool,
            Neo4jCausalChainTool,
            Neo4jBlastRadiusTool
        )

        Neo4jRootCauseTool(neo4j_service)
        Neo4jCausalChainTool(neo4j_service)
        Neo4jBlastRadiusTool(neo4j_service)

        # Initialize agents
        graph_tools = tool_registry.get_tools_by_category('graph')
        self.graph_agent = GraphAgent(llm_client=None, tools=graph_tools)

    async def investigate(
        self,
        query: str,
        tenant_id: str,
        time_window: Dict[str, str]
    ) -> InvestigationResult:
        """Simple investigation - just GraphAgent for now"""

        incident_id = f"inc-{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        # Create scope
        scope = {
            "tenant_id": tenant_id,
            "time_window": time_window
        }

        # Execute GraphAgent
        graph_result = await self.graph_agent.investigate(query, scope)

        # Simple synthesis (no LLM yet)
        synthesis = {
            "summary": f"Found {len(graph_result.findings)} findings from causality graph",
            "root_causes": [f for f in graph_result.findings if f.kind == "root_cause"],
            "confidence": max([f.confidence for f in graph_result.findings], default=0.0)
        }

        total_latency = int((time.time() - start_time) * 1000)

        return InvestigationResult(
            incident_id=incident_id,
            tenant_id=tenant_id,
            query=query,
            scope=IncidentScope(**scope),
            agent_results={"GraphAgent": graph_result},
            synthesis=synthesis,
            confidence=synthesis['confidence'],
            total_cost_usd=0.0,
            total_latency_ms=total_latency
        )
```

**Checklist**:
- [ ] Create simple orchestrator
- [ ] Create FastAPI endpoint
- [ ] Test end-to-end flow
- [ ] Write integration tests

#### 1.5: API Endpoint (Week 2, Day 5)

```python
# src/api/routes/investigate.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
from src.orchestrator.orchestrator import SimpleOrchestrator

router = APIRouter()
orchestrator = None  # Initialize in main.py

class InvestigateRequest(BaseModel):
    query: str
    tenant_id: str
    time_window: Dict[str, str]

@router.post("/investigate")
async def investigate_incident(request: InvestigateRequest):
    try:
        result = await orchestrator.investigate(
            query=request.query,
            tenant_id=request.tenant_id,
            time_window=request.time_window
        )
        return result.dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Checklist**:
- [ ] Create FastAPI app
- [ ] Add `/investigate` endpoint
- [ ] Test with curl/Postman
- [ ] Add basic error handling

### Deliverables (Phase 1)
- ✅ Tool Registry working
- ✅ GraphAgent wrapping existing Neo4j RCA
- ✅ Simple orchestrator
- ✅ REST API endpoint

### Success Criteria
- GraphAgent can query Neo4j and return root causes
- API endpoint `/investigate` returns structured results
- End-to-end test passes: query → orchestrator → GraphAgent → Neo4j → response

### Demo
```bash
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

## Phase 2: Kafka Ingestion (Week 3-4)

### Goals
- Set up Kafka topics
- Build canonical event envelope processor
- Stream K8s events → Kafka → Neo4j

### Tasks

#### 2.1: Kafka Infrastructure (Week 3, Days 1-2)

```bash
# scripts/setup_kafka_topics.sh
#!/bin/bash

KAFKA_BROKER="localhost:9092"
TENANTS=("acme-01" "startupxyz")
SOURCES=("k8s-events" "k8s-state" "datadog-metrics" "argo-logs" "cicd-events" "slack-incidents")

for tenant in "${TENANTS[@]}"; do
  for source in "${SOURCES[@]}"; do
    TOPIC="${source}-${tenant}"
    echo "Creating topic: ${TOPIC}"

    kafka-topics --create \
      --bootstrap-server ${KAFKA_BROKER} \
      --topic ${TOPIC} \
      --partitions 6 \
      --replication-factor 3 \
      --config retention.ms=604800000 \
      --if-not-exists
  done
done

# Create audit topic
kafka-topics --create \
  --bootstrap-server ${KAFKA_BROKER} \
  --topic audit-orchestrator \
  --partitions 3 \
  --replication-factor 3 \
  --if-not-exists
```

**Checklist**:
- [ ] Run Kafka locally or on cluster
- [ ] Create topics for 2 test tenants
- [ ] Verify topics created: `kafka-topics --list`

#### 2.2: Event Envelope Processor (Week 3, Days 3-5)

```python
# src/ingestion/envelope.py
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

class CanonicalEvent(BaseModel):
    tenant_id: str
    source: str
    event_type: str
    ts: datetime
    correlation_ids: Dict[str, Optional[str]] = {}
    entity: Dict[str, Any]
    severity: str
    payload: Dict[str, Any]
    ingest_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = "v1"

    @validator('severity')
    def validate_severity(cls, v):
        allowed = ['debug', 'info', 'warn', 'error', 'critical']
        if v not in allowed:
            raise ValueError(f'severity must be one of {allowed}')
        return v

def transform_k8s_event(raw_event: Dict, tenant_id: str) -> CanonicalEvent:
    """Transform K8s event to canonical envelope"""

    involved_obj = raw_event.get("involvedObject", {})
    service = extract_service_from_resource(involved_obj.get("name", ""))

    return CanonicalEvent(
        tenant_id=tenant_id,
        source="k8s.events",
        event_type=raw_event.get("reason", "Unknown"),
        ts=datetime.fromisoformat(raw_event["metadata"]["creationTimestamp"].replace("Z", "+00:00")),
        correlation_ids={},
        entity={
            "cluster": raw_event.get("clusterName", "unknown"),
            "namespace": raw_event["metadata"].get("namespace", "default"),
            "service": service,
            "pod": involved_obj.get("name"),
            "kind": involved_obj.get("kind")
        },
        severity="error" if raw_event.get("type") == "Warning" else "info",
        payload=raw_event
    )

def extract_service_from_resource(resource_name: str) -> str:
    """Extract service name from pod/resource name"""
    # nginx-api-7d8f9b-xyz → nginx-api
    parts = resource_name.rsplit('-', 2)
    return parts[0] if parts else resource_name
```

**Checklist**:
- [ ] Create envelope schema
- [ ] Create transform functions for K8s
- [ ] Write unit tests
- [ ] Validate against sample events

#### 2.3: Kafka Consumer (Week 4, Days 1-3)

```python
# src/ingestion/kafka_consumer.py
from confluent_kafka import Consumer, KafkaError
from src.ingestion.envelope import CanonicalEvent, transform_k8s_event
from src.ingestion.processors.k8s_processor import K8sEventProcessor
import json
import logging

logger = logging.getLogger(__name__)

class MultiTenantKafkaConsumer:
    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        neo4j_service
    ):
        self.consumer = Consumer({
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'latest',
            'enable.auto.commit': False
        })

        self.processors = {
            'k8s-events': K8sEventProcessor(neo4j_service)
        }

    def start(self, topics: list[str]):
        """Start consuming from topics"""
        self.consumer.subscribe(topics)
        logger.info(f"Subscribed to {len(topics)} topics")

        try:
            while True:
                msg = self.consumer.poll(1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error(f"Kafka error: {msg.error()}")
                        break

                # Process message
                await self.process_message(msg)
                self.consumer.commit()

        except KeyboardInterrupt:
            pass
        finally:
            self.consumer.close()

    async def process_message(self, msg):
        """Route message to appropriate processor"""
        topic = msg.topic()
        base_topic = self.extract_base_topic(topic)

        processor = self.processors.get(base_topic)
        if not processor:
            logger.warning(f"No processor for topic: {base_topic}")
            return

        try:
            event = json.loads(msg.value())
            await processor.process(event)
        except Exception as e:
            logger.error(f"Processing error: {e}")

    @staticmethod
    def extract_base_topic(topic: str) -> str:
        """k8s-events-acme-01 → k8s-events"""
        return '-'.join(topic.split('-')[:-1])
```

```python
# src/ingestion/processors/k8s_processor.py
from src.ingestion.envelope import CanonicalEvent
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class K8sEventProcessor:
    def __init__(self, neo4j_service):
        self.neo4j = neo4j_service

    async def process(self, event: CanonicalEvent):
        """Process K8s event → Neo4j"""
        logger.info(f"Processing K8s event: {event.event_type} for {event.tenant_id}")

        # Store in Neo4j (reuse existing logic)
        await self.neo4j.store_event({
            "client_id": event.tenant_id,
            "eid": event.ingest_id,
            "reason": event.event_type,
            "event_time": event.ts,
            "namespace": event.entity.get("namespace"),
            "service": event.entity.get("service"),
            "pod_name": event.entity.get("pod"),
            "severity": event.severity,
            "payload": event.payload
        })

        # Trigger causality building for critical events
        if event.event_type in ['OOMKilled', 'ImagePullBackOff', 'CrashLoopBackOff']:
            logger.info(f"Triggering causality build for {event.tenant_id}")
            # Schedule async task to build causality
            # (Don't block consumer)
```

**Checklist**:
- [ ] Create consumer framework
- [ ] Create K8s event processor
- [ ] Test with sample Kafka messages
- [ ] Add dead-letter queue for errors

#### 2.4: Producer for Testing (Week 4, Days 4-5)

```python
# scripts/load_test_data.py
from confluent_kafka import Producer
from src.ingestion.envelope import transform_k8s_event
import json

def load_k8s_events(tenant_id: str, events: list):
    """Load sample K8s events into Kafka"""

    producer = Producer({'bootstrap.servers': 'localhost:9092'})

    for raw_event in events:
        canonical = transform_k8s_event(raw_event, tenant_id)
        topic = f"k8s-events-{tenant_id}"

        producer.produce(
            topic,
            key=canonical.ingest_id,
            value=canonical.json()
        )

    producer.flush()
    print(f"Loaded {len(events)} events to {topic}")

# Sample data
sample_events = [
    {
        "metadata": {"name": "nginx.oom", "namespace": "payments", "creationTimestamp": "2025-10-30T07:41:03Z"},
        "involvedObject": {"kind": "Pod", "name": "nginx-api-xyz"},
        "reason": "OOMKilled",
        "type": "Warning"
    }
]

load_k8s_events("acme-01", sample_events)
```

**Checklist**:
- [ ] Create test data loader
- [ ] Load sample events
- [ ] Verify events consumed
- [ ] Verify events in Neo4j

### Deliverables (Phase 2)
- ✅ Kafka topics created
- ✅ Canonical envelope processor
- ✅ K8s events → Kafka → Neo4j pipeline working

### Success Criteria
- Events flow: K8s → Kafka → Consumer → Neo4j
- Existing causality builder works with new events
- GraphAgent can query new events

### Demo
```bash
# Terminal 1: Start consumer
python -m src.ingestion.kafka_consumer

# Terminal 2: Load test data
python scripts/load_test_data.py

# Terminal 3: Query via API
curl -X POST http://localhost:8000/api/v1/investigate ...
```

---

## Phase 3: Additional Agents (Week 5-8)

### 3.1: MetricsAgent (Week 5)
### 3.2: LogsAgent (Week 6)
### 3.3: CodeAgent (Week 7)
### 3.4: ContextAgent (Week 8)

(See detailed implementation in separate docs)

---

## Phase 4: Intelligence Layer (Week 9-10)

### 4.1: Rule-Based Router
### 4.2: LLM Planner
### 4.3: Result Synthesizer

---

## Phase 5: Production Hardening (Week 11-12)

### 5.1: Circuit Breakers
### 5.2: Observability
### 5.3: Security

---

## Phase 6: Advanced Features (Week 13+)

### 6.1: Vector Similarity
### 6.2: Automated Runbooks
### 6.3: Proactive Detection

---

## Next Steps

1. **Review this roadmap** with your team
2. **Create tickets** for Phase 1 tasks
3. **Assign owners** to each task
4. **Start with Phase 1.1** (Core Infrastructure)

**Let's build! 🚀**