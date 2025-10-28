// ============================================================================
// CREATE SERVICE TOPOLOGY RELATIONSHIPS
// ============================================================================
// This script creates SELECTS and RUNS_ON relationships between Resources
// These are needed for cross-service causality detection in enhanced RCA
// ============================================================================

// ============================================================================
// STEP 1: Create Service -> Pod SELECTS relationships
// ============================================================================

// Match services with pods based on namespace and label matching
MATCH (svc:Resource {client_id: 'ab-01', kind: 'Service'})
MATCH (pod:Resource {client_id: 'ab-01', kind: 'Pod'})
WHERE pod.ns = svc.ns
  AND pod.labels IS NOT NULL
  AND svc.selector IS NOT NULL
  AND pod.labels CONTAINS svc.selector

MERGE (svc)-[:SELECTS]->(pod)
RETURN count(*) as selects_created_by_selector;


// Fallback: Match by naming convention (pod name contains service name)
MATCH (svc:Resource {client_id: 'ab-01', kind: 'Service'})
MATCH (pod:Resource {client_id: 'ab-01', kind: 'Pod'})
WHERE pod.ns = svc.ns
  AND svc.selector IS NULL  // Only for services without explicit selectors
  AND pod.name CONTAINS svc.name

MERGE (svc)-[:SELECTS]->(pod)
RETURN count(*) as selects_created_by_naming;


// ============================================================================
// STEP 2: Create Pod -> Node RUNS_ON relationships
// ============================================================================

// Match pods with their host nodes
MATCH (pod:Resource {client_id: 'ab-01', kind: 'Pod'})
WHERE pod.node IS NOT NULL

WITH pod, pod.node as node_name

// Create Node resource if it doesn't exist
MERGE (node:Resource {
  client_id: 'ab-01',
  kind: 'Node',
  name: node_name
})
ON CREATE SET
  node.created_at = datetime(),
  node.ns = 'cluster'

MERGE (pod)-[:RUNS_ON]->(node)
RETURN count(*) as runs_on_created;


// ============================================================================
// STEP 3: Create Deployment -> ReplicaSet CONTROLS relationships
// ============================================================================

// Match deployments with their replica sets
MATCH (deploy:Resource {client_id: 'ab-01', kind: 'Deployment'})
MATCH (rs:Resource {client_id: 'ab-01', kind: 'ReplicaSet'})
WHERE rs.ns = deploy.ns
  AND (
    rs.name STARTS WITH deploy.name
    OR rs.labels CONTAINS deploy.name
  )

MERGE (deploy)-[:CONTROLS]->(rs)
RETURN count(*) as deploy_to_rs_created;


// ============================================================================
// STEP 4: Create ReplicaSet -> Pod CONTROLS relationships
// ============================================================================

// Match replica sets with their pods
MATCH (rs:Resource {client_id: 'ab-01', kind: 'ReplicaSet'})
MATCH (pod:Resource {client_id: 'ab-01', kind: 'Pod'})
WHERE pod.ns = rs.ns
  AND (
    pod.name CONTAINS rs.name
    OR (pod.labels IS NOT NULL AND rs.labels IS NOT NULL AND pod.labels CONTAINS rs.labels)
  )

MERGE (rs)-[:CONTROLS]->(pod)
RETURN count(*) as rs_to_pod_created;


// ============================================================================
// STEP 5: Create DaemonSet -> Pod CONTROLS relationships
// ============================================================================

// Match daemon sets with their pods
MATCH (ds:Resource {client_id: 'ab-01', kind: 'DaemonSet'})
MATCH (pod:Resource {client_id: 'ab-01', kind: 'Pod'})
WHERE pod.ns = ds.ns
  AND (
    pod.name CONTAINS ds.name
    OR (pod.labels IS NOT NULL AND ds.labels IS NOT NULL AND pod.labels CONTAINS ds.labels)
  )

MERGE (ds)-[:CONTROLS]->(pod)
RETURN count(*) as ds_to_pod_created;


// ============================================================================
// STEP 6: Verify what was created
// ============================================================================

// Count all topology relationships by type
MATCH ()-[r]-()
WHERE type(r) IN ['SELECTS', 'RUNS_ON', 'CONTROLS']
RETURN
  type(r) as relationship_type,
  count(r) as total_count
ORDER BY total_count DESC;


// Show relationship distribution by resource types
MATCH (r1:Resource)-[rel]->(r2:Resource)
WHERE type(rel) IN ['SELECTS', 'RUNS_ON', 'CONTROLS']
RETURN
  r1.kind as source_type,
  type(rel) as relationship,
  r2.kind as target_type,
  count(*) as count
ORDER BY count DESC;


// ============================================================================
// STEP 7: Sample verification - Show topology for one service
// ============================================================================

// Pick a service and show its full topology
MATCH (svc:Resource {client_id: 'ab-01', kind: 'Service'})
WITH svc LIMIT 1

OPTIONAL MATCH (svc)-[:SELECTS]->(pod:Resource)
OPTIONAL MATCH (pod)-[:RUNS_ON]->(node:Resource)
OPTIONAL MATCH (deploy:Resource)-[:CONTROLS]->(:Resource)-[:CONTROLS]->(pod)

RETURN
  svc.name as service_name,
  svc.ns as namespace,
  count(DISTINCT pod) as pods_selected,
  count(DISTINCT node) as nodes_used,
  collect(DISTINCT pod.name)[0..5] as sample_pods,
  collect(DISTINCT node.name) as nodes;


// ============================================================================
// STEP 8: Verify cross-service paths exist
// ============================================================================

// Find multi-hop topology paths (this enables cross-service causality)
MATCH path = (r1:Resource)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r2:Resource)
WHERE r1.client_id = 'ab-01'
  AND r2.client_id = 'ab-01'
  AND r1 <> r2

RETURN
  length(path) as hops,
  count(DISTINCT path) as path_count
ORDER BY hops;


// ============================================================================
// STEP 9: Check topology coverage
// ============================================================================

// How many pods have topology relationships?
MATCH (pod:Resource {client_id: 'ab-01', kind: 'Pod'})
OPTIONAL MATCH (pod)-[rel:SELECTS|RUNS_ON|CONTROLS]-()

WITH pod, count(rel) as topology_rels
RETURN
  count(CASE WHEN topology_rels > 0 THEN 1 END) as pods_with_topology,
  count(CASE WHEN topology_rels = 0 THEN 1 END) as pods_without_topology,
  count(*) as total_pods,
  toFloat(count(CASE WHEN topology_rels > 0 THEN 1 END)) / count(*) as coverage_percentage;


// ============================================================================
// SUCCESS CRITERIA
// ============================================================================
// After running this script, you should have:
// 1. SELECTS relationships: Service -> Pod (expect 50-200 depending on services)
// 2. RUNS_ON relationships: Pod -> Node (expect ~241, one per pod)
// 3. CONTROLS relationships: Deployment/RS/DS -> Pod (expect 200-400)
// 4. Multi-hop paths for cross-service causality detection
// 5. >80% topology coverage for pods
// ============================================================================
