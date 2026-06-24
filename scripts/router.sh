#!/bin/bash

set -e

echo "🧠 Routing files..."

# ✅ PDFs → pdfplumber first
if ls input/pdf/*.pdf 1> /dev/null 2>&1; then
  echo "📄 Processing PDFs with pdfplumber..."

  docker exec markitdown bash -c "python scripts/pdf_convert.py"

  # ✅ fallback check
  for f in output/*.md; do
    if [ -f "$f" ]; then
      size=$(wc -c < "$f")

      if [ "$size" -lt 200 ]; then
        echo "⚠️ Weak PDF extraction → fallback to MarkItDown"

        name=$(basename "$f" .md)
        docker exec markitdown markitdown "/input/pdf/$name.pdf" -o "/output/$name.md"
      fi
    fi
  done
fi

# ✅ Images → OCR
if ls input/image/* 1> /dev/null 2>&1; then
  echo "🖼️ Processing images via OCR..."

  for f in input/image/*; do
    filename=$(basename -- "$f")
    name="${filename%.*}"

    # tesseract writes "<base>.txt" by default; force .md so clean/chunk
    # steps (which only glob output/*.md) pick it up
    docker exec markitdown tesseract "/input/image/$filename" "/output/$name"
    docker exec markitdown bash -c "mv /output/$name.txt /output/$name.md"
  done
fi

# ✅ HTML → MarkItDown
if ls input/html/*.html 1> /dev/null 2>&1; then
  echo "🌐 Processing HTML..."

  for f in input/html/*.html; do
    filename=$(basename -- "$f")
    name="${filename%.*}"

    docker exec markitdown markitdown "/input/html/$filename" -o "/output/$name.md"
  done
fi

# ✅ DOCX / others → MarkItDown
if ls input/docx/* 1> /dev/null 2>&1; then
  echo "📄 Processing DOCX..."

  for f in input/docx/*; do
    filename=$(basename -- "$f")
    name="${filename%.*}"

    docker exec markitdown markitdown "/input/docx/$filename" -o "/output/$name.md"
  done
fi

if ls input/other/* 1> /dev/null 2>&1; then
  echo "📦 Processing OTHER..."

  for f in input/other/*; do
    filename=$(basename -- "$f")
    name="${filename%.*}"

    echo "➡️ Processing $filename"

    # ✅ Plain text → no need for MarkItDown (prevents encoding crash)
    cp "$f" "output/$name.md"

    echo "✅ Saved: output/$name.md"
  done
fi

echo "✅ Routing complete"
