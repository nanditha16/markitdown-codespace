#!/bin/bash
#
# variant_rank.sh — Stage 1: build a prompt that gates relevance THEN
# ranks resume variants against a JD using actual LLM judgment.
#
# WHY THIS REPLACED THE EMBEDDING-BASED APPROACH:
# Two earlier versions used sentence-transformer embeddings (whole-document,
# then section-filtered) to score variants. Direct measurement showed this
# didn't work: two genuinely different resume variants scored 0.81-0.82
# similar to EACH OTHER regardless of filtering, while either scored only
# 0.27-0.37 similar to the actual JD. The resumes share too much invariant
# content (same employers, same years, same hard metrics) for embedding
# distance to discriminate the small JD-tailored differences that matter.
#
# WHY A RELEVANCE GATE WAS ADDED (Stage 0):
# A real run against a government/healthcare-system JD showed ALL 19
# variants are "the same underlying resume from slightly different
# angles" — none had genuine government-stakeholder or public-sector
# experience. Ranking 19 weak options against each other produces false
# precision: a numbered list implies meaningful differentiation that
# doesn't exist when the whole variant bank shares the same fundamental
# domain gap. Stage 0 checks the collective bank's profile against the
# JD's core domain/seniority BEFORE producing a ranked list, so a bad-fit
# JD gets flagged plainly instead of dressed up with a fake top pick.
#
# This produces a prompt-only file — paste/upload variant_rank_prompt.txt
# to Claude.ai to get the actual evaluation. Nothing in this script calls
# an API or scores anything itself.
#
# Usage:
#   ./scripts/variant_rank.sh "path/to/jd.txt" "output/resume"
#   ./scripts/variant_rank.sh "Senior TPM role requiring..." "output/resume"
#
set -e

JD_INPUT="$1"
VARIANT_DIR="${2:-output/resume}"

if [ -z "$JD_INPUT" ]; then
  echo "❌ Usage: ./scripts/variant_rank.sh <jd_file_or_text> [variant_directory]"
  echo "   Default variant directory: output/resume"
  exit 1
fi

if [ -f "$JD_INPUT" ]; then
  JD_TEXT=$(cat "$JD_INPUT")
elif [[ "$JD_INPUT" == *"/"* || "$JD_INPUT" == *.txt || "$JD_INPUT" == *.md ]]; then
  echo "❌ '$JD_INPUT' looks like a file path but doesn't exist."
  exit 1
else
  JD_TEXT="$JD_INPUT"
fi

if [ ! -d "$VARIANT_DIR" ]; then
  echo "❌ Directory not found: $VARIANT_DIR"
  exit 1
fi

shopt -s nullglob
VARIANT_FILES=("$VARIANT_DIR"/*.md)
shopt -u nullglob

if [ ${#VARIANT_FILES[@]} -eq 0 ]; then
  echo "❌ No .md files found in $VARIANT_DIR"
  echo "   (If your variants are .pdf, convert them first — this script"
  echo "   only reads .md, same as the rest of the pipeline.)"
  exit 1
fi

echo "📦 Found ${#VARIANT_FILES[@]} resume variant(s) in $VARIANT_DIR"
echo "🧠 Building relevance-gated ranking prompt..."

VARIANT_INVENTORY=""
for f in "${VARIANT_FILES[@]}"; do
  filename=$(basename "$f")
  content=$(cat "$f")
  VARIANT_INVENTORY="${VARIANT_INVENTORY}

### VARIANT: ${filename}
${content}

---"
done

mkdir -p prompts
OUTPUT_FILE="prompts/variant_rank_prompt.txt"

cat > "$OUTPUT_FILE" << EOF
# Role
You are a senior technical recruiter evaluating whether a candidate's
resume bank is worth tailoring for a specific job, and if so, which
variant to start from. The candidate has multiple tailored versions of
the same underlying resume (same person, same 13+ years of experience,
same core employers) — each variant was written or adjusted with a
different target role/company in mind.

# STAGE 0 — Relevance Gate (do this FIRST, before any ranking)

Before ranking individual variants, assess the CANDIDATE'S BANK AS A
WHOLE: what is the common underlying profile across all variants (core
domain, seniority level, type of organization typically targeted —
e.g. "enterprise tech / regulated private-sector TPM, 13+ years,
platform delivery focus")?

Compare that collective profile against the JD's actual core
requirements — not individual keyword matches, but the fundamental
nature of the role:
- What SECTOR does the JD require (e.g. government/public-sector vs.
  private enterprise vs. startup)?
- What STAKEHOLDER TYPE does the JD require experience with (e.g.
  Ministry/government partners vs. internal corporate stakeholders vs.
  consumer-facing)?
- What KIND OF SCOPE does the JD require (e.g. provincial/system-wide
  policy and funding vs. product/platform delivery)?

Then answer plainly:

## Stage 0: Is This Worth Pursuing With This Resume Bank?
State one of:
- **GOOD FIT** — the bank's core domain/sector/stakeholder type
  genuinely matches the JD. Proceed to full ranking below.
- **PARTIAL FIT** — some genuine overlap exists (name what, specifically)
  but a structural gap remains (name it). Proceed to ranking, but the
  candidate should know going in that even the best variant will need
  real reframing, not just paraphrasing.
- **POOR FIT** — the JD's core domain/sector/stakeholder requirement has
  NO genuine counterpart anywhere in the resume bank (e.g. the JD
  requires government/public-sector stakeholder experience and every
  variant's experience is private-sector corporate). If this is the
  case, say so plainly, explain WHY in 2-3 sentences citing the specific
  structural gap, and advise against spending further effort tailoring
  any variant for this JD — no amount of paraphrasing manufactures
  experience that isn't there. You may still produce the ranking below
  if asked, but lead with this assessment so the candidate can decide
  whether it's worth reading further.

---

# STAGE 1 — Ranking (only meaningful if Stage 0 is GOOD FIT or PARTIAL FIT)

For each variant, score 0-100 on each dimension:
- **Domain Fit** (0-100): does the variant's industry/sector framing
  match the JD's actual sector?
- **Seniority/Scope Fit** (0-100): does the variant's framing match the
  JD's level and scope (IC vs. people-management, single program vs.
  portfolio, internal vs. external/regulatory stakeholder scope)?
- **Requirement Coverage** (0-100): how many of the JD's explicitly
  named requirements (tools, certifications, years, domain experience)
  does this variant's content already support with real evidence?

Then give an **Overall Fit Score (0-100)** — NOT a simple average; weight
Domain Fit and Seniority/Scope Fit higher than Requirement Coverage,
since a domain mismatch can't be paraphrased away the way a missing
keyword can.

IMPORTANT: do not inflate scores to create false differentiation. If
multiple variants are genuinely similar in fit, give them similar
scores and say so explicitly — a forced ranking with arbitrary score
gaps is worse than an honest tie.

## Output Format

### Ranking (with scores)
| Rank | Variant | Domain Fit | Seniority/Scope Fit | Requirement Coverage | Overall |
|---|---|---|---|---|---|
| 1 | [filename] | X/100 | X/100 | X/100 | X/100 |
(continue for every variant — but you may group clearly-irrelevant
variants together rather than scoring each individually if Stage 0
was POOR FIT)

### Top Pick
Name the single best-starting-point variant (if any genuinely qualify)
and explain in 2-3 sentences why, citing actual scored dimensions.

### Gaps Even in the Top Pick
List any JD requirements the top-ranked variant does NOT currently
address, so the candidate knows what Stage 2 (ats_optimize.sh) and
Stage 3 (ats_recommend.sh) will need to work on.

### Variants With No Real Fit
Name variants clearly the wrong domain/seniority for this JD, so the
candidate doesn't waste a Stage 2 evaluation on them.

---

# JOB DESCRIPTION
${JD_TEXT}

---

# RESUME VARIANTS (${#VARIANT_FILES[@]} total)
${VARIANT_INVENTORY}

---
Now complete Stage 0 first. Only proceed to the full Stage 1 ranking if
Stage 0 found a GOOD FIT or PARTIAL FIT — if POOR FIT, you may still
provide an abbreviated ranking if useful, but lead with the Stage 0
verdict and reasoning.
EOF

echo "✅ Relevance-gated ranking prompt saved to $OUTPUT_FILE"
echo ""
echo "👉 Upload $OUTPUT_FILE directly to Claude.ai as a file attachment."
echo "   (Use file upload, not copy/paste — clipboard round-trips have"
echo "   been shown to corrupt non-ASCII characters like em-dashes.)"
