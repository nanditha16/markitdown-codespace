# Session Summary — markitdown-codespace ATS Tooling Build

## What this session built

Starting from a basic PDF→Markdown conversion pipeline (MarkItDown +
pdfplumber + Docker), this session added a full prompt-generation toolchain
for resume/JD evaluation: ATS scoring, cover letter drafting, multi-variant
resume ranking, file-level edit recommendations, and PDF export. Every tool
is **prompt-only** — scripts assemble structured prompts and save them to
`prompts/`; nothing calls an LLM API. The person uploads the generated file
to Claude.ai (or any LLM) to get the actual analysis.

## Final architecture

```
input/{pdf,docx,html,image,other}/  → router.sh → output/*.md
                                                  → clean.sh (perl, in-container)
                                                  → smart_chunk.sh → chunks/*.md
                                                  → retrieve.py (embeddings, in-container)
                                                  → {ats_optimize,cover_letter,
                                                     variant_rank,ats_recommend}.sh
                                                  → prompts/*.txt
                                                  → [human uploads to Claude.ai]
```

Two execution contexts, chosen deliberately per script:
- **In-container** (`docker exec`): anything doing text transformation
  (clean.sh, smart_chunk.sh, retrieve.py, router.sh's conversions) — host
  vs. container OS differences (BSD vs GNU tools, locale defaults) caused
  real bugs when this wasn't enforced consistently.
- **Host-side**: pure file concatenation with no transformation logic
  (ask.sh, prompt.sh — also because they use `pbcopy`, Mac-only) and
  JD-loading/path-validation logic in the prompt-builder scripts.

## Full list of bugs found and fixed this session

1. **`sed -i` cross-platform incompatibility** — BSD sed (Mac host) and
   GNU sed (Linux container) have incompatible `-i` flag syntax. Fixed by
   switching `clean.sh` to `perl -pi`, which is identical on both — then
   later moved the whole script to run in-container anyway, removing the
   host/container split that caused this class of bug in the first place.

2. **`wkhtmltopdf` unavailable on Debian Trixie** — added to the
   Dockerfile based on availability in an unrelated sandbox (Ubuntu
   24.04), never verified against the actual base image
   (`python:3.12-slim`, Trixie). Failed on real build. Lesson: **a
   sandbox is not a reliable proxy for the target container** — package
   availability must be verified with `docker exec` against the real
   image, not assumed from wherever code happens to be tested.

3. **`reportlab` missing despite being "obviously" a dependency** —
   assumed `markitdown[all]` pulled it in because it was present in the
   sandbox. It wasn't (`pip show markitdown` lists actual deps —
   reportlab isn't one). Same root cause as #2: sandbox presence ≠
   container presence. This led to an explicit standing rule from the
   user: **never assume package availability — always provide a verification
   command and wait for real output before editing the Dockerfile.**

4. **HuggingFace model cache not persisting** — diagnosed (incorrectly,
   twice) as a Docker volume-mount issue requiring `--force-recreate`.
   The actual explanation: "Loading weights" is the model loading into
   memory (a per-process, unavoidable cost), not a re-download from HF
   Hub. The cache was working the whole time; `docker exec markitdown du
   -sh /root/.cache/huggingface` (88M, populated) proved it. Two rounds
   of unnecessary fixes happened before checking this directly.

5. **Mojibake (`‚Äî` instead of `—`) chased through 5 wrong theories**
   before being correctly diagnosed: it wasn't `clean.sh`'s perl, not
   Python locale handling, not the markitdown CLI, not file encoding at
   all. Direct file uploads of the exact same content rendered perfectly;
   only `pbcopy`-then-paste-into-chat corrupted it. Root cause:
   **`pbcopy`/clipboard round-trip corrupts non-ASCII characters.** Fix:
   removed `pbcopy` from every script; all scripts now instruct
   "upload as file attachment, never paste."

6. **Embedding-based variant ranking didn't discriminate between
   resumes.** Two real resume variants for different companies measured
   0.81–0.82 cosine similarity to *each other* (even after excluding
   boilerplate sections like Skills/Certifications), while either was
   only 0.27–0.37 similar to the actual JD — and a 6-way tie within
   0.0002 appeared among clearly different variants. Root cause: the
   resumes share too much invariant content (same employers, same hard
   metrics) for `all-MiniLM-L6-v2` whole-document embeddings to separate
   the small JD-tailored differences that matter. **Replaced embedding
   scoring entirely with an LLM-judgment prompt** (`variant_rank.sh`) —
   this is the one case in the project where "fix the math" was abandoned
   in favor of "use a fundamentally different tool for this job."

7. **`np.dot()` without `normalize_embeddings=True`** — a real, separate
   bug (magnitude-dominated dot product instead of cosine similarity)
   found and fixed in both `retrieve.py` and the now-deleted
   `variant_rank.py`, even though it turned out not to be the cause of
   bug #6 (proven by re-testing after the fix — scores were unchanged).
   Kept as a correctness fix regardless, since it was still wrong math.

8. **Stage 0/1 (`variant_rank.sh`) needed a relevance gate, not just a
   ranking.** A real run against a government-healthcare JD (Ontario
   Health) showed all 19 resume variants share the identical
   disqualifying gap (no government/Ministry stakeholder experience).
   Ranking them against each other implied false differentiation. Added
   an explicit **GOOD FIT / PARTIAL FIT / POOR FIT** gate that runs
   before any scoring, with instructions to say "not worth pursuing"
   plainly when that's the honest answer rather than always producing a
   polished-looking top pick.

9. **`ats_recommend.sh` mixed chunks from multiple resume variants** —
   `smart_chunk.sh` chunks *every* `.md` file in `output/`, so if more
   than one resume variant was ever present there, `chunks/` accumulated
   all of them with no separation. Fixed two ways: (a) added
   `prepare_variant.sh` (Stage 1.5) to clear `output/` down to one
   variant + the JD before chunking, archiving (not deleting) everything
   else; (b) made `ats_recommend.sh`'s variant-name argument **required**
   and validated — it now refuses to run if the name matches zero or
   multiple variants, rather than silently guessing.

10. **(Found in this final session, NOT YET FIXED)** `retrieve.py` globs
    *all* of `chunks/*.md` as retrieval candidates with no exclusion for
    the JD's own chunk file. Since `prepare_variant.sh` correctly leaves
    the JD `.md` in `output/` (so `ats_optimize.sh` can read it),
    `smart_chunk.sh` then chunks the JD too, and JD boilerplate
    (French-translation notice, benefits intro, accessibility notice)
    ends up in the "resume sections retrieved as most relevant" list —
    because the JD is being matched against itself. **Needs a fix**:
    `retrieve.py` (or the scripts calling it) should exclude any chunk
    file matching the JD's filename from the candidate pool.

## Workflow as it stands today

```bash
./run.sh                                                          # build/route/clean/chunk everything in input/
./scripts/variant_rank.sh "<jd>" "output/resume"                  # Stage 0/1: fit gate + LLM ranking
./scripts/prepare_variant.sh "output/resume/<chosen>.md" "output/<jd>.md"  # Stage 1.5: isolate one variant
./scripts/smart_chunk.sh                                          # re-chunk, now single-variant
./scripts/ats_optimize.sh "<jd>" "output/<chosen>.md"             # Stage 2: full ATS score
./scripts/ats_recommend.sh "<jd>" "<variant_name>"                # Stage 3: file-level edits
./scripts/cover_letter.sh "<jd>" "output/<chosen>.md"             # cover letter draft
./scripts/md_to_pdf.sh "prompts/some_output.md"                   # → PDF (Liberation Serif)
```

All generated prompts land in `prompts/`. Upload (never paste) to Claude.ai.

## Hard-won principles for future extension

These came from real failures in this session, not abstract best
practices — useful as guardrails for whoever (human or agent) extends
this next:

1. **Verify, don't infer, environment state.** A sandbox/test environment
   is not the target environment. Before claiming a package, file, or
   config is "definitely there," provide a verification command and wait
   for real output.

2. **An LLM prompt and a numeric algorithm are different tools — pick
   based on what's actually being measured.** Embedding similarity is
   good at "is this text generally about the same topic." It is bad at
   "does this specific resume satisfy this specific structured
   requirement set," especially when comparing near-duplicate documents.
   Requirement-matching, gap analysis, and fit judgment are LLM-prompt
   problems, not vector-math problems — this session learned that the
   hard way (twice) before accepting it.

3. **A ranking implies meaningful differentiation; don't produce one when
   it doesn't exist.** If every option shares the same disqualifying
   gap, say so before ranking, not after.

4. **A required, validated argument beats a smart default.**
   `ats_recommend.sh`'s variant-name argument was made required (not
   optional-with-a-default) specifically because a default would have
   silently picked the wrong scope when multiple variants were present —
   the same failure mode the script exists to prevent.

5. **Distinguish presentation gaps from structural gaps, always.** A
   resume's wording can be fixed; a resume's underlying experience
   cannot be invented. Every evaluation prompt in this project now makes
   this distinction explicit, because conflating them produces
   confident-sounding advice that sets the candidate up to misrepresent
   themselves in an interview.

6. **The clipboard is not a reliable data channel.** Any future
   chat-bot/agent UI built on this should default to file-based handoffs
   (upload/download) over copy-paste, given the confirmed corruption
   issue — or, if building a true integrated UI (not relying on
   Claude.ai's upload), ensure the data path between script output and
   LLM input never round-trips through an OS clipboard at all.

## Roadmap: evolving this into an agent / UI / chatbot system

The current design is intentionally "prompt factory + human in the loop
to paste/upload into Claude.ai." To evolve toward something more
integrated, in rough order of effort:

### Near-term (still prompt-only, easier UX)
- **Fix bug #10** (JD self-retrieval) — quick, isolated fix.
- **Single entrypoint script** (`./ats_workflow.sh <jd> <variant_dir>`)
  that chains Stage 0→1.5→2→3 automatically, stopping at Stage 0 if
  POOR FIT, prompting for variant choice after ranking.
- **A `manifest.json` per resume variant** (company, role, date tailored,
  last Stage 2 score) so the system has structured metadata instead of
  parsing filenames.

### Medium-term (light agentic layer)
- **Wire the Anthropic API directly into the scripts** (the
  `anthropic_api_in_artifacts` pattern this environment already
  supports) so `ats_optimize.sh` etc. can optionally *call* Claude and
  write the actual evaluation to a file, instead of only producing a
  prompt for manual upload. Keep the prompt-only mode as a fallback/audit
  trail.
- **A lightweight local web UI** (could be a single HTML+JS file using
  the project's existing Docker container as a backend) that lists
  variants, shows Stage 0/1/2/3 results, and lets the person trigger each
  stage with a button instead of remembering CLI arguments.

### Longer-term (full agent/chatbot)
- **An orchestrating agent** that, given a JD URL or pasted text, runs
  the full pipeline autonomously: fetch/save JD → Stage 0 fit gate →
  (if GOOD/PARTIAL) auto-select top variant → Stage 1.5→2→3 → draft
  cover letter → flag for human review before anything is sent anywhere.
  The structural-vs-presentation gap distinction (principle #5 above)
  becomes even more important here — an autonomous agent must not
  "smooth over" a POOR FIT verdict just to produce a complete-looking
  output.
- **Persistent state/history**: which JDs were evaluated, which variant
  was used, what the score was, whether the person applied — enabling
  the agent to learn which variants tend to score well for which JD
  types over time, without re-deriving everything from scratch each run.
- **Human approval gate before any external action** (sending an
  application, posting a cover letter) — this project never sends
  anything anywhere today; any future agent version should preserve that
  boundary explicitly, generating drafts for review rather than acting
  autonomously on the person's behalf.

# Orchestration Layer — Summary

## Tree: what changed and why

```
scripts/llm_execute.sh        [NEW, then revised 3x]
  v1: provider-agnostic (Ollama + Claude/OpenAI/Gemini API stubs)
      → reverted: user wanted Ollama-only for now, untested cloud code
        removed rather than left as dead/unverified paths
  v2: Ollama-only, single hardcoded response path
      → bug found via real test: two different models' responses
        overwrote each other (ats_prompt_response.txt collision)
  v3: routes output to prompts/<sanitized_model_name>/ per model
      → tested: confirmed llama3.1:8b and llama3:8b produce
        non-colliding paths
  v3.1: timeout 900s hardcoded → ${LLM_TIMEOUT_SECONDS:-1800}, configurable
      → bug found via real test: deepseek-r1:14b timed out at 900s;
        generic error gave no indication it was a timeout vs. a crash
      → added: distinct timeout detection (exit code 2), explanatory
        message, 3 concrete next steps (longer timeout / smaller model /
        Claude.ai)

scripts/ats_workflow.sh       [NEW, then revised 1x]
  v1: chains Stage 0→1.5→2→3, auto-executes each via Ollama, hardcoded
      default model "llama3.1:8b"
      → bug found via real test: user deleted llama3.1:8b, pulled
        deepseek-r1:14b, hardcoded default would have silently pointed
        at a model that no longer existed
  v2: no --model given → queries live /api/tags, lists actually-pulled
      models with context length, prompts for explicit selection
      → tested: both explicit-flag and no-flag code paths verified

scripts/variant_rank.sh       [unchanged this phase — already rebuilt
                                 earlier this session from embedding-based
                                 to LLM-prompt-based scoring]
```

## Design considerations

1. **Additive, never a replacement.** Every auto-execution script still
   writes the underlying prompt file to `prompts/` regardless of whether
   automation runs or succeeds. The manual Claude.ai upload path is the
   permanent fallback/primary, not a legacy mode being phased out.

2. **Verify against the real environment, not assumptions.** Every claim
   in this layer (context window per model, response shape, timeout
   behavior) was confirmed against the user's actual running Ollama
   instance via real `curl`/script output — not inferred from
   documentation or a different sandbox. This was an explicit standing
   rule established earlier in the session after two prior incidents
   (`wkhtmltopdf` availability, `reportlab` dependency) where sandbox
   presence was wrongly treated as proof of container presence.

3. **Warn, don't block — but warn specifically, not generically.**
   Stage 0/1 and Stage 3 warnings name the exact failure modes seen in
   real testing (no variant named, hallucinated content, lost output
   format) rather than a generic "this might not work" — the warning
   text itself is evidence-based.

4. **Required arguments over silent defaults, when a wrong default is
   worse than an error.** Model selection moved from a hardcoded default
   to a required, live-queried choice specifically because a silent
   wrong default (pointing at a deleted model) is a worse failure mode
   than asking.

## Model evaluation — 3 models tested, same JD/resume/prompts throughout

| Model | Params | Stage 0/1 (52K tok) | Stage 2 (4K tok) | Stage 3 (6K tok) | Time (0/1 → 2 → 3) |
|---|---|---|---|---|---|
| llama3:8b | 8B | not tested this phase | Fabricated a Critical Gap (missing PM experience) that's the candidate's core qualification | not tested this phase | — |
| llama3.1:8b | 8B | Never named a single variant from 21; confused a resume filename ("eBay") with the target company | Same core misread as llama3:8b (called PM experience "lacking") | Used job titles instead of chunk filenames; audited dates instead of proposing wording edits | ~309s / ~275s / ~262s |
| deepseek-r1:14b | 14.8B | Only addressed 3 of 21 variants; invented two non-existent "eBay Resume 1/2" variants; concluded "GOOD FIT" for an unspecified generic role, not the real JD | **Best result of all three** — accurate, grounded gaps (language/culture fit, mentorship), no fabricated claims | Produced a formatting/style audit instead of paraphrase edits; invented "Deloitte 1/2/3" when only one resume was in scope | ~738s / ~871s / ~918s |

**Conclusion, evidence-based:** single-resume, moderate-length, single-task
prompts (Stage 2) are within reach of local 8–14B models — `deepseek-r1:14b`
in particular gave a usable result. Multi-document, multi-entity,
strict-output-format tasks (Stage 0/1, Stage 3) failed on **all three
models tested**, and a larger/slower/reasoning-tuned model did not
improve quality — it took 2.4–3x longer to produce a differently-wrong
answer. This is treated as a capability ceiling at this model size class
for this task type, not a model-selection problem solvable by trying a
fourth model.

A live system check during the `deepseek-r1:14b` run also showed the
Mac under real memory pressure (147MB free of 16GB, active bidirectional
swapping in the tens of millions of pages, ~4.3GB held idle by two
Docker Desktop VM processes) — the slow times may partly reflect memory
contention, not pure compute cost. Worth knowing, but does not change
the *quality* finding above, which was about correctness, not speed.

## Practical implication for the orchestrator / UI

- **Stage 2 (`ats_optimize.sh`): safe to auto-run locally by default.**
  No warning needed beyond what already exists.
- **Stage 0/1 (`variant_rank.sh`) and Stage 3 (`ats_recommend.sh`): should
  require explicit, deliberate opt-in, not just a soft warning + pause.**
  Three real failures across three models is enough evidence to make this
  a harder gate in the UI (e.g., a confirmation checkbox with the failure
  modes listed, not a single "proceed anyway" button) — discussed as a
  candidate change but not yet implemented; flagging it here as a known
  open item for the UI phase rather than deciding it unilaterally.
- **Any UI showing local-model output should visually distinguish
  "Ollama draft (unverified)" from "Claude.ai result" — never present
  them with equal visual weight**, given the confirmed failure rate on
  the harder stages.
- **Timeouts need a progress indicator, not a silent wait.** A user
  watching a spinner for 15+ minutes with no feedback has no way to
  distinguish "working" from "hung" — the CLI's elapsed-time-only
  feedback was barely adequate even there.

## What's needed for the next phase (chatbot-style UI, no CLI)

Concrete, scoped to what this session's testing actually surfaced as
necessary — not a generic feature wishlist:

1. **A persistent job/run state model.** The CLI orchestrator runs
   synchronously in one terminal session with `read -p` blocking on
   user input. A UI needs the workflow to be resumable/async: JD
   uploaded → Stage 0/1 running in background → user can leave and
   come back → variant selection happens whenever the user is ready,
   not blocking a script.
2. **Streaming or progress feedback for long-running local-model calls.**
   Real generation times observed: 262s–918s. A chatbot UI showing
   nothing for 15 minutes will read as broken. At minimum, surface
   Ollama's `done: false` streaming chunks (the API supports
   `stream: true`, not used yet in this project) or a live elapsed-timer
   with the known model/prompt-size context ("this typically takes
   ~5-15 min for this prompt size on your machine").
3. **A model-quality indicator baked into the UI, not just docs.** Given
   the confirmed 3-model failure pattern on Stage 0/1 and Stage 3, the UI
   should surface this as structured metadata (e.g., a badge: "Local
   models: reliable for this stage" vs. "Local models: unreliable for
   this stage — Claude.ai recommended") rather than relying on the user
   having read this summary.
4. **File-system abstraction.** Everything currently keyed on literal
   paths (`output/resume/*.md`, `chunks/*.md`, `prompts/<model>/*.txt`)
   works for a CLI user who knows the project layout. A chatbot UI needs
   this abstracted into named entities (variants, JDs, runs) the user
   interacts with by name/upload, not by knowing the directory structure.
5. **Decide the UI's relationship to Docker.** Every stage currently
   requires the `markitdown` container running and reachable via
   `docker exec`. A genuinely "no CLI" experience needs the UI to manage
   container lifecycle itself (start/health-check/stop) rather than
   assuming the user has already run `./run.sh` in a terminal.
6. **Decide whether the UI calls scripts as subprocesses or
   reimplements logic natively.** Reimplementing risks drifting from the
   now-tested CLI behavior; shelling out to the existing scripts
   preserves everything verified in this session but means the UI's
   backend needs the same shell/Docker access the CLI does. This is a
   real architectural fork to decide explicitly before writing UI code,
   not something to default into.
