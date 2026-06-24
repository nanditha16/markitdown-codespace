# markitdown-codespace

A document ingestion and ATS resume evaluation pipeline built on
[MarkItDown](https://github.com/microsoft/markitdown), Docker, sentence
embeddings, and a policy-gated prompt-generation layer for use with
Claude.ai (or any LLM).

**Design principle:** every script generates a structured prompt file and
saves it to `prompts/`. Nothing calls an LLM API by default. You upload
the prompt to Claude.ai for the actual evaluation. Local Ollama execution
is available as an additive layer — it never replaces the prompt files.

---

## Folder structure

```
markitdown-codespace/
├── input/                    Drop source files here before running run.sh
│   ├── pdf/                  Resume PDFs → pdfplumber (MarkItDown fallback)
│   ├── docx/                 Word docs → MarkItDown
│   ├── html/                 HTML files → MarkItDown
│   ├── image/                Images → tesseract OCR
│   └── other/                JD text files, anything else → MarkItDown
├── output/                   Converted + cleaned .md files land here
│   ├── resume/               Variant bank — one .md per target role/company
│   ├── cover/                Cover letters (.md) and exported PDFs
│   └── _archive/             Files moved by prepare_variant.sh (not deleted)
├── chunks/                   Heading-split .md chunks (rebuilt each run.sh)
├── prompts/                  ALL generated prompt files land here
│   └── <model_name>/         Ollama response files, separated per model
├── policy/
│   ├── execution_policy.json Stage trust classifications (single source of
│   │                         truth — edit here to change system behavior)
│   └── policy_check.py       Enforcement layer (read by llm_execute.sh)
├── scripts/                  All pipeline scripts
├── run.sh                    Entry point: build → route → clean → chunk
├── Dockerfile
└── docker-compose.yml
```

---

## Quick start

```bash
# 1. Put your files in input/{pdf,docx,html,image,other}/
# 2. Run the pipeline
./run.sh

# 3. Follow the next-steps output for your workflow
```

---

## Workflows
### One time data set building
```
# Stage -1 - (One Time Activity) — file-level edits Enhance based on evidence
# → (converts evidence to output/career_wealth_chunk/*.md")
./scripts/ingest_evidence.sh

```

### Single resume, manual

```bash
./scripts/ats_optimize.sh "output/JD.md" "output/Resume.md"
# → upload prompts/ats_prompt.txt to Claude.ai

./scripts/cover_letter.sh "output/JD.md" "output/Resume.md"
# → upload prompts/cover_letter_prompt.txt to Claude.ai
# → save output to output/cover/cover_letter.md
./scripts/md_to_pdf.sh "output/cover/cover_letter.md"
# → output/cover/cover_letter.pdf
```

### Multi-variant, manual (recommended path - per round)

```bash
# Stage 0/1 — fit gate + ranking
./scripts/variant_rank.sh "output/JD.md" "output/resume"
# → upload prompts/variant_rank_prompt.txt to Claude.ai (manual_only per policy)

# Stage 1.5 — isolate chosen variant
./scripts/prepare_variant.sh "output/resume/<chosen>.md" "output/JD.md"
./scripts/smart_chunk.sh
rm -f chunks/<jd_basename>_part_*.md   # drop JD chunks from retrieval pool

# Stage 2 — ATS evaluation
./scripts/ats_optimize.sh "output/JD.md" "output/<chosen>.md"
# → upload prompts/ats_prompt.txt to Claude.ai
# → or run locally: ./scripts/llm_execute.sh prompts/ats_prompt.txt stage_2_ats_optimize <model>

"
# Stage 3 — file-level edits
./scripts/ats_recommend.sh "output/JD.md" "<variant_name_without_extension>"
# → upload prompts/ats_recommend_prompt.txt to Claude.ai (manual_only per policy)

# Stage 4 - Run the gap pass:
./scripts/ats_evidence_gap.sh \"output/JD.md\" \"<variant_name>\""
# → prompts/ats_evidence_gap_prompt.txt  [UPLOAD TO CLAUDE.AI]"
# Surfaces real experience never captured in any resume variant"

# Stage 5 - Convert the updated resume PDF inside the container
docker exec markitdown markitdown "/output/Nanditha_Murthy_Resume_JD5.pdf" \
  -o "/output/Nanditha_Murthy_Resume_JD5.md"

# Verify it produced content
wc -c output/Nanditha_Murthy_Resume_JD5.md

# Stage 6 - Cover letter for the updated file
./scripts/cover_letter.sh "output/JD.md" "output/<chosen>.md"

./scripts/cover_letter.sh "output/JD5.md" "output/Nanditha_Murthy_Resume_JD5.md"

"
# → upload prompts/cover_letter_prompt.txt to Claude.ai
./scripts/md_to_pdf.sh "output/cover/cover_letter.md"


```

### Agent workflow (Ollama)

```bash
./scripts/ats_workflow.sh "output/JD.md" "output/resume"
# → interactive model selection from pulled Ollama models
# → or: --model deepseek-r1:14b to specify directly
# → all prompts still written to prompts/ regardless of automation
```

---

## Policy and execution trust

All execution rules live in `policy/execution_policy.json`. Edit that file
to change system behavior — no script hardcodes rules independently.

| Stage | Script | Policy | Trust Level |
|---|---|---|---|
| Stage 0/1 Variant Rank | variant_rank.sh | `manual_only` | — |
| Stage 1.5 Prepare | prepare_variant.sh | `local_always` | N/A (no LLM) |
| Stage 2 ATS Optimize | ats_optimize.sh | `local_allowed` | advisory |
| Stage 3 ATS Recommend | ats_recommend.sh | `manual_only` | — |
| Cover Letter | cover_letter.sh | `untested` | — |

**Why manual_only for Stage 0/1 and Stage 3:** three different local models
(llama3:8b, llama3.1:8b, deepseek-r1:14b) were tested against identical
prompts. All three failed Stage 0/1 (hallucinated variant names, ignored
the actual task) and all three failed Stage 3 (produced formatting audits
instead of the requested paraphrase edits). This is a documented, measured
capability ceiling — not a configuration problem. Stage 2 (single-resume
scoring) worked adequately across all three models.

**Trust labels on every Ollama response file:**
- `advisory` — Stage 2 output. Directionally useful, spot-check Critical
  Gaps specifically (2/3 models fabricated at least one).
- `unsafe` — Stage 0/1 or Stage 3 output run via Ollama with `--override`.
  Never present as a final answer.

---

## Local Ollama execution

```bash
# Run a stage locally (policy-gated):
./scripts/llm_execute.sh <prompt_file> <stage_key> <model>

# Examples:
./scripts/llm_execute.sh prompts/ats_prompt.txt stage_2_ats_optimize llama3.1:8b
./scripts/llm_execute.sh prompts/variant_rank_prompt.txt stage_0_1_variant_rank llama3.1:8b --override

# Check policy for a stage:
python3 policy/policy_check.py stage_2_ats_optimize
python3 policy/policy_check.py stage_0_1_variant_rank          # shows why it's blocked
python3 policy/policy_check.py stage_0_1_variant_rank --override  # shows unsafe trust level

# Context window: always queried live from /api/tags — never hardcoded
# Timeout: default 1800s, override with: LLM_TIMEOUT_SECONDS=3600 ./scripts/llm_execute.sh ...
# Response location: prompts/<sanitized_model_name>/<prompt_name>_response.txt
```

---

## Known gotchas

**Clipboard corruption:** `pbcopy` was confirmed to corrupt em-dashes and
smart quotes on the clipboard round-trip. Always upload prompt files as
file attachments — never paste.

**JD chunks in retrieval pool:** `smart_chunk.sh` chunks every `.md` in
`output/`, including the JD file. After chunking, run:
```bash
rm -f chunks/<jd_basename>_part_*.md
```
This is done automatically by `ats_workflow.sh` but is a manual step in
the individual-script workflow. The eBay JD run (JD2.md, final test) was
verified clean — no JD content in retrieved resume sections.

**Model warm-up time:** `deepseek-r1:14b` measured at 738s/871s/918s per
stage on a 16GB Mac with active memory pressure. The machine had only
147MB free RAM and was actively swapping during these runs. Freeing memory
(quit Docker when not in use, `docker compose down`) improves these times.

**Wrong stage_key:** passing `stage_1_5_prepare_variant` as a stage_key to
`llm_execute.sh` now errors immediately (that stage involves no LLM).

---

## Architecture notes (for future extension)

- **Host vs. container:** text-transforming scripts (`clean.sh`,
  `smart_chunk.sh`, `retrieve.py`) run via `docker exec` for
  Linux/Mac compatibility (BSD vs GNU tool differences caused real bugs).
  Prompt-assembly scripts run host-side (pure file I/O, no transformation).

- **Embedding similarity was replaced** for variant ranking. Two tested
  variants scored 0.81 similar to each other (shared boilerplate dominated)
  while either scored only 0.27–0.37 against the JD. LLM-judgment prompts
  are used instead in `variant_rank.sh`.

- **Policy as code, not documentation:** `execution_policy.json` and
  `policy_check.py` enforce the trust model in code. Editing the JSON
  propagates to every script — nothing re-implements the rules inline.

- **Additive automation:** local model execution is always additive. Every
  prompt file exists independently of whether automation ran. If Ollama
  fails, the prompt file is still there for Claude.ai upload.

- **Cloud API integration deliberately deferred:** placeholder schema
  exists in `policy/execution_policy.json` under `cost_and_limits`, marked
  `"integrated": false`. Do not display cost estimates to users until a
  provider is actually wired in and verified against real billing.
