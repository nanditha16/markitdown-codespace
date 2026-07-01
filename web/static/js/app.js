/* app.js — ATS Pipeline UI
 *
 * State model:
 *   currentStep  : 0-4 (which panel is visible)
 *   statusData   : last /api/status response
 *   modal context: { jd, stage, promptPath, mode }
 */

let currentStep = 0;
let statusData  = null;
let modalCtx    = {};

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadStatus();
  loadVariantBankStatus();
  checkAndShowApiButton();
  setInterval(loadStatus, 30000);
});

// ── Navigation ────────────────────────────────────────────────────────────────
function showStep(n) {
  document.querySelectorAll(".step-panel").forEach((p, i) => {
    p.classList.toggle("hidden", i !== n);
  });
  document.querySelectorAll(".step-btn").forEach((b, i) => {
    b.classList.toggle("step-btn--active", i === n);
  });
  currentStep = n;
  if (n === 0) loadVariantBankStatus();
  if (n === 4) renderDashboard();
  if (n === 2) renderRankCards();
  if (n === 3) { renderAtsCards(); checkAndShowApiButton(); }
  if (n === 5) loadTierStatus();
}

// ── Status / health ───────────────────────────────────────────────────────────
async function loadStatus() {
  try {
    const r = await fetch("/api/status");
    statusData = await r.json();
    updateHealth(statusData.system);
    if (currentStep === 2) renderRankCards();
    if (currentStep === 3) renderAtsCards();
    if (currentStep === 4) renderDashboard();
    updateSavedJDs();
    if (currentStep === 0) loadVariantBankStatus();
  } catch (e) {
    setDot("dotDocker", "error");
    setLabel("lblDocker", "Cannot reach server");
  }
}

function updateHealth(sys) {
  // Docker
  setDot("dotDocker", sys.docker ? "ok" : "error");
  setLabel("lblDocker", sys.docker ? "Docker running" : "Docker not running");
  setCheckIcon("chkDockerIcon", sys.docker ? "✅" : "❌");

  // Resumes
  const hasResumes = sys.resume_count > 0;
  setDot("dotResumes", hasResumes ? "ok" : "warn");
  setLabel("lblResumes", `${sys.resume_count} resume variant${sys.resume_count === 1 ? "" : "s"}`);
  el("chkResumesLabel").textContent =
    hasResumes ? `${sys.resume_count} resume variants in output/resume/` : "No resume variants — run run.sh";
  setCheckIcon("chkResumesIcon", hasResumes ? "✅" : "⚠️");

  // Evidence
  const hasEvidence = sys.evidence_chunks > 0;
  setDot("dotEvidence", hasEvidence ? "ok" : "warn");
  setLabel("lblEvidence", `${sys.evidence_chunks} evidence chunks`);
  el("chkEvidenceLabel").textContent =
    hasEvidence ? `${sys.evidence_chunks} evidence chunks ready` : "No evidence chunks — run ingest";
  setCheckIcon("chkEvidenceIcon", hasEvidence ? "✅" : "⚠️");
}

function setDot(id, state) {
  const d = el(id);
  if (!d) return;
  d.className = `dot dot--${state}`;
}
function setLabel(id, text) { const e = el(id); if (e) e.textContent = text; }
function setCheckIcon(id, icon) { const e = el(id); if (e) e.textContent = icon; }

// ── Tab switching ─────────────────────────────────────────────────────────────
function switchTab(name) {
  el("tabPaste").classList.toggle("hidden", name !== "paste");
  el("tabUpload").classList.toggle("hidden", name !== "upload");
  el("tabBtnPaste").classList.toggle("tab-btn--active", name === "paste");
  el("tabBtnUpload").classList.toggle("tab-btn--active", name === "upload");
}

// ── JD upload / paste ─────────────────────────────────────────────────────────
async function submitJDText() {
  const text = el("jdText").value.trim();
  if (!text) { toast("Paste a job description first.", "err"); return; }
  const r = await fetch("/api/upload-jd", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const data = await r.json();
  if (data.ok) {
    el("jdText").value = "";
    toast(`Saved as ${data.saved.join(", ")}`, "ok");
    await loadStatus();
  } else {
    toast(data.error || "Save failed", "err");
  }
}

async function uploadFiles(files) {
  const fd = new FormData();
  for (const f of files) fd.append("file", f);
  const r    = await fetch("/api/upload-jd", { method: "POST", body: fd });
  const data = await r.json();
  if (data.ok) {
    toast(`Saved: ${data.saved.join(", ")}`, "ok");
    await loadStatus();
  } else {
    toast(data.error || "Upload failed", "err");
  }
}

function handleDrop(e) {
  e.preventDefault();
  el("dropzone").classList.remove("drag-over");
  const files = [...e.dataTransfer.files].filter(f => f.name.endsWith(".txt"));
  if (!files.length) { toast("Only .txt files are accepted.", "err"); return; }
  uploadFiles(files);
}
function handleFileSelect(e) {
  const files = [...e.target.files];
  if (files.length) uploadFiles(files);
}

function updateSavedJDs() {
  const container = el("savedJDs");
  if (!statusData) return;
  const jds = (statusData.jds || []).map(j => j.name);
  if (!jds.length) { container.innerHTML = ""; return; }
  container.innerHTML = jds.map(j =>
    `<span class="jd-tag">${j}</span>`
  ).join("");
}

// ── Script streaming ──────────────────────────────────────────────────────────
function streamToLog(url, logId, bodyId, onDone) {
  const logPanel = el(logId);
  const logBody  = el(bodyId);
  logPanel.classList.remove("hidden");
  logBody.textContent = "";

  const src = new EventSource(url);
  src.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data === "__DONE__") return;
    if (typeof data === "object" && data.exit_code !== undefined) {
      src.close();
      const ok = data.exit_code === 0;
      appendLog(logBody, ok ? "✓ Done" : `✗ Exit code ${data.exit_code}`,
                ok ? "ok" : "err");
      if (onDone) onDone(ok);
      loadStatus();
      return;
    }
    appendLog(logBody, data);
  };
  src.onerror = () => {
    src.close();
    appendLog(logBody, "Connection closed.", "warn");
    loadStatus();
  };
}

function appendLog(el, line, cls) {
  const span = document.createElement("span");
  if (cls) span.className = `log-line--${cls}`;

  // Auto-colour based on content
  if (!cls) {
    if (/^✅|^✓|Done|complete/i.test(line)) span.className = "log-line--ok";
    else if (/^⚠️|^⚠|warn|skip/i.test(line)) span.className = "log-line--warn";
    else if (/^❌|^✗|fail|error/i.test(line)) span.className = "log-line--err";
    else if (/^═|^──|^##/.test(line)) span.className = "log-line--head";
  }

  span.textContent = line + "\n";
  el.appendChild(span);
  el.scrollTop = el.scrollHeight;
}

function closeLog(id) { el(id).classList.add("hidden"); }

// ── Variant bank (Step 0) ─────────────────────────────────────────────────────
async function loadVariantBankStatus() {
  try {
    const r = await fetch("/api/variant-bank-status");
    const d = await r.json();

    const icon  = el("bankStatusIcon");
    const label = el("bankStatusLabel");
    const hint  = el("bankHint");
    const btnBuild   = el("btnBuildBank");
    const btnRebuild = el("btnRebuildBank");
    const btnDl      = el("btnDownloadBank");

    if (!icon) return;  // card not in DOM yet

    if (!d.bank_exists) {
      icon.textContent  = "⚠️";
      label.textContent = `No variant bank yet — ${d.resume_count} resume${d.resume_count === 1 ? "" : "s"} ready to package`;
      hint.textContent  = "Click 'Build variant bank' to create it from your resumes in output/resume/.";
      btnBuild.textContent = "Build variant bank";
      btnBuild.style.display   = "";
      btnRebuild.style.display = "none";
      btnDl.style.display      = "none";

    } else if (d.bank_stale) {
      icon.textContent  = "🟡";
      label.textContent = `Bank is stale — '${d.newest_variant}' is newer than the bank`;
      hint.textContent  = "A resume was added or edited since the last build. Rebuild to include the latest changes.";
      btnBuild.style.display   = "none";
      btnRebuild.style.display = "";
      btnDl.style.display      = "";

    } else {
      const kb = d.bank_size ? Math.round(d.bank_size / 1024) : "?";
      icon.textContent  = "✅";
      label.textContent = `Variant bank ready — ${d.resume_count} variant${d.resume_count === 1 ? "" : "s"} packaged (${kb} KB)`;
      hint.textContent  = "Reuse this file for every job application. Rebuild only when you add or edit resumes.";
      btnBuild.style.display   = "none";
      btnRebuild.style.display = "";
      btnDl.style.display      = "";
    }
  } catch(e) {
    const label = el("bankStatusLabel");
    if (label) label.textContent = "Could not check bank status.";
  }
}

function buildVariantBank(forceRebuild) {
  const url = "/api/build-variant-bank" + (forceRebuild ? "?rebuild=1" : "");
  const btn = forceRebuild ? el("btnRebuildBank") : el("btnBuildBank");
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> Building…`; }

  streamToLog(url, "log-bank", "log-bank-body", (ok) => {
    if (btn) { btn.disabled = false; btn.textContent = forceRebuild ? "Rebuild bank" : "Build variant bank"; }
    if (ok) {
      toast("Variant bank built successfully.", "ok");
      loadVariantBankStatus();
    } else {
      toast("Build failed — see log above.", "err");
    }
  });
}

// ── Pipeline actions ──────────────────────────────────────────────────────────
function runPipeline() {
  streamToLog("/api/run-pipeline", "log-setup", "log-setup-body",
    (ok) => ok && toast("Pipeline complete.", "ok"));
}

function ingestEvidence() {
  streamToLog("/api/ingest-evidence", "log-setup", "log-setup-body",
    (ok) => ok && toast("Evidence ingested.", "ok"));
}

function generateStage1(jd) {
  // For a specific JD: only run variant_rank.sh (writes jd_current.txt).
  // Bank must already exist (built in step 0). For "all JDs" batch, the
  // API endpoint chains build check + variant_rank for each JD.
  const url = jd ? `/api/generate-stage1?jd=${jd}` : "/api/generate-stage1";
  disableBtn("btnGenStage1");
  streamToLog(url, "log-stage1", "log-stage1-body", (ok) => {
    enableBtn("btnGenStage1");
    if (ok) { toast("All files verified — download from each JD card below.", "ok"); renderRankCards(); }
  });
}

function generateStages24(jd) {
  const force = el("forceRegen") ? el("forceRegen").checked : false;
  let url = "/api/generate-stages-2-4";
  if (jd) url += `?jd=${jd}`;
  if (force) url += (url.includes("?") ? "&" : "?") + "force=1";
  disableBtn("btnGenStages24");
  streamToLog(url, "log-stages24", "log-stages24-body", (ok) => {
    enableBtn("btnGenStages24");
    if (ok) { toast("ATS prompts ready.", "ok"); renderAtsCards(); }
  });
}

// ── Rank cards (Step 2) ───────────────────────────────────────────────────────
function renderRankCards() {
  const container = el("jdRankCards");
  if (!statusData) { container.innerHTML = "<p class='empty-state'>Loading…</p>"; return; }

  const bank = statusData.variant_bank || {};
  const jds  = statusData.jds.filter(j => !j.poor_fit);

  if (!jds.length) {
    container.innerHTML = "<p class='empty-state'>No JDs found. Add JDs in step 1 first.</p>";
    return;
  }

  const bankReady  = bank.bank_exists && !bank.bank_stale;
  const promptFile = bank.prompt_exists ? "prompts/variant_rank_prompt.txt" : null;

  container.innerHTML = jds.map(j => {
    // j.jd_file     = output/JDx.md  (produced by pipeline — no generation needed)
    // j.prompt_file = prompts/variant_rank_prompt.txt (shared static, built in Step 0)
    const hasJdMd   = j.jd_file;     // output/JDx.md exists
    const hasPrompt = j.prompt_file;  // variant_rank_prompt.txt exists
    const hasBank   = bank.bank_exists;
    const hasResp   = j.has_response;
    const allReady  = hasJdMd && hasPrompt && hasBank;

    let statusPill = "";
    if      (!hasJdMd)  statusPill = pill("Run pipeline first (output/" + j.name + ".md missing)", "missing");
    else if (!hasBank)  statusPill = pill("Build variant bank first (Step 0)", "missing");
    else if (!hasResp)  statusPill = pill("Waiting for Claude.ai response", "waiting");
    else {
      const verdictColors = { "GOOD FIT": "done", "PARTIAL FIT": "waiting", "POOR FIT": "poor" };
      const vc = verdictColors[j.fit_verdict] || "done";
      const vl = j.fit_verdict || "Response received \u2713";
      statusPill = pill(vl, vc);
    }

    // Chosen variant display (after response)
    const variantShort = j.chosen_variant
      ? j.chosen_variant.replace(/Nanditha_Murthy_Resume_/, "").replace(/_/g, " ")
      : "";

    const downloadSection = allReady ? `
      <div class="split-prompt-files">
        <div class="split-prompt-label">Upload all three files to Claude.ai or ChatGPT in one conversation:</div>
        <div class="split-prompt-row">
          <span class="split-file-badge">1</span>
          <span class="split-file-name">variant_bank.txt
            <span style="color:var(--text-muted);font-size:11px"> — ${bank.resume_count || "?"} variants, static</span>
          </span>
          <a class="btn btn--ghost btn--sm" href="/api/download-bank" download title="Reuse across all JDs">\u2193 Download</a>
          ${!bankReady ? `<span style="color:var(--yellow);font-size:11px;margin-left:4px">\u26a0 rebuild bank</span>` : ""}
        </div>
        <div class="split-prompt-row">
          <span class="split-file-badge">2</span>
          <span class="split-file-name">variant_rank_prompt.txt
            <span style="color:var(--text-muted);font-size:11px"> — instructions, static</span>
          </span>
          <a class="btn btn--ghost btn--sm" href="/api/download?path=${encodeURIComponent("prompts/variant_rank_prompt.txt")}" download="variant_rank_prompt.txt" title="Reuse across all JDs">\u2193 Download</a>
        </div>
        <div class="split-prompt-row">
          <span class="split-file-badge">3</span>
          <span class="split-file-name">${j.name}.md
            <span style="color:var(--text-muted);font-size:11px"> — this job description</span>
          </span>
          <a class="btn btn--ghost btn--sm" href="/api/download?path=${encodeURIComponent(j.jd_file)}" download="${j.name}.md">\u2193 Download</a>
        </div>
        <a class="btn btn--ghost btn--sm" href="https://claude.ai" target="_blank"
           style="margin-top:6px;align-self:flex-start">Open Claude.ai \u2197</a>
      </div>` : "";

    // Show verify button only if jd.md is missing (pipeline not run)
    // or bank missing (Step 0 incomplete) — otherwise files are already there
    const needsAction = !allReady && !hasResp;

    return `
    <div class="jd-card ${hasResp ? "jd-card--complete" : ""}">
      <div class="jd-card-header">
        <span class="jd-card-name">${j.name}</span>
        ${statusPill}
        ${variantShort ? `<span class="jd-card-variant" title="${j.chosen_variant || ""}">→ ${variantShort}</span>` : ""}
      </div>
      ${allReady
        ? downloadSection
        : needsAction
          ? `<div class="jd-card-actions">
               <button class="btn btn--ghost btn--sm" onclick="generateStage1('${j.name}')">Verify readiness</button>
             </div>`
          : ""
      }
      <div class="jd-card-actions" style="margin-top:${allReady ? "10px" : "0"}">
        ${allReady ? `<button class="btn btn--primary btn--sm" onclick="openPaste('${j.name}', 's1')">Paste Claude response</button>` : ""}
        ${hasResp  ? `<button class="btn btn--ghost btn--sm" onclick="viewResponse('${j.name}', 's1')">View saved response</button>` : ""}
      </div>
    </div>`;
  }).join("");
}

// ── ATS cards (Step 3) ────────────────────────────────────────────────────────
function renderAtsCards() {
  const container = el("jdAtsCards");
  if (!statusData) { container.innerHTML = "<p class='empty-state'>Loading…</p>"; return; }

  const jds = statusData.jds.filter(j => j.has_response && !j.poor_fit);
  if (!jds.length) {
    container.innerHTML = "<p class='empty-state'>No JDs with ranking responses yet. Complete Step 2 first.</p>";
    return;
  }

  container.innerHTML = jds.map(j => {
    const stages = [
      { key: "s2", label: "Stage 2: ATS gaps",         pathKey: "s2" },
      { key: "s3", label: "Stage 3: Paraphrase edits",  pathKey: "s3" },
      { key: "s4", label: "Stage 4: Evidence gaps",     pathKey: "s4" },
    ];

    const pills = stages.map(s => {
      const has = j.stage_prompts[s.pathKey];
      return pill(s.label, has ? "done" : "missing");
    }).join("");

    const stageButtons = stages.map(s => {
      const path = j.stage_prompts[s.pathKey];
      if (!path) return "";
      const hasResp = j.responses && j.responses[s.key];
      return `
        <div class="jd-card" style="border:none;background:var(--surface-2);padding:10px 14px;">
          <div class="jd-card-header">
            <span style="font-size:12px;color:var(--text-muted)">${s.label}</span>
            ${hasResp ? pill("Response saved ✓", "done") : pill("Waiting for response", "waiting")}
          </div>
          <div class="jd-card-actions">
            <button class="btn btn--ghost btn--sm" onclick="viewPrompt('${j.name}', '${s.key}', '${path}')">View / download</button>
            <a class="btn btn--ghost btn--sm" href="https://claude.ai" target="_blank">Claude.ai ↗</a>
            <button class="btn btn--primary btn--sm" onclick="openPaste('${j.name}', '${s.key}')">Paste response</button>
          </div>
        </div>`;
    }).join("");

    const allReady = j.s2 && j.s3 && j.s4;

    return `
    <div class="jd-card ${allReady ? "jd-card--complete" : ""}">
      <div class="jd-card-header">
        <span class="jd-card-name">${j.name}</span>
        <span class="jd-card-variant">${j.chosen_variant || ""}</span>
        <div class="stage-pills">${pills}</div>
      </div>
      ${!allReady
        ? `<div class="action-row">
             <button class="btn btn--ghost btn--sm" onclick="generateStages24('${j.name}')">Generate this JD's prompts</button>
           </div>`
        : ""}
      <div style="display:flex;flex-direction:column;gap:6px;">${stageButtons}</div>
    </div>`;
  }).join("");
}

// ── Dashboard (Step 4) ────────────────────────────────────────────────────────
function renderDashboard() {
  const container = el("dashboardRows");
  if (!statusData) { container.innerHTML = "<p class='empty-state'>Loading…</p>"; return; }

  if (!statusData.jds.length) {
    container.innerHTML = "<p class='empty-state'>No JDs found. Add JD text files to input/other/ and run step 1.</p>";
    return;
  }

  container.innerHTML = statusData.jds.map(j => {
    const stageChip = {
      complete:           `<span class="status-chip status-chip--complete">Complete</span>`,
      poor_fit:           `<span class="status-chip status-chip--poor">Poor fit</span>`,
      needs_stages_2_4:   `<span class="status-chip status-chip--active">In progress</span>`,
      waiting_response:   `<span class="status-chip status-chip--waiting">Awaiting response</span>`,
      needs_stage1_prompt:`<span class="status-chip status-chip--waiting">Need prompt</span>`,
    }[j.stage] || `<span class="status-chip status-chip--waiting">${j.stage}</span>`;

    const s1c = j.has_response ? "ok" : (j.prompt_exists ? "waiting" : "no");
    const s2c = j.s2 ? "ok" : "no";
    const s3c = j.s3 ? "ok" : "no";
    const s4c = j.s4 ? "ok" : "no";

    const variantShort = j.chosen_variant
      ? j.chosen_variant.replace("Nanditha_Murthy_Resume_", "")
      : j.poor_fit ? "— poor fit" : "—";

    return `
    <div class="db-row">
      <div class="db-jd">${j.name}</div>
      <div class="db-var" title="${j.chosen_variant || ""}">${variantShort}</div>
      <div class="db-status">${stageChip}</div>
      <div class="db-s db-s--${s1c}" title="Stage 0/1 ranking">${s1c === "ok" ? "✓" : s1c === "waiting" ? "P" : "—"}</div>
      <div class="db-s db-s--${s2c}" title="Stage 2 ATS">${s2c === "ok" ? "✓" : "—"}</div>
      <div class="db-s db-s--${s3c}" title="Stage 3 recommend">${s3c === "ok" ? "✓" : "—"}</div>
      <div class="db-s db-s--${s4c}" title="Stage 4 evidence">${s4c === "ok" ? "✓" : "—"}</div>
    </div>`;
  }).join("");
}

// ── Modal: view prompt ────────────────────────────────────────────────────────
async function viewPrompt(jd, stage, path) {
  const r    = await fetch(`/api/prompt-content?path=${encodeURIComponent(path)}`);
  const data = await r.json();
  if (!data.ok) { toast("Could not load prompt file.", "err"); return; }

  modalCtx = { jd, stage, promptPath: path, mode: "view" };

  el("modalTitle").textContent = `${jd} — ${data.name}`;
  el("modalBody").innerHTML = `
    <p class="modal-label">Upload this file to <a href="https://claude.ai" target="_blank" class="link">claude.ai</a> as a file attachment (not copy-paste — clipboard corrupts em-dashes).</p>
    <div class="prompt-actions">
      <button class="btn btn--primary btn--sm" onclick="copyPromptText()">Copy to clipboard</button>
      <a class="btn btn--ghost btn--sm" href="/api/download?path=${encodeURIComponent(path)}" download>Download file</a>
      <a class="btn btn--ghost btn--sm" href="https://claude.ai" target="_blank">Open Claude.ai ↗</a>
    </div>
    <pre class="prompt-preview" id="promptPreviewText">${escHtml(data.content)}</pre>
    <div style="margin-top:10px;">
      <button class="btn btn--ghost btn--sm" onclick="switchModalToPaste()">→ I've got a response to paste</button>
    </div>`;
  openModal();
}

function switchModalToPaste() {
  const { jd, stage } = modalCtx;
  el("modalTitle").textContent = `${jd} — Paste Claude.ai response`;
  el("modalBody").innerHTML = `
    <p class="modal-label">Paste Claude's complete response for <strong>${jd}</strong> stage <strong>${stage}</strong>.</p>
    <textarea class="paste-area" id="pasteArea" placeholder="Paste Claude.ai response here…"></textarea>
    <div class="modal-footer">
      <button class="btn btn--ghost" onclick="closeModal()">Cancel</button>
      <button class="btn btn--primary" onclick="saveModalResponse()">Save response</button>
    </div>`;
}

async function openPaste(jd, stage) {
  modalCtx = { jd, stage, mode: "paste" };
  const stageLabel = { s1: "Variant ranking (Stage 0/1)", s2: "ATS analysis (Stage 2)",
                       s3: "Paraphrase edits (Stage 3)", s4: "Evidence gaps (Stage 4)",
                       s5: "Cover letter (Stage 6)" }[stage] || stage;
  el("modalTitle").textContent = `${jd} — ${stageLabel}`;
  el("modalBody").innerHTML = `
    <p class="modal-label">Paste Claude's complete response for <strong>${jd}</strong>.</p>
    <textarea class="paste-area" id="pasteArea" placeholder="Paste Claude.ai response here…"></textarea>
    <div class="modal-footer">
      <button class="btn btn--ghost" onclick="closeModal()">Cancel</button>
      <button class="btn btn--primary" onclick="saveModalResponse()">Save response</button>
    </div>`;
  openModal();
}

async function viewResponse(jd, stage) {
  if (!statusData) return;
  const jdData = statusData.jds.find(j => j.name === jd);
  if (!jdData) return;
  const path = jdData.responses && jdData.responses[stage];
  if (!path) { toast("Response file not found.", "err"); return; }
  const r    = await fetch(`/api/prompt-content?path=${encodeURIComponent(path)}`);
  const data = await r.json();
  if (!data.ok) { toast("Could not load response.", "err"); return; }

  const text = data.content;
  let verdictBanner = "";

  if (stage === "s1") {
    // Extract Stage 0 verdict for banner
    const goodFit    = /GOOD\s+FIT/i.test(text);
    const partialFit = /PARTIAL\s+FIT/i.test(text);
    const poorFit    = /POOR\s+FIT/i.test(text);

    // Extract the Stage 0 section text (up to Stage 1 or end)
    const s0Match = text.match(/##\s*Stage\s*0[^\n]*\n([\s\S]*?)(?=\n##\s*Stage\s*1|\n---|\n#\s|$)/i);
    const s0Text  = s0Match ? s0Match[1].trim() : "";

    const [bgColor, label] =
      goodFit    ? ["var(--green)",  "✅ GOOD FIT"]    :
      partialFit ? ["var(--yellow)", "⚠ PARTIAL FIT"] :
      poorFit    ? ["var(--red)",    "❌ POOR FIT"]    :
                   ["var(--gray)",   "Stage 0 verdict not detected"];

    verdictBanner = `
      <div style="background:${bgColor}22;border:1px solid ${bgColor};border-radius:6px;padding:12px 16px;margin-bottom:14px;">
        <div style="font-weight:700;font-size:14px;color:${bgColor};margin-bottom:${s0Text ? "6px" : "0"}">${label}</div>
        ${s0Text ? `<div style="font-size:13px;color:var(--text);line-height:1.6">${escHtml(s0Text)}</div>` : ""}
      </div>`;
  }

  el("modalTitle").textContent = `${jd} — Response (${stage === "s1" ? "Stage 0/1 Ranking" : stage})`;
  el("modalBody").innerHTML = `
    <p class="modal-label">Saved response from Claude.ai</p>
    ${verdictBanner}
    <pre class="prompt-preview" style="margin-top:0">${escHtml(text)}</pre>`;
  openModal();
}

async function saveModalResponse() {
  const { jd, stage } = modalCtx;
  const text = (el("pasteArea") || {}).value || "";
  if (!text.trim()) { toast("Nothing to save — paste a response first.", "err"); return; }

  const endpoint = stage === "s1" ? "/api/paste-response" : "/api/paste-stage-response";
  const body = stage === "s1"
    ? { jd, text }
    : { jd, stage, text };

  const r    = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (data.ok) {
    closeModal();
    toast(`Response saved for ${jd}`, "ok");
    await loadStatus();
  } else {
    toast(data.error || "Save failed", "err");
  }
}

function copyPromptText() {
  const txt = el("promptPreviewText");
  if (!txt) return;
  navigator.clipboard.writeText(txt.textContent)
    .then(() => toast("Copied to clipboard", "ok"))
    .catch(() => toast("Clipboard not available — download the file instead", "err"));
}

// ── Modal helpers ─────────────────────────────────────────────────────────────
function openModal()  { el("modalOverlay").classList.remove("hidden"); }
function closeModal() { el("modalOverlay").classList.add("hidden"); modalCtx = {}; }

// ── Toast ─────────────────────────────────────────────────────────────────────
let toastTimer;
function toast(msg, type = "ok") {
  const t = el("toast");
  t.textContent = msg;
  t.className   = `toast toast--${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 3500);
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function el(id) { return document.getElementById(id); }

function pill(label, state) {
  return `<span class="stage-pill stage-pill--${state}">${label}</span>`;
}

function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function disableBtn(id) {
  const b = el(id);
  if (b) { b.disabled = true; b.innerHTML = `<span class="spinner"></span> Running…`; }
}
function enableBtn(id) {
  const b = el(id);
  if (!b) return;
  b.disabled = false;
  const labels = {
    btnGenStage1:    "Check all JDs",
    btnGenStages24:  "Generate ATS prompts for all ready JDs",
    btnRunStage2Api: "⚡ Run Stage 2 via API (Pro)",
  };
  b.textContent = labels[id] || "Run";
}

// ── Settings / Tier ───────────────────────────────────────────────────────────
function switchSettingsTab(name) {
  el("settingsGCP").classList.toggle("hidden", name !== "gcp");
  el("settingsClaude").classList.toggle("hidden", name !== "claude");
  el("tabBtnGCP").classList.toggle("tab-btn--active", name === "gcp");
  el("tabBtnClaude").classList.toggle("tab-btn--active", name === "claude");
}

async function loadTierStatus() {
  const box = el("tierStatus");
  if (!box) return;
  try {
    const r = await fetch("/api/tier");
    const d = await r.json();
    const tier = d.tier || "free";
    const icons = { free: "🆓", pro: "⚡", team: "🏢" };
    const labels = {
      free: "Free — manual Claude.ai upload/paste",
      pro:  "Pro — Stage 2 automation enabled (BYOK)",
      team: "Team — all stages automated (managed)",
    };
    box.innerHTML = `
      <div class="check-row">
        <span class="check-icon">${icons[tier] || "?"}</span>
        <span style="font-weight:600">${tier.toUpperCase()}</span>
        <span style="color:var(--text-muted);margin-left:8px">${labels[tier] || tier}</span>
      </div>
      ${tier !== "free" ? '<p class="hint" style="margin-top:8px;color:var(--green)">✅ API key already configured — Stage 2 automation is active.</p>' : ''}`;

    // Pre-populate GCP project if set
    if (d.gcp_project && el("gcpProject")) {
      el("gcpProject").value = d.gcp_project;
    }
    // Show which provider is active
    if (d.provider === "vertex" && el("tabBtnGCP")) {
      switchSettingsTab("gcp");
    } else if (d.provider === "claude" && el("tabBtnClaude")) {
      switchSettingsTab("claude");
    }
  } catch(e) {
    box.innerHTML = `<p class="hint">Could not load tier status.</p>`;
  }
}

async function saveConfig() {
  const gcp    = (el("gcpProject") || {}).value || "";
  const claude = (el("claudeKey")  || {}).value || "";
  if (!gcp && !claude) { toast("Enter at least one key or project ID.", "err"); return; }
  const r    = await fetch("/api/save-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ gcp_project: gcp, anthropic_api_key: claude }),
  });
  const data = await r.json();
  if (data.ok) {
    toast(`Saved. Tier: ${data.tier}`, "ok");
    if (el("claudeKey")) el("claudeKey").value = "";
    await loadTierStatus();
  } else {
    toast("Save failed.", "err");
  }
}

// Load tier when settings step is shown
const _origShowStep = showStep;
// Patch showStep to load tier when navigating to step 5

async function checkAndShowApiButton() {
  try {
    const r = await fetch("/api/tier");
    const d = await r.json();
    const btn = el("stage2ApiRow");
    if (btn) btn.style.display = (d.tier === "pro" || d.tier === "team") ? "flex" : "none";
  } catch(e) {}
}

// ── Stage 2 API automation ────────────────────────────────────────────────────
function runStage2API(jd, forceOverride) {
  const force = forceOverride || false;

  // Ask user which provider if both could be available
  const provider = el("apiProviderSelect") ? el("apiProviderSelect").value : "auto";

  let url = "/api/run-stage2";
  const params = [];
  if (jd)       params.push("jd=" + jd);
  if (force)    params.push("force=1");
  if (provider && provider !== "auto") params.push("provider=" + provider);
  if (params.length) url += "?" + params.join("&");

  // Show the dedicated API log panel
  el("log-stage2-api").classList.remove("hidden");
  el("log-stage2-api-body").textContent = "";

  disableBtn("btnRunStage2Api");
  streamToLog(url, "log-stage2-api", "log-stage2-api-body", (ok) => {
    enableBtn("btnRunStage2Api");
    if (ok) { toast("Stage 2 complete. Responses saved automatically.", "ok"); renderAtsCards(); }
    else     { toast("Stage 2 failed — see log above.", "err"); }
  });
}
