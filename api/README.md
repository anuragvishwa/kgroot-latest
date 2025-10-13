# Knowledge Graph RCA API

Production-ready TypeScript API for Root Cause Analysis, Semantic Search, and Graph Queries.

## 🚀 Features

- **Root Cause Analysis (RCA)**: Advanced RCA with confidence scoring and causal chains
- **Semantic Search**: Natural language search across events and incidents
- **Graph Queries**: Query resource topology, relationships, and event history
- **Incident Management**: Track, update, and get recommendations for incidents
- **Resource Health**: Monitor resource health scores and status
- **Real-time Updates**: Incremental graph updates via API
- **Production Ready**: Rate limiting, authentication, error handling, and logging
- **API Documentation**: Auto-generated Swagger/OpenAPI documentation

## 📋 Prerequisites

- Node.js >= 20.0.0
- Neo4j Database >= 5.0
- TypeScript >= 5.0

## 🛠️ Installation

```bash
cd api
npm install
```

## ⚙️ Configuration

Copy the example environment file and configure:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Server
PORT=3000
NODE_ENV=development

# Neo4j
NEO4J_URI=neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# Authentication (optional)
AUTH_ENABLED=false
API_KEYS=your-api-key-1,your-api-key-2

# Logging
LOG_LEVEL=info
```

## 🏃 Running the API

### Development Mode

```bash
npm run dev
```

### Production Build

```bash
npm run build
npm start
```

### Using tsx (faster development)

```bash
npm run start:dev
```

## 📚 API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:3000/docs
- **Health Check**: http://localhost:3000/healthz
- **API Root**: http://localhost:3000/

## 🔗 API Endpoints

### Root Cause Analysis

```bash
# Perform RCA for an event
POST /api/v1/rca
{
  "event_id": "evt-abc123",
  "min_confidence": 0.6,
  "max_hops": 3
}

# Get RCA by event ID
GET /api/v1/rca/:event_id

# Get RCA for a resource
POST /api/v1/rca/resource
{
  "resource_uid": "pod-uid-123",
  "time_window_hours": 24
}

# Bulk RCA
POST /api/v1/rca/bulk
{
  "event_ids": ["evt-1", "evt-2", "evt-3"]
}
```

### Search

```bash
# Semantic search
POST /api/v1/search/semantic
{
  "query": "memory leak causing crashes",
  "top_k": 10,
  "filters": {
    "severity": ["ERROR", "FATAL"],
    "namespace": ["production"]
  }
}

# Causal search
POST /api/v1/search/causal
{
  "query": "What caused the service outage",
  "max_chain_length": 5
}

# Find similar events
POST /api/v1/search/similar
{
  "event_id": "evt-abc123",
  "top_k": 10
}
```

### Graph Queries

```bash
# Get graph statistics
GET /api/v1/graph/stats

# Get resource topology
GET /api/v1/graph/topology/:uid?depth=2

# Get resource events
GET /api/v1/graph/events/:uid?severity=ERROR,FATAL&limit=100

# Get system timeline
GET /api/v1/graph/timeline?start_time=2025-01-01T00:00:00Z&end_time=2025-01-02T00:00:00Z

# Apply graph updates
POST /api/v1/graph/updates
{
  "timestamp": "2025-01-01T00:00:00Z",
  "resources": [
    {
      "action": "UPDATE",
      "kind": "Pod",
      "uid": "pod-123",
      "name": "my-pod",
      "namespace": "default"
    }
  ]
}
```

### Incidents

```bash
# List incidents
GET /api/v1/incidents?status=open&severity=FATAL&page=1&page_size=20

# Get incident details
GET /api/v1/incidents/:incident_id

# Update incident
PATCH /api/v1/incidents/:incident_id
{
  "status": "acknowledged",
  "assignee": "engineer@example.com",
  "notes": "Investigating memory leak"
}

# Get recommendations
GET /api/v1/incidents/:incident_id/recommendations
```

### Resources

```bash
# List resources
GET /api/v1/resources?kind=Pod&namespace=production&page=1

# Get resource details
GET /api/v1/resources/:resource_uid

# Get resource health
GET /api/v1/resources/:resource_uid/health
```

### Health & Metrics

```bash
# Health check
GET /healthz

# Readiness check
GET /readyz

# Prometheus metrics
GET /metrics
```

## 🔒 Authentication

Enable authentication by setting:

```bash
AUTH_ENABLED=true
API_KEYS=key1,key2,key3
```

Include the API key in requests:

```bash
curl -H "X-API-Key: your-api-key" http://localhost:3000/api/v1/rca
```

## 📊 Response Format

### Success Response

```json
{
  "event_id": "evt-123",
  "reason": "OOMKilled",
  "severity": "FATAL",
  "potential_causes": [...]
}
```

### Error Response

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Event 'evt-123' not found",
    "details": {},
    "timestamp": "2025-01-01T00:00:00Z"
  }
}
```

### Error Codes

- `RESOURCE_NOT_FOUND` (404) - Resource not found
- `VALIDATION_ERROR` (400) - Invalid request parameters
- `UNAUTHORIZED` (401) - Authentication required
- `FORBIDDEN` (403) - Insufficient permissions
- `RATE_LIMIT_EXCEEDED` (429) - Too many requests
- `INTERNAL_ERROR` (500) - Server error
- `SERVICE_UNAVAILABLE` (503) - Service unavailable

## 🔧 Development

### Project Structure

```
api/
├── src/
│   ├── config/          # Configuration and database
│   ├── middleware/      # Express/Fastify middleware
│   ├── models/          # Data models
│   ├── routes/          # API routes
│   ├── services/        # Business logic
│   ├── types/           # TypeScript types
│   ├── utils/           # Utilities (logger, errors)
│   └── server.ts        # Main server file
├── tests/               # Test files
├── .env.example         # Environment template
├── package.json
├── tsconfig.json
└── README.md
```

### Available Scripts

```bash
npm run dev          # Start development server with watch
npm run build        # Build for production
npm start            # Start production server
npm run start:dev    # Start with tsx (faster)
npm test             # Run tests
npm run lint         # Lint code
npm run format       # Format code
```

### Adding New Endpoints

1. Create service in `src/services/`
2. Create route in `src/routes/`
3. Register route in `src/routes/index.ts`
4. Add types in `src/types/index.ts`

Example:

```typescript
// src/services/my.service.ts
export class MyService {
  async doSomething(id: string) {
    // Implementation
  }
}

// src/routes/my.routes.ts
export async function myRoutes(fastify: FastifyInstance) {
  fastify.get('/my/:id', async (request, reply) => {
    const { id } = request.params;
    const result = await myService.doSomething(id);
    return reply.send(result);
  });
}

// src/routes/index.ts
import { myRoutes } from './my.routes';
await fastify.register(myRoutes);
```

## 🐳 Docker

Build and run with Docker:

```bash
docker build -t kg-rca-api .
docker run -p 3000:3000 --env-file .env kg-rca-api
```

## 🧪 Testing

```bash
# Run all tests
npm test

# Run with coverage
npm test -- --coverage

# Run specific test
npm test -- my.test.ts
```

## 📈 Performance

- **Rate Limiting**: 1000 requests/minute (configurable)
- **Connection Pooling**: Neo4j connection pool (max 50)
- **Response Times**:
  - Simple queries: < 50ms
  - RCA queries: < 200ms
  - Complex searches: < 500ms

## 🔍 Monitoring

The API exposes Prometheus metrics at `/metrics`:

```
# Resource counts
kg_resources_total
kg_resources_by_kind{kind="Pod"}

# Event counts
kg_events_total
kg_events_by_severity{severity="ERROR"}

# Incident counts
kg_incidents_total
kg_incidents_by_status{status="open"}

# Service uptime
kg_uptime_seconds
```

## 🚨 Troubleshooting

### Connection Issues

```bash
# Check Neo4j connectivity
curl http://localhost:3000/readyz

# View logs
tail -f logs/api.log
```

### Common Errors

**"Failed to connect to Neo4j"**
- Verify Neo4j is running: `docker ps | grep neo4j`
- Check NEO4J_URI in .env
- Verify credentials

**"Rate limit exceeded"**
- Increase rate limit in config
- Use API key for higher limits

**"Event not found"**
- Verify event_id exists in database
- Check event ingestion pipeline

## 📝 API Examples

### Complete RCA Example

```javascript
const axios = require('axios');

async function performRCA(eventId) {
  const response = await axios.post('http://localhost:3000/api/v1/rca', {
    event_id: eventId,
    time_window_minutes: 15,
    max_hops: 3,
    min_confidence: 0.5,
    include_blast_radius: true,
    include_timeline: true
  });

  const rca = response.data;

  console.log(`Event: ${rca.reason}`);
  console.log(`Potential Causes: ${rca.potential_causes.length}`);

  rca.potential_causes.forEach(cause => {
    console.log(`- ${cause.reason} (confidence: ${cause.confidence})`);
  });

  if (rca.recommendation) {
    console.log(`\nRecommendation: ${rca.recommendation.action}`);
  }
}

performRCA('evt-abc123');
```

### Search Example

```javascript
async function searchIssues(query) {
  const response = await axios.post('http://localhost:3000/api/v1/search/semantic', {
    query: query,
    top_k: 5,
    filters: {
      severity: ['ERROR', 'FATAL'],
      namespace: ['production']
    }
  });

  const results = response.data.results;

  results.forEach(result => {
    console.log(`${result.event_id}: ${result.reason}`);
    console.log(`  Similarity: ${result.similarity}`);
    console.log(`  Resource: ${result.subject.kind}/${result.subject.name}`);
  });
}

searchIssues('memory leak causing crashes');
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 License

MIT

## 🆘 Support

- Documentation: [production/api-docs/API_REFERENCE.md](../production/api-docs/API_REFERENCE.md)
- Issues: GitHub Issues
- Email: support@example.com

## 🎯 Roadmap

- [ ] Vector search with embeddings
- [ ] Real-time WebSocket support
- [ ] GraphQL API
- [ ] Multi-tenancy support
- [ ] Advanced caching with Redis
- [ ] Kafka integration for events
- [ ] Machine learning recommendations

---

Built with ❤️ for Production RCA and Observability
