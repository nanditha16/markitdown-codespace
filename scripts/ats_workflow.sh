#!/bin/bash
#
# ats_workflow.sh — Single-entry orchestrator for the full multi-variant
# ATS workflow. Chains variant_rank → prepare_variant → smart_chunk →
# ats_optimize → ats_recommend, auto-executing each stage's prompt via
# Ollama (swappable model), while still writing every prompt file to
# prompts/ for manual upload — automation is additive, never a
# replacement for the manual path.
#
# MODEL SWAPPING: set via --model flag or OLLAMA_MODEL env var. Defaults
# to llama3.1:8b if neither is set (confirmed working in this project's
# testing — 131072 context window, better instruction-following than
# llama3:8b). Any model you've pulled via `ollama pull <model>` works.
#
# STAGE WARNINGS, NOT BLOCKS: Stage 0/1 (variant_rank) and Stage 3
# (ats_recommend) print a strong recommendation to use Claude.ai instead
# of auto-running on Ollama, based on real testing in this project showing
# local 8B-class models fail multi-document reasoning tasks even within
# their context window (ignored the actual task, hallucinated content).
# This is a WARNING — per design choice, it does not block. You decide
# each time whether to proceed with local auto-execution or stop and use
# the manually-generated prompt file with Claude.ai instead.
#
# Usage:
#   ./scripts/ats_workflow.sh "output/JD.md" "output/resume" [--model llama3.1:8b]
#
# After Stage 0/1 auto-runs and prints its result, you'll be asked to
# confirm/enter which variant filename to proceed with — this script does
# NOT auto-select a variant for you, since that's a judgment call.
#
set -e

JD_PATH="$1"
VARIANT_DIR="${2:-output/resume}"
MODEL="$OLLAMA_MODEL"
MODEL_EXPLICITLY_SET=false
[ -n "$MODEL" ] && MODEL_EXPLICITLY_SET=true

# Parse --model flag if given (overrides env var / default)
shift 2 2>/dev/null || true
while [ $# -gt 0 ]; do
  case "$1" in
    --model)
      MODEL="$2"
      MODEL_EXPLICITLY_SET=true
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

if [ -z "$JD_PATH" ]; then
  echo "❌ Usage: ./scripts/ats_workflow.sh <jd.md> [variant_dir] [--model <model_name>]"
  echo "   Example: ./scripts/ats_workflow.sh \"output/JD1.md\" \"output/resume\" --model deepseek-r1:14b"
  exit 1
fi

# If no --model/OLLAMA_MODEL was given, don't silently fall back to a
# hardcoded default — list whatever's actually pulled in Ollama right now
# and ask. A hardcoded default string can reference a model that's been
# deleted (confirmed real scenario: llama3.1:8b was the old default, then
# deleted, then deepseek-r1:14b pulled — a hardcoded default would have
# pointed at a model that no longer exists).
if [ "$MODEL_EXPLICITLY_SET" = false ]; then
  OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
  echo "🔍 No --model given — checking which models are available in Ollama..."
  TAGS_RESPONSE=$(curl -s --max-time 5 "$OLLAMA_URL/api/tags" 2>&1) || {
    echo "❌ Could not reach Ollama at $OLLAMA_URL to list models. Is it running?"
    echo "   Or pass --model explicitly: --model <name>"
    exit 1
  }

  AVAILABLE_MODELS=$(echo "$TAGS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for i, m in enumerate(data.get('models', []), 1):
    ctx = m.get('details', {}).get('context_length', '?')
    print(f\"{i}. {m.get('name')} (context: {ctx})\")
")

  if [ -z "$AVAILABLE_MODELS" ]; then
    echo "❌ No models found in Ollama. Pull one first: ollama pull <model>"
    exit 1
  fi

  echo ""
  echo "Available models:"
  echo "$AVAILABLE_MODELS"
  echo ""
  read -p "Enter the exact model name to use (e.g. deepseek-r1:14b): " MODEL

  if [ -z "$MODEL" ]; then
    echo "❌ No model selected. Re-run with --model <name> or select one above."
    exit 1
  fi
fi

if [ ! -f "$JD_PATH" ]; then
  echo "❌ JD file not found: $JD_PATH"
  exit 1
fi

echo "════════════════════════════════════════════════════════════"
echo "  ATS Workflow — model: $MODEL"
echo "════════════════════════════════════════════════════════════"
echo ""

# ─────────────────────────────────────────────────────────────────────
# STAGE 0/1 — Fit gate + ranking
# ─────────────────────────────────────────────────────────────────────
echo "▶ STAGE 0/1 — Fit gate + variant ranking"
./scripts/variant_rank.sh "$JD_PATH" "$VARIANT_DIR"

echo ""
echo "⚠️  STAGE 0/1 RECOMMENDATION: this is a multi-document reasoning task"
echo "   (all resume variants embedded in one prompt). Real testing in this"
echo "   project showed local 8B models fail this task even when it fits"
echo "   their context window — Claude.ai is strongly recommended instead."
echo ""
read -p "   Auto-run on Ollama ($MODEL) anyway? [y/N] " RUN_STAGE_0
if [[ "$RUN_STAGE_0" =~ ^[Yy]$ ]]; then
  ./scripts/llm_execute.sh prompts/variant_rank_prompt.txt "$MODEL" --force
  echo ""
  echo "📄 Result: prompts/variant_rank_prompt_response.txt"
  echo "   Read it before choosing a variant below — given the warning above,"
  echo "   verify the named variant(s) actually appear in your resume bank"
  echo "   and that the reasoning makes sense before trusting it."
else
  echo "   Skipped. Upload prompts/variant_rank_prompt.txt to Claude.ai,"
  echo "   then come back and re-run this script (it will resume from here"
  echo "   if you answer 'n' again, or just run stages 2+ manually)."
fi

echo ""
echo "────────────────────────────────────────────────────────────"
read -p "Enter the chosen variant filename (e.g. Nanditha_Murthy_Resume_eBay.md): " CHOSEN_VARIANT

if [ -z "$CHOSEN_VARIANT" ]; then
  echo "❌ No variant given. Exiting — re-run when you've decided."
  exit 1
fi

CHOSEN_VARIANT_PATH="$VARIANT_DIR/$CHOSEN_VARIANT"
if [ ! -f "$CHOSEN_VARIANT_PATH" ]; then
  echo "❌ Variant not found at $CHOSEN_VARIANT_PATH"
  exit 1
fi

# ─────────────────────────────────────────────────────────────────────
# STAGE 1.5 — Isolate the chosen variant
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▶ STAGE 1.5 — Isolating chosen variant"
./scripts/prepare_variant.sh "$CHOSEN_VARIANT_PATH" "$JD_PATH"

echo ""
echo "▶ Re-chunking (single variant only)"
./scripts/smart_chunk.sh

# Drop the JD's own chunks so Stage 2/3 retrieval doesn't match the JD
# against itself — known issue, documented fix from this project's
# real testing (see SESSION_SUMMARY.md, bug #10).
JD_BASENAME=$(basename "${JD_PATH%.*}")
rm -f "chunks/${JD_BASENAME}_part_"*.md
echo "🧹 Removed JD's own chunks from chunks/ (prevents JD-matches-itself"
echo "   retrieval bug)"

VARIANT_NAME="${CHOSEN_VARIANT%.*}"

# ─────────────────────────────────────────────────────────────────────
# STAGE 2 — ATS score
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▶ STAGE 2 — ATS evaluation"
./scripts/ats_optimize.sh "$JD_PATH" "output/$CHOSEN_VARIANT"

echo ""
echo "✅ Single-resume task — Ollama tested reliably for this stage."
read -p "   Auto-run on Ollama ($MODEL)? [Y/n] " RUN_STAGE_2
if [[ ! "$RUN_STAGE_2" =~ ^[Nn]$ ]]; then
  ./scripts/llm_execute.sh prompts/ats_prompt.txt "$MODEL"
  echo "📄 Result: prompts/ats_prompt_response.txt"
else
  echo "   Skipped. Upload prompts/ats_prompt.txt to Claude.ai manually."
fi

# ─────────────────────────────────────────────────────────────────────
# STAGE 3 — File-level recommendations
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▶ STAGE 3 — File-level edit recommendations"
./scripts/ats_recommend.sh "$JD_PATH" "$VARIANT_NAME"

echo ""
echo "⚠️  STAGE 3 RECOMMENDATION: this prompt embeds ALL chunks of the"
echo "   chosen resume — a multi-section reasoning task. Same caveat as"
echo "   Stage 0/1 applies; Claude.ai is recommended for precision-critical"
echo "   gap analysis (distinguishing fixable wording from real experience"
echo "   gaps)."
read -p "   Auto-run on Ollama ($MODEL) anyway? [y/N] " RUN_STAGE_3
if [[ "$RUN_STAGE_3" =~ ^[Yy]$ ]]; then
  ./scripts/llm_execute.sh prompts/ats_recommend_prompt.txt "$MODEL" --force
  echo "📄 Result: prompts/ats_recommend_prompt_response.txt"
else
  echo "   Skipped. Upload prompts/ats_recommend_prompt.txt to Claude.ai."
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Workflow complete."
echo "════════════════════════════════════════════════════════════"
echo "  All prompts are in prompts/ regardless of what auto-ran above —"
echo "  use them with Claude.ai any time for a second opinion or as the"
echo "  primary path."
