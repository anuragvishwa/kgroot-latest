// ============================================
// Topology Analysis
// ============================================

// 1. Resource hierarchy in test namespace
MATCH (r:Resource)
WHERE r.ns = 'kg-testing'
OPTIONAL MATCH (r)-[rel:CONTROLS|RUNS_ON|SELECTS]-(related:Resource)
RETURN
  r.name as resource,
  labels(r) as type,
  type(rel) as relationship,
  related.name as related_resource,
  labels(related) as related_type
ORDER BY resource;

// 2. Deployment → ReplicaSet → Pod hierarchy
MATCH path = (d:Deployment)-[:CONTROLS*1..2]->(p:Pod)
WHERE d.ns = 'kg-testing'
RETURN
  d.name as deployment,
  [node in nodes(path) | labels(node)[0] + ':' + node.name] as hierarchy,
  length(path) as depth
ORDER BY deployment;

// 3. Pods and their parent controllers
MATCH (p:Pod)<-[:CONTROLS]-(parent)
WHERE p.ns = 'kg-testing'
RETURN
  p.name as pod,
  labels(parent) as parent_type,
  parent.name as parent_name
ORDER BY parent_name, pod;

// 4. Services and their selected pods
MATCH (s:Service)-[:SELECTS]->(p:Pod)
WHERE s.ns = 'kg-testing'
RETURN
  s.name as service,
  collect(p.name) as pods,
  count(p) as pod_count
ORDER BY service;

// 5. Events per resource type
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.ns = 'kg-testing'
RETURN
  labels(r) as resource_type,
  e.severity as severity,
  count(*) as event_count
ORDER BY resource_type, severity;
