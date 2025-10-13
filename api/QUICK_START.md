# KG RCA API - Quick Start Guide

Get the API running in 5 minutes!

## 🚀 Quick Start

### 1. Prerequisites

```bash
# Check Node.js version (must be >= 20)
node --version

# Check npm version
npm --version

# Ensure Neo4j is running
# Default: neo4j://localhost:7687
```

### 2. Install Dependencies

```bash
cd api
npm install
```

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
# Minimum required: NEO4J_PASSWORD
```

### 4. Start the Server

```bash
# Development mode (auto-reload)
npm run dev

# Or start with tsx (faster)
npm run start:dev
```

### 5. Verify Installation

Open your browser to:
- **API**: http://localhost:3000
- **Docs**: http://localhost:3000/docs
- **Health**: http://localhost:3000/healthz

Or use curl:

```bash
# Health check
curl http://localhost:3000/healthz

# Get stats
curl http://localhost:3000/api/v1/graph/stats

# Perform RCA
curl -X POST http://localhost:3000/api/v1/rca \
  -H "Content-Type: application/json" \
  -d '{"event_id": "your-event-id"}'
```

## 📦 Production Deployment

### Build for Production

```bash
# Build TypeScript
npm run build

# Start production server
npm start
```

### Using Docker

```bash
# Build image
docker build -t kgroot-api:latest .

# Run container
docker run -p 3000:3000 \
  -e NEO4J_URI=neo4j://neo4j:7687 \
  -e NEO4J_PASSWORD=your-password \
  kgroot-api:latest
```

### Using Docker Compose

Create `docker-compose.yml`:

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
    depends_on:
      - neo4j
    restart: unless-stopped

  neo4j:
    image: neo4j:5.14
    ports:
      - "7687:7687"
      - "7474:7474"
    environment:
      - NEO4J_AUTH=neo4j/password
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
```

Then run:

```bash
docker-compose up -d
```

## 🧪 Test the API

### Test RCA Endpoint

```bash
curl -X POST http://localhost:3000/api/v1/rca \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt-abc123",
    "min_confidence": 0.6,
    "max_hops": 3
  }'
```

### Test Search Endpoint

```bash
curl -X POST http://localhost:3000/api/v1/search/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "memory leak",
    "top_k": 5
  }'
```

### Test Graph Stats

```bash
curl http://localhost:3000/api/v1/graph/stats | jq
```

## 🔒 Enable Authentication

1. Edit `.env`:
```bash
AUTH_ENABLED=true
API_KEYS=your-secret-key-1,your-secret-key-2
```

2. Restart the server

3. Include API key in requests:
```bash
curl -H "X-API-Key: your-secret-key-1" \
  http://localhost:3000/api/v1/graph/stats
```

## 🐛 Troubleshooting

### Port Already in Use

```bash
# Change port in .env
PORT=3001
```

### Cannot Connect to Neo4j

```bash
# Check Neo4j is running
docker ps | grep neo4j

# Or check Neo4j status
systemctl status neo4j

# Verify connection
curl http://localhost:7474
```

### Module Not Found Errors

```bash
# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install
```

## 📚 Next Steps

1. Read the [README](./README.md) for detailed API documentation
2. Explore the [Swagger UI](http://localhost:3000/docs) for interactive API testing
3. Check [API_IMPLEMENTATION.md](./API_IMPLEMENTATION.md) for architecture details
4. Review the [API Reference](../production/api-docs/API_REFERENCE.md) for all endpoints

## 💡 Tips

- Use `npm run dev` for development (auto-reload on changes)
- Use `npm run start:dev` for faster startup with tsx
- Enable pretty logging in development (already enabled)
- Check logs for detailed error messages
- Use Swagger UI at `/docs` for easy API testing

## 🆘 Get Help

- Check the logs for error messages
- Verify all environment variables are set
- Ensure Neo4j contains data
- Test Neo4j connectivity independently
- Review the [Production Deployment Guide](../production/prod-docs/PRODUCTION_DEPLOYMENT_GUIDE.md)

---

Happy API building! 🚀
