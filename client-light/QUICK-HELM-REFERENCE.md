# Quick Helm Reference

## For End Users

### Install kg-rca-agent

```bash
helm repo add kg-rca-agent https://anuragvishwa.github.io/kgroot-latest/
helm repo update
helm install kg-rca-agent kg-rca-agent/kg-rca-agent \
  --namespace observability \
  --create-namespace \
  --set kafka.bootstrapServers="your-kafka:9092"
```

### Verify Installation

```bash
helm list -n observability
kubectl get pods -n observability
```

### Upgrade

```bash
helm repo update
helm upgrade kg-rca-agent kg-rca-agent/kg-rca-agent -n observability
```

### Uninstall

```bash
helm uninstall kg-rca-agent -n observability
```

---

## For Maintainers

### Publish New Version

**Automatic (Recommended):**
```bash
# 1. Update version in helm-chart/Chart.yaml
# 2. Commit and push to main
git add helm-chart/Chart.yaml
git commit -m "chore: bump chart to v1.0.6"
git push origin main
# GitHub Actions will auto-publish
```

**Manual:**
```bash
cd client-light
./scripts/publish-helm.sh
```

### Test Locally

```bash
helm install test ./helm-chart --dry-run --debug
```

---

## Quick Links

- [Full Installation Guide](./INSTALLATION-GUIDE.md)
- [Publishing Guide](./HELM-PUBLISHING-GUIDE.md)
- [Setup Complete Report](./HELM-REPO-SETUP-COMPLETE.md)
