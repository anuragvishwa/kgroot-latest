# Publishing KG RCA Agent to Artifact Hub - Step by Step

## Summary

We're publishing your Helm chart to **Artifact Hub** under the repository name **"Lumni"**.

**Repository**: https://github.com/anuragvishwa/kgroot-latest
**Chart**: kg-rca-agent v1.0.1
**Company**: Lumniverse
**Support**: support@lumniverse.com

## What We've Prepared

✅ **Chart.yaml** - Updated with version 1.0.1 and Artifact Hub annotations
✅ **README.md** - Comprehensive documentation with installation instructions
✅ **artifacthub-repo.yml** - Repository metadata for Artifact Hub
✅ **All files validated** - Ready to push

## Steps to Publish

### Step 1: Commit and Push to GitHub (5 minutes)

```bash
cd /Users/anuragvishwa/Anurag/kgroot_latest

# Add all Helm chart files
git add saas/client/helm-chart/kg-rca-agent/

# Add Artifact Hub metadata
git add artifacthub-repo.yml

# Add documentation
git add ARTIFACT-HUB-GUIDE.md PUBLISH-TO-ARTIFACTHUB.md

# Commit
git commit -m "feat: Prepare KG RCA Agent v1.0.1 for Artifact Hub

- Update Chart.yaml to v1.0.1 with Lumniverse branding
- Add comprehensive README.md with installation instructions
- Add Artifact Hub repository metadata
- Add SSL/TLS configuration examples
- Include troubleshooting and security best practices

Ready for Artifact Hub publishing under Lumni repository"

# Push to GitHub
git push origin main
```

**Expected output:**
```
[main abc1234] feat: Prepare KG RCA Agent v1.0.1 for Artifact Hub
 X files changed, Y insertions(+)
 create mode 100644 saas/client/helm-chart/kg-rca-agent/README.md
 create mode 100644 artifacthub-repo.yml
...
```

### Step 2: Create GitHub Release v1.0.1 (3 minutes)

#### Option A: Using GitHub CLI (Recommended)

```bash
# If you have gh CLI installed
gh release create v1.0.1 \
  --title "KG RCA Agent v1.0.1 - Production Release" \
  --notes "## KG RCA Agent v1.0.1 by Lumniverse

### 🎉 Production Release

The KG RCA Agent is now production-ready! Deploy intelligent Kubernetes observability to your clusters.

### ✨ Features

- **Real-time Event Collection**: Capture all Kubernetes events as they happen
- **Log Aggregation**: Collect pod logs with Vector for comprehensive analysis
- **SSL/TLS Security**: Secure communication with encrypted Kafka connections
- **Resource Optimized**: Configurable limits for any cluster size
- **RBAC Compliant**: Minimal required permissions following best practices
- **Multi-Namespace**: Monitor single namespace or entire cluster
- **Easy Installation**: One-command Helm chart deployment

### 📦 Installation

\`\`\`bash
# Add Lumni Helm repository
helm repo add lumni https://anuragvishwa.github.io/kgroot-latest
helm repo update

# Install KG RCA Agent
helm install my-rca-agent lumni/kg-rca-agent \\
  --version 1.0.1 \\
  --set client.id=<your-client-id> \\
  --set client.apiKey=<your-api-key> \\
  --set server.kafka.brokers=\"kafka.lumniverse.com:9093\" \\
  --set server.kafka.security.protocol=\"SSL\"
\`\`\`

### 📚 Documentation

- [Chart README](https://github.com/anuragvishwa/kgroot-latest/blob/main/saas/client/helm-chart/kg-rca-agent/README.md)
- [Quick Start Guide](https://github.com/anuragvishwa/kgroot-latest/blob/main/client/QUICKSTART.md)
- [SSL Setup Guide](https://github.com/anuragvishwa/kgroot-latest/blob/main/SSL-SETUP-GUIDE.md)

### 🔐 Security

- SSL/TLS encryption for data in transit
- RBAC with minimal required permissions
- Secure credential management with Kubernetes secrets
- Certificate verification enabled by default

### 🎯 What's Included

- Kubernetes event exporter (real-time)
- Vector log collector (production-ready)
- Prometheus metrics export
- Configurable resource limits
- Comprehensive RBAC policies
- Multi-namespace support

### 🚀 Next Steps

1. Install the agent in your Kubernetes cluster
2. Monitor events flowing to kafka.lumniverse.com
3. View knowledge graph and RCA insights
4. Get intelligent root cause analysis for incidents

### 📧 Support

- **Email**: support@lumniverse.com
- **Issues**: https://github.com/anuragvishwa/kgroot-latest/issues
- **Website**: https://lumniverse.com

---

**Made with ❤️ by Lumniverse for better Kubernetes observability**
"
```

#### Option B: Using GitHub Web UI

1. Go to: https://github.com/anuragvishwa/kgroot-latest/releases/new

2. **Tag version**: `v1.0.1`
   - Click "Choose a tag"
   - Type: `v1.0.1`
   - Click "Create new tag: v1.0.1 on publish"

3. **Release title**: `KG RCA Agent v1.0.1 - Production Release`

4. **Description**: Copy the release notes from Option A above (everything after `--notes`)

5. Click **"Publish release"**

**Result**: https://github.com/anuragvishwa/kgroot-latest/releases/tag/v1.0.1

### Step 3: Set Up GitHub Pages for Helm Repository (10 minutes)

#### Install and Configure Chart Releaser

```bash
# Install chart-releaser (if not already installed)
# macOS:
brew install chart-releaser

# Linux:
curl -sSL https://github.com/helm/chart-releaser/releases/download/v1.6.0/chart-releaser_1.6.0_linux_amd64.tar.gz | tar xz
sudo mv cr /usr/local/bin/

# Verify installation
cr version
```

#### Package and Upload Chart

```bash
cd /Users/anuragvishwa/Anurag/kgroot_latest

# Package the chart
mkdir -p .cr-release-packages
helm package saas/client/helm-chart/kg-rca-agent -d .cr-release-packages

# This creates: .cr-release-packages/kg-rca-agent-1.0.1.tgz

# Set GitHub token (if not already set)
export GITHUB_TOKEN="your-github-token-here"  # Get from: https://github.com/settings/tokens

# Upload to GitHub Release
cr upload \
  --owner anuragvishwa \
  --git-repo kgroot-latest \
  --release-name-template "v{{ .Version }}" \
  --package-path .cr-release-packages

# Create/update Helm repository index
cr index \
  --owner anuragvishwa \
  --git-repo kgroot-latest \
  --charts-repo https://anuragvishwa.github.io/kgroot-latest \
  --index-path . \
  --package-path .cr-release-packages \
  --push
```

**This will**:
1. Create a `gh-pages` branch
2. Add `index.yaml` (Helm repository index)
3. Push to GitHub

#### Enable GitHub Pages

1. Go to: https://github.com/anuragvishwa/kgroot-latest/settings/pages
2. **Source**: Deploy from a branch
3. **Branch**: `gh-pages`
4. **Folder**: `/ (root)`
5. Click **"Save"**

**Wait 1-2 minutes**, then verify:
- https://anuragvishwa.github.io/kgroot-latest/index.yaml should be accessible

### Step 4: Add Repository to Artifact Hub (5 minutes)

1. **Go to Artifact Hub**: https://artifacthub.io/control-panel

2. **Log in** with your GitHub account

3. **Click "Add repository"**

4. **Fill in details**:
   - **Name**: `Lumni` (this is the repository name users will see)
   - **Display name**: `Lumni - Kubernetes Observability`
   - **Type**: `Helm charts`
   - **URL**: `https://anuragvishwa.github.io/kgroot-latest`
   - **Repository ID**: (leave blank, auto-generated)
   - **Verified publisher**: ✓ (if available)
   - **Official**: ✓ (if you want to mark it as official)

5. **Advanced settings** (optional):
   - **Branch**: `gh-pages`
   - **Path**: (leave blank)

6. Click **"Add"**

### Step 5: Verify on Artifact Hub (Wait 5-10 minutes)

Artifact Hub scans repositories periodically (usually within 10-30 minutes).

**Check status**:
1. Go to: https://artifacthub.io/control-panel
2. Look for "Lumni" in your repositories
3. Check "Last scan" timestamp
4. Click "Rescan" if needed

**Search for your chart**:
1. Go to: https://artifacthub.io/packages/search?ts_query=kg-rca-agent
2. Or: https://artifacthub.io/packages/helm/lumni/kg-rca-agent

**You should see**:
- Chart name: KG RCA Agent by Lumniverse
- Version: 1.0.1
- Description, README, installation instructions
- All metadata from Chart.yaml

### Step 6: Test Installation (2 minutes)

```bash
# Add Lumni repository
helm repo add lumni https://anuragvishwa.github.io/kgroot-latest
helm repo update

# Search for the chart
helm search repo kg-rca-agent

# Expected output:
# NAME                    CHART VERSION   APP VERSION     DESCRIPTION
# lumni/kg-rca-agent      1.0.1           1.0.1           Knowledge Graph RCA Agent - Client-side...

# Test installation (dry-run)
helm install test-agent lumni/kg-rca-agent \
  --version 1.0.1 \
  --set client.id=test-123 \
  --set client.apiKey=test-key \
  --set server.kafka.brokers="kafka.lumniverse.com:9093" \
  --dry-run --debug
```

## Automation with GitHub Actions (Optional)

For automatic publishing on new releases, create this file:

**`.github/workflows/release-helm-chart.yml`**:

```yaml
name: Release Helm Chart

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Configure Git
        run: |
          git config user.name "$GITHUB_ACTOR"
          git config user.email "$GITHUB_ACTOR@users.noreply.github.com"

      - name: Install Helm
        uses: azure/setup-helm@v3
        with:
          version: v3.13.0

      - name: Run chart-releaser
        uses: helm/chart-releaser-action@v1.6.0
        with:
          charts_dir: saas/client/helm-chart
          mark_as_latest: true
        env:
          CR_TOKEN: "${{ secrets.GITHUB_TOKEN }}"
```

**To use**:
```bash
# Commit the workflow
git add .github/workflows/release-helm-chart.yml
git commit -m "ci: Add Helm chart release automation"
git push

# Future releases: just create a tag
git tag v1.0.2
git push origin v1.0.2

# GitHub Actions will automatically:
# - Package the chart
# - Create GitHub release
# - Update Helm repository index
# - Artifact Hub will detect and update
```

## Troubleshooting

### Chart Not Showing on Artifact Hub

**Check**:
1. GitHub Pages is enabled: https://github.com/anuragvishwa/kgroot-latest/settings/pages
2. index.yaml is accessible: https://anuragvishwa.github.io/kgroot-latest/index.yaml
3. Repository is added in Artifact Hub: https://artifacthub.io/control-panel
4. Click "Rescan" in Artifact Hub control panel

**Fix**:
```bash
# Verify index.yaml exists
curl https://anuragvishwa.github.io/kgroot-latest/index.yaml

# Re-run cr index if needed
cr index \
  --owner anuragvishwa \
  --git-repo kgroot-latest \
  --charts-repo https://anuragvishwa.github.io/kgroot-latest \
  --index-path . \
  --package-path .cr-release-packages \
  --push
```

### Helm Repo Add Fails

**Check**:
```bash
# Test URL directly
curl https://anuragvishwa.github.io/kgroot-latest/index.yaml

# Should return valid YAML with chart entries
```

**Fix**: Wait a few minutes for GitHub Pages to deploy

### Chart Install Fails

**Check**:
```bash
# Lint the chart
helm lint saas/client/helm-chart/kg-rca-agent

# Test template rendering
helm template test saas/client/helm-chart/kg-rca-agent --debug
```

## Success Checklist

- [ ] Code pushed to GitHub (main branch)
- [ ] GitHub release v1.0.1 created
- [ ] Chart packaged (.cr-release-packages/kg-rca-agent-1.0.1.tgz)
- [ ] Chart uploaded to GitHub release assets
- [ ] gh-pages branch created with index.yaml
- [ ] GitHub Pages enabled and accessible
- [ ] Repository added to Artifact Hub
- [ ] Chart visible on Artifact Hub
- [ ] `helm repo add lumni ...` works
- [ ] `helm search repo kg-rca-agent` shows chart
- [ ] Test installation succeeds

## Next Steps After Publishing

1. **Share the news**:
   - Social media post
   - Blog announcement
   - Community forums

2. **Add badge to main README**:
   ```markdown
   [![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/lumni)](https://artifacthub.io/packages/helm/lumni/kg-rca-agent)
   ```

3. **Monitor**:
   - Artifact Hub dashboard for downloads
   - GitHub issues for user questions
   - Stars and forks

4. **Update regularly**:
   - Fix bugs → v1.0.2
   - New features → v1.1.0
   - Breaking changes → v2.0.0

## Quick Reference

```bash
# Add repository
helm repo add lumni https://anuragvishwa.github.io/kgroot-latest

# Search
helm search repo kg-rca

# Install
helm install my-agent lumni/kg-rca-agent --version 1.0.1

# Upgrade
helm upgrade my-agent lumni/kg-rca-agent

# Uninstall
helm uninstall my-agent
```

## Support

**Questions?** Check:
- [Artifact Hub Guide](./ARTIFACT-HUB-GUIDE.md) - Detailed documentation
- [Chart README](./saas/client/helm-chart/kg-rca-agent/README.md) - Chart documentation
- [GitHub Issues](https://github.com/anuragvishwa/kgroot-latest/issues) - Report problems

---

**Ready? Let's start with Step 1! 🚀**
