# Biosphere · AP Biology Study Studio — Functional Audit

**Date:** November 4, 2026  
**Scope:** The AP Biology app source from the prior public-hosting release, reviewed and improved in an isolated working copy. Render's deployment status and runtime logs had previously confirmed that the existing public app was live. This audit does **not** modify the live GitHub repository or Render production deployment.

## What was actually tested

- **20 isolated FastAPI regression tests passed** (Python `pytest`). They cover units, file upload/search/edit/download/delete, PDF/DOCX/PPTX text extraction, source-restricted card generation, spaced-review records, quiz creation/answer secrecy/objective grading/self-grading, saved guides, planner tasks, backup export and restore, validation, disabled-AI behavior, public password gate and cross-site write blocking, and data remaining after database initialization.
- **12 browser workflow checks passed** using the real HTML, CSS and JavaScript in Chromium with API requests bridged to an isolated FastAPI TestClient. They exercised the overview, desktop/mobile navigation, library unit creation and text upload, source search, flashcard review, quiz flags and submission, result display, guide creation/reopening, progress page, planner task, tutor disabled state, ET50 lab, settings/restore form, and theme. The browser reported **no JavaScript exceptions** and no mobile horizontal overflow in the tested 390px viewport.
- The browser's ordinary localhost navigation was blocked by this testing environment; requests were instead routed to the app's real API through a test bridge. This verifies UI behavior against the same backend code, **not** an authenticated end-to-end session on the live Render hostname.
- No real school files, production credentials, or personal records were used for tests. Test data was synthetic and disposable.

## Feature-by-feature findings

| Feature | Audit outcome | Scope / limitations |
|---|---|---|
| Desktop navigation, mobile menu, theme | **Passed** | Main pages work and mobile layout has no observed horizontal overflow; no exhaustive accessibility audit. |
| Units and document library | **Passed** | Create/edit/delete, upload/search/metadata/download, unsupported-file rejection tested. |
| PDF, DOCX and PPTX | **Passed for selectable text** | Figures, screenshots, handwritten text and scanned PDFs are **not** reliably interpreted. |
| Images | **Limited** | Original upload is saved; OCR availability/accuracy depends on Tesseract and quality. No reliable diagram interpretation. |
| Flashcard creation/edit/review | **Passed with improvements** | Local generator extracts source definitions and selected source sentences; it is not a semantic AI generator. Review answers for accuracy. |
| Spaced repetition/mastery | **Passed with improvement** | Due dates save correctly. 'Mastered' no longer means three clicks in one day; it requires three recent successful reviews spanning two dates. |
| Quizzes and practice tests | **Passed with caveats** | All advertised local response types are supported; objective scoring uses exact/equivalent text matching, and short answers require self-review. Some question types fall back to fill-in when sources are thin. |
| Answer protection | **Passed** | Answer keys and explanations are withheld from active quiz API responses. They appear after submission. |
| Written answer grading | **Passed with improvement** | Blank responses count as incorrect; self-grades can be adjusted. No reliable automatic free-response evaluation without external AI. |
| Timers, navigation, flags | **Partially verified** | Question navigation and preserved flags tested in a browser. Timer behavior was reviewed in code but not stress-tested across clock changes/device sleep. |
| Study guides | **Passed with limitation** | Saved/reopened/deleted and included in backup. Non-AI guides are extraction-based outlines, not comprehensive pedagogical summaries. |
| Search | **Passed** | Search inside extracted materials and card text. Image-only content not indexed reliably. |
| Progress | **Passed with improvement** | Quiz scores, subject topics, reviews and repetitions are recorded. Scores exclude unreviewed written responses; the display now explains this. Adaptive prioritization is basic, not a proven learning-science model. |
| ET50 / lab bench | **Passed with improvements** | Calculator, interpolation, graph, CSV and note controls function; default demo values are removed in favor of an explicit example. Lab drafts remain browser-local. |
| Study planner | **Passed** | Task create/completion; local server stores it. |
| Export & recovery | **Passed after new feature** | Complete ZIP backup and **validated restore** now work; archive includes uploaded file bytes. JSON export alone doesn't include uploaded files. |
| Security | **Passed for current simple password gate** | Public-mode files, APIs and backups require HTTP Basic auth, and cross-origin write requests are blocked. No per-user roles, login recovery or brute-force rate limiting. |
| AI tutor / AI-generated quizzes | **Unavailable without setup** | The app correctly refuses to fabricate conversations and requires an actual `OPENAI_API_KEY` with separate usage billing. |
| Project sync | **Not implemented** | Files from this ChatGPT Project must be uploaded manually to the website. |
| Durable data on Render Free | **Unresolved external limitation** | Render Free's temporary filesystem can be erased on restart/redeploy; the app now warns clearly and supports restoring backups, but cannot make this hosting tier durable by itself. |

## Verified code changes

1. **Full backup restoration:** Added a `POST /api/backup/restore` endpoint and a Settings upload form, with explicit confirmation, archive size/path validation, required-table/schema/integrity checks, file/database consistency checks, and a rollback snapshot for failed replacements. A successful test restored uploaded bytes, flashcards, quiz results, guides and tasks after deleting them.
2. **Honest free-hosting storage warnings:** Detected temporary data directories and added warnings in the dashboard and Settings. Removed the false implication that all Render deployments have a persistent disk, and corrected the sidebar's local/hosted label.
3. **Study flow improvements:** Flashcard grading advances to the next card; the deck manager is collapsed until needed. Less-used quiz generator options now live behind a clearly labeled disclosure, keeping common quiz setup shorter.
4. **Quiz reliability:** Flagged questions survive leaving/reopening an assessment in the same browser, and are cleared on submission. A blank written response can no longer be self-marked correct. Students can correct a written self-grade later; the score is labeled as based on **graded questions**.
5. **Better progress claims:** Mastery requires successful repeated reviews on multiple days, rather than a single session of repetitive clicks.
6. **Source isolation:** Explicit file IDs cannot bypass a selected unit when generating source-grounded resources.
7. **ET50:** Starts with clearly uncompleted measurements rather than synthetic study data, offers an explicit example button, warns before clearing, and rejects blank readings instead of silently treating them as zero.
8. **Stability and clarity:** Added a safe fallback for corrupted browser-local lab JSON, clarified the non-AI generator's limits, and noted that diagrams may not be read on upload.

## Outstanding limitations that require outside action or a larger project

**High priority — permanent data:** The currently deployed Render Free filesystem is temporary. Keep frequent backups on your Mac. To guarantee ongoing access all school year, use Render with an attached persistent disk on an eligible paid plan or move to an external persistent database + object storage service. Simply adding more code or deploying repeatedly does not solve this.

**AI:** An OpenAI API key and an eligible API billing account are required to activate the tutor and higher-quality AI-generated guides/questions. This is independent of ChatGPT Plus. With no key, source extraction and ordinary study tools still work. Don't add a secret to GitHub source code.

**Source fidelity:** Extracted PDF text misses many figures; PPTX/DOCX images are not interpreted. Images may have OCR unavailable. Teachers' answer keys cannot be independently verified without the teacher's materials, and some AI-generated questions may need manual checking.

**Accessibility and stress testing:** Screen-reader navigation, hundreds of simultaneous users, large archive performance, server clock jumps, and deployment on every platform are not comprehensively tested. The system is best suited to one personal account.

**Live verification/deployment:** I have not tested an authenticated live Render user session or your real school materials, and I have not pushed these changes to GitHub. The passing tests are for this **audited update package**. The production site remains on the earlier revision until the update files are committed and Render successfully redeploys.

## Safe deployment instructions

1. **Before any update, open your current website → Settings & Backup → Download complete backup (.zip)** and keep that file in your Downloads or cloud drive. This is especially important on Render Free.
2. Extract the companion **AP_Bio_Audit_Fixes_GitHub_Update.zip** package. It only contains updated application files and tests; **it does not replace `render.yaml`**, which controls your free hosting plan.
3. Commit the updated files under your existing GitHub repo's `AP_Biology_Study_Platform/` folder. The essential changed files are `main.py`, `static/app.js`, and `static/styles.css`. You can also add this report and the new test file. Keep the existing `render.yaml` at the repository root untouched.
4. Render is configured to auto-deploy `main`, so after committing, check your Render service for a successful deployment and reload the live site. Your login credentials stay configured in Render Environment, not GitHub.
5. In the updated site, visit Settings & Backup to confirm the **Restore** form exists; create a harmless test unit and backup to verify recovery before trusting this workflow with your only copy of important notes.

**Recovery safety:** Restore **replaces**, not merges, the current server's study database and uploaded files. Download a new complete backup before attempting restore.
