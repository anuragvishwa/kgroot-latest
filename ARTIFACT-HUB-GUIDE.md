# Publishing to Artifact Hub Guide

## Overview

This guide walks you through publishing the KG RCA Agent Helm chart to Artifact Hub, making it easy for users to discover and install your chart.

## What is Artifact Hub?

Artifact Hub is a centralized repository for Kubernetes packages (Helm charts, operators, etc.). Think of it as the "npm registry" for Kubernetes.

## Prerequisites

- [x] GitHub repository: `https://github.com/anuragvishwa/kgroot-latest`
- [x] GitHub account connected to Artifact Hub
- [ ] Helm chart prepared (we'll do this)
- [ ] GitHub release/tag created

## Architecture

```
Your GitHub Repo
       │
       │ (1) Push code with Helm chart
       ↓
GitHub (main branch)
       │
       │ (2) Create release/tag
       ↓
GitHub Release (v0.1.0)
       │
       │ (3) Artifact Hub discovers via webhook
       ↓
Artifact Hub
       │
       │ (4) Users discover and install
       ↓
kubectl/helm install
```

## Step-by-Step Process

### Step 1: Commit and Push Helm Chart

We've prepared everything you need. Now let's commit:

```bash
# Add all Helm chart files
git add saas/client/helm-chart/kg-rca-agent/

# Add Artifact Hub metadata
git add artifacthub-repo.yml

# Add documentation
git add ARTIFACT-HUB-GUIDE.md

# Commit
git commit -m "feat: Prepare KG RCA Agent Helm chart for Artifact Hub

- Add comprehensive README.md for chart documentation
- Update Chart.yaml with Artifact Hub annotations
- Add artifacthub-repo.yml for repository metadata
- Chart version: 0.1.0
- Ready for Artifact Hub publishing"

# Push to GitHub
git push origin main
```

### Step 2: Create GitHub Release

There are two ways to create a release:

#### Option A: Using GitHub CLI (Recommended)

```bash
# Install gh CLI if not installed
# macOS: brew install gh
# Login: gh auth login

# Create release
gh release create v0.1.0 \
  --title "KG RCA Agent v0.1.0" \
  --notes "## KG RCA Agent v0.1.0 - Initial Release

### Features
- ✨ Kubernetes event collection
- 📝 Pod log aggregation with Vector
- 🔐 SSL/TLS support for secure communication
- 📊 Prometheus metrics export
- ⚙️ Configurable resource limits
- 🎯 Namespace-scoped or cluster-wide monitoring

### Installation

\`\`\`bash
helm install my-rca-agent oci://ghcr.io/anuragvishwa/helm-charts/kg-rca-agent \\
  --version 0.1.0 \\
  --set client.id=<your-client-id> \\
  --set client.apiKey=<your-api-key> \\
  --set server.kafka.brokers=\"kafka.lumniverse.com:9093\" \\
  --set server.kafka.security.protocol=\"SSL\"
\`\`\`

### Documentation
- [Chart README](https://github.com/anuragvishwa/kgroot-latest/blob/main/saas/client/helm-chart/kg-rca-agent/README.md)
- [Quick Start Guide](https://github.com/anuragvishwa/kgroot-latest/blob/main/client/QUICKSTART.md)

### What's Next
- Monitor your Kubernetes clusters
- Get intelligent root cause analysis
- Correlate events across your infrastructure
"
```

#### Option B: Using GitHub Web UI

1. Go to: `https://github.com/anuragvishwa/kgroot-latest/releases/new`
2. Click "Choose a tag" → Type: `v0.1.0` → Click "Create new tag: v0.1.0 on publish"
3. Release title: `KG RCA Agent v0.1.0`
4. Description: Copy the release notes from Option A above
5. Click "Publish release"

### Step 3: Configure Artifact Hub Repository

1. **Go to Artifact Hub Console**: https://artifacthub.io/control-panel
2. **Add Repository**:
   - Click "Add repository"
   - Choose "Helm charts"
   - Repository type: "Helm charts repository"
   - **Name**: `kg-rca-charts` (or your preferred name)
   - **URL**: `https://anuragvishwa.github.io/kgroot-latest/` (we'll set this up)
   - Click "Add"

Wait! We need to set up GitHub Pages first...

### Step 3b: Set Up GitHub Pages for Helm Repository (Alternative Method)

Actually, there's a simpler way using Artifact Hub's **GitHub integration**:

1. **Go to Artifact Hub**: https://artifacthub.io/control-panel
2. **Add Repository**:
   - Repository type: **"Helm charts repository from Git Hub repository"**
   - GitHub repository: `https://github.com/anuragvishwa/kgroot-latest`
   - Branch: `main`
   - Path: `saas/client/helm-chart` (directory containing your charts)
   - Click "Add"

This method is simpler - Artifact Hub will automatically scan your GitHub repository!

### Step 4: Verify on Artifact Hub

After a few minutes (Artifact Hub scans every hour):
1. Go to: https://artifacthub.io/packages/search?ts_query=kg-rca-agent
2. You should see your chart!
3. Click on it to see the README and installation instructions

### Step 5: Install Chart from Artifact Hub

Users can now install your chart:

```bash
# Add your repository
helm repo add kg-rca https://anuragvishwa.github.io/kgroot-latest

# Update repositories
helm repo update

# Install chart
helm install my-rca-agent kg-rca/kg-rca-agent \
  --version 0.1.0 \
  --set client.id=<client-id> \
  --set client.apiKey=<api-key> \
  --set server.kafka.brokers="kafka.lumniverse.com:9093"
```

## Alternative: Using Chart Releaser (Recommended for Multiple Charts)

If you plan to publish multiple charts, use `chart-releaser`:

### Step 1: Install Chart Releaser

```bash
# macOS
brew install chart-releaser

# Linux
curl -sSL https://github.com/helm/chart-releaser/releases/download/v1.5.0/chart-releaser_1.5.0_linux_amd64.tar.gz | tar xz
sudo mv cr /usr/local/bin/
```

### Step 2: Package and Release

```bash
# Package the chart
helm package saas/client/helm-chart/kg-rca-agent

# This creates: kg-rca-agent-0.1.0.tgz

# Upload to GitHub Release
cr upload \
  --owner anuragvishwa \
  --git-repo kgroot-latest \
  --token $GITHUB_TOKEN \
  --package-path .

# Update index
cr index \
  --owner anuragvishwa \
  --git-repo kgroot-latest \
  --token $GITHUB_TOKEN \
  --index-path . \
  --package-path . \
  --push
```

### Step 3: Enable GitHub Pages

1. Go to: `https://github.com/anuragvishwa/kgroot-latest/settings/pages`
2. Source: `gh-pages` branch
3. Save

Your charts will be available at: `https://anuragvishwa.github.io/kgroot-latest/`

## GitHub Actions (Automated Publishing)

For continuous publishing, add this GitHub Action:

```yaml
# .github/workflows/release-chart.yml
name: Release Helm Chart

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v3
        with:
          fetch-depth: 0

      - name: Configure Git
        run: |
          git config user.name "$GITHUB_ACTOR"
          git config user.email "$GITHUB_ACTOR@users.noreply.github.com"

      - name: Install Helm
        uses: azure/setup-helm@v3
        with:
          version: v3.12.0

      - name: Run chart-releaser
        uses: helm/chart-releaser-action@v1.5.0
        with:
          charts_dir: saas/client/helm-chart
        env:
          CR_TOKEN: "${{ secrets.GITHUB_TOKEN }}"
```

## Updating the Chart

When you make changes:

1. **Update version** in `Chart.yaml`:
   ```yaml
   version: 0.2.0  # Increment version
   ```

2. **Update changelog** in `Chart.yaml` annotations:
   ```yaml
   artifacthub.io/changes: |
     - kind: changed
       description: Updated resource limits
     - kind: fixed
       description: Fixed SSL connection issue
   ```

3. **Commit and push**:
   ```bash
   git add saas/client/helm-chart/kg-rca-agent/Chart.yaml
   git commit -m "chore: Bump chart version to 0.2.0"
   git push
   ```

4. **Create new release**:
   ```bash
   gh release create v0.2.0 \
     --title "KG RCA Agent v0.2.0" \
     --notes "See CHANGELOG.md for details"
   ```

5. **Artifact Hub auto-updates** within an hour

## Troubleshooting

### Chart Not Appearing on Artifact Hub

**Check:**
1. Repository is added in Artifact Hub console
2. Chart.yaml has correct format
3. GitHub repository is public
4. Release tag exists: `git tag -l`

**Fix:**
```bash
# Force Artifact Hub to rescan
# Go to: https://artifacthub.io/control-panel
# Click on your repository → "Rescan"
```

### Chart Install Fails

**Check:**
1. Chart syntax: `helm lint saas/client/helm-chart/kg-rca-agent`
2. Template rendering: `helm template test saas/client/helm-chart/kg-rca-agent --debug`

**Fix issues and re-release**

### Version Conflicts

If you need to republish the same version:
1. Delete the GitHub release
2. Delete the tag: `git tag -d v0.1.0 && git push origin :refs/tags/v0.1.0`
3. Recreate release with fixes

## Best Practices

1. **Semantic Versioning**: Follow semver (0.1.0, 0.2.0, 1.0.0)
2. **Changelog**: Always update `artifacthub.io/changes` annotation
3. **Testing**: Test chart locally before releasing
4. **Documentation**: Keep README.md up to date
5. **Images**: Use specific image tags (not `latest`)
6. **Security**: Document security considerations
7. **Examples**: Provide clear installation examples

## Security Scanning

Artifact Hub automatically scans charts for:
- Security vulnerabilities
- Deprecated Kubernetes APIs
- Best practice violations

Check the "Security Report" on your chart's Artifact Hub page.

## Verification Checklist

Before publishing:
- [ ] Chart.yaml has correct version
- [ ] README.md is comprehensive
- [ ] values.yaml has good defaults
- [ ] Chart lints successfully: `helm lint`
- [ ] Chart installs successfully: `helm install test .`
- [ ] All templates render correctly
- [ ] RBAC permissions are minimal
- [ ] Images are from trusted sources
- [ ] Documentation is clear

## Quick Reference

```bash
# Package chart
helm package saas/client/helm-chart/kg-rca-agent

# Test chart
helm lint saas/client/helm-chart/kg-rca-agent
helm install test saas/client/helm-chart/kg-rca-agent --dry-run --debug

# Create release
gh release create v0.1.0 --title "v0.1.0" --notes "Initial release"

# Check Artifact Hub
open https://artifacthub.io/packages/search?ts_query=kg-rca-agent
```

## Next Steps

After publishing:
1. ✅ Share on social media
2. ✅ Add Artifact Hub badge to README
3. ✅ Monitor downloads and stars
4. ✅ Respond to issues
5. ✅ Plan next version

## Artifact Hub Badge

Add this to your main README.md:

```markdown
[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/kg-rca-charts)](https://artifacthub.io/packages/helm/kg-rca-charts/kg-rca-agent)
```

## Support

- **Artifact Hub Docs**: https://artifacthub.io/docs
- **Helm Docs**: https://helm.sh/docs
- **Chart Releaser**: https://github.com/helm/chart-releaser

---

Ready to publish? Let's do it! 🚀
