#!/bin/bash

# Script to publish client-light Helm chart to gh-pages branch
# Usage: ./publish-to-gh-pages.sh

set -e

echo "🚀 Publishing Helm chart to GitHub Pages..."
echo ""

# Get current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Get chart version
CHART_VERSION=$(grep '^version:' "${SCRIPT_DIR}/helm-chart/Chart.yaml" | awk '{print $2}')
echo "📦 Chart version: ${CHART_VERSION}"
echo ""

# Package the chart
echo "📦 Packaging Helm chart..."
cd "${SCRIPT_DIR}"
helm package helm-chart/

if [ ! -f "kg-rca-agent-${CHART_VERSION}.tgz" ]; then
    echo "❌ Error: Chart package not found!"
    exit 1
fi

echo "✅ Chart packaged: kg-rca-agent-${CHART_VERSION}.tgz"
echo ""

# Check if gh-pages worktree exists
if [ -d "${REPO_ROOT}/gh-pages-content" ]; then
    echo "📂 Using existing gh-pages-content directory..."
    cd "${REPO_ROOT}/gh-pages-content"

    # Make sure we're on gh-pages branch
    CURRENT_BRANCH=$(git branch --show-current)
    if [ "${CURRENT_BRANCH}" != "gh-pages" ]; then
        echo "⚠️  Not on gh-pages branch, checking out..."
        git checkout gh-pages
    fi

    # Pull latest changes
    git pull origin gh-pages
else
    echo "📂 Cloning gh-pages branch..."
    cd "${REPO_ROOT}"
    git worktree add gh-pages-content gh-pages
    cd gh-pages-content
fi

echo ""
echo "📋 Copying chart to gh-pages..."

# Copy the chart package to root
cp "${SCRIPT_DIR}/kg-rca-agent-${CHART_VERSION}.tgz" .

# Update the Helm repository index
echo "📋 Updating Helm repository index..."
helm repo index . --url https://anuragvishwa.github.io/kgroot-latest/ --merge index.yaml

# Show what changed
echo ""
echo "📊 Changes:"
git status --short

# Commit and push
echo ""
read -p "❓ Commit and push to gh-pages? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    git add kg-rca-agent-${CHART_VERSION}.tgz index.yaml

    if git diff --staged --quiet; then
        echo "ℹ️  No changes to commit"
    else
        git commit -m "chore: Publish kg-rca-agent v${CHART_VERSION}

- Add chart package kg-rca-agent-${CHART_VERSION}.tgz
- Update Helm repository index"

        git push origin gh-pages

        echo ""
        echo "✅ Chart published successfully!"
        echo ""
        echo "🔗 Installation instructions:"
        echo ""
        echo "  # Add the repository"
        echo "  helm repo add kg-rca https://anuragvishwa.github.io/kgroot-latest/"
        echo "  helm repo update"
        echo ""
        echo "  # Install the chart"
        echo "  helm install kg-rca-agent kg-rca/kg-rca-agent \\"
        echo "    --version ${CHART_VERSION} \\"
        echo "    --namespace observability \\"
        echo "    --set client.id='your-client-id' \\"
        echo "    --set cluster.name='Your Cluster' \\"
        echo "    --set client.kafka.brokers='kafka:9092'"
        echo ""
        echo "⏳ Note: GitHub Pages may take 5-10 minutes to update"
    fi
else
    echo "❌ Skipped push. Changes are staged but not pushed."
fi

echo ""
echo "✨ Done!"
