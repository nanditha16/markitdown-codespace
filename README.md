# MarkItDown Codespace

A document ingestion + ATS resume tooling pipeline, built on Microsoft's
[MarkItDown](https://github.com/microsoft/markitdown), Docker, and
prompt-generation scripts for use with Claude.ai (or any LLM).

Everything here is **prompt-only** — scripts assemble structured prompts
and save them to `prompts/`; nothing calls an LLM API directly. You upload
the generated file to Claude.ai (or paste it) to get the actual analysis.

Orchestrator = agent skeleton 
llm_execute.sh = tool runner 
Stage gating = decision system 

## Folder structure

```
markitdown-codespace/
├── input/                  Drop source files here, sorted by type
│   ├── pdf/                 → pdfplumber, falls back to MarkItDown if weak
│   ├── docx/                → MarkItDown
│   ├── html/                → MarkItDown
│   ├── image/                → tesseract OCR
│   └── other/                → MarkItDown (JD text files etc.)
├── output/                  Converted .md files land here
│   ├── resume/                Your resume variant bank (one .md per
│   │                          target company/role)
│   └── _archive/              Files moved aside by prepare_variant.sh
│                              (never deleted, just out of the way)
├── chunks/                  Heading-split .md chunks of whatever's
│                              currently in output/ (built by
│                              smart_chunk.sh)
├── prompts/                 ALL generated prompt files land here —
│                              nothing is written to the project root.
│                              Upload these to Claude.ai.
└── scripts/                 Everything below

Phase 2: Orchestration ATS Workflow:
markitdown-codespace/
├── scripts/llm_execute.sh    [REVERTED to Ollama-only] dropped the
│                               Claude/OpenAI/Gemini API code added
│                               earlier in this turn — per your decision
│                               to skip cloud API calling for now. Back to
│                               the exact logic tested 4x against your
│                               real Ollama instance, plus the warning
│                               logic for multi-document prompts.
│
├── scripts/ats_workflow.sh   [NEW] Single-entry orchestrator. Chains
│                               Stage 0/1 → 1.5 → 2 → 3, auto-executing
│                               via Ollama at every stage (per your "keep
│                               all stages agentic auto" instruction),
│                               with --model flag / OLLAMA_MODEL env var
│                               for full model swapping. Stage 0/1 and
│                               Stage 3 print a warning + 3-second pause
│                               before auto-running (not a block, per
│                               your instruction) — Stage 2 runs without
│                               the warning since it tested reliably.
│                               Every prompt file still gets written to
│                               prompts/ regardless of auto-execution.
│                               Drops JD's own chunks automatically
│                               (the manual `rm` step from earlier in
│                               this session, now built in).
│
├── run.sh                    [MODIFIED] added ats_workflow.sh as the
│                               documented one-command option
│
└── README.md                 [MODIFIED] new section documenting the
                                 orchestrator usage and the real Ollama
                                 findings (single-resume: adequate;
                                 multi-document: unreliable even within
                                 context window) as a permanent reference,
                                 not just chat history
                                 
```

## Why Docker

Most scripts run inside the `markitdown` container via `docker exec`, not
on your host shell. This matters because host (Mac, BSD tools) and
container (Linux, GNU tools) have real behavioral differences — `sed -i`
syntax, locale defaults, available packages — that caused real bugs
earlier in this project's life. Two scripts (`ask.sh`, `prompt.sh`) are
pure file concatenation with no text-transforming logic and correctly run
host-side, since they also rely on `pbcopy` (Mac-only).

## Setup

```bash
./run.sh
```

This builds/starts the container, routes and converts everything in
`input/`, cleans the output, and chunks it. Safe to re-run any time.

## Core pipeline (single resume)

```bash
./run.sh                                                    # router → clean → chunk
./scripts/semantic_retrieve.sh "your question"               # Q&A over the document
./scripts/ats_optimize.sh "output/JD.md" "output/Resume.md"  # ATS score + gaps
./scripts/cover_letter.sh "output/JD.md" "output/Resume.md"  # cover letter draft
```

## Multi-variant ATS workflow

If you maintain multiple tailored resume versions (`output/resume/*.md`,
one per target company/role), use this instead of running
`ats_optimize.sh` blind against every variant:

```bash
# Stage 0/1 — fit gate + ranking. Tells you plainly if the JD is even
# worth pursuing with your current resume bank before ranking anything.
./scripts/variant_rank.sh "output/JD.md" "output/resume"

# Stage 1.5 — clears output/ down to ONLY the chosen variant + JD.
# Required: smart_chunk.sh chunks every .md file in output/, so without
# this step, chunks/ ends up mixing multiple resumes together.
./scripts/prepare_variant.sh "output/resume/<chosen>.md" "output/JD.md"
./scripts/smart_chunk.sh

# Stage 2 — full ATS score against the chosen variant
./scripts/ats_optimize.sh "output/JD.md" "output/<chosen>.md"

# Stage 3 — file-level, line-level edit recommendations. Variant name is
# required (not optional) — the script refuses to run if it resolves to
# zero or multiple variants, to prevent the same chunk-mixing problem.
./scripts/ats_recommend.sh "output/JD.md" "<variant_name>"

# Stage 4 — single orchestrator ats_workflow.sh
# Runs Stage 0→1.5→2→3 (and optionally cover letter), same scripts as today, unchanged. 
# After each prompt file is written, offers to execute it via local Ollama or skip (manual/cloud path stays primary).
#   - Single entrypoint, auto-runs every stage via Ollama, model swappable via a flag/env var, warns (not blocks) on Stage 0/1/3.
#   - --model qwen2.5:14b correctly overrides the default. 
#   - calls every underlying stage script (variant_rank.sh, prepare_variant.sh, smart_chunk.sh, ats_optimize.sh, ats_recommend.sh, llm_execute.sh)

# llm_execute.sh : 
    - new, reusable (Optional automation layer): 
        - Reads an existing prompts/*.txt file (never replaces the manual-flow scripts), 
        - checks estimated token count against the target model's real context_length (queried live from /api/tags, not hardcoded), 
        - refuses oversized prompts unless --force, calls /api/generate, 
        - saves response to prompts/<name>_response.txt.
        - Used by ats_workflow.sh, callable standalone too.
    -  The size-check math was verified against your real ~213K-character ats_recommend_prompt.txt (correctly blocks) and a trivial prompt (correctly allows). 

# Model Evaluation:
    ollama rm deepseek-r1:14b  <model>
    ```
    - ollama pull llama3:8b
    - ollama pull llama3.1:8b 
    - ollama pull deepseek-r1:14b 
    - ollama pull qwen2.5-coder:32b
    ```

# Stage 5 — UI
# built after the orchestrator works, since it should call the same scripts rather than duplicate logic.
# Practical takeaway for the orchestrator/UI we're about to build: Ollama is now genuinely viable for the fast first-pass role we designed it for (and the context-window fix unblocks Stage 0/1 too), but Stage 2/3 decisions that actually matter for an application should still route to Claude.ai as the source of truth — worth making that distinction visible in the UI, not just in our heads, so you don't accidentally trust an Ollama "Critical Gap" that's actually wrong.

# Practical implication for the orchestrator/UI: Stage 0/1 (variant_rank.sh) should be hard-routed to cloud models only (Claude.ai/OpenAI/Gemini) — not offered as an Ollama option at all, regardless of context window size. Stage 2 (ats_optimize.sh, single resume, ~4K tokens) is the legitimate Ollama use case we've now validated twice. Want me to encode that distinction directly into llm_execute.sh or the upcoming ats_workflow.sh — e.g., a warning (or hard block) when someone points it at variant_rank_prompt.txt or ats_recommend_prompt.txt specifically, separate from the token-count check?

```

**TEST**

```
# 1. Put your new JD into input/other/ as a .txt file, e.g. input/other/JD2.txt
# 2. Run the pipeline to convert + clean it
# ./run.sh

# 3. Rank your variants against this new JD (fit gate + ranking)
# ./scripts/variant_rank.sh "output/JD2.md" "output/resume"
#    → upload prompts/variant_rank_prompt.txt to Claude.ai, read the verdict

# 4. Once you've picked a variant, isolate it (clears output/ to just this one + JD)
# ./scripts/prepare_variant.sh "output/resume/<chosen_variant>.md" "output/JD2.md"

# 5. Re-chunk — now chunks/ only has the chosen variant + the JD
# ./scripts/smart_chunk.sh

# 6. Manual step (per our earlier fix) — drop the JD's own chunks so
#    retrieval doesn't match the JD against itself
# rm -f chunks/JD2_part_*.md

# 7. NOW generate the actual ATS prompt
# ./scripts/ats_optimize.sh "output/JD2.md" "output/<chosen_variant>.md"
#    → this produces prompts/ats_prompt.txt, clean and ready

# or 1- 7 steps using llm_execute.sh: (not recommended to use smaller models)
# ./scripts/llm_execute.sh prompts/variant_rank_prompt.txt llama3.1:8b

# 8. llm_execute.sh check: 
# ./scripts/llm_execute.sh prompts/ats_prompt.txt llama3:8b

```

**Both Stage 0 and Stage 3 distinguish presentation gaps (real fact,
wrong wording — fixable by paraphrase) from structural gaps (the JD needs
a type of experience that doesn't exist anywhere in the resume — not
fixable by wording).** This came from a real failure mode: an earlier
version would happily produce a polished-looking ranking or edit list
even when every resume variant shared the same fundamental domain
mismatch with the JD. The current prompts are built to say "this isn't a
good fit, don't bother" when that's the honest answer.

## Other utilities

```bash
./scripts/md_to_pdf.sh "output/cover_letter.md"   # → PDF, Liberation Serif
                                                    # (Times New Roman substitute
                                                    # — the real font isn't
                                                    # redistributable via apt)
./scripts/ask.sh "question"                        # simple Q&A prompt (all chunks)
./scripts/prompt.sh                                 # summarize-all-chunks prompt
./scripts/watch.sh                                  # auto-convert on file save
                                                    # (LOW PRIORITY / KNOWN LIMITED:
                                                    # uses flat MarkItDown, not the
                                                    # type-routed pipeline; requires
                                                    # inotifywait, Linux-only)
python3 scripts/fix_encoding.py file1.md file2.txt  # reverses the
                                                    # UTF-8→cp1252→UTF-8
                                                    # mojibake pattern.
                                                    # Most mojibake actually
                                                    # seen in this project
                                                    # turned out to be caused
                                                    # by pbcopy/clipboard
                                                    # corruption, not file
                                                    # encoding — see note below.
```

## Known gotcha: clipboard corruption

`pbcopy` was confirmed (via direct file-vs-clipboard comparison) to
corrupt em-dashes and smart quotes on the clipboard round-trip into
Claude.ai's chat box, even when the source file was verified correct
UTF-8 on disk. **Always upload generated prompt files directly as file
attachments — never copy/paste their contents.** Every script's final
echo line says this explicitly.


## Lessons baked into this codebase

A few non-obvious things this project's scripts encode, in case you're
extending them:

- **Embedding similarity (`sentence-transformers`) does not reliably
  rank near-identical resume variants against a JD.** Two genuinely
  different variants measured 0.81-0.82 cosine similarity to *each
  other* regardless of section-filtering, while either was only
  0.27-0.37 similar to the actual JD — the shared boilerplate/invariant
  content (same employers, same metrics) drowns out the small
  JD-tailored differences. `variant_rank.sh` uses an LLM prompt instead
  of embeddings for this reason.
- **`python:3.12-slim` (Debian Trixie) doesn't have a UTF-8 locale by
  default** and dropped `wkhtmltopdf` from its repos. `md_to_pdf.py`
  uses pure-Python `reportlab` specifically to avoid apt-package
  availability risk.
- **Always verify package/file availability inside the actual
  container** (`docker exec markitdown ...`) before assuming something
  works — this sandbox's host environment is not a reliable proxy for
  what's installed in the Docker image.

## 🚀


format compliance improves with better fine-tuning, but factual grounding on long structured documents is a harder problem that mostly scales with model size, not just training quality.

