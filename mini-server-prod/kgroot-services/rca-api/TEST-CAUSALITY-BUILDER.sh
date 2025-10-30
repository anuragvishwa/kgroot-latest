#!/bin/bash

# Test script for the on-demand causality builder endpoint
# Usage: ./TEST-CAUSALITY-BUILDER.sh [client_id] [rca_api_url]

CLIENT_ID=${1:-"loc-01"}
RCA_API_URL=${2:-"http://localhost:8083"}

echo "==============================================="
echo "Testing On-Demand Causality Builder"
echo "Client: $CLIENT_ID"
echo "API: $RCA_API_URL"
echo "==============================================="

echo ""
echo "Step 1: Diagnostic Mode (check events and relationships)"
echo "-------------------------------------------------------"
curl -s -X POST "$RCA_API_URL/api/v1/rca/build-causality/$CLIENT_ID?build_relationships=false" | jq .

echo ""
echo ""
echo "Step 2: Build Causality Relationships (24 hours, min_confidence 0.3)"
echo "-------------------------------------------------------------------"
curl -s -X POST "$RCA_API_URL/api/v1/rca/build-causality/$CLIENT_ID?time_range_hours=24&min_confidence=0.3&build_relationships=true" | jq .

echo ""
echo ""
echo "Step 3: Verify Root Causes are now found"
echo "-----------------------------------------"
curl -s "$RCA_API_URL/api/v1/rca/root-causes/$CLIENT_ID?time_range_hours=24&limit=5" | jq .

echo ""
echo ""
echo "Step 4: Check Health Summary"
echo "-----------------------------"
curl -s "$RCA_API_URL/api/v1/health/summary/$CLIENT_ID?time_range_hours=24" | jq .

echo ""
echo "==============================================="
echo "Test Complete!"
echo "==============================================="
echo ""
echo "Next Steps:"
echo "1. If root causes found, get blast radius: GET /api/v1/rca/blast-radius/{event_id}?client_id=$CLIENT_ID"
echo "2. Run RCA analysis with GPT-5:"
echo "   curl -X POST $RCA_API_URL/api/v1/rca/analyze \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"query\": \"What caused failures in buglab namespace?\", \"client_id\": \"$CLIENT_ID\", \"time_range_hours\": 24}' | jq ."
echo ""
