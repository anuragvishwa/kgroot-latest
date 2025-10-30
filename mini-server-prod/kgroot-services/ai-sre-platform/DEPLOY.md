# Deployment Guide - AI SRE Platform

> **Complete guide** for deploying to production

---

## Pre-Deployment Checklist

- [ ] OpenAI API key obtained (with GPT-5 access)
- [ ] Neo4j database with causality data
- [ ] Docker & Docker Compose installed
- [ ] Domain name configured (optional, for SSL)
- [ ] Firewall rules configured

---

## Quick Deploy (5 Minutes)

### Step 1: Configure Environment

```bash
cd /Users/anuragvishwa/Anurag/kgroot_latest/mini-server-prod/kgroot-services/ai-sre-platform

# Create .env from template
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required variables**:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-secure-neo4j-password
OPENAI_API_KEY=sk-your-openai-api-key
LLM_MODEL=gpt-5
```

### Step 2: Test System

```bash
# Install dependencies (if running test locally)
pip install -r requirements.txt python-dotenv

# Run system test
python test_system.py
```

**Expected output**:

```
==========================================================
Test Summary
==========================================================

✓ neo4j: PASSED
✓ tool_registry: PASSED
✓ graph_agent: PASSED
✓ router: PASSED
✓ orchestrator: PASSED

Results: 5/5 tests passed

🎉 All tests passed! System ready to deploy.
```

### Step 3: Deploy with Docker Compose

```bash
# Pull images
docker-compose pull

# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### Step 4: Verify Deployment

```bash
# Health check
curl http://localhost:8084/health

# Test investigation
curl -X POST http://localhost:8084/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Test investigation",
    "tenant_id": "test-01",
    "time_window_hours": 24
  }' | jq .
```

---

## Production Deployment

### Architecture

```
              ┌──────────────┐
              │ Load Balancer│
              │   (Nginx)    │
              └──────┬───────┘
                     │
      ┌──────────────┴──────────────┐
      │                             │
┌─────▼─────┐              ┌────────▼──────┐
│ AI SRE    │              │  AI SRE       │
│ API (1)   │              │  API (2)      │
└─────┬─────┘              └────────┬──────┘
      │                             │
      └──────────────┬──────────────┘
                     │
              ┌──────▼───────┐
              │   Neo4j      │
              │   (Cluster)  │
              └──────────────┘
```

### 1. Production docker-compose.yml

Create `docker-compose.prod.yml`:

```yaml
version: "3.8"

services:
  ai-sre-api:
    image: ai-sre-platform:latest
    deploy:
      replicas: 3
      restart_policy:
        condition: on-failure
        max_attempts: 3
    environment:
      - NEO4J_URI=${NEO4J_URI}
      - NEO4J_USER=${NEO4J_USER}
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LLM_MODEL=${LLM_MODEL:-gpt-5}
      - LOG_LEVEL=INFO
    ports:
      - "8000-8002:8000" # Multiple replicas
    networks:
      - ai-sre-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  ai-sre-network:
    external: true
```

### 2. Nginx Load Balancer

```nginx
# /etc/nginx/sites-available/ai-sre

upstream ai_sre_backend {
    least_conn;  # Load balancing algorithm
    server localhost:8084 max_fails=3 fail_timeout=30s;
    server localhost:8085 max_fails=3 fail_timeout=30s;
    server localhost:8086 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name ai-sre.your-domain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ai-sre.your-domain.com;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/ai-sre.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ai-sre.your-domain.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Logging
    access_log /var/log/nginx/ai-sre-access.log;
    error_log /var/log/nginx/ai-sre-error.log;

    # Proxy settings
    location / {
        proxy_pass http://ai_sre_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }

    # Health check endpoint (direct, no buffering)
    location /health {
        proxy_pass http://ai_sre_backend;
        proxy_buffering off;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/ai-sre /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. SSL Certificate (Let's Encrypt)

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d ai-sre.your-domain.com

# Auto-renewal (cron)
sudo crontab -e
# Add: 0 0 * * * certbot renew --quiet
```

---

## Monitoring & Observability

### 1. Prometheus Metrics

Add to `src/api/main.py`:

```python
from prometheus_client import Counter, Histogram, generate_latest

# Metrics
investigation_counter = Counter('investigations_total', 'Total investigations', ['tenant'])
investigation_latency = Histogram('investigation_latency_seconds', 'Investigation latency')
investigation_cost = Counter('investigation_cost_usd', 'Investigation cost in USD')

# Endpoint
@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

### 2. Prometheus Configuration

```yaml
# prometheus.yml
scrape_configs:
  - job_name: "ai-sre-platform"
    static_configs:
      - targets: ["localhost:8084", "localhost:8085", "localhost:8086"]
    scrape_interval: 15s
```

### 3. Grafana Dashboard

Import dashboard JSON (create separate file for this)

---

## Scaling

### Horizontal Scaling

```bash
# Scale API replicas
docker-compose -f docker-compose.prod.yml up -d --scale ai-sre-api=5
```

### Vertical Scaling

Update docker-compose resource limits:

```yaml
services:
  ai-sre-api:
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 4G
        reservations:
          cpus: "1.0"
          memory: 2G
```

---

## Backup & Disaster Recovery

### 1. Neo4j Backup

```bash
# Backup Neo4j data
docker exec neo4j neo4j-admin backup \
  --from=localhost:6362 \
  --backup-dir=/backups \
  --name=neo4j-$(date +%Y%m%d)

# Copy to safe location
cp /var/lib/neo4j/backups/* /backup/storage/
```

### 2. Configuration Backup

```bash
# Backup .env and configs
tar -czf ai-sre-config-$(date +%Y%m%d).tar.gz \
  .env \
  docker-compose.yml \
  nginx.conf
```

---

## Security Hardening

### 1. API Authentication (Add JWT)

```python
# Add to src/api/main.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    # Implement JWT verification
    if not valid_token(credentials.credentials):
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/api/v1/investigate", dependencies=[Depends(verify_token)])
async def investigate(...):
    ...
```

### 2. Rate Limiting

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/api/v1/investigate")
@limiter.limit("10/minute")
async def investigate(request: Request, ...):
    ...
```

### 3. Firewall Rules

```bash
# Allow only necessary ports
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 22/tcp    # SSH
sudo ufw deny 8084       # Direct API access (only via Nginx)
sudo ufw enable
```

---

## Troubleshooting

### Issue: High Memory Usage

```bash
# Check memory
docker stats

# Increase memory limit
# Edit docker-compose.yml
services:
  ai-sre-api:
    deploy:
      resources:
        limits:
          memory: 4G
```

### Issue: Slow Investigations

**Causes**:

1. Neo4j query slow → Add indexes
2. LLM API timeout → Increase timeout or use faster model
3. Too many agents → Optimize routing

**Solutions**:

```cypher
# Add Neo4j indexes
CREATE INDEX episodic_client_time IF NOT EXISTS
FOR (e:Episodic) ON (e.client_id, e.event_time);
```

### Issue: High Costs

**Optimization**:

1. Use `gpt-4o` instead of `gpt-5` (10x cheaper)
2. Optimize routing (more rules = less LLM)
3. Cache LLM responses

---

## Rollback Procedure

```bash
# Stop current version
docker-compose down

# Restore previous version
docker-compose -f docker-compose.yml.backup up -d

# Verify
curl http://localhost:8000/health
```

---

## Post-Deployment

### 1. Smoke Test

```bash
# Run automated tests
python test_system.py

# Manual test
curl -X POST https://ai-sre.your-domain.com/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{"query": "Smoke test", "tenant_id": "test-01", "time_window_hours": 1}'
```

### 2. Monitor Logs

```bash
# Watch logs for errors
docker-compose logs -f --tail=100

# Check for errors
docker-compose logs | grep ERROR
```

### 3. Load Testing

```bash
# Install locust
pip install locust

# Run load test (create locustfile.py separately)
locust -f locustfile.py --host=https://ai-sre.your-domain.com
```

---

## Maintenance Schedule

| Task                    | Frequency     | Command                              |
| ----------------------- | ------------- | ------------------------------------ |
| **Backup Neo4j**        | Daily         | `./backup-neo4j.sh`                  |
| **Update SSL Cert**     | Every 90 days | `certbot renew`                      |
| **Review logs**         | Daily         | `docker-compose logs`                |
| **Update dependencies** | Monthly       | `pip install -U -r requirements.txt` |
| **Neo4j maintenance**   | Weekly        | Rebuild causality                    |

---

## Support & Monitoring

### Alerts to Set Up

1. **API Down**: Alert if health check fails
2. **High Latency**: Alert if p95 > 10s
3. **High Cost**: Alert if daily cost > $10
4. **Neo4j Down**: Alert if connection fails

### Dashboards

1. **Investigations/hour**
2. **Average latency (p50, p95, p99)**
3. **Cost per investigation**
4. **Success rate**
5. **Agent execution breakdown**

---

## Success Metrics

Track these KPIs:

- **MTTR**: Mean time to resolution
- **Investigation success rate**: % with confidence > 0.8
- **Cost per investigation**: Should be < $0.10
- **API uptime**: Target 99.9%
- **User satisfaction**: Collect feedback

---

**Your AI SRE Platform is now production-ready! 🚀**
