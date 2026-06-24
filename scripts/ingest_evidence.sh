#!/bin/bash
#
# ingest_evidence.sh — Converts raw evidence files placed in input/evidence/
# into chunked .md files under output/career_wealth_chunk/.
#
# Handles: .pdf (pdfplumber → MarkItDown → Tesseract OCR fallback chain)
#          .xlsx/.xls, .docx, .txt, .md
#
# Filenames with spaces are fully supported — output names sanitize
# spaces to underscores so downstream globs work safely.
#
# Usage:
#   ./scripts/ingest_evidence.sh
#
set -e

EVIDENCE_DIR="input/evidence"
EVIDENCE_OUT="output/career_wealth_chunk"
CHUNK_SIZE_THRESHOLD=8192   # bytes — files larger than this get chunked
CHUNK_LINE_LIMIT=120        # fallback: split every N lines if no headings found

echo "📂 Ingesting evidence files from $EVIDENCE_DIR/ ..."

if [ ! -d "$EVIDENCE_DIR" ] || [ -z "$(ls -A "$EVIDENCE_DIR" 2>/dev/null | grep -v '^[.]')" ]; then
  echo "⚠️  No files found in $EVIDENCE_DIR/"
  echo "   Drop evidence files there first: .pdf, .xlsx, .txt, .docx"
  exit 1
fi

echo "🗑️  Clearing stale chunks from $EVIDENCE_OUT/ ..."
docker exec markitdown bash -c "rm -f /output/career_wealth_chunk/*.md 2>/dev/null || true"
mkdir -p "$EVIDENCE_OUT"

# ── Helpers ───────────────────────────────────────────────────────────────────
sanitize() { echo "$1" | tr ' ' '_' | tr -d "'" | tr -d '(' | tr -d ')'; }

container_size() {
  docker exec markitdown bash -c "wc -c < '$1' 2>/dev/null || echo 0" | tr -d '[:space:]'
}

# ── PDFs: pdfplumber → MarkItDown → Tesseract OCR ─────────────────────────────
while IFS= read -r -d '' f; do
  filename=$(basename -- "$f")
  name="${filename%.*}"
  safe_name=$(sanitize "$name")
  out_md="/output/career_wealth_chunk/${safe_name}.md"

  echo "📄 PDF → $filename"

  # Pass 1: pdfplumber (best text fidelity for digital PDFs)
  PLUMBER_RESULT=$(docker exec -i markitdown python3 << PYEOF
import pdfplumber, sys
src = "/input/evidence/${filename}"
out = "${out_md}"
try:
    with pdfplumber.open(src) as pdf:
        text = "\n\n".join(p.extract_text() or "" for p in pdf.pages).strip()
    if len(text) >= 200:
        with open(out, "w") as fh:
            fh.write("# ${safe_name}\n\n" + text)
        print("OK:" + str(len(text)))
    else:
        print("WEAK:" + str(len(text)))
except Exception as e:
    print("ERROR:" + str(e))
PYEOF
)

  if echo "$PLUMBER_RESULT" | grep -qE "^OK:"; then
    CHARS=$(echo "$PLUMBER_RESULT" | sed 's/OK://')
    echo "   ✅ pdfplumber: ${CHARS} chars"
    continue
  fi

  echo "   ↳ pdfplumber ${PLUMBER_RESULT} — trying MarkItDown"

  # Pass 2: MarkItDown
  docker exec markitdown markitdown "/input/evidence/${filename}" -o "${out_md}" 2>/dev/null || true
  SIZE=$(container_size "$out_md")

  if [ "$SIZE" -ge 200 ]; then
    echo "   ✅ MarkItDown: ${SIZE} chars"
    continue
  fi

  echo "   ↳ MarkItDown weak (${SIZE} chars) — trying Tesseract OCR"

  # Pass 3: Tesseract OCR (for scanned/image-only PDFs)
  # Convert PDF pages to images via pdftoppm, then OCR each page
  OCR_RESULT=$(docker exec -i markitdown python3 << PYEOF
import subprocess, os, glob, sys

src = "/input/evidence/${filename}"
safe = "${safe_name}"
out = "${out_md}"
work_dir = f"/tmp/ocr_{safe}"
os.makedirs(work_dir, exist_ok=True)

# Convert PDF to PNG images (one per page) using pdftoppm
try:
    r = subprocess.run(
        ["pdftoppm", "-r", "200", "-png", src, f"{work_dir}/page"],
        capture_output=True, text=True, timeout=120
    )
    pages = sorted(glob.glob(f"{work_dir}/page*.png"))
except FileNotFoundError:
    pages = []

if not pages:
    # pdftoppm not available or no pages — try ghostscript
    try:
        r = subprocess.run(
            ["gs", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m", "-r200",
             f"-sOutputFile={work_dir}/page%03d.png", src],
            capture_output=True, text=True, timeout=120
        )
        pages = sorted(glob.glob(f"{work_dir}/page*.png"))
    except FileNotFoundError:
        pages = []

if not pages:
    print("NO_IMAGES")
    sys.exit(0)

# OCR each page with Tesseract
all_text = []
for page_img in pages:
    page_name = os.path.splitext(page_img)[0]
    try:
        subprocess.run(
            ["tesseract", page_img, page_name, "-l", "eng"],
            capture_output=True, timeout=60
        )
        txt_file = page_name + ".txt"
        if os.path.exists(txt_file):
            with open(txt_file) as fh:
                all_text.append(fh.read().strip())
    except Exception as e:
        all_text.append(f"[OCR error on {os.path.basename(page_img)}: {e}]")

full_text = "\n\n".join(t for t in all_text if t)
if len(full_text) >= 100:
    with open(out, "w") as fh:
        fh.write(f"# {safe}\n\n{full_text}")
    print("OK:" + str(len(full_text)))
else:
    print("WEAK:" + str(len(full_text)))
PYEOF
)

  if echo "$OCR_RESULT" | grep -qE "^OK:"; then
    CHARS=$(echo "$OCR_RESULT" | sed 's/OK://')
    echo "   ✅ Tesseract OCR: ${CHARS} chars"
  elif echo "$OCR_RESULT" | grep -q "NO_IMAGES"; then
    echo "   ⚠️  $filename — no image conversion tool available (pdftoppm/gs missing)"
    echo "      This is likely a scanned PDF. Manual option: export pages as PNG,"
    echo "      save to input/evidence/ as .txt after OCR-ing externally."
  else
    echo "   ⚠️  $filename — all 3 extraction methods failed ($OCR_RESULT)"
    echo "      File may be encrypted, corrupted, or purely image-based without"
    echo "      an available OCR tool. Add a .txt companion file manually."
  fi

done < <(find "$EVIDENCE_DIR" -maxdepth 2 -name "*.pdf" -print0)

# ── XLSX / XLS ────────────────────────────────────────────────────────────────
while IFS= read -r -d '' f; do
  filename=$(basename -- "$f")
  name="${filename%.*}"
  safe_name=$(sanitize "$name")
  echo "📊 XLSX → $filename"
  docker exec markitdown markitdown "/input/evidence/${filename}" \
    -o "/output/career_wealth_chunk/${safe_name}.md"
done < <(find "$EVIDENCE_DIR" -maxdepth 2 \( -name "*.xlsx" -o -name "*.xls" \) -print0)

# ── DOCX ──────────────────────────────────────────────────────────────────────
while IFS= read -r -d '' f; do
  filename=$(basename -- "$f")
  name="${filename%.*}"
  safe_name=$(sanitize "$name")
  echo "📝 DOCX → $filename"
  docker exec markitdown markitdown "/input/evidence/${filename}" \
    -o "/output/career_wealth_chunk/${safe_name}.md"
done < <(find "$EVIDENCE_DIR" -maxdepth 2 -name "*.docx" -print0)

# ── TXT / MD ──────────────────────────────────────────────────────────────────
while IFS= read -r -d '' f; do
  filename=$(basename -- "$f")
  name="${filename%.*}"
  safe_name=$(sanitize "$name")
  echo "📋 TXT/MD → $filename"
  {
    echo "# ${safe_name}"
    echo ""
    cat "$f"
  } | docker exec -i markitdown bash -c "cat > /output/career_wealth_chunk/${safe_name}.md"
done < <(find "$EVIDENCE_DIR" -maxdepth 2 \( -name "*.txt" -o -name "*.md" \) -print0)

# ── Chunk large files ──────────────────────────────────────────────────────────
# Two strategies:
#   1. Heading-based split (ALL CAPS lines or # markdown headings)
#   2. Line-count fallback for large files with no recognized headings
echo "✂️  Chunking large evidence files ..."

# Write chunk script to a temp file and execute — avoids heredoc quoting/path issues
docker exec -i markitdown python3 << 'PYEOF_CHUNK'
import os, re

THRESHOLD = 8192
LINE_LIMIT = 120
CHUNK_DIR = "output/career_wealth_chunk"

# Find the container's actual working directory
import subprocess
cwd = subprocess.run(["pwd"], capture_output=True, text=True).stdout.strip()
chunk_dir = os.path.join(cwd, CHUNK_DIR)

if not os.path.isdir(chunk_dir):
    # Try absolute path
    chunk_dir = "/" + CHUNK_DIR
    if not os.path.isdir(chunk_dir):
        print(f"ERROR: cannot find {CHUNK_DIR} from cwd={cwd}")
        exit(1)

print(f"   Chunking from: {chunk_dir}")

for fname in sorted(os.listdir(chunk_dir)):
    if not fname.endswith(".md"):
        continue
    fpath = os.path.join(chunk_dir, fname)
    size = os.path.getsize(fpath)
    if size <= THRESHOLD:
        continue

    name = fname[:-3]  # strip .md
    with open(fpath) as fh:
        lines = fh.readlines()

    # Count heading lines
    heading_re = re.compile(r"^(#{1,6} |[A-Z][A-Z ]+$)")
    heading_idxs = [i for i, l in enumerate(lines) if heading_re.match(l.rstrip())]

    MIN_CHUNK = 200  # bytes — merge tiny chunks into previous

    if len(heading_idxs) >= 3:
        print(f"   ✂️  Heading-split: {fname} ({size} bytes, {len(heading_idxs)} headings)")
        # Split at each heading
        raw_parts = []
        for j, idx in enumerate(heading_idxs):
            end = heading_idxs[j+1] if j+1 < len(heading_idxs) else len(lines)
            raw_parts.append(lines[idx:end])
        # Merge tiny chunks (heading-only orphans) into next chunk
        parts = []
        pending = []
        for rp in raw_parts:
            content_size = sum(len(l) for l in rp)
            if content_size < MIN_CHUNK and pending:
                pending.extend(rp)  # merge into previous
            else:
                if pending:
                    parts.append(pending)
                pending = list(rp)
        if pending:
            parts.append(pending)
    else:
        print(f"   ✂️  Line-split: {fname} ({size} bytes, {len(heading_idxs)} headings — {LINE_LIMIT}-line chunks)")
        parts = [lines[i:i+LINE_LIMIT] for i in range(0, len(lines), LINE_LIMIT)]

    # Secondary split: any part still > 3x threshold gets line-split
    final_parts = []
    for part in parts:
        psize = sum(len(l) for l in part)
        if psize > THRESHOLD * 3:
            sub = [part[i:i+LINE_LIMIT] for i in range(0, len(part), LINE_LIMIT)]
            final_parts.extend(sub)
        else:
            final_parts.append(part)

    # Write parts
    for pi, part_lines in enumerate(final_parts, 1):
        if not part_lines:
            continue
        out_path = os.path.join(chunk_dir, f"{name}_part_{pi}.md")
        with open(out_path, "w") as fh:
            fh.writelines(part_lines)

    os.remove(fpath)

# Remove empty files
for fname in os.listdir(chunk_dir):
    fpath = os.path.join(chunk_dir, fname)
    if os.path.getsize(fpath) == 0:
        os.remove(fpath)

print("   Chunking complete.")
PYEOF_CHUNK

true  # ensure set -e doesn't fire on the heredoc exit

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "✅ Evidence ingestion complete."
echo ""
echo "   Files produced in $EVIDENCE_OUT/:"
TOTAL=0
SKIPPED=0
if ls "$EVIDENCE_OUT"/*.md 2>/dev/null | grep -q .; then
  while IFS= read -r chunk; do
    SIZE=$(wc -c < "$chunk")
    if [ "$SIZE" -lt 50 ]; then
      echo "     ⚠️  $(basename "$chunk")  (${SIZE} bytes — likely empty/failed)"
      SKIPPED=$((SKIPPED + 1))
    else
      echo "     ✅ $(basename "$chunk")  (${SIZE} bytes)"
      TOTAL=$((TOTAL + 1))
    fi
  done < <(ls "$EVIDENCE_OUT"/*.md)
else
  echo "     (none — all conversions may have failed)"
fi

echo ""
[ "$SKIPPED" -gt 0 ] && echo "   ⚠️  $SKIPPED file(s) failed — see warnings above for manual action."
echo "   ✅ $TOTAL usable chunk(s) ready for evidence gap pass."
echo ""
echo "👉 Next:"
echo "   ./scripts/ats_evidence_gap.sh \"output/JD.md\" \"<variant_name>\""
