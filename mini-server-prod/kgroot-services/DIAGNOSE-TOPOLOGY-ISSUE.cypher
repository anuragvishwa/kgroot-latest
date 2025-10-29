// ============================================================================
// DIAGNOSE WHY TOPOLOGY ISN'T BEING USED IN CAUSAL RELATIONSHIPS
// ============================================================================
:param client_id => 'ab-01'

// ============================================================================
// TEST 1: Check if topology relationships have client_id
// ============================================================================

MATCH ()-[r:SELECTS|RUNS_ON|CONTROLS]->()
RETURN
  type(r) as rel_type,
  count(CASE WHEN r.client_id IS NOT NULL THEN 1 END) as with_client_id,
  count(CASE WHEN r.client_id IS NULL THEN 1 END) as without_client_id,
  count(*) as total
ORDER BY rel_type;

// EXPECTED: All should have client_id
// If without_client_id > 0, that's the problem!


// ============================================================================
// TEST 2: Check if Resources linked by ABOUT have topology
// ============================================================================

MATCH (e1:Episodic {client_id: $client_id})-[:ABOUT]->(r1:Resource)
MATCH (e2:Episodic {client_id: $client_id})-[:ABOUT]->(r2:Resource)
WHERE e1 <> e2
  AND e1.event_time > datetime() - duration({hours: 24})
  AND e2.event_time > e1.event_time
  AND e2.event_time < e1.event_time + duration({minutes: 10})

OPTIONAL MATCH topology_path = (r1)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r2)

RETURN
  count(*) as total_event_pairs_checked,
  count(topology_path) as pairs_with_topology,
  count(CASE WHEN topology_path IS NULL THEN 1 END) as pairs_without_topology,
  round(toFloat(count(topology_path)) / count(*) * 100) as topology_coverage_pct
LIMIT 1;

// This shows what % of event pairs have topology connections


// ============================================================================
// TEST 3: Sample events that should have topology but don't
// ============================================================================

MATCH (e1:Episodic {client_id: $client_id})-[:ABOUT]->(r1:Resource)
MATCH (e2:Episodic {client_id: $client_id})-[:ABOUT]->(r2:Resource)
WHERE e1 <> e2
  AND e1.event_time > datetime() - duration({hours: 24})
  AND e2.event_time > e1.event_time
  AND e2.event_time < e1.event_time + duration({minutes: 10})
  AND r1.ns = r2.ns  // Same namespace, should have topology

OPTIONAL MATCH topology_path = (r1)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r2)

WITH r1, r2, topology_path
WHERE topology_path IS NULL

RETURN
  r1.kind as r1_kind,
  r1.name as r1_name,
  r2.kind as r2_kind,
  r2.name as r2_name,
  r1.ns as namespace
LIMIT 10;

// Shows specific resource pairs that lack topology


// ============================================================================
// TEST 4: Check if ABOUT relationships exist
// ============================================================================

MATCH (e:Episodic {client_id: $client_id})
WHERE e.event_time > datetime() - duration({hours: 24})

OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource)

RETURN
  count(e) as total_events,
  count(r) as events_with_resource,
  count(CASE WHEN r IS NULL THEN 1 END) as events_without_resource,
  round(toFloat(count(r)) / count(e) * 100) as coverage_pct;

// If events_without_resource is high, that's the issue!


// ============================================================================
// TEST 5: Check topology path filtering with client_id
// ============================================================================

// This simulates what the causal script does
MATCH (e1:Episodic {client_id: $client_id})-[:ABOUT]->(r1:Resource {client_id: $client_id})
MATCH (e2:Episodic {client_id: $client_id})-[:ABOUT]->(r2:Resource {client_id: $client_id})
WHERE e1 <> e2
  AND e1.event_time > datetime() - duration({hours: 24})
  AND e2.event_time > e1.event_time
  AND e2.event_time < e1.event_time + duration({minutes: 10})

OPTIONAL MATCH topology_path = (r1)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r2)
WHERE ALL(rel IN relationships(topology_path) WHERE rel.client_id = $client_id)

RETURN
  count(*) as total_pairs,
  count(topology_path) as pairs_with_topology_after_filter,
  count(CASE WHEN topology_path IS NULL THEN 1 END) as pairs_without_topology
LIMIT 1;

// Compare this to TEST 2 - if much lower, the WHERE clause is filtering out valid paths


// ============================================================================
// TEST 6: Are topology relationships missing client_id?
// ============================================================================

MATCH (r1:Resource {client_id: $client_id})-[rel:SELECTS|RUNS_ON|CONTROLS]->(r2:Resource {client_id: $client_id})
RETURN
  type(rel) as rel_type,
  count(*) as total,
  count(CASE WHEN rel.client_id = $client_id THEN 1 END) as matching_client_id,
  count(CASE WHEN rel.client_id IS NULL THEN 1 END) as null_client_id,
  count(CASE WHEN rel.client_id IS NOT NULL AND rel.client_id <> $client_id THEN 1 END) as wrong_client_id
ORDER BY rel_type;

// Shows if relationships have correct client_id


// ============================================================================
// TEST 7: Sample a working topology path
// ============================================================================

MATCH (r1:Resource {client_id: $client_id})-[rel:SELECTS|RUNS_ON|CONTROLS]->(r2:Resource {client_id: $client_id})
WHERE rel.client_id = $client_id
WITH r1, r2, rel
LIMIT 1

RETURN
  r1.kind as from_kind,
  r1.name as from_name,
  type(rel) as relationship,
  r2.kind as to_kind,
  r2.name as to_name,
  rel.client_id as rel_client_id;

// Shows a concrete example of what topology looks like


// ============================================================================
// INTERPRETATION GUIDE
// ============================================================================
// Based on results, the issue is likely one of these:
//
// 1. TEST 1 shows without_client_id > 0
//    → Fix: Run topology script again, relationships missing client_id
//
// 2. TEST 4 shows high events_without_resource
//    → Fix: Events aren't linked to Resources via ABOUT
//    → This means topology can't help even if it exists
//
// 3. TEST 5 shows much lower than TEST 2
//    → Fix: The WHERE clause filtering is too strict
//    → Topology exists but filtered out by client_id check
//
// 4. TEST 6 shows null_client_id or wrong_client_id
//    → Fix: Re-run topology creation with proper client_id
//
// 5. TEST 2/5 show 0 pairs_with_topology
//    → Fix: Resources in events don't match Resources in topology
//    → Check if resource names/IDs are consistent
// ============================================================================
