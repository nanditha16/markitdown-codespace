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
│   ├── evidence/             Career records, project notes, xlsx, PDFs
│   │                         → used by ingest_evidence.sh (one-time / per update)
│   └── other/                JD text files (JD1.txt, JD2.txt …) → MarkItDown
├── output/                   Converted + cleaned .md files land here
│   ├── resume/               Variant bank — one .md per target role/company
│   ├── cover/                Cover letters (.md) and exported PDFs
│   ├── career_wealth_chunk/  Evidence chunks (from ingest_evidence.sh)
│   └── _archive/             Files moved by prepare_variant.sh (not deleted)
├── chunks/                   Heading-split .md chunks (rebuilt per JD+variant pair)
├── prompts/                  ALL generated prompt files land here
│   ├── JD_Analysis/          Stage 0/1 prompts + responses, one folder per JD
│   │   ├── JDx/              variant_rank_prompt.txt + variant_rank_prompt_response.txt
│   │   └── JDx_NO/           POOR FIT decisions (archived here automatically)
│   ├── JDx_PREP/             Per-JD prep folder (created after variant chosen)
│   │   ├── prom/             All numbered prompt files for this JD
│   │   │   ├── 1_variant_rank_prompt.txt
│   │   │   ├── 1.5_semantic_prompt.txt
│   │   │   ├── 2_ats_prompt.txt
│   │   │   ├── 3_ats_recommend_prompt.txt
│   │   │   └── 4_ats_evidence_gap_prompt.txt
│   │   └── resp/             Paste Claude.ai responses here
│   │       ├── variant_rank_prompt_response.txt
│   │       ├── ats_prompt_response.txt
│   │       ├── ats_recommend_prompt_response.txt
│   │       └── ats_evidence_gap_response.txt
│   └── <model_name>/         Ollama response files, separated per model
├── policy/
│   ├── execution_policy.json Stage trust classifications (single source of
│   │                         truth — edit here to change system behavior)
│   └── policy_check.py       Enforcement layer (read by llm_execute.sh)
├── scripts/                  All pipeline scripts
├── run.sh                    Entry point: setup → route → clean → chunk
├── Dockerfile
└── docker-compose.yml
```

---

## Quick start

```bash
# 1. Put resume PDFs in input/pdf/, JD text files in input/other/JD1.txt etc.
# 2. Run the base pipeline
./run.sh

# 3. (One-time) Ingest career evidence corpus
./scripts/ingest_evidence.sh

# 4. Run batch prep for all JDs — see Batch Workflow below
./scripts/batch_prep.sh
```

---

## Workflows

---

### One-time: Build evidence corpus

```bash
# Drop career records into input/evidence/:
#   Career_Wealth.xlsx, iRecon_pointers.pdf, project notes, etc.

./scripts/ingest_evidence.sh
# → converts all evidence files to output/career_wealth_chunk/*.md
# → uses pdfplumber → MarkItDown → Tesseract OCR fallback chain for PDFs
# → run again whenever new evidence files are added (idempotent)
```

---

### Batch workflow (recommended — handles 1-25 JDs per run)

This is the primary workflow. It automates the full Sequence 1→5 and
reduces manual work to a single human gate: uploading Stage 0/1 prompts
to Claude.ai and pasting responses back.

#### Step 1 — Add JDs and generate Stage 0/1 prompts

```bash
# Drop JD text files into input/other/:
#   JD1.txt, JD2.txt, ... JD25.txt (paste the full JD text into each)

./scripts/batch_prep.sh
# → For each JDx.txt:
#     - Converts JDx.txt → output/JDx.md (via router.sh)
#     - Runs variant_rank.sh against all 21 resume variants
#     - Writes prompts/JD_Analysis/JDx/variant_rank_prompt.txt
# → Prints status dashboard showing all JDs and their stage completion
```

#### Step 2 — Human gate (Claude.ai)

```
For each JD in prompts/JD_Analysis/JDx/:
  1. Upload variant_rank_prompt.txt to Claude.ai (as file attachment)
  2. Paste Claude's full response into:
     prompts/JD_Analysis/JDx/variant_rank_prompt_response.txt
```

Claude's response will include:
- **GOOD FIT / PARTIAL FIT / POOR FIT** decision
- Ranked table of all variants with scores
- **Top Pick** — the specific variant filename to use

#### Step 3 — Generate Stages 2-4 for all JDs with responses

```bash
./scripts/batch_prep.sh --continue
# → Reads each JDx response, extracts chosen variant (auto-resolves fuzzy names)
# → POOR FIT JDs are archived to prompts/JD_Analysis/JDx_NO/ automatically
# → For each GOOD/PARTIAL FIT JD, in order per variant group:
#     1.5  prepare_variant.sh  → isolates chosen resume + JD in output/
#          smart_chunk.sh      → wipes chunks/, rechunks this pair only
#          rm chunks/JDx_part_*.md  → drops JD chunks, keeps resume only
#     2    ats_optimize.sh     → prompts/JDx_PREP/prom/2_ats_prompt.txt
#     3    ats_recommend.sh    → prompts/JDx_PREP/prom/3_ats_recommend_prompt.txt
#     4    ats_evidence_gap.sh → prompts/JDx_PREP/prom/4_ats_evidence_gap_prompt.txt
# → Prints updated dashboard

# Single JD only:
./scripts/batch_prep.sh --continue --jd JD3

# Force regenerate even if prompts exist:
FORCE=1 ./scripts/batch_prep.sh --continue --jd JD3

# Status dashboard only:
./scripts/batch_prep.sh --status
```

#### Step 4 — Upload Stages 2-4 prompts to Claude.ai

For each JDx in `prompts/JDx_PREP/prom/`, upload in order:

| File | Upload to Claude.ai | Save response as |
|---|---|---|
| `2_ats_prompt.txt` | Stage 2: ATS gap analysis | `resp/ats_prompt_response.txt` |
| `3_ats_recommend_prompt.txt` | Stage 3: Paraphrase edits | `resp/ats_recommend_prompt_response.txt` |
| `4_ats_evidence_gap_prompt.txt` | Stage 4: Evidence gaps | `resp/ats_evidence_gap_response.txt` |

Stages 2-4 can be uploaded in parallel across JDs — each is self-contained.

#### Step 5 — Update resume + generate cover letter

```bash
# After editing your resume PDF based on Stage 2/3/4 recommendations:

# Convert updated PDF → MD (inside the container)
docker exec markitdown markitdown "/output/Your_Resume_Updated.pdf" \
  -o "/output/Your_Resume_Updated.md"

# Generate cover letter prompt
./scripts/batch_prep.sh --cover JD3
# → prompts/JD3_PREP/prom/5_cover_letter_prompt.txt  [upload to Claude.ai]

# Or manually:
./scripts/cover_letter.sh "output/JD3.md" "output/Your_Resume_Updated.md"
# → prompts/cover_letter_prompt.txt  [upload to Claude.ai]
./scripts/md_to_pdf.sh "output/cover/cover_letter.md"
# → output/cover/cover_letter.pdf
```

#### batch_prep.sh — all flags

```bash
./scripts/batch_prep.sh                        # Sequence 1: gen Stage 0/1 prompts for all JDx.txt
./scripts/batch_prep.sh --continue             # Sequences 3-5: gen Stages 2-4 for all JDs with responses
./scripts/batch_prep.sh --continue --jd JD3   # Same but single JD only
./scripts/batch_prep.sh --status              # Print dashboard, no other action
./scripts/batch_prep.sh --cover JD3           # Gen Stage 6 cover letter prompt for one JD
FORCE=1 ./scripts/batch_prep.sh --continue    # Re-run even if prompts already exist
```

---

### Non-developer UI

```bash
./scripts/ui.sh
# → Numbered terminal menu covering all steps:
#   1. Add Job Descriptions
#   2. Update Evidence Corpus
#   3. Generate Stage 0/1 Prompts
#   4. Continue → Stages 2-4
#   5. Status Dashboard
#   6. Convert Updated Resume PDF
#   7. Generate Cover Letter
```

---

### Single resume, manual

```bash
# ATS evaluation
./scripts/ats_optimize.sh "output/JD.md" "output/Resume.md"
# → upload prompts/ats_prompt.txt to Claude.ai

# Cover letter
./scripts/cover_letter.sh "output/JD.md" "output/Resume.md"
# → upload prompts/cover_letter_prompt.txt to Claude.ai
./scripts/md_to_pdf.sh "output/cover/cover_letter.md"
# → output/cover/cover_letter.pdf
```

---

### Multi-variant, manual (step-by-step)

Use this when you want full control over each step. `batch_prep.sh --continue`
automates this entire sequence.

```bash
# Stage 0/1 — fit gate + ranking (all variants against one JD)
./scripts/variant_rank.sh "output/JD.md" "output/resume"
# → prompts/variant_rank_prompt.txt  [UPLOAD TO CLAUDE.AI — manual_only per policy]
# → paste response → prompts/JD_Analysis/JDx/variant_rank_prompt_response.txt

# Stage 1.5 — isolate chosen variant (cleans output/ to single variant + JD)
./scripts/prepare_variant.sh "output/resume/<chosen>.md" "output/JD.md"
./scripts/smart_chunk.sh
rm -f chunks/<jd_basename>_part_*.md   # drop JD chunks from retrieval pool

# Stage 2 — ATS evaluation
./scripts/ats_optimize.sh "output/JD.md" "output/<chosen>.md"
# → prompts/ats_prompt.txt  [upload to Claude.ai]
# → or run locally: ./scripts/llm_execute.sh prompts/ats_prompt.txt stage_2_ats_optimize <model>

# Stage 3 — file-level paraphrase edits
./scripts/ats_recommend.sh "output/JD.md" "<variant_name_without_extension>"
# → prompts/ats_recommend_prompt.txt  [UPLOAD TO CLAUDE.AI — manual_only per policy]

# Stage 4 — evidence gap pass
./scripts/ats_evidence_gap.sh "output/JD.md" "<variant_name>"
# → prompts/ats_evidence_gap_prompt.txt  [UPLOAD TO CLAUDE.AI]

# Stage 5 — convert updated resume PDF after edits
docker exec markitdown markitdown "/output/Updated_Resume.pdf" -o "/output/Updated_Resume.md"

# Stage 6 — cover letter
./scripts/cover_letter.sh "output/JD.md" "output/Updated_Resume.md"
# → prompts/cover_letter_prompt.txt  [upload to Claude.ai]
./scripts/md_to_pdf.sh "output/cover/cover_letter.md"
```

---

### Agent workflow (Ollama)

```bash
./scripts/ats_workflow.sh "output/JD.md" "output/resume"
# → interactive model selection from pulled Ollama models
# → or: --model deepseek-r1:14b to specify directly
# → Stage 0/1 and Stage 3 warn and require --override (manual_only per policy)
# → Stage 2 runs automatically (local_allowed)
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
| Stage 3.5 Evidence Gap | ats_evidence_gap.sh | `manual_only` | — |
| Cover Letter | cover_letter.sh | `untested` | — |

**Why manual_only for Stage 0/1 and Stage 3:** three local models
(llama3:8b, llama3.1:8b, deepseek-r1:14b) were tested. All three failed
Stage 0/1 (hallucinated variant names) and Stage 3 (produced formatting
audits instead of paraphrase edits). Stage 2 worked adequately on all three.

---

## Local Ollama execution

```bash
# Run a stage locally (policy-gated):
./scripts/llm_execute.sh <prompt_file> <stage_key> <model>

# Examples:
./scripts/llm_execute.sh prompts/ats_prompt.txt stage_2_ats_optimize llama3.1:8b
./scripts/llm_execute.sh prompts/variant_rank_prompt.txt stage_0_1_variant_rank llama3.1:8b --override

# Check policy:
python3 policy/policy_check.py stage_2_ats_optimize
python3 policy/policy_check.py stage_0_1_variant_rank --override

# Timeout: default 1800s
LLM_TIMEOUT_SECONDS=3600 ./scripts/llm_execute.sh ...

# Responses: prompts/<sanitized_model_name>/<prompt_name>_response.txt
```

---

## Utility: normalize old prompt naming

If you have JD folders with the old unnumbered naming convention
(`ats_prompt.txt` instead of `2_ats_prompt.txt`), run once:

```bash
./scripts/normalize_prompt_names.sh
# Renames: ats_prompt.txt → 2_ats_prompt.txt
#          ats_recommend_prompt.txt → 3_ats_recommend_prompt.txt
#          ats_evidence_gap_prompt.txt → 4_ats_evidence_gap_prompt.txt
#          semantic_prompt.txt → 1.5_semantic_prompt.txt
#          variant_rank_prompt.txt → 1_variant_rank_prompt.txt
```

---

## Known gotchas

**Clipboard corruption:** `pbcopy` corrupts em-dashes and smart quotes.
Always upload prompt files as file attachments — never paste.

**JD chunks in retrieval pool:** `smart_chunk.sh` chunks every `.md` in
`output/`, including the JD. After chunking, remove JD chunks:
```bash
rm -f chunks/<jd_basename>_part_*.md
```
`batch_prep.sh` does this automatically. Manual workflow requires it explicitly.

**Filenames with spaces:** resume filenames with spaces (e.g.
`Walmart_staff_ R-2506210.md`) can cause glob failures. Rename to remove spaces:
```bash
mv "output/resume/Name_ With_Space.md" "output/resume/Name_Without_Space.md"
```

**FORCE=1 re-runs completed JDs:** without `FORCE=1`, `--continue` skips
any JD that already has `4_ats_evidence_gap_prompt.txt`. Use `FORCE=1` to
regenerate a specific JD after fixing a bug or changing the chosen variant.

**Model warm-up:** deepseek-r1:14b measured at 738–918s/stage on a 16GB
Mac under memory pressure. Free RAM before running: quit Docker when not
in use, `docker compose down`.

---

## Architecture notes

- **Chunking is per JD+variant pair.** `smart_chunk.sh` wipes `chunks/`
  and rechunks whatever is in `output/`. `prepare_variant.sh` isolates
  exactly one resume + one JD in `output/` first. `batch_prep.sh` mirrors
  this sequence exactly.

- **Embedding similarity was replaced** for variant ranking. Two variants
  scored 0.81 similar to each other (shared boilerplate) while either
  scored 0.27–0.37 against the JD. LLM-judgment prompts are used instead.

- **Policy as code:** `execution_policy.json` and `policy_check.py` enforce
  the trust model in code. Editing the JSON propagates everywhere.

- **Additive automation:** every prompt file exists independently of whether
  automation ran. If Ollama fails, the prompt file is still there for
  Claude.ai upload.
