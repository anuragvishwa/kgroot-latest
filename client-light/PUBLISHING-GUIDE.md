# Publishing Guide for KG RCA Agent

This guide explains how to publish new versions of the KG RCA Agent for customers.

## Prerequisites

1. Docker Hub account: `anuragvishwa`
2. Docker installed and logged in: `docker login`
3. Helm 3.x installed
4. GitHub CLI (`gh`) for releases

## Publishing Workflow

### Step 1: Build and Push Docker Images

```bash
cd client-light

# Login to Docker Hub (first time only)
docker login

# Build and push all images to Docker Hub
./publish-images.sh
```

This will publish:
- `anuragvishwa/kg-alert-receiver:1.0.2` (and `:latest`)
- `anuragvishwa/kg-state-watcher:1.0.2` (and `:latest`)

### Step 2: Update Version Numbers

Update the version in these files:
- [helm-chart/Chart.yaml](helm-chart/Chart.yaml) - `version` and `appVersion`
- [helm-chart/values.yaml](helm-chart/values.yaml) - image `tag` fields
- [publish-images.sh](publish-images.sh) - `VERSION` variable

### Step 3: Package Helm Chart

```bash
cd client-light

# Package the chart
helm package helm-chart

# This creates: kg-rca-agent-1.0.2.tgz
```

### Step 4: Create GitHub Release

```bash
# Create and push git tag
git tag -a v1.0.2 -m "Release v1.0.2 - Description here"
git push origin v1.0.2

# Create GitHub release and upload Helm chart
gh release create v1.0.2 \
  kg-rca-agent-1.0.2.tgz \
  --title "KG RCA Agent v1.0.2" \
  --notes "Release notes here..."
```

### Step 5: Update Helm Repository Index

```bash
# Create/update index for Helm repository
helm repo index . --url https://github.com/anuragvishwa/kgroot-latest/releases/download/v1.0.2/

# Commit and push the index
git add index.yaml
git commit -m "Update Helm repository index for v1.0.2"
git push origin main
```

## Customer Installation

Customers can now install with a simple command:

```bash
# Download and install
wget https://github.com/anuragvishwa/kgroot-latest/releases/download/v1.0.2/kg-rca-agent-1.0.2.tgz

helm install kg-rca-agent kg-rca-agent-1.0.2.tgz \
  --set client.id=customer-cluster \
  --set client.kafka.brokers=98.90.147.12:9092 \
  --namespace observability \
  --create-namespace
```

All images are automatically pulled from Docker Hub - no building required!

## Version Strategy

- **Major.Minor.Patch** (e.g., 1.0.2)
- Image tags match chart versions
- Always maintain `:latest` tag pointing to newest stable release
- Document breaking changes in release notes

## Checklist

Before publishing a new version:

- [ ] All images built and pushed to Docker Hub
- [ ] Version numbers updated in Chart.yaml and values.yaml
- [ ] CHANGELOG.md updated with release notes
- [ ] Helm chart packaged successfully
- [ ] Git tag created and pushed
- [ ] GitHub release created with .tgz file
- [ ] Helm repository index updated
- [ ] Documentation reflects new version numbers
- [ ] Tested installation from scratch

## Rollback

If a release has issues:

```bash
# Delete GitHub release
gh release delete v1.0.2 --yes

# Delete git tag
git tag -d v1.0.2
git push origin :refs/tags/v1.0.2

# Revert to previous version in documentation
```

## Docker Hub Management

View published images:
- https://hub.docker.com/r/anuragvishwa/kg-alert-receiver/tags
- https://hub.docker.com/r/anuragvishwa/kg-state-watcher/tags

Delete old tags if needed (via Docker Hub web UI).

## Artifact Hub (Optional)

For wider distribution, publish to Artifact Hub:
1. Fork https://github.com/artifacthub/hub
2. Add entry in `repositories/kgroot.yaml`
3. Submit PR

See [ARTIFACT-HUB-GUIDE.md](../ARTIFACT-HUB-GUIDE.md) for details.
