#!/bin/bash
# Safe deployment script for shelldon.monoroc.de
# ONLY deploys Astro-built content
# NEVER touches games/ directory

set -e  # Exit on error

echo "🐚 Starting safe deployment..."

# Build Astro project
echo "📦 Building Astro project..."
npm run build

# Target directory
TARGET="/var/www/shelldon.monoroc.de"

# Deploy ONLY Astro-built directories and files
# We explicitly copy only what Astro builds, leaving games/ completely untouched
echo "🚀 Deploying Astro content to $TARGET..."

# Copy root files
echo "  → Copying root files..."
cp -f dist/index.html "$TARGET/"
cp -f dist/favicon.svg "$TARGET/" 2>/dev/null || true

# Copy Astro directories (recreate to ensure clean state)
echo "  → Copying /about/..."
rm -rf "$TARGET/about" && cp -r dist/about "$TARGET/"

echo "  → Copying /experiments/..."
rm -rf "$TARGET/experiments" && cp -r dist/experiments "$TARGET/"

echo "  → Copying /assets/..."
rm -rf "$TARGET/assets" && cp -r dist/assets "$TARGET/"

echo "  → Copying /food/..."
rm -rf "$TARGET/food" && cp -r dist/food "$TARGET/"

echo ""
echo "✅ Deployment complete!"
echo "📍 Site: https://shelldon.monoroc.de"
echo ""
echo "⚠️  IMPORTANT: games/ directory was NOT touched (as intended)"

# Verify games/ still exists and show its state
if [ -d "$TARGET/games/" ]; then
  echo "✅ Games directory preserved:"
  ls -lh "$TARGET/games/"
else
  echo "❌ WARNING: games/ directory missing! This should not happen!"
  exit 1
fi
