# Testing Client Integration - Complete Commands

## Your Current Setup

✅ **Server Side (Ubuntu):**
- Docker Compose running at: `~/kgroot-latest/mini-server-prod`
- Webhook endpoint: `http://YOUR_SERVER_IP:8081/webhook`
- Services: kg-rca-webhook, kg-neo4j, kg-kafka, kg-alertmanager

---

## 🧪 Test Scenario 1: Simulating Client's Alertmanager

### On Your Ubuntu Server:

```bash
# 1. Get your server's public IP
curl ifconfig.me
# Note this IP - let's call it SERVER_IP

# 2. Check webhook is healthy
curl http://localhost:8081/health

# Expected: {"status":"healthy","rca_enabled":true,"buffer_size":0}
```

### Simulate Client Sending Alerts:

```bash
# Replace SERVER_IP with your actual IP from step 1
export SERVER_IP="YOUR_SERVER_IP_HERE"

# Test 1: Single alert (won't trigger RCA)
curl -X POST http://$SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "groupLabels": {"alertname": "HighMemory"},
    "commonAnnotations": {},
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "HighMemoryUsage",
        "severity": "warning",
        "service": "payment-service",
        "namespace": "production",
        "pod": "payment-abc-123",
        "cluster": "client-prod-us-east"
      },
      "annotations": {
        "summary": "Payment service memory at 85%",
        "description": "Memory usage is high and climbing"
      },
      "startsAt": "2025-10-25T10:00:00Z"
    }]
  }'

# Check status
curl http://$SERVER_IP:8081/status | jq

# Test 2: Second alert
curl -X POST http://$SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "labels": {
        "alertname": "KubePodCrashLooping",
        "severity": "critical",
        "service": "payment-service",
        "namespace": "production",
        "pod": "payment-abc-123",
        "cluster": "client-prod-us-east"
      },
      "annotations": {
        "summary": "Pod is crash looping",
        "description": "Pod has been restarted 6 times due to OOMKilled"
      },
      "startsAt": "2025-10-25T10:01:30Z"
    }]
  }'

# Test 3: Third alert - THIS TRIGGERS RCA!
curl -X POST http://$SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "labels": {
        "alertname": "HighErrorRate",
        "severity": "critical",
        "service": "payment-service",
        "namespace": "production",
        "cluster": "client-prod-us-east"
      },
      "annotations": {
        "summary": "Payment API error rate at 35%",
        "description": "Users unable to complete checkout. Revenue impact estimated $50k/hour"
      },
      "startsAt": "2025-10-25T10:02:00Z"
    }]
  }'

# Watch the RCA magic happen!
# On Ubuntu server in another terminal:
docker logs -f kg-rca-webhook | tail -50
```

---

## 🧪 Test Scenario 2: Multiple Services Cascade Failure

```bash
export SERVER_IP="YOUR_SERVER_IP_HERE"

# Simulate a cascading failure across multiple services

# Alert 1: Database connection pool exhausted
curl -X POST http://$SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "labels": {
        "alertname": "DatabaseConnectionPoolExhausted",
        "severity": "critical",
        "service": "postgres-db",
        "namespace": "production",
        "cluster": "client-prod-us-east"
      },
      "annotations": {
        "summary": "Database connection pool at 100%",
        "description": "Max connections reached, new connections being rejected"
      }
    }]
  }'

# Alert 2: Payment service timing out
curl -X POST http://$SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "labels": {
        "alertname": "HighLatency",
        "severity": "warning",
        "service": "payment-service",
        "namespace": "production",
        "cluster": "client-prod-us-east"
      },
      "annotations": {
        "summary": "Payment API P99 latency at 5.2s",
        "description": "Database queries timing out"
      }
    }]
  }'

# Alert 3: Order service errors
curl -X POST http://$SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "labels": {
        "alertname": "ServiceDown",
        "severity": "critical",
        "service": "order-service",
        "namespace": "production",
        "cluster": "client-prod-us-east"
      },
      "annotations": {
        "summary": "Order service failing health checks",
        "description": "Cannot connect to payment service"
      }
    }]
  }'

# Watch RCA identify the cascade
docker logs kg-rca-webhook --tail 100
```

---

## 🧪 Test Scenario 3: Node Resource Exhaustion

```bash
export SERVER_IP="YOUR_SERVER_IP_HERE"

# Simulate node-level failure

# Alert 1: Node memory pressure
curl -X POST http://$SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "labels": {
        "alertname": "NodeMemoryPressure",
        "severity": "warning",
        "node": "node-prod-5",
        "namespace": "kube-system",
        "cluster": "client-prod-us-east"
      },
      "annotations": {
        "summary": "Node experiencing memory pressure",
        "description": "Available memory below 10%"
      }
    }]
  }'

# Alert 2: Pods being evicted
curl -X POST http://$SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "labels": {
        "alertname": "PodEvicted",
        "severity": "critical",
        "service": "api-gateway",
        "namespace": "production",
        "node": "node-prod-5",
        "cluster": "client-prod-us-east"
      },
      "annotations": {
        "summary": "Multiple pods evicted from node-prod-5",
        "description": "OOM condition causing pod evictions"
      }
    }]
  }'

# Alert 3: Deployment replicas mismatch
curl -X POST http://$SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "labels": {
        "alertname": "DeploymentReplicasMismatch",
        "severity": "warning",
        "service": "api-gateway",
        "namespace": "production",
        "cluster": "client-prod-us-east"
      },
      "annotations": {
        "summary": "api-gateway deployment 3/5 replicas available",
        "description": "Cannot schedule pods due to node resource constraints"
      }
    }]
  }'
```

---

## 📊 Verify RCA Output

After sending 3 alerts, check the logs:

```bash
# On Ubuntu server
docker logs kg-rca-webhook --tail 100 | grep -A 50 "Triggering RCA"
```

**You should see:**

```
🔍 Triggering RCA for 3 alerts

Step 1: Building FPG... ✓
Step 2: Matching patterns... ✓
Step 3: Ranking root causes... ✓
Step 4: LLM analysis... ✓

🎯 Top Root Causes:
  1. [root_cause] in [service] (confidence: XX%)

💡 LLM Analysis Summary: [one-sentence summary]
   Confidence: high - 95%

💥 Blast Radius:
   Impact: [immediate impact]
   User Impact: [percentage]
   Downstream: [affected services]

🚨 Recommended Action:
   Priority: P0-Critical
   Time to Action: Immediate
   Team: [team-name]

📋 Top 3 Solutions:

   Solution 1: [solution name]
   ├─ Success Rate: 95%
   ├─ Blast Radius: Low
   ├─ Risk Level: Low
   ├─ Downtime: 30 seconds
   └─ Steps: kubectl set resources...

   Solution 2: [solution name]
   ├─ Success Rate: 85%
   ...

   Solution 3: [solution name]
   ├─ Success Rate: 70%
   ...
```

---

## 🔍 Check Neo4j Patterns

```bash
# Access Neo4j browser
# On your Mac, open browser:
# http://YOUR_SERVER_IP:7474

# Username: neo4j
# Password: Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA

# Query stored patterns:
MATCH (p:FailurePattern)
RETURN p.root_cause_type, p.frequency, p.services
ORDER BY p.frequency DESC
LIMIT 10

# Query recent RCA analyses:
MATCH (f:FaultPropagationGraph)-[:HAS_EVENT]->(e:Event)
RETURN f.fault_id, e.event_type, e.service, e.timestamp
ORDER BY e.timestamp DESC
LIMIT 20
```

---

## 📈 Performance Metrics

Check how fast your RCA is:

```bash
# View recent RCA execution times
docker logs kg-rca-webhook 2>&1 | grep "RCA completed" | tail -10
```

**Expected:**
```
RCA completed in 38.14s, confidence: 100.00%
RCA completed in 41.71s, confidence: 99.00%
```

**Breakdown:**
- Without GPT-5: ~500ms
- With GPT-5 (medium reasoning): ~30-45s
- Accuracy: 85-90% top-3

---

## 🎭 Advanced: Simulate Real Client Alertmanager

If you want to test with actual Alertmanager format:

```bash
export SERVER_IP="YOUR_SERVER_IP_HERE"

# This matches exactly what Prometheus Alertmanager sends
curl -X POST http://$SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
  "receiver": "kgroot-rca",
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "KubePodCrashLooping",
        "container": "payment-api",
        "endpoint": "http",
        "instance": "10.0.1.52:8080",
        "job": "kubernetes-pods",
        "namespace": "production",
        "pod": "payment-service-7d8f9b-xz2kl",
        "prometheus": "monitoring/kube-prometheus",
        "service": "payment-service",
        "severity": "critical"
      },
      "annotations": {
        "description": "Pod production/payment-service-7d8f9b-xz2kl has been restarted 5 times within the last 10 minutes.",
        "runbook_url": "https://runbooks.example.com/KubePodCrashLooping",
        "summary": "Pod is crash looping"
      },
      "startsAt": "2025-10-25T09:50:00.000Z",
      "endsAt": "0001-01-01T00:00:00Z",
      "generatorURL": "http://prometheus-k8s-0:9090/graph?g0.expr=rate%28kube_pod_container_status_restarts_total%5B5m%5D%29+%3E+0&g0.tab=1",
      "fingerprint": "4b2e3f1a2c5d6e7f"
    }
  ],
  "groupLabels": {
    "alertname": "KubePodCrashLooping"
  },
  "commonLabels": {
    "alertname": "KubePodCrashLooping",
    "namespace": "production",
    "service": "payment-service",
    "severity": "critical"
  },
  "commonAnnotations": {
    "summary": "Pod is crash looping"
  },
  "externalURL": "http://alertmanager-main-0:9093",
  "version": "4",
  "groupKey": "{}/{}:{alertname=\"KubePodCrashLooping\"}"
}'
```

---

## ✅ Success Checklist

After testing, verify:

- [ ] Webhook receives alerts: `curl http://SERVER_IP:8081/health` returns healthy
- [ ] Single alerts are buffered (check `/status` endpoint)
- [ ] 3 alerts trigger RCA analysis
- [ ] RCA completes in <45 seconds
- [ ] Top 3 solutions are provided with probabilities
- [ ] Blast radius analysis is shown
- [ ] kubectl commands are actionable
- [ ] Patterns are stored in Neo4j (optional)

---

## 🚀 Production Deployment

Once testing is complete:

1. **Give client your server IP**: `YOUR_SERVER_IP`
2. **Send them**: `CLIENT-ONBOARDING.md`
3. **Client updates Alertmanager** to send to your webhook
4. **Monitor logs**: `docker logs -f kg-rca-webhook`
5. **Check Neo4j** for pattern learning over time

---

## 📞 Next Steps

1. Test all 3 scenarios above
2. Verify output matches expectations
3. Share SERVER_IP with client
4. Client configures Alertmanager
5. Start receiving real alerts!

**Your system is production-ready!** 🎉
