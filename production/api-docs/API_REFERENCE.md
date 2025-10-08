# Knowledge Graph RCA System - Complete API Reference

## Table of Contents
1. [RCA & Analysis APIs](#rca--analysis-apis)
2. [Vector Search APIs](#vector-search-apis)
3. [Graph Query APIs](#graph-query-apis)
4. [Incident Management APIs](#incident-management-apis)
5. [Resource APIs](#resource-apis)
6. [Metrics & Health APIs](#metrics--health-apis)
7. [Admin & Maintenance APIs](#admin--maintenance-apis)

---

## Base URLs

| Environment | Base URL |
|-------------|----------|
| Production | `https://kg-api.your-domain.com/api/v1` |
| Development | `http://localhost:8080/api/v1` |

---

## Authentication

```bash
# Bearer Token (recommended for production)
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://kg-api.your-domain.com/api/v1/rca

# API Key (alternative)
curl -H "X-API-Key: YOUR_API_KEY" \
  https://kg-api.your-domain.com/api/v1/rca
```

---

## 1. RCA & Analysis APIs

### 1.1 Get Root Cause Analysis

**Endpoint**: `POST /rca`

**Description**: Perform root cause analysis for a specific event with confidence scoring

**Request**:
```json
{
  "event_id": "evt-abc123",
  "time_window_minutes": 15,
  "max_hops": 3,
  "min_confidence": 0.5,
  "include_blast_radius": true,
  "include_timeline": true
}
```

**Response**:
```json
{
  "event_id": "evt-abc123",
  "event_time": "2025-10-08T10:15:30Z",
  "reason": "CrashLoopBackOff",
  "severity": "ERROR",
  "message": "Back-off restarting failed container",
  "subject": {
    "rid": "pod:default:my-app-7d9f8b",
    "kind": "Pod",
    "name": "my-app-7d9f8b",
    "namespace": "default",
    "labels": {
      "app": "my-app",
      "version": "v2"
    }
  },
  "potential_causes": [
    {
      "event_id": "evt-abc100",
      "event_time": "2025-10-08T10:14:45Z",
      "reason": "OOMKilled",
      "message": "Container exceeded memory limit",
      "severity": "FATAL",
      "confidence": 0.95,
      "hops": 1,
      "temporal_score": 0.92,
      "distance_score": 1.0,
      "domain_score": 0.95,
      "subject": {
        "rid": "pod:default:my-app-7d9f8b",
        "kind": "Pod",
        "name": "my-app-7d9f8b"
      },
      "explanation": "High confidence: OOMKilled → CrashLoop pattern"
    },
    {
      "event_id": "evt-abc090",
      "event_time": "2025-10-08T10:14:00Z",
      "reason": "HighMemoryUsage",
      "confidence": 0.75,
      "hops": 2,
      "explanation": "Memory pressure led to OOM"
    }
  ],
  "related_incident": {
    "incident_id": "inc-2025-10-08-001",
    "resource_id": "pod:default:my-app-7d9f8b",
    "window_start": "2025-10-08T10:10:00Z",
    "window_end": "2025-10-08T10:20:00Z",
    "event_count": 12,
    "severity": "FATAL"
  },
  "blast_radius": [
    {
      "rid": "service:default:my-app",
      "kind": "Service",
      "name": "my-app",
      "impact": "Service endpoints reduced"
    },
    {
      "rid": "deployment:default:my-app",
      "kind": "Deployment",
      "name": "my-app",
      "impact": "Deployment degraded"
    }
  ],
  "timeline": [
    {
      "event_time": "2025-10-08T10:14:00Z",
      "reason": "HighMemoryUsage",
      "severity": "WARNING",
      "resource": "pod:default:my-app-7d9f8b"
    },
    {
      "event_time": "2025-10-08T10:14:45Z",
      "reason": "OOMKilled",
      "severity": "FATAL",
      "resource": "pod:default:my-app-7d9f8b"
    },
    {
      "event_time": "2025-10-08T10:15:30Z",
      "reason": "CrashLoopBackOff",
      "severity": "ERROR",
      "resource": "pod:default:my-app-7d9f8b"
    }
  ],
  "recommendation": {
    "action": "Increase memory limits",
    "details": "Pod is experiencing OOM kills. Current limit: 512Mi. Suggested: 1Gi",
    "confidence": 0.95
  }
}
```

**Use Cases**:
```bash
# Basic RCA
curl -X POST http://localhost:8080/api/v1/rca \
  -H "Content-Type: application/json" \
  -d '{"event_id": "evt-abc123"}'

# RCA with high confidence threshold
curl -X POST http://localhost:8080/api/v1/rca \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt-abc123",
    "min_confidence": 0.8,
    "max_hops": 2
  }'
```

---

### 1.2 Get RCA by Resource

**Endpoint**: `POST /rca/resource`

**Description**: Get all RCA analysis for a specific resource

**Request**:
```json
{
  "resource_uid": "abc-123-def",
  "time_window_hours": 24,
  "severity": ["ERROR", "FATAL"]
}
```

**Response**:
```json
{
  "resource": {
    "uid": "abc-123-def",
    "kind": "Pod",
    "name": "my-app-7d9f8b",
    "namespace": "default"
  },
  "analysis_count": 5,
  "analyses": [
    { /* RCA object */ },
    { /* RCA object */ }
  ]
}
```

---

### 1.3 Bulk RCA Analysis

**Endpoint**: `POST /rca/bulk`

**Description**: Analyze multiple events in one request

**Request**:
```json
{
  "event_ids": ["evt-1", "evt-2", "evt-3"],
  "min_confidence": 0.6
}
```

---

## 2. Vector Search APIs

### 2.1 Semantic Search

**Endpoint**: `POST /search/semantic`

**Description**: Natural language search across all events using vector embeddings

**Request**:
```json
{
  "query": "What bug is caused by memory leaks",
  "top_k": 10,
  "min_similarity": 0.6,
  "time_window_days": 7,
  "filters": {
    "severity": ["ERROR", "FATAL"],
    "kind": ["Pod", "Service"],
    "namespace": ["default", "production"],
    "has_incident": true
  }
}
```

**Response**:
```json
{
  "query": "What bug is caused by memory leaks",
  "results": [
    {
      "event_id": "evt-mem-001",
      "reason": "OOMKilled",
      "message": "Container memory limit exceeded, process killed",
      "severity": "FATAL",
      "event_time": "2025-10-08T10:14:45Z",
      "subject": {
        "rid": "pod:default:my-app",
        "kind": "Pod",
        "name": "my-app"
      },
      "similarity": 0.92,
      "root_causes": ["evt-mem-000"],
      "incident": "inc-2025-10-08-001",
      "explanation": "Matched: 'memory' in reason, 'leak' semantic similarity"
    }
  ],
  "total_results": 5,
  "execution_time_ms": 45
}
```

**Use Cases**:
```bash
# Find memory-related issues
curl -X POST http://localhost:8080/api/v1/search/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "memory leak causing pod crashes",
    "top_k": 5
  }'

# Find network issues
curl -X POST http://localhost:8080/api/v1/search/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "connection timeout service unavailable",
    "filters": {
      "severity": ["ERROR"],
      "namespace": ["production"]
    }
  }'

# Find image pull errors
curl -X POST http://localhost:8080/api/v1/search/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "cannot pull container image",
    "time_window_days": 1
  }'
```

---

### 2.2 Causal Search

**Endpoint**: `POST /search/causal`

**Description**: Answer "what caused what" questions with causal chains

**Request**:
```json
{
  "query": "What caused the service outage yesterday",
  "max_chain_length": 5,
  "min_confidence": 0.5
}
```

**Response**:
```json
{
  "query": "What caused the service outage yesterday",
  "causal_chains": [
    {
      "effect_id": "evt-outage-001",
      "effect_reason": "ServiceUnavailable",
      "effect_resource": "service:prod:api-gateway",
      "chain_length": 3,
      "causal_path": [
        {
          "step": 1,
          "event_id": "evt-disk-001",
          "reason": "DiskFull",
          "resource": "node:worker-01",
          "confidence": 0.85
        },
        {
          "step": 2,
          "event_id": "evt-evict-001",
          "reason": "PodEvicted",
          "resource": "pod:prod:api-gateway-abc",
          "confidence": 0.90
        },
        {
          "step": 3,
          "event_id": "evt-outage-001",
          "reason": "ServiceUnavailable",
          "resource": "service:prod:api-gateway",
          "confidence": 0.95
        }
      ],
      "explanation": "Disk full on node → Pod evicted → Service unavailable",
      "overall_confidence": 0.90
    }
  ]
}
```

---

### 2.3 Similar Events

**Endpoint**: `POST /search/similar`

**Description**: Find events similar to a given event

**Request**:
```json
{
  "event_id": "evt-abc123",
  "top_k": 10,
  "time_window_days": 30
}
```

---

## 3. Graph Query APIs

### 3.1 Get Resource Topology

**Endpoint**: `GET /graph/topology/{resource_uid}`

**Description**: Get complete topology graph for a resource

**Response**:
```json
{
  "resource": {
    "uid": "abc-123",
    "kind": "Pod",
    "name": "my-app"
  },
  "relationships": {
    "controls": [
      {
        "target": {
          "kind": "ReplicaSet",
          "name": "my-app-rs"
        },
        "relationship_type": "CONTROLLED_BY"
      }
    ],
    "runs_on": [
      {
        "target": {
          "kind": "Node",
          "name": "worker-01"
        }
      }
    ],
    "selects": [
      {
        "target": {
          "kind": "Service",
          "name": "my-app-svc"
        }
      }
    ]
  },
  "depth": 2
}
```

---

### 3.2 Get Event History

**Endpoint**: `GET /graph/events/{resource_uid}`

**Description**: Get event timeline for a resource

**Query Parameters**:
- `start_time`: ISO 8601 timestamp
- `end_time`: ISO 8601 timestamp
- `severity`: Comma-separated list
- `limit`: Max events to return

**Response**:
```json
{
  "resource_uid": "abc-123",
  "events": [
    {
      "event_id": "evt-1",
      "event_time": "2025-10-08T10:00:00Z",
      "reason": "Started",
      "severity": "INFO"
    }
  ],
  "total_count": 42
}
```

---

### 3.3 Get Incident Timeline

**Endpoint**: `GET /graph/timeline`

**Description**: Get system-wide event timeline

**Query Parameters**:
- `start_time`: ISO 8601
- `end_time`: ISO 8601
- `namespaces`: Comma-separated
- `severity`: Comma-separated
- `include_incidents`: boolean

---

## 4. Incident Management APIs

### 4.1 List Active Incidents

**Endpoint**: `GET /incidents`

**Query Parameters**:
- `status`: open, acknowledged, resolved
- `severity`: ERROR, FATAL
- `namespace`: filter by namespace
- `sort`: created_at, event_count, severity

**Response**:
```json
{
  "incidents": [
    {
      "incident_id": "inc-2025-10-08-001",
      "resource_id": "pod:default:my-app",
      "status": "open",
      "severity": "FATAL",
      "window_start": "2025-10-08T10:10:00Z",
      "window_end": "2025-10-08T10:20:00Z",
      "event_count": 12,
      "events": [
        {
          "event_id": "evt-1",
          "reason": "OOMKilled"
        }
      ],
      "root_cause": {
        "event_id": "evt-0",
        "reason": "MemoryLeak",
        "confidence": 0.92
      }
    }
  ],
  "total_count": 5,
  "page": 1,
  "page_size": 20
}
```

---

### 4.2 Get Incident Details

**Endpoint**: `GET /incidents/{incident_id}`

**Response**:
```json
{
  "incident_id": "inc-2025-10-08-001",
  "resource": {
    "uid": "abc-123",
    "kind": "Pod",
    "name": "my-app"
  },
  "status": "open",
  "severity": "FATAL",
  "created_at": "2025-10-08T10:10:00Z",
  "updated_at": "2025-10-08T10:20:00Z",
  "event_count": 12,
  "events": [ /* list of events */ ],
  "root_cause_analysis": { /* RCA object */ },
  "blast_radius": [ /* affected resources */ ],
  "timeline": [ /* event timeline */ ],
  "recommendations": [
    {
      "action": "Increase memory limit",
      "priority": "high",
      "confidence": 0.95
    }
  ]
}
```

---

### 4.3 Update Incident Status

**Endpoint**: `PATCH /incidents/{incident_id}`

**Request**:
```json
{
  "status": "acknowledged",
  "assignee": "oncall-engineer@example.com",
  "notes": "Investigating memory leak in pod",
  "tags": ["memory", "production"]
}
```

---

### 4.4 Get Incident Recommendations

**Endpoint**: `GET /incidents/{incident_id}/recommendations`

**Description**: Get AI-generated recommendations for incident resolution

**Response**:
```json
{
  "incident_id": "inc-2025-10-08-001",
  "recommendations": [
    {
      "id": "rec-1",
      "type": "resource_adjustment",
      "action": "Increase memory limit",
      "details": {
        "current": "512Mi",
        "recommended": "1Gi",
        "reason": "Pod consistently hitting memory limit"
      },
      "confidence": 0.95,
      "priority": "high",
      "automated": false,
      "command": "kubectl set resources deployment my-app --limits=memory=1Gi"
    },
    {
      "id": "rec-2",
      "type": "code_fix",
      "action": "Add memory leak detection",
      "details": {
        "description": "Enable heap profiling to identify memory leak source"
      },
      "confidence": 0.75,
      "priority": "medium"
    }
  ]
}
```

---

## 5. Resource APIs

### 5.1 Get Resource Details

**Endpoint**: `GET /resources/{resource_uid}`

**Response**:
```json
{
  "uid": "abc-123",
  "rid": "pod:default:my-app-7d9f8b",
  "kind": "Pod",
  "name": "my-app-7d9f8b",
  "namespace": "default",
  "labels": {
    "app": "my-app",
    "version": "v2"
  },
  "status": {
    "phase": "Running",
    "conditions": []
  },
  "spec": {
    "containers": []
  },
  "created_at": "2025-10-08T09:00:00Z",
  "updated_at": "2025-10-08T10:00:00Z",
  "relationships": {
    "owned_by": ["deployment:default:my-app"],
    "runs_on": ["node:worker-01"],
    "selected_by": ["service:default:my-app"]
  },
  "event_count": {
    "total": 42,
    "error": 5,
    "warning": 12
  },
  "health_score": 0.75
}
```

---

### 5.2 List Resources

**Endpoint**: `GET /resources`

**Query Parameters**:
- `kind`: Pod, Service, Deployment, etc.
- `namespace`: filter by namespace
- `labels`: key=value pairs
- `status`: Running, Failed, Pending
- `has_errors`: boolean
- `sort`: name, created_at, health_score
- `page`: page number
- `page_size`: results per page

---

### 5.3 Get Resource Health

**Endpoint**: `GET /resources/{resource_uid}/health`

**Description**: Get health score and status for a resource

**Response**:
```json
{
  "resource_uid": "abc-123",
  "health_score": 0.75,
  "status": "degraded",
  "checks": [
    {
      "name": "error_rate",
      "status": "warning",
      "value": 5,
      "threshold": 10,
      "message": "5 errors in last hour"
    },
    {
      "name": "restart_count",
      "status": "ok",
      "value": 0,
      "threshold": 5
    },
    {
      "name": "memory_usage",
      "status": "critical",
      "value": 95,
      "threshold": 80,
      "message": "Memory usage at 95%"
    }
  ],
  "recent_incidents": 2,
  "last_error": "2025-10-08T10:15:00Z"
}
```

---

### 5.4 Update Resource (Incremental)

**Endpoint**: `POST /resources/update`

**Description**: Incrementally update resource state (for external systems)

**Request**:
```json
{
  "timestamp": "2025-10-08T10:00:00Z",
  "resources": [
    {
      "action": "UPDATE",
      "kind": "Pod",
      "uid": "abc-123",
      "name": "my-pod",
      "namespace": "default",
      "labels": {"app": "web"},
      "status": {"phase": "Running"}
    },
    {
      "action": "DELETE",
      "uid": "def-456"
    }
  ]
}
```

---

## 6. Metrics & Health APIs

### 6.1 Get System Statistics

**Endpoint**: `GET /stats`

**Response**:
```json
{
  "timestamp": "2025-10-08T10:00:00Z",
  "graph": {
    "resources": {
      "total": 1010,
      "by_kind": {
        "Pod": 450,
        "Service": 120,
        "Deployment": 80
      }
    },
    "events": {
      "total": 45230,
      "by_severity": {
        "INFO": 30000,
        "WARNING": 10000,
        "ERROR": 4500,
        "FATAL": 730
      }
    },
    "incidents": {
      "total": 125,
      "open": 5,
      "acknowledged": 3,
      "resolved": 117
    },
    "edges": {
      "total": 2340,
      "by_type": {
        "SELECTS": 450,
        "RUNS_ON": 450,
        "CONTROLS": 890,
        "POTENTIAL_CAUSE": 550
      }
    }
  },
  "performance": {
    "avg_rca_time_ms": 125,
    "avg_search_time_ms": 45,
    "kafka_lag": {
      "events.normalized": 0,
      "logs.normalized": 12
    }
  },
  "health": {
    "neo4j": "healthy",
    "kafka": "healthy",
    "embedding_service": "healthy"
  }
}
```

---

### 6.2 Health Check

**Endpoint**: `GET /healthz`

**Response**:
```json
{
  "status": "healthy",
  "components": {
    "neo4j": "up",
    "kafka": "up",
    "embedding_service": "up"
  },
  "version": "1.0.0"
}
```

---

### 6.3 Readiness Check

**Endpoint**: `GET /readyz`

---

### 6.4 Get Metrics (Prometheus)

**Endpoint**: `GET /metrics`

**Description**: Prometheus-formatted metrics

---

## 7. Admin & Maintenance APIs

### 7.1 Trigger Cleanup

**Endpoint**: `POST /admin/cleanup`

**Description**: Manually trigger data cleanup

**Request**:
```json
{
  "retention_days": 7,
  "dry_run": false,
  "cleanup_types": ["events", "incidents", "orphaned_nodes"]
}
```

**Response**:
```json
{
  "events_deleted": 1250,
  "incidents_deleted": 5,
  "orphaned_nodes_deleted": 23,
  "execution_time_ms": 3450
}
```

---

### 7.2 Reindex Embeddings

**Endpoint**: `POST /admin/reindex-embeddings`

**Description**: Generate embeddings for events that don't have them

**Request**:
```json
{
  "batch_size": 100,
  "force_reindex": false
}
```

---

### 7.3 Get System Configuration

**Endpoint**: `GET /admin/config`

**Description**: Get current system configuration

---

### 7.4 Update System Configuration

**Endpoint**: `PUT /admin/config`

**Description**: Update system configuration (requires admin role)

**Request**:
```json
{
  "rca_window_minutes": 20,
  "min_confidence_threshold": 0.6,
  "anomaly_detection_enabled": true
}
```

---

## Error Responses

All APIs return standard error responses:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Event evt-abc123 not found",
    "details": {
      "event_id": "evt-abc123"
    },
    "timestamp": "2025-10-08T10:00:00Z"
  }
}
```

**Error Codes**:
- `RESOURCE_NOT_FOUND` (404)
- `INVALID_REQUEST` (400)
- `UNAUTHORIZED` (401)
- `FORBIDDEN` (403)
- `RATE_LIMIT_EXCEEDED` (429)
- `INTERNAL_ERROR` (500)
- `SERVICE_UNAVAILABLE` (503)

---

## Rate Limiting

**Limits**:
- Anonymous: 100 requests/minute
- Authenticated: 1000 requests/minute
- Admin: 10000 requests/minute

**Headers**:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 995
X-RateLimit-Reset: 1696780800
```

---

## Pagination

All list endpoints support pagination:

**Request**:
```
GET /incidents?page=2&page_size=50
```

**Response**:
```json
{
  "data": [ /* results */ ],
  "pagination": {
    "page": 2,
    "page_size": 50,
    "total_pages": 10,
    "total_count": 487
  }
}
```

---

## Webhooks

### Register Webhook

**Endpoint**: `POST /webhooks`

**Request**:
```json
{
  "url": "https://your-system.com/webhook",
  "events": ["incident.created", "incident.resolved"],
  "filters": {
    "severity": ["FATAL"],
    "namespace": ["production"]
  },
  "secret": "your-webhook-secret"
}
```

**Webhook Payload**:
```json
{
  "event_type": "incident.created",
  "timestamp": "2025-10-08T10:00:00Z",
  "data": {
    "incident_id": "inc-001",
    "severity": "FATAL",
    "resource": "pod:prod:api"
  },
  "signature": "sha256=..."
}
```

---

## SDK Examples

### Python SDK

```python
from kg_rca_client import KGRCAClient

client = KGRCAClient(
    base_url="http://localhost:8080/api/v1",
    api_key="your-api-key"
)

# Semantic search
results = client.search.semantic(
    query="memory leak causing crashes",
    top_k=5
)

# RCA
analysis = client.rca.analyze(
    event_id="evt-abc123",
    min_confidence=0.7
)

# List incidents
incidents = client.incidents.list(
    status="open",
    severity=["FATAL"]
)
```

### JavaScript/TypeScript SDK

```typescript
import { KGRCAClient } from '@kg-rca/client';

const client = new KGRCAClient({
  baseURL: 'http://localhost:8080/api/v1',
  apiKey: 'your-api-key'
});

// Semantic search
const results = await client.search.semantic({
  query: 'connection timeout',
  topK: 10
});

// RCA
const analysis = await client.rca.analyze({
  eventId: 'evt-abc123'
});
```

---

## Best Practices

1. **Use semantic search for natural language queries**
2. **Set appropriate confidence thresholds** (0.6-0.8 recommended)
3. **Use time windows to limit scope** (7-30 days typical)
4. **Implement pagination for large result sets**
5. **Cache frequently accessed data**
6. **Use webhooks for real-time notifications**
7. **Monitor rate limits**
8. **Handle errors gracefully**

---

## Support

- Documentation: https://docs.kg-rca.com
- API Status: https://status.kg-rca.com
- Support: support@kg-rca.com
