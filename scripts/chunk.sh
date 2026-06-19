#!/bin/bash

set -e

CHUNK_SIZE=500   # lines per chunk (tune this)

echo "📦 Chunking Markdown files..."

mkdir -p chunks

for f in output/*.md; do
  if [ -f "$f" ]; then
    filename=$(basename -- "$f")
    name="${filename%.*}"

    echo "➡️ Chunking $filename"

    split -l $CHUNK_SIZE "$f" "chunks/${name}_part_"

    # Rename chunks nicely
    i=1
    for chunk in chunks/${name}_part_*; do
      mv "$chunk" "chunks/${name}_part_${i}.md"
      ((i++))
    done
  fi
done

echo "✅ Chunking complete → see /chunks/"

