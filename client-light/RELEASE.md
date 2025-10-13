# Release Instructions

## Preparing for GitHub Release

### 1. Package Helm Chart

```bash
cd client-light
helm package helm-chart/kg-rca-agent
# Creates: kg-rca-agent-1.0.1.tgz
```

### 2. Create Release Archive

```bash
# Create release tarball with all files
tar -czf kg-rca-agent-v1.0.1.tar.gz \
  helm-chart/ \
  README.md \
  QUICK-START.md \
  example-values.yaml \
  .gitignore

# Verify contents
tar -tzf kg-rca-agent-v1.0.1.tar.gz
```

### 3. Generate Checksums

```bash
# SHA256 checksums
shasum -a 256 kg-rca-agent-v1.0.1.tar.gz > checksums.txt
shasum -a 256 kg-rca-agent-1.0.1.tgz >> checksums.txt

cat checksums.txt
```

### 4. Create GitHub Release

```bash
# Tag the release
git tag -a v1.0.1 -m "Release v1.0.1 - Initial client agent"
git push origin v1.0.1

# Create release using GitHub CLI
gh release create v1.0.1 \
  --title "KG RCA Agent v1.0.1" \
  --notes "Initial release of KG RCA Agent for Kubernetes

**Features:**
- Vector log collection
- Kubernetes event monitoring
- Resource state tracking
- Topology monitoring
- Kafka integration

**Installation:**
See QUICK-START.md for 5-minute setup instructions.

**Requirements:**
- Kubernetes 1.20+
- Helm 3.x
- KG RCA Server endpoint

**Support:** support@lumniverse.com" \
  kg-rca-agent-v1.0.1.tar.gz \
  kg-rca-agent-1.0.1.tgz \
  checksums.txt
```

### 5. Test Installation from GitHub

```bash
# Download release
wget https://github.com/your-org/kg-rca-agent/releases/download/v1.0.1/kg-rca-agent-v1.0.1.tar.gz

# Extract
tar -xzf kg-rca-agent-v1.0.1.tar.gz

# Install
cd kg-rca-agent-v1.0.1
helm install kg-rca-agent ./helm-chart/kg-rca-agent \
  --values example-values.yaml \
  --namespace observability \
  --create-namespace
```

## Publishing to Helm Repository (Optional)

### Option 1: GitHub Pages

```bash
# Create gh-pages branch
git checkout --orphan gh-pages
git rm -rf .

# Add Helm chart
helm package ../client-light/helm-chart/kg-rca-agent
helm repo index . --url https://your-org.github.io/kg-rca-agent

# Commit and push
git add .
git commit -m "Initial Helm repository"
git push origin gh-pages

# Users can now add:
# helm repo add lumniverse https://your-org.github.io/kg-rca-agent
```

### Option 2: Artifact Hub

1. Go to https://artifacthub.io
2. Sign in with GitHub
3. Add repository
4. Follow verification steps
5. Chart will be publicly discoverable

## Version Numbering

Use semantic versioning: MAJOR.MINOR.PATCH

- **MAJOR**: Breaking changes (e.g., 2.0.0)
- **MINOR**: New features, backwards compatible (e.g., 1.1.0)
- **PATCH**: Bug fixes (e.g., 1.0.1)

## Checklist Before Release

- [ ] Update Chart.yaml version
- [ ] Update README.md with new features
- [ ] Test installation on clean cluster
- [ ] Verify connectivity to server
- [ ] Check all pods start successfully
- [ ] Verify data reaches server
- [ ] Update CHANGELOG.md
- [ ] Tag release in git
- [ ] Create GitHub release
- [ ] Announce in documentation/Slack

## Rolling Back a Release

```bash
# Delete tag locally
git tag -d v1.0.1

# Delete tag remotely
git push origin :refs/tags/v1.0.1

# Delete GitHub release
gh release delete v1.0.1
```
