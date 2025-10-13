# Next Steps to Complete Artifact Hub Publishing

## ✅ What's Done

- ✅ Chart.yaml updated to v1.0.1 with Lumniverse branding
- ✅ README.md created with comprehensive documentation
- ✅ artifacthub-repo.yml added for repository metadata
- ✅ Code committed and pushed to GitHub
- ✅ GitHub release v1.0.1 created: https://github.com/anuragvishwa/kgroot-latest/releases/tag/v1.0.1

## 🎯 What You Need to Do

### Option 1: Quick Setup (Manual - Recommended for First Time)

#### Step 1: Install chart-releaser (One-time)

**macOS:**
```bash
brew install chart-releaser
```

**Linux:**
```bash
curl -sSL https://github.com/helm/chart-releaser/releases/download/v1.6.0/chart-releaser_1.6.0_linux_amd64.tar.gz | tar xz
sudo mv cr /usr/local/bin/
```

#### Step 2: Create GitHub Personal Access Token (One-time)

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Name: "Helm Chart Releaser"
4. Select scopes:
   - ✓ **repo** (all)
   - ✓ **write:packages**
5. Click "Generate token"
6. **Copy the token** (you won't see it again!)

#### Step 3: Run the Setup Script

```bash
cd /Users/anuragvishwa/Anurag/kgroot_latest

# Set your GitHub token
export GITHUB_TOKEN="ghp_your_token_here"  # Replace with your token

# Run the setup script
chmod +x /tmp/setup-helm-repo.sh
/tmp/setup-helm-repo.sh
```

**Expected output:**
```
╔══════════════════════════════════════════════════════════════╗
║     Setting up Helm Repository for Artifact Hub             ║
╚══════════════════════════════════════════════════════════════╝

✓ chart-releaser is installed
✓ GITHUB_TOKEN is set

Step 1: Creating package directory...
✓ Directory created

Step 2: Packaging Helm chart...
✓ Chart packaged

Step 3: Uploading chart to GitHub Release...
✓ Chart uploaded to GitHub Release

Step 4: Creating Helm repository index...
✓ Index created and pushed to gh-pages branch

╔══════════════════════════════════════════════════════════════╗
║              Setup Complete!                                 ║
╚══════════════════════════════════════════════════════════════╝
```

#### Step 4: Enable GitHub Pages

1. Go to: https://github.com/anuragvishwa/kgroot-latest/settings/pages
2. Under "Source":
   - **Branch**: `gh-pages`
   - **Folder**: `/ (root)`
3. Click **"Save"**
4. Wait 1-2 minutes for deployment

#### Step 5: Verify Helm Repository

```bash
# Wait 2 minutes, then test:
curl https://anuragvishwa.github.io/kgroot-latest/index.yaml

# Should return YAML with chart information
# If you get 404, wait a bit longer

# Test adding repository
helm repo add lumni https://anuragvishwa.github.io/kgroot-latest
helm repo update

# Search for your chart
helm search repo kg-rca-agent

# Expected output:
# NAME                    CHART VERSION   APP VERSION     DESCRIPTION
# lumni/kg-rca-agent      1.0.1           1.0.1           Knowledge Graph RCA Agent...
```

#### Step 6: Add to Artifact Hub

1. Go to: https://artifacthub.io/control-panel
2. **Log in** with your GitHub account
3. Click **"Add repository"**
4. Fill in:
   - **Name**: `Lumni`
   - **Display name**: `Lumni - Kubernetes Observability`
   - **Type**: `Helm charts`
   - **URL**: `https://anuragvishwa.github.io/kgroot-latest`
5. Click **"Add"**

#### Step 7: Wait for Artifact Hub to Index

- Artifact Hub scans every 30-60 minutes
- Or click **"Rescan"** in the control panel
- After scan, your chart will appear at: https://artifacthub.io/packages/helm/lumni/kg-rca-agent

### Option 2: Alternative Method (If chart-releaser doesn't work)

If you have issues with chart-releaser, you can manually set up GitHub Pages:

```bash
cd /Users/anuragvishwa/Anurag/kgroot-latest

# Create gh-pages branch
git checkout --orphan gh-pages
git rm -rf .

# Package chart
helm package saas/client/helm-chart/kg-rca-agent

# Create index
helm repo index . --url https://anuragvishwa.github.io/kgroot-latest

# Commit and push
git add index.yaml kg-rca-agent-1.0.1.tgz
git commit -m "feat: Initial Helm repository"
git push origin gh-pages

# Return to main branch
git checkout main
```

Then follow Step 4-7 from Option 1.

## 🧪 Testing Your Chart

Once published, anyone can install it:

```bash
# Add repository
helm repo add lumni https://anuragvishwa.github.io/kgroot-latest
helm repo update

# Install
helm install test-agent lumni/kg-rca-agent \
  --version 1.0.1 \
  --set client.id=test-123 \
  --set client.apiKey=test-key \
  --set server.kafka.brokers="kafka.lumniverse.com:9093" \
  --set server.kafka.security.protocol="SSL"

# Check status
kubectl get pods -l app=kg-rca-agent

# View logs
kubectl logs -l app=kg-rca-agent
```

## 📊 Monitoring

### Check Artifact Hub Stats

Visit: https://artifacthub.io/control-panel

You can see:
- Number of downloads
- Stars
- Repository health
- Last scan time

### Chart on Artifact Hub

After indexing, your chart will be available at:
- Main page: https://artifacthub.io/packages/helm/lumni/kg-rca-agent
- Search: https://artifacthub.io/packages/search?ts_query=kg-rca-agent

## 🔄 Updating the Chart (Future)

When you make changes:

```bash
# 1. Update version in Chart.yaml
# version: 1.0.2

# 2. Update changelog in Chart.yaml annotations
# artifacthub.io/changes: |
#   - kind: fixed
#     description: Fixed XYZ issue

# 3. Commit changes
git add saas/client/helm-chart/kg-rca-agent/Chart.yaml
git commit -m "chore: Bump chart version to 1.0.2"
git push

# 4. Create new release
gh release create v1.0.2 \
  --title "KG RCA Agent v1.0.2" \
  --notes "Bug fixes and improvements"

# 5. Run setup script again
export GITHUB_TOKEN="your-token"
/tmp/setup-helm-repo.sh

# 6. Artifact Hub auto-updates within an hour
```

## 🐛 Troubleshooting

### chart-releaser not found

**Install it:**
```bash
brew install chart-releaser  # macOS
```

### GitHub Pages 404

**Wait longer:** GitHub Pages takes 1-2 minutes to deploy

**Check settings:** https://github.com/anuragvishwa/kgroot-latest/settings/pages

### Artifact Hub not showing chart

**Check:**
1. Helm repository is accessible: `curl https://anuragvishwa.github.io/kgroot-latest/index.yaml`
2. Repository is added in Artifact Hub control panel
3. Click "Rescan" in control panel
4. Wait 30-60 minutes for automatic scan

### helm repo add fails

**Verify URL:**
```bash
curl -I https://anuragvishwa.github.io/kgroot-latest/index.yaml
# Should return 200 OK
```

## 📁 Files Created

- `.cr-release-packages/kg-rca-agent-1.0.1.tgz` - Packaged chart
- `gh-pages` branch - Contains index.yaml and charts
- GitHub release v1.0.1 - With chart attached

## 🎓 Resources

- **Artifact Hub Docs**: https://artifacthub.io/docs
- **Chart Releaser**: https://github.com/helm/chart-releaser
- **Helm Docs**: https://helm.sh/docs/topics/chart_repository/
- **Your Guides**:
  - [ARTIFACT-HUB-GUIDE.md](./ARTIFACT-HUB-GUIDE.md)
  - [PUBLISH-TO-ARTIFACTHUB.md](./PUBLISH-TO-ARTIFACTHUB.md)

## ✅ Success Checklist

- [ ] chart-releaser installed
- [ ] GitHub token created
- [ ] Setup script executed successfully
- [ ] GitHub Pages enabled (gh-pages branch)
- [ ] index.yaml accessible at https://anuragvishwa.github.io/kgroot-latest/index.yaml
- [ ] `helm repo add lumni ...` works
- [ ] `helm search repo kg-rca-agent` shows chart
- [ ] Repository added to Artifact Hub
- [ ] Chart visible on Artifact Hub (after scan)

## 🚀 Quick Commands

```bash
# Full setup (run these in order)
brew install chart-releaser  # or Linux equivalent
export GITHUB_TOKEN="your-token-here"
chmod +x /tmp/setup-helm-repo.sh
/tmp/setup-helm-repo.sh

# Enable GitHub Pages (manual step)
# Visit: https://github.com/anuragvishwa/kgroot-latest/settings/pages

# Test
curl https://anuragvishwa.github.io/kgroot-latest/index.yaml
helm repo add lumni https://anuragvishwa.github.io/kgroot-latest
helm search repo kg-rca-agent

# Add to Artifact Hub (manual step)
# Visit: https://artifacthub.io/control-panel
```

---

**Any questions? Check the detailed guides or let me know!** 🎉
