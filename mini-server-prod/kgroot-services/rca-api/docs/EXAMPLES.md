# KGRoot RCA API Examples

Real-world usage examples and scenarios.

## Table of Contents

- [Basic RCA Analysis](#basic-rca-analysis)
- [Advanced Search Queries](#advanced-search-queries)
- [Resource Catalog Queries](#resource-catalog-queries)
- [Health Monitoring](#health-monitoring)
- [AI Assistant Usage](#ai-assistant-usage)
- [Complete Workflows](#complete-workflows)
- [Python Client Examples](#python-client-examples)
- [cURL Examples](#curl-examples)

---

## Basic RCA Analysis

### Example 1: Investigate Pod Failures

**Scenario:** nginx pods are failing in production, need to find root cause.

```bash
curl -X POST "http://localhost:8083/rca/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Why did nginx pods fail in the production namespace?",
    "client_id": "ab-01",
    "time_range_hours": 6,
    "reasoning_effort": "medium",
    "verbosity": "high",
    "include_remediation": true
  }'
```

**Response:**

```json
{
  "query": "Why did nginx pods fail in the production namespace?",
  "summary": "The nginx pods failed due to OOMKilled errors caused by insufficient memory limits. The root cause was a memory leak in the nginx-prometheus-exporter sidecar that accumulated over 24 hours. This caused cascading failures affecting the nginx-service and downstream API gateway.",
  "root_causes": [
    {
      "reason": "OOMKilled",
      "resource_kind": "Pod",
      "resource_name": "nginx-deployment-7d4f9c8b6-xk2pl",
      "namespace": "production",
      "timestamp": "2025-01-15T10:30:15Z",
      "confidence": 0.92,
      "blast_radius": 8,
      "message": "Container nginx-prometheus-exporter exceeded memory limit"
    }
  ],
  "causal_chains": [
    [
      {
        "step": 1,
        "event_reason": "OOMKilled",
        "resource": "Pod/nginx-deployment-7d4f9c8b6-xk2pl",
        "namespace": "production",
        "timestamp": "2025-01-15T10:30:15Z",
        "confidence": 0.92,
        "is_root_cause": true
      },
      {
        "step": 2,
        "event_reason": "BackOff",
        "resource": "Pod/nginx-deployment-7d4f9c8b6-xk2pl",
        "namespace": "production",
        "timestamp": "2025-01-15T10:30:45Z",
        "confidence": 0.88,
        "is_root_cause": false
      },
      {
        "step": 3,
        "event_reason": "Unhealthy",
        "resource": "Service/nginx-service",
        "namespace": "production",
        "timestamp": "2025-01-15T10:31:00Z",
        "confidence": 0.85,
        "is_root_cause": false
      }
    ]
  ],
  "affected_resources": [
    {
      "reason": "Unhealthy",
      "resource_kind": "Service",
      "resource_name": "nginx-service",
      "namespace": "production",
      "distance_from_root": 2
    },
    {
      "reason": "Failed",
      "resource_kind": "Ingress",
      "resource_name": "api-gateway",
      "namespace": "production",
      "distance_from_root": 3
    }
  ],
  "remediation_steps": [
    "Increase memory limit for nginx-prometheus-exporter sidecar to 256Mi",
    "kubectl set resources deployment nginx-deployment -c nginx-prometheus-exporter --limits=memory=256Mi -n production",
    "Restart the deployment to apply changes",
    "kubectl rollout restart deployment nginx-deployment -n production",
    "Monitor memory usage for 24 hours",
    "kubectl top pods -n production -l app=nginx",
    "Investigate memory leak in nginx-prometheus-exporter version"
  ],
  "confidence_score": 0.88,
  "reasoning_tokens": 1450,
  "processing_time_ms": 3420
}
```

---

### Example 2: Quick Analysis with Low Reasoning

**Scenario:** Need fast RCA for minor issue.

```bash
curl -X POST "http://localhost:8083/rca/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What failures happened in the last hour?",
    "client_id": "ab-01",
    "time_range_hours": 1,
    "reasoning_effort": "low",
    "verbosity": "low",
    "include_remediation": false
  }'
```

**Response time:** ~1.5 seconds (vs 3-4 seconds with medium reasoning)

---

### Example 3: Critical Analysis with High Reasoning

**Scenario:** Major production outage, need thorough analysis.

```bash
curl -X POST "http://localhost:8083/rca/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Complete analysis of the production outage affecting payment service",
    "client_id": "ab-01",
    "time_range_hours": 24,
    "reasoning_effort": "high",
    "verbosity": "high",
    "include_remediation": true
  }'
```

**Features with high reasoning:**
- Extended thinking time
- More detailed causal analysis
- Better confidence assessment
- Comprehensive remediation plan

---

## Advanced Search Queries

### Example 4: Find OOM Errors

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

**Response:**

```json
{
  "query": "show me all OOM errors in production namespace last 6 hours",
  "results": [
    {
      "item_type": "Event",
      "item_id": "evt-12345",
      "content": "Pod nginx-deployment-7d4f9c8b6-xk2pl OOMKilled in production namespace at 2025-01-15T10:30:15Z",
      "metadata": {
        "reason": "OOMKilled",
        "resource_kind": "Pod",
        "resource_name": "nginx-deployment-7d4f9c8b6-xk2pl",
        "namespace": "production",
        "timestamp": "2025-01-15T10:30:15Z"
      },
      "similarity_score": 0.95,
      "timestamp": "2025-01-15T10:30:15Z"
    }
  ],
  "total_results": 5,
  "query_embedding_time_ms": 120,
  "search_time_ms": 45
}
```

---

### Example 5: Find Resources by Owner

```bash
curl -X POST "http://localhost:8083/search/" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "find all pods owned by team-backend that failed",
    "client_id": "ab-01",
    "resource_types": ["Pod"],
    "limit": 50
  }'
```

---

### Example 6: Temporal Search

```bash
curl -X POST "http://localhost:8083/search/" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "what happened to the auth service between 10am and 11am today",
    "client_id": "ab-01",
    "time_range_hours": 2,
    "limit": 100
  }'
```

---

## Resource Catalog Queries

### Example 7: Browse All Pods in Production

```bash
curl -X GET "http://localhost:8083/catalog/resources/ab-01?namespaces=production&kinds=Pod&page=1&page_size=50"
```

**Response:**

```json
{
  "resources": [
    {
      "resource_id": "res-12345",
      "name": "nginx-deployment-7d4f9c8b6-xk2pl",
      "kind": "Pod",
      "namespace": "production",
      "client_id": "ab-01",
      "labels": {
        "app": "nginx",
        "tier": "frontend",
        "version": "1.21"
      },
      "owner": "team-backend",
      "size": "Medium",
      "created_at": "2025-01-10T08:00:00Z",
      "status": "Running",
      "dependencies": [
        "Service/nginx-service",
        "ConfigMap/nginx-config",
        "Secret/nginx-tls"
      ],
      "recent_events": 3
    }
  ],
  "total_count": 234,
  "filtered_count": 45,
  "page": 1,
  "page_size": 50
}
```

---

### Example 8: Find Unhealthy Resources

```bash
curl -X GET "http://localhost:8083/catalog/resources/ab-01?healthy_only=false" | jq '.resources[] | select(.recent_events > 5)'
```

---

### Example 9: Get Service Topology

```bash
curl -X GET "http://localhost:8083/catalog/topology/ab-01/production/nginx-service?resource_kind=Service"
```

**Response:**

```json
{
  "service_name": "nginx-service",
  "namespace": "production",
  "pods": [
    {
      "name": "nginx-deployment-7d4f9c8b6-xk2pl",
      "status": "Running",
      "node": "node-1"
    },
    {
      "name": "nginx-deployment-7d4f9c8b6-m9k4z",
      "status": "Running",
      "node": "node-2"
    }
  ],
  "nodes": ["node-1", "node-2"],
  "upstream_services": ["api-gateway", "load-balancer"],
  "downstream_services": ["backend-api", "auth-service", "database-service"],
  "health_status": "Healthy"
}
```

---

### Example 10: List Resource Owners

```bash
curl -X GET "http://localhost:8083/catalog/owners/ab-01"
```

**Response:**

```json
{
  "owners": [
    {
      "owner": "team-backend",
      "resource_count": 125,
      "namespaces": ["production", "staging"],
      "resource_kinds": ["Pod", "Deployment", "Service", "ConfigMap"]
    },
    {
      "owner": "team-frontend",
      "resource_count": 87,
      "namespaces": ["production", "staging"],
      "resource_kinds": ["Pod", "Deployment", "Service", "Ingress"]
    }
  ]
}
```

---

## Health Monitoring

### Example 11: Check Cluster Health

```bash
curl -X GET "http://localhost:8083/health/status/ab-01"
```

**Response:**

```json
{
  "client_id": "ab-01",
  "healthy_resources": 487,
  "unhealthy_resources": 23,
  "total_resources": 510,
  "active_incidents": 2,
  "health_percentage": 95.5,
  "top_issues": [
    {
      "reason": "OOMKilled",
      "count": 8,
      "affected_namespaces": ["production"],
      "severity": "high"
    },
    {
      "reason": "CrashLoopBackOff",
      "count": 5,
      "affected_namespaces": ["staging"],
      "severity": "medium"
    }
  ],
  "timestamp": "2025-01-15T12:00:00Z"
}
```

---

### Example 12: Send Health Report to Slack

```bash
curl -X POST "http://localhost:8083/health/send-health-report/ab-01?channel=%23health-reports"
```

---

### Example 13: Get Active Incidents

```bash
curl -X GET "http://localhost:8083/health/incidents/ab-01?min_severity=high"
```

**Response:**

```json
{
  "incidents": [
    {
      "incident_id": "inc-12345",
      "root_cause": "OOMKilled",
      "affected_services": ["nginx-service", "api-gateway"],
      "affected_namespaces": ["production"],
      "severity": "high",
      "started_at": "2025-01-15T10:30:00Z",
      "event_count": 8,
      "blast_radius": 15
    }
  ]
}
```

---

## AI Assistant Usage

### Example 14: Ask About Infrastructure

```bash
curl -X POST "http://localhost:8083/chat/" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is causing high memory usage in the auth service?",
    "client_id": "ab-01",
    "reasoning_effort": "low"
  }'
```

**Response:**

```json
{
  "message": "Based on recent events, the auth service is experiencing high memory usage due to a memory leak in the session management code. The service is currently using 1.8GB out of 2GB allocated memory.\n\nI recommend:\n1. Restart the auth service pods to clear accumulated memory\n2. Review session cleanup logic in the code\n3. Increase memory limit to 3GB temporarily while investigating\n4. Add memory profiling to identify the leak source\n\nWould you like me to generate kubectl commands for these steps?",
  "conversation_id": "conv-12345",
  "suggested_queries": [
    "Show me the kubectl commands",
    "What are similar past incidents?",
    "How do I profile memory in the auth service?"
  ],
  "related_events": ["evt-11113", "evt-11114"],
  "confidence": 0.82,
  "reasoning_summary": "Analyzed recent events and resource usage patterns. High confidence based on clear memory growth trend."
}
```

---

### Example 15: Multi-turn Conversation

**Turn 1:**
```bash
curl -X POST "http://localhost:8083/chat/" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me recent failures in production",
    "client_id": "ab-01"
  }'
```

**Turn 2:**
```bash
curl -X POST "http://localhost:8083/chat/" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me more about the OOM errors",
    "client_id": "ab-01",
    "conversation_id": "conv-12345"
  }'
```

---

### Example 16: Get Troubleshooting Help

```bash
curl -X POST "http://localhost:8083/chat/" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How do I debug CrashLoopBackOff in the payment service?",
    "client_id": "ab-01",
    "context_events": ["evt-11111"]
  }'
```

---

## Complete Workflows

### Workflow 1: Investigate and Fix Production Issue

**Step 1: Discover issue via health check**
```bash
curl -X GET "http://localhost:8083/health/status/ab-01" | jq '.top_issues'
```

**Step 2: Search for related events**
```bash
curl -X POST "http://localhost:8083/search/" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "OOMKilled events in production",
    "client_id": "ab-01",
    "limit": 10
  }'
```

**Step 3: Get detailed RCA**
```bash
curl -X POST "http://localhost:8083/rca/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Why are pods getting OOMKilled in production?",
    "client_id": "ab-01",
    "reasoning_effort": "high"
  }'
```

**Step 4: Get remediation runbook**
```bash
curl -X POST "http://localhost:8083/rca/runbook" \
  -H "Content-Type: application/json" \
  -d '{
    "failure_pattern": "OOMKilled pod restarts",
    "resource_type": "Pod"
  }'
```

**Step 5: Apply fix and verify**
```bash
# Apply fix (from remediation steps)
kubectl set resources deployment nginx-deployment --limits=memory=256Mi -n production

# Wait 5 minutes

# Verify health improved
curl -X GET "http://localhost:8083/health/status/ab-01"
```

---

### Workflow 2: Proactive Monitoring

**Daily health report (cron job)**
```bash
#!/bin/bash
# /usr/local/bin/daily-health-report.sh

# Get health status
HEALTH=$(curl -s "http://localhost:8083/health/status/ab-01")
HEALTH_PCT=$(echo $HEALTH | jq -r '.health_percentage')

# Alert if health < 90%
if (( $(echo "$HEALTH_PCT < 90" | bc -l) )); then
  # Send to Slack
  curl -X POST "http://localhost:8083/health/send-health-report/ab-01"

  # Trigger RCA for top issues
  curl -X POST "http://localhost:8083/rca/analyze" \
    -H "Content-Type: application/json" \
    -d '{
      "query": "What are the top issues affecting cluster health?",
      "client_id": "ab-01",
      "time_range_hours": 24
    }'
fi
```

---

## Python Client Examples

### Example 17: Python Script for RCA

```python
import requests
import json


class KGRootRCAClient:
    """Client for KGRoot RCA API"""

    def __init__(self, base_url: str = "http://localhost:8083", client_id: str = "ab-01"):
        self.base_url = base_url
        self.client_id = client_id

    def analyze_rca(
        self,
        query: str,
        time_range_hours: int = 24,
        reasoning_effort: str = "medium"
    ) -> dict:
        """Perform RCA analysis"""
        response = requests.post(
            f"{self.base_url}/rca/analyze",
            json={
                "query": query,
                "client_id": self.client_id,
                "time_range_hours": time_range_hours,
                "reasoning_effort": reasoning_effort,
                "include_remediation": True
            }
        )
        response.raise_for_status()
        return response.json()

    def search(self, query: str, limit: int = 20) -> dict:
        """Search for events and resources"""
        response = requests.post(
            f"{self.base_url}/search/",
            json={
                "query": query,
                "client_id": self.client_id,
                "limit": limit
            }
        )
        response.raise_for_status()
        return response.json()

    def get_health(self) -> dict:
        """Get cluster health status"""
        response = requests.get(
            f"{self.base_url}/health/status/{self.client_id}"
        )
        response.raise_for_status()
        return response.json()

    def chat(self, message: str, conversation_id: str = None) -> dict:
        """Chat with AI assistant"""
        payload = {
            "message": message,
            "client_id": self.client_id
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

        response = requests.post(
            f"{self.base_url}/chat/",
            json=payload
        )
        response.raise_for_status()
        return response.json()


# Usage
if __name__ == "__main__":
    client = KGRootRCAClient(client_id="ab-01")

    # Check health
    health = client.get_health()
    print(f"Cluster health: {health['health_percentage']}%")

    # If unhealthy, investigate
    if health["health_percentage"] < 95:
        print("\n🔍 Investigating issues...")

        # Perform RCA
        rca_result = client.analyze_rca(
            query="What are the main issues affecting cluster health?",
            reasoning_effort="high"
        )

        print(f"\n📊 RCA Summary:\n{rca_result['summary']}")
        print(f"\n🔧 Remediation Steps:")
        for i, step in enumerate(rca_result["remediation_steps"], 1):
            print(f"  {i}. {step}")

        # Chat for more details
        chat_response = client.chat(
            message="Explain the root cause in detail and provide kubectl commands"
        )
        print(f"\n💬 AI Assistant:\n{chat_response['message']}")
```

---

### Example 18: Async Python Client

```python
import asyncio
import aiohttp


class AsyncKGRootClient:
    """Async client for KGRoot RCA API"""

    def __init__(self, base_url: str, client_id: str):
        self.base_url = base_url
        self.client_id = client_id

    async def analyze_rca(self, query: str) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/rca/analyze",
                json={
                    "query": query,
                    "client_id": self.client_id
                }
            ) as response:
                return await response.json()

    async def get_health(self) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/health/status/{self.client_id}"
            ) as response:
                return await response.json()


async def main():
    client = AsyncKGRootClient("http://localhost:8083", "ab-01")

    # Run multiple requests concurrently
    health, rca = await asyncio.gather(
        client.get_health(),
        client.analyze_rca("What failures happened today?")
    )

    print(f"Health: {health['health_percentage']}%")
    print(f"RCA: {rca['summary']}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## cURL Examples

### Example 19: Complete cURL Workflow

```bash
#!/bin/bash
# rca-investigation.sh - Complete RCA investigation workflow

API_URL="http://localhost:8083"
CLIENT_ID="ab-01"

echo "🔍 Step 1: Check cluster health"
HEALTH=$(curl -s "${API_URL}/health/status/${CLIENT_ID}")
HEALTH_PCT=$(echo $HEALTH | jq -r '.health_percentage')
echo "Health: ${HEALTH_PCT}%"

echo -e "\n📊 Step 2: Get top issues"
echo $HEALTH | jq -r '.top_issues[] | "- \(.reason): \(.count) events (\(.severity) severity)"'

echo -e "\n🔎 Step 3: Search for OOM errors"
curl -s -X POST "${API_URL}/search/" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"show me OOM errors\",
    \"client_id\": \"${CLIENT_ID}\",
    \"limit\": 5
  }" | jq -r '.results[] | "- \(.content)"'

echo -e "\n🧠 Step 4: Perform deep RCA"
RCA=$(curl -s -X POST "${API_URL}/rca/analyze" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"Why are pods getting OOMKilled?\",
    \"client_id\": \"${CLIENT_ID}\",
    \"reasoning_effort\": \"high\"
  }")

echo "Summary:"
echo $RCA | jq -r '.summary'

echo -e "\n🔧 Remediation Steps:"
echo $RCA | jq -r '.remediation_steps[] | "  - \(.)"'

echo -e "\n✅ Investigation complete!"
```

---

## Next Steps

- [API Reference](API.md) - Complete API documentation
- [Setup Guide](SETUP.md) - Installation and configuration
- [Architecture](ARCHITECTURE.md) - System design
- [Integrations](INTEGRATIONS.md) - Slack and other connectors
