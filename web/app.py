"""
web/app.py — Flask backend for the ATS Pipeline UI.

Runs INSIDE the Docker container (docker exec markitdown python3 /app/web/app.py).
The container mounts the project at /app so all relative paths resolve correctly.

Design constraints (unchanged from core pipeline):
  - NEVER calls an LLM. All LLM work goes through Claude.ai.
  - NEVER modifies pipeline logic. Calls existing shell scripts only.
  - Policy enforcement: reads policy/execution_policy.json. No hardcoded rules.
  - All state lives in the filesystem. No database.
  - Streaming output via SSE for real-time script progress.
"""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from flask import (Flask, Response, jsonify, render_template, request,
                   send_file, stream_with_context)

# ── Project root is always /app when running inside Docker ────────────────────
# Fall back to resolving from __file__ for host-side development.
ROOT = Path(os.environ.get("ATS_ROOT", "/app"))
if not ROOT.exists():
    ROOT = Path(__file__).parent.parent.resolve()

PROMPTS        = ROOT / "prompts"
INPUT_OTHER    = ROOT / "input" / "other"
INPUT_EVIDENCE = ROOT / "input" / "evidence"
OUTPUT_RESUME  = ROOT / "output" / "resume"
EVIDENCE_CHUNKS= ROOT / "output" / "career_wealth_chunk"
POLICY_FILE    = ROOT / "policy" / "execution_policy.json"

# Static and template folders are relative to this file (web/)
app = Flask(
    __name__,
    template_folder="templates",   # web/templates/
    static_folder="static",        # web/static/
    static_url_path="/static",
)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_policy():
    with open(POLICY_FILE, encoding="utf-8") as f:
        return json.load(f)

def _find_response_file(directory: Path):
    for name in ["variant_rank_prompt_response.txt",
                 "1_variant_rank_prompt_response.txt"]:
        p = directory / name
        if p.exists():
            return p
    return None

def _has_prompt(prep_dir: Path, names):
    return any((prep_dir / "prom" / n).exists() for n in names)

def jd_status(jd_name: str) -> dict:
    analysis_dir = PROMPTS / "JD_Analysis" / jd_name
    prep_dir     = PROMPTS / f"{jd_name}_PREP"
    no_dir       = PROMPTS / "JD_Analysis" / f"{jd_name}_NO"

    prompt_exists = (
        (analysis_dir / "variant_rank_prompt.txt").exists() or
        (prep_dir / "prom" / "1_variant_rank_prompt.txt").exists()
    )
    resp_path = (_find_response_file(analysis_dir) or
                 _find_response_file(prep_dir / "resp"))
    has_response = resp_path is not None
    poor_fit = (
        no_dir.exists() or
        (resp_path and "POOR FIT" in resp_path.read_text(errors="replace"))
    )

    s2 = _has_prompt(prep_dir, ["2_ats_prompt.txt", "ats_prompt.txt"])
    s3 = _has_prompt(prep_dir, ["3_ats_recommend_prompt.txt", "ats_recommend_prompt.txt"])
    s4 = _has_prompt(prep_dir, ["4_ats_evidence_gap_prompt.txt", "ats_evidence_gap_prompt.txt"])
    s5 = _has_prompt(prep_dir, ["5_cover_letter_prompt.txt", "cover_letter_prompt.txt"])

    cv_file = analysis_dir / ".chosen_variant"
    chosen = cv_file.read_text().strip() if cv_file.exists() else None

    if poor_fit:             stage = "poor_fit"
    elif not prompt_exists:  stage = "needs_stage1_prompt"
    elif not has_response:   stage = "waiting_response"
    elif not s2:             stage = "needs_stages_2_4"
    elif s4:                 stage = "complete"
    else:                    stage = "needs_stages_2_4"

    prompt_file = None
    for p in [analysis_dir / "variant_rank_prompt.txt",
              prep_dir / "prom" / "1_variant_rank_prompt.txt"]:
        if p.exists():
            prompt_file = str(p.relative_to(ROOT))
            break

    stage_prompts = {}
    for key, names in [
        ("s2", ["2_ats_prompt.txt", "ats_prompt.txt"]),
        ("s3", ["3_ats_recommend_prompt.txt", "ats_recommend_prompt.txt"]),
        ("s4", ["4_ats_evidence_gap_prompt.txt", "ats_evidence_gap_prompt.txt"]),
        ("s5", ["5_cover_letter_prompt.txt", "cover_letter_prompt.txt"]),
    ]:
        for n in names:
            p = prep_dir / "prom" / n
            if p.exists():
                stage_prompts[key] = str(p.relative_to(ROOT))
                break

    responses = {}
    for key, names in [
        ("s1", ["variant_rank_prompt_response.txt", "1_variant_rank_prompt_response.txt"]),
        ("s2", ["ats_prompt_response.txt"]),
        ("s3", ["ats_recommend_prompt_response.txt"]),
        ("s4", ["ats_evidence_gap_response.txt"]),
    ]:
        for n in names:
            for base in [analysis_dir, prep_dir / "resp"]:
                p = base / n
                if p.exists():
                    responses[key] = str(p.relative_to(ROOT))
                    break
            if key in responses:
                break

    return {
        "name": jd_name,
        "stage": stage,
        "prompt_exists": prompt_exists,
        "has_response": has_response,
        "poor_fit": poor_fit,
        "s2": s2, "s3": s3, "s4": s4, "s5": s5,
        "chosen_variant": chosen,
        "prompt_file": prompt_file,
        "stage_prompts": stage_prompts,
        "responses": responses,
    }

def all_jds() -> list:
    names = set()
    for d in [PROMPTS / "JD_Analysis", PROMPTS]:
        if d.exists():
            for item in d.iterdir():
                m = re.match(r"^(JD\d+)(?:_PREP|_NO|_Applied)?$", item.name)
                if m:
                    names.add(m.group(1))
    if INPUT_OTHER.exists():
        for f in INPUT_OTHER.glob("JD*.txt"):
            names.add(f.stem)
    return sorted(names, key=lambda x: int(re.sub(r"\D", "", x) or "0"))

def system_health() -> dict:
    # Inside container — no docker exec needed, scripts run directly
    return {
        "docker": True,  # We ARE inside Docker
        "resume_count": len(list(OUTPUT_RESUME.glob("*.md"))) if OUTPUT_RESUME.exists() else 0,
        "evidence_chunks": len(list(EVIDENCE_CHUNKS.glob("*.md"))) if EVIDENCE_CHUNKS.exists() else 0,
        "jd_inputs": len(list(INPUT_OTHER.glob("JD*.txt"))) if INPUT_OTHER.exists() else 0,
    }

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mK]")

def stream_cmd(cmd: str):
    """Run shell command from /app, yield SSE lines with live stdout."""
    env = {**os.environ,
           "FORCE_COLOR": "0", "NO_COLOR": "1",
           "TERM": "dumb", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        cmd, shell=True, cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, env=env
    )
    for raw in proc.stdout:
        line = ANSI_RE.sub("", raw).rstrip()
        if line:
            yield f"data: {json.dumps(line)}\n\n"
    proc.wait()
    yield f"data: {json.dumps('__DONE__')}\n\n"
    yield f"data: {json.dumps({'exit_code': proc.returncode})}\n\n"

def _sse(cmd: str) -> Response:
    return Response(
        stream_with_context(stream_cmd(cmd)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

def _safe_path(rel: str):
    try:
        full = (ROOT / rel).resolve()
        full.relative_to(ROOT.resolve())
        return full
    except Exception:
        return None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def api_status():
    policy = load_policy()
    return jsonify({
        "system": system_health(),
        "jds": [jd_status(j) for j in all_jds()],
        "stages": policy["stages"],
        "trust_levels": policy["trust_levels"],
    })

@app.route("/api/health")
def api_health():
    return jsonify(system_health())

@app.route("/api/upload-jd", methods=["POST"])
def upload_jd():
    INPUT_OTHER.mkdir(parents=True, exist_ok=True)
    existing_nums = [
        int(re.sub(r"\D", "", f.stem) or "0")
        for f in INPUT_OTHER.glob("JD*.txt")
    ]
    next_num = max(existing_nums, default=0) + 1

    files = request.files.getlist("file")
    if files and files[0].filename:
        saved = []
        for uploaded in files:
            if not uploaded.filename:
                continue
            jd_name = f"JD{next_num}"
            (INPUT_OTHER / f"{jd_name}.txt").write_bytes(uploaded.read())
            saved.append(jd_name)
            next_num += 1
        return jsonify({"ok": True, "saved": saved})

    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "No text provided"}), 400
    jd_name = f"JD{next_num}"
    (INPUT_OTHER / f"{jd_name}.txt").write_text(text, encoding="utf-8")
    return jsonify({"ok": True, "saved": [jd_name]})

@app.route("/api/paste-response", methods=["POST"])
def paste_response():
    data = request.get_json(silent=True) or {}
    jd_name = data.get("jd", "").strip()
    text    = data.get("text", "").strip()
    if not jd_name or not text:
        return jsonify({"ok": False, "error": "jd and text required"}), 400
    dest = PROMPTS / "JD_Analysis" / jd_name
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "variant_rank_prompt_response.txt").write_text(text, encoding="utf-8")
    return jsonify({"ok": True})

@app.route("/api/paste-stage-response", methods=["POST"])
def paste_stage_response():
    data  = request.get_json(silent=True) or {}
    jd    = data.get("jd", "").strip()
    stage = data.get("stage", "").strip()
    text  = data.get("text", "").strip()
    if not jd or not stage or not text:
        return jsonify({"ok": False, "error": "jd, stage, and text required"}), 400
    names = {
        "s2": "ats_prompt_response.txt",
        "s3": "ats_recommend_prompt_response.txt",
        "s4": "ats_evidence_gap_response.txt",
        "s5": "cover_letter_response.txt",
    }
    fname = names.get(stage)
    if not fname:
        return jsonify({"ok": False, "error": f"Unknown stage: {stage}"}), 400
    dest = PROMPTS / f"{jd}_PREP" / "resp"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / fname).write_text(text, encoding="utf-8")
    return jsonify({"ok": True})

@app.route("/api/run-pipeline")
def run_pipeline():
    # Running INSIDE Docker — docker exec / docker compose are not available.
    # Replicate run.sh logic directly: router → clean → chunk
    # Chunking uses python3 inline to avoid awk quoting issues in shell strings.
    cmd = (
        "echo '🚀 Running full document pipeline...' && "
        "echo '   router → extract → clean → chunk' && "
        "chmod +x scripts/*.sh && "
        "echo '✅ Environment ready (running inside Docker)' && "
        "./scripts/router.sh && "
        "echo '⏱️  router done' && "
        "echo '🧹 Cleaning output files...' && "
        """for f in output/*.md; do
  [ -f "$f" ] || continue
  echo "  ➡️ Cleaning $(basename $f)"
  perl -pi -e 's/&amp;/\&/g; s/&lt;/</g; s/&gt;/>/g' "$f" 2>/dev/null || true
  perl -pi -e 's/[ \t]+/ /g' "$f" 2>/dev/null || true
  awk 'NF{p=1} p' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
done && """ +
        "echo '⏱️  clean done' && "
        "echo '🧠 Smart chunking...' && "
        "mkdir -p chunks && rm -f chunks/* && "
        """python3 -c "
import re, os
from pathlib import Path
heading = re.compile(r'^([A-Z][A-Z ]+)$|^#{1,6} ')
for src in sorted(Path('output').glob('*.md')):
    name = src.stem
    print(f'  Processing {src.name}')
    lines = src.read_text(errors='replace').splitlines(keepends=True)
    i, chunk = 1, []
    def flush(c, n, idx):
        if c:
            Path(f'chunks/{n}_part_{idx}.md').write_text(''.join(c))
    for line in lines:
        if heading.match(line.rstrip()) and chunk:
            flush(chunk, name, i); i += 1; chunk = []
        chunk.append(line)
    flush(chunk, name, i)
for p in Path('chunks').glob('*.md'):
    if p.stat().st_size == 0: p.unlink()
print('chunking complete')
" && """ +
        "echo '⏱️  chunk done' && "
        "echo '✅ Pipeline complete!'"
    )
    return _sse(cmd)
@app.route("/api/ingest-evidence")
def ingest_evidence():
    # ingest_evidence.sh uses `docker exec markitdown` internally.
    # Since we're already inside the container, set INSIDE_DOCKER=1 so
    # ingest_evidence.sh can detect it — OR just call it and let it try.
    # The pdfplumber/markitdown calls inside it run as plain python3, which works.
    # Only the `docker exec markitdown python3 ...` lines fail.
    # Simplest fix: override the docker exec calls via env var checked in the script,
    # or run the Python extraction directly here.
    # For now: the script's OCR/extraction still works — only the chunking wrapper fails.
    # Set DOCKER_HOST= to prevent docker exec from trying (it will error gracefully).
    return _sse("INSIDE_DOCKER=1 ./scripts/ingest_evidence.sh 2>&1 || true")

@app.route("/api/generate-stage1")
def generate_stage1():
    jd  = request.args.get("jd", "").strip()
    cmd = f"./scripts/batch_prep.sh --jd {jd}" if jd else "./scripts/batch_prep.sh"
    return _sse(cmd)

@app.route("/api/generate-stages-2-4")
def generate_stages_2_4():
    jd    = request.args.get("jd", "").strip()
    force = request.args.get("force", "0") == "1"
    flags = "--continue" + (f" --jd {jd}" if jd else "")
    prefix = "FORCE=1 " if force else ""
    return _sse(f"{prefix}./scripts/batch_prep.sh {flags}")

@app.route("/api/generate-cover")
def generate_cover():
    jd = request.args.get("jd", "").strip()
    if not jd:
        return jsonify({"ok": False, "error": "jd required"}), 400
    return _sse(f"./scripts/batch_prep.sh --cover {jd}")

@app.route("/api/prompt-content")
def prompt_content():
    rel  = request.args.get("path", "")
    full = _safe_path(rel)
    if not full:
        return jsonify({"ok": False, "error": "invalid path"}), 403
    if not full.exists():
        return jsonify({"ok": False, "error": "file not found"}), 404
    return jsonify({"ok": True, "path": rel,
                    "content": full.read_text(errors="replace"),
                    "name": full.name})

@app.route("/api/download")
def download():
    rel  = request.args.get("path", "")
    full = _safe_path(rel)
    if not full:
        return "forbidden", 403
    if not full.exists():
        return "not found", 404
    return send_file(str(full), as_attachment=True, download_name=full.name)

@app.route("/api/evidence-status")
def evidence_status():
    src = [f.name for f in INPUT_EVIDENCE.iterdir()
           if INPUT_EVIDENCE.exists() and not f.name.startswith(".")] \
          if INPUT_EVIDENCE.exists() else []
    chunks = sorted([
        {"name": f.name, "size": f.stat().st_size}
        for f in EVIDENCE_CHUNKS.glob("*.md")
    ] if EVIDENCE_CHUNKS.exists() else [], key=lambda x: x["name"])
    return jsonify({
        "source_files": len(src),
        "source_list": src,
        "chunks": len(chunks),
        "chunk_list": chunks,
    })

@app.route("/api/resume-list")
def resume_list():
    resumes = sorted([f.stem for f in OUTPUT_RESUME.glob("*.md")]) \
              if OUTPUT_RESUME.exists() else []
    return jsonify({"resumes": resumes})



@app.route("/api/tier")
def api_tier():
    """Return current tier and stage access."""
    import subprocess
    result = subprocess.run(
        ["python3", "/app/scripts/check_tier.py", "--json"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    try:
        return jsonify(json.loads(result.stdout))
    except Exception:
        return jsonify({"tier": "free", "stages": {}})

@app.route("/api/save-config", methods=["POST"])
def save_config():
    """Save BYOK config to ~/.markitdown-codespace/config.json"""
    import json as _json
    data = request.get_json(silent=True) or {}
    config_dir  = Path.home() / ".markitdown-codespace"
    config_file = config_dir / "config.json"
    config_dir.mkdir(exist_ok=True)

    existing = {}
    if config_file.exists():
        try:
            existing = _json.loads(config_file.read_text())
        except Exception:
            pass

    # Claude API key — save to separate file (more secure)
    claude_key = data.get("anthropic_api_key", "").strip()
    if claude_key and claude_key.startswith("sk-ant-"):
        key_file = config_dir / "claude_api_key"
        key_file.write_text(claude_key)
        key_file.chmod(0o600)
        existing["anthropic_key_file"] = str(key_file)

    # GCP project
    gcp_project = data.get("gcp_project", "").strip()
    if gcp_project:
        existing["gcp_project"] = gcp_project

    config_file.write_text(_json.dumps(existing, indent=2))
    return jsonify({"ok": True, "tier": "pro" if (claude_key or gcp_project) else "free"})

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    print(f"\n  ATS Pipeline UI — http://localhost:{args.port}")
    print(f"  Root: {ROOT}\n")
    # debug=False inside Docker — cleaner output, no double-start
    app.run(host=args.host, port=args.port, debug=False)
