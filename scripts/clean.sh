#!/bin/bash

set -e

echo "🧹 Cleaning unified output..."

for f in output/*.md; do
  if [ -f "$f" ]; then
    echo "➡️ Cleaning $(basename "$f")"

    # ✅ Fix HTML entities
    sed -i '' \
      -e 's/&amp;/\&/g' \
      -e 's/&lt;/</g' \
      -e 's/&gt;/>/g' \
      "$f"

    # ✅ Normalize whitespace
    sed -i '' -e 's/[[:space:]]\+/ /g' "$f"

    # ✅ Join broken lines
    perl -0777 -pe 's/\n([a-z])/ \1/g' -i "$f"

    # ✅ Normalize bullets
    sed -i '' \
      -e 's/^•/- /g' \
      -e 's/^·/- /g' \
      -e 's/^–/- /g' \
      "$f"

    # ✅ Light encoding cleanup
    sed -i '' \
      -e 's/‚Äì/-/g' \
      -e 's/‚Äî/-/g' \
      -e 's/¬∑/-/g' \
      "$f"

    # ✅ Add spacing around headings
    sed -i '' \
      -e 's/^\([A-Z][A-Z ]*\)$/\n\1\n/g' \
      "$f"

    # ✅ ✅ CRITICAL FIX: remove leading blank lines AFTER all transforms
    awk 'NF{p=1} p' "$f" > "$f.tmp" && mv "$f.tmp" "$f"

  fi
done

echo "✅ Cleaning complete"
