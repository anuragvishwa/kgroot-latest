# Multi-Tenant Isolation Guide for RCA System

> **Critical**: In a multi-tenant environment, proper isolation prevents data leakage between customers.

---

## Problem: Data Leakage Risk

Your Neo4j database serves multiple clients (`client_id: 'ab-01'`, `'ab-02'`, etc.). Without proper isolation:

❌ **WRONG**: Relationships without `client_id`
```cypher
// This creates cross-tenant data leakage!
MATCH (e1:Episodic)-[:POTENTIAL_CAUSE]->(e2:Episodic)
// Could match events from different clients!
```

✅ **CORRECT**: Relationships WITH `client_id`
```cypher
// Properly isolated by client_id
MATCH (e1:Episodic {client_id: 'ab-01'})-[pc:POTENTIAL_CAUSE]->(e2:Episodic {client_id: 'ab-01'})
WHERE pc.client_id = 'ab-01'
// Only matches within same tenant
```

---

## Solution: 3-Layer Isolation

### Layer 1: Node-Level Isolation
**Rule**: Every query MUST filter by `client_id` on all nodes

```cypher
// ✅ CORRECT
MATCH (e1:Episodic {client_id: $client_id})
MATCH (e2:Episodic {client_id: $client_id})

// ❌ WRONG
MATCH (e1:Episodic)  // Could match any client!
```

### Layer 2: Relationship-Level Isolation
**Rule**: Every relationship MUST have `client_id` property

```cypher
// ✅ CORRECT
MERGE (e1)-[pc:POTENTIAL_CAUSE]->(e2)
SET pc.client_id = $client_id,
    pc.confidence = 0.85

// ❌ WRONG
MERGE (e1)-[pc:POTENTIAL_CAUSE]->(e2)
SET pc.confidence = 0.85  // Missing client_id!
```

### Layer 3: Cross-Reference Validation
**Rule**: Always verify endpoints match relationship's `client_id`

```cypher
// ✅ CORRECT - Triple verification
MATCH (e1:Episodic {client_id: $client_id})-[pc:POTENTIAL_CAUSE]->(e2:Episodic {client_id: $client_id})
WHERE pc.client_id = $client_id
  AND e1.client_id = e2.client_id
  AND e1.client_id = pc.client_id

// ❌ WRONG - Only checks nodes
MATCH (e1:Episodic {client_id: $client_id})-[pc:POTENTIAL_CAUSE]->(e2:Episodic {client_id: $client_id})
// Relationship might have different client_id!
```

---

## Files Updated for Multi-Tenant Safety

### 1. CREATE-TOPOLOGY-RELATIONSHIPS.cypher
**Changes**:
- ✅ All relationships get `client_id` property
- ✅ Parameterized `$client_id` for easy per-client execution
- ✅ Triple safety checks (nodes + relationship)
- ✅ Added Step 10: Cross-tenant violation detector

**Usage** (single client):
```cypher
:param client_id => 'ab-01';
// Run the script
```

### 2. CREATE-TOPOLOGY-ALL-CLIENTS.cypher (NEW)
**Purpose**: Batch create topology for ALL clients at once

**Features**:
- ✅ Automatically finds all unique `client_id` values
- ✅ Creates topology for each client in isolation
- ✅ Verifies results per client
- ✅ Checks for cross-tenant violations

**Usage**:
```bash
cypher-shell -u neo4j -p password -f CREATE-TOPOLOGY-ALL-CLIENTS.cypher
```

### 3. Enhanced RCA Script (to be created)
Will include same multi-tenant protections for POTENTIAL_CAUSE relationships.

---

## Verification Queries

### Query 1: Check Isolation Health
```cypher
// Count relationships per client
MATCH (r1:Resource)-[rel:SELECTS|RUNS_ON|CONTROLS]->(r2:Resource)
RETURN
  rel.client_id as client_id,
  type(rel) as rel_type,
  count(*) as count
ORDER BY client_id, rel_type;
```

**Expected**: Each client has their own count, no mixing.

### Query 2: Detect Cross-Tenant Violations
```cypher
// Find ANY cross-tenant contamination
MATCH (r1)-[rel]->(r2)
WHERE r1.client_id IS NOT NULL
  AND r2.client_id IS NOT NULL
  AND (
    r1.client_id <> r2.client_id
    OR (rel.client_id IS NOT NULL AND r1.client_id <> rel.client_id)
    OR (rel.client_id IS NOT NULL AND r2.client_id <> rel.client_id)
  )
RETURN
  count(*) as violations,
  collect({
    from: r1.client_id,
    to: r2.client_id,
    rel_client: rel.client_id,
    type: type(rel)
  })[0..10] as samples;
```

**Expected**: `violations: 0` (CRITICAL!)

### Query 3: Verify Relationship Properties
```cypher
// Check if all topology relationships have client_id
MATCH ()-[rel:SELECTS|RUNS_ON|CONTROLS]->()
WHERE rel.client_id IS NULL
RETURN
  count(*) as relationships_without_client_id,
  type(rel) as rel_type
ORDER BY relationships_without_client_id DESC;
```

**Expected**: `relationships_without_client_id: 0`

### Query 4: Per-Client Topology Summary
```cypher
// Get topology stats for each client
MATCH (r:Resource)
WITH DISTINCT r.client_id as client_id

CALL {
  WITH client_id
  MATCH (r1:Resource {client_id: client_id})-[rel]->(r2:Resource {client_id: client_id})
  WHERE type(rel) IN ['SELECTS', 'RUNS_ON', 'CONTROLS']
    AND rel.client_id = client_id
  RETURN
    count(CASE WHEN type(rel) = 'SELECTS' THEN 1 END) as selects,
    count(CASE WHEN type(rel) = 'RUNS_ON' THEN 1 END) as runs_on,
    count(CASE WHEN type(rel) = 'CONTROLS' THEN 1 END) as controls
}

CALL {
  WITH client_id
  MATCH (r:Resource {client_id: client_id})
  RETURN
    count(CASE WHEN r.kind = 'Pod' THEN 1 END) as pods,
    count(CASE WHEN r.kind = 'Service' THEN 1 END) as services,
    count(CASE WHEN r.kind = 'Deployment' THEN 1 END) as deployments
}

RETURN
  client_id,
  pods,
  services,
  deployments,
  selects,
  runs_on,
  controls,
  (selects + runs_on + controls) as total_topology
ORDER BY client_id;
```

---

## Best Practices

### DO ✅

1. **Always use parameters for client_id**
   ```cypher
   :param client_id => 'ab-01';
   MATCH (e:Episodic {client_id: $client_id})
   ```

2. **Set client_id on relationship creation**
   ```cypher
   MERGE (a)-[r:REL]->(b)
   ON CREATE SET r.client_id = $client_id
   ```

3. **Verify isolation in all queries**
   ```cypher
   WHERE e1.client_id = $client_id
     AND e2.client_id = $client_id
     AND e1.client_id = e2.client_id
   ```

4. **Index client_id for performance**
   ```cypher
   CREATE INDEX episodic_client_id IF NOT EXISTS FOR (e:Episodic) ON (e.client_id);
   CREATE INDEX resource_client_id IF NOT EXISTS FOR (r:Resource) ON (r.client_id);
   ```

5. **Run cross-tenant checks after major operations**
   ```cypher
   // After bulk operations
   CALL {
     // Run violation detector
   }
   ```

### DON'T ❌

1. **Don't create relationships without client_id**
   ```cypher
   // ❌ BAD
   MERGE (a)-[r:REL]->(b)
   SET r.confidence = 0.85
   ```

2. **Don't use wildcards without client filter**
   ```cypher
   // ❌ BAD
   MATCH (e:Episodic)  // Matches ALL clients!
   ```

3. **Don't assume node filters are enough**
   ```cypher
   // ❌ BAD - relationship might have wrong client_id
   MATCH (e1:Episodic {client_id: 'ab-01'})-[r:REL]->(e2:Episodic {client_id: 'ab-01'})
   // Still need: WHERE r.client_id = 'ab-01'
   ```

4. **Don't mix client_id values in same query**
   ```cypher
   // ❌ BAD - Opens cross-tenant queries
   MATCH (e1:Episodic {client_id: 'ab-01'})-[r]->(e2:Episodic {client_id: 'ab-02'})
   ```

---

## Migration: Fixing Existing Data

If you already have relationships without `client_id`:

### Step 1: Audit Existing Data
```cypher
// Find relationships missing client_id
MATCH (n1)-[r]->(n2)
WHERE r.client_id IS NULL
  AND n1.client_id IS NOT NULL
  AND n2.client_id IS NOT NULL
RETURN
  type(r) as rel_type,
  count(*) as missing_client_id,
  count(CASE WHEN n1.client_id = n2.client_id THEN 1 END) as same_client,
  count(CASE WHEN n1.client_id <> n2.client_id THEN 1 END) as cross_client
ORDER BY missing_client_id DESC;
```

### Step 2: Fix Same-Client Relationships
```cypher
// Add client_id to valid relationships
MATCH (n1)-[r]->(n2)
WHERE r.client_id IS NULL
  AND n1.client_id IS NOT NULL
  AND n2.client_id IS NOT NULL
  AND n1.client_id = n2.client_id  // Only fix same-client rels
SET r.client_id = n1.client_id
RETURN count(*) as fixed_relationships;
```

### Step 3: DELETE Cross-Client Relationships
```cypher
// CRITICAL: Delete cross-client contamination
MATCH (n1)-[r]->(n2)
WHERE r.client_id IS NULL
  AND n1.client_id IS NOT NULL
  AND n2.client_id IS NOT NULL
  AND n1.client_id <> n2.client_id  // Cross-client contamination!
DELETE r
RETURN count(*) as deleted_violations;
```

### Step 4: Verify Clean State
```cypher
// Should return 0
MATCH ()-[r]->()
WHERE r.client_id IS NULL
RETURN count(*) as remaining_without_client_id;
```

---

## Performance Optimization

### Indexes for Multi-Tenant Queries

```cypher
// Composite indexes for common patterns
CREATE INDEX episodic_client_time IF NOT EXISTS
FOR (e:Episodic) ON (e.client_id, e.event_time);

CREATE INDEX resource_client_kind IF NOT EXISTS
FOR (r:Resource) ON (r.client_id, r.kind);

CREATE INDEX resource_client_kind_ns IF NOT EXISTS
FOR (r:Resource) ON (r.client_id, r.kind, r.ns);

// Relationship property index
CREATE INDEX rel_client_id IF NOT EXISTS
FOR ()-[r:POTENTIAL_CAUSE]-() ON (r.client_id);

CREATE INDEX topology_rel_client IF NOT EXISTS
FOR ()-[r:SELECTS]-() ON (r.client_id);
```

### Query Performance Tips

1. **Put client_id filter first**
   ```cypher
   // ✅ FAST - Uses index
   MATCH (e:Episodic {client_id: $client_id})
   WHERE e.event_time > datetime() - duration({hours: 24})

   // ❌ SLOW - Scans all events first
   MATCH (e:Episodic)
   WHERE e.event_time > datetime() - duration({hours: 24})
     AND e.client_id = $client_id
   ```

2. **Use CALL subqueries for per-client processing**
   ```cypher
   // ✅ EFFICIENT - Processes each client independently
   MATCH (r:Resource)
   WITH DISTINCT r.client_id as client_id
   CALL {
     WITH client_id
     MATCH (e:Episodic {client_id: client_id})
     // Process this client's events
     RETURN count(*) as event_count
   }
   RETURN client_id, event_count
   ```

---

## Automated Monitoring

Create a scheduled job to check isolation health:

```cypher
// Run daily: Check for violations
MATCH (n1)-[r]->(n2)
WHERE (n1.client_id IS NOT NULL AND n2.client_id IS NOT NULL)
  AND (
    r.client_id IS NULL
    OR n1.client_id <> n2.client_id
    OR n1.client_id <> r.client_id
    OR n2.client_id <> r.client_id
  )
RETURN
  date() as check_date,
  count(*) as violations,
  collect({
    from_client: n1.client_id,
    to_client: n2.client_id,
    rel_client: r.client_id,
    rel_type: type(r)
  })[0..5] as samples;

// Alert if violations > 0
```

---

## Summary: Critical Changes

| Item | Before | After | Impact |
|------|--------|-------|--------|
| **Node queries** | `MATCH (e:Episodic)` | `MATCH (e:Episodic {client_id: $client_id})` | ✅ Isolated |
| **Relationships** | No `client_id` property | All have `client_id` property | ✅ Isolated |
| **Verification** | Only node filters | Node + relationship + cross-check | ✅ Triple safety |
| **Topology script** | Single client only | Batch all clients OR parameterized | ✅ Scalable |
| **Monitoring** | None | Cross-tenant violation detector | ✅ Auditable |

---

## Next Steps

1. ✅ Run `CREATE-TOPOLOGY-RELATIONSHIPS.cypher` with `:param client_id => 'ab-01'`
2. ✅ Run verification Query 2 (should return 0 violations)
3. ✅ Create enhanced RCA script with same isolation
4. ✅ Add indexes for performance
5. ✅ Set up daily violation monitoring

**Result**: Complete multi-tenant isolation with zero data leakage risk!
