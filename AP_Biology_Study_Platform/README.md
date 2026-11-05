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

To **restore a backup**, open **Settings & Backup → Restore a complete backup**, select a previously downloaded complete ZIP, and type `RESTORE`. This replaces all current study records and uploaded originals with the backed-up version, so download a backup of current data first. Database files should not be changed by hand on a running server.

## Important limitations and privacy

- This is an **individual local app with no login**. It binds only to `127.0.0.1`; don't expose it to the internet without real authentication, HTTPS, access controls and hardening.
- Password-protected PDFs, scanned PDFs without selectable text, and slides that are only pictures may not generate useful text. If extraction fails, convert or paste teacher notes into a text file; never trust OCR blindly. Original files remain downloadable.
- Guide generation uses selected source excerpts, not a complete synthesis, unless the optional AI connection is configured.
- Quiz difficulty and knowledge/application sliders affect AI-generated questions; they don't make the local extractive generator magically create reasoning problems.
- Mastery estimates are approximate; repeated successful reviews and performance matter more than one correct answer.
- Browser session answers and lab drafts may disappear if browser storage is cleared. Submit quizzes and download lab notes to preserve important work.
- Class materials currently in **this ChatGPT Project** are not automatically available to the separately running website. The installation starts with an empty source library.

## Current GitHub + Render deployment

The public site is deployed from the existing `Awinland29/AP-Bio-Study` GitHub repository. **The `render.yaml` at the repository ROOT** controls your Render deployment plan. The user has selected Render **Free**; this release's update-only ZIP intentionally does not include or change that file. An older `render.yaml` *inside* `AP_Biology_Study_Platform/` was part of an earlier template and may describe a paid configuration; do not use it to replace the root Blueprint.

To publish an audited code update, keep the free Blueprint and commit the updated app files (`AP_Biology_Study_Platform/main.py`, `static/app.js`, `static/styles.css`) in the existing repo. Render auto-deploys GitHub `main` changes; check the web service's status and logs to confirm success. Before updating, download a complete backup from the current live website.

For a new installation, `APBIO_PUBLIC=1` requires the server environment variables `APBIO_ADMIN_USERNAME` and `APBIO_ADMIN_PASSWORD` (at least 16 characters), plus `APBIO_DATA_DIR`. Set passwords in Render **Environment**, never GitHub. `APBIO_DATA_DIR` under `/tmp` works for launching a free demonstration but **does not preserve your data across redeploys/restarts**. New releases support browser-based **Settings & Backup → Restore complete backup** to recover from a ZIP you kept elsewhere.

**Public access and privacy:** The homepage now opens without sign-in. Visitors have independent browser-linked study databases and uploads; they do **not** access the existing private owner's files. Existing owner data is available at `/owner` with the former Basic-authentication credentials, then a signed owner cookie keeps the owner in their original workspace. `/owner/logout` leaves that legacy workspace. Browser cookies are not multi-device accounts: clearing cookies, using another browser, or Render Free restarting can lose access to that visitor's data. Each visitor should download full ZIP backups. No guest can use a paid OpenAI API key, even if one is configured by the server owner. Public visitor access is not a substitute for production-grade accounts, user quotas, and durable storage; avoid uploading sensitive student information.

**Optional AI:** Set `OPENAI_API_KEY` only in the host environment when an eligible separately billed account is available. ChatGPT Plus is not an API subscription. If disabled, ordinary local study features still work and no artificial tutoring responses are shown.

**Data limitation:** No guarantee of year-long progress retention is possible on the current temporary Render Free filesystem. To guarantee persistence, use an eligible paid Render disk or implement a properly managed external database and file storage service.

---

## Development and verification

The app uses FastAPI + SQLite + plain HTML/CSS/JavaScript. For regression checks:

```bash
.venv/bin/python -m pip install pytest httpx
.venv/bin/python -m pytest -q tests/
```

All tests use isolated temporary databases, so they don't touch your study records. The frontend intentionally has no JavaScript framework build step. To change the appearance, edit `static/styles.css`; to adjust study features, edit `static/app.js` or `main.py` and restart.

---

## November 2026 reliability audit update

This source tree adds backup *restoration*, truthful Render Free warnings, multi-day mastery checks, faster flashcard reviewing, smaller default quiz setup, preserved question flags, and stricter handling of unanswered written responses. See `AUDIT_REPORT.md` for complete testing and limitations.

**If using Render Free:** Your `APBIO_DATA_DIR` under `/tmp/` is **not persistent**. Download a full ZIP backup frequently and keep it off the server. After data loss, use **Settings & Backup → Restore a complete backup**. Restoration replaces any current data with the contents of the chosen ZIP. This release adds a restore form; older versions could only export.

**Never upload any API keys, password values, real saved student data or backup ZIPs to a public GitHub repository.** Keep environment secrets in Render's Environment page. The standalone update ZIP does not contain `render.yaml`, so it does not change your plan.

Audit test commands: `python -m pytest -q` (the `tests/audit_browser.py` smoke test additionally needs Playwright and Chromium installed).

## Assignments & Schedule (Nov 2026)

- The new **Assignments & Schedule** page stores actual assignments, tests, class events and dates. Marking an assignment completed changes Biosphere only, not the school's LMS.
- Enter dates manually or import a UTF-8 `.csv` file with `Title,Due Date,Type,Start Time,End Time,Details,URL` columns; use `YYYY-MM-DD` or `MM/DD/YYYY` dates. Calendar `.ics` imports support regular event start/end times, but only the first instance of any recurring rule. Reimporting the same unchanged event is deduplicated.
- Class schedules and assignment-list documents can also be uploaded in **Course Resources** as normal files. PDFs and screenshots are stored as reference files, not magically converted into dates.
- The **Google Classroom link** field is only a shortcut to your class; it does **not** grant access or synchronize assignments. True Classroom sync requires a Google Cloud project, OAuth consent, Google API scopes and possibly approval from the school's Google Workspace administrator. Don't share login passwords with the website.
- New `schedule_entries` and `schedule_links` tables are included in complete ZIP backups and JSON exports. Older backups are migrated on restore. On Render Free, `/tmp` storage remains ephemeral, so download a fresh backup after important edits.


### Bright public study spaces (no login)

- The main site is a one-click open link, even for first-time visitors. Each browser gets a random, HTTP-only session cookie that maps to its own SQLite database and uploaded file folder. No shared public database is exposed.
- A visitor's work isn't synchronized across devices or browsers. Save **Settings & Backup → Download complete backup** regularly.
- The original password-protected owner workspace is retained for earlier course files. Open `/owner` and enter the old credentials once to access it. `/owner/logout` switches back to a public guest workspace.
- Google Classroom is still a **shortcut only**, not automatic synchronization. Assignments & Schedule can import CSV and `.ics` snapshots. Real syncing needs authorized OAuth, school approval where required, and a properly designed integration.
- Light mode has mint, warm yellow and sky accents; dark mode retains its previous contrast.
