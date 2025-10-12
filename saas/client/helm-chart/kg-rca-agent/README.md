# KG RCA Agent - Helm Chart

![Version: 1.0.1](https://img.shields.io/badge/Version-1.0.1-informational?style=flat-square)
![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square)
![AppVersion: 1.0.1](https://img.shields.io/badge/AppVersion-1.0.1-informational?style=flat-square)

[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/lumni)](https://artifacthub.io/packages/helm/lumni/kg-rca-agent)
> **Knowledge Graph RCA Agent** - Client-side data collection agent for Kubernetes observability and root cause analysis.

## Overview

The KG RCA Agent collects Kubernetes events, logs, and metrics from your cluster and sends them to the KG RCA platform for intelligent root cause analysis. Using a knowledge graph-based approach, the platform correlates events across your infrastructure to identify issues and suggest remediation.

## Features

- 📊 **Event Collection**: Captures Kubernetes events in real-time
- 📝 **Log Aggregation**: Collects pod logs for analysis
- 📈 **Metrics Export**: Exposes Prometheus metrics
- 🔄 **Auto-Discovery**: Automatically discovers cluster resources
- 🔐 **Secure**: SSL/TLS encryption for data transmission
- ⚡ **Lightweight**: Minimal resource footprint
- 🎯 **Configurable**: Fine-tune collection scope and behavior

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- Client ID and API Key (obtain from KG RCA platform)
- Network access to KG RCA server

## Installation

### Quick Start

# Add Lumni Helm repository
helm repo add lumni https://anuragvishwa.github.io/kgroot-latest
helm repo update


```bash
helm install my-rca-agent lumni/kg-rca-agent \
  --version 1.0.1 \
  --set client.id=<your-client-id> \
  --set client.apiKey=<your-api-key> \
  --set server.kafka.brokers="kafka.lumniverse.com:9093" \
  --set server.kafka.security.protocol="SSL"
```

### Using values.yaml

1. Create a `values.yaml` file:

```yaml
client:
  id: "client-prod-001"
  apiKey: "your-secure-api-key"
  namespace: "default"  # Namespace to monitor, or "all" for cluster-wide

server:
  kafka:
    brokers: "kafka.lumniverse.com:9093"
    security:
      protocol: "SSL"  # Use SSL for production

eventExporter:
  enabled: true
  resources:
    requests:
      memory: "64Mi"
      cpu: "50m"
    limits:
      memory: "128Mi"
      cpu: "100m"

vector:
  enabled: true
  resources:
    requests:
      memory: "128Mi"
      cpu: "100m"
    limits:
      memory: "256Mi"
      cpu: "200m"
```

2. Install the chart:

```bash
helm install my-rca-agent lumni/kg-rca-agent \
  --version 1.0.1 \
  --values values.yaml
```

## Configuration

### Required Values

| Parameter | Description | Example |
|-----------|-------------|---------|
| `client.id` | Unique client identifier | `"client-prod-001"` |
| `client.apiKey` | API key for authentication | `"your-api-key"` |
| `server.kafka.brokers` | Kafka broker address | `"kafka.lumniverse.com:9093"` |

### Optional Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `client.namespace` | Namespace to monitor ("all" for cluster-wide) | `"default"` |
| `server.kafka.security.protocol` | Kafka security protocol (PLAINTEXT or SSL) | `"SSL"` |
| `eventExporter.enabled` | Enable Kubernetes event collection | `true` |
| `vector.enabled` | Enable log collection with Vector | `true` |
| `eventExporter.resources.requests.memory` | Memory request for event exporter | `"64Mi"` |
| `eventExporter.resources.requests.cpu` | CPU request for event exporter | `"50m"` |
| `vector.resources.requests.memory` | Memory request for Vector | `"128Mi"` |
| `vector.resources.requests.cpu` | CPU request for Vector | `"100m"` |

### Advanced Configuration

#### SSL/TLS Configuration

For secure connections (recommended for production):

```yaml
server:
  kafka:
    brokers: "kafka.lumniverse.com:9093"
    security:
      protocol: "SSL"
      ssl:
        endpoint:
          identification:
            algorithm: "https"  # Verify server certificate
```

#### Resource Tuning

Adjust resources based on cluster size:

```yaml
# Small cluster (<50 pods)
eventExporter:
  resources:
    requests:
      memory: "64Mi"
      cpu: "50m"

# Large cluster (>200 pods)
eventExporter:
  resources:
    requests:
      memory: "256Mi"
      cpu: "200m"
```

#### Namespace Filtering

Monitor specific namespaces:

```yaml
client:
  namespace: "production"  # Single namespace
  # OR
  namespace: "all"  # Cluster-wide monitoring
```

## Verification

### Check Deployment Status

```bash
# Check pod status
kubectl get pods -l app=kg-rca-agent

# View logs
kubectl logs -l app=kg-rca-agent --tail=50 -f

# Check events
kubectl get events --field-selector involvedObject.name=kg-rca-agent
```

### Expected Output

When successfully connected, logs should show:

```
INFO  Starting KG RCA Agent
INFO  Client ID: client-prod-001
INFO  Connecting to Kafka: kafka.lumniverse.com:9093
INFO  Security protocol: SSL
INFO  Successfully connected to broker
INFO  Monitoring namespace: default
INFO  Event exporter started
INFO  Vector log collector started
```

## Troubleshooting

### Connection Issues

**Problem**: Agent can't connect to Kafka server

**Solution**:
1. Verify broker address: `nslookup kafka.lumniverse.com`
2. Check network connectivity: `telnet kafka.lumniverse.com 9093`
3. Verify API key is correct
4. Check pod logs: `kubectl logs -l app=kg-rca-agent`

### Authentication Errors

**Problem**: Authentication failed

**Solution**:
1. Verify `client.id` and `client.apiKey` are correct
2. Check if client is registered on the server
3. Ensure API key hasn't expired

### Resource Issues

**Problem**: Pods crashing due to OOM

**Solution**:
Increase memory limits:
```bash
helm upgrade my-rca-agent lumni/kg-rca-agent \
  --set eventExporter.resources.limits.memory="256Mi"
```

## Upgrading

```bash
# Update repository
helm repo update

# Upgrade to latest version
helm upgrade my-rca-agent lumni/kg-rca-agent

# Upgrade to specific version
helm upgrade my-rca-agent lumni/kg-rca-agent \
  --version 1.0.2
```

## Uninstalling

```bash
helm uninstall my-rca-agent
```

This will remove all resources created by the chart.

## Architecture

```
┌─────────────────────────────────────────────────┐
│           Kubernetes Cluster                    │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │  KG RCA Agent                           │   │
│  │                                         │   │
│  │  ┌──────────────┐  ┌──────────────┐   │   │
│  │  │Event Exporter│  │    Vector    │   │   │
│  │  │  (K8s Events)│  │ (Pod Logs)   │   │   │
│  │  └──────┬───────┘  └──────┬───────┘   │   │
│  │         │                  │           │   │
│  │         └──────────┬───────┘           │   │
│  │                    │                   │   │
│  │              ┌─────▼─────┐             │   │
│  │              │  Kafka    │             │   │
│  │              │ Producer  │             │   │
│  │              └─────┬─────┘             │   │
│  └────────────────────┼───────────────────┘   │
└───────────────────────┼───────────────────────┘
                        │ SSL/TLS
                        ▼
        ┌───────────────────────────────┐
        │    KG RCA Platform            │
        │  (kafka.lumniverse.com:9093)  │
        │                               │
        │  • Event Processing           │
        │  • Knowledge Graph Building   │
        │  • Root Cause Analysis        │
        │  • Alert Correlation          │
        └───────────────────────────────┘
```

## Security Considerations

- **SSL/TLS**: Always use SSL in production (`server.kafka.security.protocol: SSL`)
- **API Keys**: Store API keys in Kubernetes secrets (not in values.yaml)
- **RBAC**: Chart creates minimal required RBAC permissions
- **Network Policies**: Consider adding network policies to restrict egress

### Using Kubernetes Secrets for API Keys

```bash
# Create secret
kubectl create secret generic kg-rca-credentials \
  --from-literal=client-id=client-prod-001 \
  --from-literal=api-key=your-secure-api-key

# Reference in values.yaml
client:
  id:
    valueFrom:
      secretKeyRef:
        name: kg-rca-credentials
        key: client-id
  apiKey:
    valueFrom:
      secretKeyRef:
        name: kg-rca-credentials
        key: api-key
```

## Support

- **Documentation**: [Full documentation](https://github.com/anuragvishwa/kgroot-latest)
- **Issues**: [GitHub Issues](https://github.com/anuragvishwa/kgroot-latest/issues)
- **Email**: support@lumniverse.com

## License

Copyright © 2024 Lumniverse

## Changelog

### 1.0.1 (Production Release)
- Production-ready release of KG RCA Agent Helm chart
- Kubernetes event collection with real-time streaming
- Pod log aggregation with Vector
- SSL/TLS support for secure Kafka communication
- Configurable resource limits and requests
- RBAC with minimal required permissions
- Multi-namespace and cluster-wide monitoring support
- Comprehensive documentation and examples
---

Made with ❤️ by Lumniverse for better Kubernetes observability
