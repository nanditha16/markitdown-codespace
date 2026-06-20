#!/bin/bash

set -e

echo "🧹 Cleaning unified output..."

# This now runs INSIDE the container via docker exec, matching every other
# stage of the pipeline (router, retrieve, ats_optimize). Previously this
# ran on the host (Mac), which meant output/*.md was being touched by two
# different OS/locale/perl environments across a single ./run.sh call —
# a real source of subtle, hard-to-reproduce bugs even after individual
# perl commands were made cross-platform-safe.

docker exec markitdown bash -c '
for f in output/*.md; do
  if [ -f "$f" ]; then
    echo "➡️ Cleaning $(basename "$f")"

    perl -pi -e "s/&amp;/&/g; s/&lt;/</g; s/&gt;/>/g" "$f"
    perl -pi -e "s/[ \t]+/ /g" "$f"
    perl -0777 -pi -e "s/\n([a-z])/ \1/g" "$f"
    perl -pi -e "s/^•/- /; s/^·/- /; s/^–/- /" "$f"
    perl -pi -e "s/‚Äì/-/g; s/‚Äî/-/g; s/¬∑/-/g" "$f"
    perl -pi -e "s/^([A-Z][A-Z ]*)\$/\n\$1\n/" "$f"

    awk "NF{p=1} p" "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  fi
done
'

echo "✅ Cleaning complete"
