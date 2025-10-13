# KG RCA API - Complete Implementation Documentation

## 📋 Overview

A production-ready TypeScript API implementation for the Knowledge Graph Root Cause Analysis system. Built with Fastify, Neo4j, and comprehensive error handling, logging, and documentation.

## 🏗️ Architecture

### Technology Stack

- **Framework**: Fastify 5.5.0 (High-performance Node.js web framework)
- **Language**: TypeScript 5.9.2 (Strict mode enabled)
- **Database**: Neo4j 5.28.1 (Graph database)
- **Logger**: Pino (High-performance logging)
- **API Documentation**: Swagger/OpenAPI 3.0
- **Security**: Helmet, CORS, Rate Limiting, API Key Auth
- **Runtime**: Node.js 20+

### Directory Structure

```
api/
├── src/
│   ├── config/
│   │   ├── database.ts          # Neo4j connection management
│   │   └── index.ts              # Application configuration
│   ├── middleware/
│   │   ├── auth.middleware.ts    # API key authentication
│   │   ├── error.middleware.ts   # Global error handler
│   │   └── logging.middleware.ts # Request logging
│   ├── routes/
│   │   ├── index.ts              # Route registration
│   │   ├── rca.routes.ts         # RCA endpoints
│   │   ├── search.routes.ts      # Search endpoints
│   │   ├── graph.routes.ts       # Graph endpoints
│   │   ├── incidents.routes.ts   # Incident management
│   │   ├── resources.routes.ts   # Resource management
│   │   └── health.routes.ts      # Health checks
│   ├── services/
│   │   ├── rca.service.ts        # RCA business logic
│   │   ├── search.service.ts     # Search business logic
│   │   ├── graph.service.ts      # Graph queries
│   │   ├── incidents.service.ts  # Incident management
│   │   ├── resources.service.ts  # Resource management
│   │   └── index.ts              # Service exports
│   ├── types/
│   │   └── index.ts              # TypeScript type definitions
│   ├── utils/
│   │   ├── errors.ts             # Custom error classes
│   │   └── logger.ts             # Logger configuration
│   └── server.ts                 # Main application entry point
├── tests/                        # Test files
├── .env.example                  # Environment template
├── .dockerignore                 # Docker ignore file
├── Dockerfile                    # Multi-stage Docker build
├── package.json                  # Dependencies
├── tsconfig.json                 # TypeScript configuration
├── README.md                     # User documentation
└── API_IMPLEMENTATION.md         # This file
```

## 🔧 Core Components

### 1. Configuration (`src/config/`)

#### Database Connection (`database.ts`)
- Singleton pattern for Neo4j connection
- Connection pooling (max 50 connections)
- Automatic retry logic
- Health check functionality
- Graceful shutdown support

#### Application Config (`index.ts`)
- Environment-based configuration
- Type-safe config object
- Defaults for all settings
- Support for development and production modes

### 2. Services (`src/services/`)

#### RCA Service (`rca.service.ts`)
**Methods:**
- `performRCA(query)` - Execute root cause analysis with confidence scoring
- `getRCAByResource(resourceUid, timeWindow, severities)` - Get all RCA for a resource
- `bulkRCA(eventIds, minConfidence)` - Analyze multiple events

**Features:**
- Confidence-based cause ranking
- Temporal, distance, and domain scoring
- Blast radius calculation
- Timeline generation
- Automatic recommendations

#### Search Service (`search.service.ts`)
**Methods:**
- `semanticSearch(query)` - Natural language event search
- `causalSearch(query)` - Find causal chains
- `similarEvents(eventId, topK, timeWindow)` - Find similar events

**Features:**
- Text-based similarity matching
- Causal path traversal
- Configurable filters (severity, namespace, kind)
- Explanation generation

#### Graph Service (`graph.service.ts`)
**Methods:**
- `getStats()` - System-wide statistics
- `getResourceTopology(uid, depth)` - Resource relationships
- `getResourceEvents(uid, filters)` - Event history
- `getTimeline(startTime, endTime, filters)` - System timeline
- `applyGraphUpdate(update)` - Incremental updates

**Features:**
- Aggregated counts by kind, severity, type
- Relationship traversal
- Time-based filtering
- Batch updates

#### Incidents Service (`incidents.service.ts`)
**Methods:**
- `listIncidents(filters, pagination)` - List with filters
- `getIncidentById(incidentId)` - Detailed incident info
- `updateIncidentStatus(incidentId, updates)` - Update status/assignee
- `getIncidentRecommendations(incidentId)` - AI recommendations

**Features:**
- Pattern-based recommendation engine
- Dynamic filter building
- Pagination support
- Status validation

#### Resources Service (`resources.service.ts`)
**Methods:**
- `getResourceById(resourceUid)` - Resource details
- `listResources(filters, pagination)` - List with filters
- `getResourceHealth(resourceUid)` - Health assessment

**Features:**
- Health score calculation (0-100)
- Status categorization (healthy/degraded/critical)
- Event frequency analysis
- Label-based filtering

### 3. Routes (`src/routes/`)

#### RCA Routes
- `POST /api/v1/rca` - Perform RCA
- `GET /api/v1/rca/:event_id` - Get RCA by event
- `POST /api/v1/rca/resource` - RCA for resource
- `POST /api/v1/rca/bulk` - Bulk RCA

#### Search Routes
- `POST /api/v1/search/semantic` - Semantic search
- `POST /api/v1/search/causal` - Causal search
- `POST /api/v1/search/similar` - Similar events

#### Graph Routes
- `GET /api/v1/graph/stats` - Statistics
- `GET /api/v1/graph/topology/:uid` - Topology
- `GET /api/v1/graph/events/:uid` - Events
- `GET /api/v1/graph/timeline` - Timeline
- `POST /api/v1/graph/updates` - Updates

#### Incidents Routes
- `GET /api/v1/incidents` - List incidents
- `GET /api/v1/incidents/:id` - Get incident
- `PATCH /api/v1/incidents/:id` - Update incident
- `GET /api/v1/incidents/:id/recommendations` - Recommendations

#### Resources Routes
- `GET /api/v1/resources` - List resources
- `GET /api/v1/resources/:uid` - Get resource
- `GET /api/v1/resources/:uid/health` - Health check

#### Health Routes
- `GET /healthz` - Health check
- `GET /readyz` - Readiness check
- `GET /metrics` - Prometheus metrics

### 4. Middleware (`src/middleware/`)

#### Authentication (`auth.middleware.ts`)
- API key validation
- Configurable enable/disable
- Request tagging for audit

#### Error Handling (`error.middleware.ts`)
- Custom error class support
- Validation error handling
- Unexpected error handling
- Structured error responses

#### Logging (`logging.middleware.ts`)
- Request/response logging
- Duration tracking
- User agent and IP logging

### 5. Types (`src/types/index.ts`)

Comprehensive TypeScript interfaces for:
- Resource information
- Event information
- RCA results and queries
- Search queries and results
- Graph statistics
- Health status
- Pagination
- Error responses
- Webhooks

### 6. Utilities (`src/utils/`)

#### Error Classes (`errors.ts`)
- `APIError` - Base error class
- `NotFoundError` (404)
- `ValidationError` (400)
- `UnauthorizedError` (401)
- `ForbiddenError` (403)
- `RateLimitError` (429)
- `InternalServerError` (500)
- `ServiceUnavailableError` (503)

#### Logger (`logger.ts`)
- Pino-based structured logging
- Pretty printing in development
- JSON format in production
- Configurable log levels

## 🚀 Deployment

### Local Development

```bash
# Install dependencies
cd api
npm install

# Copy environment file
cp .env.example .env

# Start development server
npm run dev
```

### Production Build

```bash
# Build TypeScript
npm run build

# Start production server
npm start
```

### Docker Deployment

```bash
# Build Docker image
docker build -t kgroot-api:latest .

# Run container
docker run -p 3000:3000 \
  -e NEO4J_URI=neo4j://neo4j:7687 \
  -e NEO4J_PASSWORD=password \
  kgroot-api:latest
```

### Docker Compose

```yaml
version: '3.8'
services:
  api:
    build: ./api
    ports:
      - "3000:3000"
    environment:
      - NEO4J_URI=neo4j://neo4j:7687
      - NEO4J_USER=neo4j
      - NEO4J_PASSWORD=password
      - AUTH_ENABLED=true
      - API_KEYS=production-key-1
    depends_on:
      - neo4j
    restart: unless-stopped
```

## 🔒 Security Features

### Authentication
- API key-based authentication
- Configurable enable/disable
- Header-based key passing (`X-API-Key`)
- Multiple API keys support

### Rate Limiting
- 1000 requests/minute default
- Per-IP rate limiting
- Configurable window and max requests
- Custom error responses

### Security Headers
- Helmet.js integration
- CORS configuration
- Content Security Policy
- XSS protection

### Input Validation
- Type-safe request parsing
- Query parameter validation
- Body payload validation
- Error messages without sensitive data

## 📊 Monitoring & Observability

### Health Checks
- `/healthz` - Basic health check
- `/readyz` - Readiness check with DB validation
- Database connectivity check
- Component status reporting

### Metrics
- Prometheus-compatible `/metrics` endpoint
- Resource counts
- Event counts by severity
- Incident counts by status
- Service uptime

### Logging
- Structured JSON logging
- Request/response logging
- Error stack traces
- Performance metrics (request duration)

## 🧪 Testing

```bash
# Run tests
npm test

# Run with coverage
npm test -- --coverage

# Run specific test
npm test -- rca.service.test.ts
```

## 📈 Performance Considerations

### Database Connection Pool
- Max 50 connections
- Connection reuse
- Automatic reconnection
- 30s acquisition timeout

### Query Optimization
- Indexed queries on event_id, uid, rid
- Parameterized queries
- Limited result sets
- Efficient relationship traversal

### Response Times
- Simple queries: < 50ms
- RCA queries: < 200ms
- Complex searches: < 500ms
- Graph stats: < 100ms

## 🔄 API Versioning

Current version: `v1`

All routes are prefixed with `/api/v1` for future versioning support.

## 📝 Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| PORT | Server port | 3000 | No |
| HOST | Server host | 0.0.0.0 | No |
| NODE_ENV | Environment | development | No |
| NEO4J_URI | Neo4j URI | neo4j://localhost:7687 | Yes |
| NEO4J_USER | Neo4j username | neo4j | Yes |
| NEO4J_PASSWORD | Neo4j password | password | Yes |
| AUTH_ENABLED | Enable API key auth | false | No |
| API_KEYS | Comma-separated API keys | - | If auth enabled |
| CORS_ORIGIN | CORS allowed origins | * | No |
| LOG_LEVEL | Log level | info | No |

## 🐛 Troubleshooting

### Common Issues

**Error: Failed to connect to Neo4j**
- Check Neo4j is running
- Verify NEO4J_URI is correct
- Check credentials
- Ensure network connectivity

**Error: Rate limit exceeded**
- Increase RATE_LIMIT_MAX
- Use API key for higher limits
- Implement client-side throttling

**Error: Event not found**
- Verify event exists in database
- Check event_id format
- Ensure data ingestion is working

## 🎯 Future Enhancements

- [ ] Vector embeddings for semantic search
- [ ] WebSocket support for real-time updates
- [ ] GraphQL API
- [ ] Redis caching layer
- [ ] Kafka integration for event streaming
- [ ] Machine learning-based recommendations
- [ ] Multi-tenancy support
- [ ] Enhanced authentication (JWT, OAuth)
- [ ] Query result caching
- [ ] Batch operations optimization

## 📚 Additional Resources

- [Main README](./README.md) - User documentation
- [API Reference](../production/api-docs/API_REFERENCE.md) - Complete API docs
- [Production Deployment](../production/prod-docs/PRODUCTION_DEPLOYMENT_GUIDE.md)
- [Fastify Documentation](https://fastify.dev/)
- [Neo4j Driver Documentation](https://neo4j.com/docs/javascript-manual/)

## 🤝 Contributing

1. Follow TypeScript strict mode
2. Add JSDoc comments
3. Include error handling
4. Write unit tests
5. Update documentation
6. Follow existing code patterns

## 📄 License

MIT License - See LICENSE file for details

---

**Status**: ✅ Production Ready

**Last Updated**: 2025-10-11

**Maintained By**: KGroot Team
