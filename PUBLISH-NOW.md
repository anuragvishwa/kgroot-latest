# Publish to Artifact Hub - Final Steps

## Current Status

✅ Chart is ready (v1.0.1)
✅ README updated with working configuration (port 9092)
✅ Changes committed and pushed to GitHub
✅ GitHub release v1.0.1 exists
✅ chart-releaser installed

## What You Need to Do

### Step 1: Create GitHub Token (One-time, 2 minutes)

1. Go to: https://github.com/settings/tokens
2. Click **"Generate new token (classic)"**
3. Name: `Helm Chart Releaser`
4. Select scopes:
   - ✅ **repo** (all sub-options)
   - ✅ **write:packages**
5. Click **"Generate token"**
6. **Copy the token** (starts with `ghp_...`)

### Step 2: Run These Commands (5 minutes)

Open a new terminal and run:

```bash
cd /Users/anuragvishwa/Anurag/kgroot_latest

# Set your GitHub token (replace with your actual token)
export GITHUB_TOKEN="ghp_your_token_here"

# Create package directory
mkdir -p .cr-release-packages

# Package the chart
helm package saas/client/helm-chart/kg-rca-agent -d .cr-release-packages

# Upload to GitHub Release
cr upload \
  --owner anuragvishwa \
  --git-repo kgroot-latest \
  --release-name-template "v{{ .Version }}" \
  --package-path .cr-release-packages

# Create Helm repository index
cr index \
  --owner anuragvishwa \
  --git-repo kgroot-latest \
  --charts-repo https://anuragvishwa.github.io/kgroot-latest \
  --index-path . \
  --package-path .cr-release-packages \
  --push
```

**Expected output:**
```
==> Using existing package: .cr-release-packages/kg-rca-agent-1.0.1.tgz
 ----> Uploading kg-rca-agent-1.0.1.tgz...
 ----> Uploaded kg-rca-agent-1.0.1.tgz
==> Updating index
 ----> Found kg-rca-agent-1.0.1.tgz
 ----> Extracting chart metadata from .cr-release-packages/kg-rca-agent-1.0.1.tgz
 ----> Pushing index.yaml to gh-pages branch
```

### Step 3: Enable GitHub Pages (2 minutes)

1. Go to: https://github.com/anuragvishwa/kgroot-latest/settings/pages
2. Under **"Source"**:
   - Branch: `gh-pages`
   - Folder: `/ (root)`
3. Click **"Save"**
4. Wait 1-2 minutes

### Step 4: Verify Helm Repository (1 minute)

```bash
# Test index.yaml (wait 2 minutes after enabling GitHub Pages)
curl https://anuragvishwa.github.io/kgroot-latest/index.yaml

# Should show YAML with kg-rca-agent information

# Add repository
helm repo add lumni https://anuragvishwa.github.io/kgroot-latest
helm repo update

# Search for chart
helm search repo kg-rca-agent

# Expected:
# NAME                    CHART VERSION   APP VERSION     DESCRIPTION
# lumni/kg-rca-agent      1.0.1           1.0.1           Knowledge Graph RCA Agent...
```

### Step 5: Add to Artifact Hub (3 minutes)

1. Go to: https://artifacthub.io/control-panel
2. Log in with GitHub
3. Click **"Add repository"**
4. Fill in:
   - **Name**: `Lumni`
   - **Display name**: `Lumni - Kubernetes Observability`
   - **Type**: `Helm charts`
   - **URL**: `https://anuragvishwa.github.io/kgroot-latest`
5. Click **"Add"**

### Step 6: Wait for Artifact Hub to Index (10-30 minutes)

Artifact Hub scans repositories every 30-60 minutes.

**Or manually trigger**:
1. Go to control panel
2. Find "Lumni" repository
3. Click **"Rescan"**

**Your chart will appear at**:
- https://artifacthub.io/packages/helm/lumni/kg-rca-agent

## Test Installation

Once published, anyone can install:

```bash
# Add repository
helm repo add lumni https://anuragvishwa.github.io/kgroot-latest
helm repo update

# Install
helm install test-agent lumni/kg-rca-agent \
  --set client.id=test-001 \
  --set client.apiKey=test-key \
  --set server.kafka.brokers="kafka.lumniverse.com:9092"

# Verify
kubectl get pods -l app=kg-rca-agent
kubectl logs -l app=kg-rca-agent
```

## Troubleshooting

### cr upload fails

**Error**: Authentication failed

**Fix**: Make sure `GITHUB_TOKEN` is set correctly:
```bash
echo $GITHUB_TOKEN  # Should show your token
```

### GitHub Pages shows 404

**Fix**: Wait 2-3 minutes after enabling, then refresh

### Artifact Hub doesn't show chart

**Check**:
1. Repository added in control panel ✓
2. URL is correct: `https://anuragvishwa.github.io/kgroot-latest` ✓
3. index.yaml is accessible ✓
4. Wait 30-60 minutes or click "Rescan"

## Quick Commands Summary

```bash
# Set token
export GITHUB_TOKEN="ghp_..."

# Package & publish
mkdir -p .cr-release-packages
helm package saas/client/helm-chart/kg-rca-agent -d .cr-release-packages
cr upload --owner anuragvishwa --git-repo kgroot-latest --release-name-template "v{{ .Version }}" --package-path .cr-release-packages
cr index --owner anuragvishwa --git-repo kgroot-latest --charts-repo https://anuragvishwa.github.io/kgroot-latest --index-path . --package-path .cr-release-packages --push

# Enable GitHub Pages (manual step in browser)
# Visit: https://github.com/anuragvishwa/kgroot-latest/settings/pages

# Test
curl https://anuragvishwa.github.io/kgroot-latest/index.yaml
helm repo add lumni https://anuragvishwa.github.io/kgroot-latest
helm search repo kg-rca-agent

# Add to Artifact Hub (manual step in browser)
# Visit: https://artifacthub.io/control-panel
```

---

**Ready? Start with Step 1 to create your GitHub token!** 🚀
