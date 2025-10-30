# Deploy with Existing Neo4j

> Use this guide when Neo4j is already running on your server

---

## Quick Deploy (2 Minutes)

Your server already has Neo4j running on ports 7474 and 7687. This guide shows how to deploy the AI SRE Platform to use your existing Neo4j instance.

---

## Step 1: Stop the Failed Containers

```bash
cd ~/kgroot-latest/mini-server-prod/kgroot-services/ai-sre-platform

# Clean up the failed deployment
docker-compose down
```

---

## Step 2: Configure Environment

```bash
# Create .env file
nano .env
```

**Add these variables:**
```bash
# Neo4j (your existing instance)
NEO4J_PASSWORD=your-actual-neo4j-password
NEO4J_USER=neo4j

# OpenAI
OPENAI_API_KEY=your-openai-api-key

# Model
LLM_MODEL=gpt-5
```

**Save and exit** (Ctrl+X, Y, Enter)

---

## Step 3: Deploy Using Production Config

```bash
# Use docker-compose.prod.yml (connects to existing Neo4j)
docker compose -f docker-compose.prod.yml up -d
```

**Expected output:**
```
[+] Building...
[+] Running 1/1
 ✔ Container ai-sre-api  Started
```

---

## Step 4: Check Status

```bash
# Check container is running
docker ps | grep ai-sre-api

# View logs
docker logs ai-sre-api -f
```

**Expected logs:**
```
=== Starting AI SRE Platform ===
Connecting to Neo4j at bolt://172.17.0.1:7687...
✓ Neo4j connected
Initializing orchestrator with model=gpt-5...
✓ GraphAgent initialized with 4 tools
✓ Router initialized with 25 event patterns
=== AI SRE Platform ready ===
```

---

## Step 5: Verify Deployment

```bash
# Health check
curl http://localhost:8084/health

# Expected response:
{
  "status": "healthy",
  "neo4j_connected": true,
  "available_agents": ["GraphAgent"],
  "available_tools": "Neo4jService"
}
```

---

## Step 6: Test Investigation

```bash
curl -X POST http://localhost:8084/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Find any incidents in the last 24 hours",
    "tenant_id": "test-01",
    "time_window_hours": 24
  }' | jq .
```

---

## Understanding the Network Configuration

### Why 172.17.0.1:7687?

- Your existing Neo4j is running on the **host** (outside Docker)
- `172.17.0.1` is the **default Docker bridge gateway** - allows containers to reach host services
- Port `7687` is Neo4j's Bolt protocol port

### Alternative: Use Host Network

If `172.17.0.1` doesn't work, you can use host networking:

Edit `docker-compose.prod.yml`:
```yaml
services:
  ai-sre-api:
    network_mode: "host"  # Use host network
    ports: []  # Remove ports mapping when using host network
    environment:
      - NEO4J_URI=bolt://localhost:7687  # Now localhost works!
```

Then deploy:
```bash
docker compose -f docker-compose.prod.yml up -d
```

Access API at: `http://localhost:8084`

---

## Troubleshooting

### Issue: "Neo4j connection failed"

**Check Neo4j is accessible:**
```bash
# From host
docker exec kg-neo4j cypher-shell -u neo4j -p <password> "RETURN 1"

# Check Neo4j container network
docker inspect kg-neo4j | grep IPAddress
```

**Option 1: Use Neo4j's Docker IP directly**
```bash
# Get Neo4j container IP
NEO4J_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' kg-neo4j)
echo $NEO4J_IP  # e.g., 172.17.0.2

# Update .env
NEO4J_URI=bolt://172.17.0.2:7687
```

**Option 2: Connect both containers to same network**
```bash
# Get Neo4j's network
docker inspect kg-neo4j | grep NetworkMode

# Join that network
docker-compose.prod.yml:
  ai-sre-api:
    networks:
      - bridge  # Or whatever network kg-neo4j is on
    environment:
      - NEO4J_URI=bolt://kg-neo4j:7687  # Use container name
```

**Option 3: Use host.docker.internal (Linux)**
```bash
# In docker-compose.prod.yml
environment:
  - NEO4J_URI=bolt://host.docker.internal:7687
```

### Issue: "Port 8084 already in use"

```bash
# Check what's using port 8084
sudo lsof -i :8084

# Change to different port in docker-compose.prod.yml
ports:
  - "8085:8000"  # Use 8085 instead
```

### Issue: "OpenAI API error"

```bash
# Verify API key is set
docker exec ai-sre-api env | grep OPENAI_API_KEY

# If empty, check .env file
cat .env | grep OPENAI_API_KEY

# Restart container to reload env
docker restart ai-sre-api
```

---

## Verify Neo4j Connection

```bash
# Test Neo4j from inside container
docker exec -it ai-sre-api python3 -c "
from neo4j import GraphDatabase
import os
uri = os.getenv('NEO4J_URI', 'bolt://172.17.0.1:7687')
user = os.getenv('NEO4J_USER', 'neo4j')
password = os.getenv('NEO4J_PASSWORD')
driver = GraphDatabase.driver(uri, auth=(user, password))
driver.verify_connectivity()
print('✓ Neo4j connection successful!')
driver.close()
"
```

---

## Current Server Setup

Based on your `docker ps` output:

```
Container Name       | Port         | Purpose
---------------------|--------------|------------------
kg-neo4j             | 7474, 7687   | Neo4j (existing)
kg-rca-api           | 8082         | Current RCA v1
kg-rca-api-v2        | 8083         | Current RCA v2
kg-control-plane     | 9090         | Control plane
kg-alert-receiver    | 8080         | Alerts
kg-rca-webhook       | 8081         | Webhooks
kg-kafka             | 9092         | Kafka
kg-alertmanager      | 9093         | Alertmanager
kg-kafka-ui          | 7777         | Kafka UI
ai-sre-api (NEW)     | 8084         | AI SRE Platform ✨
```

**No conflicts!** Port 8084 is available.

---

## Production Checklist

- [ ] Neo4j connection verified
- [ ] OpenAI API key configured
- [ ] Container running on port 8084
- [ ] Health check returns "healthy"
- [ ] Test investigation succeeds
- [ ] Logs show no errors

---

## Managing the Service

### View Logs
```bash
docker logs ai-sre-api -f
```

### Restart Service
```bash
docker restart ai-sre-api
```

### Stop Service
```bash
docker stop ai-sre-api
```

### Update Configuration
```bash
# Edit .env
nano .env

# Restart to apply changes
docker restart ai-sre-api
```

### Rebuild and Redeploy
```bash
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Next Steps

Once deployed and verified:

1. **Test with Real Data**
   ```bash
   curl -X POST http://localhost:8084/api/v1/investigate \
     -H "Content-Type: application/json" \
     -d '{
       "query": "Why did service X fail?",
       "tenant_id": "your-actual-tenant-id",
       "event_type": "OOMKilled",
       "time_window_hours": 24
     }'
   ```

2. **Monitor Costs**
   ```bash
   curl http://localhost:8084/api/v1/stats
   ```

3. **Check Router Statistics**
   ```bash
   curl http://localhost:8084/api/v1/stats | jq .router
   ```

4. **Add Custom Patterns** (see READY_TO_DEPLOY.md)

---

## API Documentation

Once running, access interactive docs:
- Swagger UI: http://your-server:8084/docs
- ReDoc: http://your-server:8084/redoc

---

## Success!

Your AI SRE Platform is now running on **port 8084** and connected to your existing Neo4j instance on **ports 7474/7687**.

**Quick Command Reference:**
```bash
# Health check
curl http://localhost:8084/health

# View logs
docker logs ai-sre-api -f

# Restart
docker restart ai-sre-api

# Stats
curl http://localhost:8084/api/v1/stats
```

🚀 **Ready for production RCA investigations!**
