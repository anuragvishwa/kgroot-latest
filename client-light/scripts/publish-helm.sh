#!/bin/bash
set -e

# Helm Chart Publishing Script
# Publishes the kg-rca-agent Helm chart to GitHub Pages

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_LIGHT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$CLIENT_LIGHT_DIR")"
CHART_DIR="$CLIENT_LIGHT_DIR/helm-chart"
GH_PAGES_DIR="$REPO_ROOT/gh-pages-content"
REPO_URL="https://anuragvishwa.github.io/kgroot-latest/"

echo "==================================="
echo "Helm Chart Publishing Script"
echo "==================================="
echo ""

# Check if helm is installed
if ! command -v helm &> /dev/null; then
    echo "Error: helm is not installed. Please install Helm first."
    exit 1
fi

# Get chart version
CHART_VERSION=$(grep '^version:' "$CHART_DIR/Chart.yaml" | awk '{print $2}')
echo "Chart version: $CHART_VERSION"
echo ""

# Step 1: Package the chart
echo "Step 1: Packaging Helm chart..."
cd "$CLIENT_LIGHT_DIR"
helm package helm-chart/
CHART_PACKAGE="kg-rca-agent-${CHART_VERSION}.tgz"

if [ ! -f "$CHART_PACKAGE" ]; then
    echo "Error: Failed to create chart package"
    exit 1
fi
echo "✓ Chart packaged: $CHART_PACKAGE"
echo ""

# Step 2: Update gh-pages content
echo "Step 2: Updating GitHub Pages content..."
mkdir -p "$GH_PAGES_DIR"
cp "$CHART_PACKAGE" "$GH_PAGES_DIR/"

# Step 3: Update Helm repo index
echo "Step 3: Updating Helm repository index..."
cd "$GH_PAGES_DIR"
helm repo index . --url "$REPO_URL" --merge index.yaml 2>/dev/null || helm repo index . --url "$REPO_URL"
echo "✓ Repository index updated"
echo ""

# Step 4: Commit and push to gh-pages
echo "Step 4: Committing and pushing to GitHub..."
cd "$GH_PAGES_DIR"

# Check if it's a git repository
if [ ! -d ".git" ]; then
    git init
    git remote add origin https://github.com/anuragvishwa/kgroot-latest.git
    git branch -m gh-pages
fi

git add .
git commit -m "chore: publish Helm chart v${CHART_VERSION}" || echo "No changes to commit"
git push origin gh-pages

echo ""
echo "==================================="
echo "✓ Publishing Complete!"
echo "==================================="
echo ""
echo "Chart version $CHART_VERSION has been published to:"
echo "  $REPO_URL"
echo ""
echo "Users can now install with:"
echo "  helm repo add kg-rca-agent $REPO_URL"
echo "  helm repo update"
echo "  helm install kg-rca-agent kg-rca-agent/kg-rca-agent --version $CHART_VERSION"
echo ""
echo "Next steps:"
echo "  1. Enable GitHub Pages in repository settings (if not already done)"
echo "     Go to: https://github.com/anuragvishwa/kgroot-latest/settings/pages"
echo "     Select 'gh-pages' branch and '/ (root)' folder"
echo "  2. Wait 1-2 minutes for GitHub Pages to deploy"
echo "  3. Verify at: $REPO_URL"
echo "  4. (Optional) Submit to Artifact Hub for discoverability"
echo ""
