#!/bin/bash

set -e

echo "🚀 Running full document pipeline..."

# ✅ 1. Setup / ensure container is running
./scripts/setup.sh

# ✅ 2. Route + convert based on file type
./scripts/router.sh

# ✅ 3. Clean extracted text
./scripts/clean.sh

# ✅ 4. Smart chunking
./scripts/smart_chunk.sh

echo "✅ Pipeline complete!"

echo ""
echo "👉 Next:"
echo "   ./scripts/ask.sh \"Your question here\""
``
