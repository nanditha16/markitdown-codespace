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

## Prerequisites

| Requirement | Why | Install |
|---|---|---|
| **Docker Desktop** | Runs the entire pipeline — all tools live inside | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop) |
| **Git** | Clone the repo | Pre-installed on most Macs; [git-scm.com](https://git-scm.com) on Windows |
| **Terminal** | Run the startup command | Terminal.app (Mac) / Git Bash (Windows) |

**Git on Mac:** run `git --version`. If missing, `xcode-select --install` installs
the command-line tools only (not full Xcode). Most Macs with Docker Desktop already have Git.

**Port note:** macOS reserves port 5000 for AirPlay. This app uses port **5001**.

---

## First-time setup

Clone the repo and run one script:

```bash
git clone https://github.com/YOUR-ORG/markitdown-codespace.git
cd markitdown-codespace
./setup_first_time.sh
```

`setup_first_time.sh` checks Git and Docker, builds the container (5–15 min first time
while AI models download), creates all folders, and opens the web app automatically.
See `SETUP.md` for the full plain-language walkthrough.

**Every day after that:**
```bash
./scripts/serve.sh    # → http://localhost:5001
```

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
│   │                         (PDFs in input/pdf/ are routed here automatically
│   │                         by run.sh; non-PDF resumes must be moved here manually)
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
│   │   │   ├── 1.5_semantic_prompt.txt   ← diagnostic only, not uploaded to Claude
│   │   │   ├── 2_ats_prompt.txt
│   │   │   ├── 3_ats_recommend_prompt.txt
│   │   │   └── 4_ats_evidence_gap_prompt.txt
│   │   └── resp/             Paste Claude.ai responses here
│   │       ├── variant_rank_prompt_response.txt
│   │       ├── ats_prompt_response.txt
│   │       ├── ats_recommend_prompt_response.txt
│   │       └── ats_evidence_gap_response.txt
│   └── <model_name>/         Ollama response files, separated per model
├── web/                      Local web UI (Flask, runs inside Docker)
│   ├── app.py                Flask backend — calls existing scripts, no new logic
│   ├── templates/index.html  5-step guided interface
│   └── static/               CSS + JS
├── setup_first_time.sh       One-command first-time setup for new users
├── SETUP.md                  Plain-language setup guide
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
# 2. Start the web UI
./scripts/serve.sh       # → http://localhost:5001

# Or use the command line:
# Re-process files after adding new PDFs or JDs:
./run.sh                 # → route → clean → route PDFs to output/resume/ → chunk
                          #   (skips Docker setup if already running)

# (One-time) Ingest career evidence corpus:
./scripts/ingest_evidence.sh

# Run batch prep for all JDs — see Batch Workflow below:
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
#     - Runs variant_rank.sh against all resume variants in output/resume/
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

### Web UI (browser-based — recommended for non-technical users)

Runs entirely inside Docker. No extra installs needed after first-time setup.

```bash
./scripts/serve.sh
# → opens http://localhost:5001 automatically
# → streams live script output in the browser
# → download buttons for every prompt file
# → paste boxes that save responses directly to the correct folder
```

The UI walks through the same workflow as the batch commands above, step by step:
- **Step 0 Setup** — system check (Docker, resume count, evidence chunks) + run pipeline
  - Run this after adding new resume PDFs to `input/pdf/`. Conversion is
    one-time per PDF: files already present in `output/resume/` are skipped
    on subsequent runs, so hand-edited resume `.md` files are never
    overwritten.
  - Evidence ingest is separate — run `./scripts/ingest_evidence.sh` once
    when you add files to `input/evidence/`; it is not part of Step 0.
- **Step 1 Add JDs** — paste or drag-and-drop job description text files
- **Step 2 Rank Variants** — generate prompts → open Claude.ai → paste response back
- **Step 3 ATS Analysis** — generate Stages 2-4 → upload each → paste responses
- **Step 4 Dashboard** — full status across all JDs: chosen variant, stage completion

The UI calls the same shell scripts as the command line. It adds visibility and
removes the need to manage file paths manually — no pipeline logic changes.

---

### Non-developer UI (terminal menu)

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

**Stage 2 silently fails:** `ats_optimize.sh` passes JD text via a temp file to
avoid shell argument length limits with `docker exec`. If Stage 2 produces no
output, check that `output/<chosen>.md` exists (prepare_variant.sh must run first).

**`docker exec` inside Docker:** all pipeline scripts detect `/.dockerenv` and run
directly when inside the container (web UI), falling back to `docker exec` on the
host (terminal). Both paths work correctly — no manual switching needed.

**Port 5001 blocked:** `lsof -i :5001` shows what's using it. Kill that process
or change the port in `docker-compose.yml` and `scripts/serve.sh`.

**gcloud token expiry:** Vertex AI auth expires periodically. Run `gcloud auth application-default login` on the Mac host when Stage 2 returns `Reauthentication is needed`. No container rebuild needed.

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

---

## The full decision tree is:

**Round 1 — Go/No-Go on variant (Stage 0/1)**
    - Claude.ai reads all x variants against the JD
    - Verdict: GOOD FIT / PARTIAL FIT / POOR FIT
    - POOR FIT → stop, archive, don't waste time
    - GOOD/PARTIAL → pick best variant, proceed

**Round 2 — Go/No-Go on applying ATS Optimizer (Stage 2)**
    - Claude.ai scores the chosen variant against the JD honestly
    - Verdict: Interview Probability score + Shortlist YES/NO
    - Low score → conscious decision: is the role worth a stretch application with a strong cover letter, or skip?
    - High score → proceed to Stage 3/4 for the actual edits

**Round 3 — What to fix (Stages 3 + 4)**
    - Stage 3: specific paraphrase edits to the variant (don't change facts, change framing)
    - Stage 4: what real experience from your evidence corpus you can surface that isn't on the resume yet
    
---

## Right problems in the right order:

1. Safety before automation ✅
    - policy enforcement
    - trust labeling

2. Automation without losing control ✅
    - optional execution
    - prompt-first preserved

3. Grounding: this is what prevents "AI-looking correct but wrong" ✅
    - evidence layer (Career_Wealth.xlsx, project notes, employer PDFs → 49 retrievable chunks)

4. Scalability ✅
    - batch workflows (1-25 JDs per run, variant grouping, auto POOR FIT archiving)

5. UI / agent layer ✅
    - Web UI (browser, Flask inside Docker, http://localhost:5001) — Persona A delivered
    - Terminal menu (ui.sh) — developer fallback
    - Agent workflow (ats_workflow.sh + Ollama) — local LLM execution with policy gates

6. Feedback collection + interest validation
    - Recommended sequence
        Clean up repo for public sharing
        Add CONTRIBUTING.md with feedback form link
        Add ROADMAP.md with tier plan
        Remove API keys from scripts (replace with setup guide)
        Tag v0.1-demo and share

    - After 10+ users give feedback (2-4 weeks):
        Add license key validation (one Python file + one Cloudflare Worker endpoint)
        Add BYOK setup flow to Web UI (settings page with key input)
        Stripe for license key purchase
    - After first paying customers:
        Move to Path A (managed SaaS)
        Private repo for production codebase
        Keep public repo as "community edition"

7. API (future)
    - Persona B: user supplies Claude/Gemini API key → UI calls LLM directly
    - Same prompt files, same pipeline — API becomes an optional execution path
    - Integration Cost Analysis:
        - You get an API key from console.anthropic.com, add it once to the project, and a script calls /v1/messages with each prompt file as input and writes the response to the correct resp/ file. 
        - This is ~50 lines of Python. Cost: roughly $0.50–2.00 per JD for all 4 stages at Sonnet pricing.
        - The policy layer already has a slot for this. execution_policy.json has local_allowed for Stage 2. Stages 3 and 4 are manual_only but that's a policy decision you can change for API execution since the API is Claude — same model, same quality, just programmatic.
        - Example:
            prompts/JDx_PREP/prom/2_ats_prompt.txt  →  Claude API  →  prompts/JDx_PREP/resp/ats_prompt_response.txt
            prompts/JDx_PREP/prom/3_ats_recommend_prompt.txt  →  Claude API  →  prompts/JDx_PREP/resp/ats_recommend_prompt_response.txt
            prompts/JDx_PREP/prom/4_ats_evidence_gap_prompt.txt  →  Claude API  →  prompts/JDx_PREP/resp/ats_evidence_gap_response.txt

## FUTURE Extension

- freemium SaaS model with a self-hosted free tier. 
    Free tier:  Clone repo → run locally → manual Claude.ai upload/paste
    Paid tier:  BYOK (Bring Your Own Key): Register → pay → AI automates Stage 2/3/4 via API
        User registers → enters their own Gemini/Claude API key
        → key stored encrypted in their local config
        → usage billed directly to their account
        → you charge for the pipeline software, not the AI calls
        
**Persona B — API-backed automation:**
Technical users who want the UI to call Claude directly instead of the
manual upload/paste loop. They supply an API key; the UI uses it for
Stages 0/1 and 3 (currently manual_only). The prompt files and pipeline
structure remain completely unchanged — the API becomes one more
execution path alongside Claude.ai upload and local Ollama.

        | Category | Manual Claude.ai | Claude API | Gemini API |
        |----------|------------------|------------|-------------|
        | Model | Claude Sonnet 4.5 (latest) | Claude Sonnet 4.5 (same) | Gemini 2.0 Flash (different) |
        | Quality | Best | Identical to manual | Good but different model |
        | Cost | Included in Claude.ai plan | ~$0.30-1.50 per JD (all 4 stages) | Free tier |
        | Speed | Manual upload/wait/paste | ~10-30s automated | ~10-30s automated |
        | Trust | Authoritative | Same quality, advisory label | Advisory |
        | Context window | 200K | 200K | 1M |
        
Track 1 — Vertex AI (org-billed, production path)
    - A billable SaaS pipeline where usage is metered per org.
    - The Phase 3-12 work you already did is correct architecture. What's missing is updating api_execute.py to use the Vertex AI SDK instead of the REST API with a personal key. That's the production path.
    - infrastructure:
        - gcloud authenticated (application_default_credentials.json exists)
        - Project set (fit-reference-500713-c0)
        - $414.86 free credit, $0.00063 for one JD Stage 2 — your $414 credit covers 657,000 calls. 
        - vertex_execute.py uses ADC automatically, no key needed
        - Only pre-req:  SDK on your Mac host Python, this completes, run the dry-run, then the real call
            ```
            python3 -m pip install google-cloud-aiplatform
            ```
    - model: gemini-2.5-flash and gemini-2.5-pro 
    -  it's designed for org-level billing, quotas per project, audit trails, and cost attribution
        - The estimate looks — $0.011 for all 13 JDs, $300 covers 27,000 runs. Now let's actually run it:
    ```
        User (org member) → ATS Pipeline → LLM API → billed to org account
                                                      → usage tracked per JD/stage
                                                      → cost surfaced to user
     ```
                                              
Track 2 — Claude API (personal billing, staging path)
    - Fix your key file, use it now for testing. This lets you validate token counts, response quality, and cost estimates before the Vertex AI integration is complete.        
    - Usig Claude:
        - Cost Estimation, Claude cost for one call for Stage 2 alone:
            1,866 input + 1,465 output tokens
            Sonnet pricing: $3/M input, $15/M output
            Cost: (1,866 × $0.000003) + (1,465 × $0.000015) = $0.0056 + $0.022 = ~$0.028, exactly $0.03
            
            
**Comparison**
- Gemini was $0.00063. Claude was ~$0.028. Claude costs ~44× more per call for Stage 2 per call per JD.

---

**Quality comparison — both responses are good, but differ in focus:**

| Dimension | Claude | Gemini |
|---|---|---|
| ATS Score | 72 | 75 |
| Interview Probability | 65% | 70% |
| Verdict | MAYBE | MAYBE |
| Depth of rewrite suggestions | ✅ More specific | ✅ Comparable |
| Caught "Dec 2025" date issue | ❌ Missed | ✅ Caught it |
| Missing keywords table | ✅ More complete | ✅ Good |
| Tone | Analytical | More prescriptive |
| Action plan | 3 steps, detailed | 5 steps, more checklist |

**Gemini caught something Claude missed** — the "Technical Director - Divinity Science (Dec 2025 – Present)" date discrepancy is flagged as a critical red flag. That's a real issue — Dec 2025 is a future date from when the resume was written. Claude glossed over it entirely.

**Claude's rewrite suggestions are slightly more polished** — the executive summary rewrite and experience bullet rewrites read more naturally and directly mirror JD language. Gemini's rewrites are good but more generic.

**Verdict for your use case:**
- Gemini → batch all JDs for fast go/no-go signal (~$0.01 for all 13 JDs)
- Claude → selective use on shortlisted JDs where you're seriously applying (~$0.03/JD)
- Manual Claude.ai → for Stage 3/4 where citation accuracy matters most

Known Gaps: Gemini hallucinated a credibility issue that doesn't exist.
The date discrepancy Gemini caught is worth fixing regardless of which model you use — that's a recruiter flag that would get the resume screened out automatically. This is exactly why the responses are labeled ADVISORY vs AUTHORITATIVE. 
BUt, Dec 2025 to Jun 2026 is 7 months of real experience. Gemini flagged it as a "future date" which was wrong — it was reading the resume without understanding the current date context. That's an advisory error in the Gemini response, not a real issue with your resume. Claude correctly ignored it.
 Gemini is still very useful for batch screening but spot-checking its Critical Gaps section is essential before acting on anything it flags.


