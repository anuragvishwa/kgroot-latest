## 1.0.2 - 2025-10-14

- Fixed: Vector DaemonSet crash by providing `self_node_name` in `kubernetes_logs` and injecting `VECTOR_SELF_NODE_NAME` from `spec.nodeName`.
- Fixed: Added `namespaces` to RBAC ClusterRole resources to avoid 403 warnings when listing namespaces.

## 1.0.1 - 2025-10-xx

- Initial chart for SaaS client.

