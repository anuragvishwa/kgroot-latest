# Helm Chart Publishing Guide

This guide explains how the kg-rca-agent Helm chart is published and how to use it.

## Published Helm Repository

The chart is published to GitHub Pages and available at:

**Repository URL**: `https://anuragvishwa.github.io/kgroot-latest/`

## For Users: Installing the Chart

### Quick Start

```bash
# Add the Helm repository
helm repo add kg-rca-agent https://anuragvishwa.github.io/kgroot-latest/
helm repo update

# Search for available charts
helm search repo kg-rca-agent

# Install the chart
helm install kg-rca-agent kg-rca-agent/kg-rca-agent \
  --namespace observability \
  --create-namespace \
  --set kafka.bootstrapServers="your-kafka:9092"
```

### View Available Versions

```bash
helm search repo kg-rca-agent --versions
```

### Install Specific Version

```bash
helm install kg-rca-agent kg-rca-agent/kg-rca-agent \
  --version 1.0.5 \
  --namespace observability \
  --create-namespace
```

## For Maintainers: Publishing New Versions

### Option 1: Automated Publishing (GitHub Actions)

The chart is automatically published when changes are pushed to the `main` branch.

**Trigger automatic publishing:**

```bash
# Make changes to the chart
vim helm-chart/Chart.yaml  # Update version

# Commit and push
git add helm-chart/
git commit -m "chore: bump chart version to 1.0.6"
git push origin main
```

The GitHub Actions workflow will:
1. Package the chart
2. Update the Helm repository index
3. Push to gh-pages branch
4. Make it available at the repository URL

**Manual trigger via GitHub Actions:**

Go to: https://github.com/anuragvishwa/kgroot-latest/actions/workflows/publish-helm-chart.yml
- Click "Run workflow"
- Optionally specify a chart version
- Click "Run workflow"

### Option 2: Manual Publishing (Local Script)

Use the provided script to publish from your local machine:

```bash
cd client-light
./scripts/publish-helm.sh
```

The script will:
1. Package the Helm chart
2. Copy to gh-pages-content directory
3. Update the Helm repository index
4. Commit and push to gh-pages branch

### Publishing Checklist

Before publishing a new version:

- [ ] Update [helm-chart/Chart.yaml](./helm-chart/Chart.yaml):
  - Bump `version` field
  - Update `appVersion` if images changed
  - Update `artifacthub.io/changes` annotations
- [ ] Update [CHANGELOG.md](./CHANGELOG.md)
- [ ] Test the chart locally:
  ```bash
  helm install test-release ./helm-chart --dry-run --debug
  ```
- [ ] Verify all images are pushed to Docker Hub
- [ ] Run the publish script or merge to main

### Version Numbering

Follow semantic versioning (SemVer):

- **Major** (1.x.x): Breaking changes
- **Minor** (x.1.x): New features, backward compatible
- **Patch** (x.x.1): Bug fixes, backward compatible

Example:
- `1.0.5` → `1.0.6`: Bug fix
- `1.0.5` → `1.1.0`: New feature
- `1.0.5` → `2.0.0`: Breaking change

## Repository Structure

```
kgroot-latest/
├── client-light/
│   ├── helm-chart/              # Source Helm chart
│   │   ├── Chart.yaml           # Chart metadata (UPDATE VERSION HERE)
│   │   ├── values.yaml          # Default values
│   │   └── templates/           # Kubernetes templates
│   └── scripts/
│       └── publish-helm.sh      # Publishing script
├── gh-pages-content/            # GitHub Pages content
│   ├── index.yaml               # Helm repository index
│   ├── kg-rca-agent-1.0.5.tgz  # Chart packages
│   └── README.md                # Repository README
└── .github/workflows/
    └── publish-helm-chart.yml   # GitHub Actions workflow
```

## GitHub Pages Setup

The Helm repository is hosted on GitHub Pages from the `gh-pages` branch.

### Initial Setup (Already Configured)

If you need to set up GitHub Pages for a new repository:

1. Go to repository Settings → Pages
2. Select Source: `gh-pages` branch
3. Select folder: `/ (root)`
4. Click Save

GitHub Pages will be available at: `https://<username>.github.io/<repository>/`

### Verifying GitHub Pages

After publishing, verify the repository is accessible:

```bash
# Check if index.yaml is accessible
curl https://anuragvishwa.github.io/kgroot-latest/index.yaml

# Check if chart package is accessible
curl -I https://anuragvishwa.github.io/kgroot-latest/kg-rca-agent-1.0.5.tgz
```

## Artifact Hub Integration

To make your chart discoverable on [Artifact Hub](https://artifacthub.io/):

### 1. Submit Repository

1. Go to https://artifacthub.io/
2. Sign in with your GitHub account
3. Go to Control Panel → Add repository
4. Fill in:
   - **Name**: kg-rca-agent
   - **URL**: https://anuragvishwa.github.io/kgroot-latest/
   - **Type**: Helm charts
5. Click "Add"

### 2. Verify Listing

After submission (takes a few minutes):
- Search for "kg-rca-agent" on Artifact Hub
- Your chart should appear in search results
- Verify all metadata is correctly displayed

### 3. Claim Ownership

1. Go to your chart page on Artifact Hub
2. Click "Claim ownership"
3. Follow verification steps
4. This allows you to feature the chart and add additional metadata

## Troubleshooting

### Chart Not Appearing After Publishing

**Wait 1-2 minutes** for GitHub Pages to deploy.

Check deployment status:
```bash
# Verify gh-pages branch exists
git ls-remote origin gh-pages

# Verify index.yaml was updated
curl https://anuragvishwa.github.io/kgroot-latest/index.yaml | grep version
```

### Users Can't Add Repository

Verify GitHub Pages is enabled and accessible:

```bash
curl -I https://anuragvishwa.github.io/kgroot-latest/
# Should return 200 OK
```

If getting 404, check:
1. GitHub Pages is enabled in repository settings
2. gh-pages branch exists
3. index.yaml exists in gh-pages branch

### Chart Package Not Found

Verify the chart package URL in index.yaml matches GitHub Pages URL:

```yaml
# index.yaml should have:
urls:
  - https://anuragvishwa.github.io/kgroot-latest/kg-rca-agent-1.0.5.tgz
```

Update if needed:
```bash
cd gh-pages-content
helm repo index . --url https://anuragvishwa.github.io/kgroot-latest/
git add index.yaml
git commit -m "fix: update chart URLs"
git push origin gh-pages
```

## Alternative Publishing Methods

### OCI Registry (Docker Hub)

For OCI-based distribution:

```bash
# Login to Docker Hub
echo $DOCKER_PASSWORD | helm registry login registry-1.docker.io -u anuragvishwa --password-stdin

# Package and push
helm package helm-chart/
helm push kg-rca-agent-1.0.5.tgz oci://registry-1.docker.io/anuragvishwa
```

Users install with:
```bash
helm install kg-rca-agent oci://registry-1.docker.io/anuragvishwa/kg-rca-agent --version 1.0.5
```

### GitHub Container Registry (GHCR)

```bash
# Login to GHCR
echo $GITHUB_TOKEN | helm registry login ghcr.io -u anuragvishwa --password-stdin

# Push chart
helm push kg-rca-agent-1.0.5.tgz oci://ghcr.io/anuragvishwa
```

## Maintenance

### Cleanup Old Versions

Keep the last 5 versions to reduce repository size:

```bash
cd gh-pages-content

# List all chart versions
ls -lt kg-rca-agent-*.tgz

# Remove old versions (keep last 5)
ls -t kg-rca-agent-*.tgz | tail -n +6 | xargs rm

# Update index
helm repo index . --url https://anuragvishwa.github.io/kgroot-latest/

# Commit
git add .
git commit -m "chore: cleanup old chart versions"
git push origin gh-pages
```

### Force Rebuild Index

If the index gets corrupted:

```bash
cd gh-pages-content

# Remove old index
rm index.yaml

# Rebuild from scratch
helm repo index . --url https://anuragvishwa.github.io/kgroot-latest/

# Commit
git add index.yaml
git commit -m "chore: rebuild Helm repository index"
git push origin gh-pages
```

## Support

- **Repository**: https://github.com/anuragvishwa/kgroot-latest
- **Issues**: https://github.com/anuragvishwa/kgroot-latest/issues
- **Helm Docs**: https://helm.sh/docs/
- **Artifact Hub**: https://artifacthub.io/
