# Kubernetes Bug Scenarios for RCA Testing

Comprehensive, production-like K8s failure scenarios to thoroughly test your client-light RCA pipeline. These manifests generate realistic failures across events.normalized, logs.normalized, and state.* topics.

## Quick Start

**Namespace:** `buglab`

```bash
# Deploy all scenarios
kubectl apply -k bugs

# Or install via Helm
helm repo add kgroot https://anuragvishwa.github.io/kgroot/
helm install bugs kgroot/bugs --namespace buglab --create-namespace

# Delete all
kubectl delete -k bugs
# or
helm uninstall bugs -n buglab
```

## Bug Scenarios

### Original Scenarios
1. **CrashLoopBackOff** (`crashloop.yaml`)
   - Fast-crashing container that continuously restarts
   - Tests: Container restart loops, backoff timing, restart count metrics

2. **ImagePullBackOff** (`imagepullbackoff.yaml`)
   - Invalid image tag causing pull failures
   - Tests: Image pull errors, registry connectivity issues

3. **LivenessFail** (`liveness-fail.yaml`)
   - Liveness probe pointing to wrong port/path
   - Tests: Container health check failures, restart policies

4. **FailedMount** (`failedmount.yaml`)
   - Attempting to mount non-existent ConfigMap
   - Tests: Volume mount failures, pod startup issues

5. **FailedScheduling** (`failed-scheduling.yaml`)
   - Impossible nodeSelector preventing scheduling
   - Tests: Scheduler failures, unschedulable pods

6. **OOMKilled** (`oomkill.yaml`)
   - Memory stress causing out-of-memory kills
   - Tests: Resource limit enforcement, OOM events

### New Production-Like Scenarios

7. **ReadinessFail** (`readiness-fail.yaml`)
   - Readiness probe to non-existent endpoint
   - Tests: Service mesh issues, traffic routing failures

8. **PVC Pending** (`pvc-pending.yaml`)
   - PersistentVolumeClaim with non-existent StorageClass
   - Tests: Storage provisioning failures, pod stuck in pending

9. **Secret Missing** (`secret-missing.yaml`)
   - Pod referencing non-existent Secret
   - Tests: Configuration errors, secret management issues

10. **CPU Throttle** (`cpu-throttle.yaml`)
    - CPU-intensive workload exceeding limits
    - Tests: CPU throttling, performance degradation

11. **DNS Failure** (`network-dns-fail.yaml`)
    - DNS lookup failures for internal/external services
    - Tests: Network connectivity, DNS resolution issues

12. **Init Container Fail** (`init-container-fail.yaml`)
    - Failing init container blocking main container
    - Tests: Initialization dependencies, migration failures

13. **Port Conflict** (`port-conflict.yaml`)
    - Multiple containers attempting to bind same port
    - Tests: Port binding conflicts, network configuration

14. **Disk Pressure** (`disk-pressure.yaml`)
    - Rapid log writing causing disk pressure
    - Tests: Disk space issues, eviction due to disk pressure

15. **Service No Endpoints** (`service-endpoint-fail.yaml`)
    - Service with no matching backend pods
    - Tests: Service discovery failures, endpoint availability

16. **ConfigMap Outdated** (`configmap-immutable-fail.yaml`)
    - Immutable ConfigMap with outdated configuration
    - Tests: Configuration drift, immutable config updates

17. **Memory Creep/Eviction** (`evicted-pod.yaml`)
    - Gradually increasing memory usage triggering eviction
    - Tests: Memory leaks, pod eviction policies

18. **Zombie Process** (`zombie-process.yaml`)
    - Creating orphaned zombie processes
    - Tests: Process management, PID namespace issues

19. **Terminating Stuck** (`terminating-stuck.yaml`)
    - Pod stuck in Terminating state with finalizers
    - Tests: Graceful shutdown issues, finalizer deadlocks

## Verification Commands

### View Events
```bash
# Recent events sorted by time
kubectl get events -n buglab --sort-by=.lastTimestamp | tail -n 50

# Events for specific scenario
kubectl get events -n buglab --field-selector involvedObject.name=crashloop-fast-exit
```

### Check Pod Status
```bash
# All pods in buglab
kubectl get pods -n buglab -o wide

# Pods by scenario
kubectl get pods -n buglab -l scenario=crashloop
kubectl get pods -n buglab -l scenario=pvc-pending
kubectl get pods -n buglab -l scenario=dns-fail
```

### View Logs
```bash
# Logs from crashing pod
kubectl logs -n buglab -l scenario=crashloop --tail=50

# Logs from DNS failure pod
kubectl logs -n buglab dns-lookup-fail --tail=50

# Logs from init container failure
kubectl logs -n buglab init-container-fail -c failing-init
```

### Check Resource Usage
```bash
# Pod resource metrics (requires metrics-server)
kubectl top pods -n buglab

# Describe pod for detailed status
kubectl describe pod -n buglab cpu-throttle
```

### Monitor Kafka Topics
Verify your client-light pipeline processes these failures:
- `events.normalized` - Kubernetes events from all scenarios
- `logs.normalized` - Container logs from failing pods
- `state.k8s.resource/topology` - Resource state changes
- `state.k8s.pod` - Pod state transitions
- `state.k8s.service` - Service endpoint changes

## RCA Testing Matrix

| Scenario | Events | Logs | State Changes | Metrics |
|----------|--------|------|---------------|---------|
| CrashLoopBackOff | ✓ | ✓ | ✓ | Restart count |
| ImagePullBackOff | ✓ | ✗ | ✓ | Pull errors |
| LivenessFail | ✓ | ✓ | ✓ | Health checks |
| FailedMount | ✓ | ✗ | ✓ | Volume errors |
| FailedScheduling | ✓ | ✗ | ✓ | Unschedulable |
| OOMKilled | ✓ | ✓ | ✓ | Memory usage |
| ReadinessFail | ✓ | ✓ | ✓ | Ready status |
| PVC Pending | ✓ | ✗ | ✓ | Storage errors |
| Secret Missing | ✓ | ✗ | ✓ | Config errors |
| CPU Throttle | ✗ | ✓ | ✗ | CPU throttle % |
| DNS Failure | ✗ | ✓ | ✗ | Connection errors |
| Init Container Fail | ✓ | ✓ | ✓ | Init errors |
| Port Conflict | ✓ | ✓ | ✓ | Bind errors |
| Disk Pressure | ✓ | ✓ | ✓ | Disk usage |
| Service No Endpoints | ✓ | ✓ | ✓ | Endpoint count |
| ConfigMap Outdated | ✗ | ✓ | ✗ | Config drift |
| Memory Creep | ✓ | ✓ | ✓ | Eviction events |
| Zombie Process | ✗ | ✓ | ✗ | Process count |
| Terminating Stuck | ✓ | ✓ | ✓ | Finalizer status |

## Notes

- All manifests are safe for minikube/kind and isolated to `buglab` namespace
- Scenarios use minimal resources (10m CPU, 16-64Mi memory)
- Some scenarios (OOMKill, disk-pressure) are resource-intensive but bounded
- The terminating-stuck pod has a finalizer and may need manual cleanup:
  ```bash
  kubectl patch pod terminating-stuck -n buglab -p '{"metadata":{"finalizers":null}}'
  ```
- For production testing, adjust resource limits and timing parameters as needed
