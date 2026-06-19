#!/bin/bash

set -e

echo "🚀 Setting up MarkItDown environment..."

if ! docker info >/dev/null 2>&1; then
  echo "❌ Docker is not running. Please start Docker Desktop."
  exit 1
fi

# Build and start container
docker compose up -d --build

echo "✅ Docker container is running"

# Ensure scripts are executable
chmod +x scripts/*.sh

echo "✅ Setup complete"
echo ""
echo "👉 Next steps:"
echo "  Add files to ./input/"
echo "  Run: ./scripts/convert.sh"
