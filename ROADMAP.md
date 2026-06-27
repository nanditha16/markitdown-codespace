# ATS Pipeline — Product Roadmap

## What this is

A local-first, privacy-preserving job application prep pipeline.
Your resume data and career documents never leave your machine.
AI evaluation happens via Claude.ai (manual) or API (automated tier).

---

## Tiers

### 🆓 Free — Community Edition (available now)
**Who:** Anyone who can clone a GitHub repo and run Docker.

**What's included:**
- Full pipeline: Stages 0/1 through 4 prompt generation
- Local web UI at `http://localhost:5001`
- Evidence corpus ingestion (career documents → semantic chunks)
- Batch processing for up to 25 JDs per run
- Manual Claude.ai upload/paste workflow (no API key needed)
- All generated prompts saved locally in `prompts/`

**What's NOT included:** Automated API execution (you upload prompts to Claude.ai yourself)

---

### ⚡ Pro — Automated (coming soon, BYOK)
**Who:** Regular job seekers who want to skip the manual upload/paste loop.

**What's included:**
- Everything in Free
- Stage 2 (ATS evaluation) automated via your own API key
  - Supported: Google Vertex AI (Gemini 2.5 Flash), Anthropic Claude
- Cost transparency: per-call token usage shown in terminal
- Dashboard shows which stages are automated vs manual

**How:** Bring your own API key. You pay the LLM provider directly.
We never see or hold your key — it stays in `~/.markitdown-codespace/config.json` on your machine.

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

**Pricing:** Usage-based, per-stage pricing. Contact for details.

---

## Stage automation roadmap

| Stage | Free | Pro | Team |
|---|---|---|---|
| 0/1 Variant ranking | Prompt only → Claude.ai | Prompt only (human gate) | Prompt only (human gate) |
| 2 ATS evaluation | Prompt only → Claude.ai | ✅ Automated (BYOK) | ✅ Automated (managed) |
| 3 Paraphrase edits | Prompt only → Claude.ai | Prompt only | ✅ Automated |
| 4 Evidence gaps | Prompt only → Claude.ai | Prompt only | ✅ Automated |
| 5 PDF conversion | Manual docker exec | Manual docker exec | Guided UI |
| 6 Cover letter | Prompt only → Claude.ai | Prompt only | ✅ Automated |

**Why Stages 0/1 and 3 stay manual in all tiers:**
Stage 0/1 is your go/no-go gate — a human should own that decision.
Stage 3 proposes edits to your resume; you must verify every change traces to real experience before applying it.

---

## Timeline

- **v0.1 (now):** Free tier — full pipeline, web UI, manual workflow. Public demo.
- **v0.2 (next):** Pro tier — BYOK settings page in web UI, Stage 2 automation.
- **v0.3 (future):** Team tier — managed API, multi-candidate, Stage 3/4 automation.

---

## Feedback

Using this tool? We want to hear from you.

- **General feedback:** [GitHub Discussions](../../discussions)
- **Bug reports:** [GitHub Issues](../../issues)
- **Feature requests:** [GitHub Issues](../../issues) with label `enhancement`
- **Interest in Pro/Team tier:** Fill out the [interest form](https://forms.gle/sw6kWLgJJe3f8nHUA)

Your feedback directly shapes what gets built next.
