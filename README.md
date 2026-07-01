# markitdown-codespace

A local-first, privacy-preserving job application prep pipeline built on
[MarkItDown](https://github.com/microsoft/markitdown), Docker, and a
policy-gated prompt-generation layer for use with Claude.ai (or any LLM).

**Design principle:** every script generates structured prompt files saved
to `prompts/`. Nothing calls an LLM API by default. You upload the prompts
to Claude.ai for evaluation. Local Ollama execution and API automation are
additive options — they never replace the prompt files.

---

## Prerequisites

| Requirement | Why | Install |
|---|---|---|
| **Docker Desktop** | Runs the entire pipeline — all tools live inside | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop) |
| **Git** | Clone the repo | Pre-installed on most Macs; [git-scm.com](https://git-scm.com) on Windows |
| **Terminal** | Run the startup command | Terminal.app (Mac) / Git Bash (Windows) |

**Port note:** macOS reserves port 5000 for AirPlay. This app uses port **5001**.

---

## First-time setup

```bash
git clone https://github.com/YOUR-ORG/markitdown-codespace.git
cd markitdown-codespace
./setup_first_time.sh
```

Checks Git and Docker, builds the container (5–15 min first time), creates
all folders, and opens the web app automatically. See `SETUP.md` for the
full plain-language walkthrough.

**Every day after that:**
```bash
./scripts/serve.sh    # → http://localhost:5001
```

---

## Folder structure

```
markitdown-codespace/
├── input/
│   ├── pdf/                  Resume PDFs → converted to output/resume/*.md
│   ├── evidence/             Career records, project notes, xlsx, PDFs
│   │                         → used by ingest_evidence.sh (one-time / per update)
│   └── other/                JD text files (JD1.txt, JD2.txt …)
├── output/
│   ├── resume/               Variant bank — one .md per target role/company
│   ├── JDx.md                Converted JD files (used directly by variant_rank.sh)
│   ├── cover/                Cover letters and exported PDFs
│   ├── career_wealth_chunk/  Evidence chunks (from ingest_evidence.sh)
│   └── _archive/             Files moved by prepare_variant.sh
├── chunks/                   Heading-split .md chunks (rebuilt per JD+variant pair)
├── prompts/
│   ├── variant_bank.txt      ← ALL resume variants (built once — Step 0)
│   ├── variant_rank_prompt.txt ← Evaluation instructions (built once — Step 0)
│   ├── jd_current.txt        ← Latest JD file reference (root-level copy)
│   ├── JD_Analysis/
│   │   ├── JDx/              variant_rank_prompt_response.txt (paste here)
│   │   └── JDx_NO/           POOR FIT decisions (archived automatically)
│   └── JDx_PREP/
│       ├── prom/             2_ats_prompt.txt, 3_ats_recommend_prompt.txt,
│       │                     4_ats_evidence_gap_prompt.txt, 5_cover_letter_prompt.txt
│       └── resp/             Paste Stage 2-4 Claude.ai responses here
├── policy/
│   ├── execution_policy.json Stage trust classifications (single source of truth)
│   └── policy_check.py       Enforcement layer
├── web/                      Local web UI (Flask, runs inside Docker)
│   ├── app.py
│   ├── templates/index.html
│   └── static/
├── scripts/
├── setup_first_time.sh
├── SETUP.md
├── run.sh
├── Dockerfile
└── docker-compose.yml
```

---

## How variant ranking works — three-file system

Stage 0/1 (variant ranking) uses three separate files uploaded together
to Claude.ai in one conversation. This eliminates regenerating 30-50KB of
identical variant content on every JD evaluation:

| File | Built by | When | Contains |
|---|---|---|---|
| `prompts/variant_bank.txt` | `build_variant_bank.sh` | Once (Step 0) | All resume variants |
| `prompts/variant_rank_prompt.txt` | `build_variant_bank.sh` | Once (Step 0) | Evaluation instructions |
| `output/JDx.md` | Pipeline (`run.sh`) | Once per JD | JD text |

Upload all three to Claude.ai in one conversation. No separate generation
step needed in Step 2 — the files already exist after Step 0 runs.

---

## Quick start

```bash
# 1. Add resume PDFs to input/pdf/, JD text files to input/other/JD1.txt etc.
# 2. Start the web UI
./scripts/serve.sh       # → http://localhost:5001

# Or command line:
./run.sh                 # route → clean → convert PDFs → chunk

# (One-time) Ingest career evidence corpus:
./scripts/ingest_evidence.sh

# Build the variant bank (once, after pipeline runs):
./scripts/build_variant_bank.sh
# → prompts/variant_bank.txt + prompts/variant_rank_prompt.txt

# Check all JDs are ready for Stage 0/1 upload:
./scripts/variant_rank.sh JD5

# Generate Stages 2-4 after pasting variant ranking responses:
./scripts/batch_prep.sh --continue
```

---

## Workflows

### Web UI (recommended)

```bash
./scripts/serve.sh
# → http://localhost:5001
```

Five guided steps:

- **Step 0 — Setup:** system check, run pipeline, build variant bank
  (one-time after adding resumes). Creates `prompts/variant_bank.txt` and
  `prompts/variant_rank_prompt.txt`.
- **Step 1 — Add JDs:** paste or upload JD text files
- **Step 2 — Rank Variants:** download all three files, upload to Claude.ai,
  paste response back
- **Step 3 — ATS Analysis:** generate Stages 2-4, upload each to Claude.ai,
  paste responses
- **Step 4 — Dashboard:** full status across all JDs

---

### Batch workflow (command line)

#### Step 1 — Add JDs and build variant bank

```bash
# Drop JD text files into input/other/:
#   JD1.txt, JD2.txt, ... (paste full JD text)

./run.sh
# → converts input/other/JDx.txt → output/JDx.md

./scripts/build_variant_bank.sh
# → prompts/variant_bank.txt       (all 21 variants)
# → prompts/variant_rank_prompt.txt (instructions)
# Run only once; rebuild when variants change: --rebuild flag
```

#### Step 2 — Human gate (Claude.ai) — Stage 0/1

```bash
# Verify files are ready for a JD:
./scripts/variant_rank.sh JD5
# → prints the three file paths + upload instructions
# → no file generation — files already exist from Step 1
```

Upload all three to Claude.ai in one conversation:
1. `prompts/variant_bank.txt`
2. `prompts/variant_rank_prompt.txt`
3. `output/JD5.md`

Paste Claude's response into:
`prompts/JD_Analysis/JD5/variant_rank_prompt_response.txt`

Claude's response will include **GOOD FIT / PARTIAL FIT / POOR FIT**,
a ranked table, and a **Top Pick** variant filename.

#### Step 3 — Generate Stages 2-4

```bash
./scripts/batch_prep.sh --continue
# → reads each JDx response, extracts chosen variant
# → POOR FIT JDs archived to JDx_NO/ automatically
# → for each qualifying JD:
#     Stage 1.5: prepare_variant.sh + smart_chunk.sh
#     Stage 2:   ats_optimize.sh   → 2_ats_prompt.txt
#     Stage 3:   ats_recommend.sh  → 3_ats_recommend_prompt.txt
#     Stage 4:   ats_evidence_gap.sh → 4_ats_evidence_gap_prompt.txt

# Single JD:
./scripts/batch_prep.sh --continue --jd JD5

# Force regenerate:
FORCE=1 ./scripts/batch_prep.sh --continue --jd JD5

# Status dashboard:
./scripts/batch_prep.sh --status
```

#### Step 4 — Upload Stages 2-4 to Claude.ai

Upload each file separately to Claude.ai:

| File | Stage | Save response as |
|---|---|---|
| `2_ats_prompt.txt` | ATS gap analysis | `resp/ats_prompt_response.txt` |
| `3_ats_recommend_prompt.txt` | Paraphrase edits | `resp/ats_recommend_prompt_response.txt` |
| `4_ats_evidence_gap_prompt.txt` | Evidence gaps | `resp/ats_evidence_gap_response.txt` |

Stages 2-4 can be uploaded in parallel across JDs — each is self-contained.

#### batch_prep.sh — all flags

```bash
./scripts/batch_prep.sh                        # Status dashboard (no action if no responses yet)
./scripts/batch_prep.sh --continue             # Stages 2-4 for all JDs with responses
./scripts/batch_prep.sh --continue --jd JD3   # Single JD
./scripts/batch_prep.sh --status              # Dashboard only
./scripts/batch_prep.sh --cover JD3           # Cover letter prompt for one JD
FORCE=1 ./scripts/batch_prep.sh --continue    # Force regenerate even if prompts exist
```

---

### Single resume, manual

```bash
./scripts/ats_optimize.sh "output/JD.md" "output/Resume.md"
# → prompts/ats_prompt.txt [upload to Claude.ai]

./scripts/cover_letter.sh "output/JD.md" "output/Resume.md"
# → prompts/cover_letter_prompt.txt [upload to Claude.ai]
./scripts/md_to_pdf.sh "output/cover/cover_letter.md"
# → output/cover/cover_letter.pdf
```

---

### Evidence corpus (one-time)

```bash
# Drop files into input/evidence/:
#   Career_Wealth.xlsx, project notes, PDFs

./scripts/ingest_evidence.sh
# → output/career_wealth_chunk/*.md
# Re-run when evidence files change (idempotent)
```

---

### Ollama (local model execution)

```bash
./scripts/llm_execute.sh <prompt_file> <stage_key> <model>

# Example — Stage 2 (policy: local_allowed):
./scripts/llm_execute.sh prompts/ats_prompt.txt stage_2_ats_optimize deepseek-r1:14b

# Stage 0/1 requires --override (policy: manual_only — 3/3 models failed this):
./scripts/llm_execute.sh prompts/variant_rank_prompt.txt stage_0_1_variant_rank llama3.1:8b --override

# Check policy:
python3 policy/policy_check.py stage_2_ats_optimize

# Configurable timeout (default 1800s):
LLM_TIMEOUT_SECONDS=3600 ./scripts/llm_execute.sh ...
```

---

## Policy and execution trust

All rules in `policy/execution_policy.json`. Edit that file to change
system behavior — no script hardcodes rules.

| Stage | Script | Policy | Local trust |
|---|---|---|---|
| Stage 0/1 Variant Rank | variant_rank.sh | `manual_only` | — |
| Stage 1.5 Prepare | prepare_variant.sh | `local_always` | N/A (no LLM) |
| Stage 2 ATS Optimize | ats_optimize.sh | `local_allowed` | advisory |
| Stage 3 ATS Recommend | ats_recommend.sh | `manual_only` | — |
| Stage 3.5 Evidence Gap | ats_evidence_gap.sh | `manual_only` | — |
| Cover Letter | cover_letter.sh | `untested` | — |

**Why manual_only for Stage 0/1 and Stage 3:** three models tested
(llama3:8b, llama3.1:8b, deepseek-r1:14b). All three failed Stage 0/1
(hallucinated variant names) and Stage 3 (formatting audits instead of
paraphrase edits). Stage 2 worked adequately on all three.

---

## Known gotchas

**Clipboard corruption:** always upload prompt files as file attachments —
never paste. Clipboard corrupts em-dashes and smart quotes.

**Rebuild variant bank after adding resumes:** `build_variant_bank.sh`
compares mtimes and warns if any variant in `output/resume/` is newer than
the bank. Force rebuild: `./scripts/build_variant_bank.sh --rebuild`

**JD chunks in retrieval pool:** `batch_prep.sh` removes JD chunks from
`chunks/` automatically. Manual workflow: `rm -f chunks/<jd_basename>_part_*.md`

**FORCE=1 re-runs completed JDs:** without it, `--continue` skips JDs that
already have `4_ats_evidence_gap_prompt.txt`.

**Port 5001 blocked:** `lsof -i :5001` shows what's using it.

**gcloud token expiry:** run `gcloud auth application-default login` on
the Mac host when Stage 2 returns `Reauthentication is needed`.
