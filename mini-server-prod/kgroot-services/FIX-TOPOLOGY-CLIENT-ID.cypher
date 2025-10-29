// ============================================================================
// FIX TOPOLOGY RELATIONSHIPS - ADD MISSING client_id
// ============================================================================
// This script adds client_id to existing topology relationships that are missing it
// ============================================================================

// ============================================================================
// STEP 1: Add client_id to SELECTS relationships
// ============================================================================

MATCH (r1:Resource)-[rel:SELECTS]->(r2:Resource)
WHERE rel.client_id IS NULL
  AND r1.client_id IS NOT NULL
  AND r2.client_id IS NOT NULL
  AND r1.client_id = r2.client_id  // Only fix same-client relationships
SET rel.client_id = r1.client_id
RETURN count(*) as selects_fixed;


// ============================================================================
// STEP 2: Add client_id to RUNS_ON relationships
// ============================================================================

MATCH (r1:Resource)-[rel:RUNS_ON]->(r2:Resource)
WHERE rel.client_id IS NULL
  AND r1.client_id IS NOT NULL
  AND r2.client_id IS NOT NULL
  AND r1.client_id = r2.client_id
SET rel.client_id = r1.client_id
RETURN count(*) as runs_on_fixed;


// ============================================================================
// STEP 3: Add client_id to CONTROLS relationships
// ============================================================================

MATCH (r1:Resource)-[rel:CONTROLS]->(r2:Resource)
WHERE rel.client_id IS NULL
  AND r1.client_id IS NOT NULL
  AND r2.client_id IS NOT NULL
  AND r1.client_id = r2.client_id
SET rel.client_id = r1.client_id
RETURN count(*) as controls_fixed;


// ============================================================================
// STEP 4: DELETE any cross-client contamination (if any)
// ============================================================================

MATCH (r1:Resource)-[rel:SELECTS|RUNS_ON|CONTROLS]->(r2:Resource)
WHERE r1.client_id IS NOT NULL
  AND r2.client_id IS NOT NULL
  AND r1.client_id <> r2.client_id  // Cross-client contamination!
DELETE rel
RETURN count(*) as cross_client_violations_deleted;


// ============================================================================
// STEP 5: Verify all topology relationships now have client_id
// ============================================================================

MATCH ()-[r:SELECTS|RUNS_ON|CONTROLS]->()
RETURN
  type(r) as rel_type,
  count(CASE WHEN r.client_id IS NOT NULL THEN 1 END) as with_client_id,
  count(CASE WHEN r.client_id IS NULL THEN 1 END) as without_client_id,
  count(*) as total
ORDER BY rel_type;

// EXPECTED: without_client_id = 0 for all types


// ============================================================================
// STEP 6: Verify no cross-tenant violations remain
// ============================================================================

MATCH (r1:Resource)-[rel:SELECTS|RUNS_ON|CONTROLS]->(r2:Resource)
WHERE r1.client_id <> r2.client_id
   OR r1.client_id <> rel.client_id
   OR r2.client_id <> rel.client_id
RETURN
  count(*) as remaining_violations,
  'MUST be 0!' as warning;

// EXPECTED: remaining_violations = 0
