## 1.0.3 - 2025-10-14

- Fixed: Vector DaemonSet crash by providing `self_node_name` in `kubernetes_logs` and injecting `VECTOR_SELF_NODE_NAME` from `spec.nodeName`.
- Fixed: Added `namespaces` to RBAC ClusterRole resources to avoid 403 warnings when listing namespaces.

## 1.0.4 - 2025-10-14

- Fixed: RBAC for state-watcher and event-exporter — added permissions for `events.k8s.io` (events) and `discovery.k8s.io` (EndpointSlice) plus `configmaps`.
- Fixed: Chart defaults align client topics with server topics (no client-id prefixes); uses `client.kafka.brokers` for bootstrap.

## 1.0.2 - 2025-10-xx

- Initial public chart in this branch; see Chart annotations for features.
