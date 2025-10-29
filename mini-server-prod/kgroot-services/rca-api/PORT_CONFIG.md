# Port Configuration Update

## Summary

All documentation and configuration files have been updated to use **port 8083** instead of port 8000 to avoid conflicts with existing services.

## Conflicting Ports (Already in Use)

Based on your `docker ps` output, the following ports are already occupied:

- **8080**: kg-alert-receiver
- **8081**: kg-rca-webhook  
- **8082**: kg-rca-api (existing)
- **9090**: kg-control-plane
- **9092**: kg-kafka
- **9093**: kg-alertmanager
- **7474**: kg-neo4j (HTTP)
- **7687**: kg-neo4j (Bolt)
- **7777**: kg-kafka-ui

## Selected Port

**Port 8083** - Available and not in use by any existing services.

## Updated Files

### Configuration Files
- ✅ `.env.example` - Updated `API_PORT=8083`
- ✅ `src/config.py` - Updated default `api_port: int = 8083`

### Documentation Files
- ✅ `README.md` - All examples updated to use port 8083
- ✅ `docs/API.md` - All endpoint examples updated
- ✅ `docs/SETUP.md` - All setup commands updated
- ✅ `docs/EXAMPLES.md` - All cURL examples updated
- ✅ `docs/SUMMARY.md` - All quick start commands updated
- ✅ `docs/KGRoot-RCA-API.postman_collection.json` - Base URL updated to `http://localhost:8083`
- ✅ `API_OVERVIEW.txt` - All references updated

## Quick Start (Updated Commands)

### 1. Run API
```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8083
```

### 2. Access Documentation
- Swagger UI: http://localhost:8083/docs
- ReDoc: http://localhost:8083/redoc

### 3. Test Endpoint
```bash
curl -X POST "http://localhost:8083/rca/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Why did nginx pods fail?",
    "client_id": "ab-01"
  }'
```

## Environment Configuration

Your `.env` file should include:
```bash
API_PORT=8083
```

If not specified, the application will default to port 8083 as configured in `src/config.py`.

## Docker Deployment

When running with Docker, use:
```bash
docker run -p 8083:8083 --env-file .env kgroot-rca-api:2.0.0
```

## Verification

After starting the API on port 8083, verify it's running:

```bash
# Check if port is in use
lsof -i :8083

# Test API health
curl http://localhost:8083/

# Access Swagger UI
open http://localhost:8083/docs
```

## Port Mapping Summary

| Service | Port | Status |
|---------|------|--------|
| kg-alert-receiver | 8080 | ❌ In Use |
| kg-rca-webhook | 8081 | ❌ In Use |
| kg-rca-api (existing) | 8082 | ❌ In Use |
| **NEW RCA API** | **8083** | ✅ **Available** |
| kg-control-plane | 9090 | ❌ In Use |
| kg-kafka | 9092 | ❌ In Use |
| kg-alertmanager | 9093 | ❌ In Use |
| kg-neo4j (HTTP) | 7474 | ❌ In Use |
| kg-neo4j (Bolt) | 7687 | ❌ In Use |
| kg-kafka-ui | 7777 | ❌ In Use |

---

**All configuration files and documentation have been updated. You can now run the API on port 8083 without any conflicts!**
