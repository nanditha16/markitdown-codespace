#!/bin/bash

set -e

echo "🧠 Using OCR-based conversion (better quality)..."

for f in input/*.pdf; do
  if [ -f "$f" ]; then
    filename=$(basename -- "$f")
    name="${filename%.*}"

    echo "➡️ OCR converting $filename"

    # Force OCR via pdftoppm → image → markitdown
    pdftoppm "$f" /tmp/page -png

    rm -f "/output/$name.md"

    for img in /tmp/page-*.png; do
      echo "   Processing $img"
      markitdown "$img" >> "/output/$name.md"
      echo "" >> "/output/$name.md"
    done

    rm -f /tmp/page-*.png
  fi
done

echo "✅ OCR conversion complete"
