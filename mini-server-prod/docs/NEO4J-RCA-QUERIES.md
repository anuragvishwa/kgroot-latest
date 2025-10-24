# Neo4j RCA Query Reference Guide

Complete guide for Root Cause Analysis, visualization, debugging, and monitoring using Neo4j Cypher queries.

---

## 🗺️ Schema Reference

**Important**: The actual Neo4j properties use abbreviated names. Here's the mapping:

| Common Name | Actual Property | Type | Example |
|------------|-----------------|------|---------|
| Namespace | `ns` | String | `"kgroot"` |
| Status | `status_json` | JSON String | `'{"phase":"Running"}'` |
| Created At | `updated_at` | DateTime | `2025-10-23T12:00:00Z` |
| Labels | `labels_json` | JSON String | `'{"app":"web"}'` |
| Pod IP | `podIP` | String | `"192.168.1.10"` |
| Node Name | `node` | String | `"worker-1"` |
| Image | `image` | String | `"nginx:latest"` |

**Common Properties Available**:
- `client_id` - Cluster identifier (e.g., "af-7")
- `kind` - Resource type (e.g., "Pod", "Service")
- `name` - Resource name
- `uid` - Kubernetes UID
- `rid` - Internal resource ID
- `cluster` - Cluster name

**To see all properties for a resource**:
```cypher
MATCH (n:Resource {client_id: 'af-7'})
RETURN keys(n) LIMIT 1;
```

---

## Table of Contents

1. [Basic Graph Exploration](#1-basic-graph-exploration)
2. [Root Cause Analysis Queries](#2-root-cause-analysis-queries)
3. [Event Correlation & Timeline Analysis](#3-event-correlation--timeline-analysis)
4. [Resource Relationship Mapping](#4-resource-relationship-mapping)
5. [Alert Investigation](#5-alert-investigation)
6. [Performance & Health Monitoring](#6-performance--health-monitoring)
7. [Debugging & Troubleshooting](#7-debugging--troubleshooting)
8. [Visualization Queries](#8-visualization-queries)
9. [Multi-Cluster Analysis](#9-multi-cluster-analysis)
10. [Advanced Pattern Detection](#10-advanced-pattern-detection)

---

## 1. Basic Graph Exploration

### 1.1 Count Resources by Type
```cypher
// Get count of all resource types for a specific cluster
MATCH (n:Resource {client_id: 'af-4'})
RETURN n.kind AS ResourceType, count(n) AS Count
ORDER BY Count DESC;
```
**Purpose**: Understand cluster composition and resource distribution.
**Use Case**: Initial cluster assessment, capacity planning.

### 1.2 List All Namespaces
```cypher
// Get all unique namespaces with resource counts
MATCH (n:Resource {client_id: 'af-7'})
WHERE n.ns IS NOT NULL
WITH DISTINCT n.ns AS Namespace
MATCH (r:Resource {client_id: 'af-7', ns: Namespace})
RETURN Namespace,
       count(r) AS ResourceCount
ORDER BY ResourceCount DESC;
```
**Purpose**: Namespace overview and health check.
**Use Case**: Multi-tenant cluster analysis.
**Note**: Namespaces are stored in the `ns` property, not as separate Namespace resources.

### 1.3 Resource Details
```cypher
// Get detailed information about a specific resource (use actual property names!)
MATCH (n:Resource {client_id: 'af-7', kind: 'Pod', name: 'disk-pressure'})
RETURN n.name AS Name,
       n.ns AS Namespace,
       n.status_json AS StatusJSON,
       n.updated_at AS UpdatedAt,
       n.node AS Node,
       n.podIP AS PodIP,
       n.image AS Image,
       n.labels_json AS LabelsJSON;
```
**Purpose**: Deep dive into specific resource configuration.
**Use Case**: Resource inspection, configuration audit.
**Note**: Properties use abbreviated names (ns, not namespace) and JSON strings for complex data.

---

## 2. Root Cause Analysis Queries

### 2.1 Find Failed Pods and Their Dependencies
```cypher
// Find all failed pods and trace their dependencies
MATCH (pod:Resource {client_id: 'af-7', kind: 'Pod'})
WHERE pod.status_json =~ '(?i).*(failed|crashloopbackoff|error).*'
   OR pod.status_json CONTAINS '"phase":"Failed"'
   OR pod.status_json CONTAINS 'CrashLoopBackOff'
OPTIONAL MATCH (pod)-[r:USES|MOUNTS|DEPENDS_ON*1..3]-(dep:Resource)
RETURN pod.name AS FailedPod,
       pod.ns AS Namespace,
       pod.status_json AS StatusJSON,
       pod.node AS Node,
       collect(DISTINCT {
         type: dep.kind,
         name: dep.name,
         status: dep.status_json,
         relationship: type(r)
       }) AS Dependencies
ORDER BY pod.updated_at DESC
LIMIT 20;
```
**Purpose**: Identify failing pods and understand what they depend on.
**Use Case**: Pod failure investigation, dependency analysis.
**Note**: Status is stored as JSON, so we search within the JSON string.

### 2.2 Trace Impact Radius (What Broke When This Failed?)
```cypher
// Find all resources affected by a failed component
MATCH (failed:Resource {client_id: 'af-4', name: 'api-server-deployment'})
WHERE failed.status =~ '(?i).*(failed|error|unavailable).*'
MATCH (affected:Resource {client_id: 'af-4'})-[*1..4]->(failed)
RETURN failed.name AS FailedResource,
       failed.kind AS Type,
       collect(DISTINCT {
         name: affected.name,
         kind: affected.kind,
         namespace: affected.namespace,
         status: affected.status
       }) AS AffectedResources,
       count(affected) AS ImpactCount
ORDER BY ImpactCount DESC;
```
**Purpose**: Understand blast radius of a failure.
**Use Case**: Incident impact assessment, cascade failure analysis.

### 2.3 Recent Changes Before Incident
```cypher
// Find resources that changed within 30 minutes before an incident
MATCH (n:Resource {client_id: 'af-4'})
WHERE n.last_updated > datetime('2025-10-23T12:00:00Z') - duration({minutes: 30})
  AND n.last_updated < datetime('2025-10-23T12:00:00Z')
RETURN n.kind AS ResourceType,
       n.name AS Name,
       n.namespace AS Namespace,
       n.last_updated AS ChangedAt,
       n.status AS CurrentStatus
ORDER BY n.last_updated DESC
LIMIT 50;
```
**Purpose**: Identify what changed before an incident (change correlation).
**Use Case**: Post-incident analysis, change management review.

### 2.4 Service Dependency Chain Analysis
```cypher
// Map complete service dependency chain
MATCH path = (svc:Resource {client_id: 'af-4', kind: 'Service', name: 'frontend-service'})
             -[:ROUTES_TO|DEPENDS_ON*1..5]->(dep:Resource)
RETURN nodes(path) AS DependencyChain,
       [n IN nodes(path) | n.kind] AS Types,
       [n IN nodes(path) | n.name] AS Names,
       [n IN nodes(path) | n.status] AS Statuses,
       length(path) AS ChainDepth
ORDER BY ChainDepth DESC;
```
**Purpose**: Visualize complete service dependency tree.
**Use Case**: Architecture review, bottleneck identification.

---

## 3. Event Correlation & Timeline Analysis

### 3.1 Event Timeline for Resource
```cypher
// Get chronological event timeline for a specific resource
MATCH (e:Event {client_id: 'af-4'})
WHERE e.involved_object_name = 'api-server-pod-xyz'
RETURN e.type AS EventType,
       e.reason AS Reason,
       e.message AS Message,
       e.timestamp AS Timestamp,
       e.count AS OccurrenceCount
ORDER BY e.timestamp DESC
LIMIT 100;
```
**Purpose**: Build event timeline for troubleshooting.
**Use Case**: Pod restart investigation, event pattern analysis.

### 3.2 Correlated Events Across Resources
```cypher
// Find events that occurred around the same time across different resources
MATCH (e1:Event {client_id: 'af-4'})
WHERE e1.timestamp > datetime('2025-10-23T12:00:00Z') - duration({minutes: 5})
  AND e1.timestamp < datetime('2025-10-23T12:00:00Z') + duration({minutes: 5})
WITH e1.timestamp AS incident_time
MATCH (e2:Event {client_id: 'af-4'})
WHERE e2.timestamp > incident_time - duration({minutes: 2})
  AND e2.timestamp < incident_time + duration({minutes: 2})
RETURN e2.involved_object_name AS Resource,
       e2.involved_object_kind AS Type,
       e2.reason AS Reason,
       e2.message AS Message,
       e2.timestamp AS Timestamp
ORDER BY e2.timestamp ASC;
```
**Purpose**: Find correlated events during an incident window.
**Use Case**: Cascade failure detection, root cause correlation.

### 3.3 Warning Events Leading to Failures
```cypher
// Find warning events that preceded a failure
MATCH (warn:Event {client_id: 'af-4', type: 'Warning'})
WHERE warn.timestamp > datetime() - duration({hours: 1})
OPTIONAL MATCH (fail:Event {client_id: 'af-4'})
WHERE fail.involved_object_name = warn.involved_object_name
  AND fail.timestamp > warn.timestamp
  AND fail.timestamp < warn.timestamp + duration({minutes: 10})
  AND fail.reason =~ '(?i).*(failed|error|crashed).*'
RETURN warn.involved_object_name AS Resource,
       warn.reason AS WarningReason,
       warn.message AS WarningMessage,
       warn.timestamp AS WarningTime,
       collect({
         reason: fail.reason,
         message: fail.message,
         time: fail.timestamp
       }) AS SubsequentFailures
ORDER BY warn.timestamp DESC;
```
**Purpose**: Identify early warning signs before failures.
**Use Case**: Predictive alerting, proactive remediation.

---

## 4. Resource Relationship Mapping

### 4.1 Pod to Node Mapping
```cypher
// Show which pods are running on which nodes
MATCH (pod:Resource {client_id: 'af-4', kind: 'Pod'})-[:RUNS_ON]->(node:Resource {kind: 'Node'})
RETURN node.name AS Node,
       node.status AS NodeStatus,
       collect({
         name: pod.name,
         namespace: pod.namespace,
         status: pod.status
       }) AS Pods,
       count(pod) AS PodCount
ORDER BY PodCount DESC;
```
**Purpose**: Node utilization and pod distribution analysis.
**Use Case**: Load balancing review, node failure impact assessment.

### 4.2 ConfigMap/Secret Usage
```cypher
// Find all resources using a specific ConfigMap or Secret
MATCH (resource:Resource {client_id: 'af-4'})-[:USES]->(config:Resource)
WHERE config.kind IN ['ConfigMap', 'Secret']
  AND config.name = 'app-config'
RETURN config.name AS ConfigName,
       config.kind AS Type,
       config.namespace AS Namespace,
       collect({
         kind: resource.kind,
         name: resource.name,
         namespace: resource.namespace
       }) AS UsedBy
ORDER BY size(UsedBy) DESC;
```
**Purpose**: Understand configuration impact before changes.
**Use Case**: Change impact analysis, configuration audit.

### 4.3 PVC to PV Mapping
```cypher
// Map PersistentVolumeClaims to PersistentVolumes
MATCH (pvc:Resource {client_id: 'af-4', kind: 'PersistentVolumeClaim'})
      -[:BINDS_TO]->(pv:Resource {kind: 'PersistentVolume'})
OPTIONAL MATCH (pod:Resource {kind: 'Pod'})-[:MOUNTS]->(pvc)
RETURN pvc.name AS PVC,
       pvc.namespace AS Namespace,
       pv.name AS PV,
       pv.status AS PVStatus,
       collect(pod.name) AS MountedByPods
ORDER BY pvc.namespace, pvc.name;
```
**Purpose**: Storage troubleshooting and capacity planning.
**Use Case**: Volume mount issues, storage reclamation.

### 4.4 Service to Endpoints Mapping
```cypher
// Show service endpoints and backing pods
MATCH (svc:Resource {client_id: 'af-4', kind: 'Service'})
      -[:ROUTES_TO]->(pod:Resource {kind: 'Pod'})
RETURN svc.name AS Service,
       svc.namespace AS Namespace,
       svc.cluster_ip AS ClusterIP,
       collect({
         pod: pod.name,
         status: pod.status,
         node: [(pod)-[:RUNS_ON]->(n:Resource) | n.name][0]
       }) AS Endpoints,
       count(pod) AS EndpointCount
ORDER BY svc.namespace, svc.name;
```
**Purpose**: Service connectivity and load balancing verification.
**Use Case**: Service discovery issues, endpoint troubleshooting.

---

## 5. Alert Investigation

### 5.1 Active Alerts by Severity
```cypher
// List all active alerts grouped by severity
MATCH (a:Alert {client_id: 'af-4'})
WHERE a.status = 'firing'
RETURN a.severity AS Severity,
       count(a) AS AlertCount,
       collect({
         name: a.alert_name,
         summary: a.summary,
         startsAt: a.starts_at,
         labels: a.labels
       }) AS Alerts
ORDER BY
  CASE a.severity
    WHEN 'critical' THEN 1
    WHEN 'warning' THEN 2
    WHEN 'info' THEN 3
    ELSE 4
  END;
```
**Purpose**: Prioritize alert response by severity.
**Use Case**: Incident triage, alert dashboard.

### 5.2 Alert to Resource Correlation
```cypher
// Map alerts to affected Kubernetes resources
MATCH (a:Alert {client_id: 'af-4', status: 'firing'})
WHERE a.labels.namespace IS NOT NULL
MATCH (r:Resource {client_id: 'af-4'})
WHERE r.namespace = a.labels.namespace
  AND (r.name CONTAINS a.labels.pod OR r.name CONTAINS a.labels.deployment)
RETURN a.alert_name AS Alert,
       a.severity AS Severity,
       a.summary AS Summary,
       collect({
         kind: r.kind,
         name: r.name,
         status: r.status
       }) AS AffectedResources
ORDER BY a.starts_at DESC;
```
**Purpose**: Link alerts to specific Kubernetes objects.
**Use Case**: Alert investigation, resource remediation.

### 5.3 Alert Frequency (Flapping Detection)
```cypher
// Find alerts that fire frequently (potential flapping)
MATCH (a:Alert {client_id: 'af-4'})
WHERE a.created_at > datetime() - duration({hours: 24})
WITH a.alert_name AS AlertName,
     a.fingerprint AS Fingerprint,
     count(*) AS FireCount,
     collect(a.starts_at) AS FireTimes
WHERE FireCount > 5
RETURN AlertName,
       Fingerprint,
       FireCount,
       FireTimes[0] AS FirstFire,
       FireTimes[-1] AS LastFire
ORDER BY FireCount DESC;
```
**Purpose**: Identify noisy or flapping alerts.
**Use Case**: Alert tuning, noise reduction.

### 5.4 Resolved vs Active Alerts
```cypher
// Compare resolved and active alerts over time
MATCH (a:Alert {client_id: 'af-4'})
WHERE a.created_at > datetime() - duration({days: 7})
RETURN date(a.created_at) AS Date,
       a.status AS Status,
       count(a) AS AlertCount
ORDER BY Date DESC, Status;
```
**Purpose**: Track alert trends and resolution rates.
**Use Case**: SLA monitoring, team performance metrics.

---

## 6. Performance & Health Monitoring

### 6.1 Node Resource Utilization
```cypher
// Node CPU and memory usage
MATCH (n:Resource {client_id: 'af-4', kind: 'Node'})
RETURN n.name AS Node,
       n.status AS Status,
       n.cpu_capacity AS CPUCapacity,
       n.memory_capacity AS MemoryCapacity,
       n.cpu_allocatable AS CPUAllocatable,
       n.memory_allocatable AS MemoryAllocatable,
       n.labels AS Labels
ORDER BY n.name;
```
**Purpose**: Monitor node capacity and availability.
**Use Case**: Capacity planning, node health checks.

### 6.2 Pods with High Restart Counts
```cypher
// Find pods with excessive restarts
MATCH (pod:Resource {client_id: 'af-4', kind: 'Pod'})
WHERE pod.restart_count > 5
RETURN pod.name AS Pod,
       pod.namespace AS Namespace,
       pod.restart_count AS RestartCount,
       pod.status AS Status,
       pod.created_at AS CreatedAt
ORDER BY pod.restart_count DESC
LIMIT 20;
```
**Purpose**: Identify unstable pods.
**Use Case**: Stability monitoring, crash loop investigation.

### 6.3 Resource Age Analysis
```cypher
// Find old resources that may need updates
MATCH (r:Resource {client_id: 'af-4'})
WHERE r.created_at < datetime() - duration({days: 90})
RETURN r.kind AS ResourceType,
       r.name AS Name,
       r.namespace AS Namespace,
       r.created_at AS CreatedAt,
       duration.between(r.created_at, datetime()).days AS AgeInDays
ORDER BY AgeInDays DESC
LIMIT 50;
```
**Purpose**: Identify stale resources.
**Use Case**: Resource lifecycle management, security patch tracking.

### 6.4 Namespace Resource Quotas
```cypher
// Check namespace resource usage against quotas
MATCH (quota:Resource {client_id: 'af-4', kind: 'ResourceQuota'})
MATCH (ns:Resource {kind: 'Namespace', name: quota.namespace})
OPTIONAL MATCH (r:Resource {client_id: 'af-4'})-[:IN_NAMESPACE]->(ns)
RETURN quota.namespace AS Namespace,
       quota.hard_limits AS HardLimits,
       quota.used AS Used,
       count(DISTINCT r) AS TotalResources
ORDER BY quota.namespace;
```
**Purpose**: Monitor namespace resource consumption.
**Use Case**: Multi-tenancy management, quota enforcement.

---

## 7. Debugging & Troubleshooting

### 7.1 Orphaned Resources
```cypher
// Find resources without owners (potential orphans)
MATCH (r:Resource {client_id: 'af-4'})
WHERE NOT (r)<-[:OWNS]-(:Resource)
  AND r.kind <> 'Namespace'
  AND r.kind <> 'Node'
  AND r.kind <> 'StorageClass'
  AND r.kind <> 'ClusterRole'
  AND r.kind <> 'ClusterRoleBinding'
RETURN r.kind AS ResourceType,
       r.name AS Name,
       r.namespace AS Namespace,
       r.created_at AS CreatedAt
ORDER BY r.created_at DESC;
```
**Purpose**: Find resources that may not be managed properly.
**Use Case**: Resource cleanup, garbage collection.

### 7.2 Missing Expected Resources
```cypher
// Find Deployments without ReplicaSets
MATCH (deploy:Resource {client_id: 'af-4', kind: 'Deployment'})
WHERE NOT (deploy)-[:OWNS]->(:Resource {kind: 'ReplicaSet'})
RETURN deploy.name AS Deployment,
       deploy.namespace AS Namespace,
       deploy.status AS Status,
       deploy.created_at AS CreatedAt
ORDER BY deploy.created_at DESC;
```
**Purpose**: Detect missing child resources.
**Use Case**: Deployment troubleshooting, controller issues.

### 7.3 Network Policy Impact
```cypher
// Show network policies affecting a namespace
MATCH (np:Resource {client_id: 'af-4', kind: 'NetworkPolicy'})
WHERE np.namespace = 'production'
RETURN np.name AS NetworkPolicy,
       np.pod_selector AS PodSelector,
       np.ingress_rules AS IngressRules,
       np.egress_rules AS EgressRules
ORDER BY np.name;
```
**Purpose**: Debug connectivity issues caused by network policies.
**Use Case**: Network troubleshooting, security policy review.

### 7.4 Image Pull Errors
```cypher
// Find pods with image pull errors
MATCH (e:Event {client_id: 'af-4', type: 'Warning'})
WHERE e.reason =~ '(?i).*(imagepull|backoff|errimagepull).*'
  AND e.timestamp > datetime() - duration({hours: 1})
RETURN DISTINCT e.involved_object_name AS Pod,
       e.involved_object_namespace AS Namespace,
       e.reason AS Reason,
       e.message AS Message,
       e.timestamp AS LastOccurrence
ORDER BY e.timestamp DESC;
```
**Purpose**: Identify container image issues.
**Use Case**: Registry connectivity, image availability checks.

---

## 8. Visualization Queries

### 8.1 Full Cluster Graph (Small Clusters)
```cypher
// Visualize entire cluster (use with caution on large clusters)
MATCH (n:Resource {client_id: 'af-4'})
WHERE n.namespace = 'kgroot'
OPTIONAL MATCH (n)-[r]-(m:Resource {client_id: 'af-4'})
RETURN n, r, m
LIMIT 300;
```
**Purpose**: Visual cluster topology for small namespaces.
**Use Case**: Architecture visualization, Neo4j Browser exploration.

### 8.2 Service Mesh Visualization
```cypher
// Visualize service-to-service communication
MATCH path = (svc1:Resource {client_id: 'af-4', kind: 'Service'})
             -[:ROUTES_TO*1..3]->
             (svc2:Resource {kind: 'Service'})
WHERE svc1.namespace = 'production'
RETURN path
LIMIT 100;
```
**Purpose**: Visualize microservices architecture.
**Use Case**: Service dependency mapping, communication patterns.

### 8.3 Failed Resource Subgraph
```cypher
// Visualize only failed resources and their connections
MATCH (failed:Resource {client_id: 'af-4'})
WHERE failed.status =~ '(?i).*(failed|error|crashloop).*'
MATCH path = (failed)-[*0..2]-(related:Resource {client_id: 'af-4'})
RETURN path
LIMIT 200;
```
**Purpose**: Focus visualization on problematic areas.
**Use Case**: Incident investigation, failure pattern recognition.

### 8.4 Deployment Hierarchy
```cypher
// Visualize Deployment -> ReplicaSet -> Pod hierarchy
MATCH path = (deploy:Resource {client_id: 'af-4', kind: 'Deployment', name: 'api-server'})
             -[:OWNS]->
             (rs:Resource {kind: 'ReplicaSet'})
             -[:OWNS]->
             (pod:Resource {kind: 'Pod'})
RETURN path;
```
**Purpose**: Understand deployment structure and rollout status.
**Use Case**: Deployment debugging, rollout verification.

---

## 9. Multi-Cluster Analysis

### 9.1 Cross-Cluster Resource Comparison
```cypher
// Compare resource counts across clusters
MATCH (n:Resource)
WHERE n.client_id IN ['af-4', 'af-5', 'af-6']
RETURN n.client_id AS Cluster,
       n.kind AS ResourceType,
       count(n) AS Count
ORDER BY n.client_id, Count DESC;
```
**Purpose**: Compare cluster configurations.
**Use Case**: Multi-cluster consistency checks, capacity planning.

### 9.2 Cross-Cluster Alert Comparison
```cypher
// Compare alert patterns across clusters
MATCH (a:Alert)
WHERE a.client_id IN ['af-4', 'af-5']
  AND a.created_at > datetime() - duration({hours: 24})
RETURN a.client_id AS Cluster,
       a.alert_name AS Alert,
       a.status AS Status,
       count(*) AS FireCount
ORDER BY Cluster, FireCount DESC;
```
**Purpose**: Identify common issues across clusters.
**Use Case**: Multi-cluster monitoring, pattern detection.

### 9.3 Cluster Health Summary
```cypher
// Quick health check for all managed clusters
MATCH (n:Resource)
WHERE n.client_id IN ['af-4', 'af-5', 'af-6']
WITH n.client_id AS Cluster,
     count(CASE WHEN n.status =~ '(?i).*(running|ready|active|bound).*' THEN 1 END) AS Healthy,
     count(CASE WHEN n.status =~ '(?i).*(failed|error|pending|crash).*' THEN 1 END) AS Unhealthy,
     count(n) AS Total
RETURN Cluster,
       Healthy,
       Unhealthy,
       Total,
       round(100.0 * Healthy / Total, 2) AS HealthPercentage
ORDER BY HealthPercentage ASC;
```
**Purpose**: Multi-cluster health dashboard.
**Use Case**: Fleet monitoring, SLA compliance.

---

## 10. Advanced Pattern Detection

### 10.1 Detect Circular Dependencies
```cypher
// Find circular dependencies (potential deadlocks)
MATCH path = (a:Resource {client_id: 'af-4'})-[:DEPENDS_ON*2..5]->(a)
RETURN DISTINCT [n IN nodes(path) | {kind: n.kind, name: n.name}] AS CircularDependency,
       length(path) AS CycleLength
ORDER BY CycleLength
LIMIT 10;
```
**Purpose**: Identify architectural issues.
**Use Case**: Dependency review, architecture validation.

### 10.2 Cascade Failure Simulation
```cypher
// Simulate what would fail if a node goes down
MATCH (node:Resource {client_id: 'af-4', kind: 'Node', name: 'worker-node-1'})
MATCH (pod:Resource {kind: 'Pod'})-[:RUNS_ON]->(node)
MATCH (svc:Resource {kind: 'Service'})-[:ROUTES_TO]->(pod)
OPTIONAL MATCH (ing:Resource {kind: 'Ingress'})-[:ROUTES_TO]->(svc)
RETURN node.name AS FailedNode,
       collect(DISTINCT pod.name) AS AffectedPods,
       collect(DISTINCT svc.name) AS AffectedServices,
       collect(DISTINCT ing.name) AS AffectedIngresses;
```
**Purpose**: Chaos engineering, disaster recovery planning.
**Use Case**: HA validation, node maintenance planning.

### 10.3 Resource Churn Analysis
```cypher
// Find resources that are frequently created and deleted
MATCH (n:Resource {client_id: 'af-4'})
WHERE n.created_at > datetime() - duration({hours: 24})
WITH n.kind AS ResourceType,
     n.namespace AS Namespace,
     count(*) AS CreationCount
WHERE CreationCount > 10
RETURN ResourceType,
       Namespace,
       CreationCount
ORDER BY CreationCount DESC;
```
**Purpose**: Identify churning resources (autoscaling, jobs).
**Use Case**: Cost optimization, behavior analysis.

### 10.4 Security: Find Privileged Workloads
```cypher
// Find pods running with privileged security context
MATCH (pod:Resource {client_id: 'af-4', kind: 'Pod'})
WHERE pod.security_context.privileged = true
   OR pod.security_context.runAsUser = 0
RETURN pod.name AS Pod,
       pod.namespace AS Namespace,
       pod.security_context AS SecurityContext,
       pod.created_at AS CreatedAt
ORDER BY pod.created_at DESC;
```
**Purpose**: Security audit for privileged workloads.
**Use Case**: Security compliance, vulnerability assessment.

---

## Quick Reference: Common Patterns

### Filter by Client ID
Always include `{client_id: 'af-4'}` to isolate cluster data:
```cypher
MATCH (n:Resource {client_id: 'af-4'})
```

### Time-Based Filtering
```cypher
WHERE n.created_at > datetime() - duration({hours: 1})
WHERE n.timestamp > datetime('2025-10-23T12:00:00Z')
```

### Status Matching (Case-Insensitive)
```cypher
WHERE n.status =~ '(?i).*(running|ready|active).*'
WHERE n.status =~ '(?i).*(failed|error|crashloop).*'
```

### Relationship Traversal
```cypher
// Direct relationship
MATCH (a)-[:OWNS]->(b)

// Variable depth
MATCH (a)-[:DEPENDS_ON*1..3]->(b)

// Any relationship
MATCH (a)-[*1..2]-(b)
```

### Aggregations
```cypher
// Count
WITH count(n) AS total

// Collect into list
WITH collect(n.name) AS names

// Distinct
WITH collect(DISTINCT n.kind) AS types
```

---

## Performance Tips

1. **Always use client_id filter** - Prevents scanning entire graph
2. **Use LIMIT** - Especially for visualization queries
3. **Index lookups** - Use properties in WHERE clauses that are indexed
4. **Avoid Cartesian products** - Always connect patterns with relationships
5. **Use EXPLAIN/PROFILE** - Understand query execution plans

Example:
```cypher
EXPLAIN
MATCH (n:Resource {client_id: 'af-4', kind: 'Pod'})
RETURN count(n);
```

---

## Next Steps

1. **Create Custom Dashboards**: Export query results to Grafana/Kibana
2. **Alerting Integration**: Use queries to trigger custom alerts
3. **Automation**: Schedule recurring queries via cron jobs
4. **Custom Extensions**: Write stored procedures for complex analysis
5. **Data Export**: Use `CALL apoc.export.json.query()` for bulk exports

---

## Resources

- Neo4j Browser: http://98.90.147.12:7474
- Neo4j Credentials: `neo4j / Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA`
- Cypher Manual: https://neo4j.com/docs/cypher-manual/
- APOC Documentation: https://neo4j.com/labs/apoc/

---

**Document Version**: 1.0.0
**Last Updated**: 2025-10-23
**Cluster Version**: v2.0.0 (Control Plane Architecture)
