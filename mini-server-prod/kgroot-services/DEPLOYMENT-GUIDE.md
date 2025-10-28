# KGroot RCA - Deployment Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Client's K8s Cluster                         │
│                                                                     │
│  ┌───────────────┐     ┌─────────────┐                            │
│  │  Prometheus   │────▶│ Alertmanager│────┐                        │
│  └───────────────┘     └─────────────┘    │                        │
│                                            │ Webhook                │
│  ┌─────────────────────────────────────┐  │                        │
│  │    K8s Events & Resources           │  │                        │
│  │  (Pods, Nodes, Deployments, etc.)   │  │                        │
│  └─────────────────────────────────────┘  │                        │
│                   │                        │                        │
│                   │ Read-Only Access       │                        │
│                   │ (kubeconfig)           │                        │
└───────────────────┼────────────────────────┼────────────────────────┘
                    │                        │
                    │                        │ HTTP POST
                    │                        │
┌───────────────────┼────────────────────────┼────────────────────────┐
│                   │   Your Server          │                        │
│                   │   (Docker Compose)     │                        │
│                   │                        │                        │
│  ┌────────────────▼───────────────┐  ┌────▼──────────────────────┐ │
│  │  kg-rca-k8s-collector          │  │  kg-rca-webhook           │ │
│  │  - Watches K8s events          │  │  - Receives alerts        │ │
│  │  - Enriches with context       │  │  - Converts to events     │ │
│  └────────────────┬───────────────┘  └────┬──────────────────────┘ │
│                   │                        │                        │
│                   └────────────┬───────────┘                        │
│                                │                                    │
│                   ┌────────────▼───────────────┐                   │
│                   │  RCA Orchestrator          │                   │
│                   │  - Event graph builder     │                   │
│                   │  - Pattern matcher         │                   │
│                   │  - Root cause ranker       │                   │
│                   │  - GPT-5 analysis          │                   │
│                   └────────────┬───────────────┘                   │
│                                │                                    │
│                   ┌────────────▼───────────────┐                   │
│                   │  Neo4j (Pattern Storage)   │                   │
│                   └────────────────────────────┘                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### On Your Server

- [x] Docker & Docker Compose installed
- [x] Ports 8081 (webhook), 7474/7687 (Neo4j) available
- [x] OpenAI API key (for GPT-5 analysis)
- [x] At least 4GB RAM, 2 CPU cores

### From Client

- [x] Read-only kubeconfig file (see CLIENT-SETUP-GUIDE.md)
- [x] Alertmanager webhook configured (optional)

---

## Deployment Options

### Option 1: Alertmanager Webhook Only (Recommended for MVP)

**Pros:**
- ✅ No kubeconfig needed
- ✅ Works with existing Prometheus/Alertmanager
- ✅ Less intrusive
- ✅ Easier to set up

**Cons:**
- ⚠️ Only sees alerts, not raw K8s events
- ⚠️ Limited context enrichment

### Option 2: K8s Event Collector (Full Access)

**Pros:**
- ✅ Complete event visibility
- ✅ Better context enrichment
- ✅ More accurate RCA

**Cons:**
- ⚠️ Requires kubeconfig from client
- ⚠️ More complex setup

### Option 3: Both (Maximum Accuracy)

**Pros:**
- ✅ Best of both worlds
- ✅ Highest RCA accuracy

**Cons:**
- ⚠️ Most complex setup

---

## Step-by-Step Deployment

### Step 1: Clone and Setup

```bash
cd ~/kgroot-latest/mini-server-prod
git checkout feature/kgroot-implementation
git pull origin feature/kgroot-implementation

cd kgroot-services
```

### Step 2: Configure OpenAI API

```bash
# Copy example config
cp config.yaml.example config.yaml

# Edit with your API key
nano config.yaml
```

Update the OpenAI section:
```yaml
openai:
  api_key: "sk-your-actual-api-key-here"
  embedding_model: "text-embedding-3-small"
  chat_model: "gpt-5"  # or gpt-4o if no GPT-5 access
  reasoning_effort: "medium"
  verbosity: "medium"
  enable_llm_analysis: true
```

### Step 3: Deploy Option 1 - Webhook Only

This is the simplest setup and recommended for initial deployment.

```bash
cd ~/kgroot-latest/mini-server-prod

# Start services
docker-compose -f docker-compose-control-plane.yml up -d

# Check logs
docker logs -f kg-rca-webhook
```

**Expected output:**
```
KGroot RCA - Alertmanager Webhook Receiver
✓ RCA Orchestrator initialized
✓ Listening for Alertmanager webhooks on port 8081
```

**Test webhook:**
```bash
curl -X POST http://localhost:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "labels": {
        "alertname": "HighErrorRate",
        "severity": "critical",
        "service": "api-gateway",
        "namespace": "production"
      },
      "annotations": {
        "summary": "High error rate detected"
      }
    }]
  }'
```

**Check status:**
```bash
curl http://localhost:8081/status
```

### Step 4: Deploy Option 2 - K8s Event Collector

**Prerequisites:** Client has provided `kgroot-readonly-kubeconfig.yaml`

```bash
# Copy client's kubeconfig
cp /path/to/kgroot-readonly-kubeconfig.yaml ~/kgroot-latest/mini-server-prod/kubeconfig.yaml

# Edit docker-compose-control-plane.yml
nano docker-compose-control-plane.yml
```

Uncomment the `kg-rca-k8s-collector` service:
```yaml
  kg-rca-k8s-collector:
    build: ./kgroot-services
    image: anuragvishwa/kg-rca-k8s-collector:1.0.0
    container_name: kg-rca-k8s-collector
    hostname: kg-rca-k8s-collector
    environment:
      KUBECONFIG_PATH: "/config/kubeconfig.yaml"
      KGROOT_CONFIG: "/app/config.yaml"
      ENABLE_RCA: "true"
      WATCH_NAMESPACES: ""  # Empty = all namespaces
    volumes:
      - ./kgroot-services/config.yaml:/app/config.yaml:ro
      - ./kubeconfig.yaml:/config/kubeconfig.yaml:ro
    networks:
      - kg-network
    restart: unless-stopped
    depends_on:
      - kg-neo4j
    command: ["python", "k8s_event_collector.py"]
```

```bash
# Rebuild and restart
docker-compose -f docker-compose-control-plane.yml up -d --build

# Check logs
docker logs -f kg-rca-k8s-collector
```

**Expected output:**
```
KGroot RCA - Kubernetes Event Collector
✓ Successfully connected to Kubernetes cluster
✓ Cached 150 pods, 5 nodes
✓ Starting event collection...
```

### Step 5: Configure Client's Alertmanager

Send this configuration to your client:

**alertmanager.yml:**
```yaml
route:
  receiver: 'default'
  routes:
    # Add KGroot RCA webhook
    - match:
        severity: critical|warning
      receiver: 'kgroot-webhook'
      continue: true  # Keep sending to other receivers

receivers:
  - name: 'default'
    # Client's existing receivers

  - name: 'kgroot-webhook'
    webhook_configs:
      - url: 'http://YOUR_SERVER_IP:8081/webhook'
        send_resolved: true
        http_config:
          basic_auth:
            username: 'kgroot'
            password: 'your-secure-password'  # Optional
```

Replace `YOUR_SERVER_IP` with your server's public IP.

### Step 6: Verify Integration

```bash
# Check all services are running
docker-compose -f docker-compose-control-plane.yml ps

# Check webhook health
curl http://localhost:8081/health

# Check Neo4j
curl -u neo4j:Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA http://localhost:7474

# View RCA logs
docker logs -f kg-rca-webhook
```

---

## Testing the System

### Test 1: Manual Alert Injection

```bash
# Simulate a pod crash
curl -X POST http://localhost:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [
      {
        "labels": {
          "alertname": "KubePodCrashLooping",
          "severity": "critical",
          "pod": "api-gateway-7d9f8b6c5-abcde",
          "namespace": "production",
          "service": "api-gateway"
        },
        "annotations": {
          "summary": "Pod is crash looping",
          "description": "Pod has restarted 5 times in the last 10 minutes"
        }
      },
      {
        "labels": {
          "alertname": "HighMemoryUsage",
          "severity": "warning",
          "pod": "api-gateway-7d9f8b6c5-abcde",
          "namespace": "production",
          "service": "api-gateway"
        },
        "annotations": {
          "summary": "High memory usage",
          "description": "Memory usage is at 95%"
        }
      },
      {
        "labels": {
          "alertname": "HighErrorRate",
          "severity": "warning",
          "service": "api-gateway",
          "namespace": "production"
        },
        "annotations": {
          "summary": "Error rate spiked",
          "description": "Error rate increased from 1% to 15%"
        }
      }
    ]
  }'
```

**Expected Result:**
```
📥 Received webhook: 3 alerts, status=firing
  Alert: POD_RESTART - api-gateway-7d9f8b6c5-abcde - Pod is crash looping
  Alert: MEMORY_HIGH - api-gateway-7d9f8b6c5-abcde - High memory usage
  Alert: ERROR_RATE_HIGH - api-gateway - Error rate spiked
🔍 Triggering RCA for 3 alerts
🎯 Top Root Causes:
  1. MEMORY_HIGH in api-gateway-7d9f8b6c5-abcde (confidence: 0.92)
     Explanation: Memory pressure likely causing OOM and pod crashes...
  2. POD_RESTART in api-gateway-7d9f8b6c5-abcde (confidence: 0.85)
     Explanation: Pod crash loop detected...
  3. ERROR_RATE_HIGH in api-gateway (confidence: 0.78)
     Explanation: Cascading effect from pod instability...
💡 LLM Insight: Root cause is likely a memory leak in the api-gateway service...
```

### Test 2: K8s Event Watching

If you deployed the K8s event collector:

```bash
# Watch the logs
docker logs -f kg-rca-k8s-collector

# You should see:
📥 Event: POD_RESTART - my-app-xyz - Back-off restarting failed container
📥 Event: MEMORY_HIGH - node-1 - Node is under memory pressure
🔍 Triggering RCA analysis for 5 events
🎯 Top Root Cause: MEMORY_HIGH in node-1 (confidence: 0.89)
```

---

## Monitoring & Maintenance

### View Logs

```bash
# Webhook receiver
docker logs -f kg-rca-webhook

# K8s collector (if deployed)
docker logs -f kg-rca-k8s-collector

# Neo4j
docker logs -f kg-neo4j

# All services
docker-compose -f docker-compose-control-plane.yml logs -f
```

### Check Resource Usage

```bash
# Container stats
docker stats kg-rca-webhook kg-rca-k8s-collector kg-neo4j

# Disk usage
docker system df
```

### Access Neo4j Browser

```
URL: http://localhost:7474
Username: neo4j
Password: Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA
```

Query stored patterns:
```cypher
// View all failure patterns
MATCH (p:FailurePattern)
RETURN p.root_cause_type, p.frequency, p.services
ORDER BY p.frequency DESC
LIMIT 10

// View recent RCA analyses
MATCH (f:FaultPropagationGraph)-[:HAS_EVENT]->(e:Event)
RETURN f.fault_id, e.event_type, e.service, e.timestamp
ORDER BY e.timestamp DESC
LIMIT 20
```

### Restart Services

```bash
# Restart all
docker-compose -f docker-compose-control-plane.yml restart

# Restart specific service
docker restart kg-rca-webhook

# Rebuild after code changes
docker-compose -f docker-compose-control-plane.yml up -d --build
```

---

## Troubleshooting

### Issue: Webhook not receiving alerts

**Check:**
1. Is the service running? `docker ps | grep kg-rca-webhook`
2. Is port 8081 accessible? `curl http://localhost:8081/health`
3. Check client's Alertmanager config
4. Check firewall rules

**Solution:**
```bash
# Test locally first
curl -X POST http://localhost:8081/webhook -d '{"status":"firing","alerts":[]}'

# If that works, problem is network/firewall
```

### Issue: RCA not triggering

**Check:**
```bash
# Check logs
docker logs kg-rca-webhook

# Check config
docker exec kg-rca-webhook cat /app/config.yaml

# Verify OpenAI key
docker exec kg-rca-webhook python -c "import os; print(os.environ.get('KGROOT_CONFIG'))"
```

**Solution:**
- Ensure `ENABLE_RCA=true` in docker-compose
- Verify OpenAI API key is correct
- Check if threshold is reached (default: 3 alerts)

### Issue: K8s collector can't connect

**Check:**
```bash
# Test kubeconfig manually
docker exec -it kg-rca-k8s-collector bash
kubectl --kubeconfig=/config/kubeconfig.yaml get nodes

# If fails, kubeconfig is invalid
```

**Solution:**
- Ask client to regenerate kubeconfig
- Check kubeconfig file permissions
- Verify cluster endpoint is accessible

### Issue: High memory usage

**Check:**
```bash
docker stats kg-rca-webhook
```

**Solution:**
- Reduce buffer size in code
- Restart service periodically
- Increase server resources

### Issue: GPT-5 errors

**Common errors:**
- "Model not found" → Use `gpt-4o` instead
- "Rate limit exceeded" → Reduce reasoning_effort to "minimal"
- "Insufficient quota" → Check OpenAI billing

**Solution:**
```yaml
# In config.yaml
openai:
  chat_model: "gpt-4o"  # Fallback to GPT-4o
  reasoning_effort: "minimal"  # Use less compute
```

---

## Scaling & Optimization

### For High Alert Volume

```yaml
# In docker-compose-control-plane.yml
kg-rca-webhook:
  deploy:
    replicas: 3
    resources:
      limits:
        cpus: '2'
        memory: 2G
```

### For Cost Optimization

```yaml
# In config.yaml
openai:
  chat_model: "gpt-5-mini"  # Cheaper model
  reasoning_effort: "minimal"  # Faster, cheaper
  enable_llm_analysis: false  # Disable for non-critical alerts
```

### For Better Accuracy

```yaml
# In config.yaml
openai:
  chat_model: "gpt-5"
  reasoning_effort: "high"  # More thorough analysis
  verbosity: "high"  # Detailed explanations
```

---

## Production Checklist

- [ ] OpenAI API key configured
- [ ] Client kubeconfig received and tested
- [ ] Alertmanager webhook configured
- [ ] Services running and healthy
- [ ] Neo4j accessible and backed up
- [ ] Logs being monitored
- [ ] Resource limits set
- [ ] Firewall rules configured
- [ ] Backup strategy in place
- [ ] Documentation shared with team

---

## Next Steps

1. **Monitor for 1 week** - Watch logs, verify RCA accuracy
2. **Tune parameters** - Adjust thresholds, time windows
3. **Add more clients** - Repeat process for each client cluster
4. **Build dashboards** - Visualize RCA insights
5. **Automate remediation** - Trigger runbooks based on root causes

---

## Support

For issues or questions:
- Check logs: `docker logs -f kg-rca-webhook`
- Review [TROUBLESHOOTING-PLAYBOOK.md](../docs/TROUBLESHOOTING-PLAYBOOK.md)
- Check [GPT5-SETUP.md](GPT5-SETUP.md) for LLM issues
- Refer to [KGroot paper](https://arxiv.org/abs/2402.13264) for algorithm details

**End of Deployment Guide**
