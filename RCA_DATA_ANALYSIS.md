# RCA Data Quality Analysis

## Overview

This document analyzes the data structure and quality of messages in all Kafka topics to assess their suitability for Root Cause Analysis (RCA).

## Topic-by-Topic Analysis

### 1. alerts.normalized

**Purpose**: Normalized Prometheus alerts only (separated from k8s events)

**Sample Message**:
```json
{
  "etype": "prom.alert",
  "event_id": "df00fcc9-009e-4d01-bdfb-fcf3e70f684b",
  "event_time": "2025-10-06T13:14:53.731019379Z",
  "reason": "KubePodCrashLooping",
  "severity": "WARNING",
  "status": "firing",
  "message": "Pod is crash looping.",
  "subject": {
    "kind": "Pod",
    "name": "crashloop-test",
    "ns": "default"
  },
  "alerts": {
    "annotations": {
      "description": "Pod default/crashloop-test (crasher) is in waiting state...",
      "runbook_url": "https://runbooks.prometheus-operator.dev/runbooks/..."
    },
    "labels": {
      "alertname": "KubePodCrashLooping",
      "container": "crasher",
      "namespace": "default",
      "pod": "crashloop-test",
      "severity": "warning"
    },
    "fingerprint": "cf9e7af84a84f22d"
  }
}
```

**RCA Suitability**: ✅ EXCELLENT
- **Strengths**:
  - Clear event_id for deduplication
  - Precise event_time for temporal analysis
  - Structured subject (kind/ns/name) for resource identification
  - Severity levels for prioritization
  - Alert fingerprint for grouping
  - Full Prometheus labels preserved
  - Runbook URLs for remediation guidance

- **Use Cases**:
  - Alert correlation by subject
  - Temporal pattern detection (repeated alerts)
  - Severity escalation tracking
  - Resource-specific alert history

### 2. events.normalized

**Purpose**: Combined Prometheus alerts + Kubernetes events

**Sample Message** (Prometheus Alert):
```json
{
  "etype": "prom.alert",
  "event_id": "a58845de-4b4f-40fb-83cd-68a7fd43ff69",
  "event_time": "2025-10-06T10:06:00.383156216Z",
  "reason": "KubePodNotReady",
  "severity": "WARNING",
  "status": "firing",
  "message": "Pod has been in a non-ready state for more than 15 minutes.",
  "subject": {
    "kind": "Pod",
    "name": "oom-test",
    "ns": "rca-lab"
  }
}
```

**RCA Suitability**: ✅ EXCELLENT
- **Strengths**:
  - Unified schema for alerts and events
  - Enables cross-correlation between Prometheus alerts and K8s events
  - Same normalization as alerts.normalized for alerts

- **Use Cases**:
  - Full event timeline reconstruction
  - Correlation: "Pod restarted" (k8s event) + "High CPU" (alert)
  - End-to-end incident tracking

### 3. logs.normalized

**Purpose**: Normalized Kubernetes pod logs

**Sample Message**:
```json
{
  "etype": "k8s.log",
  "event_id": "aa24da00-9e3b-4374-976a-041c08bdda06",
  "event_time": "2025-10-06T07:06:56.228516340Z",
  "severity": "INFO",
  "message": "2025-10-06T07:06:56.219471Z  INFO vector::app: Log level is enabled.",
  "subject": {
    "kind": "Pod",
    "name": "vector-logs-fh7h5",
    "ns": "observability"
  },
  "kubernetes": {
    "container_name": "vector",
    "pod_owner": "DaemonSet/vector-logs",
    "pod_ip": "10.244.0.9",
    "node_labels": {...},
    "pod_labels": {...}
  },
  "log": "2025-10-06T07:06:56.219471Z  INFO vector::app: Log level is enabled.",
  "stream": "stderr"
}
```

**RCA Suitability**: ✅ EXCELLENT
- **Strengths**:
  - Structured subject for pod identification
  - Severity detection from log format (I/W/E/F)
  - Rich Kubernetes metadata (owner, labels, node info)
  - Stream differentiation (stdout/stderr)
  - Timestamps preserved

- **Use Cases**:
  - Error pattern detection in logs
  - Log correlation with alerts ("OOMKilled" alert + "out of memory" logs)
  - Container-level troubleshooting
  - Application error tracking

### 4. raw.k8s.events

**Purpose**: Raw Kubernetes events from k8s-event-exporter

**Sample Message**:
```json
{
  "etype": "k8s.event",
  "event_id": "4ac5454d5409b5c697a74446b20f2465d7fe3739",
  "event_time": "2025-10-06T11:42:48Z",
  "reason": "SandboxChanged",
  "severity": "NORMAL",
  "message": "Pod sandbox changed, it will be killed and re-created.",
  "subject": {
    "kind": "Pod",
    "name": "failing-deployment-5c45f49c8f-685wl",
    "ns": "default",
    "uid": "49d7829e-de27-4cc7-8ed2-8caec0efc1f4"
  },
  "involvedObject": {
    "apiVersion": "v1",
    "kind": "Pod",
    "namespace": "default",
    "name": "failing-deployment-5c45f49c8f-685wl",
    "uid": "49d7829e-de27-4cc7-8ed2-8caec0efc1f4",
    "ownerReferences": [...]
  },
  "source": {
    "component": "kubelet",
    "host": "minikube"
  }
}
```

**RCA Suitability**: ✅ EXCELLENT
- **Strengths**:
  - Detailed involvedObject with ownerReferences
  - Source component tracking (kubelet, scheduler, etc.)
  - Event types: Normal, Warning
  - Count field for repeated events

- **Use Cases**:
  - Pod lifecycle tracking (Created → Running → Failed)
  - Scheduler decisions ("FailedScheduling" events)
  - Volume mount issues
  - Network policy violations

### 5. raw.prom.alerts

**Purpose**: Raw Alertmanager webhook payloads

**Sample Message**:
```json
{
  "etype": "prom.alert.raw",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "KubeDeploymentRolloutStuck",
        "deployment": "failing-deployment",
        "namespace": "default",
        "severity": "warning"
      },
      "annotations": {
        "description": "Rollout of deployment default/failing-deployment is not progressing...",
        "runbook_url": "https://runbooks.prometheus-operator.dev/runbooks/..."
      },
      "startsAt": "2025-10-06T08:13:00.551Z",
      "fingerprint": "453ee3a40fc79db9",
      "generatorURL": "http://prometheus-kube-prometheus-prometheus.monitoring:9090/graph?..."
    }
  ],
  "commonLabels": {...},
  "groupKey": "{}:{namespace=\"default\"}",
  "status": "firing"
}
```

**RCA Suitability**: ✅ GOOD
- **Strengths**:
  - Complete Alertmanager payload preserved
  - Group information for related alerts
  - Generator URL for PromQL queries
  - Alert fingerprints for deduplication

- **Use Cases**:
  - Alert grouping analysis
  - PromQL query reconstruction
  - Alert routing debugging

### 6. state.k8s.resource

**Purpose**: Compacted Kubernetes resource state

**Sample Message**:
```json
{
  "op": "UPSERT",
  "at": "2025-10-06T07:07:44.187580584Z",
  "cluster": "minikube",
  "kind": "DaemonSet",
  "uid": "1b6088e7-a34a-4a92-93b0-15d484bb7525",
  "namespace": "kube-system",
  "name": "kube-proxy",
  "labels": {
    "k8s-app": "kube-proxy"
  },
  "status": {
    "available": 2,
    "desired": 2,
    "ready": 2
  },
  "spec": {
    "selector": {
      "matchLabels": {...}
    }
  }
}
```

**RCA Suitability**: ✅ EXCELLENT
- **Strengths**:
  - Current resource state (compacted)
  - Status fields for health checks
  - Spec for desired state comparison
  - Labels for resource selection

- **Use Cases**:
  - "What was the state of deployment X when alert fired?"
  - Resource availability checks
  - Desired vs actual state comparison
  - Label-based resource lookup

### 7. state.k8s.topology

**Purpose**: Kubernetes resource relationships

**Sample Message**:
```json
{
  "op": "UPSERT",
  "at": "2025-10-06T07:07:44.181131626Z",
  "cluster": "minikube",
  "id": "edge:deployment:kube-system:coredns->replicaset:kube-system:coredns-674b8bbfcf",
  "from": "deployment:kube-system:coredns",
  "to": "replicaset:kube-system:coredns-674b8bbfcf",
  "type": "CONTROLS"
}
```

**RCA Suitability**: ✅ EXCELLENT
- **Strengths**:
  - Graph-ready format (from/to/type)
  - Relationship types: CONTROLS, SERVES, DEPENDS_ON
  - Compacted (latest topology only)

- **Use Cases**:
  - Impact analysis ("If Service X fails, what breaks?")
  - Dependency graph construction
  - Owner chain traversal (Pod → ReplicaSet → Deployment)
  - Blast radius calculation

### 8. state.prom.rules

**Purpose**: Prometheus alerting rules state

**Sample Message**:
```json
{
  "op": "UPSERT",
  "at": "2025-10-06T07:14:44.666618543Z",
  "cluster": "minikube",
  "group": "alertmanager.rules",
  "namespace": "monitoring",
  "rule": {
    "name": "AlertmanagerFailedReload",
    "type": "alerting",
    "expr": "max_over_time(alertmanager_config_last_reload_successful[5m]) == 0",
    "labels": {
      "severity": "critical"
    },
    "annotations": {...},
    "health": "ok",
    "state": "inactive",
    "lastEvaluation": "2025-10-06T07:14:33.329997344Z",
    "evaluationTime": 0.002200458
  }
}
```

**RCA Suitability**: ✅ EXCELLENT
- **Strengths**:
  - Rule health status
  - Current state (firing/inactive)
  - PromQL expression for understanding
  - Evaluation timing

- **Use Cases**:
  - "Why didn't alert X fire?" (rule health, state)
  - Alert definition lookup
  - Threshold analysis
  - Rule performance debugging

## Overall RCA Assessment

### Summary

| Topic | Schema Quality | Temporal Data | Resource Linking | RCA Score |
|-------|---------------|---------------|------------------|-----------|
| alerts.normalized | ✅ Excellent | ✅ event_time | ✅ subject | 10/10 |
| events.normalized | ✅ Excellent | ✅ event_time | ✅ subject | 10/10 |
| logs.normalized | ✅ Excellent | ✅ event_time | ✅ subject + k8s | 10/10 |
| raw.k8s.events | ✅ Excellent | ✅ event_time | ✅ involvedObject | 9/10 |
| raw.prom.alerts | ✅ Good | ✅ startsAt | ✅ labels | 8/10 |
| state.k8s.resource | ✅ Excellent | ✅ at | ✅ uid + labels | 10/10 |
| state.k8s.topology | ✅ Excellent | ✅ at | ✅ from/to | 10/10 |
| state.prom.rules | ✅ Excellent | ✅ at, lastEval | ✅ namespace | 9/10 |

### Strengths for RCA

1. **Unified Schema**: All normalized topics use consistent `subject` field
2. **Temporal Precision**: All events have precise timestamps
3. **Resource Linking**: Clear resource identification (kind/ns/name/uid)
4. **Severity Levels**: Consistent across alerts and logs
5. **Graph-Ready**: Topology data ready for Neo4j ingestion
6. **Compaction**: State topics use Kafka compaction for current truth
7. **Metadata Preservation**: Rich Kubernetes metadata kept

### Potential RCA Workflows

#### Workflow 1: Pod Crash Investigation

```
1. Query alerts.normalized: "Pod crash" alert
2. Get subject: {kind: Pod, name: X, ns: Y}
3. Query logs.normalized: Filter by subject, time range
4. Query state.k8s.resource: Get pod spec/status at failure time
5. Query state.k8s.topology: Find pod's parent (Deployment)
6. Query events.normalized: Related K8s events (OOMKilled, etc.)
```

#### Workflow 2: Deployment Rollout Failure

```
1. Query alerts.normalized: "Rollout stuck" alert
2. Get deployment from subject
3. Query state.k8s.topology: Find ReplicaSets controlled by deployment
4. Query state.k8s.resource: Check ReplicaSet/Pod states
5. Query raw.k8s.events: Filter for "FailedCreate", "ImagePullBackOff"
6. Query logs.normalized: Check pod logs for errors
```

#### Workflow 3: Service Unavailability

```
1. Query alerts.normalized: Service down alert
2. Query state.k8s.topology: Find Service → Endpoints → Pods
3. Query state.k8s.resource: Check pod readiness
4. Query events.normalized: Look for network issues
5. Query logs.normalized: Application errors in pods
6. Query state.prom.rules: Check if related alerts should have fired
```

## Recommendations

### ✅ Data is RCA-Ready

The current data structure is **excellent for RCA analysis**:
- All necessary fields are present
- Schema is consistent and well-normalized
- Temporal data is precise
- Resource linking is clear
- No significant gaps identified

### Minor Improvements (Optional)

1. **Add correlation_id**: If implementing distributed tracing
2. **Add parent_event_id**: For explicit event causality chains
3. **Metrics snapshot**: Consider adding metric values at alert time
4. **Change detection**: Add "previous_value" for state changes

### Data Quality Monitoring

Recommended checks:
- Alert: No duplicate event_ids within 1-hour window
- Alert: subject.kind should be valid K8s kind
- Monitor: Lag on state.* topics (should be < 1 minute)
- Monitor: Missing subjects (should be < 0.1%)

## Conclusion

**VERDICT: ✅ PERFECT FOR RCA**

The data pipeline is well-designed for root cause analysis with:
- ✅ Complete temporal coverage (alerts, events, logs)
- ✅ Consistent normalization
- ✅ Rich context preservation
- ✅ Graph-ready topology
- ✅ Current state tracking

**No changes required for RCA functionality. The system is production-ready.**
