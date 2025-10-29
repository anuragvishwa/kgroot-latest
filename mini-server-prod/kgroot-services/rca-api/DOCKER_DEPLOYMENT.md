# Docker Deployment Guide

## Quick Start with Docker

### 1. Stop the venv version (if running)

```bash
# Press CTRL+C in the terminal where uvicorn is running
```

### 2. Create .env file for Docker

```bash
cd ~/kgroot-latest/mini-server-prod/kgroot-services/rca-api
cp .env.docker .env

# Edit with your actual credentials
nano .env
```

Add:
```bash
NEO4J_PASSWORD=your-actual-password
OPENAI_API_KEY=sk-your-actual-key
SLACK_BOT_TOKEN=xoxb-your-actual-token  # Optional
```

### 3. Build and run with Docker Compose

```bash
# Build the image
docker-compose build

# Start the container
docker-compose up -d

# Check logs
docker-compose logs -f kg-rca-api-v2
```

### 4. Verify it's running

```bash
# Check container status
docker ps | grep kg-rca-api-v2

# Test endpoint
curl http://localhost:8083/health/status/ab-01

# Access Swagger UI
open http://localhost:8083/docs
```

## Alternative: Build and Push to Docker Hub

### 1. Build the image

```bash
cd ~/kgroot-latest/mini-server-prod/kgroot-services/rca-api
docker build -t anuragvishwa/kg-rca-api-v2:2.0.0 .
```

### 2. Push to Docker Hub

```bash
docker login
docker push anuragvishwa/kg-rca-api-v2:2.0.0
```

### 3. Run the container

```bash
docker run -d \
  --name kg-rca-api-v2 \
  --network kg-network \
  -p 8083:8083 \
  -e NEO4J_URI=bolt://kg-neo4j:7687 \
  -e NEO4J_USER=neo4j \
  -e NEO4J_PASSWORD=your-password \
  -e OPENAI_API_KEY=sk-your-key \
  -e OPENAI_MODEL=gpt-4-turbo \
  -v $(pwd)/embeddings_cache:/app/embeddings_cache \
  -v $(pwd)/logs:/app/logs \
  --restart unless-stopped \
  anuragvishwa/kg-rca-api-v2:2.0.0
```

## Managing the Container

### View logs
```bash
docker logs -f kg-rca-api-v2
```

### Restart
```bash
docker restart kg-rca-api-v2
```

### Stop
```bash
docker stop kg-rca-api-v2
```

### Remove
```bash
docker stop kg-rca-api-v2
docker rm kg-rca-api-v2
```

### Update to new version
```bash
# Stop old container
docker stop kg-rca-api-v2
docker rm kg-rca-api-v2

# Pull new image
docker pull anuragvishwa/kg-rca-api-v2:2.0.1

# Run new version
docker run -d ...
```

## Clean Up venv

After confirming Docker version works, clean up the venv:

```bash
cd ~/kgroot-latest/mini-server-prod/kgroot-services/rca-api

# Remove venv directory
rm -rf venv/

# Remove __pycache__ directories
find . -type d -name __pycache__ -exec rm -rf {} +

# Remove .pyc files
find . -type f -name "*.pyc" -delete
```

## Troubleshooting

### Container won't start
```bash
# Check logs
docker logs kg-rca-api-v2

# Check if Neo4j is accessible
docker exec kg-rca-api-v2 nc -zv kg-neo4j 7687
```

### Out of memory
```bash
# Reduce workers in docker-compose.yml
API_WORKERS: 1

# Or limit container memory
docker update --memory 2g kg-rca-api-v2
```

### Embeddings taking too long
```bash
# Embeddings are cached in volume
# First startup takes ~1 minute
# Subsequent startups are much faster
```

## Health Check

The container includes a built-in health check:

```bash
# Check health status
docker inspect kg-rca-api-v2 | grep -A 10 Health

# Manual health check
curl http://localhost:8083/
```

## Integration with Existing Services

The container automatically connects to your existing services:

- **Neo4j**: `kg-neo4j:7687` (via kg-network)
- **Kafka**: Available if needed
- **Slack**: Configured via env vars

All containers share the `kg-network` Docker network.

## Performance Notes

### First Startup
- Downloads sentence-transformer model (~90MB)
- Builds embedding index (1-2 minutes for 1000 events)
- Total startup: ~2-3 minutes

### Subsequent Startups
- Uses cached model
- Uses cached embeddings
- Total startup: ~10-20 seconds

## Monitoring

### Check resource usage
```bash
docker stats kg-rca-api-v2
```

### View real-time logs
```bash
docker logs -f --tail 100 kg-rca-api-v2
```

### Export logs
```bash
docker logs kg-rca-api-v2 > rca-api.log
```

## Benefits vs venv

✅ Isolated environment
✅ Easy deployment and updates
✅ Automatic restart on failure
✅ Health checks built-in
✅ Consistent with other services
✅ Easy to scale (multiple containers)
✅ Volume persistence for cache
✅ No Python version conflicts
