# Neo4j Connection Issues - Fix Guide

## Problem

Neo4j Browser shows:
```
ServiceUnavailable: WebSocket connection failure
WebSocket readyState is: 3
```

## Root Cause

Neo4j pod has **17 restarts**, causing port-forward connections to disconnect frequently.

```bash
kubectl get pod neo4j-0 -n observability
# Output: RESTARTS: 17
```

---

## Solution 1: Use Stable Port-Forward Script (Recommended)

### Step 1: Run the Keep-Alive Script

```bash
# Run the port-forward script
./scripts/neo4j-port-forward.sh

# Or with keep-alive mode (auto-restarts if connection drops)
./scripts/neo4j-port-forward.sh --keep-alive
```

This script:
- ✅ Kills old port-forwards
- ✅ Verifies Neo4j pod is running
- ✅ Starts fresh port-forward
- ✅ Tests connection
- ✅ Optionally auto-restarts if connection drops

### Step 2: Connect to Neo4j Browser

**URL:** http://localhost:7474/browser/

**Connection Details:**
```
Connect URL: bolt://localhost:7687
Username:    neo4j
Password:    anuragvishwa
```

**Important:** Make sure to use `bolt://localhost:7687` (not `bolt://127.0.0.1:63665`)

### Step 3: If Connection Drops

```bash
# Restart port-forward
./scripts/neo4j-port-forward.sh

# Or manually:
pkill -f "kubectl port-forward.*neo4j"
kubectl port-forward -n observability pod/neo4j-0 7474:7474 7687:7687 &
```

---

## Solution 2: Fix Neo4j Stability Issues

Neo4j is restarting frequently. Let's investigate and fix:

### Check Why Neo4j is Restarting

```bash
# Check pod events
kubectl describe pod neo4j-0 -n observability | grep -A 10 "Events:"

# Check previous crash logs
kubectl logs -n observability neo4j-0 --previous --tail=50

# Check current logs for errors
kubectl logs -n observability neo4j-0 --tail=100 | grep -i "error\|exception\|fatal"
```

### Common Causes and Fixes

#### Cause 1: Resource Constraints (OOMKilled)

```bash
# Check if Neo4j is OOMKilled
kubectl get pod neo4j-0 -n observability -o jsonpath='{.status.containerStatuses[0].lastState.terminated.reason}'
```

**Fix:** Increase memory limits

```bash
kubectl edit statefulset neo4j -n observability

# Add/modify under spec.template.spec.containers[0]:
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "1000m"

# Restart Neo4j
kubectl delete pod neo4j-0 -n observability
```

#### Cause 2: Liveness/Readiness Probe Failures

```bash
# Check probe configuration
kubectl get statefulset neo4j -n observability -o jsonpath='{.spec.template.spec.containers[0].livenessProbe}'
```

**Fix:** Adjust probe timings

```bash
kubectl edit statefulset neo4j -n observability

# Modify probe settings:
livenessProbe:
  tcpSocket:
    port: 7687
  initialDelaySeconds: 60  # Increase from 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 5      # Increase from 3
```

#### Cause 3: Storage/Volume Issues

```bash
# Check PVC status
kubectl get pvc -n observability | grep neo4j

# Check if volume is full
kubectl exec -n observability neo4j-0 -- df -h /data
```

**Fix:** Increase PVC size (if supported) or clean up old data

---

## Solution 3: Use NodePort (Alternative)

If port-forward keeps failing, use NodePort directly:

### Check NodePort Configuration

```bash
kubectl get svc neo4j-external -n observability
# Output shows: 7474:30474/TCP,7687:30687/TCP
```

### Access via NodePort

```bash
# Get Minikube IP
MINIKUBE_IP=$(minikube ip)
echo "Neo4j Browser: http://${MINIKUBE_IP}:30474"
echo "Bolt URL:      bolt://${MINIKUBE_IP}:30687"

# Example:
# http://192.168.49.2:30474
# bolt://192.168.49.2:30687
```

**Note:** This may not work if your Mac can't route to Minikube's internal IP.

---

## Solution 4: Access via kubectl exec (Always Works)

Use cypher-shell directly without browser:

```bash
# Execute queries directly
kubectl exec -n observability neo4j-0 -- \
  cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic) RETURN e.severity, count(*) AS count ORDER BY count DESC"

# Interactive shell
kubectl exec -it -n observability neo4j-0 -- \
  cypher-shell -u neo4j -p anuragvishwa
```

This bypasses port-forward entirely and always works.

---

## Verification Steps

### 1. Check Port-Forward is Running

```bash
lsof -i:7474,7687 | grep kubectl
# Should show two entries (7474 and 7687)
```

### 2. Test HTTP Connection

```bash
curl -s http://localhost:7474 | python3 -m json.tool
# Should return JSON with bolt_routing, neo4j_version, etc.
```

### 3. Test Bolt Connection (Python)

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "anuragvishwa"))
with driver.session() as session:
    result = session.run("RETURN 1 AS test")
    print(result.single()["test"])
driver.close()
```

### 4. Test via Neo4j Browser

1. Open http://localhost:7474/browser/
2. Click "Connect" (bolt://localhost:7687 should be pre-filled)
3. Enter credentials: `neo4j` / `anuragvishwa`
4. Run test query: `MATCH (n) RETURN count(n)`

---

## Current Status

```bash
# Check current connection status
kubectl get pod neo4j-0 -n observability
# Output: Running, RESTARTS: 17

# Port-forward status
ps aux | grep "kubectl port-forward" | grep neo4j | grep -v grep
# Output: PID 31762 (currently running)
```

**Port-forward is active** but will disconnect when Neo4j restarts.

---

## Recommended Actions

### Immediate Fix (Get Working Now)
```bash
# 1. Use the port-forward script
./scripts/neo4j-port-forward.sh

# 2. Keep browser tab open
# 3. If disconnected, re-run script
```

### Long-Term Fix (Prevent Restarts)
```bash
# 1. Investigate restart cause
kubectl describe pod neo4j-0 -n observability | tail -50

# 2. Increase resources (most likely cause)
kubectl edit statefulset neo4j -n observability
# Add memory limits: 2Gi

# 3. Restart Neo4j
kubectl delete pod neo4j-0 -n observability

# 4. Monitor
kubectl get pod neo4j-0 -n observability -w
```

---

## Quick Commands Reference

```bash
# Start port-forward
./scripts/neo4j-port-forward.sh

# Check if running
lsof -i:7474,7687 | grep kubectl

# Restart if needed
pkill -f "kubectl port-forward.*neo4j"
kubectl port-forward -n observability pod/neo4j-0 7474:7474 7687:7687 &

# Test connection
curl -s http://localhost:7474

# Query directly (bypass browser)
kubectl exec -n observability neo4j-0 -- \
  cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic) RETURN count(e)"

# Monitor Neo4j logs
kubectl logs -n observability neo4j-0 --tail=50 -f

# Check restart count
kubectl get pod neo4j-0 -n observability -o jsonpath='{.status.containerStatuses[0].restartCount}'
```

---

## Connection URLs Summary

| Method | URL | Stability | Notes |
|--------|-----|-----------|-------|
| Port-forward (HTTP) | http://localhost:7474/browser/ | Medium | Disconnects on Neo4j restart |
| Port-forward (Bolt) | bolt://localhost:7687 | Medium | For Neo4j Browser connection |
| NodePort (HTTP) | http://192.168.49.2:30474 | High | May not work on Mac |
| NodePort (Bolt) | bolt://192.168.49.2:30687 | High | May not work on Mac |
| kubectl exec | N/A (direct) | Very High | Always works, no browser |

**Recommended:** Use port-forward with the keep-alive script for best balance of usability and stability.

---

## Troubleshooting Specific Errors

### Error: "WebSocket readyState is: 3"
**Cause:** Port-forward died or Neo4j restarted
**Fix:** Restart port-forward script

### Error: "Connection refused"
**Cause:** Port-forward not running
**Fix:** Run `./scripts/neo4j-port-forward.sh`

### Error: "ServiceUnavailable"
**Cause:** Neo4j pod is not ready
**Fix:** Wait for pod to be ready: `kubectl wait --for=condition=ready pod/neo4j-0 -n observability`

### Error: Browser shows old connection URL (http://127.0.0.1:63665)
**Cause:** Browser cached old URL
**Fix:** Clear connection, use `bolt://localhost:7687`

---

## Summary

**Problem:** Neo4j restarting 17 times → Port-forward disconnects
**Quick Fix:** Run `./scripts/neo4j-port-forward.sh` and reconnect browser
**Long-term Fix:** Increase Neo4j memory limits to prevent restarts
**Always Works:** Use `kubectl exec` with `cypher-shell` for direct queries
