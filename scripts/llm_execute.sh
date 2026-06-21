#!/bin/bash
#
# llm_execute.sh — Sends a prompt file to a local Ollama model and saves
# the response. ADDITIVE — the prompt file this reads already exists
# regardless of whether this runs; if Ollama isn't running or this fails,
# the prompt file is still there to upload manually to Claude.ai.
#
# Model is fully swappable — pass any model name you have pulled via
# `ollama pull <model>`. Context window is queried LIVE from Ollama's
# /api/tags for whichever model you specify, never hardcoded — verified
# against a real instance across multiple models (llama3:8b → 8192,
# llama3.1:8b → 131072).
#
# Usage:
#   ./scripts/llm_execute.sh <prompt_file> <model> [--force]
#
#   Examples:
#     ./scripts/llm_execute.sh prompts/ats_prompt.txt llama3.1:8b
#     ./scripts/llm_execute.sh prompts/ats_prompt.txt qwen2.5:14b
#
# KNOWN LIMITATION (confirmed via real testing, not theoretical): even
# when a prompt fits within a model's context window, multi-document
# reasoning tasks (variant_rank_prompt.txt, ats_recommend_prompt.txt) have
# shown unreliable results on 8B-class models — wrong task entirely
# ignored, hallucinated content, lost output format. This script WARNS on
# those filenames but does not block, per design choice — you decide.
#
set -e

PROMPT_FILE="$1"
MODEL="$2"
FORCE_FLAG="$3"

OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"

if [ -z "$PROMPT_FILE" ] || [ -z "$MODEL" ]; then
  echo "❌ Usage: ./scripts/llm_execute.sh <prompt_file> <model_name> [--force]"
  echo "   Example: ./scripts/llm_execute.sh prompts/ats_prompt.txt llama3.1:8b"
  echo ""
  echo "   --force sends the prompt even if it exceeds the model's context"
  echo "   window (response quality is not guaranteed in that case)."
  exit 1
fi

if [ ! -f "$PROMPT_FILE" ]; then
  echo "❌ Prompt file not found: $PROMPT_FILE"
  exit 1
fi

echo "🔍 Checking Ollama is reachable at $OLLAMA_URL ..."
TAGS_RESPONSE=$(curl -s --max-time 5 "$OLLAMA_URL/api/tags" 2>&1) || {
  echo "❌ Could not reach Ollama at $OLLAMA_URL"
  echo "   Is it running? Try: ollama serve"
  exit 1
}

if ! echo "$TAGS_RESPONSE" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
  echo "❌ Ollama responded but not with valid JSON. Got:"
  echo "$TAGS_RESPONSE" | head -c 500
  exit 1
fi

CONTEXT_LENGTH=$(echo "$TAGS_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
model = '$MODEL'
for m in data.get('models', []):
    if m.get('name') == model or m.get('model') == model:
        print(m.get('details', {}).get('context_length', ''))
        sys.exit(0)
print('')
")

if [ -z "$CONTEXT_LENGTH" ]; then
  echo "❌ Model '$MODEL' not found in 'ollama list' / /api/tags."
  echo "   Available models:"
  echo "$TAGS_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('models', []):
    print('  -', m.get('name'), f\"(context: {m.get('details', {}).get('context_length', '?')})\")
"
  echo "   Pull it first with: ollama pull $MODEL"
  exit 1
fi

echo "✅ Model '$MODEL' found, context window: $CONTEXT_LENGTH tokens"

PROMPT_CHARS=$(wc -c < "$PROMPT_FILE" | tr -d ' ')
ESTIMATED_TOKENS=$((PROMPT_CHARS / 4))
echo "📏 Prompt file: $PROMPT_FILE ($PROMPT_CHARS chars, ~${ESTIMATED_TOKENS} estimated tokens)"

if [ "$ESTIMATED_TOKENS" -gt "$CONTEXT_LENGTH" ]; then
  echo ""
  echo "❌ Prompt (~${ESTIMATED_TOKENS} tokens) exceeds '$MODEL''s context"
  echo "   window (${CONTEXT_LENGTH} tokens)."
  if [ "$FORCE_FLAG" != "--force" ]; then
    echo "   Options:"
    echo "   1. Use a larger-context model (check 'ollama list' / pull one)"
    echo "   2. Use a cloud model instead (upload $PROMPT_FILE to Claude.ai manually)"
    echo "   3. Re-run with --force to send anyway (not recommended)"
    exit 1
  else
    echo "   ⚠️  --force given, sending anyway. Output quality not guaranteed."
  fi
fi

# Warn (don't block) on multi-document reasoning prompts — confirmed via
# real testing to be unreliable on 8B-class local models even when they
# technically fit the context window.
BASENAME=$(basename "$PROMPT_FILE")
if [[ "$BASENAME" == variant_rank_prompt* || "$BASENAME" == ats_recommend_prompt* ]]; then
  echo ""
  echo "⚠️  WARNING: $BASENAME is a multi-document reasoning task."
  echo "   Real testing showed local 8B models can fit this in context but"
  echo "   still fail the task (no variant named, hallucinated content,"
  echo "   lost output format). STRONGLY RECOMMENDED: upload $PROMPT_FILE"
  echo "   to Claude.ai manually instead."
  echo "   Proceeding anyway in 3 seconds (Ctrl+C to cancel)..."
  sleep 3
fi

echo "🧠 Sending to $MODEL via Ollama (this may take a while on CPU)..."

# Timeout is configurable via LLM_TIMEOUT_SECONDS env var (default 1800s
# = 30 min). The original 900s (15 min) default was tuned against
# llama3.1:8b's ~300s real runs with headroom — too short for larger or
# reasoning-style models (e.g. deepseek-r1, which generates extended
# internal "thinking" output before its final answer, often 3-10x more
# tokens than a direct-answer model of similar size) on large prompts.
# Confirmed via real timeout: deepseek-r1:14b exceeded 900s on the
# ~52K-token Stage 0/1 prompt and never got the chance to write output.
TIMEOUT_SECONDS="${LLM_TIMEOUT_SECONDS:-1800}"
echo "   (timeout: ${TIMEOUT_SECONDS}s — set LLM_TIMEOUT_SECONDS to change)"

PROMPT_CONTENT=$(cat "$PROMPT_FILE")
REQUEST_START=$(date +%s)

RESPONSE=$(python3 -c "
import json, sys
import urllib.request

payload = json.dumps({
    'model': sys.argv[1],
    'prompt': sys.argv[2],
    'stream': False
}).encode('utf-8')

req = urllib.request.Request(
    '$OLLAMA_URL/api/generate',
    data=payload,
    headers={'Content-Type': 'application/json'},
    method='POST'
)

try:
    with urllib.request.urlopen(req, timeout=$TIMEOUT_SECONDS) as resp:
        body = json.loads(resp.read().decode('utf-8'))
        if 'error' in body:
            print('OLLAMA_ERROR:' + body['error'], file=sys.stderr)
            sys.exit(1)
        print(body.get('response', ''))
except TimeoutError:
    print('TIMEOUT_ERROR: no response after ${TIMEOUT_SECONDS}s', file=sys.stderr)
    sys.exit(2)
except Exception as e:
    err_str = str(e)
    if 'timed out' in err_str.lower():
        print('TIMEOUT_ERROR: no response after ${TIMEOUT_SECONDS}s', file=sys.stderr)
        sys.exit(2)
    print('REQUEST_ERROR:' + err_str, file=sys.stderr)
    sys.exit(1)
" "$MODEL" "$PROMPT_CONTENT")

REQUEST_EXIT=$?
REQUEST_END=$(date +%s)

if [ $REQUEST_EXIT -eq 2 ]; then
  echo "❌ TIMEOUT after $((REQUEST_END - REQUEST_START))s — this is NOT a"
  echo "   crash. The model is likely still slower than ${TIMEOUT_SECONDS}s"
  echo "   for this prompt size (larger/reasoning-style models like"
  echo "   deepseek-r1 generate extended internal output before answering)."
  echo "   Options:"
  echo "   1. Re-run with a longer timeout: LLM_TIMEOUT_SECONDS=3600 $0 $*"
  echo "   2. Use a smaller/faster model"
  echo "   3. Upload the prompt to Claude.ai instead (always available,"
  echo "      no timeout)"
  exit 1
elif [ $REQUEST_EXIT -ne 0 ]; then
  echo "❌ Ollama request failed."
  exit 1
fi

echo "⏱️  Generation took $((REQUEST_END - REQUEST_START))s"

# Sanitize model name for use as a directory name (':' and '/' aren't
# safe as literal path components on all filesystems/shells) — the real
# $MODEL value (unsanitized) is still what's sent to the Ollama API above.
MODEL_DIR=$(echo "$MODEL" | tr ':/' '__')
RESPONSE_DIR="prompts/${MODEL_DIR}"
mkdir -p "$RESPONSE_DIR"

OUTPUT_FILE="${RESPONSE_DIR}/$(basename "${PROMPT_FILE%.txt}")_response.txt"
echo "$RESPONSE" > "$OUTPUT_FILE"

echo "✅ Response saved to $OUTPUT_FILE"
echo "👉 The original prompt file ($PROMPT_FILE) is still there if you want"
echo "   to also run it through Claude.ai for comparison."
