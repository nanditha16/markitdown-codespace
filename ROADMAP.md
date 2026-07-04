# ATS Pipeline — Product Roadmap

## What this is

A local-first, privacy-preserving job application prep pipeline.
Your resume data and career documents never leave your machine.
AI evaluation happens via Claude.ai (manual upload) or API (automated tier).

---

## Architecture: three-file system (Stage 0/1)

Stage 0/1 variant ranking uses three files uploaded together to Claude.ai.
This was redesigned in v0.1.1 to eliminate regenerating 30–50KB of identical
variant content on every JD evaluation:

| File | Built when | Changes? |
|---|---|---|
| `prompts/variant_bank.txt` | Once (Step 0, after pipeline) | Only when resumes change |
| `prompts/variant_rank_prompt.txt` | Once (Step 0, after pipeline) | Only when evaluation criteria change |
| `output/JDx.md` | Pipeline run (per JD) | Unique per JD |

---

## Tiers

### 🆓 Free — Community Edition (available now)

**Who:** Anyone who can clone a GitHub repo and run Docker.

**What's included:**
- Full pipeline: Stages 0/1 through 4 prompt generation
- Local web UI at `http://localhost:5001`
- Three-file variant ranking system (variant bank + instructions + JD)
- Evidence corpus ingestion (career documents → semantic chunks)
- Batch processing for up to 25 JDs per run
- Fit verdict display (GOOD FIT / PARTIAL FIT / POOR FIT) in the web UI
- Manual Claude.ai upload/paste workflow — no API key needed
- All generated prompts saved locally in `prompts/`

**What's NOT included:** Automated API execution (you upload prompts to Claude.ai yourself)

---

### ⚡ Pro — Automated (coming soon, BYOK)

**Who:** Regular job seekers who want to skip the manual upload/paste loop for Stage 2.

**What's included:**
- Everything in Free
- Stage 2 (ATS evaluation) automated via your own API key
  - Supported: Google Vertex AI (Gemini 2.5 Flash), Anthropic Claude
- Cost transparency: per-call token usage shown in terminal
- Dashboard shows which stages are automated vs manual

**How:** Bring your own API key. You pay the LLM provider directly.
Key stays in `~/.markitdown-codespace/config.json` on your machine — we never see it.

**Pricing:** Free (you pay only your LLM API costs — ~$0.001/JD on Gemini, ~$0.03/JD on Claude)

---

### 🏢 Team — Managed (future)

**Who:** Career coaches, outplacement firms, recruiting teams processing multiple candidates.

**What's included:**
- Everything in Pro
- Managed API access (no BYOK required)
- Per-org billing dashboard
- Multi-candidate batch processing
- Stage 3 and Stage 4 automated
- Priority support

---

## Stage automation roadmap

| Stage | Free | Pro | Team |
|---|---|---|---|
| 0/1 Variant ranking | Three-file upload to Claude.ai | Three-file upload (human gate — required) | Three-file upload (human gate — required) |
| 2 ATS evaluation | Prompt only → Claude.ai | ✅ Automated (BYOK) | ✅ Automated (managed) |
| 3 Paraphrase edits | Prompt only → Claude.ai | ⚠️ Automated (BYOK, override-gated — untested for Gemini, spot-check required) | ✅ Automated (managed) |
| 4 Evidence gaps | Prompt only → Claude.ai | ⚠️ Automated (BYOK, override-gated — untested for Gemini, spot-check required) | ✅ Automated (managed) |
| 5 PDF conversion | Manual docker exec | Manual docker exec | Guided UI |
| 6 Cover letter | Prompt only → Claude.ai | Prompt only | ✅ Automated |

**Why Stage 3/4 in Pro is override-gated, not a plain ✅:** the underlying
model (Gemini 2.5 Flash) has not been evidence-tested against this task
shape. Every local model tried on Stage 3/4 fabricated filenames/citations.
The UI shows this warning before every run and requires acknowledging it;
it does not block the automation, since a human still reviews the output
before acting on it.

**Why Stage 0/1 stays manual in all tiers:**
This is the go/no-go gate — a human should own the GOOD/PARTIAL/POOR FIT decision.
Three local models (llama3:8b, llama3.1:8b, deepseek-r1:14b) were all tested and
all failed (hallucinated variant names, wrong fit verdicts). This is a confirmed
capability ceiling, not a model-selection problem.

**Why Stage 3 is override-gated (not default-automated) in Pro:**
Stage 3 proposes edits to your resume. You must verify every change traces to real
experience before applying it. Local model testing confirmed all three models
produced formatting audits instead of paraphrase edits — wrong task entirely.
Gemini has been run against Stage 3/4 in production use (5 JDs, no fabricated
filenames observed in that sample) but not scored against a labeled
correctness set the way the local models above were — so Pro's automation
still requires acknowledging this risk each run rather than defaulting to it
silently. "Ran without an obvious failure" is not the same bar as "evidence-tested."

---

## Policy trust model

All execution trust rules live in `policy/execution_policy.json`:

| Stage | Policy | Local trust | Evidence basis |
|---|---|---|---|
| Stage 0/1 Variant Rank | `manual_only` | — | 3/3 models hallucinated variant names |
| Stage 1.5 Prepare | `local_always` | N/A | No LLM — deterministic file ops |
| Stage 2 ATS Optimize | `local_allowed` | advisory | 3/3 models: directionally OK, 2/3 fabricated one gap |
| Stage 3 ATS Recommend | `manual_only` | — | 3/3 models: produced formatting audits instead |
| Stage 4 Evidence Gap | `manual_only` | — | Not yet tested locally |
| Cover Letter | `untested` | — | Not yet tested locally |

---

## Timeline

- **v0.1 (released):** Free tier — full pipeline, web UI, manual workflow.
- **v0.1.1 (released):** Split-prompt architecture — three-file Stage 0/1 system; variant bank built once; `output/JDx.md` used directly (no redundant `jd_current.txt`); POSIX shell compatibility fixes; fit verdict display in web UI; `extract_variant` extended for new response format.
- **v0.1.2 (released):** Bug fix pass — see changelog above. Stage 2 API automation (Claude + Vertex/Gemini) shipped; Stage 3/4 API automation added with explicit untested-model warnings (override-gated, not default); per-JD cost display; duplicate response file cleanup; readiness-check archive fallback.
- **v0.2 (next):** Pro tier settings UI polish (BYOK key management currently file-based); evidence-basis testing for Gemini on Stage 3/4 to potentially reclassify from `manual_only` if results warrant it.
- **v0.3 (future):** Team tier — managed API, multi-candidate, Stage 3/4 automation.

---

## v0.1.2 — Bug fixes from field testing 

All items below were reported during real usage and are now fixed. Grouped
by root cause, not by report order.

**Container/execution bugs**
1. **Evidence refresh failed** — `ingest_evidence.sh: line 31: docker: command not found`.
   RCA: `app.py` runs inside the `markitdown` container and sets `INSIDE_DOCKER=1`
   when calling the script, but the script never read that variable — it always
   shelled out to `docker exec markitdown`, which doesn't exist inside the
   container itself. Fixed: added `INSIDE_DOCKER` detection (honors the env var
   plus `/.dockerenv` as fallback) and `drun`/`drun_i` wrappers used across all
   10 call sites. *Risk: assumes `INSIDE_DOCKER=1` is only ever set from within
   the actual container — true for current call sites.*
2. **`router.sh`'s `drun_bash` self-recursion bug** — the "not inside docker"
   branch called itself instead of `docker exec markitdown bash -c`, which
   would have infinite-looped or errored the first time it was exercised from
   the host. Fixed.

**UX gaps**
3. **Resume filenames with spaces break Stage 3/4 prompt generation.** Added
   a warning in the Step 0 UI next to `input/pdf/` — documentation only, no
   automatic sanitization (avoids silently renaming files users expect to find
   under their original name).
4. **No way to re-run the pipeline after adding a JD without returning to
   Step 0.** Added a "Convert JDs → output/JDx.md" button directly on Step 1
   and a "Convert new JDs" button on Step 2 (2a), both calling the same
   `/api/run-pipeline` route Step 0 uses.
5. **JD5's Step 2 card didn't render** even though its ranking succeeded. RCA:
   `poor_fit` and the displayed `fit_verdict` were computed independently —
   a response mentioning "POOR FIT" for one variant among many (not the
   overall verdict) tripped `poor_fit` while `fit_verdict` still showed
   GOOD/PARTIAL, and the card was silently filtered out. Fixed: `poor_fit`
   now derives from `fit_verdict`, so they can't disagree.

**Data duplication**
6. **`variant_rank_prompt_response.txt` was written to two locations**
   (`JD_Analysis/JDx/` and `JDx_PREP/resp/`). `batch_prep.sh` no longer copies
   it into `PREP/resp/`; `JD_Analysis/JDx/` is the single source of truth.
   Old copies from prior runs are dead weight — safe to delete manually.
7. **Step 2 readiness check was live-path-only.** `prepare_variant.sh` moves
   every non-current JD's `output/{jd}.md` into `output/_archive/` to prevent
   `smart_chunk.sh` from mixing variants — so after a batch run, only the
   last-processed JD showed as "ready." Fixed: readiness (and the download
   link) now falls back to `output/_archive/{jd}.md` when the live file is
   archived.

**Stage 2/3/4 API automation (new capability, not just a fix)**
8. **No way to view/download a saved response after running Stage 2 via
   API.** The button was wired to the *prompt* file regardless of state.
   Fixed: added a "View response" button when a response exists.
   — **Stage 3 and 4 API automation added** (previously prompt-file-only in
   Free/Pro per the table below). Both Claude and Vertex/Gemini backends now
   support `--stages 2,3,4`. Vertex extension is **explicitly untested** —
   `execution_policy.json` marks Stage 3/4 `manual_only` because every local
   model tried fabricated filenames/citations on this task shape; Gemini
   hasn't been evidence-tested against it either. UI shows this warning
   before every Stage 3/4 API run and requires it to proceed non-interactively
   without hanging (fixed a separate bug where the confirmation prompt blocked
   forever when invoked from the web UI's non-interactive subprocess).
   — **Per-stage and per-JD cost now displayed** in the UI, parsed from the
   `Cost: ~$X.XXXXX` header each API response already wrote to disk.

**Evidence ingestion noise**
9. **CamScanner watermark polluting every evidence prompt.** A scanned PDF
   in `input/evidence/` had "Scanned by CamScanner" stamped on every page —
   real embedded text, not part of the image, so it survived extraction
   verbatim (37 occurrences in one file). Two-part fix: (a) strip the
   watermark line before measuring the pdfplumber OK/WEAK threshold — a
   watermark-only scan was clearing the 200-char threshold on noise alone
   and skipping the OCR fallback that should have run; (b) strip it again
   post-chunking, since OCR re-introduces it from the visible page image.

**Session cost Example:** 
Claude (claude-sonnet-4-5):
Stage 2: 0.03593+0.03324+0.03376+0.03666+0.03708 = $0.17667
Stage 3: 0.11604+0.09957+0.11257+0.11846+0.10138 = $0.54802
Stage 4: 0.46027+0.45805+0.42910+0.45497+0.43892 = $2.24131
Claude total: $2.96600

Gemini (gemini-2.5-flash):
Stage 2: not run (no Gemini-suffixed Stage 2 file exists)
Stage 3: 0.00049+0.00077+0.00052+0.00053+0.00048 = $0.00279
Stage 4: 0.00901+0.00903+0.00907+0.00906+0.00906 = $0.04523
Gemini total: $0.04802

Grand total (both providers, all stages, 5 JDs each): $3.01402

---

## Feedback

- **General feedback:** [GitHub Discussions](../../discussions)
- **Bug reports:** [GitHub Issues](../../issues)
- **Feature requests:** [GitHub Issues](../../issues) with label `enhancement`
- **Interest in Pro/Team:** [Interest form](https://forms.gle/sw6kWLgJJe3f8nHUA)

Your feedback directly shapes what gets built next.
