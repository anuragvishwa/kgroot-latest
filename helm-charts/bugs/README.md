# Bugs Helm Chart

Kubernetes Bug Scenarios for RCA Testing - comprehensive production-like failures for thorough testing.

## Installation

```bash
# Add the repository
helm repo add kgroot https://anuragvishwa.github.io/kgroot/
helm repo update

# Install in buglab namespace
helm install bugs kgroot/bugs --namespace buglab --create-namespace

# Or install from source
helm install bugs ./helm-charts/bugs --namespace buglab --create-namespace
```

## What's Included

This chart deploys 19 different bug scenarios that generate realistic Kubernetes failures:

### Original Scenarios
- CrashLoopBackOff
- ImagePullBackOff
- Liveness Probe Failure
- Failed Mount (ConfigMap)
- Failed Scheduling
- OOM Killed

### Production-Like Scenarios
- Readiness Probe Failure
- PVC Pending (Storage)
- Secret Missing
- CPU Throttle
- DNS Failure
- Init Container Failure
- Port Conflict
- Disk Pressure
- Service Without Endpoints
- ConfigMap Outdated
- Memory Creep/Eviction
- Zombie Processes
- Terminating Stuck Pod

## Configuration

The `values.yaml` file contains all configurable options:

```yaml
namespace: buglab

scenarios:
  crashloop: true
  imagepullbackoff: true
  # ... enable/disable specific scenarios
```

## Verification

After installation, verify the scenarios are running:

```bash
# Check pods
kubectl get pods -n buglab -o wide

# View events
kubectl get events -n buglab --sort-by=.lastTimestamp | tail -n 50

# View logs from failing pods
kubectl logs -n buglab -l scenario=crashloop --tail=50
```

## Uninstallation

```bash
# Remove terminating-stuck pod if needed
kubectl patch pod terminating-stuck -n buglab -p '{"metadata":{"finalizers":null}}'

# Uninstall the chart
helm uninstall bugs -n buglab

# Delete namespace
kubectl delete namespace buglab
```

## RCA Testing

These scenarios generate data for:
- `events.normalized` - Kubernetes events
- `logs.normalized` - Container logs
- `state.k8s.*` - Resource state changes

Perfect for testing RCA pipelines, monitoring systems, and alerting mechanisms.

## Chart Details

- **Chart Version**: 1.0.0
- **App Version**: 1.0.0
- **Namespace**: buglab (configurable)

## Source

GitHub: https://github.com/anuragvishwa/kgroot
