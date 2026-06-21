#!/bin/bash

set -e

PIPELINE_START=$(date +%s)

echo "🚀 Running full document pipeline..."
echo "   router → extract → clean → chunk → retrieve → ATS prompt"

# ✅ 1. Setup / ensure container is running
STAGE_START=$(date +%s)
./scripts/setup.sh
echo "⏱️  setup: $(($(date +%s) - STAGE_START))s"

# ✅ 2. Route + convert based on file type
#    pdf/  -> pdfplumber, fallback to MarkItDown if extraction is weak
#    docx/ -> MarkItDown
#    html/ -> MarkItDown
#    image/-> tesseract OCR
#    other/-> MarkItDown
STAGE_START=$(date +%s)
./scripts/router.sh
echo "⏱️  router: $(($(date +%s) - STAGE_START))s"

# ✅ 3. Clean extracted text (encoding, bullets, broken lines, headings)
STAGE_START=$(date +%s)
./scripts/clean.sh
echo "⏱️  clean: $(($(date +%s) - STAGE_START))s"

# ✅ 4. Smart chunking by heading (LLM-friendly chunks in chunks/)
STAGE_START=$(date +%s)
./scripts/smart_chunk.sh
echo "⏱️  smart_chunk: $(($(date +%s) - STAGE_START))s"

TOTAL=$(( $(date +%s) - PIPELINE_START ))
echo "✅ Pipeline complete! (total: ${TOTAL}s)"
echo ""
echo "👉 Next steps:"
echo "   General Q&A over the document:"
echo "     ./scripts/semantic_retrieve.sh \"your question\""
echo ""
echo "   ATS-style resume evaluation against a job description"
echo "   (scoring, gaps, recruiter verdict — facts-only, upload file to Claude.ai):"
echo "     ./scripts/ats_optimize.sh \"output/JD_filename.md\" \"output/YourResume.md\""
echo ""
echo "   Cover letter for a job description"
echo "   (facts-only, flags unaddressed JD requirements, upload file to Claude.ai):"
echo "     ./scripts/cover_letter.sh \"output/JD_filename.md\" \"output/YourResume.md\""
echo ""
echo "   Multiple resume variants? Use this workflow instead of ats_optimize.sh:"
echo "     1. ./scripts/variant_rank.sh \"<jd>\" \"output/resume\"   (fit gate + ranking)"
echo "     2. ./scripts/prepare_variant.sh \"output/resume/<chosen>.md\" \"output/<jd>.md\""
echo "     3. ./scripts/smart_chunk.sh"
echo "     4. rm -f chunks/<jd_basename>_part_*.md          # ← the manual step: drop JD chunks before Stage 2/3"
echo "     5. ./scripts/ats_optimize.sh \"<jd>\" \"output/<chosen>.md\""
echo "     6. ./scripts/ats_recommend.sh \"<jd>\" \"<variant_name>\""
echo "   All generated prompt files (ats_prompt.txt, cover_letter_prompt.txt,"
echo "   variant_rank_prompt.txt, ats_recommend_prompt.txt, semantic_prompt.txt)"
echo "   are saved under prompts/, not the project root."
echo ""
echo "   NOTE: point these at output/*.md (post-clean), not input/*.txt —"
echo "   the input/ version hasn't had encoding/mojibake cleanup applied yet."
echo "   Convert and md file to pdf"
echo ""
echo "   Or run all 6 stages automatically (local Ollama, swappable model,"
echo "   warns before auto-running multi-document stages):"
echo "     ./scripts/ats_workflow.sh \"output/JD.md\" \"output/resume\" --model llama3.1:8b"
