# Alertmanager Integration Fix

## Problem Identified

The `raw.prom.alerts` topic was not receiving data because **Alertmanager was not configured to send alerts to the Vector webhook endpoint**.

### Root Cause Analysis

1. **Vector webhook was properly configured** ✅
   - HTTP server listening on `0.0.0.0:9090`
   - Kubernetes Service: `kg-rca-agent-kg-rca-agent-alert-webhook.observability.svc:9090`
   - Sinks configured for both `raw.prom.alerts` and `events.normalized`

2. **Alertmanager configuration was incomplete** ❌
   - Only had a "null" receiver (discards all alerts)
   - No webhook receiver configured
   - Default route sent everything to "null"

## Solution Applied

Updated Alertmanager configuration to include the KG RCA webhook receiver:

```yaml
receivers:
- name: "null"
- name: "kg-rca-webhook"
  webhook_configs:
  - url: 'http://kg-rca-agent-kg-rca-agent-alert-webhook.observability.svc.cluster.local:9090'
    send_resolved: true
    max_alerts: 0

route:
  group_by:
  - namespace
  group_interval: 5m
  group_wait: 30s
  receiver: "kg-rca-webhook"  # Changed from "null" to "kg-rca-webhook"
  repeat_interval: 12h
  routes:
  - matchers:
    - alertname = "Watchdog"
    receiver: "null"  # Watchdog still goes to null
```

## Changes Made

1. **Updated Alertmanager Secret**
   ```bash
   kubectl create secret generic alertmanager-prom-kube-prometheus-stack-alertmanager \
     -n monitoring \
     --from-file=alertmanager.yaml=./alertmanager-config-patch.yaml \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

2. **Restarted Alertmanager StatefulSet**
   ```bash
   kubectl rollout restart statefulset -n monitoring \
     alertmanager-prom-kube-prometheus-stack-alertmanager
   ```

## Verification

Tested with a real alert via Alertmanager API:

```bash
curl -X POST http://prom-kube-prometheus-stack-alertmanager.monitoring.svc.cluster.local:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{"labels":{"alertname":"RealTestAlert","severity":"critical","namespace":"test"},
       "annotations":{"summary":"This is a real test alert from Alertmanager"},
       "startsAt":"2025-10-16T02:20:00Z"}]'
```

**Results:**
- ✅ Alert received by Alertmanager
- ✅ Forwarded to Vector webhook (`receiver: "kg-rca-webhook"`)
- ✅ Stored in `raw.prom.alerts` topic (raw payload)
- ✅ Normalized and published to `events.normalized` topic (with `etype: "prom.alert"`)

## About the "raw.events" Topic

Note: There is **no `raw.events` topic** in the configuration. The actual topics are:
- ✅ `raw.k8s.events` - K8s events from event-exporter (working)
- ✅ `raw.prom.alerts` - Prometheus/Alertmanager alerts (now working)

## Data Flow Summary

```
Prometheus Alerts → Alertmanager → Vector Webhook (port 9090)
                                        │
                                        ├─→ raw.prom.alerts (raw payload)
                                        └─→ events.normalized (normalized)
                                                   ↓
                                          alerts-enricher consumes
                                                   ↓
                                          alerts.enriched (output)
```

```
K8s Events → event-exporter
                 │
                 ├─→ raw.k8s.events (raw)
                 └─→ events.normalized (normalized)
```

## Files Created

1. [alertmanager-config-patch.yaml](alertmanager-config-patch.yaml) - New Alertmanager configuration

## Current Status

🟢 **All topics receiving data:**
- `raw.prom.alerts` - Prometheus alerts (fixed)
- `raw.k8s.events` - Kubernetes events (working)
- `events.normalized` - Both alert types normalized (working)
- `alerts.enriched` - Enriched alerts (working via alert-receiver)