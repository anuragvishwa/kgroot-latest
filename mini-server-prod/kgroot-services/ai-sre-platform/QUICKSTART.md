# AI SRE Platform - Quick Start Guide

> Get the platform running in **5 minutes**

---

## Prerequisites

- Docker & Docker Compose installed
- OpenAI API key (for GPT-5)
- Neo4j with existing causality data (or use fresh instance)

---

## Option 1: Docker Compose (Recommended)

### Step 1: Clone and Configure

```bash
cd /Users/anuragvishwa/Anurag/kgroot_latest/mini-server-prod/kgroot-services/ai-sre-platform

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

**Required environment variables**:
```bash
NEO4J_PASSWORD=your-neo4j-password
OPENAI_API_KEY=sk-your-openai-key
LLM_MODEL=gpt-5  # or gpt-4o for cheaper option
```

### Step 2: Start Services

```bash
# Production mode
docker-compose up -d

# Development mode (with hot-reload)
docker-compose -f docker-compose.dev.yml up
```

### Step 3: Verify

```bash
# Check health
curl http://localhost:8084/health

# Expected output:
# {
#   "status": "healthy",
#   "neo4j_connected": true,
#   "available_agents": ["GraphAgent"],
#   "available_tools": "Neo4jService"
# }
```

### Step 4: Test Investigation

```bash
curl -X POST http://localhost:8084/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Why did nginx pods fail?",
    "tenant_id": "acme-01",
    "event_type": "OOMKilled",
    "time_window_hours": 24
  }'
```

---

## Option 2: Local Development (Without Docker)

### Step 1: Install Dependencies

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Set Environment Variables

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your-password
export OPENAI_API_KEY=sk-your-key
export LLM_MODEL=gpt-5
```

### Step 3: Run Application

```bash
# Start API server
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 4: Test

```bash
# In another terminal
curl http://localhost:8084/health
```

---

## API Endpoints

### 1. Health Check
```bash
GET /health
```

### 2. Investigate Incident
```bash
POST /api/v1/investigate

Body:
{
  "query": "Why did nginx pods fail?",
  "tenant_id": "acme-01",
  "service": "nginx-api",           # Optional
  "namespace": "production",         # Optional
  "event_type": "OOMKilled",         # Optional (for routing)
  "time_window_hours": 24
}
```

### 3. Get Statistics
```bash
GET /api/v1/stats
```

### 4. API Documentation
```bash
# Interactive docs
http://localhost:8084/docs

# ReDoc
http://localhost:8084/redoc
```

---

## Example Investigation Flow

### 1. OOMKilled Pod Investigation

```bash
curl -X POST http://localhost:8084/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Nginx pod was OOMKilled, what caused it?",
    "tenant_id": "acme-01",
    "event_type": "OOMKilled",
    "service": "nginx-api",
    "namespace": "production",
    "time_window_hours": 2
  }' | jq .
```

**Expected Response**:
```json
{
  "incident_id": "inc-a1b2c3d4",
  "tenant_id": "acme-01",
  "query": "Nginx pod was OOMKilled...",
  "synthesis": {
    "summary": "Nginx pod exceeded memory limits due to traffic spike...",
    "root_causes": [
      {
        "event_id": "evt-123",
        "reason": "OOMKilled",
        "resource": "Pod/nginx-api-7d8f-xyz",
        "confidence": 0.92
      }
    ],
    "blast_radius": {
      "affected_pods": 3,
      "affected_services": ["nginx-api"]
    },
    "immediate_actions": [
      "1. Increase memory limits in deployment",
      "2. Review recent traffic patterns"
    ],
    "confidence": 0.90
  },
  "total_cost_usd": 0.03,
  "total_latency_ms": 2450
}
```

### 2. General Investigation

```bash
curl -X POST http://localhost:8084/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Find all incidents in the last 24 hours",
    "tenant_id": "acme-01",
    "time_window_hours": 24
  }' | jq .synthesis
```

---

## Connecting to Existing Neo4j

If you have existing Neo4j with causality data:

### Option 1: Update docker-compose.yml

```yaml
services:
  ai-sre-api:
    environment:
      - NEO4J_URI=bolt://your-neo4j-host:7687
      - NEO4J_USER=neo4j
      - NEO4J_PASSWORD=your-password
    # Remove depends_on: neo4j if using external Neo4j

  # Remove neo4j service if using external
```

### Option 2: Use .env

```bash
NEO4J_URI=bolt://your-neo4j-host:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
```

---

## Logs and Debugging

### View Logs

```bash
# All services
docker-compose logs -f

# API only
docker-compose logs -f ai-sre-api

# Neo4j only
docker-compose logs -f neo4j
```

### Debug Mode

```bash
# Set log level to DEBUG in .env
LOG_LEVEL=DEBUG

# Restart
docker-compose restart ai-sre-api
```

### Check Neo4j Connection

```bash
# Enter Neo4j container
docker exec -it neo4j cypher-shell -u neo4j -p password

# Run test query
MATCH (e:Episodic) RETURN count(e) as event_count;
```

---

## Troubleshooting

### Issue: "Orchestrator not initialized"

**Solution**: Check OpenAI API key is set correctly

```bash
# Check environment
docker-compose exec ai-sre-api env | grep OPENAI
```

### Issue: "Failed to connect to Neo4j"

**Solution**: Verify Neo4j is running and credentials are correct

```bash
# Test Neo4j connection
docker exec -it neo4j cypher-shell -u neo4j -p password

# Check Neo4j logs
docker-compose logs neo4j
```

### Issue: "No events found"

**Solution**: Make sure Neo4j has Episodic nodes with client_id

```cypher
# Check data exists
MATCH (e:Episodic)
RETURN DISTINCT e.client_id as client_id, count(e) as event_count
LIMIT 10;
```

---

## Production Deployment

### 1. Use Production Docker Compose

```bash
docker-compose up -d
```

### 2. Configure Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name ai-sre.your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3. Set Up SSL (Let's Encrypt)

```bash
certbot --nginx -d ai-sre.your-domain.com
```

### 4. Configure Monitoring

```bash
# Add Prometheus metrics endpoint
curl http://localhost:8084/metrics
```

---

## Next Steps

1. **Test with Real Data**: Use your existing Neo4j causality data
2. **Add More Agents**: See [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md) Phase 3
3. **Configure Alerts**: Set up Prometheus alerts for failures
4. **Scale**: Add more API replicas with load balancer

---

## Cost Monitoring

### Track API Costs

```bash
# Get stats
curl http://localhost:8084/api/v1/stats

# Each investigation shows cost
"total_cost_usd": 0.03  # ~3 cents per investigation
```

### Typical Costs (GPT-5)

- Simple investigation: **$0.02-0.05**
- Complex investigation: **$0.10-0.20**
- Monthly (100 investigations/day): **$150-300/month**

---

## Support

- **Documentation**: [README.md](./README.md)
- **Architecture**: [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Issues**: GitHub Issues

---

**You're ready to go! Start investigating with AI 🚀**
