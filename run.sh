#!/bin/bash

set -e

PIPELINE_START=$(date +%s)

echo "🚀 Running full document pipeline..."
echo "   router → extract → clean → chunk"

# ✅ 1. Setup / ensure container is running
STAGE_START=$(date +%s)
./scripts/setup.sh
echo "⏱️  setup: $(($(date +%s) - STAGE_START))s"

# ✅ 2. Route + convert based on file type
#    pdf/  -> pdfplumber, fallback to MarkItDown if extraction is weak
#    docx/ -> MarkItDown
#    html/ -> MarkItDown
#    image/-> tesseract OCR
#    other/-> MarkItDown (JD .txt files etc.)
STAGE_START=$(date +%s)
./scripts/router.sh
echo "⏱️  router: $(($(date +%s) - STAGE_START))s"

# ✅ 3. Clean extracted text (encoding, bullets, broken lines, headings)
#    Runs via docker exec (perl -pi — cross-platform, Linux/Mac safe)
STAGE_START=$(date +%s)
./scripts/clean.sh
echo "⏱️  clean: $(($(date +%s) - STAGE_START))s"

# ✅ 4. Smart chunking by heading (LLM-friendly chunks in chunks/)
#    Note: chunks ALL .md files currently in output/ — use
#    prepare_variant.sh first if you need single-variant scope for
#    Stage 2/3, or rm -f chunks/<jd_basename>_part_*.md after this
#    step to drop the JD's own chunks from the retrieval candidate pool.
STAGE_START=$(date +%s)
./scripts/smart_chunk.sh
echo "⏱️  smart_chunk: $(($(date +%s) - STAGE_START))s"

TOTAL=$(( $(date +%s) - PIPELINE_START ))
echo "✅ Pipeline complete! (total: ${TOTAL}s)"
echo ""
echo "👉 Next steps:"
echo ""
echo "── SINGLE RESUME ──────────────────────────────────────────────────"
echo "   ATS evaluation against a JD:"
echo "     ./scripts/ats_optimize.sh \"output/JD.md\" \"output/Resume.md\""
echo "     → prompts/ats_prompt.txt  [upload to Claude.ai]"
echo ""
echo "   Cover letter:"
echo "     ./scripts/cover_letter.sh \"output/JD.md\" \"output/Resume.md\""
echo "     → prompts/cover_letter_prompt.txt  [upload to Claude.ai]"
echo "     → save Claude's output to output/cover/cover_letter.md"
echo "     ./scripts/md_to_pdf.sh \"output/cover/cover_letter.md\""
echo "     → output/cover/cover_letter.pdf"
echo ""
echo "   General Q&A:"
echo "     ./scripts/semantic_retrieve.sh \"your question\""
echo "     → prompts/semantic_prompt.txt  [upload to Claude.ai]"
echo ""
echo "── MULTI-VARIANT MANUAL WORKFLOW ──────────────────────────────────"
echo "   1. ./scripts/variant_rank.sh \"output/JD.md\" \"output/resume\""
echo "      → prompts/variant_rank_prompt.txt"
echo "      → UPLOAD TO CLAUDE.AI (Stage 0/1: manual_only per policy)"
echo ""
echo "   2. ./scripts/prepare_variant.sh \"output/resume/<chosen>.md\" \"output/JD.md\""
echo "      → isolates one variant in output/ (archives the rest)"
echo ""
echo "   3. ./scripts/smart_chunk.sh"
echo "      rm -f chunks/<jd_basename>_part_*.md   ← drop JD chunks"
echo ""
echo "   4. ./scripts/ats_optimize.sh \"output/JD.md\" \"output/<chosen>.md\""
echo "      → prompts/ats_prompt.txt  [upload to Claude.ai, or run locally]"
echo "      Optional local: ./scripts/llm_execute.sh prompts/ats_prompt.txt stage_2_ats_optimize <model>"
echo ""
echo "   5. ./scripts/ats_recommend.sh \"output/JD.md\" \"<variant_name>\""
echo "      → prompts/ats_recommend_prompt.txt"
echo "      → UPLOAD TO CLAUDE.AI (Stage 3: manual_only per policy)"
echo ""
echo "   6. ./scripts/cover_letter.sh \"output/JD.md\" \"output/<chosen>.md\""
echo "      → prompts/cover_letter_prompt.txt  [upload to Claude.ai]"
echo "      → ./scripts/md_to_pdf.sh \"output/cover/cover_letter.md\""
echo ""
echo "── AGENT WORKFLOW (all stages, Ollama) ─────────────────────────────"
echo "   ./scripts/ats_workflow.sh \"output/JD.md\" \"output/resume\""
echo "   → interactive model selection from pulled Ollama models"
echo "   → or: --model deepseek-r1:14b to specify directly"
echo "   → Stage 0/1 and Stage 3 warn and require confirmation (manual_only)"
echo "   → Stage 2 runs automatically (local_allowed)"
echo "   → all prompts still written to prompts/ regardless of automation"
echo ""
echo "── POLICY LAYER ────────────────────────────────────────────────────"
echo "   Execution rules live in policy/execution_policy.json"
echo "   Enforcement: policy/policy_check.py <stage_key>"
echo "   Stage classifications:"
echo "     stage_0_1_variant_rank  → manual_only  (3/3 local models failed)"
echo "     stage_1_5_prepare_variant → local_always (no LLM, deterministic)"
echo "     stage_2_ats_optimize    → local_allowed (advisory trust)"
echo "     stage_3_ats_recommend   → manual_only  (3/3 local models failed)"
echo "     cover_letter            → untested     (manual until evaluated)"
echo ""
echo "── OUTPUT LOCATIONS ────────────────────────────────────────────────"
echo "   prompts/                  generated prompt files (all stages)"
echo "   prompts/<model_name>/     Ollama response files, per model"
echo "   output/                   converted + cleaned .md files"
echo "   output/resume/            variant bank (.md, one per target role)"
echo "   output/cover/             cover letters and PDFs"
echo "   output/_archive/          files moved by prepare_variant.sh"
echo "   chunks/                   heading-split chunks (rebuilt each run)"
echo ""
echo "   NOTE: always use output/*.md (post-clean), not input/ source files"
