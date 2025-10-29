# KGRoot RCA API

Intelligent Root Cause Analysis API powered by GPT-5, Neo4j, and Semantic Search.

## Features

- 🧠 **GPT-5 Powered RCA**: Natural language analysis with reasoning effort control
- 🔍 **Semantic Search**: Find events and resources using natural language
- 📊 **Resource Catalog**: Browse infrastructure with metadata, ownership, and dependencies
- 🏥 **Real-time Health**: Monitor cluster health and active incidents
- 💬 **AI Assistant**: Chat with an SRE expert about your infrastructure
- 📢 **Slack Integration**: Automated alerts and health reports
- 🔒 **Multi-tenant Safe**: Complete client isolation at every layer

## Quick Start

### Prerequisites

- Python 3.9+
- Neo4j 5.x with APOC plugin
- OpenAI API key (GPT-5 access)
- Slack workspace (optional)

### Installation

1. **Clone and navigate to the directory:**
   ```bash
   cd mini-server-prod/kgroot-services/rca-api
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

5. **Run the API:**
   ```bash
   uvicorn src.main:app --reload --host 0.0.0.0 --port 8083
   ```

6. **Access API docs:**
   - Swagger UI: http://localhost:8083/docs
   - ReDoc: http://localhost:8083/redoc

## Configuration

Edit `.env` file:

```bash
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# OpenAI (GPT-5)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5
OPENAI_REASONING_EFFORT=medium  # minimal, low, medium, high
OPENAI_VERBOSITY=medium  # low, medium, high

# Slack (Optional)
SLACK_BOT_TOKEN=xoxb-...
SLACK_DEFAULT_CHANNEL=#alerts

# Embedding Model
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_CACHE_DIR=./embeddings_cache

# Redis (Optional - for caching)
REDIS_URL=redis://localhost:6379
```

## API Endpoints

### RCA Analysis

- `POST /rca/analyze` - Perform intelligent RCA analysis
- `GET /rca/root-causes/{client_id}` - Get likely root causes
- `GET /rca/causal-chain/{event_id}` - Get causal chain
- `GET /rca/blast-radius/{event_id}` - Get blast radius
- `GET /rca/cross-service-failures/{client_id}` - Get cross-service failures
- `POST /rca/runbook` - Generate runbook for failure pattern

### Semantic Search

- `POST /search/` - Natural language search
- `POST /search/rebuild-index/{client_id}` - Rebuild search index
- `GET /search/suggestions` - Get search suggestions

### Resource Catalog

- `GET /catalog/resources/{client_id}` - Browse resources with filters
- `GET /catalog/topology/{client_id}/{namespace}/{resource_name}` - Get topology view
- `GET /catalog/owners/{client_id}` - List resource owners
- `GET /catalog/namespaces/{client_id}` - List namespaces with counts

### Health Monitoring

- `GET /health/status/{client_id}` - Get health status
- `POST /health/send-health-report/{client_id}` - Send health report to Slack
- `GET /health/incidents/{client_id}` - Get active incidents

### AI Assistant

- `POST /chat/` - Chat with RCA assistant
- `DELETE /chat/conversations/{conversation_id}` - Clear conversation
- `GET /chat/conversations/{conversation_id}` - Get conversation history

## Usage Examples

### 1. Analyze a Failure

```bash
curl -X POST "http://localhost:8083/rca/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Why did nginx pods fail in the default namespace?",
    "client_id": "ab-01",
    "time_range_hours": 24,
    "reasoning_effort": "medium",
    "include_remediation": true
  }'
```

### 2. Search for Events

```bash
curl -X POST "http://localhost:8083/search/" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "show me all OOM errors in production namespace last 6 hours",
    "client_id": "ab-01",
    "time_range_hours": 6,
    "namespaces": ["production"],
    "limit": 20
  }'
```

### 3. Browse Resource Catalog

```bash
curl -X GET "http://localhost:8083/catalog/resources/ab-01?kinds=Pod&kinds=Deployment&healthy_only=false&page=1&page_size=50"
```

### 4. Check Health Status

```bash
curl -X GET "http://localhost:8083/health/status/ab-01"
```

### 5. Chat with Assistant

```bash
curl -X POST "http://localhost:8083/chat/" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is causing high memory usage in the auth service?",
    "client_id": "ab-01",
    "reasoning_effort": "low"
  }'
```

## Documentation

- [API Reference](docs/API.md) - Complete API documentation
- [Setup Guide](docs/SETUP.md) - Detailed installation and configuration
- [Architecture Guide](docs/ARCHITECTURE.md) - System design and data flow
- [Integration Guide](docs/INTEGRATIONS.md) - Slack and future connectors
- [Examples](docs/EXAMPLES.md) - Real-world usage examples

## Development

### Run Tests

```bash
pytest tests/ -v
```

### Code Formatting

```bash
black src/
isort src/
```

### Type Checking

```bash
mypy src/
```

## Deployment

### Docker

```bash
docker build -t kgroot-rca-api:2.0.0 .
docker run -p 8083:8083 --env-file .env kgroot-rca-api:2.0.0
```

### Kubernetes

```bash
kubectl apply -f k8s/deployment.yaml
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed deployment instructions.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Web UI     │────▶│  FastAPI     │────▶│   Neo4j     │
│  (Future)   │     │  RCA API     │     │   Graph DB  │
└─────────────┘     └──────────────┘     └─────────────┘
                           │                     │
                           │                     │
                           ▼                     ▼
                    ┌──────────────┐     ┌─────────────┐
                    │   GPT-5      │     │  Embeddings │
                    │   Responses  │     │   (FAISS)   │
                    └──────────────┘     └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │    Slack     │
                    │  Integration │
                    └──────────────┘
```

## Multi-Tenant Isolation

All queries and relationships are isolated by `client_id`:
- Neo4j queries filter by `client_id` in nodes and relationships
- Embeddings tagged with `client_id`
- Slack alerts include `client_id` context
- Complete data isolation between clients

## Performance

- **RCA Analysis**: 2-5 seconds (depends on GPT-5 reasoning effort)
- **Semantic Search**: <500ms (with FAISS index)
- **Catalog Browse**: <1 second (with proper Neo4j indexes)
- **Health Status**: <500ms

## Troubleshooting

### Neo4j Connection Failed

```bash
# Check Neo4j is running
docker ps | grep neo4j

# Verify credentials
cypher-shell -u neo4j -p your-password
```

### GPT-5 API Errors

```bash
# Verify API key
echo $OPENAI_API_KEY

# Check model access
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Embedding Index Empty

```bash
# Rebuild index
curl -X POST "http://localhost:8000/search/rebuild-index/ab-01"
```

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## License

MIT License - see LICENSE file for details

## Support

- Documentation: [docs/](docs/)
- Issues: Create GitHub issue
- Slack: #kgroot-support (internal)

---

Built with ❤️ for SREs by the KGRoot team
