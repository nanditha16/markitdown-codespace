#!/bin/bash

set -e

echo "🧠 Smart chunking (fixed empty chunk issue)..."

mkdir -p chunks
rm -f chunks/*

for f in output/*.md; do
  if [ -f "$f" ]; then
    filename=$(basename -- "$f")
    name="${filename%.*}"

    echo "➡️ Processing $filename"

    awk -v prefix="chunks/${name}_part_" '
    BEGIN {
        i=1
        outfile=prefix i ".md"
        chunk=""
    }

    # ✅ Detect headings
    /^[A-Z][A-Z ]+$/ || /^#{1,6} / {

        # ✅ Only write if chunk has content
        if (length(chunk) > 0) {
            print chunk > outfile
            close(outfile)
            i++
            outfile=prefix i ".md"
            chunk=""
        }

        # ✅ IMPORTANT: include heading line in next chunk
        chunk = $0 "\n"
        next
    }

    {
        chunk = chunk $0 "\n"
    }

    END {
        if (length(chunk) > 0) {
            print chunk > outfile
        }
    }
    ' "$f"

  fi
done

# ✅ Remove any leftover empty files
find chunks/ -type f -size 0 -delete

echo "✅ Smart chunks created (no empty files)"
