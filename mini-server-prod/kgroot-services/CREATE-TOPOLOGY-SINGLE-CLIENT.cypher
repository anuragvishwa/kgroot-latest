// ============================================================================
// CREATE TOPOLOGY FOR SINGLE CLIENT (SIMPLER VERSION)
// ============================================================================
// Use this script to create topology for ONE client at a time
// Safer and easier to debug than the batch version
// ============================================================================

// ============================================================================
// CONFIGURATION: Set your client_id here
// ============================================================================
// In Neo4j Browser, run this first:
// :param client_id => 'ab-01'

// ============================================================================
// STEP 1: Create Service -> Pod SELECTS relationships (by selector)
// ============================================================================

MATCH (svc:Resource {kind: 'Service', client_id: $client_id})
MATCH (pod:Resource {kind: 'Pod', client_id: $client_id})
WHERE pod.ns = svc.ns
  AND pod.labels IS NOT NULL
  AND svc.selector IS NOT NULL
  AND pod.labels CONTAINS svc.selector

MERGE (svc)-[r:SELECTS]->(pod)
ON CREATE SET
  r.client_id = $client_id,
  r.created_at = datetime(),
  r.created_by = 'topology_builder'
ON MATCH SET
  r.updated_at = datetime()

RETURN count(*) as selects_by_selector;


// ============================================================================
// STEP 2: Create Service -> Pod SELECTS relationships (by naming)
// ============================================================================

MATCH (svc:Resource {kind: 'Service', client_id: $client_id})
MATCH (pod:Resource {kind: 'Pod', client_id: $client_id})
WHERE pod.ns = svc.ns
  AND svc.selector IS NULL
  AND pod.name CONTAINS svc.name

MERGE (svc)-[r:SELECTS]->(pod)
ON CREATE SET
  r.client_id = $client_id,
  r.created_at = datetime(),
  r.created_by = 'topology_builder'
ON MATCH SET
  r.updated_at = datetime()

RETURN count(*) as selects_by_naming;


// ============================================================================
// STEP 3: Create Pod -> Node RUNS_ON relationships
// ============================================================================

MATCH (pod:Resource {kind: 'Pod', client_id: $client_id})
WHERE pod.node IS NOT NULL

WITH pod, pod.node as node_name

MERGE (node:Resource {
  client_id: $client_id,
  kind: 'Node',
  name: node_name
})
ON CREATE SET
  node.created_at = datetime(),
  node.ns = 'cluster'

MERGE (pod)-[r:RUNS_ON]->(node)
ON CREATE SET
  r.client_id = $client_id,
  r.created_at = datetime(),
  r.created_by = 'topology_builder'
ON MATCH SET
  r.updated_at = datetime()

RETURN count(*) as runs_on_created;


// ============================================================================
// STEP 4: Create Deployment -> ReplicaSet CONTROLS relationships
// ============================================================================

MATCH (deploy:Resource {kind: 'Deployment', client_id: $client_id})
MATCH (rs:Resource {kind: 'ReplicaSet', client_id: $client_id})
WHERE rs.ns = deploy.ns
  AND (rs.name STARTS WITH deploy.name OR rs.labels CONTAINS deploy.name)

MERGE (deploy)-[r:CONTROLS]->(rs)
ON CREATE SET
  r.client_id = $client_id,
  r.created_at = datetime(),
  r.created_by = 'topology_builder'
ON MATCH SET
  r.updated_at = datetime()

RETURN count(*) as deploy_to_rs_created;


// ============================================================================
// STEP 5: Create ReplicaSet -> Pod CONTROLS relationships
// ============================================================================

MATCH (rs:Resource {kind: 'ReplicaSet', client_id: $client_id})
MATCH (pod:Resource {kind: 'Pod', client_id: $client_id})
WHERE pod.ns = rs.ns
  AND (pod.name CONTAINS rs.name
       OR (pod.labels IS NOT NULL AND rs.labels IS NOT NULL AND pod.labels CONTAINS rs.labels))

MERGE (rs)-[r:CONTROLS]->(pod)
ON CREATE SET
  r.client_id = $client_id,
  r.created_at = datetime(),
  r.created_by = 'topology_builder'
ON MATCH SET
  r.updated_at = datetime()

RETURN count(*) as rs_to_pod_created;


// ============================================================================
// STEP 6: Create DaemonSet -> Pod CONTROLS relationships
// ============================================================================

MATCH (ds:Resource {kind: 'DaemonSet', client_id: $client_id})
MATCH (pod:Resource {kind: 'Pod', client_id: $client_id})
WHERE pod.ns = ds.ns
  AND (pod.name CONTAINS ds.name
       OR (pod.labels IS NOT NULL AND ds.labels IS NOT NULL AND pod.labels CONTAINS ds.labels))

MERGE (ds)-[r:CONTROLS]->(pod)
ON CREATE SET
  r.client_id = $client_id,
  r.created_at = datetime(),
  r.created_by = 'topology_builder'
ON MATCH SET
  r.updated_at = datetime()

RETURN count(*) as ds_to_pod_created;


// ============================================================================
// VERIFICATION QUERIES (Run these after creating topology)
// ============================================================================

// Query 1: Count topology relationships by type
MATCH (r1:Resource {client_id: $client_id})-[rel]->(r2:Resource {client_id: $client_id})
WHERE type(rel) IN ['SELECTS', 'RUNS_ON', 'CONTROLS']
  AND rel.client_id = $client_id
RETURN
  type(rel) as relationship_type,
  count(*) as total_count
ORDER BY total_count DESC;


// Query 2: Show topology distribution by resource types
MATCH (r1:Resource {client_id: $client_id})-[rel]->(r2:Resource {client_id: $client_id})
WHERE type(rel) IN ['SELECTS', 'RUNS_ON', 'CONTROLS']
  AND rel.client_id = $client_id
RETURN
  r1.kind as source_type,
  type(rel) as relationship,
  r2.kind as target_type,
  count(*) as count
ORDER BY count DESC;


// Query 3: Sample topology for one service
MATCH (svc:Resource {kind: 'Service', client_id: $client_id})
WITH svc LIMIT 1

OPTIONAL MATCH (svc)-[r1:SELECTS {client_id: $client_id}]->(pod:Resource {client_id: $client_id})
OPTIONAL MATCH (pod)-[r2:RUNS_ON {client_id: $client_id}]->(node:Resource {client_id: $client_id})

RETURN
  svc.name as service_name,
  svc.ns as namespace,
  count(DISTINCT pod) as pods_selected,
  count(DISTINCT node) as nodes_used,
  collect(DISTINCT pod.name)[0..5] as sample_pods,
  collect(DISTINCT node.name) as nodes;


// Query 4: Verify multi-hop paths exist
MATCH path = (r1:Resource {client_id: $client_id})-[*1..3]-(r2:Resource {client_id: $client_id})
WHERE r1 <> r2
  AND ALL(rel IN relationships(path) WHERE type(rel) IN ['SELECTS', 'RUNS_ON', 'CONTROLS'])
  AND ALL(rel IN relationships(path) WHERE rel.client_id = $client_id)

RETURN
  length(path) as hops,
  count(DISTINCT path) as path_count
ORDER BY hops;


// Query 5: Topology coverage for pods
MATCH (pod:Resource {kind: 'Pod', client_id: $client_id})
OPTIONAL MATCH (pod)-[rel:SELECTS|RUNS_ON|CONTROLS {client_id: $client_id}]-()

WITH pod, count(rel) as topology_rels
RETURN
  count(CASE WHEN topology_rels > 0 THEN 1 END) as pods_with_topology,
  count(CASE WHEN topology_rels = 0 THEN 1 END) as pods_without_topology,
  count(*) as total_pods,
  round(toFloat(count(CASE WHEN topology_rels > 0 THEN 1 END)) / count(*) * 100) as coverage_percentage;


// Query 6: CRITICAL - Check for cross-tenant violations
MATCH (r1:Resource)-[rel:SELECTS|RUNS_ON|CONTROLS]->(r2:Resource)
WHERE (r1.client_id = $client_id OR r2.client_id = $client_id OR rel.client_id = $client_id)
  AND (
    r1.client_id <> r2.client_id
    OR r1.client_id <> rel.client_id
    OR r2.client_id <> rel.client_id
  )
RETURN
  count(*) as cross_tenant_violations,
  'MUST be 0!' as warning,
  collect({
    from_client: r1.client_id,
    to_client: r2.client_id,
    rel_client: rel.client_id,
    from: r1.kind + ':' + r1.name,
    to: r2.kind + ':' + r2.name
  })[0..5] as sample_violations;


// ============================================================================
// USAGE INSTRUCTIONS
// ============================================================================
// 1. Set parameter: :param client_id => 'ab-01'
// 2. Run Steps 1-6 (one at a time or all together)
// 3. Run verification queries 1-6
// 4. Verify Query 6 returns cross_tenant_violations = 0
// 5. Repeat for other clients by changing the parameter
// ============================================================================
