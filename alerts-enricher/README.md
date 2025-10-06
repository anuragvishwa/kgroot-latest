# Alerts Enricher

Enriches Prometheus alerts from `events.normalized` topic with Kubernetes context from state topics.

## What It Does

1. Consumes alerts from `events.normalized` topic
2. Maintains in-memory cache of:
   - Kubernetes resource state from `state.k8s.resource`
   - Kubernetes topology from `state.k8s.topology`
3. Enriches each alert with:
   - Current resource state (spec, status)
   - Related resources (based on topology)
   - Topology edges (relationships)
4. Produces enriched alerts to `alerts.enriched` topic

## Enrichment Example

**Input** (from events.normalized):
```json
{
  "etype": "prom.alert",
  "event_id": "abc123",
  "reason": "KubePodCrashLooping",
  "severity": "WARNING",
  "subject": {
    "kind": "Pod",
    "ns": "default",
    "name": "myapp-pod"
  }
}
```

**Output** (to alerts.enriched):
```json
{
  "etype": "prom.alert",
  "event_id": "abc123",
  "reason": "KubePodCrashLooping",
  "severity": "WARNING",
  "subject": {
    "kind": "Pod",
    "ns": "default",
    "name": "myapp-pod"
  },
  "enrichment": {
    "enriched_at": "2025-10-06T13:00:00Z",
    "resource": {
      "kind": "Pod",
      "status": {
        "phase": "CrashLoopBackOff",
        "restartCount": 5
      }
    },
    "topology": [
      {
        "from": "replicaset:default:myapp-rs",
        "to": "pod:default:myapp-pod",
        "type": "CONTROLS"
      }
    ],
    "related_resources": [
      {
        "kind": "ReplicaSet",
        "name": "myapp-rs",
        "status": { "replicas": 1, "ready": 0 }
      }
    ]
  }
}
```

## Building

### Local Development

```bash
npm install
npm run dev
```

### Docker Build

```bash
docker build -t alerts-enricher:latest .
```

### Minikube

```bash
# Build
docker build -t alerts-enricher:latest .

# Load into Minikube
minikube image load alerts-enricher:latest

# Deploy
kubectl apply -f ../k8s/alerts-enricher.yaml
```

## Configuration

Environment variables:

- `KAFKA_BROKERS`: Kafka bootstrap servers (default: `localhost:9092`)
- `KAFKA_GROUP`: Consumer group ID (default: `alerts-enricher-alerts`)
- `INPUT_TOPIC`: Input topic to consume (default: `events.normalized`)
- `OUTPUT_TOPIC`: Output topic to produce (default: `alerts.enriched`)
- `STATE_RESOURCE_TOPIC`: Kubernetes resource state topic (default: `state.k8s.resource`)
- `STATE_TOPOLOGY_TOPIC`: Kubernetes topology topic (default: `state.k8s.topology`)

## Monitoring

Check logs:
```bash
kubectl logs -n observability deployment/alerts-enricher -f
```

Check consumer lag:
```bash
kubectl exec -n observability kafka-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group alerts-enricher-alerts \
  --describe
```

## RCA Use Case

The enriched alerts are ideal for root cause analysis because they contain:

1. **Alert Context**: What alert fired and why
2. **Resource State**: Current state of the affected resource
3. **Topology**: What other resources are related (owner, dependencies)
4. **Related Resources**: State of related resources (e.g., parent ReplicaSet)

This allows RCA systems to immediately understand:
- What failed
- What state it was in
- What it depends on
- What depends on it
