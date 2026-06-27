# Contributing to ATS Pipeline

Thank you for trying this tool. This is an early-stage demo prototype — your feedback directly shapes what gets built.

---

## Quickest way to help: share your experience

**5 minutes:** Fill out the [feedback form](https://forms.gle/YOUR_FORM_LINK) ← update this link

It asks:
- Which steps worked smoothly
- Where you got stuck
- Which JD/resume combinations you tested
- Whether you'd use an automated tier (and what you'd pay)

---

## Reporting bugs

Open a [GitHub Issue](../../issues/new?template=bug_report.md) with:

1. What you were trying to do
2. What command you ran (or which UI button you clicked)
3. The exact error message (paste it, don't screenshot terminal text)
4. Your OS and Docker version (`docker --version`)

**Do NOT include:** your resume content, JD text, or any personal data in issues.

---

## Requesting features

Open a [GitHub Issue](../../issues/new?template=feature_request.md) with label `enhancement`.

Most useful format:
> "I wanted to [do X] but the tool [did Y instead / didn't support it]. My workaround was [Z]."

---

## What we're actively looking for feedback on

- **Setup experience:** Did `./setup_first_time.sh` work on your machine? Where did it break?
- **Stage 2 quality:** How does the ATS gap analysis compare to what you'd write manually?
- **Evidence corpus:** Did the Stage 4 evidence gap prompt surface real experience you'd missed?
- **Web UI:** What's confusing or missing?
- **Cost:** If Stage 2 were automated at ~$0.001/JD (Gemini) or ~$0.03/JD (Claude), would you pay for that?

---

## Contributing code

This is a demo prototype. The codebase is intentionally simple (shell scripts + Python + Flask).

Before submitting a PR:
1. Open an issue first to discuss the change
2. Keep PRs focused — one change per PR
3. Test on macOS (primary target) and Linux if possible
4. Don't add new dependencies without discussion

Core design constraints that must be preserved:
- **Prompt-first:** every stage writes a prompt file, automation is always optional
- **Local-first:** no user data leaves the machine without explicit consent
- **Policy layer:** `policy/execution_policy.json` is the authoritative source for stage trust levels
- **No breaking changes to the manual workflow:** CLI users and web UI users must have identical capabilities

---

## Interest in Pro/Team tier

If you'd use an automated version with managed API access, let us know:
- [Interest form](https://forms.gle/YOUR_FORM_LINK) ← update this link
- Or open an issue with label `tier-feedback`

We're gauging interest before building payment infrastructure. No commitment required.
