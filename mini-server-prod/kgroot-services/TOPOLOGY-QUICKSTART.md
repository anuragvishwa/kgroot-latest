# Topology Creation Quickstart

## Which Script Should I Use?

### Option 1: Single Client (Recommended for first time)
**File**: [CREATE-TOPOLOGY-SINGLE-CLIENT.cypher](CREATE-TOPOLOGY-SINGLE-CLIENT.cypher)

**When to use:**
- ✅ First time creating topology
- ✅ Testing with one client before rolling out to all
- ✅ Need to debug issues per client
- ✅ Want to run queries step-by-step

**How to run:**
```cypher
// In Neo4j Browser:
:param client_id => 'ab-01'

// Then paste and run the script
```

**Pros:**
- Simple and clear
- Easy to debug
- Can run steps individually
- Built-in verification queries

**Cons:**
- Need to run for each client separately
- More manual work for many clients

---

### Option 2: All Clients Batch
**File**: [CREATE-TOPOLOGY-ALL-CLIENTS.cypher](CREATE-TOPOLOGY-ALL-CLIENTS.cypher)

**When to use:**
- ✅ You've tested with single client successfully
- ✅ You have many clients (5+)
- ✅ You want to automate for all clients at once

**How to run:**
```bash
# Via cypher-shell
cypher-shell -u neo4j -p password -f CREATE-TOPOLOGY-ALL-CLIENTS.cypher

# Or in Neo4j Browser:
# Just paste and run (no parameters needed)
```

**Pros:**
- Processes all clients automatically
- One command for everything
- Returns per-client stats

**Cons:**
- Harder to debug if issues occur
- Processes all clients (can't pick specific ones)

---

### Option 3: Original Parameterized
**File**: [CREATE-TOPOLOGY-RELATIONSHIPS.cypher](CREATE-TOPOLOGY-RELATIONSHIPS.cypher)

**When to use:**
- ✅ You want the most detailed version
- ✅ You want extensive inline documentation
- ✅ Single client with detailed explanations

**How to run:**
```cypher
:param client_id => 'ab-01'
// Then run the script
```

**Pros:**
- Most comprehensive documentation
- Detailed comments explaining each step
- Same safety as other scripts

**Cons:**
- Longer file to read through
- More verbose

---

## Recommended Workflow

### Step 1: Test with One Client
Use **CREATE-TOPOLOGY-SINGLE-CLIENT.cypher** for client `'ab-01'`:

```cypher
// 1. Set parameter
:param client_id => 'ab-01'

// 2. Run the topology creation (Steps 1-6)
// (paste the script)

// 3. Verify results
// Expected output:
// - selects_by_selector: 20-100
// - selects_by_naming: 5-20
// - runs_on_created: ~241
// - deploy_to_rs_created: ~23
// - rs_to_pod_created: 100-200
// - ds_to_pod_created: 10-50

// 4. Run verification queries (included in script)
```

### Step 2: Check Isolation
Run the cross-tenant violation check:

```cypher
MATCH (r1:Resource)-[rel:SELECTS|RUNS_ON|CONTROLS]->(r2:Resource)
WHERE r1.client_id <> r2.client_id
   OR r1.client_id <> rel.client_id
   OR r2.client_id <> rel.client_id
RETURN count(*) as cross_tenant_violations;

// MUST return: 0
```

### Step 3: Verify Topology Works
Check that you can find multi-hop paths:

```cypher
:param client_id => 'ab-01'

MATCH path = (r1:Resource {client_id: $client_id})-[*1..3]-(r2:Resource {client_id: $client_id})
WHERE r1 <> r2
  AND ALL(rel IN relationships(path) WHERE type(rel) IN ['SELECTS', 'RUNS_ON', 'CONTROLS'])
  AND ALL(rel IN relationships(path) WHERE rel.client_id = $client_id)
RETURN
  length(path) as hops,
  count(DISTINCT path) as path_count
ORDER BY hops;

// Expected:
// hops=1: 300-600 paths
// hops=2: 1000-3000 paths
// hops=3: 3000-10000 paths
```

### Step 4: Roll Out to All Clients
Once verified with one client, use **CREATE-TOPOLOGY-ALL-CLIENTS.cypher**:

```bash
cypher-shell -u neo4j -p password -f CREATE-TOPOLOGY-ALL-CLIENTS.cypher
```

**Or** run it manually for specific clients:
```cypher
// Client 2
:param client_id => 'ab-02'
// Run CREATE-TOPOLOGY-SINGLE-CLIENT.cypher

// Client 3
:param client_id => 'ab-03'
// Run CREATE-TOPOLOGY-SINGLE-CLIENT.cypher
```

---

## Quick Verification Checklist

After creating topology, verify these:

- [ ] **Relationships have client_id**
  ```cypher
  MATCH ()-[rel:SELECTS|RUNS_ON|CONTROLS]->()
  WHERE rel.client_id IS NULL
  RETURN count(*) as missing_client_id;
  // Expected: 0
  ```

- [ ] **No cross-tenant contamination**
  ```cypher
  MATCH (r1:Resource)-[rel:SELECTS|RUNS_ON|CONTROLS]->(r2:Resource)
  WHERE r1.client_id <> r2.client_id
     OR r1.client_id <> rel.client_id
     OR r2.client_id <> rel.client_id
  RETURN count(*) as violations;
  // Expected: 0
  ```

- [ ] **Topology counts look reasonable**
  ```cypher
  :param client_id => 'ab-01'

  MATCH (r1:Resource {client_id: $client_id})-[rel]->(r2:Resource {client_id: $client_id})
  WHERE type(rel) IN ['SELECTS', 'RUNS_ON', 'CONTROLS']
    AND rel.client_id = $client_id
  RETURN
    type(rel) as rel_type,
    count(*) as count;

  // Expected:
  // RUNS_ON: ~241 (one per pod)
  // CONTROLS: 200-400
  // SELECTS: 50-150
  ```

- [ ] **Multi-hop paths exist**
  ```cypher
  // Should return paths with 1, 2, and 3 hops
  ```

- [ ] **Pod coverage is high**
  ```cypher
  MATCH (pod:Resource {kind: 'Pod', client_id: $client_id})
  OPTIONAL MATCH (pod)-[rel:SELECTS|RUNS_ON|CONTROLS {client_id: $client_id}]-()
  WITH pod, count(rel) as topology_rels
  RETURN
    count(CASE WHEN topology_rels > 0 THEN 1 END) * 100.0 / count(*) as coverage_pct;

  // Expected: >80%
  ```

---

## Troubleshooting

### Issue: selects_by_selector returns 0

**Cause**: Resource nodes don't have `selector` or `labels` properties.

**Fix**: Check what properties exist:
```cypher
MATCH (r:Resource {client_id: 'ab-01', kind: 'Pod'}) RETURN keys(r) LIMIT 1;
MATCH (r:Resource {client_id: 'ab-01', kind: 'Service'}) RETURN keys(r) LIMIT 1;
```

Update script to use correct property names (might be `label`, `pod_labels`, etc.)

### Issue: runs_on_created returns 0

**Cause**: Pods don't have `node` property.

**Fix**: Check property name:
```cypher
MATCH (r:Resource {client_id: 'ab-01', kind: 'Pod'})
RETURN r.node, r.nodeName, r.host_node LIMIT 1;
```

Update script with correct property name.

### Issue: Cross-tenant violations > 0

**Cause**: Existing relationships without `client_id` or wrong `client_id`.

**Fix**: Run migration from [MULTI-TENANT-ISOLATION-GUIDE.md](MULTI-TENANT-ISOLATION-GUIDE.md):

```cypher
// Delete cross-client contamination
MATCH (n1)-[r]->(n2)
WHERE n1.client_id <> n2.client_id
DELETE r;

// Fix same-client relationships
MATCH (n1)-[r]->(n2)
WHERE r.client_id IS NULL
  AND n1.client_id = n2.client_id
SET r.client_id = n1.client_id;
```

---

## Next Steps After Topology Creation

1. **Re-run Enhanced RCA Script**
   Now that topology exists, re-run causal relationship creation to use topology data.

2. **Verify topology_enhanced_relationships > 0**
   ```cypher
   MATCH ()-[pc:POTENTIAL_CAUSE]->()
   WHERE pc.distance_score IN [0.85, 0.70, 0.55]
   RETURN count(*) as topology_enhanced;

   // Should now be > 0 (was 0 before)
   ```

3. **Check improved accuracy**
   ```cypher
   MATCH ()-[pc:POTENTIAL_CAUSE]->()
   RETURN
     avg(pc.confidence) as avg_confidence,
     avg(pc.distance_score) as avg_distance_score;

   // Expected improvement:
   // avg_confidence: 0.85 → 0.88-0.90
   // avg_distance_score: 0.3-0.4 → 0.5-0.6
   ```

---

## Summary

| Script | Best For | Complexity | Multi-Client |
|--------|----------|------------|--------------|
| CREATE-TOPOLOGY-SINGLE-CLIENT.cypher | **First time, testing** | Low | Manual per client |
| CREATE-TOPOLOGY-ALL-CLIENTS.cypher | Production rollout | Medium | Automatic |
| CREATE-TOPOLOGY-RELATIONSHIPS.cypher | Detailed documentation | Medium | Manual per client |

**Recommendation**: Start with **CREATE-TOPOLOGY-SINGLE-CLIENT.cypher** for `client_id='ab-01'`, verify it works, then use **CREATE-TOPOLOGY-ALL-CLIENTS.cypher** for the rest.
