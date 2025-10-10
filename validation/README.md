# Query Library Validation

This directory contains validation scripts and reports for the Knowledge Graph query library.

## Overview

All queries from [production/neo4j-queries/QUERY_LIBRARY.md](../production/neo4j-queries/QUERY_LIBRARY.md) have been validated and are working correctly.

## Validation Scripts

### 1. `test-query-library.sh`
Automated test suite that validates all 17 query categories for syntax correctness and execution.

**Usage:**
```bash
./validation/test-query-library.sh
```

**Output:**
- ✅ Pass/Fail status for each query category
- Number of results returned
- Execution errors (if any)
- Summary statistics

**Test Coverage:**
- RCA & Causality Queries (3 tests)
- Vector Embedding Queries (2 tests)
- Resource & Topology Queries (3 tests)
- Incident Analysis Queries (2 tests)
- Anomaly Detection Queries (2 tests)
- Performance & Health Queries (3 tests)
- Maintenance Queries (2 tests)

### 2. `test-rca-quality.sh`
Comprehensive validation of RCA quality and meaningfulness of results.

**Usage:**
```bash
./validation/test-rca-quality.sh
```

**Tests:**
1. Recent ERROR/FATAL events detection
2. Detailed RCA with confidence scoring
3. POTENTIAL_CAUSE relationship validation
4. Causal chain discovery
5. Cascading failure detection
6. Resource blast radius calculation
7. Incident clustering
8. System health dashboard
9. Error-prone resource identification
10. Topology relationship validation

### 3. `interactive-query-test.sh`
Interactive menu-driven query tester for exploring the knowledge graph.

**Usage:**
```bash
./validation/interactive-query-test.sh
```

**Features:**
- 11 pre-built queries covering common use cases
- Custom query execution
- User-friendly menu interface
- Sample data auto-population

**Available Queries:**
1. Find recent ERROR/FATAL events
2. Root cause analysis for a specific event
3. Find cascading failures
4. Check system health
5. Find error-prone resources
6. Get topology for a resource
7. Find causal chains
8. Get incident timeline
9. Detect memory leaks (OOM events)
10. Check embedding coverage
11. Database statistics
12. Custom query (enter your own)

## Validation Report

See [QUERY_LIBRARY_VALIDATION_REPORT.md](./QUERY_LIBRARY_VALIDATION_REPORT.md) for detailed results.

### Summary

✅ **Status**: All queries validated successfully

**Knowledge Graph Stats:**
- Total Events: 4,473
- Total Resources: 335
- POTENTIAL_CAUSE Relationships: 7,544
- Topology Relationships: 202
- Incidents: Multiple clustered incidents

**RCA Quality:**
- ✅ Root cause detection working
- ✅ Confidence scoring operational
- ✅ Causal chains identified (up to 3 hops)
- ✅ Cascading failures detected (80+ cascaded events)
- ✅ Incident clustering functional
- ✅ Topology traversal working

## Quick Start

### Prerequisites

- Docker running with Neo4j container: `kgroot_latest-neo4j-1`
- Neo4j credentials: `neo4j/anuragvishwa`
- cypher-shell available in container

### Run All Validations

```bash
# Navigate to validation directory
cd validation

# Make scripts executable
chmod +x *.sh

# Run syntax validation
./test-query-library.sh

# Run RCA quality validation
./test-rca-quality.sh

# Start interactive tester
./interactive-query-test.sh
```

## Example Output

### Successful Test
```
Test 1: Find Root Causes with Confidence
Description: Find root causes for an event with confidence scores
✓ Query executed successfully
  Results: 5 rows
```

### RCA Results
```
Chain Example:
Root: e864d7a4 (KubePodCrashLooping)
  ↓ [confidence: 0.49]
  → fbd691f8 (KubePodCrashLooping)
  ↓ [confidence: 0.70]
Effect: 970df7e5 (KubePodCrashLooping)
```

## Troubleshooting

### Authentication Error
If you see "incorrect authentication details":
```bash
# Check Neo4j password in docker-compose.yml
grep NEO4J_AUTH docker-compose.yml

# Update scripts with correct password
# Edit NEO4J_PASS variable in script headers
```

### Container Not Running
```bash
# Check if Neo4j is running
docker ps | grep neo4j

# Start services if needed
docker-compose up -d neo4j
```

### Empty Results
If queries return no results:
```bash
# Check if data is loaded
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (n) RETURN count(n) AS total_nodes"

# If empty, run data ingestion
# (See main README for data loading instructions)
```

## Query Categories Validated

1. **RCA & Causality Queries**
   - Root cause detection with confidence scoring
   - Complete causal chain analysis
   - Cascading failure detection

2. **Vector Embedding Queries**
   - Semantic similarity search
   - Batch embedding generation
   - Duplicate event detection

3. **Resource & Topology Queries**
   - Complete resource topology
   - Blast radius calculation
   - Orphaned resource detection

4. **Incident Analysis Queries**
   - Event clustering into incidents
   - Incident timeline analysis
   - Impact scoring

5. **Anomaly Detection Queries**
   - Error spike detection
   - Memory leak patterns
   - Cascading failures
   - Resource churn

6. **Performance & Health Queries**
   - System health dashboard
   - Resource health scores
   - Error-prone resource identification

7. **Maintenance Queries**
   - Event cleanup
   - Orphaned incident cleanup
   - Database statistics
   - Index management

## Notes

- All queries use parameterized inputs where applicable
- Time-based filters use Neo4j `duration()` functions
- Confidence scoring uses weighted averages of temporal, distance, and domain scores
- Causal chains support up to 5 hops (configurable)
- All queries are optimized for performance with proper indexes

## Files

```
validation/
├── README.md                              # This file
├── QUERY_LIBRARY_VALIDATION_REPORT.md     # Detailed validation report
├── test-query-library.sh                  # Automated query syntax tests
├── test-rca-quality.sh                    # RCA quality validation
└── interactive-query-test.sh              # Interactive query tester
```

## Support

For issues or questions:
1. Check the validation report for known issues
2. Run the interactive tester to explore queries
3. Review query syntax in production/neo4j-queries/QUERY_LIBRARY.md
4. Check Neo4j logs: `docker logs kgroot_latest-neo4j-1`

---

**Last Updated**: 2025-10-08
**Status**: ✅ All queries validated and working
