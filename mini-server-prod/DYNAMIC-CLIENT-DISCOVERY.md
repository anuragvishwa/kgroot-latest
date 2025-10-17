# Dynamic Client Discovery for Multi-Tenant Setup

## Overview

This approach automatically discovers which `client_id` values are actually sending data to your Kafka topics and generates the appropriate docker-compose configuration dynamically.

**Benefits:**
- ✅ No hardcoded client IDs
- ✅ Automatically adapts to new clients
- ✅ Only creates graph-builders for active clients
- ✅ Easy to regenerate when clients are added/removed

## How It Works

```
┌─────────────────┐
│  Kafka Topics   │
│  (actual data)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Discovery Script│ ← Samples messages, extracts client_ids
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Auto-Generate  │ ← Creates docker-compose.multi-client.generated.yml
│   Config File   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Deploy Builders │ ← One graph-builder per discovered client_id
└─────────────────┘
```

## Quick Start

### Step 1: Discover Client IDs

Run the discovery script to see what client IDs are in your Kafka topics:

```bash
cd mini-server-prod
./discover-client-ids.sh
```

**Example output:**
```
==========================================
Discovering Client IDs in Kafka Topics
==========================================

📊 Sampling topic: logs.normalized
   ✅ Found client_id(s):
      - prod-us-east-1
      - staging-eu-west-1

📊 Sampling topic: events.normalized
   ✅ Found client_id(s):
      - prod-us-east-1

==========================================
Summary of All Unique Client IDs
==========================================

Found 2 unique client ID(s):

  • prod-us-east-1
  • staging-eu-west-1
```

### Step 2: Generate Configuration

Generate the docker-compose configuration automatically:

```bash
./generate-multi-client-compose.sh
```

This creates `docker-compose.multi-client.generated.yml` with graph-builder services for each discovered client.

### Step 3: Deploy

Stop the single graph-builder and deploy the multi-client setup:

```bash
# Stop single graph-builder
docker compose -f compose/docker-compose.yml stop graph-builder

# Deploy multi-client graph-builders
docker compose -f compose/docker-compose.yml -f compose/docker-compose.multi-client.generated.yml up -d
```

### Step 4: Verify

Check that all graph-builders are running:

```bash
# View running containers
docker compose ps | grep graph-builder

# Check consumer groups
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list | grep kg-builder

# Check metrics for each client
curl http://localhost:9091/metrics  # First client
curl http://localhost:9092/metrics  # Second client
curl http://localhost:9093/metrics  # Third client
```

## When to Regenerate

Regenerate the configuration when:

1. **New client added** - A new Kubernetes cluster starts sending data
2. **Client removed** - You want to stop processing a client's data
3. **Client ID renamed** - A client changes their identifier

Just run the generator script again:

```bash
./generate-multi-client-compose.sh
docker compose -f docker-compose.yml -f docker-compose.multi-client.generated.yml up -d
```

## What If No Client IDs Found?

If the discovery script finds no client IDs, it means:

1. **No messages sent yet** - Wait for clients to send data
2. **Missing client_id field** - Client-side Vector not configured
3. **Wrong topic names** - Check that topics match your setup

### Fix: Configure Client-Side

Ensure your client-side Helm chart has `client.id` set:

```yaml
# client-light/helm-chart/values.yaml
client:
  id: "prod-us-east-1"  # Set this!
  kafka:
    brokers: "your-kafka-server:9092"
```

Then deploy/upgrade the Helm chart:

```bash
helm upgrade --install client-light ./client-light/helm-chart \
  --set client.id=prod-us-east-1 \
  --set client.kafka.brokers=your-kafka:9092
```

## Manual Client IDs (Alternative)

If you want to pre-configure clients before they send data, create a manual list:

```bash
# manual-client-ids.txt
prod-us-east-1
prod-eu-west-1
staging-dev-1
```

Then modify the generator script to read from this file instead of Kafka.

## Comparison with Static Configuration

| Approach | Pros | Cons |
|----------|------|------|
| **Dynamic Discovery** (this approach) | ✅ Auto-adapts to real clients<br>✅ No hardcoding<br>✅ Always in sync with reality | ⚠️ Requires existing data<br>⚠️ Can't pre-provision |
| **Static Config** (docker-compose.multi-client.yml) | ✅ Can pre-provision<br>✅ Explicit control | ❌ Must manually update<br>❌ Easy to get out of sync |
| **Environment Variables** | ✅ Flexible<br>✅ Good for few clients | ❌ Complex for many clients<br>❌ Still requires manual config |

## Best Practice: Hybrid Approach

1. **Development/Testing**: Use static config with dummy client IDs
2. **Production**: Use dynamic discovery to match reality
3. **Before Go-Live**: Pre-configure expected clients manually

## Monitoring Client IDs

### Check Neo4j for Client Distribution

```cypher
// Count resources per client
MATCH (r:Resource)
RETURN r.client_id as client, count(*) as resources
ORDER BY resources DESC

// Count events per client
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
RETURN r.client_id as client, count(DISTINCT e) as events
ORDER BY events DESC
```

### Check Kafka Consumer Lag

```bash
# List all consumer groups
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list | grep kg-builder

# Check lag for specific client
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group kg-builder-prod-us-east-1 \
  --describe
```

## Troubleshooting

### Script Says "No client_ids found"

**Cause**: Messages don't have `client_id` field

**Fix**:
1. Check a message manually:
```bash
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic logs.normalized \
  --max-messages 1 | jq '.'
```

2. Verify Vector config has client_id transformation:
```toml
.client_id = "{{ .Values.client.id }}"
```

### Graph-builder not filtering messages

**Cause**: CLIENT_ID environment variable not set correctly

**Fix**: Check container environment:
```bash
docker inspect kg-graph-builder-prod-us-east-1 | jq '.[0].Config.Env' | grep CLIENT_ID
```

### Too many old client IDs

**Cause**: Discovery script finds historical clients no longer active

**Fix**: Sample only recent messages:
```bash
# Modify SAMPLE_SIZE or use --max-messages with offset
# Or manually edit the generated file to remove unwanted clients
```

## Advanced: Auto-Discovery Service

For large-scale deployments, consider creating a service that:

1. Continuously monitors Kafka for new client_ids
2. Automatically updates docker-compose config
3. Triggers container redeployment
4. Sends notifications when new clients appear

This could be a simple cron job:

```bash
# /etc/cron.hourly/update-client-builders
#!/bin/bash
cd /path/to/mini-server-prod
./generate-multi-client-compose.sh
docker compose -f docker-compose.yml -f docker-compose.multi-client.generated.yml up -d
```

## See Also

- [MULTI-TENANT-SETUP.md](./MULTI-TENANT-SETUP.md) - Complete multi-tenant guide
- [README.md](./README.md) - General setup instructions
- [client-light Helm chart](../client-light/helm-chart/) - Client-side configuration
