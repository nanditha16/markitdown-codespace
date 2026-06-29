# Setting Up the ATS Pipeline — Step by Step

This guide gets you from zero to a running web app with no prior technical knowledge required.
Estimated time: **15–30 minutes**, mostly waiting for downloads.

---

## What you need before starting

You need three things installed on your computer. All are free.

| What | Why | Mac | Windows |
|------|-----|-----|---------|
| **Git** | To download the source code | Usually pre-installed | Download from git-scm.com |
| **Docker Desktop** | Runs the pipeline in a safe container | docker.com/products/docker-desktop | docker.com/products/docker-desktop |
| **A terminal** | To run a few commands | Built-in (Terminal app) | Windows Terminal or Git Bash |

---

## Step 1 — Install Git

**Mac:**
Open Terminal (press Cmd+Space, type "Terminal", press Enter) and run:
```
git --version
```
If you see a version number, Git is already installed. If you see an error, run:
```
xcode-select --install
```
A popup will appear — click Install and wait for it to finish.

**Windows:**
Download and install from: https://git-scm.com/download/win
Use all the default options during installation.

---

## Step 2 — Install Docker Desktop

1. Go to: https://www.docker.com/products/docker-desktop
2. Click **Download Docker Desktop** for your operating system
3. Open the downloaded file and follow the installer
4. Once installed, **open Docker Desktop** from your Applications folder (Mac) or Start menu (Windows)
5. Wait for the Docker whale icon to appear in your menu bar / taskbar and show "Docker Desktop is running"

> ⚠️ Docker Desktop must be **open and running** every time you use this app.

**Mac note:** macOS uses port 5000 for AirPlay. This app uses port 5001 to avoid that conflict — no action needed on your part, just be aware.

---

## Step 3 — Download the source code

Open Terminal and run these commands one at a time:

```bash
cd <YOUR_CHOSEN_FOLDER>
git clone https://github.com/nanditha16/markitdown-codespace.git
cd markitdown-codespace
```

You should now see a folder called `markitdown-codespace` in your chosen directory.

---

## Step 3b — Configure your local paths

This step tells Docker where to find your credentials on your specific machine.

```bash
cp .env.example .env
```

Open the `.env` file in any text editor and set your paths:

**Mac/Linux:**
```
GCLOUD_CONFIG_DIR=~/.config/gcloud
MARKITDOWN_CODESPACE_DIR=~/.markitdown-codespace
```

**Windows (Git Bash or Windows Terminal):**
```
GCLOUD_CONFIG_DIR=C:/Users/YOURNAME/.config/gcloud
MARKITDOWN_CODESPACE_DIR=C:/Users/YOURNAME/.markitdown-codespace
```
Replace `YOURNAME` with your Windows username (e.g. `john`).

> ⚠️ On Windows, use forward slashes (`/`) not backslashes (`\`).

> ℹ️ The `.env` file is personal — it is listed in `.gitignore` and will never be committed to GitHub.

---

## Step 4 — Run the one-time setup

Still in Terminal, run:

**Mac/Linux:**
```bash
chmod +x scripts/*.sh
./scripts/setup.sh
```

**Windows (Git Bash):**
```bash
./scripts/setup.sh
```
> ℹ️ `chmod` is not needed on Windows — Git Bash handles script permissions automatically.

This will:
- Check that Docker is running
- Download and build the pipeline environment (takes 5–10 minutes the first time)
- Set up all the necessary tools inside Docker

You'll see a lot of text scrolling — that's normal. Wait until you see:
```
✅ Setup complete
```

> If you see `❌ Docker is not running` — make sure Docker Desktop is open and the whale icon shows "running", then try again.

---

## Step 5 — Start the web app

```bash
./scripts/serve.sh
```

Your browser should open automatically to `http://localhost:5001`

If it doesn't open automatically, open your browser and go to: **http://localhost:5001**

You should see the ATS Pipeline interface with a system check showing green checkmarks.

---

## Step 6 — Add your resume files (first time only)

Before using the app, add your resume PDF files:

1. Find the `markitdown-codespace` folder on your computer
2. Open the `input` folder inside it
3. Open the `pdf` folder
4. Copy your resume PDF files into this folder

Then go back to the web app and click **"Run pipeline (run.sh)"** on the Setup page.
This converts your PDFs to the format the system needs. Wait for it to finish (1–2 minutes).

5. create a folder 'output/resume'
    ```
    mkdir output/resume
    ```
6. move teh resume variant .md files to output/resume

NOTE: Cluade.ai is default, but prompts can be used on any platform

---

## Step 7 — Add your career evidence files (first time only)

Your career evidence files (Career_Wealth.xlsx, project notes, PDFs of past work) go here:

```
markitdown-codespace/input/evidence/
```

After adding files, click **"Refresh evidence"** on the Setup page.
This only needs to be done once, or when you add new evidence files.

---

## Every time you use the app

1. Open Docker Desktop and wait for it to show "running"
2. Open Terminal
3. Run:
   ```bash
   # Mac/Linux:
   cd <YOUR_CHOSEN_FOLDER>/markitdown-codespace

   # Windows (Git Bash):
   cd <YOUR_CHOSEN_FOLDER>/markitdown-codespace

   ./scripts/serve.sh
   ```
4. Go to http://localhost:5001 in your browser
5. Press Ctrl+C in Terminal when you're done to stop the app
6. After each batch run, you can shutdown
    ```
    docker compose down
    ```
---

## Troubleshooting

**"Docker is not running"**
→ Open Docker Desktop from your Applications/Start menu and wait for it to fully start

**"port 5001 already in use"**
→ Another app is using that port.
- **Mac/Linux:** Run `lsof -i :5001` to see what it is, then close that app
- **Windows:** Run `netstat -ano | findstr :5001` to find the process, then close it

**"No such file or directory: ./scripts/serve.sh"**
→ You're not in the right folder.
- **Mac/Linux:** Run `cd ~/markitdown-codespace`
- **Windows:** Run `cd $HOME/markitdown-codespace`

**The browser shows a blank page**
→ Wait 10 seconds and refresh. The app takes a moment to start inside Docker

**Stage 2 API returns "Reauthentication is needed"** (Vertex AI users)
→ Your gcloud token expired. Run on your **local terminal** (not inside Docker):
```bash
gcloud auth application-default login
```
Then restart the server (`./scripts/serve.sh`). The Docker container picks up the
refreshed credentials automatically — no rebuild needed. Tokens typically last
several hours; this will happen occasionally during active use.

**Stage 2 API returns "invalid x-api-key"** (Claude users)
→ The key file contains extra text (filename or newline appended). Fix it:

**Mac/Linux:**
```bash
printf 'sk-ant-api03-YOUR_KEY_HERE' > ~/.markitdown-codespace/claude_api_key
chmod 600 ~/.markitdown-codespace/claude_api_key
wc -c ~/.markitdown-codespace/claude_api_key   # should be ~108 chars, not more
```

**Windows (Git Bash):**
```bash
printf 'sk-ant-api03-YOUR_KEY_HERE' > $HOME/.markitdown-codespace/claude_api_key
wc -c $HOME/.markitdown-codespace/claude_api_key   # should be ~108 chars, not more
```

Always use `printf` not `echo` — echo on some systems appends a newline or
the shell may concatenate extra text. If the count is much higher than 108,
the file contains more than just the key.

**Stage 2 API returns "No API key configured"** after adding your GCP project
→ Restart the server after saving Settings. Flask needs to reload to pick up
the new config. If it persists, verify your GCP project is set:
```bash
docker exec markitdown python3 -c "
import json; d=json.load(open('/root/.config/gcloud/application_default_credentials.json'))
print(d.get('quota_project_id'))
"
```

**"Cannot connect to Docker"**
→ Docker Desktop isn't running. Open it from your Applications folder

**First time setup takes too long (>15 min)**
→ Normal on slow internet — the setup downloads ~2GB of AI models. Leave it running.

---

## What each folder does

```
markitdown-codespace/
├── input/
│   ├── pdf/          ← Put your resume PDFs here
│   ├── evidence/     ← Put Career_Wealth.xlsx and project notes here
│   └── other/        ← JD text files go here (the app manages these)
├── output/
│   ├── resume/       ← Converted resume files (auto-generated)
│   └── ...
└── prompts/          ← All generated prompts live here (auto-managed)
```

You only ever need to touch `input/pdf/` and `input/evidence/`. Everything else is managed by the app.

---

## System requirements

| | Minimum | Recommended |
|--|---------|-------------|
| **RAM** | 8 GB | 16 GB |
| **Storage** | 10 GB free | 20 GB free |
| **OS** | macOS 12+ or Windows 10/11 | macOS 13+ |
| **Internet** | Required for first setup and Claude.ai | — |

---

## Getting help

If something isn't working, share the error message you see in the Terminal with whoever gave you access to this tool. The error message is the key piece of information — a screenshot of the terminal window is the easiest way to share it.
