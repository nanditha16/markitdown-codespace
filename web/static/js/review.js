// web/static/js/review.js — Stage 6 diff-review page.
//
// Loads the candidate-change manifest from /api/stage6-manifest (computed
// by scripts/synthesize_resume.py --manifest-only -- this file never
// computes a diff or an accept/reject decision itself, it only renders
// what that script already decided and lets the user override it), tracks
// checkbox state client-side, and POSTs the approved id list to
// /api/stage6-apply on demand.

let currentJD = null;
let currentChanges = [];
let baseWordCount = 0;
const WORDS_PER_PAGE = 550; // rough heuristic -- see updateAcceptedCount() note

async function initReview(jd) {
  currentJD = jd;
  const list = document.getElementById("changeList");
  const meta = document.getElementById("reviewMeta");

  let data;
  try {
    const res = await fetch(`/api/stage6-manifest?jd=${encodeURIComponent(jd)}`);
    data = await res.json();
  } catch (e) {
    list.innerHTML = `<p class="empty-state">Failed to load: ${e}</p>`;
    return;
  }

  if (!data.ok) {
    meta.textContent = "Error";
    list.innerHTML = `<p class="empty-state">${escapeHtml(data.error || "Unknown error")}</p>`;
    return;
  }

  meta.textContent = `Variant: ${data.variant} · Stage 2 score ${data.s2.score}/100 · Verdict ${data.s2.verdict}`;
  baseWordCount = data.base_word_count || 0;

  if (data.gated) {
    const banner = document.getElementById("gatedBanner");
    banner.style.display = "block";
    banner.innerHTML = `
      <strong>Stage 5/6 gated — Stage 2 verdict is NO.</strong>
      <div class="gate-reasoning">${escapeHtml(data.s2.reason)}</div>
      <div class="gate-reasoning">Paraphrasing or adding evidence-backed bullets can't fix a structural
      mismatch. No candidate changes were computed for this JD.</div>`;
    list.innerHTML = "";
    document.getElementById("applyBtn").disabled = true;
    return;
  }

  currentChanges = data.changes;
  renderChanges();
}

function renderChanges() {
  const list = document.getElementById("changeList");
  if (!currentChanges.length) {
    list.innerHTML = `<p class="empty-state">No candidate changes parsed for this JD.</p>`;
    updateAcceptedCount();
    return;
  }

  list.innerHTML = currentChanges.map(c => {
    const isInsertion = c.type === "insertion";
    const confClass = (c.confidence || "").toLowerCase().includes("high") ? "high"
                     : (c.confidence || "").toLowerCase().includes("medium") ? "medium"
                     : (c.confidence || "").toLowerCase().includes("low") ? "low" : "";
    const diffHtml = isInsertion
      ? `<div class="diff-block diff-block--insertion-only">+ ${c.diff_html.after || escapeHtml(c.after)}</div>`
      : `<div class="diff-block">
           <div>${c.diff_html.before}</div>
           <div style="margin-top:4px;">${c.diff_html.after}</div>
         </div>`;

    const sourceLabel = { stage2: "STAGE 2", stage3: "STAGE 3", stage4: "STAGE 4" }[c.source] || c.source.toUpperCase();
    const atsBadge = c.ats_score > 0
      ? `<span class="ats-score" title="Weighted count of this JD's missing keywords this text introduces">ATS +${c.ats_score}</span>`
      : "";
    const wordBadge = wordDeltaBadge(c.word_delta);

    const altBlock = c.alt_suggestion ? `
      <div class="alt-suggestion">
        <div class="alt-suggestion-label">
          💡 Stage 2 also suggested a larger rewrite here
          ${c.alt_suggestion.ats_score > 0 ? `<span class="ats-score ats-score--alt">ATS +${c.alt_suggestion.ats_score}</span>` : ""}
          ${wordDeltaBadge(c.alt_suggestion.word_delta)}
        </div>
        <div class="alt-suggestion-text">${escapeHtml(c.alt_suggestion.after)}</div>
        <div class="alt-suggestion-note">${escapeHtml(c.alt_suggestion.note)}</div>
      </div>` : "";

    return `
      <div class="change-card ${c.default_accepted ? "" : "change-card--rejected"}" id="card-${c.id}">
        <div class="change-card-top">
          <input type="checkbox" id="chk-${c.id}" ${c.default_accepted ? "checked" : ""}
                 onchange="toggleChange('${c.id}')">
          <div class="change-card-body">
            <div class="change-card-meta">
              <span class="change-type change-type--${c.type}">${c.type}</span>
              <span class="change-source change-source--${c.source}">${sourceLabel}</span>
              ${confClass ? `<span class="change-confidence change-confidence--${confClass}">${escapeHtml(c.confidence)}</span>` : ""}
              ${atsBadge}
              ${wordBadge}
              <span class="change-file">${escapeHtml(c.file || "")}</span>
            </div>
            ${diffHtml}
            <div class="change-reason">${escapeHtml(c.reason || "")}</div>
            ${altBlock}
          </div>
        </div>
      </div>`;
  }).join("");

  updateAcceptedCount();
}

function wordDeltaBadge(delta) {
  if (delta == null) return "";
  if (delta === 0) return `<span class="word-delta word-delta--zero">±0w</span>`;
  const sign = delta > 0 ? "+" : "";
  const cls = delta > 30 ? "word-delta--high" : delta > 10 ? "word-delta--mid" : "word-delta--low";
  return `<span class="word-delta ${cls}" title="Net word count change if applied">${sign}${delta}w</span>`;
}

let sortBySize = false;
function toggleSort() {
  sortBySize = !sortBySize;
  const btn = document.getElementById("sortToggleBtn");
  if (sortBySize) {
    currentChanges = [...currentChanges].sort((a, b) => (b.word_delta || 0) - (a.word_delta || 0));
    if (btn) btn.textContent = "Sort: by word cost (highest first) ↓";
  } else {
    currentChanges = [...currentChanges].sort((a, b) => {
      const an = parseInt(a.id.split("-")[1], 10), bn = parseInt(b.id.split("-")[1], 10);
      return a.id.split("-")[0] === b.id.split("-")[0] ? an - bn : a.id.localeCompare(b.id);
    });
    if (btn) btn.textContent = "Sort: as generated";
  }
  renderChanges();
}

function toggleChange(id) {
  const card = document.getElementById(`card-${id}`);
  const checked = document.getElementById(`chk-${id}`).checked;
  card.classList.toggle("change-card--rejected", !checked);
  updateAcceptedCount();
}

function getAcceptedIds() {
  return currentChanges
    .filter(c => document.getElementById(`chk-${c.id}`) && document.getElementById(`chk-${c.id}`).checked)
    .map(c => c.id);
}

function updateAcceptedCount() {
  const accepted = currentChanges.filter(c => document.getElementById(`chk-${c.id}`) && document.getElementById(`chk-${c.id}`).checked);
  const n = accepted.length;
  const netWords = accepted.reduce((sum, c) => sum + (c.word_delta || 0), 0);
  const total = baseWordCount + netWords;
  // Rough heuristic only: ~550 words/page is a common estimate for a
  // single-column technical resume at 10-11pt with standard margins.
  // Actual page count depends on font, margins, and bullet wrapping once
  // this markdown is laid out as a real document -- treat this as a
  // directional warning, not a guarantee, and check the real export.
  const pages = total / WORDS_PER_PAGE;
  document.getElementById("acceptedCount").innerHTML =
    `${n} selected · ~${total}w (${netWords >= 0 ? "+" : ""}${netWords}w) · ` +
    `<span class="${pages > 2 ? "page-est page-est--over" : "page-est"}">~${pages.toFixed(1)} pages (est.)</span>`;
  document.getElementById("applyBtn").disabled = currentChanges.length === 0;
}

async function applyApproved() {
  const btn = document.getElementById("applyBtn");
  const resultBanner = document.getElementById("resultBanner");
  btn.disabled = true;
  btn.textContent = "Applying…";
  resultBanner.style.display = "none";

  try {
    const res = await fetch("/api/stage6-apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jd: currentJD, accepted_ids: getAcceptedIds() }),
    });
    const data = await res.json();
    resultBanner.style.display = "block";
    if (data.ok) {
      resultBanner.className = "banner banner--warn";
      resultBanner.style.background = "var(--green-bg)";
      resultBanner.style.color = "var(--green)";
      resultBanner.innerHTML = `✅ Saved <strong>${data.resume_path}</strong>.<br><pre style="white-space:pre-wrap;font-size:11px;margin-top:6px;">${escapeHtml(data.log)}</pre>`;
    } else {
      resultBanner.className = "banner banner--warn";
      resultBanner.innerHTML = `❌ ${escapeHtml(data.error || data.log || "Apply failed")}`;
    }
  } catch (e) {
    resultBanner.style.display = "block";
    resultBanner.className = "banner banner--warn";
    resultBanner.innerHTML = `❌ ${escapeHtml(String(e))}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Apply approved changes → save resume";
  }
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}
