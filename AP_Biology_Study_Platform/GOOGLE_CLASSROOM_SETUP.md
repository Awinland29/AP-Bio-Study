# Google Classroom connection — administrator setup

Biosphere provides an **optional, read-only** connection to Google Classroom assignments. You can open the site without an account; only people who choose to connect a Google account use Google OAuth. Each browser workspace has a separate connection and encrypted refresh token. It does **not** submit assignments, edit coursework, or modify Classroom grades.

## One-time Google Cloud setup

1. Open the [Google Cloud Console](https://console.cloud.google.com/), create or select a project, and enable the **Google Classroom API**.
2. In **Google Auth Platform**, configure Branding, Audience, and Data Access for your app (name **Biosphere**), and select the following *read-only* scopes:
   - `https://www.googleapis.com/auth/classroom.courses.readonly`
   - `https://www.googleapis.com/auth/classroom.coursework.me.readonly`
3. Under **Clients**, create an **OAuth 2.0 Client ID** of type **Web application**. Add this **authorized redirect URI** exactly:
   `https://ap-biology-study-studio.onrender.com/api/google-classroom/callback`
4. If testing with **External** audience, add the school Google account to the app's test-user list. Google may require app verification before general public use; testing-mode refresh tokens can expire relatively quickly. Some Google Workspace accounts cannot authorize External testing apps.
5. In the existing Render service, add these **environment variables** (never commit them to GitHub or paste a client secret into chat):
   - `GOOGLE_CLASSROOM_CLIENT_ID` — the Google OAuth client ID
   - `GOOGLE_CLASSROOM_CLIENT_SECRET` — the Google OAuth client secret
   - `GOOGLE_CLASSROOM_TOKEN_KEY` — a stable Fernet encryption key, generated with `cryptography.fernet.Fernet.generate_key()` and saved as a Render secret
   - `GOOGLE_CLASSROOM_REDIRECT_URI` — `https://ap-biology-study-studio.onrender.com/api/google-classroom/callback` (optional if the URL is unchanged)
6. After deployment, open **Assignments & Schedule → Google Classroom → Connect Google Classroom**, select the school Google account, and accept the read-only permissions. The page syncs on opening and periodically while open, and offers **Sync now** and **Disconnect**.

**School approval is separate.** Google Workspace for Education accounts designated under 18 generally cannot use an unconfigured third-party app until their school's Workspace administrator approves the OAuth app. Do not attempt to work around a school block. The admin can review the app's **OAuth client ID** and grant access in the Admin console.

## What synchronizes

- Active classes and published coursework, assignment titles/descriptions, Classroom links, deadlines, and a student's own turned-in/returned state
- Re-sync adds new items and updates existing ones using a stable Classroom ID (no duplicates)
- Course work with no deadline appears under **No due date**
- Imported Classroom items stay in Biosphere if the connection is removed; you can delete them separately
- Refresh happens when the schedule page is opened, about every five minutes while it stays open, or when **Sync now** is used. It **does not** run in the background when the site isn't open.

## Privacy, reliability and troubleshooting

- The Google OAuth callback is checked against a one-use, short-lived state and a PKCE verifier stored only in that browser's workspace.
- The refresh token is encrypted in the workspace SQLite DB using the separate encryption key. Never reuse the encryption key publicly or commit it.
- On Render Free, the database and connection can disappear after restarts/redeployments. Export a full ZIP backup regularly. The encryption key must stay stable across restores, otherwise reconnect Google.
- A **403 / admin_policy_enforced / access_not_configured** response means the school needs to approve the app. A Google Cloud OAuth testing/verification error means the developer must configure Google Auth Platform before students can connect.
- Google Classroom API access and OAuth configuration are external dependencies; enabling the code alone does **not** grant access to private Google account data.
