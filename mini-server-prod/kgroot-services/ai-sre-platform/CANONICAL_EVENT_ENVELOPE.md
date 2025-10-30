# Canonical Event Envelope Standard

> **Version**: v1.0
> **Status**: Proposed
> **Owner**: AI SRE Platform Team

---

## Purpose

Define **one canonical event envelope** across all data sources (K8s, Datadog, Argo, GitHub, Slack, etc.) to:

1. **Simplify downstream processing** - single schema to handle
2. **Enable correlation** - link events across systems via correlation_ids
3. **Support multi-tenancy** - tenant_id in every event
4. **Ensure idempotency** - ingest_id for deduplication
5. **Allow evolution** - schema_version for backward compatibility

---

## Schema Definition

### Core Structure

```json
{
  "tenant_id": "string (required)",
  "source": "string (required)",
  "event_type": "string (required)",
  "ts": "ISO-8601 timestamp (required)",
  "correlation_ids": "object (optional)",
  "entity": "object (required)",
  "severity": "enum (required)",
  "payload": "object (required)",
  "ingest_id": "uuid (required)",
  "schema_version": "string (required)"
}
```

### Field Descriptions

#### `tenant_id` (string, required)
- **Description**: Unique identifier for the tenant/client
- **Format**: Kebab-case, lowercase (e.g., `acme-01`, `company-xyz`)
- **Purpose**: Multi-tenant isolation, routing, billing
- **Examples**: `"acme-01"`, `"startupxyz"`, `"enterprise-prod"`

#### `source` (string, required)
- **Description**: Origin system of the event
- **Format**: Dot-notation namespace (e.g., `k8s.events`, `datadog.metrics`)
- **Allowed Values**:
  - `k8s.events` - Kubernetes events
  - `k8s.state` - Kubernetes resource state changes
  - `datadog.metrics` - Datadog metrics
  - `datadog.traces` - Datadog APM traces
  - `prometheus.alerts` - Prometheus alert manager
  - `argo.workflows` - Argo Workflow events
  - `argo.logs` - Argo Workflow logs
  - `github.cicd` - GitHub Actions/CI/CD
  - `gitlab.cicd` - GitLab CI/CD
  - `slack.incidents` - Slack incident channel messages
  - `pagerduty.incidents` - PagerDuty incidents
- **Extensible**: New sources can be added

#### `event_type` (string, required)
- **Description**: Specific type of event within the source
- **Format**: PascalCase or dot-notation
- **Examples**:
  - K8s: `PodOOMKilled`, `ImagePullBackOff`, `CrashLoopBackOff`, `NodeNotReady`
  - Datadog: `metric.anomaly`, `trace.error_spike`
  - Argo: `workflow.succeeded`, `workflow.failed`, `workflow.running`
  - GitHub: `deploy.started`, `deploy.succeeded`, `deploy.failed`, `commit.pushed`
  - Slack: `incident.created`, `incident.resolved`, `incident.escalated`

#### `ts` (string, required)
- **Description**: Event timestamp (when the event occurred, not when ingested)
- **Format**: ISO-8601 with timezone (UTC preferred)
- **Examples**: `"2025-10-30T07:41:03.123Z"`, `"2025-10-30T07:41:03+00:00"`

#### `correlation_ids` (object, optional)
- **Description**: Cross-system identifiers for correlating related events
- **Fields**:
  - `trace_id` (string) - Distributed tracing ID (Datadog, Jaeger, etc.)
  - `commit` (string) - Git commit SHA
  - `workflow` (string) - Argo Workflow ID
  - `deployment` (string) - Deployment ID
  - `incident_id` (string) - PagerDuty/Slack incident ID
  - `request_id` (string) - HTTP request ID
- **Example**:
  ```json
  {
    "trace_id": "abc123def456",
    "commit": "a1b2c3d4e5f6",
    "workflow": "argo-deploy-prod-789",
    "deployment": "deploy-v1.2.3-xyz"
  }
  ```

#### `entity` (object, required)
- **Description**: The resource/entity this event is about
- **Common Fields**:
  - `cluster` (string) - Kubernetes cluster name
  - `namespace` (string) - K8s namespace or logical grouping
  - `service` (string) - Service/application name
  - `pod` (string) - Pod name (K8s)
  - `node` (string) - Node name (K8s)
  - `container` (string) - Container name
  - `host` (string) - Hostname (non-K8s)
- **Extensible**: Add source-specific fields
- **Example**:
  ```json
  {
    "cluster": "prod-us-west-2",
    "namespace": "payments",
    "service": "nginx-api",
    "pod": "nginx-api-7d8f9b-xyz",
    "node": "ip-10-0-1-100",
    "container": "nginx"
  }
  ```

#### `severity` (enum, required)
- **Description**: Severity/priority of the event
- **Allowed Values**: `"debug"`, `"info"`, `"warn"`, `"error"`, `"critical"`
- **Mapping from sources**:
  - K8s Warning → `"warn"`
  - K8s Normal → `"info"`
  - OOMKilled → `"error"`
  - NodeNotReady → `"critical"`
  - Datadog alert → based on alert severity

#### `payload` (object, required)
- **Description**: Raw, vendor-specific event data
- **Purpose**: Preserve all original information for deep analysis
- **Format**: JSON object (flexible schema)
- **Example for K8s**:
  ```json
  {
    "reason": "OOMKilled",
    "message": "Container nginx was OOMKilled (memory limit exceeded)",
    "involvedObject": {
      "kind": "Pod",
      "name": "nginx-api-7d8f9b-xyz",
      "uid": "abc-123-def"
    },
    "metadata": {
      "resourceVersion": "12345",
      "creationTimestamp": "2025-10-30T07:41:03Z"
    }
  }
  ```
- **Example for Datadog**:
  ```json
  {
    "metric": "system.cpu.user",
    "value": 95.7,
    "tags": ["env:prod", "service:nginx-api"],
    "alert_triggered": true,
    "threshold": 80.0
  }
  ```

#### `ingest_id` (string, required)
- **Description**: Unique identifier for this specific ingestion (idempotency key)
- **Format**: UUID v4
- **Purpose**: Prevent duplicate processing if events are retried
- **Example**: `"550e8400-e29b-41d4-a716-446655440000"`
- **Generation**: Generated by the ingestion layer (not the source)

#### `schema_version` (string, required)
- **Description**: Version of this envelope schema
- **Format**: Semantic versioning (e.g., `"v1"`, `"v1.1"`, `"v2"`)
- **Purpose**: Handle schema evolution gracefully
- **Current**: `"v1"`

---

## Full Example: Kubernetes OOMKilled Event

```json
{
  "tenant_id": "acme-01",
  "source": "k8s.events",
  "event_type": "PodOOMKilled",
  "ts": "2025-10-30T07:41:03.245Z",
  "correlation_ids": {
    "trace_id": null,
    "commit": "a1b2c3d",
    "workflow": "argo-deploy-nginx-prod-456",
    "deployment": "nginx-api-v1.2.3"
  },
  "entity": {
    "cluster": "prod-us-west-2",
    "namespace": "payments",
    "service": "nginx-api",
    "pod": "nginx-api-7d8f9b-xyz",
    "node": "ip-10-0-1-100",
    "container": "nginx"
  },
  "severity": "error",
  "payload": {
    "reason": "OOMKilled",
    "message": "Container nginx in pod nginx-api-7d8f9b-xyz was OOMKilled",
    "count": 1,
    "type": "Warning",
    "involvedObject": {
      "kind": "Pod",
      "namespace": "payments",
      "name": "nginx-api-7d8f9b-xyz",
      "uid": "abc-123-def-456",
      "apiVersion": "v1",
      "resourceVersion": "12345",
      "fieldPath": "spec.containers{nginx}"
    },
    "source": {
      "component": "kubelet",
      "host": "ip-10-0-1-100"
    },
    "firstTimestamp": "2025-10-30T07:41:03Z",
    "lastTimestamp": "2025-10-30T07:41:03Z",
    "metadata": {
      "name": "nginx-api-7d8f9b-xyz.oom-killed",
      "namespace": "payments",
      "uid": "event-oom-789",
      "resourceVersion": "67890",
      "creationTimestamp": "2025-10-30T07:41:03Z"
    }
  },
  "ingest_id": "550e8400-e29b-41d4-a716-446655440000",
  "schema_version": "v1"
}
```

---

## Full Example: Datadog Metric Anomaly

```json
{
  "tenant_id": "acme-01",
  "source": "datadog.metrics",
  "event_type": "metric.anomaly",
  "ts": "2025-10-30T07:42:15.678Z",
  "correlation_ids": {
    "trace_id": "dd-trace-abc123",
    "commit": null,
    "workflow": null,
    "deployment": null
  },
  "entity": {
    "cluster": "prod-us-west-2",
    "namespace": "payments",
    "service": "nginx-api",
    "pod": null,
    "node": null,
    "container": null,
    "host": "ip-10-0-1-100.ec2.internal"
  },
  "severity": "warn",
  "payload": {
    "metric": "system.cpu.user",
    "value": 95.7,
    "baseline": 45.2,
    "deviation": 2.8,
    "anomaly_score": 0.92,
    "tags": [
      "env:prod",
      "service:nginx-api",
      "cluster:prod-us-west-2",
      "namespace:payments"
    ],
    "alert_id": "dd-alert-12345",
    "alert_name": "High CPU on nginx-api"
  },
  "ingest_id": "660f9511-f3ac-52e5-b827-557766551111",
  "schema_version": "v1"
}
```

---

## Full Example: Argo Workflow Failed

```json
{
  "tenant_id": "acme-01",
  "source": "argo.workflows",
  "event_type": "workflow.failed",
  "ts": "2025-10-30T07:40:32.123Z",
  "correlation_ids": {
    "trace_id": null,
    "commit": "a1b2c3d",
    "workflow": "argo-deploy-nginx-prod-456",
    "deployment": "nginx-api-v1.2.3"
  },
  "entity": {
    "cluster": "prod-us-west-2",
    "namespace": "argo",
    "service": "nginx-api",
    "pod": null,
    "node": null,
    "container": null,
    "workflow_name": "deploy-nginx-api-prod",
    "workflow_uid": "argo-wf-abc-123"
  },
  "severity": "error",
  "payload": {
    "workflow_name": "deploy-nginx-api-prod",
    "phase": "Failed",
    "message": "Step 'apply-manifests' failed: exit code 1",
    "started_at": "2025-10-30T07:38:00Z",
    "finished_at": "2025-10-30T07:40:32Z",
    "duration_seconds": 152,
    "failed_step": "apply-manifests",
    "error_message": "error: unable to apply manifests: ImagePullBackOff",
    "parameters": {
      "image_tag": "v1.2.3",
      "environment": "prod",
      "namespace": "payments"
    }
  },
  "ingest_id": "770fa622-g4bd-63f6-c938-668877662222",
  "schema_version": "v1"
}
```

---

## Full Example: GitHub CI/CD Deploy Succeeded

```json
{
  "tenant_id": "acme-01",
  "source": "github.cicd",
  "event_type": "deploy.succeeded",
  "ts": "2025-10-30T07:38:45.890Z",
  "correlation_ids": {
    "trace_id": null,
    "commit": "a1b2c3d4e5f6",
    "workflow": "github-actions-run-123",
    "deployment": "nginx-api-v1.2.3"
  },
  "entity": {
    "cluster": "prod-us-west-2",
    "namespace": "payments",
    "service": "nginx-api",
    "pod": null,
    "node": null,
    "container": null,
    "repository": "acme/nginx-api",
    "branch": "main"
  },
  "severity": "info",
  "payload": {
    "repository": "acme/nginx-api",
    "branch": "main",
    "commit_sha": "a1b2c3d4e5f6",
    "commit_message": "fix: increase memory limits for nginx",
    "author": "alice@acme.com",
    "workflow_id": "deploy-prod.yml",
    "run_id": "123456789",
    "run_number": 42,
    "job": "deploy-to-k8s",
    "status": "success",
    "conclusion": "success",
    "started_at": "2025-10-30T07:35:00Z",
    "completed_at": "2025-10-30T07:38:45Z",
    "duration_seconds": 225,
    "artifacts": [
      {
        "name": "deployment-manifest",
        "url": "https://github.com/acme/nginx-api/runs/123/artifacts/456"
      }
    ]
  },
  "ingest_id": "880fb733-h5ce-74g7-d049-779988773333",
  "schema_version": "v1"
}
```

---

## Full Example: Slack Incident Created

```json
{
  "tenant_id": "acme-01",
  "source": "slack.incidents",
  "event_type": "incident.created",
  "ts": "2025-10-30T07:43:00.456Z",
  "correlation_ids": {
    "trace_id": null,
    "commit": null,
    "workflow": null,
    "deployment": null,
    "incident_id": "inc-123"
  },
  "entity": {
    "cluster": null,
    "namespace": null,
    "service": "nginx-api",
    "pod": null,
    "node": null,
    "container": null,
    "channel": "incidents",
    "thread_ts": "1698653580.123456"
  },
  "severity": "critical",
  "payload": {
    "incident_id": "inc-123",
    "title": "nginx-api pods crashing in payments namespace",
    "description": "Multiple OOMKilled events detected",
    "channel": "incidents",
    "thread_ts": "1698653580.123456",
    "created_by": "U12345ABC",
    "created_by_name": "Alice Johnson",
    "assignee": "U67890DEF",
    "assignee_name": "Bob Smith",
    "status": "investigating",
    "priority": "p1",
    "affected_services": ["nginx-api", "payment-processor"],
    "tags": ["oom", "payments", "prod"]
  },
  "ingest_id": "990fc844-i6df-85h8-e15a-88aa99884444",
  "schema_version": "v1"
}
```

---

## Kafka Topic Strategy

### Topic Naming Convention

```
{source_prefix}-{tenant_id}
```

**Examples**:
- `k8s-events-acme-01`
- `k8s-events-startupxyz`
- `datadog-metrics-acme-01`
- `argo-logs-acme-01`
- `cicd-events-acme-01`
- `slack-incidents-acme-01`

### Partitioning

**Partition Key**: `tenant_id + entity.service`

**Reasoning**:
- Co-locate events for same tenant + service on same partition
- Enables ordered processing per service
- Good load distribution across partitions

**Example**:
```
partition_key = f"{tenant_id}:{entity.service}"
# "acme-01:nginx-api" → partition 3
# "acme-01:payment-processor" → partition 7
```

### Retention

- **Short-lived topics** (k8s-events, metrics): 7 days
- **Long-lived topics** (cicd-events, slack-incidents): 30 days
- **Audit topics**: 90 days

### Replication Factor

- **Production**: 3 (high availability)
- **Development**: 1 (cost savings)

---

## Schema Evolution

### Adding New Fields

✅ **Allowed**: Add optional fields to `payload` or new top-level optional fields

```json
{
  "tenant_id": "acme-01",
  "source": "k8s.events",
  ...
  "new_optional_field": "some_value",  // OK - optional
  "schema_version": "v1.1"
}
```

❌ **Not Allowed**: Remove or rename required fields

### Version Migration

When breaking changes are needed:

1. Introduce new schema version (e.g., `v2`)
2. Run dual-write period (write both `v1` and `v2`)
3. Migrate consumers to `v2`
4. Deprecate `v1` after 90 days

---

## Validation

### Required Field Check

```python
REQUIRED_FIELDS = [
    "tenant_id",
    "source",
    "event_type",
    "ts",
    "entity",
    "severity",
    "payload",
    "ingest_id",
    "schema_version"
]

def validate_envelope(event: dict) -> bool:
    for field in REQUIRED_FIELDS:
        if field not in event:
            raise ValueError(f"Missing required field: {field}")

    # Validate severity enum
    if event["severity"] not in ["debug", "info", "warn", "error", "critical"]:
        raise ValueError(f"Invalid severity: {event['severity']}")

    # Validate timestamp format
    try:
        datetime.fromisoformat(event["ts"].replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Invalid timestamp format: {event['ts']}")

    return True
```

### Schema Registry Integration

Use **Confluent Schema Registry** or **AWS Glue Schema Registry**:

```python
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer

# Register Avro schema
schema_str = """
{
  "type": "record",
  "name": "CanonicalEvent",
  "namespace": "com.acme.events",
  "fields": [
    {"name": "tenant_id", "type": "string"},
    {"name": "source", "type": "string"},
    ...
  ]
}
"""

schema_registry_client = SchemaRegistryClient({"url": "http://schema-registry:8081"})
avro_serializer = AvroSerializer(schema_registry_client, schema_str)
```

---

## Idempotency

### Deduplication Strategy

Use `ingest_id` to prevent duplicate processing:

```python
# At sink (Neo4j, OpenSearch, etc.)
def store_event(event: dict):
    ingest_id = event["ingest_id"]

    # Check if already processed
    if redis_client.exists(f"processed:{ingest_id}"):
        logger.info(f"Skipping duplicate event: {ingest_id}")
        return

    # Process event
    neo4j_service.store(event)

    # Mark as processed (24h TTL)
    redis_client.setex(f"processed:{ingest_id}", 86400, "1")
```

---

## Performance Considerations

### Compression

Enable compression at Kafka producer level:

```python
producer_config = {
    "bootstrap.servers": "localhost:9092",
    "compression.type": "snappy",  # or "lz4", "gzip"
}
```

**Benchmarks**:
- `snappy`: 2-3x compression, fast
- `lz4`: 2-3x compression, faster than snappy
- `gzip`: 4-5x compression, slower

### Batch Size

Tune batch size for throughput:

```python
producer_config = {
    "batch.size": 16384,  # 16KB (default)
    "linger.ms": 10,      # Wait 10ms for batching
}
```

---

## Migration from Existing Events

### K8s Events (Current Format)

**Before** (raw K8s event):
```json
{
  "metadata": {"name": "nginx.oom", "namespace": "payments"},
  "involvedObject": {"kind": "Pod", "name": "nginx-api-xyz"},
  "reason": "OOMKilled",
  "message": "Container was OOMKilled",
  "type": "Warning",
  "firstTimestamp": "2025-10-30T07:41:03Z"
}
```

**After** (canonical envelope):
```json
{
  "tenant_id": "acme-01",
  "source": "k8s.events",
  "event_type": "PodOOMKilled",
  "ts": "2025-10-30T07:41:03Z",
  "entity": {
    "namespace": "payments",
    "service": "nginx-api",
    "pod": "nginx-api-xyz"
  },
  "severity": "error",
  "payload": { ...original K8s event... },
  "ingest_id": "uuid",
  "schema_version": "v1"
}
```

### Transformation Pipeline

```python
def transform_k8s_event(raw_event: dict, tenant_id: str) -> dict:
    """Transform K8s event to canonical envelope"""

    involved_obj = raw_event["involvedObject"]

    return {
        "tenant_id": tenant_id,
        "source": "k8s.events",
        "event_type": f"{involved_obj['kind']}{raw_event['reason']}",
        "ts": raw_event["firstTimestamp"],
        "correlation_ids": {},
        "entity": {
            "namespace": raw_event["metadata"]["namespace"],
            "service": extract_service_from_pod(involved_obj["name"]),
            "pod": involved_obj["name"],
        },
        "severity": "error" if raw_event["type"] == "Warning" else "info",
        "payload": raw_event,
        "ingest_id": str(uuid.uuid4()),
        "schema_version": "v1"
    }
```

---

## Testing

### Example Test Cases

```python
import pytest
from src.ingestion.envelope import validate_envelope, CanonicalEvent

def test_valid_envelope():
    event = {
        "tenant_id": "test-01",
        "source": "k8s.events",
        "event_type": "PodOOMKilled",
        "ts": "2025-10-30T07:41:03Z",
        "correlation_ids": {},
        "entity": {"service": "nginx"},
        "severity": "error",
        "payload": {},
        "ingest_id": "uuid",
        "schema_version": "v1"
    }
    assert validate_envelope(event) == True

def test_missing_required_field():
    event = {"tenant_id": "test-01"}
    with pytest.raises(ValueError, match="Missing required field"):
        validate_envelope(event)

def test_invalid_severity():
    event = {
        "tenant_id": "test-01",
        "source": "k8s.events",
        "event_type": "PodOOMKilled",
        "ts": "2025-10-30T07:41:03Z",
        "correlation_ids": {},
        "entity": {"service": "nginx"},
        "severity": "invalid",  # Invalid
        "payload": {},
        "ingest_id": "uuid",
        "schema_version": "v1"
    }
    with pytest.raises(ValueError, match="Invalid severity"):
        validate_envelope(event)
```

---

## FAQ

### Q: Why not use vendor-specific schemas?

**A**: Vendor schemas vary wildly. Downstream agents would need custom parsers for each source. Canonical envelope = single parser.

### Q: What if payload is too large (>1MB)?

**A**: Store payload externally (S3) and include reference:

```json
{
  "payload_ref": "s3://events/acme-01/evt-123.json",
  "payload_size_bytes": 2048000
}
```

### Q: How to handle high-cardinality fields?

**A**: Keep high-cardinality fields (trace IDs, pod names) in `payload` or `correlation_ids`, not in partition key.

### Q: Can I add custom fields?

**A**: Yes, add to `payload` (vendor-specific) or extend `entity` (if universally applicable).

---

## References

- [CloudEvents Spec](https://cloudevents.io/) - Inspiration for envelope design
- [Kafka Best Practices](https://kafka.apache.org/documentation/)
- [Schema Registry](https://docs.confluent.io/platform/current/schema-registry/)

---

**Next**: See [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md) for how to implement this.