#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "  RCA End-to-End Testing Suite"
echo "========================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

function info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

function warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

function error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

function section() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# Check prerequisites
info "Checking prerequisites..."

if ! kubectl get namespace observability &>/dev/null; then
    error "observability namespace not found. Deploy KGroot first."
    exit 1
fi

if ! kubectl get pod -n observability -l app=neo4j | grep -q Running; then
    error "Neo4j not running. Deploy Neo4j first."
    exit 1
fi

if ! kubectl get pod -n observability -l app=kg-builder | grep -q Running; then
    error "kg-builder not running. Deploy kg-builder first."
    exit 1
fi

info "All prerequisites met!"

# Baseline validation
section "Baseline Validation (Before Tests)"
./test/validate-rca.sh || {
    warn "Baseline validation had warnings. Continuing..."
}

# Test 1: ImagePullBackOff
section "Test 1: ImagePullBackOff (Wrong Image Tag)"
info "Deploying test app with non-existent image..."
kubectl apply -f test/01-imagepull-failure.yaml

info "Waiting 60 seconds for events to propagate..."
sleep 60

info "Checking pod status..."
kubectl get pods -l test=rca-imagepull

info "Checking events captured in Kafka..."
kubectl exec -n observability kafka-0 -- \
    kafka-console-consumer.sh --bootstrap-server localhost:9092 \
    --topic events.normalized --max-messages 5 --timeout-ms 5000 2>/dev/null | grep -i "pull" || {
    warn "No ImagePull events found in Kafka yet"
}

info "Verifying in Neo4j..."
kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH (e:Episodic) WHERE e.reason CONTAINS 'Pull' AND e.event_time > datetime() - duration({minutes: 10}) RETURN e.reason, e.message LIMIT 3;" || {
    warn "No ImagePull events in Neo4j yet"
}

info "✅ Test 1 deployed. Keeping it running for RCA analysis."
echo ""

# Test 2: CrashLoopBackOff
section "Test 2: CrashLoopBackOff (Application Panic)"
info "Deploying app that crashes immediately..."
kubectl apply -f test/02-crashloop.yaml

info "Waiting 60 seconds for crashes and logs..."
sleep 60

info "Checking pod status..."
kubectl get pods -l test=rca-crashloop

info "Checking logs captured..."
kubectl exec -n observability kafka-0 -- \
    kafka-console-consumer.sh --bootstrap-server localhost:9092 \
    --topic logs.normalized --max-messages 5 --timeout-ms 5000 2>/dev/null | grep -i "error\|fatal" || {
    warn "No error logs found in Kafka yet"
}

info "Verifying in Neo4j..."
kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH (e:Episodic {etype: 'k8s.log'}) WHERE e.severity IN ['ERROR', 'FATAL'] AND e.event_time > datetime() - duration({minutes: 10}) RETURN e.reason, e.message LIMIT 3;" || {
    warn "No error logs in Neo4j yet"
}

info "✅ Test 2 deployed. Logs should show 'ERROR: Fatal panic!'"
echo ""

# Test 3: OOMKilled
section "Test 3: OOMKilled (Memory Exhaustion)"
info "Deploying memory-hungry app with strict limits..."
kubectl apply -f test/03-oomkilled.yaml

info "Waiting 90 seconds for OOM kill..."
sleep 90

info "Checking pod status (should see OOMKilled)..."
kubectl get pods -l test=rca-oom
kubectl describe pod -l test=rca-oom | grep -A 5 "Last State" || true

info "✅ Test 3 deployed."
echo ""

# Test 4: Service Selector Mismatch
section "Test 4: Service Unavailable (Selector Mismatch)"
info "Deploying service with wrong selector..."
kubectl apply -f test/04-service-mismatch.yaml

info "Waiting 30 seconds..."
sleep 30

info "Checking service endpoints (should be empty)..."
kubectl describe service test-backend | grep -A 3 "Endpoints:" || true

info "Checking pods (should be running but not selected)..."
kubectl get pods -l app=backend,version=v1

info "Verifying in Neo4j (service should have 0 SELECTS relationships)..."
kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH (svc:Resource:Service {name: 'test-backend'}) OPTIONAL MATCH (svc)-[:SELECTS]->(pod) RETURN svc.name, count(pod) AS pod_count;" || {
    warn "Service not in Neo4j yet"
}

info "✅ Test 4 deployed."
echo ""

# Test 5: Cascading Failure
section "Test 5: Cascading Failure (DB → API → Frontend)"
info "Deploying 3-tier app with broken database..."
kubectl apply -f test/05-cascading-failure.yaml

info "Waiting 120 seconds for cascade to propagate..."
sleep 120

info "Checking all tiers..."
echo "Database:"
kubectl get pods -l tier=database

echo "API:"
kubectl get pods -l tier=api

echo "Frontend:"
kubectl get pods -l tier=frontend

info "Checking for causal links in Neo4j..."
kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH (e1:Episodic)-[:POTENTIAL_CAUSE]->(e2:Episodic) WHERE e1.event_time > datetime() - duration({minutes: 15}) RETURN e1.reason AS cause, e2.reason AS effect LIMIT 5;" || {
    warn "No POTENTIAL_CAUSE links yet. May need more time."
}

info "✅ Test 5 deployed. This is the most complex test!"
echo ""

# Test 6: Missing Environment Variable
section "Test 6: Configuration Error (Missing Env Var)"
info "Deploying app that expects DATABASE_URL..."
kubectl apply -f test/06-missing-env.yaml

info "Waiting 60 seconds..."
sleep 60

info "Checking pod status..."
kubectl get pods -l test=rca-config

info "Checking logs for FATAL error..."
kubectl logs -l test=rca-config --tail=10 2>/dev/null || {
    warn "Pod may not have started yet"
}

info "✅ Test 6 deployed."
echo ""

# Final validation
section "Final Validation (After All Tests)"
sleep 30  # Give kg-builder time to process

info "Running comprehensive validation..."
./test/validate-rca.sh

# Summary
section "Test Deployment Summary"
echo "All test scenarios deployed!"
echo ""
echo "Running pods:"
kubectl get pods -l test

echo ""
echo "Next Steps:"
echo "=========================================="
echo ""
echo "1. Access Neo4j Browser:"
echo "   kubectl port-forward -n observability svc/neo4j-external 7474:7474"
echo "   URL: http://localhost:7474"
echo "   User: neo4j / Password: anuragvishwa"
echo ""
echo "2. Run example queries from RCA_TESTING_GUIDE.md"
echo ""
echo "3. Check specific test results:"
echo ""
echo "   # ImagePullBackOff"
echo "   cypher-shell> MATCH (e:Episodic) WHERE e.reason CONTAINS 'Pull' RETURN e;"
echo ""
echo "   # CrashLoop with log correlation"
echo "   cypher-shell> MATCH (log:Episodic {etype: 'k8s.log'})-[:POTENTIAL_CAUSE]->(crash:Episodic) RETURN log.message, crash.reason;"
echo ""
echo "   # Cascading failure chain"
echo "   cypher-shell> MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..3]->(symptom:Episodic) WHERE root.event_time > datetime() - duration({minutes: 30}) RETURN path;"
echo ""
echo "4. View Kafka messages:"
echo "   kubectl exec -n observability kafka-0 -- kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic events.normalized --from-beginning"
echo ""
echo "5. Check kg-builder logs:"
echo "   kubectl logs -n observability -l app=kg-builder -f"
echo ""
echo "6. Cleanup tests when done:"
echo "   ./test/cleanup-tests.sh"
echo ""
echo "=========================================="
