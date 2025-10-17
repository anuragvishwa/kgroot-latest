# Multi-Tenant Deployment Guide

This guide explains how to get `client_id` in all Kafka topics and deploy multi-tenant graph-builders.

## Current Status

Based on your discovery script output:
- ✅ **logs.normalized** - Has `client_id: af-3` (working!)
- ❌ **events.normalized** - NO `client_id` yet
- ❌ **state.k8s.resource** - NO `client_id` yet
- ❌ **state.k8s.topology** - NO `client_id` yet

## Why Missing client_id?

1. **events.normalized** - Produced by event-exporter **in client K8s clusters**
   - You upgraded the Helm chart, but need to restart the event-exporter pod

2. **state.k8s.resource & state.k8s.topology** - Produced by state-watcher **in client K8s clusters**
   - These are produced by state-watcher running IN the client K8s cluster
   - Need to deploy/upgrade state-watcher in client clusters

3. **Server-side graph-builder** - 4 days old, doesn't understand client_id filtering yet
   - Need to rebuild with new code

## Step-by-Step Fix

### Step 1: Pull Latest Code on Server

```bash
ssh ubuntu@ip-172-31-82-85
cd ~/kgroot-latest
git pull
```

### Step 2: Rebuild Server-Side Components

```bash
cd mini-server-prod
chmod +x rebuild-and-restart.sh
./rebuild-and-restart.sh
```

This will:
- Rebuild graph-builder with client_id support
- Restart the service
- Wait 30 seconds for logs to flow

### Step 3: Deploy State-Watcher in Client K8s Cluster

**On your client K8s cluster (where you have af-3):**

```bash
# Option A: If state-watcher is not deployed yet
kubectl apply -f state-watcher-deployment.yaml

# Option B: If using Helm (recommended)
# The client-light helm chart should include state-watcher
helm upgrade kg-rca-agent ./client-light/helm-chart \
  --set client.id=af-3 \
  --set client.kafka.brokers=<kafka-broker> \
  --set stateWatcher.enabled=true \
  # ... other values
```

**Check if state-watcher exists:**
```bash
kubectl get pods -n observability | grep state-watcher
```

If not, you need to add it to your client-light Helm chart or deploy it separately.

### Step 4: Restart Event-Exporter in Client Cluster

The event-exporter needs to be restarted to pick up the new layout configuration:

```bash
kubectl rollout restart deployment <event-exporter-name> -n observability
```

Or if using Helm:
```bash
helm upgrade kg-rca-agent ./client-light/helm-chart \
  --set client.id=af-3 \
  --reuse-values
```

### Step 5: Wait and Verify

Wait 1-2 minutes for messages to flow, then run discovery:

```bash
cd ~/kgroot-latest/mini-server-prod
./discover-client-ids.sh
```

You should now see:
```
✅ Found client_id(s) in logs.normalized: af-3
✅ Found client_id(s) in events.normalized: af-3
✅ Found client_id(s) in state.k8s.resource: af-3
✅ Found client_id(s) in state.k8s.topology: af-3
```

### Step 6: Generate Multi-Client Compose File

```bash
./generate-multi-client-compose.sh
```

This creates `compose/docker-compose.multi-client.yml` with a graph-builder for each client.

### Step 7: Deploy Multi-Tenant Graph-Builders

```bash
cd compose
docker compose -f docker-compose.yml -f docker-compose.multi-client.yml up -d
```

### Step 8: Verify Consumer Groups

```bash
# Check consumer groups
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list

# You should see:
# - kg-builder (main, processes all messages)
# - kg-builder-af-3 (tenant-specific, filters by client_id)
```

## Cleanup Old Consumer Groups

```bash
chmod +x cleanup-consumer-groups.sh
./cleanup-consumer-groups.sh
```

This will:
- Show all consumer groups
- Identify empty/inactive groups
- Let you delete them interactively

## Troubleshooting

### events.normalized still missing client_id

**Cause:** Event-exporter not restarted after Helm upgrade

**Fix:**
```bash
kubectl rollout restart deployment <event-exporter> -n observability
kubectl logs -f <event-exporter-pod> -n observability
```

### state.k8s.resource missing client_id

**Cause:** State-watcher not deployed in client cluster

**Solution 1 - Check if it exists:**
```bash
kubectl get pods -A | grep state
```

**Solution 2 - Deploy it:**
State-watcher should be part of your client-light Helm chart. If not:
1. Add it to the chart templates
2. Or deploy it separately with kubectl
3. Make sure it has CLIENT_ID environment variable set

### No messages in topics at all

**Check Vector/event-exporter logs in client cluster:**
```bash
kubectl logs -f <vector-pod> -n observability
kubectl logs -f <event-exporter-pod> -n observability
```

## Architecture Summary

```
┌─────────────────────────────────────────┐
│       Client K8s Cluster (af-3)         │
├─────────────────────────────────────────┤
│                                         │
│  Vector DaemonSet                       │
│  ├─ Adds client_id: af-3               │
│  └─> logs.normalized                   │
│                                         │
│  Event-Exporter                         │
│  ├─ Adds client_id: af-3               │
│  └─> events.normalized                 │
│                                         │
│  State-Watcher                          │
│  ├─ Adds client_id: af-3               │
│  ├─> state.k8s.resource                │
│  └─> state.k8s.topology                │
│                                         │
└─────────────────────────────────────────┘
                 │
                 ▼
        ┌────────────────┐
        │  Kafka Server  │
        └────────────────┘
                 │
    ┌────────────┴────────────┐
    ▼                         ▼
┌─────────────┐     ┌─────────────────┐
│ graph-      │     │ graph-builder-  │
│ builder     │     │ af-3            │
│ (all msgs)  │     │ (CLIENT_ID=af-3)│
│             │     │ (filters msgs)  │
└─────────────┘     └─────────────────┘
```

## Next Steps After Setup

1. **Monitor consumer lag:**
   ```bash
   docker exec kg-kafka kafka-consumer-groups.sh \
     --bootstrap-server localhost:9092 \
     --describe --group kg-builder-af-3
   ```

2. **Check Neo4j for client-specific data:**
   ```cypher
   MATCH (r:Resource {client_id: "af-3"}) RETURN count(r)
   ```

3. **Add more clients:**
   - Deploy client-light Helm chart with new client.id
   - Run discover-client-ids.sh
   - Run generate-multi-client-compose.sh
   - Deploy new graph-builder instances
