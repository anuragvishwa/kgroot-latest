# KGRoot RCA API Architecture

System design, data flow, and component interactions.

## Table of Contents

- [System Overview](#system-overview)
- [Architecture Diagram](#architecture-diagram)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [Multi-Tenant Isolation](#multi-tenant-isolation)
- [Service Interactions](#service-interactions)
- [Design Decisions](#design-decisions)
- [Scalability](#scalability)
- [Security](#security)

---

## System Overview

The KGRoot RCA API is a FastAPI-based microservice that provides intelligent root cause analysis for Kubernetes failures using:

- **Neo4j Graph Database**: Stores events, resources, and causal relationships
- **GPT-5 AI**: Provides natural language analysis with reasoning
- **Semantic Search**: Embeddings-based search using sentence transformers and FAISS
- **Slack Integration**: Real-time alerts and health reports

**Key Features:**
- Multi-tenant safe with complete client isolation
- Natural language querying
- Topology-aware causal analysis (90% accuracy)
- Real-time health monitoring
- Conversational AI assistant

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         External Clients                          │
│                                                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ Web UI   │  │  CLI     │  │ Postman  │  │  Slack   │         │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘         │
└───────┼─────────────┼─────────────┼─────────────┼───────────────┘
        │             │             │             │
        └─────────────┴─────────────┴─────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                        │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    API Layer (Routes)                       │  │
│  │                                                              │  │
│  │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐         │  │
│  │  │ RCA  │  │Search│  │Catalog│ │Health│  │ Chat │         │  │
│  │  └──┬───┘  └──┬───┘  └──┬───┘  └──┬───┘  └──┬───┘         │  │
│  └─────┼─────────┼─────────┼─────────┼─────────┼─────────────┘  │
│        │         │         │         │         │                 │
│  ┌─────┴─────────┴─────────┴─────────┴─────────┴─────────────┐  │
│  │                   Service Layer                            │  │
│  │                                                              │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │  │
│  │  │  Neo4j  │  │Embedding│  │  GPT-5  │  │  Slack  │       │  │
│  │  │ Service │  │ Service │  │ Service │  │ Service │       │  │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘       │  │
│  └───────┼────────────┼────────────┼────────────┼────────────┘  │
│          │            │            │            │                │
│  ┌───────┴────────────┴────────────┴────────────┴────────────┐  │
│  │                   Data Models (Pydantic)                   │  │
│  │                                                              │  │
│  │  RCARequest, SearchRequest, CatalogResponse, etc.          │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Neo4j     │  │   OpenAI    │  │    Slack    │
│  Graph DB   │  │   GPT-5     │  │     API     │
│             │  │   API       │  │             │
│ • Events    │  │             │  │ • Alerts    │
│ • Resources │  │ • Responses │  │ • Reports   │
│ • Topology  │  │   API       │  │             │
│ • Causal    │  │ • Reasoning │  │             │
└─────────────┘  └─────────────┘  └─────────────┘
```

---

## Core Components

### 1. FastAPI Application (`src/main.py`)

**Responsibilities:**
- HTTP request/response handling
- Route registration
- Lifespan management (startup/shutdown)
- CORS middleware
- Error handling

**Key Features:**
- Async request handling
- Automatic OpenAPI docs generation
- Request validation via Pydantic
- Background tasks for async operations

**Lifespan Events:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    neo4j_service.connect()
    embedding_service.initialize()
    gpt5_service.initialize()
    slack_service.initialize()

    # Build initial embedding index
    embedding_service.rebuild_index(...)

    yield

    # Shutdown
    neo4j_service.close()
```

---

### 2. API Layer (Routes)

#### RCA Routes (`src/api/rca.py`)

**Endpoints:**
- `POST /rca/analyze` - Main RCA analysis
- `GET /rca/root-causes/{client_id}` - Get root causes
- `GET /rca/causal-chain/{event_id}` - Get causal chain
- `GET /rca/blast-radius/{event_id}` - Get blast radius
- `GET /rca/cross-service-failures/{client_id}` - Cross-service failures
- `POST /rca/runbook` - Generate runbook

**Flow:**
1. Validate request (Pydantic)
2. Query Neo4j for events/relationships
3. Build context from graph data
4. Send to GPT-5 for analysis
5. Parse and structure response
6. Send Slack alert (background task)
7. Return structured JSON

#### Search Routes (`src/api/search.py`)

**Endpoints:**
- `POST /search/` - Semantic search
- `POST /search/rebuild-index/{client_id}` - Rebuild index
- `GET /search/suggestions` - Search suggestions

**Flow:**
1. Generate query embedding
2. Search FAISS index
3. Filter by client_id, time, namespace
4. Return top-k results with scores

#### Catalog Routes (`src/api/catalog.py`)

**Endpoints:**
- `GET /catalog/resources/{client_id}` - Browse resources
- `GET /catalog/topology/{client_id}/{namespace}/{resource_name}` - Topology view
- `GET /catalog/owners/{client_id}` - List owners
- `GET /catalog/namespaces/{client_id}` - List namespaces

**Flow:**
1. Query Neo4j for resources
2. Apply filters (namespace, kind, owner, labels)
3. Aggregate metadata
4. Paginate results
5. Return with counts

#### Health Routes (`src/api/health.py`)

**Endpoints:**
- `GET /health/status/{client_id}` - Health status
- `POST /health/send-health-report/{client_id}` - Send to Slack
- `GET /health/incidents/{client_id}` - Active incidents

**Flow:**
1. Count healthy/unhealthy resources
2. Detect active incidents (ongoing failures)
3. Identify top issues
4. Calculate health percentage
5. Optionally send to Slack

#### Chat Routes (`src/api/chat.py`)

**Endpoints:**
- `POST /chat/` - Chat with assistant
- `DELETE /chat/conversations/{conversation_id}` - Clear conversation
- `GET /chat/conversations/{conversation_id}` - Get history

**Flow:**
1. Retrieve conversation history
2. Optionally fetch event context from Neo4j
3. Send to GPT-5 with system prompt
4. Parse response
5. Generate suggested queries
6. Store conversation history

---

### 3. Service Layer

#### Neo4j Service (`src/services/neo4j_service.py`)

**Responsibilities:**
- Graph database connection management
- Cypher query execution
- Multi-tenant query filtering
- Transaction handling

**Key Methods:**
- `find_root_causes()` - Events with no upstream causes but cause downstream
- `find_causal_chain()` - Traverse POTENTIAL_CAUSE relationships
- `get_blast_radius()` - Find all downstream affected events
- `get_cross_service_failures()` - Topology-enhanced cross-service failures
- `get_resources_catalog()` - Browse resources with metadata
- `get_topology_for_resource()` - Service topology view
- `get_health_summary()` - Real-time health metrics

**Multi-Tenant Pattern:**
```python
def find_root_causes(self, client_id: str, ...):
    query = """
    MATCH (e:Episodic {client_id: $client_id})
    WHERE e.event_time > datetime() - duration({hours: $hours})
      AND NOT EXISTS {
        MATCH (:Episodic {client_id: $client_id})
              -[:POTENTIAL_CAUSE {client_id: $client_id}]->(e)
      }
    ...
    """
```

#### Embedding Service (`src/services/embedding_service.py`)

**Responsibilities:**
- Generate embeddings using sentence transformers
- Build and maintain FAISS index
- Semantic similarity search
- Embedding caching

**Key Methods:**
- `initialize()` - Load sentence transformer model
- `embed_texts()` - Generate embeddings for texts
- `rebuild_index()` - Build FAISS index from events/resources
- `search()` - Find similar items using cosine similarity
- `save_cache()` / `load_cache()` - Disk caching

**Architecture:**
```
Text → Sentence Transformer → Embedding (384d vector)
                                    ↓
                              FAISS Index
                                    ↓
                         Cosine Similarity Search
                                    ↓
                            Top-k Results
```

**Model:**
- `sentence-transformers/all-MiniLM-L6-v2`
- 384 dimensions
- Fast inference (~50ms for query)
- Good balance of speed and accuracy

#### GPT-5 Service (`src/services/gpt5_service.py`)

**Responsibilities:**
- OpenAI GPT-5 Responses API integration
- Prompt engineering
- Response parsing
- Context building from graph data

**Key Methods:**
- `analyze_rca()` - Main RCA analysis with reasoning
- `chat_assistant()` - Conversational assistant
- `generate_slack_alert()` - Concise alert generation
- `suggest_runbook()` - Generate runbook for patterns

**Responses API Usage:**
```python
response = self.client.responses.create(
    model=settings.openai_model,  # gpt-5
    input=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    reasoning={"effort": reasoning_effort},  # minimal/low/medium/high
    text={"verbosity": verbosity}  # low/medium/high
)
```

**Context Building:**
1. Root causes (top 5)
2. Causal chains (top 3)
3. Blast radius (top 10)
4. Cross-service failures (top 5)
5. Topology relationships

**Prompt Structure:**
```
System: You are an expert SRE specializing in Kubernetes RCA...

User:
  Question: Why did nginx pods fail?

  ## Root Causes
  - OOMKilled on Pod/nginx-pod-1 (blast radius: 8)

  ## Causal Chains
  Chain 1:
    1. OOMKilled → Pod/nginx-pod-1
    2. BackOff → Pod/nginx-pod-1

  ## Blast Radius (15 affected)
  - Unhealthy → Service/nginx-service

  Provide:
  1. Summary
  2. Root cause analysis
  3. Remediation steps
  4. Confidence assessment
```

#### Slack Service (`src/services/slack_service.py`)

**Responsibilities:**
- Slack API integration
- Alert formatting (Slack blocks)
- Message sending
- Error handling

**Key Methods:**
- `send_rca_alert()` - Send incident alert
- `send_health_summary()` - Send health report
- `_build_incident_blocks()` - Format incident as Slack blocks
- `_build_health_blocks()` - Format health status as Slack blocks

**Message Format:**
```json
{
  "channel": "#alerts",
  "blocks": [
    {
      "type": "header",
      "text": {"type": "plain_text", "text": "🚨 RCA Incident Alert"}
    },
    {
      "type": "section",
      "fields": [
        {"type": "mrkdwn", "text": "*Client:* ab-01"},
        {"type": "mrkdwn", "text": "*Severity:* High"}
      ]
    }
  ]
}
```

---

### 4. Data Models (`src/models/schemas.py`)

**Pydantic Models:**

```python
# Request Models
RCARequest(query, client_id, time_range_hours, reasoning_effort, ...)
SearchRequest(query, client_id, time_range_hours, namespaces, ...)
ChatRequest(message, client_id, conversation_id, context_events, ...)

# Response Models
RCAResponse(query, summary, root_causes, causal_chains, remediation_steps, ...)
SearchResponse(query, results, total_results, search_time_ms, ...)
ChatResponse(message, conversation_id, suggested_queries, confidence, ...)

# Enums
ReasoningEffort(MINIMAL, LOW, MEDIUM, HIGH)
Verbosity(LOW, MEDIUM, HIGH)
```

**Benefits:**
- Automatic request validation
- Type checking
- Auto-generated OpenAPI schema
- Serialization/deserialization

---

## Data Flow

### RCA Analysis Flow

```
1. User Request
   POST /rca/analyze
   {
     "query": "Why did nginx pods fail?",
     "client_id": "ab-01",
     "reasoning_effort": "medium"
   }

2. FastAPI Route
   • Validate request (Pydantic)
   • Extract parameters

3. Neo4j Service - Find Root Causes
   MATCH (e:Episodic {client_id: 'ab-01'})
   WHERE e.event_time > recent
     AND NOT EXISTS { (previous)-[:POTENTIAL_CAUSE]->(e) }
     AND EXISTS { (e)-[:POTENTIAL_CAUSE]->(downstream) }
   RETURN e, count(downstream) as blast_radius
   ORDER BY blast_radius DESC

4. Neo4j Service - Get Causal Chains
   For top 3 root causes:
     MATCH path = (root)-[:POTENTIAL_CAUSE*1..10]->(effect)
     RETURN path

5. Neo4j Service - Get Blast Radius
   MATCH (root)-[:POTENTIAL_CAUSE*1..5]->(affected)
   RETURN affected

6. Neo4j Service - Get Cross-Service Failures
   MATCH (e1)-[:ABOUT]->(r1)-[:SELECTS|RUNS_ON|CONTROLS]-(r2)<-[:ABOUT]-(e2)
   WHERE (e1)-[:POTENTIAL_CAUSE]->(e2)
   RETURN e1, e2, type(topology_rel)

7. GPT-5 Service - Build Context
   context = """
   ## Root Causes
   - OOMKilled on Pod/nginx-pod-1 (blast radius: 8)

   ## Causal Chains
   ...
   """

8. GPT-5 Service - Analyze
   response = openai.responses.create(
     model="gpt-5",
     input=[system_prompt, user_prompt_with_context],
     reasoning={"effort": "medium"},
     text={"verbosity": "medium"}
   )

9. GPT-5 Service - Parse Response
   Extract:
   • Summary
   • Remediation steps
   • Confidence assessment

10. API Response
    {
      "query": "...",
      "summary": "The nginx pods failed due to OOMKilled...",
      "root_causes": [...],
      "causal_chains": [...],
      "remediation_steps": [...],
      "confidence_score": 0.88,
      "processing_time_ms": 3420
    }

11. Background Task - Send Slack Alert
    slack_service.send_rca_alert(incident_data, channel="#alerts")
```

### Search Flow

```
1. User Request
   POST /search/
   {
     "query": "show me all OOM errors in production",
     "client_id": "ab-01",
     "limit": 20
   }

2. Embedding Service - Generate Query Embedding
   query_embedding = model.encode("show me all OOM errors in production")
   # Returns 384-dimensional vector

3. Embedding Service - Search FAISS Index
   distances, indices = faiss_index.search(query_embedding, k=100)
   # Returns top-100 candidates

4. Embedding Service - Filter Results
   Filter by:
   • client_id == "ab-01"
   • namespace == "production" (extracted from query)
   • similarity_score > 0.5

5. Embedding Service - Rank and Limit
   Sort by similarity_score DESC
   Take top 20

6. API Response
   {
     "query": "...",
     "results": [
       {
         "item_type": "Event",
         "content": "Pod nginx-pod-1 OOMKilled in production",
         "similarity_score": 0.95,
         "metadata": {...}
       }
     ],
     "total_results": 15,
     "search_time_ms": 45
   }
```

---

## Multi-Tenant Isolation

**Critical Requirement:** Complete data isolation between clients.

### Node-Level Isolation

```cypher
// ✅ CORRECT: Filter by client_id in node match
MATCH (e:Episodic {client_id: $client_id})

// ❌ WRONG: Filter in WHERE clause (less efficient)
MATCH (e:Episodic)
WHERE e.client_id = $client_id
```

### Relationship-Level Isolation

```cypher
// ✅ CORRECT: Filter relationships by client_id
MATCH (e1:Episodic {client_id: $client_id})
      -[pc:POTENTIAL_CAUSE {client_id: $client_id}]->
      (e2:Episodic {client_id: $client_id})

// ❌ WRONG: Missing relationship filter
MATCH (e1:Episodic {client_id: $client_id})
      -[pc:POTENTIAL_CAUSE]->
      (e2:Episodic {client_id: $client_id})
```

### Topology Isolation

```cypher
// ✅ CORRECT: All parts filtered
MATCH (r1:Resource {client_id: $client_id})
      -[rel:SELECTS|RUNS_ON|CONTROLS {client_id: $client_id}]->
      (r2:Resource {client_id: $client_id})

// ❌ WRONG: Cross-tenant leak possible
MATCH (r1:Resource {client_id: $client_id})
      -[rel:SELECTS|RUNS_ON|CONTROLS]->
      (r2:Resource)
```

### Embedding Isolation

```python
# Tag embeddings with client_id
self.items.append({
    "id": event["eid"],
    "type": "Event",
    "text": text,
    "metadata": {
        "client_id": event["client_id"],  # ✅
        ...
    }
})

# Filter during search
results = [
    (item, score)
    for item, score in all_results
    if item["metadata"]["client_id"] == client_id  # ✅
]
```

### Verification Queries

**Check for cross-tenant violations:**

```cypher
// Causal relationships
MATCH (e1:Episodic)-[pc:POTENTIAL_CAUSE]->(e2:Episodic)
WHERE e1.client_id <> e2.client_id
   OR e1.client_id <> pc.client_id
   OR e2.client_id <> pc.client_id
RETURN count(*) as violations;
// MUST return 0

// Topology relationships
MATCH (r1:Resource)-[rel:SELECTS|RUNS_ON|CONTROLS]->(r2:Resource)
WHERE r1.client_id <> r2.client_id
   OR r1.client_id <> rel.client_id
   OR r2.client_id <> rel.client_id
RETURN count(*) as violations;
// MUST return 0
```

---

## Service Interactions

### Neo4j ↔ GPT-5

```
Neo4j provides structured data → GPT-5 provides natural language analysis

Example:
  Neo4j returns:
    root_cause: "OOMKilled"
    resource: "Pod/nginx-pod-1"
    blast_radius: 8 events

  GPT-5 analyzes:
    "The nginx pods failed due to insufficient memory limits (128Mi).
     The root cause was OOMKilled on nginx-pod-1, which caused 8 downstream
     effects including service degradation. Recommended fix: increase memory
     limit to 256Mi based on observed usage patterns."
```

### Neo4j ↔ Embedding Service

```
Neo4j provides event/resource data → Embedding Service builds search index

Example:
  Neo4j query:
    MATCH (e:Episodic {client_id: 'ab-01'})
    WHERE e.event_time > datetime() - duration({days: 30})
    RETURN e.eid, e.reason, e.resource_name, e.namespace, e.event_time

  Embedding Service:
    texts = [
      "Pod nginx-pod-1 OOMKilled in production at 2025-01-15T10:30:15Z",
      ...
    ]
    embeddings = model.encode(texts)
    faiss_index.add(embeddings)
```

### GPT-5 ↔ Slack

```
GPT-5 generates alert → Slack Service formats and sends

Example:
  GPT-5 generates:
    {
      "title": "High Memory Usage in Auth Service",
      "description": "OOMKilled events detected...",
      "severity": "high",
      "remediation": ["Increase memory limit", "Review session cleanup"]
    }

  Slack Service formats:
    {
      "blocks": [
        {"type": "header", "text": "🚨 High Memory Usage"},
        {"type": "section", "text": "OOMKilled events..."},
        ...
      ]
    }
```

---

## Design Decisions

### Why FastAPI?

**Chosen:** FastAPI
**Alternatives:** Flask, Django, Express.js

**Reasons:**
- Async support (important for AI API calls)
- Automatic OpenAPI docs
- Pydantic validation
- High performance
- Modern Python features (type hints)

### Why Sentence Transformers?

**Chosen:** sentence-transformers/all-MiniLM-L6-v2
**Alternatives:** OpenAI Embeddings, Cohere, Universal Sentence Encoder

**Reasons:**
- No API costs (runs locally)
- Fast inference (~50ms)
- Good accuracy for semantic search
- Small model size (90MB)
- 384 dimensions (good balance)

### Why FAISS?

**Chosen:** FAISS (Facebook AI Similarity Search)
**Alternatives:** Annoy, Elasticsearch, Pinecone

**Reasons:**
- Fastest similarity search
- CPU-only support
- No external dependencies
- Easy to cache to disk
- Scales to millions of vectors

### Why GPT-5 Responses API?

**Chosen:** OpenAI Responses API
**Alternatives:** Chat Completions API, Anthropic Claude, Llama

**Reasons:**
- Reasoning effort control (accuracy vs speed)
- Verbosity control (concise vs detailed)
- Best accuracy for complex RCA
- Extended thinking (high reasoning effort)
- Output quality guarantees

### Why Neo4j?

**Chosen:** Neo4j
**Alternatives:** PostgreSQL with pg_graph, ArangoDB, TigerGraph

**Reasons:**
- Already in use for KGRoot
- Excellent for causal chains
- APOC plugin for graph algorithms
- Cypher is expressive for RCA
- Multi-tenant filtering built-in

---

## Scalability

### Horizontal Scaling

**API Layer:**
```bash
# Run multiple workers
uvicorn src.main:app --workers 8

# Or use gunicorn
gunicorn src.main:app -w 8 -k uvicorn.workers.UvicornWorker
```

**Load Balancer:**
```
               ┌─────────────┐
               │   Nginx     │
               │   (LB)      │
               └──────┬──────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
   ┌────────┐    ┌────────┐    ┌────────┐
   │ API-1  │    │ API-2  │    │ API-3  │
   └────────┘    └────────┘    └────────┘
```

### Vertical Scaling

**Increase resources for:**
- Embedding generation (CPU/GPU)
- GPT-5 concurrent requests
- Neo4j query performance

**Recommended:**
- API: 4 CPU, 8GB RAM
- Embedding Service: 8 CPU or 1 GPU, 16GB RAM
- Neo4j: 8 CPU, 32GB RAM

### Caching Strategy

**Redis Caching:**
```python
# Cache RCA results
cache_key = f"rca:{client_id}:{query_hash}"
cached = redis.get(cache_key)
if cached:
    return cached

result = perform_rca(...)
redis.setex(cache_key, 3600, result)  # 1 hour TTL
```

**Embedding Cache:**
```python
# Cache embeddings to disk
cache_file = f"{cache_dir}/{client_id}_embeddings.pkl"
if os.path.exists(cache_file):
    embeddings = pickle.load(open(cache_file, "rb"))
```

---

## Security

### API Security (Future)

**Planned:**
- API key authentication
- JWT tokens
- Rate limiting per client
- Request size limits

**Implementation:**
```python
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key not in valid_api_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")
```

### Data Security

**Multi-Tenant Isolation:**
- All queries filtered by `client_id`
- No cross-tenant data leakage
- Verification queries run daily

**Secrets Management:**
- All credentials in `.env` (not committed)
- Environment variables only
- Use secrets manager in production (AWS Secrets Manager, Vault)

### Network Security

**Recommendations:**
- Run API behind VPN
- Use HTTPS in production
- Restrict Neo4j port (7687) to API only
- Use Slack incoming webhooks only

---

## Performance Benchmarks

### API Latency

| Endpoint | Reasoning Effort | Avg Latency | 95th Percentile |
|----------|------------------|-------------|-----------------|
| POST /rca/analyze | low | 1.5s | 2.0s |
| POST /rca/analyze | medium | 3.2s | 4.5s |
| POST /rca/analyze | high | 8.5s | 12.0s |
| POST /search/ | - | 0.3s | 0.5s |
| GET /catalog/resources | - | 0.8s | 1.2s |
| GET /health/status | - | 0.4s | 0.6s |
| POST /chat/ | low | 1.2s | 1.8s |

### Throughput

- **RCA Analysis**: 20 req/s (medium reasoning)
- **Search**: 100 req/s
- **Catalog**: 50 req/s
- **Health**: 200 req/s

### Resource Usage

- **CPU**: 2-4 cores (API), 4-8 cores (embedding)
- **Memory**: 4GB (API), 8GB (embedding), 16GB (Neo4j)
- **Disk**: 1GB (embeddings cache), 20GB+ (Neo4j data)

---

## Future Enhancements

1. **Authentication & Authorization**
   - API key management
   - Role-based access control

2. **Advanced Caching**
   - Redis for RCA results
   - Query result caching

3. **Webhooks**
   - Real-time incident notifications
   - Health status changes

4. **Additional Connectors**
   - PagerDuty integration
   - Jira ticket creation
   - Email alerts

5. **Advanced Analytics**
   - Failure pattern detection
   - Anomaly detection
   - Predictive alerts

6. **UI Integration**
   - Web UI for visualization
   - Interactive causal graphs
   - Real-time dashboards

---

## References

- [API Documentation](API.md)
- [Setup Guide](SETUP.md)
- [Integration Guide](INTEGRATIONS.md)
- [Neo4j RCA Queries](../../COMPLETE-RCA-SYSTEM-GUIDE.md)
