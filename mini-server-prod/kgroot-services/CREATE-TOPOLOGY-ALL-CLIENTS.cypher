// ============================================================================
// CREATE TOPOLOGY FOR ALL CLIENTS (MULTI-TENANT BATCH)
// ============================================================================
// This script runs topology creation for ALL clients in the database
// Each client's topology is completely isolated
// ============================================================================

// ============================================================================
// STEP 1: Get all unique client_ids and process each
// ============================================================================

MATCH (r:Resource)
WHERE r.client_id IS NOT NULL
WITH DISTINCT r.client_id as client_id
ORDER BY client_id

// ============================================================================
// STEP 2: For each client, create Service -> Pod SELECTS relationships
// ============================================================================

WITH collect(client_id) as all_clients
UNWIND all_clients as cid

// Create SELECTS by selector
CALL {
  WITH cid
  MATCH (svc:Resource {kind: 'Service', client_id: cid})
  MATCH (pod:Resource {kind: 'Pod', client_id: cid})
  WHERE pod.ns = svc.ns
    AND pod.labels IS NOT NULL
    AND svc.selector IS NOT NULL
    AND pod.labels CONTAINS svc.selector

  MERGE (svc)-[r:SELECTS]->(pod)
  ON CREATE SET
    r.client_id = cid,
    r.created_at = datetime(),
    r.created_by = 'topology_builder_batch'
  ON MATCH SET
    r.updated_at = datetime()

  RETURN count(*) as selects_by_selector
}

// Create SELECTS by naming convention
CALL {
  WITH cid
  MATCH (svc:Resource {kind: 'Service', client_id: cid})
  MATCH (pod:Resource {kind: 'Pod', client_id: cid})
  WHERE pod.ns = svc.ns
    AND svc.selector IS NULL
    AND pod.name CONTAINS svc.name

  MERGE (svc)-[r:SELECTS]->(pod)
  ON CREATE SET
    r.client_id = cid,
    r.created_at = datetime(),
    r.created_by = 'topology_builder_batch'
  ON MATCH SET
    r.updated_at = datetime()

  RETURN count(*) as selects_by_naming
}

// Create RUNS_ON relationships
CALL {
  WITH cid
  MATCH (pod:Resource {kind: 'Pod', client_id: cid})
  WHERE pod.node IS NOT NULL

  WITH pod, pod.node as node_name, pod.client_id as client_id

  MERGE (node:Resource {
    client_id: client_id,
    kind: 'Node',
    name: node_name
  })
  ON CREATE SET
    node.created_at = datetime(),
    node.ns = 'cluster'

  MERGE (pod)-[r:RUNS_ON]->(node)
  ON CREATE SET
    r.client_id = client_id,
    r.created_at = datetime(),
    r.created_by = 'topology_builder_batch'
  ON MATCH SET
    r.updated_at = datetime()

  RETURN count(*) as runs_on_created
}

// Create Deployment -> ReplicaSet CONTROLS
CALL {
  WITH cid
  MATCH (deploy:Resource {kind: 'Deployment', client_id: cid})
  MATCH (rs:Resource {kind: 'ReplicaSet', client_id: cid})
  WHERE rs.ns = deploy.ns
    AND (rs.name STARTS WITH deploy.name OR rs.labels CONTAINS deploy.name)

  MERGE (deploy)-[r:CONTROLS]->(rs)
  ON CREATE SET
    r.client_id = cid,
    r.created_at = datetime(),
    r.created_by = 'topology_builder_batch'
  ON MATCH SET
    r.updated_at = datetime()

  RETURN count(*) as deploy_to_rs
}

// Create ReplicaSet -> Pod CONTROLS
CALL {
  WITH cid
  MATCH (rs:Resource {kind: 'ReplicaSet', client_id: cid})
  MATCH (pod:Resource {kind: 'Pod', client_id: cid})
  WHERE pod.ns = rs.ns
    AND (pod.name CONTAINS rs.name
         OR (pod.labels IS NOT NULL AND rs.labels IS NOT NULL AND pod.labels CONTAINS rs.labels))

  MERGE (rs)-[r:CONTROLS]->(pod)
  ON CREATE SET
    r.client_id = cid,
    r.created_at = datetime(),
    r.created_by = 'topology_builder_batch'
  ON MATCH SET
    r.updated_at = datetime()

  RETURN count(*) as rs_to_pod
}

// Create DaemonSet -> Pod CONTROLS
CALL {
  WITH cid
  MATCH (ds:Resource {kind: 'DaemonSet', client_id: cid})
  MATCH (pod:Resource {kind: 'Pod', client_id: cid})
  WHERE pod.ns = ds.ns
    AND (pod.name CONTAINS ds.name
         OR (pod.labels IS NOT NULL AND ds.labels IS NOT NULL AND pod.labels CONTAINS ds.labels))

  MERGE (ds)-[r:CONTROLS]->(pod)
  ON CREATE SET
    r.client_id = cid,
    r.created_at = datetime(),
    r.created_by = 'topology_builder_batch'
  ON MATCH SET
    r.updated_at = datetime()

  RETURN count(*) as ds_to_pod
}

RETURN
  cid as client_id,
  selects_by_selector,
  selects_by_naming,
  runs_on_created,
  deploy_to_rs,
  rs_to_pod,
  ds_to_pod,
  (selects_by_selector + selects_by_naming + runs_on_created +
   deploy_to_rs + rs_to_pod + ds_to_pod) as total_relationships_created
ORDER BY client_id;


// ============================================================================
// Verify results per client
// ============================================================================

MATCH (r:Resource)
WITH DISTINCT r.client_id as client_id
WHERE client_id IS NOT NULL

CALL {
  WITH client_id
  MATCH (r1:Resource {client_id: client_id})-[rel]->(r2:Resource {client_id: client_id})
  WHERE type(rel) IN ['SELECTS', 'RUNS_ON', 'CONTROLS']
    AND rel.client_id = client_id
  RETURN
    client_id,
    count(CASE WHEN type(rel) = 'SELECTS' THEN 1 END) as selects_count,
    count(CASE WHEN type(rel) = 'RUNS_ON' THEN 1 END) as runs_on_count,
    count(CASE WHEN type(rel) = 'CONTROLS' THEN 1 END) as controls_count,
    count(rel) as total_topology_rels
}

RETURN
  client_id,
  selects_count,
  runs_on_count,
  controls_count,
  total_topology_rels
ORDER BY client_id;


// ============================================================================
// CRITICAL: Verify NO cross-tenant contamination
// ============================================================================

MATCH (r1:Resource)-[rel:SELECTS|RUNS_ON|CONTROLS]->(r2:Resource)
WHERE r1.client_id <> r2.client_id
   OR r1.client_id <> rel.client_id
   OR r2.client_id <> rel.client_id
RETURN
  count(*) as cross_tenant_violations,
  'CRITICAL: This MUST be 0 for proper isolation!' as warning,
  collect({
    from_client: r1.client_id,
    to_client: r2.client_id,
    rel_client: rel.client_id,
    from: r1.kind + ':' + r1.name,
    to: r2.kind + ':' + r2.name
  })[0..10] as sample_violations;
