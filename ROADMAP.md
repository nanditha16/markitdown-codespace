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
| 3 Paraphrase edits | Prompt only → Claude.ai | Prompt only | ✅ Automated |
| 4 Evidence gaps | Prompt only → Claude.ai | Prompt only | ✅ Automated |
| 5 PDF conversion | Manual docker exec | Manual docker exec | Guided UI |
| 6 Cover letter | Prompt only → Claude.ai | Prompt only | ✅ Automated |

**Why Stage 0/1 stays manual in all tiers:**
This is the go/no-go gate — a human should own the GOOD/PARTIAL/POOR FIT decision.
Three local models (llama3:8b, llama3.1:8b, deepseek-r1:14b) were all tested and
all failed (hallucinated variant names, wrong fit verdicts). This is a confirmed
capability ceiling, not a model-selection problem.

**Why Stage 3 stays manual in Free and Pro:**
Stage 3 proposes edits to your resume. You must verify every change traces to real
experience before applying it. Local model testing confirmed all three models
produced formatting audits instead of paraphrase edits — wrong task entirely.

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
- **v0.2 (next):** Pro tier — BYOK settings in web UI, Stage 2 automation via Vertex AI and Claude API.
- **v0.3 (future):** Team tier — managed API, multi-candidate, Stage 3/4 automation.

---

## Feedback

- **General feedback:** [GitHub Discussions](../../discussions)
- **Bug reports:** [GitHub Issues](../../issues)
- **Feature requests:** [GitHub Issues](../../issues) with label `enhancement`
- **Interest in Pro/Team:** [Interest form](https://forms.gle/sw6kWLgJJe3f8nHUA)

Your feedback directly shapes what gets built next.
