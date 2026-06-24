#!/bin/bash
#
# ats_evidence_gap.sh — Stage 3.5 of the ATS workflow.
#
# PURPOSE:
# Stage 2 (ats_optimize) + Stage 3 (ats_recommend) identify gaps between
# the JD and the current resume variant and propose minimal paraphrases
# for PRESENTATION gaps. But both stages are constrained to what is
# ALREADY IN the resume/chunks — they cannot surface experience that was
# real but never written into any variant.
#
# This stage adds a second question: for each gap flagged in Stage 2/3,
# is there evidence in the career wealth corpus (Career_Wealth.xlsx,
# iRecon_pointers.pdf, Apple notes, etc.) that could LEGITIMATELY close
# it — material the candidate actually did, just never captured on any
# resume variant?
#
# TWO-PHASE REASONING (structured into the prompt):
#   Phase A — Gap vs. Evidence Match:
#     For each gap from Stage 2/3, search the evidence chunks for facts
#     that genuinely address it. Cite the exact source file and the
#     specific text. Do not stretch weak matches.
#   Phase B — New Material Recommendation:
#     For each match found, propose the minimal addition to the resume
#     variant — NOT paraphrase of existing text, but surfacing real
#     unlisted experience. Flag which chunk file the fact lives in so
#     the candidate knows exactly where to verify it.
#
# CONSTRAINT INHERITED FROM ats_recommend_prompt:
#   Do not fabricate. If no evidence chunk matches a gap, say so explicitly
#   as a TRUE GAP (no evidence in corpus). That is a better outcome than
#   a fabricated closure.
#
# INPUT REQUIREMENTS:
#   1. output/career_wealth_chunk/*.md   ← evidence corpus chunks
#                                           (run ingest_evidence.sh first)
#   2. prompts/ats_recommend_prompt.txt  ← Stage 3 output (gaps list)
#      OR pass the gap list inline.
#   3. JD file or text
#   4. Variant name (same as Stage 3)
#
# OUTPUT:
#   prompts/ats_evidence_gap_prompt.txt  ← upload to Claude.ai (manual_only,
#                                          same rationale as Stage 3)
#
# POLICY:
#   manual_only — same as Stage 3. Evidence cross-referencing requires
#   correct attribution (exact source file + exact text). Local 8B models
#   failed Stage 3 on this same task shape. Evidence adds MORE source
#   files to reason across, making local failure more likely, not less.
#   See policy/execution_policy.json: stage_3_5_evidence_gap.
#
# Usage:
#   ./scripts/ats_evidence_gap.sh "output/JD.md" "eBay"
#   ./scripts/ats_evidence_gap.sh "Senior SWE role..." "eBay"
#
# <variant_name>: substring matching your chosen variant's chunk filenames
# (same value you passed to ats_recommend.sh)
#
set -e

JD_INPUT="$1"
VARIANT_NAME="$2"

if [ -z "$JD_INPUT" ] || [ -z "$VARIANT_NAME" ]; then
  echo "❌ Usage: ./scripts/ats_evidence_gap.sh <jd_file_or_text> <variant_name>"
  echo "   Example: ./scripts/ats_evidence_gap.sh \"output/JD.md\" \"eBay\""
  echo ""
  echo "   Run ingest_evidence.sh first to populate output/career_wealth_chunk/"
  exit 1
fi

# ── Resolve JD ───────────────────────────────────────────────────────────────
if [ -f "$JD_INPUT" ]; then
  JD_TEXT=$(cat "$JD_INPUT")
elif [[ "$JD_INPUT" == *"/"* || "$JD_INPUT" == *.txt || "$JD_INPUT" == *.md ]]; then
  echo "❌ '$JD_INPUT' looks like a file path but doesn't exist."
  echo "   Check output/ for the converted JD (router converts input/other/*.txt → output/*.md)"
  exit 1
else
  JD_TEXT="$JD_INPUT"
fi

# ── Verify evidence chunks exist ─────────────────────────────────────────────
EVIDENCE_DIR="output/career_wealth_chunk"
if [ ! -d "$EVIDENCE_DIR" ] || [ -z "$(ls -A "$EVIDENCE_DIR"/*.md 2>/dev/null)" ]; then
  echo "❌ No evidence chunks found in $EVIDENCE_DIR/"
  echo "   Run first: ./scripts/ingest_evidence.sh"
  exit 1
fi

EVIDENCE_COUNT=$(ls "$EVIDENCE_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')
echo "📂 Found $EVIDENCE_COUNT evidence chunk(s) in $EVIDENCE_DIR/"

# ── Verify resume variant chunks exist ───────────────────────────────────────
CHUNK_DIR="chunks"
VARIANT_CHUNKS=$(ls "$CHUNK_DIR"/*"${VARIANT_NAME}"*.md 2>/dev/null)
if [ -z "$VARIANT_CHUNKS" ]; then
  echo "❌ No chunks found matching variant '$VARIANT_NAME' in $CHUNK_DIR/"
  echo "   Available variant patterns:"
  ls "$CHUNK_DIR"/*.md 2>/dev/null | sed 's/_part_[0-9]*.md//' | sort -u | \
    while read -r p; do echo "     $(basename "$p")"; done
  exit 1
fi

VARIANT_CHUNK_COUNT=$(echo "$VARIANT_CHUNKS" | wc -l | tr -d ' ')
echo "📄 Found $VARIANT_CHUNK_COUNT resume chunk(s) for variant '$VARIANT_NAME'"

# ── Load Stage 2/3 gap output if available ───────────────────────────────────
GAP_CONTEXT=""
STAGE2_FILE="prompts/ats_prompt_response.txt"
STAGE3_FILE="prompts/ats_recommend_prompt_response.txt"

# Check for model-namespaced paths too (prompts/<model>/)
for dir in prompts/*/; do
  [ -f "${dir}ats_recommend_prompt_response.txt" ] && STAGE3_FILE="${dir}ats_recommend_prompt_response.txt"
  [ -f "${dir}ats_prompt_response.txt" ] && STAGE2_FILE="${dir}ats_prompt_response.txt"
done

if [ -f "$STAGE3_FILE" ]; then
  GAP_CONTEXT="## Stage 3 Gap Output (from ats_recommend — use this as the primary gap list)

$(cat "$STAGE3_FILE" | head -200)

---
"
  echo "✅ Loaded Stage 3 gap output from: $STAGE3_FILE"
elif [ -f "$STAGE2_FILE" ]; then
  GAP_CONTEXT="## Stage 2 ATS Output (Stage 3 not found — using Stage 2 gaps instead)

$(cat "$STAGE2_FILE" | head -200)

---
"
  echo "⚠️  Stage 3 output not found — using Stage 2 ATS output for gap list: $STAGE2_FILE"
  echo "   For best results, run ats_recommend.sh first and save Claude's response"
  echo "   to $STAGE3_FILE"
else
  echo "⚠️  Neither Stage 2 nor Stage 3 response files found."
  echo "   The evidence prompt will include the JD and resume chunks but will ask"
  echo "   Claude to identify gaps itself before cross-referencing evidence."
  echo "   For better precision: save Claude's Stage 2/3 output and re-run."
fi

# ── Load resume variant chunks ────────────────────────────────────────────────
RESUME_CHUNKS_TEXT=""
for chunk in $VARIANT_CHUNKS; do
  RESUME_CHUNKS_TEXT="${RESUME_CHUNKS_TEXT}
### FILE: $(basename "$chunk")
$(cat "$chunk")
"
done

# ── Load evidence chunks ──────────────────────────────────────────────────────
EVIDENCE_CHUNKS_TEXT=""
for chunk in "$EVIDENCE_DIR"/*.md; do
  [ -f "$chunk" ] || continue
  EVIDENCE_CHUNKS_TEXT="${EVIDENCE_CHUNKS_TEXT}
### EVIDENCE FILE: $(basename "$chunk")
$(cat "$chunk")
"
done

# ── Build prompt ──────────────────────────────────────────────────────────────
PROMPT_FILE="prompts/ats_evidence_gap_prompt.txt"

cat > "$PROMPT_FILE" << PROMPT_EOF
# Role
You are a Senior Technical Recruiter and Resume Strategist performing an
evidence-backed gap resolution pass. In prior stages, a resume was scored
against the JD below and a gap list was produced. Your job in this pass
is narrower and more specific: for each identified gap, check whether the
candidate's EVIDENCE CORPUS (career records, project notes, prior work
files) contains real facts that would legitimately close that gap — facts
that were never captured in any resume variant.

This is NOT another paraphrase pass. This stage surfaces MISSING CONTENT
that already exists in the evidence, not rewording of content already on
the resume.

# Critical Distinction

**Presentation gap (Stage 3 domain):** The fact IS on the resume but
phrased differently from the JD's terminology. Fix: paraphrase.

**Evidence gap (THIS stage's domain):** The fact is NOT on the resume,
but the candidate's own records show they actually did it. Fix: add new
bullet/section from evidence. The resume currently undersells real experience.

**True gap:** The gap exists on the resume AND no evidence chunk supports
it either. This is a legitimate qualification gap. Do not invent a closure.
Name it honestly.

# Constraints — DO NOT BREAK THESE
- Every fact you surface must cite the EXACT evidence filename it came from.
- Quote the supporting text from the evidence file verbatim (do not paraphrase
  it into a claim — let the candidate verify and write the final bullet).
- Do not merge two weak evidence signals into one strong claim.
- If no evidence chunk matches a gap, say so explicitly: "TRUE GAP — no
  evidence found." That is the correct and honest output.
- Do not reference content from one stage's output as if it were evidence.
  The gap list and the evidence corpus are separate inputs.
- Preserve all numbers exactly if they appear in the evidence.

# Two-Phase Output Required

## Phase A — Gap × Evidence Matrix
For each gap from Stage 2/3 (or from your own JD analysis if no prior
output was provided):

**Gap:** [name the specific JD requirement or keyword not on the resume]
**Evidence Found:** YES / NO / PARTIAL
**Source File:** [exact filename from evidence corpus, or "none"]
**Supporting Text:** [verbatim quote from evidence file, or "N/A"]
**Assessment:** [1-2 sentences: does this evidence genuinely close the gap,
                 or is it only adjacent? Be specific about what matches
                 and what doesn't.]

## Phase B — New Material Recommendations
For each gap where Phase A found YES or PARTIAL:

**Gap Addressed:** [gap name]
**Proposed Addition to Resume:** [minimal new bullet point the candidate
  could add — grounded only in the evidence text quoted above, not inferred
  from general knowledge. Write it as a draft the candidate must verify
  before using.]
**Evidence Source:** [filename]
**Where on Resume:** [suggested section: Summary / Experience / Skills /
  Career Highlights / New section]
**Confidence:** HIGH (direct match) / MEDIUM (adjacent, needs candidate
  verification) / LOW (stretch — only use with explicit candidate confirmation)

## True Gaps (no evidence closure)
List each gap where Phase A found NO evidence in the corpus. These are
honest qualification gaps. Do not recommend fabricating content to cover
them.

## Evidence Files Not Used
List any evidence files that contained no facts relevant to any identified
gap — this helps the candidate understand what their corpus covers vs. what
it's missing.

---

# Job Description

$JD_TEXT

---

$GAP_CONTEXT

# Current Resume Variant Chunks (variant: $VARIANT_NAME)

These are the chunks from the resume variant already scored in Stage 2/3.
Use these to confirm what IS already on the resume — do not recommend
adding content that is already here.

$RESUME_CHUNKS_TEXT

---

# Evidence Corpus (output/career_wealth_chunk/)

These files represent the candidate's full career record, project notes,
and experience documentation — the raw material never fully captured in
any resume variant. This is where to look for facts that close gaps.

$EVIDENCE_CHUNKS_TEXT

---

Now produce the Phase A matrix and Phase B recommendations following the
format above. Be specific about source files. Do not generalize.
PROMPT_EOF

echo ""
echo "✅ Evidence gap prompt written to: $PROMPT_FILE"
echo ""

# ── Token estimate ────────────────────────────────────────────────────────────
CHAR_COUNT=$(wc -c < "$PROMPT_FILE")
TOKEN_ESTIMATE=$(( CHAR_COUNT / 4 ))
echo "   Estimated prompt size: ~${TOKEN_ESTIMATE} tokens (${CHAR_COUNT} chars)"
echo ""

if [ "$TOKEN_ESTIMATE" -gt 40000 ]; then
  echo "⚠️  Prompt is large (${TOKEN_ESTIMATE} est. tokens). If your evidence corpus"
  echo "   is very large, consider splitting ingest_evidence.sh runs by category"
  echo "   (e.g. one run per employer) and running this script per category."
  echo ""
fi

echo "🔒 Policy: manual_only — upload to Claude.ai for best results."
echo "   Local 8B models fail multi-document attribution tasks (see Stage 3 evidence)."
echo "   This stage adds MORE source files, making local failure more likely."
echo ""
echo "👉 Upload prompts/ats_evidence_gap_prompt.txt to Claude.ai"
echo "   Save the response to: prompts/ats_evidence_gap_response.txt"
echo ""
echo "📋 Evidence corpus summary ($EVIDENCE_COUNT files):"
ls "$EVIDENCE_DIR"/*.md 2>/dev/null | while read -r f; do
  SIZE=$(wc -c < "$f")
  echo "   $(basename "$f")  (${SIZE} bytes)"
done
