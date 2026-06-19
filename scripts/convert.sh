#!/bin/bash

set -e

echo "🔄 Converting files from input → output"

for f in input/*; do
  if [ -f "$f" ]; then
    filename=$(basename -- "$f")
    name="${filename%.*}"

    echo "➡️ Converting $filename"
    docker exec markitdown markitdown "/input/$filename" -o "/output/$name.md"
  fi
done

echo "✅ Done!"
