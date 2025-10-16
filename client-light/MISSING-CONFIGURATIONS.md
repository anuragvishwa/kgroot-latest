# Missing Configurations - Detailed Analysis

## Summary of Issues

All components are trying to connect to `kafka:9092` (hardcoded localhost fallback) instead of the actual Kafka broker `98.90.147.12:9092`. The environment variables are NOT being passed from the Helm chart to the containers.

---

## 1. Alert-Receiver (alerts-enricher)

### Current Error:
```
Connection error: getaddrinfo ENOTFOUND kafka
broker: kafka:9092
```

### Root Cause:
The alert-receiver deployment template **doesn't pass any environment variables** to the container!

### What the Code Expects (from `alerts-enricher/src/index.ts`):
```typescript
const KAFKA_BROKERS = (process.env.KAFKA_BROKERS || 'localhost:9092').split(',');
const KAFKA_GROUP = process.env.KAFKA_GROUP || 'alerts-enricher-alerts';
const INPUT_TOPIC = process.env.INPUT_TOPIC || 'events.normalized';
const OUTPUT_TOPIC = process.env.OUTPUT_TOPIC || 'alerts.enriched';
const STATE_RESOURCE_TOPIC = process.env.STATE_RESOURCE_TOPIC || 'state.k8s.resource';
const STATE_TOPOLOGY_TOPIC = process.env.STATE_TOPOLOGY_TOPIC || 'state.k8s.topology';
const GROUPING_WINDOW_MIN = parseInt(process.env.GROUPING_WINDOW_MIN || '5', 10);
const ENABLE_GROUPING = process.env.ENABLE_GROUPING !== 'false';
```

### What's Missing in Helm Template:
File: `client-light/helm-chart/templates/alert-receiver-deployment.yaml`

**Current:** The deployment has NO env vars section!

**Needs:** Add env vars section like this:
```yaml
env:
  - name: KAFKA_BROKERS
    valueFrom:
      configMapKeyRef:
        name: {{ include "kg-rca-agent.fullname" . }}-config
        key: KAFKA_BROKERS
  - name: KAFKA_GROUP
    value: "alerts-enricher-{{ .Values.client.id }}"
  - name: INPUT_TOPIC
    valueFrom:
      configMapKeyRef:
        name: {{ include "kg-rca-agent.fullname" . }}-config
        key: KAFKA_TOPIC_EVENTS
  - name: OUTPUT_TOPIC
    valueFrom:
      configMapKeyRef:
        name: {{ include "kg-rca-agent.fullname" . }}-config
        key: KAFKA_TOPIC_ALERTS
  - name: STATE_RESOURCE_TOPIC
    valueFrom:
      configMapKeyRef:
        name: {{ include "kg-rca-agent.fullname" . }}-config
        key: TOPIC_STATE
  - name: STATE_TOPOLOGY_TOPIC
    valueFrom:
      configMapKeyRef:
        name: {{ include "kg-rca-agent.fullname" . }}-config
        key: TOPIC_TOPO
```

---

## 2. State-Watcher

### Current Error:
```
kafka: client has run out of available brokers to talk to: dial tcp: lookup kafka on 10.96.0.10:53: no such host
```

### Root Cause:
Environment variables ARE being passed, but there might be additional issues (leader election, RBAC, etc.)

### What the Code Expects (from `state-watcher/main.go`):
```go
cluster := getenv("CLUSTER_NAME", "minikube")
brokers := strings.Split(getenv("KAFKA_BOOTSTRAP", "kafka:9092"), ",")
topicRes := getenv("TOPIC_STATE", "state.k8s.resource")
topicTopo := getenv("TOPIC_TOPO", "state.k8s.topology")
clientID := getenv("KAFKA_CLIENT_ID", "state-watcher")
promURL := getenv("PROM_URL", "http://kube-prometheus-stack-prometheus.monitoring.svc:9090")
topicProm := getenv("TOPIC_PROM_TARGETS", "state.prom.targets")
leaseNS := getenv("LEASE_NAMESPACE", "observability")
leaseName := getenv("LEASE_NAME", "state-watcher-leader")
id := getenv("POD_NAME", "") // Downward API
```

### What's Configured:
✅ KAFKA_BOOTSTRAP, CLUSTER_NAME, TOPIC_STATE, TOPIC_TOPO, KAFKA_CLIENT_ID are all set

### What's Missing:
1. **POD_NAME** - Needs Downward API
2. **PROM_URL** - Optional but code tries to use it
3. **TOPIC_PROM_TARGETS** - Missing from configmap
4. **LEASE_NAMESPACE** - For leader election
5. **LEASE_NAME** - For leader election

### Additional Missing:
The deployment needs Downward API for POD_NAME:
```yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
```

---

## 3. Vector

### Current Status:
No logs = container crashes immediately

### Likely Issue:
Vector runs as non-root (user 65534) but needs to:
1. Read from `/var/log/pods/**` (requires hostPath volume)
2. Access Docker socket or containerd socket

### What's Missing in Template:
```yaml
volumes:
  - name: varlog
    hostPath:
      path: /var/log/pods
  - name: varlibdockercontainers
    hostPath:
      path: /var/lib/docker/containers
```

And volume mounts:
```yaml
volumeMounts:
  - name: varlog
    mountPath: /var/log/pods
    readOnly: true
  - name: varlibdockercontainers
    mountPath: /var/lib/docker/containers
    readOnly: true
  - name: config
    mountPath: /etc/vector
```

Also needs to run with correct permissions or on host network.

---

## 4. Event-Exporter

### Current Status:
Looks like it's working! It connects to Kafka successfully and then gets terminated (probably by Kubernetes health checks or restart policy).

### Log Shows:
```
kafka: Producer initialized for topic: minikube-test-cluster.events.normalized, brokers: [98.90.147.12:9092]
```

This is **SUCCESS**! The event-exporter is configured correctly.

### Possible Issue:
It receives SIGTERM after 55 seconds, which suggests:
1. No readiness/liveness probes configured (crashing due to timeout)
2. Or it successfully starts but has no events to export yet

---

## Complete Fix Checklist

### ConfigMap Updates (configmap.yaml)
Add these missing keys:
```yaml
TOPIC_PROM_TARGETS: "{{ .Values.client.id }}.state.prom.targets"
PROM_URL: "http://kube-prometheus-stack-prometheus.monitoring.svc:9090"
LEASE_NAMESPACE: "{{ .Release.Namespace }}"
LEASE_NAME: "state-watcher-leader"
KAFKA_TOPIC_ALERTS_OUTPUT: "{{ .Values.client.id }}.alerts.enriched"
```

### Alert-Receiver Deployment
Add complete env section with all KAFKA vars.

### State-Watcher Deployment
Add Downward API for POD_NAME and POD_NAMESPACE.

### Vector DaemonSet
1. Add hostPath volumes for log access
2. Fix permissions/security context
3. May need `hostNetwork: true` or `hostPID: true`

### Event-Exporter Deployment
✅ Already working! Just needs:
- Remove/adjust health checks if causing restarts
- Or it's fine as-is

---

## Priority Order

1. **Alert-Receiver** - Quick win, just add env vars
2. **State-Watcher** - Add Downward API vars
3. **Vector** - More complex, needs hostPath volumes
4. **Event-Exporter** - Already working, minimal fixes

Would you like me to implement these fixes now?
