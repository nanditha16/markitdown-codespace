# MarkItDown Codespace

A document ingestion + ATS resume tooling pipeline, built on Microsoft's
[MarkItDown](https://github.com/microsoft/markitdown), Docker, and
prompt-generation scripts for use with Claude.ai (or any LLM).

Everything here is **prompt-only** — scripts assemble structured prompts
and save them to `prompts/`; nothing calls an LLM API directly. You upload
the generated file to Claude.ai (or paste it) to get the actual analysis.

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
