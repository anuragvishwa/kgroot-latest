# KGRoot RCA API Reference

Complete API documentation for all endpoints.

## Base URL

```
http://localhost:8083
```

## Authentication

Currently no authentication required. Future versions will support:
- API Key authentication
- OAuth2 integration
- JWT tokens

---

## RCA Analysis Endpoints

### POST /rca/analyze

Perform intelligent RCA analysis using GPT-5 and Neo4j.

**Request Body:**

```json
{
  "query": "Why did nginx pods fail in the default namespace?",
  "client_id": "ab-01",
  "time_range_hours": 24,
  "reasoning_effort": "medium",
  "verbosity": "medium",
  "include_remediation": true
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| query | string | Yes | Natural language question about failures |
| client_id | string | No | Client ID for multi-tenancy |
| time_range_hours | integer | No | Look back hours (default: 24, min: 1, max: 168) |
| reasoning_effort | enum | No | GPT-5 reasoning level: minimal, low, medium (default), high |
| verbosity | enum | No | Response verbosity: low, medium (default), high |
| include_remediation | boolean | No | Include fix suggestions (default: true) |

**Response:**

```json
{
  "query": "Why did nginx pods fail in the default namespace?",
  "summary": "The nginx pods failed due to OOMKilled errors. The root cause was insufficient memory limits (128Mi) for the workload, which requires approximately 256Mi under normal load. This caused 3 pod restarts and affected 5 downstream services.",
  "root_causes": [
    {
      "reason": "OOMKilled",
      "resource_kind": "Pod",
      "resource_name": "nginx-deployment-7d4f9c8b6-xk2pl",
      "namespace": "default",
      "timestamp": "2025-01-15T10:30:15Z",
      "confidence": 0.92,
      "blast_radius": 8
    }
  ],
  "causal_chains": [
    [
      {
        "step": 1,
        "event_reason": "OOMKilled",
        "resource": "Pod/nginx-deployment-7d4f9c8b6-xk2pl",
        "namespace": "default",
        "timestamp": "2025-01-15T10:30:15Z",
        "confidence": 0.92,
        "is_root_cause": true
      },
      {
        "step": 2,
        "event_reason": "BackOff",
        "resource": "Pod/nginx-deployment-7d4f9c8b6-xk2pl",
        "namespace": "default",
        "timestamp": "2025-01-15T10:30:45Z",
        "confidence": 0.88,
        "is_root_cause": false
      }
    ]
  ],
  "affected_resources": [
    {
      "reason": "Unhealthy",
      "resource_kind": "Service",
      "resource_name": "nginx-service",
      "namespace": "default",
      "timestamp": "2025-01-15T10:31:00Z",
      "distance_from_root": 2
    }
  ],
  "remediation_steps": [
    "Increase memory limit to 256Mi in deployment spec",
    "kubectl set resources deployment nginx-deployment --limits=memory=256Mi",
    "Monitor memory usage with: kubectl top pods -n default",
    "Consider adding memory requests to prevent pod eviction"
  ],
  "confidence_score": 0.88,
  "reasoning_tokens": 1250,
  "processing_time_ms": 3420
}
```

**Status Codes:**

- `200 OK`: Analysis completed successfully
- `400 Bad Request`: Invalid parameters
- `500 Internal Server Error`: Neo4j or GPT-5 service error

---

### GET /rca/root-causes/{client_id}

Get likely root causes (events with no upstream causes but cause downstream events).

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| client_id | string | Yes | Client ID |

**Query Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| time_range_hours | integer | No | Look back hours (default: 24) |
| limit | integer | No | Max results (default: 10) |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/rca/root-causes/ab-01?time_range_hours=24&limit=10"
```

**Response:**

```json
[
  {
    "event_id": "evt-12345",
    "reason": "OOMKilled",
    "resource_kind": "Pod",
    "resource_name": "nginx-pod-1",
    "namespace": "default",
    "timestamp": "2025-01-15T10:30:15Z",
    "confidence": 0.92,
    "blast_radius": 8,
    "message": "Container killed due to OOM"
  }
]
```

---

### GET /rca/causal-chain/{event_id}

Get the causal chain leading to a specific event.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| event_id | string | Yes | Event ID (eid) |

**Query Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| max_depth | integer | No | Maximum chain depth (default: 10) |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/rca/causal-chain/evt-12345?max_depth=10"
```

**Response:**

```json
{
  "event_id": "evt-12345",
  "causal_chain": [
    {
      "step": 1,
      "event_id": "evt-11111",
      "reason": "OOMKilled",
      "resource": "Pod/nginx-pod-1",
      "namespace": "default",
      "timestamp": "2025-01-15T10:30:00Z",
      "confidence": 0.92
    },
    {
      "step": 2,
      "event_id": "evt-11112",
      "reason": "BackOff",
      "resource": "Pod/nginx-pod-1",
      "namespace": "default",
      "timestamp": "2025-01-15T10:30:30Z",
      "confidence": 0.88
    },
    {
      "step": 3,
      "event_id": "evt-12345",
      "reason": "Failed",
      "resource": "Pod/nginx-pod-1",
      "namespace": "default",
      "timestamp": "2025-01-15T10:31:00Z",
      "confidence": 0.85
    }
  ],
  "chain_length": 3
}
```

---

### GET /rca/blast-radius/{event_id}

Get all events affected by a root cause event.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| event_id | string | Yes | Root cause event ID |

**Query Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| max_depth | integer | No | Maximum propagation depth (default: 5) |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/rca/blast-radius/evt-11111?max_depth=5"
```

**Response:**

```json
{
  "root_cause_event_id": "evt-11111",
  "affected_events": [
    {
      "event_id": "evt-11112",
      "reason": "BackOff",
      "resource": "Pod/nginx-pod-1",
      "namespace": "default",
      "timestamp": "2025-01-15T10:30:30Z",
      "distance_from_root": 1,
      "confidence": 0.88
    },
    {
      "event_id": "evt-11113",
      "reason": "Unhealthy",
      "resource": "Service/nginx-service",
      "namespace": "default",
      "timestamp": "2025-01-15T10:31:00Z",
      "distance_from_root": 2,
      "confidence": 0.82
    }
  ],
  "total_affected": 8,
  "unique_resources": 5,
  "unique_namespaces": 2
}
```

---

### GET /rca/cross-service-failures/{client_id}

Get cross-service failures detected via topology relationships.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| client_id | string | Yes | Client ID |

**Query Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| time_range_hours | integer | No | Look back hours (default: 24) |
| min_confidence | float | No | Minimum confidence score (default: 0.7) |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/rca/cross-service-failures/ab-01?time_range_hours=24&min_confidence=0.7"
```

**Response:**

```json
[
  {
    "cause_event_id": "evt-11111",
    "cause_reason": "OOMKilled",
    "cause_resource": "Pod/nginx-pod-1",
    "cause_namespace": "default",
    "effect_event_id": "evt-11113",
    "effect_reason": "Unhealthy",
    "effect_resource": "Service/nginx-service",
    "effect_namespace": "default",
    "topology_relationship": "RUNS_ON",
    "confidence": 0.85,
    "time_difference_seconds": 45
  }
]
```

---

### POST /rca/runbook

Generate a runbook for a specific failure pattern using GPT-5.

**Request Body:**

```json
{
  "failure_pattern": "OOMKilled pod restarts in Java applications",
  "resource_type": "Pod"
}
```

**Response:**

```json
{
  "runbook": "## Runbook: OOMKilled Pod Restarts in Java Applications\n\n### Investigation Steps\n1. Check current memory limits: `kubectl describe pod <pod-name>`\n2. Review memory usage: `kubectl top pod <pod-name>`\n3. Analyze heap dumps if available\n4. Check for memory leaks in application logs\n\n### Common Causes\n- Insufficient memory limits\n- Memory leaks in application code\n- Incorrect JVM heap settings\n- High traffic spikes\n\n### Remediation Commands\n```bash\n# Increase memory limit\nkubectl set resources deployment <name> --limits=memory=2Gi\n\n# Update JVM settings\nkubectl set env deployment <name> JAVA_OPTS=\"-Xmx1536m -Xms512m\"\n\n# Restart deployment\nkubectl rollout restart deployment <name>\n```\n\n### Verification Steps\n1. Monitor pod status: `kubectl get pods -w`\n2. Check memory usage: `kubectl top pods`\n3. Verify no OOMKilled events: `kubectl get events | grep OOM`\n4. Monitor for 24 hours to ensure stability",
  "pattern": "OOMKilled pod restarts in Java applications",
  "resource_type": "Pod"
}
```

---

## Search Endpoints

### POST /search/

Natural language semantic search across events and resources.

**Request Body:**

```json
{
  "query": "show me all OOM errors in production namespace last 6 hours",
  "client_id": "ab-01",
  "time_range_hours": 6,
  "resource_types": ["Pod"],
  "namespaces": ["production"],
  "limit": 20
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| query | string | Yes | Natural language search query |
| client_id | string | No | Client ID filter |
| time_range_hours | integer | No | Time range filter (default: 24) |
| resource_types | array[string] | No | Filter by resource types |
| namespaces | array[string] | No | Filter by namespaces |
| limit | integer | No | Max results (default: 20, max: 100) |

**Response:**

```json
{
  "query": "show me all OOM errors in production namespace last 6 hours",
  "results": [
    {
      "item_type": "Event",
      "item_id": "evt-12345",
      "content": "Pod nginx-deployment-7d4f9c8b6-xk2pl OOMKilled in production namespace at 2025-01-15T10:30:15Z",
      "metadata": {
        "reason": "OOMKilled",
        "resource_kind": "Pod",
        "resource_name": "nginx-deployment-7d4f9c8b6-xk2pl",
        "namespace": "production",
        "timestamp": "2025-01-15T10:30:15Z"
      },
      "similarity_score": 0.95,
      "timestamp": "2025-01-15T10:30:15Z"
    }
  ],
  "total_results": 5,
  "query_embedding_time_ms": 120,
  "search_time_ms": 45
}
```

---

### POST /search/rebuild-index/{client_id}

Rebuild the embedding index for a specific client.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| client_id | string | Yes | Client ID |

**Query Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| time_range_hours | integer | No | Include events from last N hours (default: 720 = 30 days) |

**Example Request:**

```bash
curl -X POST "http://localhost:8083/search/rebuild-index/ab-01?time_range_hours=720"
```

**Response:**

```json
{
  "status": "success",
  "client_id": "ab-01",
  "events_indexed": 12450,
  "resources_indexed": 523,
  "total_indexed": 12973,
  "index_build_time_ms": 8420
}
```

---

### GET /search/suggestions

Get search query suggestions based on common patterns.

**Query Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| client_id | string | No | Client ID filter |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/search/suggestions?client_id=ab-01"
```

**Response:**

```json
{
  "suggestions": [
    "show me all OOM errors",
    "find failed pods in production",
    "what happened to nginx service",
    "list all CrashLoopBackOff events",
    "show pods owned by team-backend",
    "find unhealthy services last hour"
  ]
}
```

---

## Catalog Endpoints

### GET /catalog/resources/{client_id}

Browse resources with metadata, ownership, and dependencies.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| client_id | string | Yes | Client ID |

**Query Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| namespaces | array[string] | No | Filter by namespaces |
| kinds | array[string] | No | Filter by resource kinds (Pod, Deployment, Service, etc.) |
| owners | array[string] | No | Filter by owner/team |
| labels | object | No | Filter by labels (key=value pairs) |
| healthy_only | boolean | No | Show only healthy resources (default: false) |
| page | integer | No | Page number (default: 1) |
| page_size | integer | No | Results per page (default: 50, max: 200) |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/catalog/resources/ab-01?kinds=Pod&kinds=Deployment&namespaces=production&owners=team-backend&healthy_only=false&page=1&page_size=50"
```

**Response:**

```json
{
  "resources": [
    {
      "resource_id": "res-12345",
      "name": "nginx-deployment",
      "kind": "Deployment",
      "namespace": "production",
      "client_id": "ab-01",
      "labels": {
        "app": "nginx",
        "tier": "frontend"
      },
      "owner": "team-backend",
      "size": "Medium",
      "created_at": "2025-01-10T08:00:00Z",
      "status": "Running",
      "dependencies": [
        "Service/nginx-service",
        "ConfigMap/nginx-config"
      ],
      "recent_events": 3
    }
  ],
  "total_count": 523,
  "filtered_count": 42,
  "page": 1,
  "page_size": 50
}
```

---

### GET /catalog/topology/{client_id}/{namespace}/{resource_name}

Get topology view for a specific service.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| client_id | string | Yes | Client ID |
| namespace | string | Yes | Namespace |
| resource_name | string | Yes | Resource name |

**Query Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| resource_kind | string | No | Resource kind (default: Service) |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/catalog/topology/ab-01/production/nginx-service?resource_kind=Service"
```

**Response:**

```json
{
  "service_name": "nginx-service",
  "namespace": "production",
  "pods": [
    {
      "name": "nginx-deployment-7d4f9c8b6-xk2pl",
      "status": "Running",
      "node": "node-1"
    }
  ],
  "nodes": ["node-1", "node-2"],
  "upstream_services": ["api-gateway"],
  "downstream_services": ["backend-api", "auth-service"],
  "health_status": "Healthy"
}
```

---

### GET /catalog/owners/{client_id}

Get list of resource owners/teams with resource counts.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| client_id | string | Yes | Client ID |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/catalog/owners/ab-01"
```

**Response:**

```json
{
  "owners": [
    {
      "owner": "team-backend",
      "resource_count": 125,
      "namespaces": ["production", "staging"],
      "resource_kinds": ["Pod", "Deployment", "Service"]
    },
    {
      "owner": "team-frontend",
      "resource_count": 87,
      "namespaces": ["production", "staging"],
      "resource_kinds": ["Pod", "Deployment", "Service", "Ingress"]
    }
  ]
}
```

---

### GET /catalog/namespaces/{client_id}

Get list of namespaces with resource counts and health status.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| client_id | string | Yes | Client ID |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/catalog/namespaces/ab-01"
```

**Response:**

```json
{
  "namespaces": [
    {
      "namespace": "production",
      "resource_count": 234,
      "pod_count": 156,
      "service_count": 45,
      "deployment_count": 33,
      "healthy_percentage": 95.5,
      "recent_events": 12
    },
    {
      "namespace": "staging",
      "resource_count": 120,
      "pod_count": 78,
      "service_count": 25,
      "deployment_count": 17,
      "healthy_percentage": 88.3,
      "recent_events": 45
    }
  ]
}
```

---

## Health Monitoring Endpoints

### GET /health/status/{client_id}

Get real-time health status for a client.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| client_id | string | Yes | Client ID |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/health/status/ab-01"
```

**Response:**

```json
{
  "client_id": "ab-01",
  "healthy_resources": 487,
  "unhealthy_resources": 23,
  "total_resources": 510,
  "active_incidents": 2,
  "health_percentage": 95.5,
  "top_issues": [
    {
      "reason": "OOMKilled",
      "count": 8,
      "affected_namespaces": ["production"],
      "severity": "high"
    },
    {
      "reason": "CrashLoopBackOff",
      "count": 5,
      "affected_namespaces": ["staging"],
      "severity": "medium"
    }
  ],
  "timestamp": "2025-01-15T12:00:00Z"
}
```

---

### POST /health/send-health-report/{client_id}

Send health status report to Slack.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| client_id | string | Yes | Client ID |

**Query Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| channel | string | No | Slack channel (overrides default) |

**Example Request:**

```bash
curl -X POST "http://localhost:8083/health/send-health-report/ab-01?channel=%23alerts"
```

**Response:**

```json
{
  "status": "success",
  "message": "Health report sent to Slack channel #alerts",
  "slack_timestamp": "1736940000.123456"
}
```

---

### GET /health/incidents/{client_id}

Get active incidents (ongoing failure patterns).

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| client_id | string | Yes | Client ID |

**Query Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| min_severity | string | No | Minimum severity (low, medium, high, critical) |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/health/incidents/ab-01?min_severity=medium"
```

**Response:**

```json
{
  "incidents": [
    {
      "incident_id": "inc-12345",
      "root_cause": "OOMKilled",
      "affected_services": ["nginx-service", "api-gateway"],
      "affected_namespaces": ["production"],
      "severity": "high",
      "started_at": "2025-01-15T10:30:00Z",
      "event_count": 8,
      "blast_radius": 15
    }
  ]
}
```

---

## Chat Assistant Endpoints

### POST /chat/

Chat with the RCA assistant powered by GPT-5.

**Request Body:**

```json
{
  "message": "What is causing high memory usage in the auth service?",
  "client_id": "ab-01",
  "conversation_id": "conv-12345",
  "context_events": ["evt-11111", "evt-11112"],
  "reasoning_effort": "low"
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| message | string | Yes | User message/question |
| client_id | string | No | Client ID for context |
| conversation_id | string | No | For multi-turn conversations |
| context_events | array[string] | No | Event IDs to include as context |
| reasoning_effort | enum | No | Response speed: minimal, low (default), medium, high |

**Response:**

```json
{
  "message": "Based on the recent events, the auth service is experiencing high memory usage due to a memory leak in the session management code. The service is currently using 1.8GB out of 2GB allocated memory. I recommend:\n\n1. Restart the auth service pods to clear accumulated memory\n2. Review session cleanup logic in the code\n3. Increase memory limit to 3GB temporarily while investigating\n4. Add memory profiling to identify the leak source\n\nWould you like me to generate kubectl commands for these steps?",
  "conversation_id": "conv-12345",
  "suggested_queries": [
    "Show me the kubectl commands",
    "What are similar past incidents?",
    "How do I profile memory in the auth service?"
  ],
  "related_events": ["evt-11113", "evt-11114"],
  "confidence": 0.82,
  "reasoning_summary": "Analyzed recent events and resource usage patterns. High confidence based on clear memory growth trend and similar past incidents."
}
```

---

### DELETE /chat/conversations/{conversation_id}

Clear conversation history.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| conversation_id | string | Yes | Conversation ID |

**Example Request:**

```bash
curl -X DELETE "http://localhost:8083/chat/conversations/conv-12345"
```

**Response:**

```json
{
  "status": "success",
  "message": "Conversation conv-12345 cleared"
}
```

---

### GET /chat/conversations/{conversation_id}

Get conversation history.

**Path Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| conversation_id | string | Yes | Conversation ID |

**Example Request:**

```bash
curl -X GET "http://localhost:8083/chat/conversations/conv-12345"
```

**Response:**

```json
{
  "conversation_id": "conv-12345",
  "messages": [
    {
      "role": "user",
      "content": "What is causing high memory usage?",
      "timestamp": "2025-01-15T12:00:00Z"
    },
    {
      "role": "assistant",
      "content": "Based on recent events...",
      "timestamp": "2025-01-15T12:00:03Z"
    }
  ],
  "started_at": "2025-01-15T12:00:00Z",
  "last_message_at": "2025-01-15T12:00:03Z"
}
```

---

## Error Responses

All endpoints return consistent error responses:

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid parameters |
| 404 | Not Found - Resource doesn't exist |
| 500 | Internal Server Error - Service failure |
| 503 | Service Unavailable - External service down |

### Example Error Response

```json
{
  "detail": "Neo4j connection failed: Unable to connect to bolt://localhost:7687"
}
```

---

## Rate Limiting

Currently no rate limiting. Future versions will implement:
- Per-client rate limits
- Per-endpoint rate limits
- Burst allowances

---

## Pagination

Endpoints that return lists support pagination:

**Query Parameters:**
- `page`: Page number (1-indexed)
- `page_size`: Results per page (max varies by endpoint)

**Response includes:**
- `total_count`: Total available results
- `filtered_count`: Results after filters
- `page`: Current page
- `page_size`: Results per page

---

## Webhooks (Future)

Future versions will support webhooks for:
- Real-time incident notifications
- Health status changes
- New failure pattern detection

---

## OpenAPI Specification

Full OpenAPI 3.0 specification available at:
- JSON: http://localhost:8083/openapi.json
- Swagger UI: http://localhost:8083/docs
- ReDoc: http://localhost:8083/redoc
