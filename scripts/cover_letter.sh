#!/bin/bash
#
# cover_letter.sh — Build a facts-only cover letter generation prompt.
#
# Given a job description (text file or inline string) and a converted
# resume markdown file, this:
#   1. Runs two-stage semantic retrieval to pull the resume sections most
#      relevant to the JD (same retrieval used by ats_optimize.sh)
#   2. Wraps those sections in a structured prompt that produces a
#      ready-to-send cover letter, under a strict no-fabrication constraint
#      — a fabricated claim in a cover letter is worse than one in a resume
#      bullet, since it's the first thing a human reads and the easiest to
#      probe in an interview.
#
# This is prompt-only: paste cover_letter_prompt.txt into Claude.ai (or any
# LLM) to get the actual letter. Nothing in this script calls an API.
#
# Usage:
#   ./scripts/cover_letter.sh "path/to/jd.txt" "output/Resume.md"
#   ./scripts/cover_letter.sh "Senior TPM role requiring..." "output/Resume.md"
#
set -e

JD_INPUT="$1"
RESUME_FILE="$2"

if [ -z "$JD_INPUT" ] || [ -z "$RESUME_FILE" ]; then
  echo "❌ Usage: ./scripts/cover_letter.sh <jd_file_or_text> <resume_markdown_path>"
  exit 1
fi

# ✅ Accept either a path to a JD file or raw JD text on the command line.
# Same guard as ats_optimize.sh: a path-like argument that doesn't exist
# fails loudly instead of silently being treated as literal JD text.
if [ -f "$JD_INPUT" ]; then
  JD_TEXT=$(cat "$JD_INPUT")
elif [[ "$JD_INPUT" == *"/"* || "$JD_INPUT" == *.txt || "$JD_INPUT" == *.md ]]; then
  echo "❌ '$JD_INPUT' looks like a file path but doesn't exist."
  echo "   If this JD was routed through input/other/, check for it at"
  echo "   output/$(basename "${JD_INPUT%.*}").md (router converts to .md)."
  exit 1
else
  JD_TEXT="$JD_INPUT"
fi

if [ ! -f "$RESUME_FILE" ]; then
  echo "❌ Resume file not found: $RESUME_FILE"
  exit 1
fi

echo "🧠 Retrieving resume sections relevant to this JD..."

RETRIEVAL_START=$(date +%s)
docker exec markitdown python /app/scripts/retrieve.py "$JD_TEXT"
RETRIEVAL_END=$(date +%s)
echo "⏱️  Retrieval took $((RETRIEVAL_END - RETRIEVAL_START))s"

if [ ! -f "prompts/semantic_prompt.txt" ]; then
  echo "❌ Retrieval failed — prompts/semantic_prompt.txt not produced"
  exit 1
fi

RELEVANT_SECTIONS=$(awk '/RELEVANT CONTEXT:/{flag=1; next} flag' prompts/semantic_prompt.txt)

mkdir -p prompts
OUTPUT_FILE="prompts/cover_letter_prompt.txt"

cat > "$OUTPUT_FILE" << EOF
# Role
You are an executive career writer who writes cover letters for senior
technical and leadership candidates (Engineering Manager, Director, Staff/
Principal Engineer, Technical Program Manager, Platform/Technology
Executive). Your goal is to write a letter a hiring manager actually wants
to finish reading — specific, evidence-based, and free of generic filler —
not a keyword-stuffed restatement of the resume.

# Constraints — DO NOT BREAK THESE
Never:
- Invent experience, employers, titles, metrics, tools, or outcomes not
  present in the resume sections below. A cover letter claim is easier to
  probe in an interview than a resume bullet — fabrication here is higher
  risk, not lower.
- Claim direct experience in a domain the JD requires if the resume
  sections below don't support it. Name the closest real, adjacent
  experience instead and let it stand on its own merit.
- Use generic openers like "I am excited to apply for..." or "I believe I
  would be a great fit..." without immediately backing the claim with a
  specific, verifiable fact from the resume sections.
- Restate the resume's bullet points verbatim in paragraph form. Select 2-3
  of the most JD-relevant facts and develop them with context the resume
  doesn't have room for (why it mattered, what changed because of it).

Always:
- Open with something specific to this company/role drawn from the JD
  text below (a product, a stated priority, a named team) — not a
  generic statement that could apply to any employer.
- Preserve all numbers exactly as stated in the resume sections (years,
  percentages, dollar amounts, team sizes).
- Keep it to 3-4 short paragraphs, under 350 words total. A longer letter
  signals the writer didn't prioritize.
- Close with a direct, low-friction call to action (e.g. availability for
  a conversation) rather than a restatement of enthusiasm.
- If the JD has a requirement with no corresponding resume fact, do not
  paper over it in the letter — either omit it or address it honestly in
  one clause (e.g. "while my background is in X rather than Y, the
  underlying skill of Z transfers directly").

# Output Format
Write the letter only — no preamble, no explanation of choices, no
placeholder brackets except [Hiring Manager Name] and [Date] if unknown.
Use a standard business letter structure: greeting, 2-3 body paragraphs,
closing line, sign-off with the candidate's name from the resume.

After the letter, add a short section titled "NOTES FOR THE CANDIDATE"
listing: (1) any placeholder the candidate must fill in, (2) any JD
requirement the letter did not address because no supporting resume fact
was found.

---

# JOB DESCRIPTION
${JD_TEXT}

---

# RESUME SECTIONS RETRIEVED AS MOST RELEVANT (ranked by semantic similarity)
NOTE: these are the top-matching excerpts only, not the full resume. If the
letter needs a fact likely covered elsewhere (e.g. full work history,
education, certifications), request the complete output/*.md file instead.

${RELEVANT_SECTIONS}

---
Now write the cover letter following the constraints and output format
above.
EOF

echo "✅ Cover letter prompt saved to $OUTPUT_FILE"
echo ""
echo "👉 Upload $OUTPUT_FILE directly to Claude.ai as a file attachment."
echo "   (Use file upload, not copy/paste — clipboard round-trips have"
echo "   been shown to corrupt non-ASCII characters like em-dashes.)"
