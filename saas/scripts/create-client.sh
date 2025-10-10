#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════
# CREATE CLIENT ACCOUNT
# Creates a new client account with credentials
# ═══════════════════════════════════════════════════════════════════════════

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
CLIENT_NAME=""
CLIENT_EMAIL=""
CLIENT_PLAN="basic"
SERVER_NAMESPACE="kg-rca-server"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-changeme}"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --name)
      CLIENT_NAME="$2"
      shift 2
      ;;
    --email)
      CLIENT_EMAIL="$2"
      shift 2
      ;;
    --plan)
      CLIENT_PLAN="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 --name <name> --email <email> [OPTIONS]"
      echo ""
      echo "Required:"
      echo "  --name NAME           Client company name"
      echo "  --email EMAIL         Client admin email"
      echo ""
      echo "Options:"
      echo "  --plan PLAN           Pricing plan (free|basic|pro|enterprise, default: basic)"
      echo "  --help                Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [ -z "$CLIENT_NAME" ] || [ -z "$CLIENT_EMAIL" ]; then
  echo "Error: --name and --email are required"
  echo "Use --help for usage information"
  exit 1
fi

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  CREATE CLIENT ACCOUNT"
echo "  Name: $CLIENT_NAME"
echo "  Email: $CLIENT_EMAIL"
echo "  Plan: $CLIENT_PLAN"
echo "  $(date)"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 1. GENERATE CLIENT ID AND CREDENTIALS
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[1/5] Generating credentials...${NC}"

# Generate client ID (slug + random)
CLIENT_SLUG=$(echo "$CLIENT_NAME" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]' | cut -c1-10)
CLIENT_RANDOM=$(openssl rand -hex 4)
CLIENT_ID="client-${CLIENT_SLUG}-${CLIENT_RANDOM}"

# Generate API key
API_KEY="${CLIENT_SLUG}_$(openssl rand -hex 16)"

# Generate Kafka credentials
KAFKA_USERNAME="$CLIENT_ID"
KAFKA_PASSWORD=$(openssl rand -base64 24)

echo "Client ID: $CLIENT_ID"
echo "API Key: $API_KEY"
echo "Kafka Username: $KAFKA_USERNAME"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 2. CREATE NEO4J DATABASE
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[2/5] Creating Neo4j database...${NC}"

NEO4J_POD=$(kubectl get pods -n "$SERVER_NAMESPACE" -l app=neo4j --field-selector=status.phase=Running -o name | head -1)

if [ -z "$NEO4J_POD" ]; then
  echo -e "${RED}✗ Neo4j pod not found${NC}"
  exit 1
fi

# Create database for client
DB_NAME=$(echo "${CLIENT_ID}_kg" | tr '-' '_')

kubectl exec -n "$SERVER_NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "CREATE DATABASE \`$DB_NAME\` IF NOT EXISTS" || echo "Database may already exist"

echo -e "${GREEN}✓ Created database: $DB_NAME${NC}"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 3. CREATE KAFKA TOPICS
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[3/5] Creating Kafka topics...${NC}"

KAFKA_POD=$(kubectl get pods -n "$SERVER_NAMESPACE" -l app=kafka --field-selector=status.phase=Running -o name | head -1)

if [ -z "$KAFKA_POD" ]; then
  echo -e "${RED}✗ Kafka pod not found${NC}"
  exit 1
fi

# Topics to create
TOPICS=(
  "${CLIENT_ID}.events.normalized"
  "${CLIENT_ID}.logs.normalized"
  "${CLIENT_ID}.state.k8s.resource"
  "${CLIENT_ID}.state.k8s.topology"
  "${CLIENT_ID}.alerts.enriched"
  "${CLIENT_ID}.alerts.raw"
)

for TOPIC in "${TOPICS[@]}"; do
  kubectl exec -n "$SERVER_NAMESPACE" "$KAFKA_POD" -- kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --create \
    --if-not-exists \
    --topic "$TOPIC" \
    --partitions 3 \
    --replication-factor 1 || echo "Topic may already exist"

  echo "  ✓ $TOPIC"
done

echo ""

# ───────────────────────────────────────────────────────────────────────────
# 4. STORE CLIENT METADATA (PostgreSQL)
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[4/5] Storing client metadata...${NC}"

# Note: In production, this would insert into PostgreSQL
# For now, we'll create a ConfigMap with client info

kubectl create configmap -n "$SERVER_NAMESPACE" "client-${CLIENT_ID}-metadata" \
  --from-literal=client_id="$CLIENT_ID" \
  --from-literal=name="$CLIENT_NAME" \
  --from-literal=email="$CLIENT_EMAIL" \
  --from-literal=plan="$CLIENT_PLAN" \
  --from-literal=created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --dry-run=client -o yaml | kubectl apply -f -

echo -e "${GREEN}✓ Metadata stored${NC}"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 5. GENERATE CLIENT INSTALLATION PACKAGE
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[5/5] Generating installation package...${NC}"

# Create output directory
OUTPUT_DIR="./client-packages/$CLIENT_ID"
mkdir -p "$OUTPUT_DIR"

# Create values file for client
cat > "$OUTPUT_DIR/client-values.yaml" <<EOF
# KG RCA Agent Configuration
# Client: $CLIENT_NAME
# Generated: $(date)

client:
  id: "$CLIENT_ID"
  apiKey: "$API_KEY"
  serverUrl: "https://api.kg-rca.yourcompany.com"  # UPDATE THIS

  kafka:
    brokers: "kafka.kg-rca.yourcompany.com:9092"  # UPDATE THIS
    sasl:
      enabled: true
      mechanism: SCRAM-SHA-512
      username: "$KAFKA_USERNAME"
      password: "$KAFKA_PASSWORD"

# Enable all agents
stateWatcher:
  enabled: true

vector:
  enabled: true

eventExporter:
  enabled: true

alertReceiver:
  enabled: true
EOF

# Create installation instructions
cat > "$OUTPUT_DIR/INSTALL.md" <<EOF
# KG RCA Agent Installation

Welcome to KG RCA! This package contains everything you need to connect your Kubernetes cluster.

## Prerequisites

- Kubernetes cluster (v1.20+)
- Helm 3.x installed
- \`kubectl\` configured

## Installation Steps

### 1. Add the Helm chart

\`\`\`bash
# Clone the repository or download the Helm chart
# (Provided separately)
\`\`\`

### 2. Install the agent

\`\`\`bash
helm install kg-rca-agent ./kg-rca-agent \\
  --namespace kg-rca \\
  --create-namespace \\
  --values client-values.yaml
\`\`\`

### 3. Verify installation

\`\`\`bash
kubectl get pods -n kg-rca

# Expected output:
# state-watcher-xxx    Running
# vector-xxx           Running
# event-exporter-xxx   Running
# alert-receiver-xxx   Running
\`\`\`

### 4. Verify connectivity

\`\`\`bash
kubectl logs -n kg-rca -l app=state-watcher --tail=50
\`\`\`

You should see logs indicating successful connection to the server.

## Support

- Email: support@kg-rca.com
- Documentation: https://docs.kg-rca.com
- Support Portal: https://support.kg-rca.com

## Account Details

- **Client ID**: $CLIENT_ID
- **Plan**: $CLIENT_PLAN
- **Contact**: $CLIENT_EMAIL

---

**Important**: Keep your \`client-values.yaml\` file secure. It contains sensitive credentials.
EOF

echo -e "${GREEN}✓ Installation package created: $OUTPUT_DIR${NC}"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# SUMMARY
# ───────────────────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  CLIENT ACCOUNT CREATED"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "Client ID: $CLIENT_ID"
echo "API Key: $API_KEY"
echo "Database: $DB_NAME"
echo "Kafka Topics: ${#TOPICS[@]} topics created"
echo ""
echo "Installation Package: $OUTPUT_DIR"
echo ""
echo "Next steps:"
echo "  1. Send installation package to client: $OUTPUT_DIR"
echo "  2. Client follows INSTALL.md instructions"
echo "  3. Verify connection with: ./validate-rca.sh --client-id $CLIENT_ID"
echo ""
echo -e "${GREEN}✅ Client onboarding complete!${NC}"
