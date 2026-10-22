#!/usr/bin/env python3
"""
scripts/synthesize_resume.py — Stage 5 of the ATS workflow.

PURPOSE
Stages 2-4 all produce judgments in prose. Nothing in the pipeline turns
those judgments into an actual edited resume — a human was expected to
read three response files and manually retype the accepted changes.
Stage 5 closes that loop: it reads the three existing response files and
writes output/review_resume/{JD}_new_resume.md automatically.

WHY THIS IS DETERMINISTIC, NOT ANOTHER LLM CALL
Stages 2-4 already did every judgment call that requires reasoning: what
the gaps are, whether evidence closes them, how confident that closure
is. Re-asking a model to "now apply your own recommendations" would
re-spend tokens re-deriving a decision that was already made, and Stage 4
is the most expensive stage in the whole pipeline (~$0.44/JD observed,
~78-120K input tokens - see ROADMAP.md session cost example). Stage 5
instead PARSES the structured output Stage 3/4 were already instructed
to produce (### FILE / **Current** / **Paraphrase**, ## Recommendation /
**Confidence**) and applies a fixed decision rule. Cost: $0.00, 0 tokens,
every run.

DECISION RULES (the "final call" logic)
  1. GATE ON STAGE 2 VERDICT.
     Shortlist: NO -> do not synthesize a resume at all. Paraphrasing or
     bolting on new bullets cannot fix a structural mismatch (Stage 2's
     own verdict already says so). Writes a SKIP report only. This is
     also where future runs should save the Stage 3/4 spend that JD1
     burned in this project's history by running those stages anyway.
  2. STAGE 3 PARAPHRASE EDITS -> always auto-applied.
     By construction (ats_recommend_prompt.txt's own constraints) these
     only reword facts already present in the resume - no new claims,
     no new numbers. That is what makes them safe to apply without a
     human in the loop at the synthesis step. Applied via exact-text
     replacement against the full (unchunked) resume, with a normalized
     whitespace/quote fallback for matching across the PDF-derived hard
     line-wraps.
  3. STAGE 4 NEW-MATERIAL RECOMMENDATIONS -> confidence-gated.
     HIGH confidence + a resume section/role Stage 5 can confidently
     locate by name -> inserted as a new bullet under that section.
     HIGH confidence but no confident location match -> appended to a
     clearly labeled "VERIFY BEFORE USE" section at the end, never
     silently guessed into place.
     MEDIUM/LOW confidence or TRUE GAP -> never touches the resume.
     Logged to the report only, exactly as ats_evidence_gap_prompt.txt's
     own instructions say ("candidate must verify before using").
  4. Every decision (applied / skipped / deferred, and why) is written
     to prompts/{JD}_PREP/resp/5_synthesis_report.md so the "why" behind
     the final resume is auditable, not silent.

USAGE
    python3 scripts/synthesize_resume.py JD2
    python3 scripts/synthesize_resume.py JD2 --force   # overwrite existing output

INPUT (all already produced by Stages 2-4 - nothing new to generate):
    prompts/JD_Analysis/{JD}/.chosen_variant
    prompts/{JD}_PREP/resp/ats_prompt_response.txt
    prompts/{JD}_PREP/resp/ats_recommend_prompt_response.txt
    prompts/{JD}_PREP/resp/ats_evidence_gap_response.txt
    output/resume/{chosen_variant}.md

OUTPUT:
    output/review_resume/{JD}_new_resume.md      <- the tailored resume
    prompts/{JD}_PREP/resp/5_synthesis_report.md <- decision log
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
PROMPTS = ROOT / "prompts"
OUTPUT = ROOT / "output"
EVIDENCE_DIR = OUTPUT / "career_wealth_chunk"
# Finalized/merged resumes live in their own subfolder, separate from the
# untouched per-JD base variants in output/resume/ -- keeps "the file you
# review and submit" visually distinct from "the raw variant Stage 0/1
# picked," which used to sit side by side in the same flat output/ dir.
REVIEW_RESUME_DIR = OUTPUT / "review_resume"

KNOWN_SECTIONS = [
    "SUMMARY", "CORE COMPETENCIES", "TECHNICAL STACK", "TOOLS & METHODS",
    "CAREER HIGHLIGHTS", "PROFESSIONAL EXPERIENCE", "AI PLATFORM PROJECT",
    "AI ENABLED PROJECT", "EDUCATION", "CERTIFICATIONS",
]


# ── text normalization (for matching only — never for output) ─────────────
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return text


def build_norm_map(text: str):
    """Collapse-whitespace normalized copy of text + index map back to original."""
    norm_chars = []
    idx_map = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            norm_chars.append(" ")
            idx_map.append(i)
            while i < n and text[i].isspace():
                i += 1
        else:
            norm_chars.append(c)
            idx_map.append(i)
            i += 1
    return "".join(norm_chars), idx_map


def find_span(resume_text: str, norm_resume: str, idx_map, needle: str):
    """Find `needle` in resume_text, tolerant of line-wrap/whitespace/quote diffs."""
    pos = resume_text.find(needle)
    if pos != -1:
        return pos, pos + len(needle)
    norm_needle, _ = build_norm_map(normalize(needle))
    norm_resume_n = normalize(norm_resume)
    pos = norm_resume_n.find(norm_needle)
    if pos == -1:
        return None
    start = idx_map[pos]
    end = idx_map[pos + len(norm_needle) - 1] + 1
    return start, end


# ── Stage 2 parsing ─────────────────────────────────────────────────────────
def parse_stage2(text: str):
    # Score and verdict come from scripts/ats_parse.py, the single shared
    # parser (Stage 10 plan, D7) -- the local regexes here had drifted from
    # app.py's copies before, which is how a whole-phrase-bolded score
    # ("**ATS Score: 88/100**") ended up shown as null on the Review Board.
    import ats_parse
    verdict = ats_parse.extract_shortlist(text)
    reason_m = re.search(r"\*\*Reason:\*\*\s*(.+?)(?=\n\n|\n---|\Z)", text, re.DOTALL)
    return {
        "score": ats_parse.extract_ats_score(text),
        "verdict": verdict or "UNKNOWN",
        "reason": reason_m.group(1).strip() if reason_m else "(no reason parsed)",
    }


# ── Stage 2's own "Recommended Improvements" + "Missing Keywords" ──────────
# Stage 2 produces a second, independent set of suggestions in prose, plus a
# keyword table. Neither was ever fed into Stage 5 before -- confirmed by
# checking a real run's 5_changes.json, which contained zero entries tracing
# to Stage 2. This section fixes that, but asymmetrically:
#
#   Stage 2's "Skills Section Addition" quotes are complete, standalone
#   lines -- safe to treat as real insertion candidates, same as Stage 4's.
#
#   Stage 2's "Current"/"Improved" pairs (Executive Summary, Experience
#   Improvements) quote the ORIGINAL sentence with a trailing "..." --
#   e.g. "Senior Technical Delivery Lead ... enterprise-scale..." -- a
#   deliberately truncated fragment, not the full sentence Stage 3 quotes
#   verbatim. Doing a find-and-replace on a truncated fragment would splice
#   the new paragraph into the MIDDLE of the old sentence and orphan its
#   tail. These are surfaced as read-only comparison context attached to
#   whichever Stage 3 edit touches the same sentence -- never as their own
#   appliable candidate -- specifically because they can't be verified safe
#   to auto-apply the way Stage 3's exact quotes can.
KEYWORD_ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*(CRITICAL|HIGH|MEDIUM)\s*\|\s*(✅|❌|Partial[^|]*)\s*\|", re.MULTILINE
)
KEYWORD_WEIGHTS = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1}


def parse_stage2_keywords(text: str):
    """Weighted {keyword: weight} for every JD keyword Stage 2 marked NOT
    already present (❌ or Partial) -- these are the terms worth rewarding
    a candidate edit for introducing. Already-✅ keywords score nothing;
    the resume already has them, so using them again isn't a gain."""
    weights = {}
    for kw, priority, present in KEYWORD_ROW_RE.findall(text):
        if present.strip() == "✅":
            continue
        weights[kw.strip().lower()] = KEYWORD_WEIGHTS.get(priority, 1)
    return weights


def score_against_keywords(text: str, keyword_weights: dict) -> int:
    if not text or not keyword_weights:
        return 0
    text_lower = text.lower()
    return sum(weight for kw, weight in keyword_weights.items() if kw in text_lower)


def parse_stage2_suggestions(text: str):
    """Returns (reference_pairs, addition_candidates).
    reference_pairs: [{before, after, reason}] -- truncated-quote Current/
      Improved pairs, attached as read-only context, never auto-applied.
    addition_candidates: recs-shaped dicts (same fields parse_stage4
      produces) built from "Add Section" quoted lines, source="stage2" --
      these ARE real, independently-appliable insertion candidates, since
      each quoted line is complete and standalone."""
    section = extract_section(text, "## RECOMMENDED IMPROVEMENTS", ["\n## PRIORITIZED ACTION PLAN", "\n## SCREENING QUESTIONS"])
    reference_pairs, addition_candidates = [], []
    current_heading = "Stage 2 suggestion"

    for chunk in re.split(r"\n---\n", section):
        heading_m = re.search(r"^#{3,4}\s*(.+)$", chunk, re.MULTILINE)
        if heading_m:
            current_heading = heading_m.group(1).strip()

        reason_m = re.search(r"\*\*Reason:\*\*\s*(.+?)(?=\Z)", chunk, re.DOTALL)
        reason = reason_m.group(1).strip() if reason_m else ""

        current_m = re.search(r"\*\*Current:\*\*\s*\n\*?\"(?P<current>.*?)\"\*?\s*\n", chunk, re.DOTALL)
        improved_m = re.search(r"\*\*Improved:\*\*\s*\n\*?\"(?P<improved>.*?)\"\*?\s*\n", chunk, re.DOTALL)
        if current_m and improved_m:
            reference_pairs.append({
                "before": current_m.group("current").strip(),
                "after": improved_m.group("improved").strip(),
                "reason": reason or current_heading,
            })
            continue

        add_m = re.search(r"\*\*Add Section:\*\*\s*\n(?P<lines>.+?)(?=\*\*Reason:\*\*|\Z)", chunk, re.DOTALL)
        if add_m:
            quote_lines = re.findall(r'\*?"(.*?)"\*?', add_m.group("lines"), re.DOTALL)
            for line in quote_lines:
                addition_candidates.append({
                    "title": current_heading,
                    "gap": current_heading,
                    "evidence": "Stage 2 (ats_prompt_response.txt) — not source-cited like Stage 4",
                    "where": "Technical Stack",
                    "confidence": "N/A (Stage 2 suggestion — not evidence-cited)",
                    "conf_note": "",
                    "addition_text": line.strip(),
                    "source": "stage2",
                })
    return reference_pairs, addition_candidates


# ── Stage 3 parsing ─────────────────────────────────────────────────────────
# NOTE: the model does not always emit the exact heading depth/nesting the
# prompt template asks for — observed variants: "### FILE:" directly above
# Current/Paraphrase/Why (JD2), and "## FILE:" followed by a "### Edit N"
# sub-heading before Current/Paraphrase/Why (JD3). Rather than parse a single
# rigid nesting shape, file headings and Current/Paraphrase/Why triples are
# matched independently, then each triple is attributed to the nearest file
# heading that precedes it in the document. This is the same tolerance
# principle the project already applies in batch_prep.sh's extract_variant()
# (multiple candidate patterns, first-match-wins) — model output format
# drifts run to run even with an unchanged prompt template.
FILE_HEADING_RE = re.compile(r"^#{2,3}\s*FILE:\s*(?P<file>.+?)\s*$", re.MULTILINE)
EDIT_TRIPLE_RE = re.compile(
    r"\*\*Current:\*\*\s*\n?\s*\"?(?P<current>.*?)\"?\s*\n+"
    r"\*\*Paraphrase:\*\*\s*\n?\s*\"?(?P<paraphrase>.*?)\"?\s*\n+"
    r"\*\*Why:\*\*\s*\n?\s*(?P<why>.*?)(?=\n---|\n#{2,3}|\Z)",
    re.DOTALL,
)
# NOTE: \n+ (one or more newlines) between fields, not \s*\n\s*\n (a
# mandatory blank line). A real run put Current/Paraphrase/Why on three
# consecutive lines with NO blank line between them -- the previous
# blank-line-mandatory pattern matched zero edits against a response that
# had 12+ well-formed, correctly-quoted edits sitting right there. \n+
# matches a single newline OR a blank line, so both this run's tighter
# formatting and every earlier run's blank-line-separated formatting work
# through the same pattern.
# NOTE: quotes around Current/Paraphrase text are now OPTIONAL (\"?, not \").
# A real run dropped the "..." quoting convention entirely -- "**Current:**"
# followed by a markdown line-break then several lines of raw unquoted text
# -- and the old quote-mandatory regex matched zero edits for that entire
# response. Since \"? only strips a quote if one is actually there, this
# still works identically against the original quoted format.

STRUCTURAL_GAP_RE = re.compile(
    r"###\s*STRUCTURAL GAPS.*?\n(?P<body>.+?)(?=\n---\n###\s*Summary|\Z)", re.DOTALL
)


def parse_stage3(text: str):
    file_headings = [(m.start(), m.group("file")) for m in FILE_HEADING_RE.finditer(text)]
    edits = []
    for m in EDIT_TRIPLE_RE.finditer(text):
        pos = m.start()
        current_file = "(unknown file)"
        for hpos, hname in file_headings:
            if hpos <= pos:
                current_file = hname
            else:
                break
        d = m.groupdict()
        d["file"] = current_file
        d["current"] = d["current"].strip().strip('"').strip()
        d["paraphrase"] = d["paraphrase"].strip().strip('"').strip()
        edits.append(d)
    struct_m = STRUCTURAL_GAP_RE.search(text)
    structural_gaps = struct_m.group("body").strip() if struct_m else ""
    return edits, structural_gaps


# ── Stage 4 parsing ──────────────────────────────────────────────────────────
def extract_section(text: str, start_heading: str, end_headings):
    """Case-insensitive on purpose: a real run produced '# PHASE B — NEW
    MATERIAL RECOMMENDATIONS' (all-caps) against a prompt template that
    only specified '## Phase B'. text.find() is case-sensitive and silently
    returned "no section found" for that entire run -- not an exception,
    not a warning, just zero Stage 4 candidates parsed. Case-insensitive
    matching is the fix; matching on the word 'phase b' regardless of
    heading level/caps/dash-style is more robust than matching the exact
    string the template asked for and hoping the model complies exactly."""
    m = re.search(re.escape(start_heading), text, re.IGNORECASE)
    if not m:
        return ""
    start = m.end()
    end = len(text)
    for h in end_headings:
        m2 = re.search(re.escape(h), text[start:], re.IGNORECASE)
        if m2:
            end = min(end, start + m2.start())
    return text[start:end]


# NOTE: same format-drift issue as Stage 3. Two observed shapes for a Phase B
# block's heading/title:
#   "## Recommendation N: <title>" + separate "**Gap Addressed:** <gap>" line   (JD2)
#   "### Gap Addressed: <title>"  (title IS the gap, no separate bold field)    (JD3)
# Rather than anchor on the heading shape, each "---"-delimited chunk inside
# Phase B is scanned independently for the bold fields that actually matter
# for the decision rule (Confidence is load-bearing; a chunk with no
# Confidence field is not a recommendation block and is skipped).
def extract_addition_fallback(chunk: str) -> str:
    """Fallback when no '> quoted' lines are found under 'Proposed Addition
    to Resume:'. A real run used a '- dash bullet' under a bolded sub-label
    ('**Career Highlights** (new bullet):') instead of the blockquote
    convention the prompt asked for -- the '>' -only extraction found
    nothing, producing an empty, useless "(no addition text parsed)" card
    even though the actual proposed text was sitting right there. This
    grabs the raw span after the label up to the next bold field, then
    drops any line that is PURELY a structural sub-heading (bold text
    plus, at most, a parenthetical and a colon -- nothing else), keeping
    everything else including bullet markers, which are stripped."""
    m = re.search(
        r"\*\*Proposed Addition(?: to Resume)?:\*\*\s*\n(?P<body>.*?)(?=\n\*\*[A-Z][^*\n]*:\*\*|\Z)",
        chunk, re.DOTALL,
    )
    if not m:
        return ""
    lines = []
    for ln in m.group("body").splitlines():
        s = ln.strip()
        if not s:
            continue
        if re.fullmatch(r"\*\*[^*]+\*\*\s*(\([^)]*\))?\s*:?", s):
            continue  # pure sub-heading label, e.g. "**Career Highlights** (new bullet):"
        s = s.lstrip("-").lstrip(">").strip().strip('"')
        if s:
            lines.append(s)
    return " ".join(lines).strip()


def parse_stage4(text: str):
    phase_b = extract_section(
        text,
        "# Phase B",
        ["\n# True Gaps", "\n# Evidence Files Not Used", "\n# Summary of Findings"],
    )
    recs = []
    for chunk in re.split(r"\n---\n", phase_b):
        chunk = chunk.strip()
        if not chunk:
            continue
        conf_m = re.search(r"\*\*Confidence:\*\*\s*(HIGH|MEDIUM|LOW)\s*(.*)", chunk, re.DOTALL)
        if not conf_m:
            continue  # not a recommendation block (e.g. leading prose before first ---)

        rec_m = re.search(r"##\s*Recommendation\s*\d+:\s*(.+)", chunk)
        gap_heading_m = re.search(r"#{2,3}\s*Gap Addressed:\s*(.+)", chunk)
        gap_field_m = re.search(r"\*\*Gap Addressed:\*\*\s*(.+)", chunk)

        title = rec_m.group(1).strip() if rec_m else None
        gap = gap_field_m.group(1).strip() if gap_field_m else None
        if gap_heading_m:
            title = title or gap_heading_m.group(1).strip()
            gap = gap or gap_heading_m.group(1).strip()
        title = title or "(untitled recommendation)"
        gap = gap or title

        evidence_m = re.search(r"\*\*Evidence Source:\*\*\s*(.+)", chunk)
        where_m = re.search(r"\*\*Where on Resume:\*\*\s*(.+)", chunk)
        quote_lines = [
            ln.strip().lstrip(">").strip().strip('"')
            for ln in chunk.splitlines() if ln.strip().startswith(">")
        ]
        addition_text = " ".join(quote_lines).strip()
        if not addition_text:
            # A real run used "**New Bullet:**" followed by the proposed
            # sentence in plain double quotes on the next line, rather
            # than the blockquote convention the prompt asked for. Without
            # this, the generic fallback below stops at this exact field
            # boundary and never reaches it -- worse, it was wrongly
            # harvesting the "**Location:** CAREER HIGHLIGHTS or ..." line
            # that sits just before it, since that line has real content
            # after the label and so isn't a "pure sub-heading" the
            # fallback's filter would exclude. That produced a real,
            # visible bug: cards showing "(untitled recommendation)" with
            # a location suggestion where the actual proposed text should
            # be -- confirmed against a real response file, not assumed.
            new_bullet_m = re.search(r'\*\*New Bullet:\*\*\s*\n"(?P<body>.*?)"\s*\n', chunk, re.DOTALL)
            if new_bullet_m:
                addition_text = new_bullet_m.group("body").strip()
        if not addition_text:
            addition_text = extract_addition_fallback(chunk)

        recs.append({
            "title": title,
            "gap": gap,
            "evidence": evidence_m.group(1).strip() if evidence_m else "(not parsed)",
            "where": where_m.group(1).strip() if where_m else "",
            "confidence": conf_m.group(1),
            "conf_note": conf_m.group(2).strip(),
            "addition_text": addition_text,
            "source": "stage4",
        })
    return recs


# ── Apply Stage 3 edits ──────────────────────────────────────────────────────
def apply_edits(resume_text: str, edits):
    applied, skipped = [], []
    for e in edits:
        norm_resume, idx_map = build_norm_map(resume_text)
        span = find_span(resume_text, norm_resume, idx_map, e["current"])
        if span is None:
            skipped.append({**e, "reason": "current text not found in base resume"})
            continue
        start, end = span
        resume_text = resume_text[:start] + e["paraphrase"] + resume_text[end:]
        applied.append(e)
    return resume_text, applied, skipped


# ── Insert Stage 4 HIGH-confidence new content ──────────────────────────────
def is_role_header(line: str) -> bool:
    """A resume experience-block header line, e.g. 'Technical Lead - TD Bank
    (via Wipro) Mississauga, ON | Aug 2021 - Apr 2025'. Detected by shape
    (has a '|' date field with a 19xx/20xx year or 'Present') rather than by
    a rigid title/company regex, because company names legitimately contain
    punctuation (parentheses, commas) that breaks a naively strict pattern --
    an earlier version missed the Citi line for exactly this reason, which
    let a new bullet spill past its block into the next one."""
    return "|" in line and bool(re.search(r"\b(19|20)\d{2}\b|Present", line))


def extract_role_anchors(resume_text: str):
    """Dynamically pull (line_idx, anchor_name) pairs from the resume itself
    -- company names from experience role lines, plus exact section headers --
    rather than guessing from JD-side vocabulary. Matching against names the
    resume itself contains is far less prone to incidental-word false
    positives than free-text keyword scanning (see locate_anchor docstring)."""
    lines = resume_text.split("\n")
    anchors = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in KNOWN_SECTIONS:
            anchors.append((i, stripped))
            continue
        if is_role_header(stripped):
            before_pipe = stripped.split("|")[0]
            # Company name is conventionally the segment after the LAST
            # " - " before the date field (title may itself contain " / ").
            rest = before_pipe.split(" - ")[-1].strip()
            anchors.append((i, rest))
    return anchors, lines


def strip_markup(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).strip()


def is_near_duplicate(resume_text: str, addition_text: str) -> bool:
    """Stage 4 sometimes proposes REPOSITIONING existing text (e.g. 'move
    this sentence to the top of the Summary') rather than genuinely NEW
    content, even under 'Proposed Addition to Resume'. Inserting those as a
    fresh bullet duplicates content already on the resume. Detected here by
    checking whether a long normalized substring of the proposed text is
    already present verbatim in the resume -- if so this is a reposition/
    emphasis suggestion, not new material, and should go to human review
    instead of being auto-inserted as a duplicate bullet."""
    norm_add, _ = build_norm_map(normalize(strip_markup(addition_text)))
    norm_resume, _ = build_norm_map(normalize(resume_text))
    window = 45
    if len(norm_add) < window:
        return norm_add.lower() in norm_resume.lower()
    for start in range(0, len(norm_add) - window, window):
        if norm_add[start:start + window].lower() in norm_resume.lower():
            return True
    return False


def locate_anchor(resume_text: str, anchors, lines, where: str):
    """Match `where` against anchor names the resume itself provides (company
    names from real role lines, or exact section headers) -- NOT against
    free-text keywords pulled from the recommendation's own wording. An
    earlier version matched incidental words (e.g. 'platform') against the
    wrong role line ('...AI-enabled digital health platform') because it
    scanned addition_text for any capitalized word. Anchoring only on names
    that exist verbatim in both `where` and the resume itself removes that
    false-positive class; ambiguous cases correctly fall through to None
    (-> human review) rather than guessing."""
    where_lower = where.lower()
    best = None  # (match_len, line_idx)
    for i, name in anchors:
        if name in KNOWN_SECTIONS:
            if name.lower() in where_lower:
                candidate = (len(name), i)
            else:
                continue
        else:
            # Company/role anchors: try the longest leading word-prefix of
            # the anchor (before any parenthetical) that appears in `where`,
            # e.g. anchor "TD Bank (via Wipro) Mississauga, ON" tries
            # "TD Bank (via Wipro) Mississauga, ON", "TD Bank (via Wipro)
            # Mississauga,", ... down to "TD Bank", down to "TD". Only
            # candidates of 4+ chars count, so a single short token like
            # "TD" can't anchor on its own, but "TD Bank" or "Citi" can --
            # these are proper nouns pulled from the resume's own role
            # lines, not generic vocabulary, so the false-positive risk
            # seen with free-text keyword scanning doesn't apply here.
            core = name.split("(")[0].strip()
            words = core.split()
            match_len = 0
            for n_words in range(len(words), 0, -1):
                prefix = " ".join(words[:n_words])
                if len(prefix) >= 4 and prefix.lower() in where_lower:
                    match_len = len(prefix)
                    break
            if match_len == 0:
                continue
            candidate = (match_len, i)
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        return None
    anchor_line_idx = best[1]
    j = anchor_line_idx + 1
    while j < len(lines):
        s = lines[j].strip()
        if s in KNOWN_SECTIONS or is_role_header(s):
            break
        j += 1
    return sum(len(l) + 1 for l in lines[:j])


def insert_high_confidence(resume_text: str, recs, force: bool = False):
    """force=True bypasses the confidence gate (used by the Stage 6 web
    review flow, where a human already looked at the specific text and
    approved it) but keeps the near-duplicate and anchor-location checks --
    those aren't policy gates, they're correctness checks that apply
    regardless of who approved the change."""
    inserted, deferred = [], []
    for r in recs:
        if not force and r["confidence"] != "HIGH":
            deferred.append({**r, "reason": f"confidence={r['confidence']} — needs human review, not auto-applied"})
            continue
        if not r["addition_text"]:
            deferred.append({**r, "reason": "no quoted addition text parsed"})
            continue
        if is_near_duplicate(resume_text, r["addition_text"]):
            deferred.append({**r, "reason": "proposed text substantially duplicates existing resume content — "
                                             "likely a reposition/emphasis suggestion, not new material"})
            continue
        anchors, lines = extract_role_anchors(resume_text)
        anchor = locate_anchor(resume_text, anchors, lines, r["where"])
        clean_text = strip_markup(r["addition_text"])
        bullet = f"• {clean_text}\n"
        if anchor is None:
            deferred.append({**r, "reason": "no confident section/role match in 'Where on Resume' — "
                                             "see VERIFY BEFORE USE section"})
            continue
        resume_text = resume_text[:anchor] + bullet + resume_text[anchor:]
        inserted.append(r)
    return resume_text, inserted, deferred


def append_review_section(resume_text: str, deferred_for_review):
    """Deferred HIGH-confidence items with no anchor still deserve visibility —
    append them under a clearly labeled section rather than dropping them."""
    no_anchor = [
        d for d in deferred_for_review
        if "no confident section/role match" in d.get("reason", "")
    ]
    if not no_anchor:
        return resume_text
    block = ["\n\nEVIDENCE-SOURCED ADDITIONS — VERIFY BEFORE USE\n"
             "(HIGH-confidence Stage 4 findings Stage 5 could not confidently place — "
             "move each into the right section above after verifying, then delete this block.)"]
    for d in no_anchor:
        block.append(f"• [{d['gap']}] {d['addition_text']} (source: {d['evidence']})")
    return resume_text + "\n".join(block) + "\n"


# ── Manifest layer — shared between CLI (Stage 5 default policy) and the ──
# Stage 6 web review UI (explicit per-change approve/reject). Building this
# as data (id + type + before/after) rather than baking the accept/reject
# decision into apply_edits/insert_high_confidence directly means both
# call sites reuse the exact same parsing and placement logic — the web UI
# can't drift from what the CLI does, because it IS the same code with a
# different `accepted_ids` filter applied before calling it.
def word_count(text: str) -> int:
    return len(text.split()) if text else 0


def find_alt_suggestion(before_text: str, reference_pairs):
    """Does any Stage 2 reference pair overlap this Stage 3 edit's source
    sentence? Stage 2's quotes are truncated (trailing '...'), so this
    checks whether Stage 2's (stripped) fragment is a normalized substring
    of Stage 3's full quote -- the direction that actually occurs in
    practice, since Stage 2 quotes less text than Stage 3, not more."""
    norm_before = normalize(before_text).lower()
    for ref in reference_pairs:
        frag = ref["before"].rstrip(".").rstrip(".").strip()
        frag = re.sub(r"\.{2,}\s*$", "", frag).strip()  # drop trailing "..."
        norm_frag = normalize(frag).lower()
        if len(norm_frag) >= 15 and norm_frag in norm_before:
            return ref
    return None


# ── Verification: metric grounding, identity-drift, topical overlap ────────
# All three checks below are pure text matching against files already on
# disk (Stage 4's own cited evidence files, the resume itself) -- zero LLM
# calls, zero added cost. They exist because an independent manual review
# of a real Stage 3/4 batch found two fabricated metrics (a "40%" that
# never appears in the evidence corpus, a "500K+" that appears nowhere at
# all) and a systemic pattern (many small, individually-defensible edits
# that together rewrite the candidate's job title) -- neither of which the
# per-card review UI or the existing near-duplicate check could surface on
# their own. Confirmed against the real evidence corpus and the real
# fabricated numbers before being wired in here, not assumed to work.

METRIC_RE = re.compile(
    r"\$\s?\d[\d,]*\.?\d*\s*[KMB]?\+?"   # dollar amounts: $4.5M, $150,000, $1B+
    r"|\d[\d,]*\.?\d*\s*%"                # percentages: 60%, 99.99%
    r"|\d[\d,]*\.?\d*\s*[KMB]\+?\b"       # bare K/M/B counts: 500K+, 2M
    r"|\d[\d,]*\.?\d*\+"                  # plain plus-counts: 15+, 8+
)


def extract_metrics(text: str) -> list:
    """Numbers shaped like the kind of padded metric Stage 4 tends to
    fabricate: percentages, dollar figures, K/M/B or +-suffixed counts.
    Deliberately excludes plain unsuffixed numbers (years, team sizes) --
    lower fabrication risk, and including them would flood every insertion
    with false positives on numbers nobody's actually worried about."""
    return [m.strip() for m in METRIC_RE.findall(text)]


def extract_metrics_with_context(text: str):
    """Each metric paired with a few significant words from its own
    sentence/clause. Needed because a bare digit-sequence match against a
    whole evidence file is too loose: testing this against the real
    corpus found Career_Wealth.md contains the literal string "40%" eight
    separate times, for eight unrelated claims (market velocity, downtime,
    reconciliation effort -- never onboarding), which would have made a
    plain substring check call a fabricated "40% onboarding" claim
    "grounded" just because SOME "40%" exists somewhere in a 134KB file.
    Pairing each metric with nearby context words and requiring both to
    co-occur closes that hole without needing anything semantic."""
    results = []
    for clause in re.split(r"[.;]\s+", text):
        metrics = extract_metrics(clause)
        if not metrics:
            continue
        words = set(re.findall(r"[a-z]{5,}", clause.lower()))
        for m in metrics:
            results.append((m, words))
    return results


def _metric_grounded_in(metric: str, context_words: set, texts: list, window: int = 150, min_shared: int = 2) -> bool:
    """True if `metric` appears in any of `texts` with at least
    `min_shared` context words within `window` characters either side.
    Tightened to 2 shared words / 150 chars (down from an initial 1
    word / 300 chars) after testing against the real fabricated "40%"
    claim: Career_Wealth.md's dense, multi-thousand-character project
    blocks are information-rich enough that a single common word
    ("through," "service," "tooling") will coincidentally sit within 300
    characters of almost any number purely by chance. Requiring two
    co-occurring words is a real precision/recall tradeoff, not a free
    win -- biased deliberately toward flagging a genuinely-grounded claim
    for a human's second look (mild friction) over calling a fabricated
    one "verified" (the actual danger this check exists to prevent)."""
    metric_lower = metric.lower()
    for text in texts:
        lower = text.lower()
        start = 0
        while True:
            idx = lower.find(metric_lower, start)
            if idx == -1:
                break
            span = lower[max(0, idx - window): idx + window]
            hits = sum(1 for w in context_words if w in span)
            if hits >= min_shared:
                return True
            start = idx + 1
    return False


def check_metric_grounding(addition_text: str, evidence_field: str):
    """For every metric-shaped number in a Stage 4 insertion, confirm it
    appears NEAR at least one context word from its own sentence, in the
    evidence file(s) Stage 4 itself cited (checked first), falling back to
    the whole evidence corpus (a weaker signal -- Stage 4 may have cited
    the wrong file for a real number) only if the cited file doesn't have
    it. Returns (grounded: bool, ungrounded: list) -- the caller downgrades
    default_accepted when ungrounded is non-empty, regardless of Stage 4's
    own confidence label, since that label means "the model said so," not
    "verified against source.\""""
    metrics_with_context = extract_metrics_with_context(addition_text)
    if not metrics_with_context:
        return True, []

    cited_files = re.findall(r"`([^`]+\.md)`", evidence_field)
    cited_texts = []
    for fname in cited_files:
        p = EVIDENCE_DIR / fname
        if p.exists():
            cited_texts.append(p.read_text(errors="replace"))

    corpus_texts = None  # lazily loaded only if a cited-file check misses
    ungrounded = []
    for metric, context_words in metrics_with_context:
        if _metric_grounded_in(metric, context_words, cited_texts):
            continue
        if corpus_texts is None:
            corpus_texts = []
            if EVIDENCE_DIR.exists():
                corpus_texts = [f.read_text(errors="replace") for f in EVIDENCE_DIR.glob("*.md")]
        if _metric_grounded_in(metric, context_words, corpus_texts):
            continue
        ungrounded.append(metric)
    return (len(ungrounded) == 0), ungrounded


IDENTITY_DRIFT_PAIRS = [
    {
        "label": "Technical Program Manager → Product Manager",
        # Broadened after a real independent review caught a genuine gap:
        # "End-to-End Product Delivery Ownership... platform product
        # programs" and "large-scale platform product programs" both
        # reframe "technical program(s)" as "product program(s)"/"product
        # delivery" -- the same identity-shift risk as swapping the title
        # outright, just phrased through the word "program" itself rather
        # than "manager". The original 4-phrase list missed both because
        # neither contains "product manager", "product management",
        # "product strategy", or "product roadmap" literally.
        "toward": ["product manager", "product management", "product strategy",
                   "product roadmap", "product program", "product delivery"],
    },
]
IDENTITY_DRIFT_THRESHOLD = 3


def scan_identity_drift(stage3_changes: list) -> list:
    """Batch-level check across ALL Stage 3 edits in one run: a title/
    identity-sensitive phrase pattern that shows up as a SERIES of small,
    individually-defensible keyword tweaks -- invisible to a one-card-at-
    a-time review, only visible once you count across the whole batch.
    No new parsing: reuses each edit's already-computed before/after text.
    Deliberately a short, curated list, not a general "detect drift"
    engine -- a string-presence count generalizes only as far as the
    pairs actually named here."""
    warnings = []
    for pair in IDENTITY_DRIFT_PAIRS:
        hits = []
        for c in stage3_changes:
            before_lower = c["before"].lower()
            after_lower = c["after"].lower()
            # Checked PER PHRASE, not collapsed into one any()/not-any() --
            # a real edit (the Core Competencies swap) had "Product
            # Delivery" already present in `before` while "Product
            # Management" was the genuinely new phrase in the same line.
            # The original any()/not-any() logic let the pre-existing
            # phrase mask the new one and silently dropped this edit from
            # the flagged list -- found by re-testing after broadening the
            # phrase set, not assumed to still work.
            newly_introduced = [p for p in pair["toward"] if p in after_lower and p not in before_lower]
            if newly_introduced:
                hits.append(c["id"])
        if len(hits) >= IDENTITY_DRIFT_THRESHOLD:
            lead_phrase = pair["toward"][0]
            warnings.append({
                "label": pair["label"],
                "count": len(hits),
                "change_ids": hits,
                "message": (
                    f"{len(hits)} edits in this batch add \"{lead_phrase}\"-style language. "
                    f"Review whether this reflects real experience before accepting all of "
                    f"them -- individually each looks like a reasonable keyword match; "
                    f"together they rewrite what job you're claiming to have held."
                ),
            })
    return warnings


TOPICAL_OVERLAP_WARN_THRESHOLD = 0.20


def topical_overlap_score(resume_text: str, addition_text: str):
    """Word-set (Jaccard) similarity between a proposed insertion and the
    single highest-overlapping existing bullet already in the resume --
    NOT the resume as one blob, which dilutes the signal past
    meaningfulness (a small addition's words are a tiny fraction of a
    whole resume's vocabulary). Same technique trim_review.py already uses
    for bullet scoring, reused rather than reinvented. Deliberately a SOFT
    signal surfaced as a warning, never an auto-defer: verified against a
    real near-duplicate pair (two differently-worded OKR-tracking bullets)
    that scored 0.212 -- well under the 0.35 the existing hard duplicate
    check effectively requires, so this catches a real gap, but shouldn't
    be trusted with the hard check's certainty. Returns (score, matched
    bullet text) so the review card can show what it's flagged against."""
    add_words = set(re.findall(r"[a-z]{4,}", strip_markup(addition_text).lower()))
    if not add_words:
        return 0.0, ""
    lines = [l.strip() for l in resume_text.split("\n")]
    # Compare against each line AND each line merged with the next one --
    # a pragmatic fix for hard-wrapped source text (confirmed on the real
    # Meta variant: a bullet split across two physical lines scored lower
    # than it should have, because half its words were sitting on the
    # line after the one being compared). Not a general-purpose logical-
    # line merger (this variant has no bullet markers at all, so "where
    # does one claim end and the next begin" isn't cleanly answerable) --
    # just enough to stop a 2-line wrap from silently halving a real match.
    candidates = []
    for i, s in enumerate(lines):
        if not s or s in KNOWN_SECTIONS or is_role_header(s):
            continue
        candidates.append(s.lstrip("•").strip())
        if i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt and nxt not in KNOWN_SECTIONS and not is_role_header(nxt):
                candidates.append((s + " " + nxt).lstrip("•").strip())

    best_score, best_bullet = 0.0, ""
    for s_clean in candidates:
        if len(s_clean) < 20:
            continue
        bullet_words = set(re.findall(r"[a-z]{4,}", s_clean.lower()))
        if not bullet_words:
            continue
        score = len(add_words & bullet_words) / len(add_words | bullet_words)
        if score > best_score:
            best_score, best_bullet = score, s_clean
    return best_score, best_bullet


HEDGE_RE = re.compile(
    r"\blikely\b|\bprobably\b|\bpresumably\b|\bmay have\b|\bmight have\b"
    r"|\bpossibly\b|\bappears to\b|\bcould have\b|\bseems to\b|\bassuming\b",
    re.IGNORECASE,
)


def check_hedge_language(why_text: str):
    """True if the model's OWN justification for a Stage 3 edit contains
    hedge language. Found by testing against a real batch: an edit that
    inserted "Python" into a historical job justified itself with "likely
    used at Apple given the timeframe" -- an admitted guess presented as a
    resume fact. If the tool's own reasoning hedges, that's not something
    to infer from the proposed text, it's stated outright. Tested against
    87 real edits across 6 JDs: exactly one hit, and it was this exact
    case -- zero false positives elsewhere, the highest-precision check
    built so far. Stage 3 only: Stage 4's "reason" field is built from
    "gap — where", not a free-text justification, so there's nothing to
    scan for hedging there."""
    m = HEDGE_RE.search(why_text)
    return (m is not None), (m.group() if m else None)


def _ngrams(text: str, n: int) -> set:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    return set(" ".join(words[i:i + n]) for i in range(len(words) - n + 1))


PHRASE_REPEAT_MIN_CARDS_3GRAM = 3
PHRASE_REPEAT_MIN_CARDS_2GRAM = 4


def scan_repeated_phrases(changes: list, resume_text: str) -> list:
    """Batch-level check: a phrase genuinely new to this resume (absent
    from the original base text) that shows up in several different
    proposed changes. Verified against six real JDs before being wired in:
    caught "across multi-cloud environments" (3-4 cards), "owned
    architectural decisions...including api design" (3-4 cards, matching
    the single most-flagged pattern in an independent review of that
    batch), "platform roadmap" (4 cards), "with clear slos" (3 cards) --
    all zero-cost text matching, no LLM call. 3-word phrases are checked
    at a lower threshold (3+ cards) since a 3-gram match is a stronger,
    more specific signal; 2-word phrases need a stricter threshold (4+)
    since shorter phrases recur more often by chance alone. Overlapping
    n-grams that flag the exact same set of cards (e.g. "across multi-
    cloud" and "across multi-cloud environments" both pointing at the same
    three cards) are reported once, not once per n-gram.
    Known gap, not handled here: a single word repeated inside a
    DIFFERENT surrounding phrase each time (e.g. "portfolio" used 9 times
    in 9 different two-word contexts) isn't caught by phrase matching at
    all -- confirmed on real JD13 data, where the word existed twice in
    the base resume and this check can't see that 2-to-9 amplification,
    only "was this exact phrase in the base resume at all." That needs
    frequency comparison, not presence matching, and isn't built yet."""
    base_2gram = _ngrams(resume_text, 2)
    base_3gram = _ngrams(resume_text, 3)

    phrase_cards_3, phrase_cards_2 = defaultdict(set), defaultdict(set)
    for c in changes:
        text = c.get("after", "")
        if not text:
            continue
        for ng in _ngrams(text, 3):
            if ng not in base_3gram:
                phrase_cards_3[ng].add(c["id"])
        for ng in _ngrams(text, 2):
            if ng not in base_2gram:
                phrase_cards_2[ng].add(c["id"])

    warnings, seen_card_sets = [], []
    for ng, ids in sorted(phrase_cards_3.items(), key=lambda x: -len(x[1])):
        if len(ids) >= PHRASE_REPEAT_MIN_CARDS_3GRAM and ids not in seen_card_sets:
            seen_card_sets.append(ids)
            warnings.append({"phrase": ng, "change_ids": sorted(ids)})
    for ng, ids in sorted(phrase_cards_2.items(), key=lambda x: -len(x[1])):
        if len(ids) >= PHRASE_REPEAT_MIN_CARDS_2GRAM and ids not in seen_card_sets:
            seen_card_sets.append(ids)
            warnings.append({"phrase": ng, "change_ids": sorted(ids)})
    return warnings


def compute_manifest(edits, recs, s2_additions=None, s2_reference=None, s2_keywords=None, resume_text=""):
    """One dict per candidate change, independent of any accept/reject
    decision. `default_accepted` mirrors Stage 5's own auto-apply policy:
      - Stage 3 paraphrase edits: always (exact-quote, reword-only, safe)
      - Stage 4 HIGH-confidence insertions: yes
      - Stage 2 insertions and anything else: no, always human-reviewed --
        Stage 2's suggestions aren't evidence-cited the way Stage 3/4 are
    `ats_score` is a weighted count of Stage 2's own MISSING KEYWORDS this
    change's proposed text would introduce (CRITICAL=3/HIGH=2/MEDIUM=1) --
    the closest thing to "which version is more applicable to this JD's ATS
    hit" that can be computed without asking a model to judge relevance."""
    s2_additions = s2_additions or []
    s2_reference = s2_reference or []
    s2_keywords = s2_keywords or {}
    all_recs = list(recs) + list(s2_additions)

    changes = []
    for i, e in enumerate(edits):
        alt = find_alt_suggestion(e["current"], s2_reference)
        change = {
            "id": f"p3-{i}",
            "type": "paraphrase",
            "source": "stage3",
            "file": e["file"],
            "before": e["current"],
            "after": e["paraphrase"],
            "reason": e["why"].strip(),
            "confidence": "N/A (reword of existing fact only)",
            "ats_score": score_against_keywords(e["paraphrase"], s2_keywords),
            "word_delta": word_count(e["paraphrase"]) - word_count(e["current"]),
            "default_accepted": True,
        }
        hedge_found, hedge_phrase = check_hedge_language(e["why"])
        if hedge_found:
            change["default_accepted"] = False
            change["hedge_flag"] = hedge_phrase
        if alt:
            change["alt_suggestion"] = {
                "source": "stage2",
                "after": alt["after"],
                "reason": alt["reason"],
                "ats_score": score_against_keywords(alt["after"], s2_keywords),
                "word_delta": word_count(alt["after"]) - word_count(e["current"]),
                "note": "Stage 2 proposed a larger rewrite here. Not auto-appliable: "
                        "its quote is a truncated fragment, not the full sentence, so a "
                        "safe find-and-replace can't be computed. Shown for comparison only.",
            }
        changes.append(change)

    # A pattern flagged across the whole batch is stronger evidence than
    # any single card looks like on its own -- once scan_identity_drift
    # confirms a real pattern (not just one edit that happens to mention
    # "product"), un-checking those specific cards by default is the
    # consistent behavior with how a Stage 4 grounding failure already
    # downgrades default_accepted. A passive warning banner elsewhere on
    # the page, with the flagged cards still sitting checked, means a
    # hands-off Apply click would still apply every one of them -- which
    # defeats the point of having caught the pattern at all.
    flagged_ids = {cid for w in scan_identity_drift(changes) for cid in w["change_ids"]}
    for c in changes:
        if c["id"] in flagged_ids:
            c["default_accepted"] = False
            c["pattern_flag"] = "Part of a batch-wide identity-drift pattern — see the warning above before accepting"

    for i, r in enumerate(all_recs):
        source = r.get("source", "stage4")
        addition_text = strip_markup(r["addition_text"]) if r["addition_text"] else ""
        if not addition_text:
            # Even the fallback extraction (extract_addition_fallback) found
            # nothing -- this candidate has no actual text to show or apply.
            # A card reading "(no addition text parsed)" is pure clutter to
            # a human reviewing 20+ cards; skip it rather than surface a
            # candidate that can never be usefully approved. The gap/where
            # info isn't lost -- it's still in the Phase A section of the
            # raw ats_evidence_gap_response.txt if anyone needs to check.
            continue

        default_accepted = source == "stage4" and r["confidence"] == "HIGH" and bool(addition_text)

        grounded, ungrounded_numbers = check_metric_grounding(addition_text, r.get("evidence", ""))
        if not grounded:
            default_accepted = False

        overlap_score, overlap_match = topical_overlap_score(resume_text, addition_text)
        possible_duplicate = overlap_score >= TOPICAL_OVERLAP_WARN_THRESHOLD

        changes.append({
            "id": f"p4-{i}",
            "type": "insertion",
            "source": source,
            "file": r.get("evidence", ""),
            "before": "",
            "after": addition_text,
            "reason": f"{r['gap'].strip()} — {r['where'].strip()}",
            "confidence": r["confidence"],
            "ats_score": score_against_keywords(addition_text, s2_keywords),
            "word_delta": word_count(addition_text),
            "default_accepted": default_accepted,
            "grounded": grounded,
            "ungrounded_numbers": ungrounded_numbers,
            "possible_duplicate": possible_duplicate,
            "duplicate_overlap_score": round(overlap_score, 2) if possible_duplicate else None,
            "duplicate_match_snippet": overlap_match if possible_duplicate else None,
        })

    # Repeated-phrase check runs across the WHOLE batch (Stage 3 + Stage 4
    # together), unlike the identity-drift scan above which is Stage-3-only
    # by design -- verified on real data that the single most-flagged
    # repeated phrase in one batch spanned three Stage 3 cards AND one
    # Stage 4 insertion, so checking only one type would have missed it.
    repeat_flagged_ids = {cid for w in scan_repeated_phrases(changes, resume_text) for cid in w["change_ids"]}
    for c in changes:
        if c["id"] in repeat_flagged_ids and c.get("default_accepted"):
            c["default_accepted"] = False
            c["repetition_flag"] = "This phrasing repeats across several other proposed changes — see the warning above before accepting"

    return changes


def apply_manifest(resume_text: str, edits, recs, accepted_ids, s2_additions=None):
    """Apply exactly the changes named in `accepted_ids` (a set/list of
    manifest ids) and nothing else. accepted_ids == every default_accepted
    id from compute_manifest() reproduces the plain Stage 5 CLI behavior
    exactly -- that equivalence is what keeps the web review flow from
    silently doing something the CLI wouldn't."""
    all_recs = list(recs) + list(s2_additions or [])
    accepted_ids = set(accepted_ids)
    accepted_edits = [e for i, e in enumerate(edits) if f"p3-{i}" in accepted_ids]
    accepted_recs = [r for i, r in enumerate(all_recs) if f"p4-{i}" in accepted_ids]

    resume_text, applied, skipped = apply_edits(resume_text, accepted_edits)
    # force=True: a human already approved this specific text in Stage 6,
    # so the confidence gate (which exists to protect an unattended run)
    # no longer applies -- but anchor-location and near-duplicate checks
    # still run, because those catch placement/formatting problems that
    # approval doesn't fix.
    resume_text, inserted, deferred = insert_high_confidence(resume_text, accepted_recs, force=True)
    resume_text = append_review_section(resume_text, deferred)
    return resume_text, applied, skipped, inserted, deferred


# ── Report ───────────────────────────────────────────────────────────────────
def build_report(jd_name, variant, s2, applied, skipped, inserted, deferred, structural_gaps, skip_mode=False):
    lines = [f"# Stage 5 Synthesis Report — {jd_name}", ""]
    lines.append(f"**Chosen variant:** {variant}")
    lines.append(f"**Stage 2 ATS Score:** {s2['score']}/100")
    lines.append(f"**Stage 2 Shortlist Verdict:** {s2['verdict']}")
    lines.append(f"**Tokens spent by Stage 5:** 0 (deterministic — no LLM call)")
    lines.append("")

    if skip_mode:
        lines.append("## Outcome: SKIPPED — no resume synthesized")
        lines.append("")
        lines.append(
            "Stage 2 verdict is NO. Paraphrase edits (Stage 3) and evidence-sourced "
            "additions (Stage 4) can only strengthen presentation of real experience — "
            "neither can close a structural mismatch Stage 2 already flagged. Generating "
            "a resume for this JD would waste the candidate's time on a doomed "
            "application. Stage 2's own reasoning:"
        )
        lines.append("")
        lines.append(f"> {s2['reason']}")
        lines.append("")
        lines.append(
            "**Process note:** if this gate had existed before Stage 3/4 ran for this "
            "JD, their cost would have been avoided entirely — Stage 3/4 together are "
            "typically the most expensive part of a per-JD run. Wire this gate in "
            "*before* Stage 3/4 execution for future JDs, not just before Stage 5."
        )
        return "\n".join(lines)

    lines.append("## Outcome: resume synthesized")
    lines.append("")
    lines.append(f"- Stage 3 edits applied: {len(applied)}")
    lines.append(f"- Stage 3 edits skipped (text not found): {len(skipped)}")
    lines.append(f"- Stage 4 items auto-inserted (HIGH confidence + located): {len(inserted)}")
    lines.append(f"- Stage 4 items deferred (needs human review): {len(deferred)}")
    lines.append("")

    if applied:
        lines.append("## Applied — Stage 3 paraphrase edits")
        for e in applied:
            lines.append(f"- **{e['file']}**: \"{e['current'][:70]}...\" → \"{e['paraphrase'][:70]}...\"")
            lines.append(f"  - Why: {e['why'].strip()}")
        lines.append("")

    if skipped:
        lines.append("## Skipped — Stage 3 edits (review manually)")
        for e in skipped:
            lines.append(f"- **{e['file']}**: {e['reason']}")
            lines.append(f"  - Current text Stage 3 quoted: \"{e['current'][:100]}...\"")
        lines.append("")

    if inserted:
        lines.append("## Inserted — Stage 4 new content (HIGH confidence)")
        for r in inserted:
            lines.append(f"- **{r['title'].strip()}** (gap: {r['gap'].strip()})")
            lines.append(f"  - Added: {r['addition_text'][:150]}...")
            lines.append(f"  - Evidence: {r['evidence'].strip()}")
        lines.append("")

    if deferred:
        lines.append("## Deferred — Stage 4 items NOT applied (human review required)")
        for r in deferred:
            lines.append(f"- **{r['title'].strip()}** — {r['reason']}")
            lines.append(f"  - Confidence: {r['confidence']} | Evidence: {r['evidence'].strip()}")
        lines.append("")

    if structural_gaps:
        lines.append("## Known structural gaps (not fixable by this stage — cover letter / interview prep)")
        lines.append(structural_gaps.strip())
        lines.append("")

    return "\n".join(lines)


# ── Shared loader — used by both the CLI (main, below) and the web app's ───
# Stage 6 routes, so path resolution and the "which files must exist" rule
# lives in exactly one place.
class JDInputsError(Exception):
    pass


def load_jd_inputs(jd_name: str):
    analysis_dir = PROMPTS / "JD_Analysis" / jd_name
    prep_dir = PROMPTS / f"{jd_name}_PREP"
    resp_dir = prep_dir / "resp"

    chosen_variant_file = analysis_dir / ".chosen_variant"
    if not chosen_variant_file.exists():
        raise JDInputsError(f"{chosen_variant_file} not found. Run batch_prep.sh --continue first.")
    variant = chosen_variant_file.read_text().strip()

    s2_file = resp_dir / "ats_prompt_response.txt"
    s3_file = resp_dir / "ats_recommend_prompt_response.txt"
    s4_file = resp_dir / "ats_evidence_gap_response.txt"
    for f in (s2_file, s3_file, s4_file):
        if not f.exists():
            raise JDInputsError(f"missing {f}. Stage 5/6 requires Stages 2, 3, and 4 responses.")

    resume_file = OUTPUT / "resume" / f"{variant}.md"
    if not resume_file.exists():
        raise JDInputsError(f"base resume not found at {resume_file}")

    s2_text = s2_file.read_text(encoding="utf-8", errors="replace")
    s2 = parse_stage2(s2_text)
    s2_keywords = parse_stage2_keywords(s2_text)
    s2_reference, s2_additions = parse_stage2_suggestions(s2_text)
    edits, structural_gaps = parse_stage3(s3_file.read_text(encoding="utf-8", errors="replace"))
    recs = parse_stage4(s4_file.read_text(encoding="utf-8", errors="replace"))
    resume_text = resume_file.read_text(encoding="utf-8", errors="replace")

    return {
        "jd_name": jd_name,
        "variant": variant,
        "resp_dir": resp_dir,
        "resume_text": resume_text,
        "s2": s2,
        "s2_keywords": s2_keywords,
        "s2_reference": s2_reference,
        "s2_additions": s2_additions,
        "edits": edits,
        "recs": recs,
        "structural_gaps": structural_gaps,
        "out_file": REVIEW_RESUME_DIR / f"{jd_name}_new_resume.md",
        "report_file": resp_dir / "5_synthesis_report.md",
        "manifest_file": resp_dir / "5_changes.json",
    }


# ── Main ─────────────────────────────────────────────────────────────────────
# Three modes, all sharing load_jd_inputs/compute_manifest/apply_manifest so
# the CLI default, a manifest-only preview, and the Stage 6 web review UI can
# never compute three different answers for the same JD:
#   (no flags)      full Stage 5 run, default accept policy — unchanged CLI behavior
#   --manifest-only print the candidate-change manifest as JSON, write nothing
#                    (this is what web/app.py's Stage 6 "load diffs" call runs)
#   --apply-ids     write the resume using EXACTLY the given change ids
#                    (this is what web/app.py's Stage 6 "apply approved" call runs)
def main():
    ap = argparse.ArgumentParser(description="Stage 5 — synthesize final tailored resume from Stage 2-4 responses.")
    ap.add_argument("jd", help="JD name, e.g. JD2")
    ap.add_argument("--force", action="store_true", help="Overwrite existing output/review_resume/{JD}_new_resume.md")
    ap.add_argument("--ignore-gate", action="store_true",
                     help="Synthesize a resume even if Stage 2's verdict is NO (explicit override)")
    ap.add_argument("--manifest-only", action="store_true",
                     help="Print the candidate-change manifest as JSON to stdout; write nothing to disk. "
                          "Used by the Stage 6 web review UI to render the diff view.")
    ap.add_argument("--apply-ids", default=None,
                     help="Comma-separated change ids (from --manifest-only output) to apply, replacing the "
                          "default accept policy entirely. Used by the Stage 6 web review UI's Apply button.")
    args = ap.parse_args()

    try:
        ctx = load_jd_inputs(args.jd)
    except JDInputsError as e:
        if args.manifest_only:
            print(json.dumps({"ok": False, "error": str(e)}))
            return
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    jd_name, variant, resp_dir = ctx["jd_name"], ctx["variant"], ctx["resp_dir"]
    resume_text, s2 = ctx["resume_text"], ctx["s2"]
    edits, recs, structural_gaps = ctx["edits"], ctx["recs"], ctx["structural_gaps"]
    s2_keywords, s2_reference, s2_additions = ctx["s2_keywords"], ctx["s2_reference"], ctx["s2_additions"]
    out_file, report_file, manifest_file = ctx["out_file"], ctx["report_file"], ctx["manifest_file"]

    gated = s2["verdict"] == "NO" and not args.ignore_gate

    if args.manifest_only:
        manifest = [] if gated else compute_manifest(edits, recs, s2_additions, s2_reference, s2_keywords, resume_text)
        pattern_warnings = [] if gated else scan_identity_drift([c for c in manifest if c["type"] == "paraphrase"])
        repetition_warnings = [] if gated else scan_repeated_phrases(manifest, resume_text)
        print(json.dumps({
            "ok": True,
            "jd": jd_name,
            "variant": variant,
            "gated": gated,
            "s2": s2,
            "base_word_count": word_count(resume_text),
            "changes": manifest,
            "pattern_warnings": pattern_warnings,
            "repetition_warnings": repetition_warnings,
        }, indent=2))
        return

    # ── GATE ── (full-run and --apply-ids modes both respect it unless overridden)
    if gated:
        report = build_report(jd_name, variant, s2, [], [], [], [], "", skip_mode=True)
        report_file.write_text(report, encoding="utf-8")
        print(f"SKIPPED — {jd_name}: Stage 2 verdict is NO. No resume written.")
        print(f"  Report: {report_file.relative_to(ROOT)}")
        if out_file.exists() and not args.force:
            print(f"  Note: {out_file.relative_to(ROOT)} already exists from a prior run — left untouched.")
        return

    if out_file.exists() and not args.force and args.apply_ids is None:
        print(f"ERROR: {out_file} already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    manifest = compute_manifest(edits, recs, s2_additions, s2_reference, s2_keywords, resume_text)
    pattern_warnings = scan_identity_drift([c for c in manifest if c["type"] == "paraphrase"])
    if pattern_warnings:
        print("⚠️  Pattern warning(s) — a batch-level check across all Stage 3 edits found:", file=sys.stderr)
        for w in pattern_warnings:
            print(f"   {w['label']}: {w['message']}", file=sys.stderr)
        print("", file=sys.stderr)
    repetition_warnings = scan_repeated_phrases(manifest, resume_text)
    if repetition_warnings:
        print("⚠️  Repetition warning(s) — a phrase new to this resume shows up in several proposed changes:", file=sys.stderr)
        for w in repetition_warnings:
            print(f"   \"{w['phrase']}\" — {len(w['change_ids'])} cards: {', '.join(w['change_ids'])}", file=sys.stderr)
        print("", file=sys.stderr)
    if args.apply_ids is not None:
        accepted_ids = [i.strip() for i in args.apply_ids.split(",") if i.strip()]
        valid_ids = {c["id"] for c in manifest}
        unknown = [i for i in accepted_ids if i not in valid_ids]
        if unknown:
            print(f"ERROR: unknown change id(s) not in this JD's manifest: {unknown}", file=sys.stderr)
            sys.exit(1)
    else:
        accepted_ids = [c["id"] for c in manifest if c["default_accepted"]]

    new_text, applied, skipped, inserted, deferred = apply_manifest(
        resume_text, edits, recs, accepted_ids, s2_additions
    )

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(new_text, encoding="utf-8")
    report = build_report(jd_name, variant, s2, applied, skipped, inserted, deferred, structural_gaps)
    report_file.write_text(report, encoding="utf-8")
    manifest_file.write_text(
        json.dumps({"jd": jd_name, "variant": variant, "changes": manifest}, indent=2),
        encoding="utf-8",
    )

    print(f"OK — {jd_name}: {len(applied)} edits applied, {len(skipped)} skipped, "
          f"{len(inserted)} additions inserted, {len(deferred)} deferred for review.")
    print(f"  Resume: {out_file.relative_to(ROOT)}")
    print(f"  Report: {report_file.relative_to(ROOT)}")
    print(f"  Manifest (for Stage 6 review UI): {manifest_file.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
