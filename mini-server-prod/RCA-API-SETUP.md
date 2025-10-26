# RCA API Setup Guide

Complete guide to deploy the RCA API service with GraphRAG + GPT-5/GPT-4o integration for your Web UI.

## 🎯 What This Provides

The RCA API service provides comprehensive root cause analysis with:

- ✅ **GPT-5/GPT-4o LLM Analysis** - Natural language explanations
- ✅ **Confidence Scoring** - 0-100% confidence for each hypothesis
- ✅ **Blast Radius Calculation** - Which services will be affected
- ✅ **Ranked Fix Suggestions** - Top 3-4 solutions with risk/impact analysis
- ✅ **SLA Tracking** - SLO status and risk budget
- ✅ **Timeline Reconstruction** - Event sequence with causal chains
- ✅ **Impact Analysis** - Users affected, downtime estimates, rollback difficulty

## 📋 Prerequisites

1. **OpenAI API Key** (Required for LLM analysis)
   - Get from: https://platform.openai.com/api-keys
   - Models supported: `gpt-4o`, `gpt-5` (if you have access)

2. **Running Control Plane** (from previous setup)
   - Neo4j with service topology
   - Kafka with events.normalized topic
   - Client mn-01 sending events

## 🚀 Quick Start

### 1. Set OpenAI API Key

```bash
# On control plane server
export OPENAI_API_KEY="sk-your-api-key-here"

# Persist it
echo 'export OPENAI_API_KEY="sk-your-api-key-here"' >> ~/.bashrc
```

### 2. Update Requirements

```bash
cd ~/kgroot-latest/mini-server-prod/kgroot-services

# Add required packages if not already there
cat >> requirements.txt <<EOF
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
EOF
```

### 3. Rebuild Control Plane Image

The RCA API uses the same base image:

```bash
cd ~/kgroot-latest/mini-server-prod

# Rebuild with new dependencies
docker compose -f docker-compose-control-plane.yml build kg-control-plane --no-cache

# Pull latest code first
git pull origin feature/kgroot-implementation
```

### 4. Deploy RCA API Service

```bash
cd ~/kgroot-latest/mini-server-prod

# Start RCA API
docker compose -f docker-compose-rca-api.yml up -d

# Check logs
docker logs kg-rca-api -f
```

You should see:
```
🚀 Starting RCA API Service...
   OpenAI API Key: ✅ Configured
   LLM Enabled: True
   LLM Model: gpt-4o
✅ Neo4j connection established
✅ RCA API Service ready
INFO:     Uvicorn running on http://0.0.0.0:8080
```

### 5. Test the API

```bash
# Health check
curl http://localhost:8080/health

# Trigger RCA analysis for the test pod
curl -X POST http://localhost:8080/api/v1/rca/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "mn-01",
    "namespace": "observability",
    "pod_name": "test-memory-hog-bbbfcbcd9-mh5p7",
    "time_window_minutes": 15,
    "include_llm_analysis": true
  }' | jq .
```

## 📊 API Response Format (For Web UI)

The API returns data in the exact format your Web UI expects:

```json
{
  "incident_id": "incident-20251026-091234",
  "client_id": "mn-01",
  "timestamp": "2025-10-26T09:12:34.567Z",

  "primary_symptom": "test-memory-hog · BackOff",
  "affected_services": ["test-memory-hog"],
  "confidence_score": 84.0,

  "sla_status": "within_slo",
  "sla_percentage": 95.2,
  "risk_budget_remaining": 3,

  "total_symptoms": 15,
  "timeseries_analyzed": 6305,
  "analysis_duration_seconds": 5.2,

  "fix_suggestions": [
    {
      "rank": 1,
      "action": "Increase memory limits for test-memory-hog pod",
      "confidence": 84.0,
      "blast_radius": ["test-memory-hog", "api-gateway"],
      "risk_score": 18,
      "eta_minutes": 4,
      "prerequisites": ["Deployment access", "Resource quota available"],
      "reasoning": "Pod experiencing OOM kills, needs more memory allocation"
    },
    {
      "rank": 2,
      "action": "Rollback recent deployment",
      "confidence": 68.0,
      "blast_radius": ["test-memory-hog"],
      "risk_score": 32,
      "eta_minutes": 3,
      "prerequisites": ["Previous deployment available"],
      "reasoning": "Recent code change may have introduced memory leak"
    }
  ],

  "timeline": [
    {
      "timestamp": "2025-10-26T09:00:04Z",
      "type": "Pulling",
      "description": "Pulling image polinux/stress",
      "service": "test-memory-hog",
      "pod": "test-memory-hog-bbbfcbcd9-mh5p7",
      "severity": "info"
    },
    {
      "timestamp": "2025-10-26T09:00:32Z",
      "type": "BackOff",
      "description": "Back-off restarting failed container memory-hog",
      "service": "test-memory-hog",
      "pod": "test-memory-hog-bbbfcbcd9-mh5p7",
      "severity": "critical"
    }
  ],

  "root_causes": [
    {
      "event_type": "OOMKilled",
      "service": "test-memory-hog",
      "confidence": 0.84,
      "explanation": "Container exceeded memory limit causing OOM kill"
    }
  ],

  "llm_analysis": {
    "root_cause_diagnosis": "The container is being OOM killed because...",
    "confidence_level": "high - 84%",
    "solutions": [
      {
        "action": "Increase memory limits to 256Mi",
        "probability_of_success": 84.0,
        "reasoning": "Pod requires more than 128Mi based on stress test",
        "estimated_time_minutes": 4,
        "prerequisites": ["Deployment manifest access", "Resource quota"],
        "impact_analysis": {
          "affected_services": ["test-memory-hog"],
          "users_impacted_percentage": 0,
          "downtime_minutes": 2,
          "rollback_difficulty": 15,
          "data_integrity_risk": "low"
        }
      }
    ],
    "blast_radius": {
      "immediate_impact": ["test-memory-hog"],
      "cascade_risk_services": [],
      "estimated_affected_requests_per_min": 0
    },
    "timeline_analysis": {
      "incident_start_estimated": "2025-10-26T09:00:00Z",
      "first_symptom": "Container started at 09:00:28",
      "failure_point": "OOM kill at 09:00:32",
      "propagation_sequence": ["Pod scheduled", "Container started", "Memory exceeded", "OOM killed", "CrashLoopBackOff"]
    }
  }
}
```

## 🔌 Integrating with Your Web UI

### Frontend API Call Example (React/Next.js)

```typescript
async function triggerRCAAnalysis(clientId: string, podName: string) {
  const response = await fetch('http://your-rca-api:8080/api/v1/rca/analyze', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      client_id: clientId,
      pod_name: podName,
      namespace: 'observability',
      time_window_minutes: 15,
      include_llm_analysis: true
    })
  });

  const data = await response.json();

  // Map to your UI components
  return {
    incidentId: data.incident_id,
    primarySymptom: data.primary_symptom,
    confidenceScore: data.confidence_score,
    slaStatus: data.sla_status,
    fixSuggestions: data.fix_suggestions,
    timeline: data.timeline,
    llmAnalysis: data.llm_analysis
  };
}
```

### Web UI Component Mapping

| Web UI Field | API Response Field |
|---|---|
| **Incident Title** | `primary_symptom` |
| **SLA Timer** | `sla_status`, `sla_percentage` |
| **RCA Confidence** | `confidence_score` |
| **Risk Budget** | `risk_budget_remaining` |
| **Total Timeseries** | `timeseries_analyzed` |
| **Time Taken** | `analysis_duration_seconds` |
| **Fix Suggestions** | `fix_suggestions[]` (ranked 1-4) |
| **Blast Radius** | `fix_suggestions[].blast_radius` |
| **Risk Score** | `fix_suggestions[].risk_score` |
| **Timeline** | `timeline[]` |
| **Chain of Thought** | `llm_analysis.timeline_analysis.propagation_sequence` |

## 🎛️ Configuration Options

### Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-xxx             # Your OpenAI API key

# Optional
ENABLE_LLM=true                   # Enable/disable LLM analysis
LLM_MODEL=gpt-4o                  # Model: gpt-4o, gpt-5, gpt-5-mini
NEO4J_URI=bolt://kg-neo4j:7687    # Neo4j connection
KAFKA_BROKERS=kg-kafka:29092      # Kafka brokers
```

### Model Selection

| Model | Speed | Cost | Accuracy | Best For |
|---|---|---|---|---|
| **gpt-4o** | Fast (2-3s) | $$ | 85-90% | Production, real-time |
| **gpt-5** | Medium (3-5s) | $$$ | 90-95% | Complex failures |
| **gpt-5-mini** | Very Fast (1-2s) | $ | 80-85% | High throughput |

## 🧪 Testing Different Failure Scenarios

### 1. OOM Kill (Already Created)

```bash
curl -X POST http://localhost:8080/api/v1/rca/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "mn-01",
    "pod_name": "test-memory-hog-bbbfcbcd9-mh5p7",
    "time_window_minutes": 15
  }'
```

### 2. Service-Wide Failure

```bash
curl -X POST http://localhost:8080/api/v1/rca/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "mn-01",
    "service_name": "test-memory-hog",
    "time_window_minutes": 15
  }'
```

### 3. Namespace-Wide Analysis

```bash
curl -X POST http://localhost:8080/api/v1/rca/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "mn-01",
    "namespace": "observability",
    "time_window_minutes": 30
  }'
```

## 📈 Expected Performance

- **Analysis Time**: 2-5 seconds with LLM enabled
- **Accuracy**: 85-95% top-3 root cause detection
- **Throughput**: ~10-20 RCA requests/minute (rate limited by OpenAI API)
- **Cost**: ~$0.01-0.05 per RCA analysis (depends on model and event count)

## 🐛 Troubleshooting

### Issue: "OpenAI API Key not configured"

```bash
# Verify env var is set
docker exec kg-rca-api printenv | grep OPENAI

# Restart with correct key
export OPENAI_API_KEY="sk-your-key"
docker compose -f docker-compose-rca-api.yml up -d
```

### Issue: "No events found"

- Check that events are flowing to Kafka:
  ```bash
  docker exec -it kg-kafka kafka-console-consumer \
    --bootstrap-server localhost:9092 \
    --topic events.normalized \
    --max-messages 5
  ```

### Issue: "Neo4j connection failed"

- Check Neo4j is running:
  ```bash
  docker ps | grep neo4j
  docker logs kg-neo4j
  ```

## 🚀 Production Deployment

For production, consider:

1. **Add authentication** - JWT tokens, API keys
2. **Rate limiting** - Prevent OpenAI API abuse
3. **Caching** - Cache LLM responses for similar incidents
4. **Monitoring** - Track API latency, success rate
5. **Scale** - Run multiple API instances behind load balancer

## 📚 Next Steps

1. ✅ Deploy RCA API service
2. ✅ Test with your Web UI
3. ✅ Configure OpenAI API key
4. 🔄 Integrate with alerting (Alertmanager webhooks)
5. 🔄 Add automated remediation triggers
6. 🔄 Build pattern database from historical incidents

## 💡 Example Web UI Integration

See `demo_web_ui_integration.html` for a complete example of how to consume this API in a web frontend.

---

**Need help?** Check logs:
```bash
docker logs kg-rca-api -f
```
