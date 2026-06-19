#!/bin/bash

set -e

QUERY="$1"

if [ -z "$QUERY" ]; then
  echo "❌ Usage: ./scripts/semantic_retrieve.sh \"your question\""
  exit 1
fi

# ✅ Run semantic retrieval inside container
docker exec markitdown python /app/scripts/semantic_retrieve.py "$QUERY"

# ✅ Copy to clipboard (FIXED syntax)
if command -v pbcopy > /dev/null 2>&1; then
  cat semantic_prompt.txt | pbcopy
  echo "✅ Semantic prompt copied to clipboard"
fi
