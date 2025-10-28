# Docker Hub Images for KG RCA Agent

All container images are published to Docker Hub for easy deployment.

## Available Images

### 1. Alert Receiver
Collects and forwards Prometheus alerts to the KG RCA server.

```bash
docker pull anuragvishwa/kg-alert-receiver:1.0.2
docker pull anuragvishwa/kg-alert-receiver:latest
```

**Docker Hub:** https://hub.docker.com/r/anuragvishwa/kg-alert-receiver

### 2. State Watcher
Monitors Kubernetes resource state and topology changes.

```bash
docker pull anuragvishwa/kg-state-watcher:1.0.2
docker pull anuragvishwa/kg-state-watcher:latest
```

**Docker Hub:** https://hub.docker.com/r/anuragvishwa/kg-state-watcher

## Third-Party Images

The Helm chart also uses these public images:

- **Event Exporter:** `opsgenie/kubernetes-event-exporter:v1.4`
- **Vector:** `timberio/vector:0.34.0-alpine`
- **Prometheus:** `prom/prometheus:latest`

## Versioning Strategy

- **Semantic Versioning:** Each release is tagged with version (e.g., `1.0.2`)
- **Latest Tag:** Always points to the most recent stable release
- **Chart Version Match:** Image versions match Helm chart versions

## Building Custom Images (Optional)

If you need to customize or build images locally:

```bash
# Clone the repository
git clone https://github.com/anuragvishwa/kgroot-latest.git
cd kgroot-latest/client-light

# Build and push (requires Docker Hub login)
docker login
./publish-images.sh
```

## For Minikube Development

If testing locally with Minikube:

```bash
# Use the local build script instead
./build-images.sh

# This builds images directly in Minikube's Docker daemon
# No need to push to Docker Hub for local testing
```

## Security

All images are:
- Built from official base images (Alpine Linux, Distroless)
- Scanned for vulnerabilities
- Run as non-root users
- Use minimal attack surface

## Support

For issues or questions:
- GitHub Issues: https://github.com/anuragvishwa/kgroot-latest/issues
- Email: support@lumniverse.com
