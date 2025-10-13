# Changelog

All notable changes to KG RCA Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2025-10-13

### Added
- Initial release of KG RCA Agent
- Vector DaemonSet for log collection and normalization
- Kubernetes Event Exporter for event monitoring
- State Watcher for resource and topology tracking
- Kafka integration for data streaming to KG RCA Server
- Helm chart with configurable values
- Support for plaintext and SSL Kafka connections
- Namespace filtering capability
- Comprehensive documentation (README, QUICK-START)
- Example configuration files

### Features
- **Log Collection**: Automatically collects logs from all pods
- **Event Monitoring**: Captures pod crashes, scheduling failures, etc.
- **State Tracking**: Monitors Deployment, Pod, Service, ConfigMap changes
- **Topology Discovery**: Builds relationships between resources
- **Flexible Deployment**: Works with any Kubernetes 1.20+ cluster
- **Resource Efficient**: ~200-500m CPU, ~400-800Mi memory per cluster

### Requirements
- Kubernetes 1.20 or higher
- Helm 3.x
- kubectl configured with cluster access
- KG RCA Server with accessible Kafka endpoint

### Known Issues
- None

### Security
- Supports SASL/SCRAM authentication
- SSL/TLS encryption for Kafka connections
- RBAC permissions limited to read-only access
- No privilege escalation required

## [Unreleased]

### Planned Features
- Automatic metric-based alerting
- Custom log filtering rules
- Multi-cluster support from single agent
- Cost optimization mode (reduced sampling)
- OpenTelemetry integration
- AWS EKS-specific optimizations
- GKE-specific optimizations

---

## Version History

- **1.0.1** (2025-10-13): Initial release
