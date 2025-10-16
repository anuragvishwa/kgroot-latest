Kubernetes Bug Scenarios (minikube-ready)

Minimal, focused manifests to generate common K8s failures so your client-light pipeline produces messages on events.normalized, logs.normalized, and state.* topics.

- Namespace: `buglab`
- Apply all: `kubectl apply -k bugs`
- Delete all: `kubectl delete -k bugs`

Scenarios
- CrashLoopBackOff: Fast-crashing container
- ImagePullBackOff: Invalid image tag
- LivenessFail: Probe to wrong port/path
- FailedMount: Mount non-existent ConfigMap
- FailedScheduling: Impossible nodeSelector
- OOMKilled (optional): Stress memory with low limit

Quick Verify
- Events in namespace: `kubectl get events -n buglab --sort-by=.lastTimestamp | tail -n 30`
- Logs from a crashing pod: `kubectl logs -n buglab -l scenario=crashloop --tail=50`
- Topics on server (examples):
  - `events.normalized` increases with new failures
  - `logs.normalized` grows from failing pods
  - `state.k8s.resource/topology` reflect resource churn

Notes
- All manifests are safe in minikube and isolated to `buglab`.
- OOMKilled needs `polinux/stress` image; skip if image pulls are restricted.
