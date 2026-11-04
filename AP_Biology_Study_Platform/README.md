# AP Biology Study Studio

A personal, locally hosted AP Biology study website. It is a working full-stack application, **not** a static HTML mockup.

## Fastest way to open it

**Mac:** Unzip the folder. Double-click `start_mac.command` inside `AP_Biology_Study_Platform` (or use Terminal: `bash start_mac.command`). On the first launch it creates an isolated Python environment and installs dependencies, so internet access is needed for setup. If macOS blocks the `.command` file, use Terminal and run `bash start_mac.command` from this folder. Python 3.10+ is recommended.

**Windows:** Unzip the folder and double-click `start_windows.bat`. Install Python 3 first if you don't have it. For best compatibility use Python 3.11–3.13; check “Add Python to PATH” during installation.

**Linux / manual:**

```bash
cd AP_Biology_Study_Platform
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python start.py
```

The app attempts to open your browser automatically at **http://127.0.0.1:8000**. If it doesn't, open that address yourself. Leave the launcher running while studying; press `Ctrl+C` or close its Terminal window to stop the server. The URL works **only on the computer running the app**, not as a public shareable link. No hosting or account is needed for local study.

## Get started

1. Open **My Library → + New unit**, e.g. `Unit 3 — Cellular Energetics`.
2. Upload teacher-supplied TXT, PDF, DOCX, PPTX, image or other supported material. Enter its unit, topic and lesson.
3. Go to **Flashcards**, **Practice & Tests**, or **Study Guides**. Select the unit and, where available, individual source files.
4. Flip flashcards and rate each recall attempt; open your test results and work through weak topics. The app preserves this data for later sessions.
5. Try **Lab Bench** for an interactive ET₅₀ estimate and graph. Note that its draft data uses browser storage, so use **Export CSV** and **Export notes** for backup.
6. Download a full data backup regularly from **Settings & Backup**.

### What works without a paid AI service

- Persistent unit management; searchable file library and original-file downloads
- Text extraction for selectable-text PDF, DOCX, PPTX, TXT, MD, CSV, JSON; optional OCR on images
- Extractive source-linked flashcards with manual edits, bookmarks, and a spaced-review scheduler
- Source-based practice quizzes and tests with multiple-choice, multi-select, true/false, matching, fill-in, and written items; timers, flagged questions, answer secrecy and result explanations
- Accurate automatic grading for objective items; **written responses are self-reviewed** against a rubric/answer
- Source-extractive study guides, available for later reopening; topic performance, mistake prioritization, study tasks, ET₅₀ lab calculator
- Full backup archive and JSON export

The **local quiz generator is not a substitute for an AI reasoning engine**. It assembles reliable recall and matching questions from explicit text in your materials; it may yield fewer than the requested number of questions, and it does not promise higher-order application questions without AI. Generated content should always be checked against your teacher’s documents.

### Optional AI tutor and advanced study tools

AI-powered tutor conversations, deeper guides, more diverse flashcards, and application-based quiz questions require a separate OpenAI API key and an active paid API billing arrangement. **ChatGPT Plus does not include API credits**. The key is read only by the local Python server; **do not put it into website JavaScript or commit it to a repository**.

On Mac/Linux, in Terminal before starting:

```bash
export OPENAI_API_KEY="YOUR_KEY_HERE"
export OPENAI_MODEL="gpt-4.1-mini"   # optional; choose a model enabled for your API account
./run.sh
```

On Windows Command Prompt (after dependencies installed):

```bat
set OPENAI_API_KEY=YOUR_KEY_HERE
.venv\Scripts\python.exe start.py
```

When the API is active, relevant excerpts from uploaded material and your questions are sent to the API to generate responses. Review class/privacy policies before enabling this feature. Uploaded content is **not** automatically synced from ChatGPT Projects; upload the materials into this website separately. Treat all generated educational content as something you should verify.

### Where your work is saved

- `data/study.sqlite3`: units, cards, quiz attempts/results, written guides, tasks, source text and tutor history
- `data/uploads/`: the original uploaded files
- Browser local storage: temporary quiz answers, theme preference, and lab draft

To **restore a backup**, stop the server, unzip the downloaded backup and replace `data/study.sqlite3` and `data/uploads/` with the files from the archive, then restart. **Keep a copy of the previous data first.** The database is initialized on first run; do not delete it unless you intend to reset everything.

## Important limitations and privacy

- This is an **individual local app with no login**. It binds only to `127.0.0.1`; don't expose it to the internet without real authentication, HTTPS, access controls and hardening.
- Password-protected PDFs, scanned PDFs without selectable text, and slides that are only pictures may not generate useful text. If extraction fails, convert or paste teacher notes into a text file; never trust OCR blindly. Original files remain downloadable.
- Guide generation uses selected source excerpts, not a complete synthesis, unless the optional AI connection is configured.
- Quiz difficulty and knowledge/application sliders affect AI-generated questions; they don't make the local extractive generator magically create reasoning problems.
- Mastery estimates are approximate; repeated successful reviews and performance matter more than one correct answer.
- Browser session answers and lab drafts may disappear if browser storage is cleared. Submit quizzes and download lab notes to preserve important work.
- Class materials currently in **this ChatGPT Project** are not automatically available to the separately running website. The installation starts with an empty source library.

## Deploy as a private study website with a public HTTPS URL (Render)

**This step requires your own Render account and approval of any charges.** The
`render.yaml` Blueprint uses the **paid Starter** web service with a 1 GB
persistent disk. The free Render web service cannot preserve the local SQLite
database or uploaded files across restarts. Check current pricing before you
approve a deployment. Render supplies a live `https://...onrender.com` URL once
its deployment finishes; no domain/URL is pre-created by this downloaded ZIP.

1. Create a **private GitHub repository** and upload the *contents* of this
   `AP_Biology_Study_Platform` folder, including `render.yaml` and `main.py`.
   `.gitignore` excludes your study database and uploaded teacher materials.
   Do not commit API keys, passwords, database files, student information or
   teacher materials.
2. Sign in to [Render](https://dashboard.render.com/), connect your GitHub
   account, and select **New → Blueprint**. Choose your repository. Review the
   requested paid Starter service and persistent disk before approval.
3. Render prompts for **APBIO_ADMIN_PASSWORD**. Enter a unique password at
   least 16 characters long; save it in your password manager. Username defaults
   to `student` (change **APBIO_ADMIN_USERNAME** in Render Environment to
   customize it). Do not paste passwords in ChatGPT.
4. After Render reports the site live, open the HTTPS URL it actually supplies.
   Your browser prompts for the username and password. The whole website,
   including downloads, is protected with HTTP Basic authentication. Do not
   disable the authentication middleware or expose the app via plain HTTP.
5. Create units and upload the materials from your local website again, or
   restore manually if you have a previous backup. There is no automatic local
   or ChatGPT Project sync. To add optional tutoring, configure `OPENAI_API_KEY`
   **only in Render's secret Environment settings**; a separate paid API account
   is required.
6. Use **Settings → Download complete backup** regularly. A disk offers
   persistence, not a substitute for your own backups. Restore currently
   requires access to the server's files and restarting it.

**Security scope:** This is a single-user, password-protected personal study
site, not a multi-user school portal. Render terminates HTTPS. The application
requires a strong password for public mode, rejects cross-site write requests,
and never exposes its AI key in frontend code. Use only with permission to
upload your teacher's materials to a third-party hosting provider. Anyone who
knows your password can access your notes and progress; change it in Render
if it's exposed. On first deploy there are no default study materials.

**If you do not want hosting charges:** keep using the local version. A stable
free hosting setup for this SQLite-plus-file-upload architecture is not included.

---

## Development and verification

The app uses FastAPI + SQLite + plain HTML/CSS/JavaScript. For regression checks:

```bash
.venv/bin/python -m pip install pytest httpx
.venv/bin/python -m pytest -q tests/
```

All tests use isolated temporary databases, so they don't touch your study records. The frontend intentionally has no JavaScript framework build step. To change the appearance, edit `static/styles.css`; to adjust study features, edit `static/app.js` or `main.py` and restart.
