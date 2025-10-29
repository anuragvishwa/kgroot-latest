# KGRoot RCA API Setup Guide

Complete installation and configuration guide.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Neo4j Setup](#neo4j-setup)
- [OpenAI GPT-5 Setup](#openai-gpt-5-setup)
- [Slack Integration Setup](#slack-integration-setup)
- [Running the API](#running-the-api)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required

- **Python 3.9 or higher**
  ```bash
  python --version  # Should be 3.9+
  ```

- **Neo4j 5.x** with APOC plugin
  ```bash
  # Check Neo4j version
  cypher-shell --version
  ```

- **OpenAI API Key** with GPT-5 access

### Optional

- **Slack Workspace** (for alerts)
- **Redis** (for caching, improves performance)
- **Docker** (for containerized deployment)

---

## Installation

### Step 1: Clone Repository

```bash
cd mini-server-prod/kgroot-services/rca-api
```

### Step 2: Create Virtual Environment

```bash
# Create venv
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Expected output:**
```
Successfully installed fastapi uvicorn neo4j openai sentence-transformers faiss-cpu slack-sdk ...
```

### Step 4: Verify Installation

```bash
python -c "import fastapi; import neo4j; import openai; print('All dependencies installed!')"
```

---

## Configuration

### Step 1: Create Environment File

```bash
cp .env.example .env
```

### Step 2: Edit .env File

Open `.env` in your editor and configure:

```bash
# ============================================================================
# Neo4j Configuration
# ============================================================================

# Neo4j connection URI (bolt protocol)
NEO4J_URI=bolt://localhost:7687

# Neo4j credentials
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-secure-password-here

# ============================================================================
# OpenAI GPT-5 Configuration
# ============================================================================

# OpenAI API key (get from https://platform.openai.com/api-keys)
OPENAI_API_KEY=sk-proj-...your-key-here...

# Model name (use gpt-5 when available, fallback to gpt-4-turbo)
OPENAI_MODEL=gpt-5

# Default reasoning effort: minimal, low, medium, high
# Higher = more accurate but slower
OPENAI_REASONING_EFFORT=medium

# Default verbosity: low, medium, high
# Higher = more detailed responses
OPENAI_VERBOSITY=medium

# ============================================================================
# Slack Integration (Optional)
# ============================================================================

# Slack Bot Token (starts with xoxb-)
# Get from: https://api.slack.com/apps -> OAuth & Permissions
SLACK_BOT_TOKEN=xoxb-your-bot-token-here

# Default Slack channel for alerts
SLACK_DEFAULT_CHANNEL=#alerts

# Enable/disable Slack integration
SLACK_ENABLED=true

# ============================================================================
# Embedding Service Configuration
# ============================================================================

# Sentence transformer model for embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Directory to cache embeddings
EMBEDDING_CACHE_DIR=./embeddings_cache

# Batch size for embedding generation (reduce if OOM)
EMBEDDING_BATCH_SIZE=32

# ============================================================================
# Redis Configuration (Optional - for caching)
# ============================================================================

# Redis connection URL
REDIS_URL=redis://localhost:6379

# Enable/disable Redis caching
REDIS_ENABLED=false

# Cache TTL in seconds
REDIS_CACHE_TTL=3600

# ============================================================================
# API Configuration
# ============================================================================

# API host
API_HOST=0.0.0.0

# API port
API_PORT=8000

# Enable debug mode (detailed error messages)
DEBUG=true

# CORS origins (comma-separated)
CORS_ORIGINS=http://localhost:3000,http://localhost:8080

# ============================================================================
# Logging Configuration
# ============================================================================

# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# Log file path
LOG_FILE=./logs/rca-api.log
```

### Step 3: Create Required Directories

```bash
mkdir -p embeddings_cache logs
```

---

## Neo4j Setup

### Option 1: Existing Neo4j Instance

If you already have Neo4j running with KGRoot data:

1. **Verify APOC plugin is installed:**
   ```cypher
   RETURN apoc.version()
   ```

2. **Verify data exists:**
   ```cypher
   MATCH (e:Episodic)
   RETURN count(e) as event_count
   ```

3. **Verify topology exists:**
   ```cypher
   MATCH ()-[r:SELECTS|RUNS_ON|CONTROLS]->()
   RETURN count(r) as topology_count
   ```

4. **Create required indexes:**
   ```cypher
   // Episodic event indexes
   CREATE INDEX episodic_client_time IF NOT EXISTS
   FOR (e:Episodic) ON (e.client_id, e.event_time);

   CREATE INDEX episodic_client_eid IF NOT EXISTS
   FOR (e:Episodic) ON (e.client_id, e.eid);

   // Resource indexes
   CREATE INDEX resource_client_kind IF NOT EXISTS
   FOR (r:Resource) ON (r.client_id, r.kind);

   CREATE INDEX resource_client_kind_ns IF NOT EXISTS
   FOR (r:Resource) ON (r.client_id, r.kind, r.ns);

   // Relationship indexes
   CREATE INDEX rel_potential_cause_client IF NOT EXISTS
   FOR ()-[r:POTENTIAL_CAUSE]-() ON (r.client_id);

   CREATE INDEX rel_topology_client IF NOT EXISTS
   FOR ()-[r:SELECTS]-() ON (r.client_id);
   ```

### Option 2: New Neo4j Instance

1. **Install Neo4j Desktop or Docker:**

   **Docker (Recommended):**
   ```bash
   docker run -d \
     --name neo4j \
     -p 7474:7474 -p 7687:7687 \
     -e NEO4J_AUTH=neo4j/your-password \
     -e NEO4J_PLUGINS='["apoc"]' \
     -e NEO4J_apoc_export_file_enabled=true \
     -e NEO4J_apoc_import_file_enabled=true \
     neo4j:5.15
   ```

   **Neo4j Desktop:**
   - Download from https://neo4j.com/download/
   - Create new database
   - Install APOC plugin from plugins tab

2. **Access Neo4j Browser:**
   ```
   http://localhost:7474
   ```

3. **Set up topology and causal relationships:**

   Follow the guides in `mini-server-prod/kgroot-services/`:
   - `COMPLETE-RCA-SYSTEM-GUIDE.md`
   - Run `CREATE-TOPOLOGY-SINGLE-CLIENT.cypher`
   - Run `CREATE-CAUSAL-RELATIONSHIPS-ENHANCED.cypher`

---

## OpenAI GPT-5 Setup

### Step 1: Get API Key

1. Go to https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Copy the key (starts with `sk-proj-` or `sk-`)
4. Add to `.env`:
   ```bash
   OPENAI_API_KEY=sk-proj-your-key-here
   ```

### Step 2: Verify GPT-5 Access

```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | grep gpt-5
```

**If GPT-5 not available:**
- Update `.env` to use GPT-4 Turbo as fallback:
  ```bash
  OPENAI_MODEL=gpt-4-turbo
  ```

### Step 3: Set Reasoning Defaults

Configure default reasoning effort in `.env`:

```bash
# For production (balanced)
OPENAI_REASONING_EFFORT=medium

# For development (faster)
OPENAI_REASONING_EFFORT=low

# For critical analysis (most accurate)
OPENAI_REASONING_EFFORT=high
```

---

## Slack Integration Setup

### Step 1: Create Slack App

1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name: "KGRoot RCA Bot"
4. Select your workspace

### Step 2: Configure Bot Permissions

1. Go to "OAuth & Permissions"
2. Add Bot Token Scopes:
   - `chat:write` - Send messages
   - `chat:write.public` - Send to public channels
   - `channels:read` - Read channel info
   - `users:read` - Read user info (for mentions)

### Step 3: Install App to Workspace

1. Click "Install to Workspace"
2. Authorize the app
3. Copy "Bot User OAuth Token" (starts with `xoxb-`)
4. Add to `.env`:
   ```bash
   SLACK_BOT_TOKEN=xoxb-your-token-here
   ```

### Step 4: Invite Bot to Channel

```
/invite @KGRoot RCA Bot
```

### Step 5: Set Default Channel

In `.env`:
```bash
SLACK_DEFAULT_CHANNEL=#alerts
```

### Step 6: Test Integration

```bash
# After starting API
curl -X POST "http://localhost:8083/health/send-health-report/ab-01"
```

---

## Running the API

### Development Mode

```bash
# Activate virtual environment
source venv/bin/activate

# Run with hot reload
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Will watch for changes in these directories: ['/path/to/rca-api']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using StatReload
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Connecting to Neo4j...
INFO:     Neo4j connected successfully
INFO:     Initializing embedding service...
INFO:     Embedding service initialized with model: sentence-transformers/all-MiniLM-L6-v2
INFO:     Initializing GPT-5 service...
INFO:     GPT-5 service initialized successfully
INFO:     Initializing Slack service...
INFO:     Slack service initialized successfully
INFO:     Building initial embedding index...
INFO:     Indexed 12450 events and 523 resources
INFO:     Application startup complete.
```

### Production Mode

```bash
# Run with multiple workers
uvicorn src.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info \
  --access-log
```

### Background Service (systemd)

Create `/etc/systemd/system/kgroot-rca-api.service`:

```ini
[Unit]
Description=KGRoot RCA API
After=network.target

[Service]
Type=simple
User=kgroot
WorkingDirectory=/path/to/rca-api
Environment="PATH=/path/to/rca-api/venv/bin"
ExecStart=/path/to/rca-api/venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable kgroot-rca-api
sudo systemctl start kgroot-rca-api
sudo systemctl status kgroot-rca-api
```

---

## Verification

### Step 1: Check API Health

```bash
curl http://localhost:8083/
```

**Expected response:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "services": {
    "neo4j": "connected",
    "gpt5": "initialized",
    "embeddings": "ready",
    "slack": "connected"
  }
}
```

### Step 2: Test RCA Analysis

```bash
curl -X POST "http://localhost:8083/rca/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What failures happened in the last hour?",
    "client_id": "ab-01",
    "time_range_hours": 1
  }'
```

### Step 3: Test Semantic Search

```bash
curl -X POST "http://localhost:8083/search/" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "show me OOM errors",
    "client_id": "ab-01",
    "limit": 5
  }'
```

### Step 4: Check Swagger UI

Open browser: http://localhost:8083/docs

You should see interactive API documentation.

### Step 5: Verify Logs

```bash
tail -f logs/rca-api.log
```

---

## Troubleshooting

### Issue 1: Neo4j Connection Failed

**Error:**
```
ERROR: Neo4j connection failed: Unable to connect to bolt://localhost:7687
```

**Solutions:**

1. **Check Neo4j is running:**
   ```bash
   # Docker
   docker ps | grep neo4j

   # Service
   sudo systemctl status neo4j
   ```

2. **Verify credentials:**
   ```bash
   cypher-shell -u neo4j -p your-password
   ```

3. **Check firewall:**
   ```bash
   sudo ufw allow 7687
   ```

4. **Verify URI in .env:**
   ```bash
   NEO4J_URI=bolt://localhost:7687  # Not http://
   ```

---

### Issue 2: GPT-5 API Errors

**Error:**
```
ERROR: GPT-5 service initialization failed: Invalid API key
```

**Solutions:**

1. **Verify API key:**
   ```bash
   curl https://api.openai.com/v1/models \
     -H "Authorization: Bearer $OPENAI_API_KEY"
   ```

2. **Check key format:**
   - Should start with `sk-proj-` or `sk-`
   - No spaces or quotes in .env

3. **Fallback to GPT-4:**
   ```bash
   # In .env
   OPENAI_MODEL=gpt-4-turbo
   ```

4. **Check billing:**
   - https://platform.openai.com/account/billing

---

### Issue 3: Embedding Service Out of Memory

**Error:**
```
RuntimeError: CUDA out of memory
```

**Solutions:**

1. **Use CPU instead of GPU:**
   ```bash
   # In .env
   EMBEDDING_DEVICE=cpu
   ```

2. **Reduce batch size:**
   ```bash
   # In .env
   EMBEDDING_BATCH_SIZE=16  # Default is 32
   ```

3. **Use smaller model:**
   ```bash
   # In .env
   EMBEDDING_MODEL=sentence-transformers/paraphrase-MiniLM-L3-v2
   ```

---

### Issue 4: Slack Integration Not Working

**Error:**
```
ERROR: Slack API error: invalid_auth
```

**Solutions:**

1. **Verify bot token:**
   ```bash
   curl -X POST https://slack.com/api/auth.test \
     -H "Authorization: Bearer $SLACK_BOT_TOKEN"
   ```

2. **Check bot permissions:**
   - Go to https://api.slack.com/apps
   - OAuth & Permissions
   - Ensure `chat:write` is added

3. **Invite bot to channel:**
   ```
   /invite @KGRoot RCA Bot
   ```

4. **Disable Slack temporarily:**
   ```bash
   # In .env
   SLACK_ENABLED=false
   ```

---

### Issue 5: Empty Search Results

**Error:**
```
{"results": [], "total_results": 0}
```

**Solutions:**

1. **Rebuild embedding index:**
   ```bash
   curl -X POST "http://localhost:8083/search/rebuild-index/ab-01"
   ```

2. **Check events exist in Neo4j:**
   ```cypher
   MATCH (e:Episodic {client_id: 'ab-01'})
   RETURN count(e)
   ```

3. **Verify time range:**
   ```bash
   # Try longer time range
   "time_range_hours": 720  # 30 days
   ```

---

### Issue 6: High API Latency

**Symptoms:**
- RCA analysis takes >10 seconds
- Search is slow

**Solutions:**

1. **Enable Redis caching:**
   ```bash
   # In .env
   REDIS_ENABLED=true
   REDIS_URL=redis://localhost:6379
   ```

2. **Reduce GPT-5 reasoning effort:**
   ```bash
   # In request
   "reasoning_effort": "low"
   ```

3. **Add Neo4j indexes** (see Neo4j Setup section)

4. **Limit search results:**
   ```bash
   # In request
   "limit": 10  # Instead of 100
   ```

---

### Issue 7: Port Already in Use

**Error:**
```
ERROR: [Errno 48] Address already in use
```

**Solutions:**

1. **Find process using port:**
   ```bash
   lsof -i :8000
   ```

2. **Kill process:**
   ```bash
   kill -9 <PID>
   ```

3. **Use different port:**
   ```bash
   uvicorn src.main:app --port 8001
   ```

---

## Performance Tuning

### For High Traffic

1. **Increase workers:**
   ```bash
   uvicorn src.main:app --workers 8
   ```

2. **Enable Redis caching:**
   ```bash
   REDIS_ENABLED=true
   ```

3. **Use connection pooling:**
   ```bash
   NEO4J_MAX_CONNECTION_POOL_SIZE=50
   ```

### For Large Datasets

1. **Batch embedding updates:**
   ```bash
   EMBEDDING_BATCH_SIZE=64
   ```

2. **Limit search index size:**
   - Only index recent events (last 30 days)
   - Rebuild index daily via cron

3. **Add more Neo4j indexes:**
   - Index on `event_time`
   - Index on `reason`
   - Index on `namespace`

---

## Next Steps

- [Architecture Guide](ARCHITECTURE.md) - Understand system design
- [API Reference](API.md) - Explore all endpoints
- [Integration Guide](INTEGRATIONS.md) - Add Slack and other connectors
- [Examples](EXAMPLES.md) - Real-world usage examples

---

## Getting Help

- Documentation: [docs/](.)
- Issues: Create GitHub issue
- Slack: #kgroot-support (internal)
